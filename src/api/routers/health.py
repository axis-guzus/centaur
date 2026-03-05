from __future__ import annotations

from typing import Annotated

import asyncpg
from fastapi import APIRouter, Depends
from starlette.responses import JSONResponse, PlainTextResponse

from api.deps import get_pool, verify_operator_api_key
from api.output_quality import get_output_quality_metrics

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
    quality_metrics = get_output_quality_metrics()
    payload = "\n".join(
        [
            "# HELP ai_v2_api_up Process health indicator.",
            "# TYPE ai_v2_api_up gauge",
            "ai_v2_api_up 1",
            "# HELP ai_v2_api_db_up Database readiness indicator.",
            "# TYPE ai_v2_api_db_up gauge",
            f"ai_v2_api_db_up {db_up}",
            "# HELP ai_v2_output_quality_total Total responses checked by output quality pipeline.",
            "# TYPE ai_v2_output_quality_total counter",
            f"ai_v2_output_quality_total {quality_metrics['total']}",
            "# HELP ai_v2_output_quality_changed_total Responses rewritten by output quality pipeline.",
            "# TYPE ai_v2_output_quality_changed_total counter",
            f"ai_v2_output_quality_changed_total {quality_metrics['changed']}",
            "# HELP ai_v2_output_quality_latency_ms_total Total latency spent in output quality pipeline.",
            "# TYPE ai_v2_output_quality_latency_ms_total counter",
            f"ai_v2_output_quality_latency_ms_total {quality_metrics['latency_ms_total']}",
            "# HELP ai_v2_output_quality_status_total Responses by output quality status.",
            "# TYPE ai_v2_output_quality_status_total counter",
            f'ai_v2_output_quality_status_total{{status="applied"}} {quality_metrics["applied"]}',
            f'ai_v2_output_quality_status_total{{status="skipped"}} {quality_metrics["skipped"]}',
            f'ai_v2_output_quality_status_total{{status="error"}} {quality_metrics["error"]}',
            "",
        ]
    )
    return PlainTextResponse(payload, media_type="text/plain; version=0.0.4; charset=utf-8")


@router.get("/health/detail", dependencies=[Depends(verify_operator_api_key)])
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
