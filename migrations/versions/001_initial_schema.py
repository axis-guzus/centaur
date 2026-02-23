"""Initial schema with pgvector support.

Revision ID: 001
Revises: None
"""
from alembic import op

revision = "001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Extensions
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")
    op.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm")

    # ── Raw records (append-only) ──────────────────────────────────────
    op.execute("""
        CREATE TABLE raw_records (
            id              BIGINT GENERATED ALWAYS AS IDENTITY,
            source          TEXT NOT NULL,
            kind            TEXT NOT NULL,
            external_id     TEXT NOT NULL,
            fetched_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            content_hash    TEXT NOT NULL,
            data            JSONB NOT NULL,
            PRIMARY KEY (source, kind, external_id, content_hash)
        )
    """)
    op.execute("CREATE INDEX idx_raw_lookup ON raw_records (source, kind, external_id, fetched_at)")
    op.execute("CREATE INDEX idx_raw_by_time ON raw_records (source, kind, fetched_at)")
    op.execute("CREATE INDEX idx_raw_data_gin ON raw_records USING GIN (data)")

    # ── Sync cursors ───────────────────────────────────────────────────
    op.execute("""
        CREATE TABLE sync_cursors (
            cursor_key  TEXT PRIMARY KEY,
            source      TEXT NOT NULL,
            kind        TEXT NOT NULL,
            entity_id   TEXT,
            cursor      TEXT NOT NULL,
            updated_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
    """)
    op.execute("CREATE INDEX idx_cursors_source ON sync_cursors (source, kind, entity_id)")

    # ── People ─────────────────────────────────────────────────────────
    op.execute("""
        CREATE TABLE people (
            slug             TEXT PRIMARY KEY,
            name             TEXT NOT NULL,
            email            TEXT,
            role             TEXT,
            is_direct_report BOOLEAN NOT NULL DEFAULT FALSE,
            focus_area       TEXT
        )
    """)

    # ── Entity mappings ────────────────────────────────────────────────
    op.execute("""
        CREATE TABLE entity_mappings (
            source      TEXT NOT NULL,
            external_id TEXT NOT NULL,
            person_slug TEXT NOT NULL REFERENCES people(slug) ON DELETE CASCADE,
            PRIMARY KEY (source, external_id)
        )
    """)
    op.execute("CREATE INDEX idx_entity_map_slug ON entity_mappings (person_slug)")

    # ── Embeddings (pgvector) ──────────────────────────────────────────
    op.execute("""
        CREATE TABLE embeddings (
            id          BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
            source      TEXT NOT NULL,
            kind        TEXT NOT NULL,
            source_id   TEXT NOT NULL,
            content     TEXT NOT NULL,
            embedding   vector(1536) NOT NULL,
            metadata    JSONB DEFAULT '{}',
            created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            UNIQUE (source, kind, source_id)
        )
    """)
    op.execute(
        "CREATE INDEX idx_embeddings_vector ON embeddings "
        "USING hnsw (embedding vector_cosine_ops)"
    )
    op.execute("CREATE INDEX idx_embeddings_source ON embeddings (source, kind)")
    op.execute("CREATE INDEX idx_embeddings_metadata ON embeddings USING GIN (metadata)")
    # Full-text search via tsvector
    op.execute(
        "ALTER TABLE embeddings ADD COLUMN content_tsv tsvector "
        "GENERATED ALWAYS AS (to_tsvector('english', content)) STORED"
    )
    op.execute("CREATE INDEX idx_embeddings_fts ON embeddings USING GIN (content_tsv)")

    # ── Secrets ────────────────────────────────────────────────────────
    op.execute("""
        CREATE TABLE secrets (
            key         TEXT PRIMARY KEY,
            value       TEXT NOT NULL,
            source      TEXT,
            description TEXT,
            created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
    """)

    # ── Sync runs ──────────────────────────────────────────────────────
    op.execute("""
        CREATE TABLE sync_runs (
            id          BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
            source      TEXT NOT NULL,
            status      TEXT NOT NULL CHECK (status IN ('running', 'success', 'error')),
            records     INT DEFAULT 0,
            kinds       JSONB DEFAULT '{}',
            error       TEXT,
            config_hash TEXT,
            started_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            finished_at TIMESTAMPTZ
        )
    """)
    op.execute("CREATE INDEX idx_sync_runs_source ON sync_runs (source, started_at DESC)")

    # ── Enrichment feedback ────────────────────────────────────────────
    op.execute("""
        CREATE TABLE enrichment_feedback (
            id          BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
            source      TEXT NOT NULL,
            entity_id   TEXT NOT NULL,
            action      TEXT NOT NULL CHECK (action IN ('ignore', 'remap', 'pin')),
            reason      TEXT,
            created_by  TEXT,
            created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            UNIQUE (source, entity_id)
        )
    """)


def downgrade() -> None:
    for table in [
        "enrichment_feedback", "sync_runs", "secrets",
        "embeddings", "entity_mappings", "people",
        "sync_cursors", "raw_records",
    ]:
        op.execute(f"DROP TABLE IF EXISTS {table} CASCADE")
    op.execute("DROP EXTENSION IF EXISTS vector")
    op.execute("DROP EXTENSION IF EXISTS pg_trgm")
