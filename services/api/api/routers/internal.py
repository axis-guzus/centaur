"""Internal endpoints served on control_net — no auth required.

Only the firewall can reach these because control_net is an internal
Docker network with only the API and firewall as members.
"""

from __future__ import annotations

from fastapi import APIRouter

router = APIRouter(prefix="/internal", tags=["internal"])
