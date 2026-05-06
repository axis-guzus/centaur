"""firewall-manager: control-plane sidecar for iron-proxy.

Exposes the same HTTP API as the legacy mitmproxy-based firewall, but instead
of mutating in-process state it rewrites the iron-proxy YAML config and
triggers a hot reload via iron-proxy's management API.

Endpoints:
  GET  /health         — liveness, no auth
  GET  /health/detail  — bearer-auth, last-reload state
  POST /injection-map  — bearer-auth, replaces the host→keys allowlist;
                         rewrites proxy.yaml and POSTs /v1/reload to iron-proxy

Note: unlike the legacy mitmproxy firewall, this service does NOT expose a
``/secrets/{key}`` passthrough — callers that need raw secrets should hit
the secrets service (``$SECRET_MANAGER_URL/secrets/{key}``) directly.
"""
from __future__ import annotations

import json
import os
import sys
import tempfile
import threading
import time
import urllib.parse
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from typing import Any

import httpx
import structlog
import yaml

CONTROL_TOKEN = os.environ.get("FIREWALL_CONTROL_TOKEN", "").strip()
HEALTH_PORT = int(os.environ.get("FIREWALL_MANAGER_PORT", "8081"))
SECRET_MANAGER_URL = os.environ.get("SECRET_MANAGER_URL", "http://secrets:8100").rstrip("/")
SECRETS_AUTH_TOKEN = os.environ.get("SECRETS_AUTH_TOKEN", "").strip()
if not SECRETS_AUTH_TOKEN:
    raise SystemExit(
        "SECRETS_AUTH_TOKEN is not set. Refusing to start: the secrets service "
        "requires bearer auth on /secrets/{key}/ref lookups."
    )
IRON_PROXY_CONFIG_PATH = Path(os.environ.get("IRON_PROXY_CONFIG_PATH", "/etc/iron-proxy/proxy.yaml"))
IRON_PROXY_MANAGEMENT_URL = os.environ.get("IRON_PROXY_MANAGEMENT_URL", "http://iron-proxy:9092").rstrip("/")
IRON_MANAGEMENT_API_KEY = os.environ.get("IRON_MANAGEMENT_API_KEY", "").strip()
SECRET_SOURCE = os.environ.get("FIREWALL_MANAGER_SECRET_SOURCE", "env").strip().lower()
SECRET_TTL = os.environ.get("FIREWALL_MANAGER_SECRET_TTL", "10m").strip()

# Headers iron-proxy will scan for proxy_value placeholders.  Literal
# strings match a single header name; values wrapped in /.../ are
# interpreted as regexes.
DEFAULT_MATCH_HEADERS: tuple[str, ...] = (
    "Authorization",
    "Proxy-Authorization",
    "Api-Key",
    "Anthropic-Api-Key",
    "Auth-Token",
    "Jwt",
    "Cookie",
    "/^x-[a-z0-9-]*(api-key|apikey|secret|token|auth)$/",
)

log = structlog.get_logger("firewall-manager")


def _fetch_secret_ref(key: str) -> str | None:
    """Ask the secrets service for a backend-native reference to a key.

    Returns ``None`` when the secrets service doesn't know the key or has
    no ref metadata for it (env-backed secrets, etc).
    """
    url = f"{SECRET_MANAGER_URL}/secrets/{urllib.parse.quote(key, safe='')}/ref"
    headers = {"Authorization": f"Bearer {SECRETS_AUTH_TOKEN}"}
    try:
        with httpx.Client(timeout=3.0) as client:
            resp = client.get(url, headers=headers)
    except httpx.HTTPError as exc:
        log.warning("ref_fetch_error", key=key, error=str(exc))
        return None
    if resp.status_code == 404:
        return None
    if resp.status_code != 200:
        log.warning("ref_fetch_status", key=key, status=resp.status_code)
        return None
    ref = resp.json().get("ref")
    return ref if isinstance(ref, str) and ref else None


def _build_source(key: str) -> dict[str, str] | None:
    """Translate a centaur key name to iron-proxy's secret source schema.

    Returns ``None`` when the source can't be built — e.g. 1P mode but the
    secrets service has no ref metadata for this key. Callers should skip
    such keys so iron-proxy doesn't get a malformed reference.
    """
    if SECRET_SOURCE == "onepassword":
        ref = _fetch_secret_ref(key)
        if ref is None:
            return None
        return {
            "type": "1password",
            "secret_ref": ref,
            "ttl": SECRET_TTL,
        }
    return {"type": "env", "var": key}


def _build_secret_transform(injection_map: dict[str, list[str]]) -> dict[str, Any] | None:
    """Convert {host: [keys]} → an iron-proxy `secrets` transform block.

    Inverts the map so each key gets one entry with all its allowed hosts as
    rules.  Returns None when the map (or every key in it) yields no usable
    sources, so callers can omit the transform entirely.
    """
    by_key: dict[str, list[str]] = {}
    for host, keys in injection_map.items():
        for key in keys:
            by_key.setdefault(key, []).append(host)

    if not by_key:
        return None

    secrets = []
    for key in sorted(by_key):
        source = _build_source(key)
        if source is None:
            log.warning("skipping_key_without_source", key=key)
            continue
        hosts = sorted(set(by_key[key]))
        secrets.append({
            "source": source,
            "proxy_value": key,
            "match_headers": list(DEFAULT_MATCH_HEADERS),
            "rules": [{"host": h} for h in hosts],
        })

    if not secrets:
        return None
    return {"name": "secrets", "config": {"secrets": secrets}}


def _render_config(injection_map: dict[str, list[str]]) -> str:
    """Load proxy.yaml, splice the new `secrets` transform in, dump as YAML.

    Other transforms (allowlist, log config, listeners) are preserved
    verbatim so this service stays a single-purpose translator.
    """
    with IRON_PROXY_CONFIG_PATH.open("r") as f:
        cfg = yaml.safe_load(f) or {}

    transforms = list(cfg.get("transforms") or [])
    transforms = [t for t in transforms if (t or {}).get("name") != "secrets"]

    secret_transform = _build_secret_transform(injection_map)
    if secret_transform is not None:
        transforms.append(secret_transform)

    cfg["transforms"] = transforms
    return yaml.safe_dump(cfg, sort_keys=False)


def _atomic_write(path: Path, content: str) -> None:
    """Write content to path via a same-directory temp + rename(2)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(prefix=".proxy.yaml.", dir=str(path.parent))
    try:
        with os.fdopen(fd, "w") as f:
            f.write(content)
        os.replace(tmp_name, path)
    except Exception:
        try:
            os.unlink(tmp_name)
        except FileNotFoundError:
            pass
        raise


def _trigger_iron_proxy_reload() -> None:
    headers = {"Authorization": f"Bearer {IRON_MANAGEMENT_API_KEY}"} if IRON_MANAGEMENT_API_KEY else {}
    with httpx.Client(timeout=5.0) as client:
        resp = client.post(f"{IRON_PROXY_MANAGEMENT_URL}/v1/reload", headers=headers)
        resp.raise_for_status()


class State:
    def __init__(self) -> None:
        self.lock = threading.Lock()
        self.last_map: dict[str, list[str]] = {}
        self.last_pushed_wall: float | None = None
        self.last_pushed_monotonic: float | None = None
        self.consecutive_failures = 0
        self.ever_pushed = False


state = State()


class Handler(BaseHTTPRequestHandler):
    def _check_auth(self) -> bool:
        if self.headers.get("Authorization", "") == f"Bearer {CONTROL_TOKEN}":
            return True
        self._json(403, {"error": "forbidden"})
        return False

    def _json(self, status: int, body: dict[str, Any]) -> None:
        data = json.dumps(body).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def _health_detail(self) -> dict[str, Any]:
        with state.lock:
            last_wall = state.last_pushed_wall
            last_mono = state.last_pushed_monotonic
            failures = state.consecutive_failures
            ever = state.ever_pushed
            host_count = len(state.last_map)
            key_count = sum(len(v) for v in state.last_map.values())
        age_s = round(time.monotonic() - last_mono, 3) if last_mono is not None else None
        return {
            "status": "ok",
            "injection_map_hosts": host_count,
            "injection_map_keys": key_count,
            "injection_map_loaded": ever,
            "injection_map_age_s": age_s,
            "injection_map_last_success_unix": last_wall,
            "injection_map_consecutive_failures": failures,
            "iron_proxy_management_url": IRON_PROXY_MANAGEMENT_URL,
        }

    def do_GET(self) -> None:  # noqa: N802 (BaseHTTPRequestHandler API)
        if self.path == "/health":
            self._json(200, {"status": "ok"})
            return
        if self.path == "/health/detail":
            if not self._check_auth():
                return
            self._json(200, self._health_detail())
            return
        self._json(404, {"error": "not found"})

    def do_POST(self) -> None:  # noqa: N802
        if self.path != "/injection-map":
            self._json(404, {"error": "not found"})
            return
        if not self._check_auth():
            return

        length = int(self.headers.get("Content-Length", 0) or 0)
        raw = self.rfile.read(length) if length else b""
        try:
            data = json.loads(raw.decode())
        except json.JSONDecodeError as exc:
            self._json(400, {"error": f"invalid json: {exc}"})
            return
        if not isinstance(data, dict):
            self._json(400, {"error": "body must be a JSON object {host: [keys]}"})
            return

        normalized: dict[str, list[str]] = {}
        for host, keys in data.items():
            if not isinstance(host, str) or not isinstance(keys, list):
                self._json(400, {"error": "each value must be a list of key names"})
                return
            normalized[host] = [k for k in keys if isinstance(k, str)]

        try:
            rendered = _render_config(normalized)
            _atomic_write(IRON_PROXY_CONFIG_PATH, rendered)
            _trigger_iron_proxy_reload()
        except FileNotFoundError as exc:
            with state.lock:
                state.consecutive_failures += 1
            log.error("config_missing", path=str(IRON_PROXY_CONFIG_PATH), error=str(exc))
            self._json(503, {"error": f"iron-proxy config not found at {IRON_PROXY_CONFIG_PATH}"})
            return
        except httpx.HTTPError as exc:
            with state.lock:
                state.consecutive_failures += 1
            log.error("iron_proxy_reload_failed", error=str(exc))
            self._json(502, {"error": f"iron-proxy reload failed: {exc}"})
            return
        except Exception as exc:  # noqa: BLE001 — surface render errors to caller
            with state.lock:
                state.consecutive_failures += 1
            log.error("injection_map_apply_failed", error=str(exc))
            self._json(500, {"error": str(exc)})
            return

        with state.lock:
            state.last_map = normalized
            state.last_pushed_wall = time.time()
            state.last_pushed_monotonic = time.monotonic()
            state.consecutive_failures = 0
            state.ever_pushed = True
        log.info(
            "injection_map_applied",
            hosts=len(normalized),
            keys=sum(len(v) for v in normalized.values()),
        )
        self._json(200, {"status": "ok"})

    def log_request(self, code: int | str = "-", size: int | str = "-") -> None:  # noqa: ARG002
        client = self.client_address[0] if self.client_address else "?"
        log.info(
            "http_request",
            method=getattr(self, "command", "?"),
            path=getattr(self, "path", "?"),
            status=code,
            client=client,
        )

    def log_message(self, fmt: str, *args: Any) -> None:  # noqa: ARG002
        return


def main() -> None:
    structlog.configure(
        processors=[
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso", utc=True),
            structlog.processors.JSONRenderer(),
        ]
    )
    if not CONTROL_TOKEN:
        log.error("control_token_missing")
        sys.stderr.write(
            "FIREWALL_CONTROL_TOKEN is not set. Refusing to start: "
            "an empty token would leave /injection-map unauthenticated.\n"
        )
        sys.exit(1)
    if not IRON_MANAGEMENT_API_KEY:
        log.error("iron_management_api_key_missing")
        sys.stderr.write("IRON_MANAGEMENT_API_KEY is not set — refusing to start.\n")
        sys.exit(1)

    log.info(
        "firewall_manager_starting",
        port=HEALTH_PORT,
        config=str(IRON_PROXY_CONFIG_PATH),
        management_url=IRON_PROXY_MANAGEMENT_URL,
        secret_source=SECRET_SOURCE,
    )
    server = HTTPServer(("0.0.0.0", HEALTH_PORT), Handler)
    server.serve_forever()


if __name__ == "__main__":
    main()
