from __future__ import annotations

import asyncpg
import structlog

log = structlog.get_logger()


async def create_pool(database_url: str) -> asyncpg.Pool:
    pool = await asyncpg.create_pool(
        database_url,
        min_size=2,
        max_size=10,
        command_timeout=60,
    )
    assert pool is not None
    await _ensure_schema(pool)
    return pool


async def close_pool(pool: asyncpg.Pool) -> None:
    await pool.close()


async def _ensure_schema(pool: asyncpg.Pool) -> None:
    async with pool.acquire() as conn:
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS sandbox_sessions (
                thread_key   TEXT PRIMARY KEY,
                sandbox_id   TEXT NOT NULL,
                channel_id   TEXT NOT NULL DEFAULT '',
                thread_ts    TEXT NOT NULL DEFAULT '',
                harness      TEXT NOT NULL DEFAULT 'amp',
                engine       TEXT NOT NULL DEFAULT 'amp',
                state        TEXT NOT NULL DEFAULT 'creating'
                             CHECK (state IN ('creating','running','idle','error','stopped','gone')),
                config_sent  BOOLEAN NOT NULL DEFAULT FALSE,
                thread_name  TEXT,
                started_at   TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                updated_at   TIMESTAMPTZ NOT NULL DEFAULT NOW()
            )
        """)
        await conn.execute(
            "ALTER TABLE sandbox_sessions DROP CONSTRAINT IF EXISTS sandbox_sessions_state_check"
        )
        await conn.execute("""
            ALTER TABLE sandbox_sessions
            ADD CONSTRAINT sandbox_sessions_state_check
            CHECK (state IN ('creating','running','idle','error','stopped','gone'))
        """)
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS chat_messages (
                id          TEXT PRIMARY KEY,
                thread_key  TEXT NOT NULL,
                role        TEXT NOT NULL,
                parts       JSONB NOT NULL DEFAULT '[]',
                metadata    JSONB NOT NULL DEFAULT '{}',
                created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
            )
        """)
        await conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_chat_messages_thread "
            "ON chat_messages (thread_key, created_at)"
        )
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS api_keys (
                id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                name        TEXT NOT NULL,
                key_prefix  TEXT NOT NULL,
                key_hash    TEXT NOT NULL UNIQUE,
                scopes      TEXT[] NOT NULL DEFAULT '{"tools:*"}',
                created_by  TEXT NOT NULL DEFAULT '',
                created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                revoked_at  TIMESTAMPTZ
            )
        """)
        await conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_api_keys_hash "
            "ON api_keys (key_hash) WHERE revoked_at IS NULL"
        )
    log.info("schema_ensured")
