from __future__ import annotations

from typing import Annotated

import asyncpg
from fastapi import APIRouter, Depends
from starlette.responses import JSONResponse, PlainTextResponse

from api.deps import get_pool, verify_api_key

router = APIRouter()


async def _database_ready(pool: asyncpg.Pool) -> tuple[bool, str | None]:
    try:
        async with pool.acquire() as conn:
            await conn.fetchval("SELECT 1")
        return True, None
    except Exception as exc:
        return False, str(exc)


@router.get("/health/live")
async def health_live() -> dict:
    """Unauthenticated process liveness check."""
    return {"status": "ok"}


@router.get("/health")
async def health() -> dict:
    """Backward-compatible alias for liveness."""
    return {"status": "ok"}


@router.get("/health/ready")
async def health_ready(pool: Annotated[asyncpg.Pool, Depends(get_pool)]) -> JSONResponse:
    """Unauthenticated readiness check for dependency health."""
    ready, error = await _database_ready(pool)
    payload = {"status": "ok" if ready else "degraded", "database": ready}
    if error:
        payload["error"] = error
    return JSONResponse(payload, status_code=200 if ready else 503)


@router.get("/metrics")
async def metrics(pool: Annotated[asyncpg.Pool, Depends(get_pool)]) -> PlainTextResponse:
    """Minimal Prometheus metrics for API health alignment."""
    ready, _ = await _database_ready(pool)
    db_up = 1 if ready else 0
    payload = "\n".join(
        [
            "# HELP ai_v2_api_up Process health indicator.",
            "# TYPE ai_v2_api_up gauge",
            "ai_v2_api_up 1",
            "# HELP ai_v2_api_db_up Database readiness indicator.",
            "# TYPE ai_v2_api_db_up gauge",
            f"ai_v2_api_db_up {db_up}",
            "",
        ]
    )
    return PlainTextResponse(payload, media_type="text/plain; version=0.0.4; charset=utf-8")


@router.get("/health/detail", dependencies=[Depends(verify_api_key)])
async def health_detail(pool: Annotated[asyncpg.Pool, Depends(get_pool)]) -> dict:
    """Authenticated health check with sync run details."""
    db_ok = False
    last_syncs: list[dict] = []
    try:
        async with pool.acquire() as conn:
            await conn.fetchval("SELECT 1")
            db_ok = True
            rows = await conn.fetch(
                """
                SELECT source, status, started_at, finished_at, records_synced
                FROM sync_runs
                WHERE (source, started_at) IN (
                    SELECT source, MAX(started_at) FROM sync_runs GROUP BY source
                )
                ORDER BY source
                """
            )
            last_syncs = [
                {
                    "source": r["source"],
                    "status": r["status"],
                    "started_at": r["started_at"].isoformat() if r["started_at"] else None,
                    "finished_at": r["finished_at"].isoformat() if r["finished_at"] else None,
                    "records_synced": r["records_synced"],
                }
                for r in rows
            ]
    except Exception:
        pass

    return {
        "status": "ok" if db_ok else "degraded",
        "database": db_ok,
        "last_syncs": last_syncs,
    }
