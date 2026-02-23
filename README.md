# Tempo AI v2

Rebuild of the Tempo AI system: **Postgres+pgvector** for data + search, **FastAPI+MCP** API layer, **Codex+Docker** sandbox.

## Architecture

```
                    ┌──────────────────────────────┐
                    │         Remote Clients        │
                    │  (Codex, agents, MCP clients) │
                    └──────────────┬───────────────┘
                                   │
                    ┌──────────────▼───────────────┐
                    │       api/ (FastAPI+MCP)      │
                    │  /api/search  (hybrid search) │
                    │  /api/query   (JSONB queries) │
                    │  /api/search/sql (raw SQL)    │
                    │  /mcp         (7 MCP tools)   │
                    └──────────────┬───────────────┘
                                   │
                    ┌──────────────▼───────────────┐
                    │   Postgres 16 + pgvector      │
                    │                               │
                    │  raw_records  (JSONB, all src) │
                    │  embeddings   (vector(1536))   │
                    │  people / entity_mappings      │
                    │  sync_cursors / sync_runs      │
                    │  secrets                       │
                    └──────────────▲───────────────┘
                                   │
                    ┌──────────────┴───────────────┐
                    │   dataplane/ (ETL pipeline)   │
                    │   10 extractors → raw_records │
                    │   → OpenAI embed → embeddings │
                    └──────────────────────────────┘
```

**No staging views. No mart views.** All queries hit JSONB directly (`data->>'field'`) or the `embeddings` table for semantic search. This replaces metronome's SQLite + qmd + 23 staging views + 12 marts with two tables.

### Data Plane (`dataplane/`)

- **10 extractors**: Slack, Linear, GitHub, GCal, Gmail, GDrive, Granola, Attio, Pylon, BetterStack
- **Storage**: `raw_records` table — append-only JSONB, dedup by `(source, kind, external_id, content_hash)`
- **Search**: `embeddings` table — pgvector HNSW index + tsvector FTS, hybrid search via RRF
- **Sync**: Cursor-based incremental, 5-min overlap for consistency

### API Layer (`api/`)

- **`POST /api/search`** — Hybrid vector + FTS search with RRF ranking
- **`POST /api/search/sql`** — Run read-only SQL directly against `raw_records` JSONB
- **`GET /api/query/*`** — Structured endpoints (slack/messages, linear/issues, github/prs, timeline, people)
- **`/mcp`** — 7 MCP tools (search, sql_query, get_slack_thread, get_person, get_timeline, list_sources, sync_status)

### Sandbox (`sandbox/`)

Docker image preloaded with 28 tempoxyz repos, auto-updated every 6h. For Codex / agent code execution.

## Quick Start

```bash
gh repo clone tempoxyz/ai_v2
cd ai_v2
cp .env.example .env        # fill in secrets
docker compose up -d         # start Postgres
make install                 # install Python deps
make migrate                 # run Alembic migrations
make sync                    # run ETL pipeline
make api                     # start API server
```

## Deployment (dev-aibot)

```bash
bash scripts/setup-postgres.sh                          # install PG + pgvector
DATABASE_URL=... uv run alembic -c migrations/alembic.ini upgrade head
python scripts/migrate-from-sqlite.py --sqlite-path ~/.pov/pov.db --database-url ...
python scripts/generate-embeddings.py --database-url ... --openai-api-key ...
bash scripts/deploy-dev-aibot.sh                        # systemd services
```

## Project Structure

```
ai_v2/
├── dataplane/          # ETL pipeline
│   └── src/ai_v2_dataplane/
│       ├── extractors/ # 10 source extractors
│       ├── embeddings.py
│       ├── pipeline.py
│       └── cli.py
├── api/                # FastAPI + MCP
│   └── src/ai_v2_api/
│       ├── routers/    # search, query, sync, secrets, health
│       └── mcp_server.py
├── sandbox/            # Docker + repo sync
├── migrations/         # Alembic (1 migration: core schema)
├── scripts/            # setup-postgres, migrate-from-sqlite, deploy, embeddings
├── docker-compose.yml
├── Makefile
└── pyproject.toml
```
