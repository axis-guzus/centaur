"""Internal endpoints served on the private service network -- no auth required.

Only trusted in-cluster services should be allowed to reach these endpoints.
"""

from __future__ import annotations

from fastapi import APIRouter

router = APIRouter(prefix="/internal", tags=["internal"])


@router.get("/injection-map")
def get_injection_map() -> dict[str, list[str]]:
    """Return the current tool injection map (host_pattern → allowed keys).

    The firewall polls this on startup and periodically so it can recover
    its map without relying on the API having pushed since the firewall
    last started. Source of truth lives in ``tool_manager``.
    """
    from api.app import get_tool_manager

    return get_tool_manager().build_injection_map()
