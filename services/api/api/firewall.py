from __future__ import annotations

import os


def control_url() -> str:
    return os.environ.get("FIREWALL_HEALTH_URL", "http://firewall-manager:8081").rstrip("/")


def control_headers() -> dict[str, str]:
    token = (os.environ.get("FIREWALL_CONTROL_TOKEN") or "").strip()
    if not token:
        return {}
    return {"Authorization": f"Bearer {token}"}


def secrets_url() -> str:
    return os.environ.get("SECRET_MANAGER_URL", "http://secrets:8100").rstrip("/")


def secrets_headers() -> dict[str, str]:
    token = (os.environ.get("SECRETS_AUTH_TOKEN") or "").strip()
    if not token:
        raise RuntimeError("SECRETS_AUTH_TOKEN must be set")
    return {"Authorization": f"Bearer {token}"}
