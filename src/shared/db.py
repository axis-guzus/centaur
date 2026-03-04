from __future__ import annotations

from typing import Any

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


async def execute(pool: asyncpg.Pool, query: str, *args: Any) -> str:
    return await pool.execute(query, *args)


async def fetch(pool: asyncpg.Pool, query: str, *args: Any) -> list[asyncpg.Record]:
    return await pool.fetch(query, *args)


async def fetchrow(pool: asyncpg.Pool, query: str, *args: Any) -> asyncpg.Record | None:
    return await pool.fetchrow(query, *args)


async def _drop_orphan_composite_type(conn: asyncpg.Connection, relation_name: str) -> None:
    """Drop leftover row-type if table was removed but type remains."""
    table_exists = await conn.fetchval(
        """
        SELECT EXISTS (
            SELECT 1
            FROM pg_class c
            JOIN pg_namespace n ON n.oid = c.relnamespace
            WHERE n.nspname = current_schema()
              AND c.relname = $1
              AND c.relkind = 'r'
        )
        """,
        relation_name,
    )
    if table_exists:
        return

    type_exists = await conn.fetchval(
        "SELECT EXISTS (SELECT 1 FROM pg_type WHERE typname = $1)",
        relation_name,
    )
    if type_exists:
        await conn.execute(f'DROP TYPE IF EXISTS "{relation_name}"')
        log.warning("dropped_orphan_composite_type", relation=relation_name)


async def _ensure_schema(pool: asyncpg.Pool) -> None:
    async with pool.acquire() as conn:
        await _drop_orphan_composite_type(conn, "agent_sessions")
        await conn.execute("CREATE EXTENSION IF NOT EXISTS vector")
        await conn.execute(
            """
            CREATE TABLE IF NOT EXISTS raw_records (
                source       TEXT NOT NULL,
                kind         TEXT NOT NULL,
                external_id  TEXT NOT NULL,
                fetched_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
                content_hash TEXT NOT NULL,
                data         JSONB NOT NULL,
                PRIMARY KEY (source, kind, external_id, content_hash)
            );
            CREATE INDEX IF NOT EXISTS idx_raw_lookup
                ON raw_records (source, kind, external_id, fetched_at);
            CREATE INDEX IF NOT EXISTS idx_raw_by_time
                ON raw_records (source, kind, fetched_at);
            """
        )
        await conn.execute(
            """
            CREATE TABLE IF NOT EXISTS sync_cursors (
                cursor_key TEXT PRIMARY KEY,
                source     TEXT NOT NULL,
                kind       TEXT NOT NULL,
                entity_id  TEXT,
                cursor     TEXT NOT NULL,
                updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
            );
            CREATE INDEX IF NOT EXISTS idx_sync_cursors_source
                ON sync_cursors (source, kind, entity_id);
            """
        )
        await conn.execute(
            """
            CREATE TABLE IF NOT EXISTS people (
                slug            TEXT PRIMARY KEY,
                name            TEXT NOT NULL,
                email           TEXT,
                role            TEXT,
                is_direct_report BOOLEAN NOT NULL DEFAULT false,
                focus_area      TEXT
            );
            """
        )
        await conn.execute(
            """
            CREATE TABLE IF NOT EXISTS entity_mappings (
                source      TEXT NOT NULL,
                external_id TEXT NOT NULL,
                person_slug TEXT NOT NULL REFERENCES people(slug),
                PRIMARY KEY (source, external_id)
            );
            """
        )
        await conn.execute(
            """
            CREATE TABLE IF NOT EXISTS embeddings (
                id         BIGSERIAL PRIMARY KEY,
                source     TEXT NOT NULL,
                kind       TEXT NOT NULL,
                source_id  TEXT NOT NULL,
                content    TEXT NOT NULL,
                embedding  vector(1536),
                metadata   JSONB NOT NULL DEFAULT '{}',
                created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
                tsv        tsvector GENERATED ALWAYS AS (
                    to_tsvector('english', content)
                ) STORED,
                UNIQUE (source, kind, source_id)
            );
            CREATE INDEX IF NOT EXISTS idx_embeddings_vec
                ON embeddings USING ivfflat (embedding vector_cosine_ops)
                WITH (lists = 100);
            CREATE INDEX IF NOT EXISTS idx_embeddings_tsv
                ON embeddings USING gin (tsv);
            CREATE INDEX IF NOT EXISTS idx_embeddings_source
                ON embeddings (source, kind);
            """
        )
        await conn.execute(
            """
            CREATE TABLE IF NOT EXISTS sync_runs (
                id              BIGSERIAL PRIMARY KEY,
                source          TEXT NOT NULL,
                status          TEXT NOT NULL DEFAULT 'pending',
                started_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
                finished_at     TIMESTAMPTZ,
                records_synced  INT NOT NULL DEFAULT 0,
                error_message   TEXT
            );
            CREATE INDEX IF NOT EXISTS idx_sync_runs_source
                ON sync_runs (source, started_at DESC);
            """
        )
        await conn.execute(
            """
            CREATE TABLE IF NOT EXISTS secrets (
                key          TEXT PRIMARY KEY,
                value        TEXT NOT NULL,
                source       TEXT,
                description  TEXT,
                created_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
                updated_at   TIMESTAMPTZ NOT NULL DEFAULT now()
            );
            """
        )
        await conn.execute(
            """
            CREATE TABLE IF NOT EXISTS agent_sessions (
                slack_thread_key TEXT PRIMARY KEY,
                container_id     TEXT NOT NULL,
                harness          TEXT NOT NULL DEFAULT 'amp',
                engine           TEXT,
                persona          TEXT,
                mode             TEXT NOT NULL DEFAULT 'default',
                agent_thread_id  TEXT,
                state            TEXT NOT NULL DEFAULT 'running',
                repo             TEXT,
                created_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
                last_activity    TIMESTAMPTZ NOT NULL DEFAULT now()
            );
            """
        )
        await conn.execute(
            "ALTER TABLE agent_sessions ADD COLUMN IF NOT EXISTS thread_name TEXT"
        )
        await conn.execute(
            "ALTER TABLE agent_sessions ADD COLUMN IF NOT EXISTS mode TEXT NOT NULL DEFAULT 'default'"
        )
        await conn.execute(
            "ALTER TABLE agent_sessions ADD COLUMN IF NOT EXISTS engine TEXT"
        )
        await conn.execute(
            "ALTER TABLE agent_sessions ADD COLUMN IF NOT EXISTS persona TEXT"
        )
        await conn.execute(
            """
            CREATE TABLE IF NOT EXISTS agent_turns (
                id               BIGSERIAL PRIMARY KEY,
                slack_thread_key TEXT NOT NULL REFERENCES agent_sessions(slack_thread_key)
                                     ON DELETE CASCADE,
                turn_id          INT NOT NULL,
                user_message     TEXT NOT NULL,
                events           JSONB NOT NULL DEFAULT '[]',
                result           TEXT NOT NULL DEFAULT '',
                started_at       TIMESTAMPTZ NOT NULL,
                finished_at      TIMESTAMPTZ,
                exit_code        INT,
                timed_out        BOOLEAN NOT NULL DEFAULT false,
                duration_s       REAL NOT NULL DEFAULT 0,
                UNIQUE (slack_thread_key, turn_id)
            );
            CREATE INDEX IF NOT EXISTS idx_agent_turns_thread
                ON agent_turns (slack_thread_key, turn_id);
            """
        )
        await conn.execute(
            """
            ALTER TABLE agent_turns
            ADD COLUMN IF NOT EXISTS artifacts JSONB NOT NULL DEFAULT '[]'::jsonb
            """
        )
        await conn.execute(
            """
            CREATE TABLE IF NOT EXISTS legal_documents (
                id               TEXT PRIMARY KEY,
                document_type    TEXT NOT NULL,
                company_name     TEXT,
                title            TEXT NOT NULL,
                status           TEXT NOT NULL DEFAULT 'draft',
                current_version  INT NOT NULL DEFAULT 0,
                deal_id          TEXT,
                slack_thread_key TEXT,
                requester_id     TEXT,
                playbook_id      TEXT,
                terms            JSONB NOT NULL DEFAULT '{}'::jsonb,
                metadata         JSONB NOT NULL DEFAULT '{}'::jsonb,
                created_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
                updated_at       TIMESTAMPTZ NOT NULL DEFAULT now()
            );
            CREATE INDEX IF NOT EXISTS idx_legal_documents_company
                ON legal_documents (company_name, document_type, updated_at DESC);
            CREATE INDEX IF NOT EXISTS idx_legal_documents_deal
                ON legal_documents (deal_id);
            """
        )
        await conn.execute(
            """
            CREATE TABLE IF NOT EXISTS legal_document_versions (
                id                BIGSERIAL PRIMARY KEY,
                document_id       TEXT NOT NULL REFERENCES legal_documents(id) ON DELETE CASCADE,
                version           INT NOT NULL,
                terms             JSONB NOT NULL DEFAULT '{}'::jsonb,
                content_text      TEXT NOT NULL,
                source_file_url   TEXT,
                source_file_hash  TEXT,
                diff_summary      TEXT,
                diff_details      JSONB,
                compliance_report JSONB,
                requested_by      TEXT,
                request_text      TEXT,
                created_at        TIMESTAMPTZ NOT NULL DEFAULT now(),
                UNIQUE (document_id, version)
            );
            CREATE INDEX IF NOT EXISTS idx_legal_doc_versions_doc
                ON legal_document_versions (document_id, version DESC);
            """
        )
        await conn.execute(
            """
            CREATE TABLE IF NOT EXISTS legal_audit_log (
                id          BIGSERIAL PRIMARY KEY,
                document_id TEXT NOT NULL REFERENCES legal_documents(id) ON DELETE CASCADE,
                action      TEXT NOT NULL,
                actor_id    TEXT,
                details     JSONB NOT NULL DEFAULT '{}'::jsonb,
                created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
            );
            CREATE INDEX IF NOT EXISTS idx_legal_audit_doc
                ON legal_audit_log (document_id, created_at DESC);
            """
        )
    log.info("schema_ensured")
