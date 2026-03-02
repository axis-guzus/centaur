from __future__ import annotations

import os
import secrets
from typing import Annotated

import asyncpg
from fastapi import Depends, Header, HTTPException, Request
from openai import AsyncOpenAI

from shared.tool_sdk import _sm_read

# Only localhost is trusted without an API key (e.g. health checks).
# All other callers — including sandbox containers on agent_net — must
# present a valid API key.  The previous "all private IPs" bypass was
# too broad and allowed sandboxes to hit admin/secrets endpoints.
_TRUSTED_PREFIXES = ("127.",)

# Nginx container IP prefix — only trust X-Forwarded-User from nginx.
# In docker-compose, nginx talks to api over the default bridge network.
_NGINX_IP_PREFIX = os.environ.get("NGINX_TRUSTED_IP_PREFIX", "172.")

_API_SECRET_KEY: str | None = None


def _get_api_secret_key() -> str:
    global _API_SECRET_KEY
    if _API_SECRET_KEY is None:
        _API_SECRET_KEY = _sm_read("API_SECRET_KEY") or ""
    return _API_SECRET_KEY


async def get_pool(request: Request) -> asyncpg.Pool:
    return request.app.state.pool


async def get_embedding_service(
    pool: Annotated[asyncpg.Pool, Depends(get_pool)],
) -> EmbeddingService:
    return EmbeddingService(pool=pool)


async def verify_api_key(
    request: Request,
    x_api_key: Annotated[str | None, Header()] = None,
) -> str:
    client_ip = request.client.host if request.client else ""
    if client_ip.startswith(_TRUSTED_PREFIXES):
        return "localhost-bypass"

    api_key = _get_api_secret_key()
    if not api_key:
        raise HTTPException(status_code=500, detail="API key not configured")

    token = x_api_key
    if not token:
        auth = request.headers.get("authorization", "")
        if auth.lower().startswith("bearer "):
            token = auth[7:]

    if not token or not secrets.compare_digest(token, api_key):
        raise HTTPException(status_code=401, detail="Invalid API key")
    return token


async def verify_ui_or_api_key(
    request: Request,
    x_api_key: Annotated[str | None, Header()] = None,
) -> str:
    """Accept nginx-forwarded auth, Docker bridge inter-service calls, or an API key.

    Trust model for /api/threads (UI) routes:
    - Nginx sets X-Forwarded-User via auth_request → trusted if from Docker bridge IP
    - Internal services (slackbot) call directly from Docker bridge → trusted
    - External callers must provide a valid API key (Bearer token)

    Sandbox containers use verify_api_key (agent/tools routes) which does NOT
    have the Docker bridge bypass.
    """
    client_ip = request.client.host if request.client else ""

    # Localhost always trusted
    if client_ip.startswith(_TRUSTED_PREFIXES):
        return "localhost-bypass"

    # Docker bridge network — trusted for inter-service calls
    if client_ip.startswith(_NGINX_IP_PREFIX):
        forwarded_user = request.headers.get("x-forwarded-user")
        if forwarded_user:
            return "nginx"
        return "docker-bridge-bypass"

    return await verify_api_key(request, x_api_key)


class EmbeddingService:
    def __init__(self, pool: asyncpg.Pool) -> None:
        self.pool = pool
        self.client = AsyncOpenAI(api_key=_sm_read("OPENAI_API_KEY") or "")

    async def embed(self, text: str) -> list[float]:
        resp = await self.client.embeddings.create(
            input=text,
            model="text-embedding-3-small",
        )
        return resp.data[0].embedding
