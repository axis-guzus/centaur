from __future__ import annotations

from typing import Annotated

import asyncpg
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from api.deps import get_pool, verify_operator_api_key

router = APIRouter(prefix="/api/secrets", dependencies=[Depends(verify_operator_api_key)])


class SecretCreate(BaseModel):
    key: str
    value: str
    source: str | None = None
    description: str | None = None


@router.get("")
async def list_secrets(
    pool: Annotated[asyncpg.Pool, Depends(get_pool)],
) -> list[dict]:
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT key, source, description, created_at, updated_at
            FROM secrets
            ORDER BY key
            """
        )
    return [
        {
            "key": r["key"],
            "value": "********",
            "source": r["source"],
            "description": r["description"],
            "created_at": r["created_at"].isoformat() if r["created_at"] else None,
            "updated_at": r["updated_at"].isoformat() if r["updated_at"] else None,
        }
        for r in rows
    ]


@router.post("")
async def create_or_update_secret(
    body: SecretCreate,
    pool: Annotated[asyncpg.Pool, Depends(get_pool)],
) -> dict:
    async with pool.acquire() as conn:
        await conn.execute(
            """
            INSERT INTO secrets (key, value, source, description, created_at, updated_at)
            VALUES ($1, $2, $3, $4, NOW(), NOW())
            ON CONFLICT (key) DO UPDATE
            SET value = $2, source = $3, description = $4, updated_at = NOW()
            """,
            body.key,
            body.value,
            body.source,
            body.description,
        )
    return {"status": "ok", "key": body.key}


@router.delete("/{key}")
async def delete_secret(
    key: str,
    pool: Annotated[asyncpg.Pool, Depends(get_pool)],
) -> dict:
    async with pool.acquire() as conn:
        result = await conn.execute("DELETE FROM secrets WHERE key = $1", key)
        if result == "DELETE 0":
            raise HTTPException(status_code=404, detail="Secret not found")
    return {"status": "deleted", "key": key}
