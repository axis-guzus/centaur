from __future__ import annotations

from typing import Annotated

import asyncpg
from fastapi import APIRouter, Depends
from pydantic import BaseModel

from api.deps import get_pool, verify_operator_api_key

router = APIRouter(prefix="/api/sync", dependencies=[Depends(verify_operator_api_key)])


class SyncRunRequest(BaseModel):
    sources: list[str] | None = None


@router.post("/run")
async def trigger_sync(
    body: SyncRunRequest,
    pool: Annotated[asyncpg.Pool, Depends(get_pool)],
) -> dict:
    async with pool.acquire() as conn:
        if body.sources:
            for source in body.sources:
                await conn.execute(
                    """
                    INSERT INTO sync_runs (source, status, started_at)
                    VALUES ($1, 'pending', NOW())
                    """,
                    source,
                )
        else:
            sources = await conn.fetch("SELECT DISTINCT source FROM sync_cursors ORDER BY source")
            for row in sources:
                await conn.execute(
                    """
                    INSERT INTO sync_runs (source, status, started_at)
                    VALUES ($1, 'pending', NOW())
                    """,
                    row["source"],
                )

    return {"status": "queued", "sources": body.sources or "all"}


@router.get("/status")
async def sync_status(
    pool: Annotated[asyncpg.Pool, Depends(get_pool)],
) -> list[dict]:
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT
                c.source,
                c.cursor AS cursor_value,
                c.updated_at AS cursor_updated_at,
                r.status AS last_run_status,
                r.started_at AS last_run_started,
                r.finished_at AS last_run_finished,
                r.records_synced AS last_run_records
            FROM sync_cursors c
            LEFT JOIN LATERAL (
                SELECT status, started_at, finished_at, records_synced
                FROM sync_runs
                WHERE source = c.source
                ORDER BY started_at DESC
                LIMIT 1
            ) r ON TRUE
            ORDER BY c.source
            """
        )
    return [dict(r) for r in rows]


@router.get("/runs")
async def sync_runs(
    pool: Annotated[asyncpg.Pool, Depends(get_pool)],
    source: str | None = None,
    limit: int = 50,
) -> list[dict]:
    if source:
        rows = await pool.fetch(
            """
            SELECT id, source, status, started_at, finished_at,
                   records_synced, error_message
            FROM sync_runs
            WHERE source = $1
            ORDER BY started_at DESC
            LIMIT $2
            """,
            source,
            limit,
        )
    else:
        rows = await pool.fetch(
            """
            SELECT id, source, status, started_at, finished_at,
                   records_synced, error_message
            FROM sync_runs
            ORDER BY started_at DESC
            LIMIT $1
            """,
            limit,
        )
    return [dict(r) for r in rows]
