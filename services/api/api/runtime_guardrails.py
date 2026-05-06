from __future__ import annotations

import os
import time
from copy import deepcopy
from urllib.parse import quote

import httpx

from api.firewall import secrets_headers, secrets_url


_PROVIDER_PROBE_KEYS = (
    "ANTHROPIC_API_KEY",
    "OPENAI_API_KEY",
)
_OPENAI_MODELS_URL = "https://api.openai.com/v1/models"
_ANTHROPIC_MODELS_URL = "https://api.anthropic.com/v1/models"
_DEFAULT_CREDENTIAL_CACHE_SECONDS = 30.0
_credential_cache_report: dict[str, object] | None = None
_credential_cache_key: tuple[object, ...] | None = None
_credential_cache_expires_at = 0.0


def _parse_secret_key_list(raw: str) -> list[str]:
    return [k.strip() for k in raw.split(",") if k.strip()]


def _unique_keys(keys: list[str]) -> list[str]:
    return list(dict.fromkeys(keys))


def _exception_code(exc: Exception) -> str:
    return exc.__class__.__name__


def _credential_cache_seconds() -> float:
    raw = os.getenv(
        "RUNTIME_CREDENTIAL_CHECK_CACHE_SECONDS",
        str(int(_DEFAULT_CREDENTIAL_CACHE_SECONDS)),
    )
    try:
        return max(0.0, float(raw))
    except ValueError:
        return _DEFAULT_CREDENTIAL_CACHE_SECONDS


def reset_runtime_credential_cache() -> None:
    global _credential_cache_report, _credential_cache_key, _credential_cache_expires_at

    _credential_cache_report = None
    _credential_cache_key = None
    _credential_cache_expires_at = 0.0


def runtime_credential_guard_enabled() -> bool:
    return os.getenv("RUNTIME_CREDENTIAL_GUARD_ENABLED", "0").strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }


def required_runtime_secret_keys() -> list[str]:
    raw = os.getenv("REQUIRED_RUNTIME_SECRET_KEYS", "AMP_API_KEY")
    return _parse_secret_key_list(raw)


def runtime_credential_probe_keys(required_keys: list[str]) -> list[str]:
    raw = os.getenv("RUNTIME_CREDENTIAL_PROBE_KEYS", "").strip()
    if raw:
        return _unique_keys(
            [key for key in _parse_secret_key_list(raw) if key in _PROVIDER_PROBE_KEYS]
        )

    required_provider_keys = [
        key for key in required_keys if key in _PROVIDER_PROBE_KEYS
    ]
    return _unique_keys(required_provider_keys)


def _runtime_credential_cache_key(
    *,
    enabled: bool,
    required_keys: list[str],
    probe_keys: list[str],
) -> tuple[object, ...]:
    return (
        enabled,
        tuple(required_keys),
        tuple(probe_keys),
        secrets_url(),
        os.getenv("SECRETS_AUTH_TOKEN", ""),
    )


def _provider_name_for_key(key: str) -> str | None:
    if key == "OPENAI_API_KEY":
        return "openai"
    if key == "ANTHROPIC_API_KEY":
        return "anthropic"
    return None


async def _probe_provider_key(
    client: httpx.AsyncClient,
    *,
    key: str,
    value: str,
) -> dict[str, object]:
    if key == "OPENAI_API_KEY":
        response = await client.get(
            _OPENAI_MODELS_URL,
            headers={"Authorization": f"Bearer {value}"},
        )
        status = (
            "invalid"
            if response.status_code in {401, 403}
            else "ok"
            if response.status_code in {200, 429}
            else "error"
        )
        return {
            "provider": "openai",
            "status": status,
            "http_status": response.status_code,
        }

    if key == "ANTHROPIC_API_KEY":
        response = await client.get(
            _ANTHROPIC_MODELS_URL,
            headers={
                "x-api-key": value,
                "anthropic-version": "2023-06-01",
                "content-type": "application/json",
            },
        )
        status = (
            "invalid"
            if response.status_code in {401, 403}
            else "ok"
            if response.status_code in {200, 429}
            else "error"
        )
        return {
            "provider": "anthropic",
            "status": status,
            "http_status": response.status_code,
        }

    raise ValueError(f"unsupported provider probe key: {key}")


async def check_runtime_credentials(*, force_refresh: bool = False) -> dict[str, object]:
    global _credential_cache_report, _credential_cache_key, _credential_cache_expires_at

    enabled = runtime_credential_guard_enabled()
    required_keys = required_runtime_secret_keys()
    probe_keys = runtime_credential_probe_keys(required_keys)
    keys = _unique_keys([*required_keys, *probe_keys])
    cache_key = _runtime_credential_cache_key(
        enabled=enabled,
        required_keys=required_keys,
        probe_keys=probe_keys,
    )
    now = time.monotonic()
    if (
        not force_refresh
        and _credential_cache_report is not None
        and _credential_cache_key == cache_key
        and now < _credential_cache_expires_at
    ):
        return deepcopy(_credential_cache_report)

    if not enabled:
        report = {
            "enabled": False,
            "status": "skipped",
            "required_keys": required_keys,
            "checked_keys": keys,
            "probe_keys": probe_keys,
            "missing_keys": [],
            "invalid_keys": [],
            "errors": [],
            "key_lengths": {},
            "keys": {},
        }
        _credential_cache_report = deepcopy(report)
        _credential_cache_key = cache_key
        _credential_cache_expires_at = now + _credential_cache_seconds()
        return report

    secrets_base = secrets_url()
    auth_headers = secrets_headers()
    missing_keys: list[str] = []
    invalid_keys: list[str] = []
    errors: list[str] = []
    provider_probe_errors: list[str] = []
    key_lengths: dict[str, int] = {}
    key_reports: dict[str, dict[str, object]] = {}
    secret_values: dict[str, str] = {}

    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            for key in keys:
                key_reports[key] = {"status": "checking"}
                url = f"{secrets_base}/secrets/{quote(key, safe='')}"
                try:
                    resp = await client.get(url, headers=auth_headers)
                except Exception as exc:  # pragma: no cover - network failures are environment-specific
                    errors.append(f"{key}:request_failed:{_exception_code(exc)}")
                    key_reports[key] = {
                        "status": "error",
                        "error": f"request_failed:{_exception_code(exc)}",
                    }
                    continue

                if resp.status_code == 404:
                    missing_keys.append(key)
                    key_reports[key] = {"status": "missing"}
                    continue
                if resp.status_code != 200:
                    errors.append(f"{key}:unexpected_status:{resp.status_code}")
                    key_reports[key] = {
                        "status": "error",
                        "error": f"unexpected_status:{resp.status_code}",
                    }
                    continue

                try:
                    payload = resp.json()
                except Exception:
                    errors.append(f"{key}:invalid_json")
                    key_reports[key] = {
                        "status": "error",
                        "error": "invalid_json",
                    }
                    continue

                value = payload.get("value")
                if not isinstance(value, str) or not value:
                    missing_keys.append(key)
                    key_reports[key] = {"status": "missing"}
                    continue
                key_lengths[key] = len(value)
                secret_values[key] = value
                key_reports[key] = {
                    "status": "ok",
                    "length": len(value),
                }

            for key in probe_keys:
                value = secret_values.get(key)
                if not value:
                    continue
                provider = _provider_name_for_key(key)
                try:
                    probe_result = await _probe_provider_key(client, key=key, value=value)
                except Exception as exc:  # pragma: no cover - network failures are environment-specific
                    error = f"probe_request_failed:{_exception_code(exc)}"
                    provider_probe_errors.append(f"{key}:{error}")
                    key_reports[key] = {
                        **key_reports.get(key, {}),
                        "status": "degraded",
                        **({"provider": provider} if provider else {}),
                        "probe_status": "request_failed",
                        "error": error,
                    }
                    continue

                key_reports[key] = {
                    **key_reports.get(key, {}),
                    "provider": probe_result["provider"],
                    "probe_status": probe_result["status"],
                    "probe_http_status": probe_result["http_status"],
                }
                if probe_result["status"] == "invalid":
                    invalid_keys.append(key)
                    key_reports[key]["status"] = "invalid"
                    continue
                if probe_result["status"] == "ok":
                    key_reports[key]["status"] = "ok"
                    continue

                provider_probe_errors.append(
                    f"{key}:probe_unexpected_status:{probe_result['http_status']}"
                )
                key_reports[key]["status"] = "degraded"
                key_reports[key]["error"] = (
                    f"probe_unexpected_status:{probe_result['http_status']}"
                )
    except Exception as exc:  # pragma: no cover - network failures are environment-specific
        errors.append(f"credential_check_failed:{_exception_code(exc)}")

    status = (
        "failed"
        if missing_keys or invalid_keys or errors
        else "degraded"
        if provider_probe_errors
        else "ok"
    )
    report = {
        "enabled": True,
        "status": status,
        "required_keys": required_keys,
        "checked_keys": keys,
        "probe_keys": probe_keys,
        "missing_keys": missing_keys,
        "invalid_keys": invalid_keys,
        "errors": errors,
        "provider_probe_errors": provider_probe_errors,
        "key_lengths": key_lengths,
        "keys": key_reports,
    }
    _credential_cache_report = deepcopy(report)
    _credential_cache_key = cache_key
    _credential_cache_expires_at = now + _credential_cache_seconds()
    return report


def runtime_credentials_blocking_failure(report: dict[str, object]) -> bool:
    return bool(report.get("enabled")) and report.get("status") == "failed"


def public_runtime_credential_report(report: dict[str, object]) -> dict[str, object]:
    """Return readiness-safe credential status without key names or metadata."""

    return {
        "enabled": bool(report.get("enabled")),
        "status": report.get("status", "unknown"),
        "missing_keys": bool(report.get("missing_keys")),
        "invalid_keys": bool(report.get("invalid_keys")),
        "errors": bool(report.get("errors")),
        "degraded": bool(report.get("provider_probe_errors")),
    }


async def assert_runtime_credentials_ready() -> None:
    report = await check_runtime_credentials(force_refresh=True)
    if runtime_credentials_blocking_failure(report):
        missing = ",".join(report.get("missing_keys", []))
        invalid = ",".join(report.get("invalid_keys", []))
        errors = ";".join(report.get("errors", []))
        raise RuntimeError(
            "runtime credential guard failed"
            + (f" missing_keys={missing}" if missing else "")
            + (f" invalid_keys={invalid}" if invalid else "")
            + (f" errors={errors}" if errors else "")
        )
