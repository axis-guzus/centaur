# Tempo AI v2

## Structure

- `dataplane/` - Postgres+pgvector ETL pipeline (Python/uv)
- `api/` - FastAPI + MCP server
- `sandbox/` - Codex+Docker sandbox builder
- `migrations/` - Alembic PG migrations
- `scripts/` - Deployment and migration scripts

## Commands

```bash
make install                    # Install all packages
make lint                       # Lint all packages
make test                       # Test all packages
make fmt                        # Auto-fix lint + format
make migrate                    # Run Postgres migrations
make sync                       # Run ETL pipeline
make api                        # Start API server
make sandbox-build              # Build sandbox Docker image
make sandbox-update-repos       # Update repos in sandbox
```

## Rules

- Python 3.11+, use `uv` for all dependency management — never pip/poetry/pipenv
- `ruff` for linting and formatting (line-length=100)
- All secrets via environment variables, never hardcode credentials
- Use `asyncpg` for Postgres connections, `pgvector` for embeddings
- No staging views or mart views — query `raw_records` JSONB directly via `data->>'field'`
- Alembic for all schema migrations — never modify the DB manually
- All API endpoints require `Authorization: Bearer <key>` auth
- Tests use pytest with pytest-asyncio; each package has its own `tests/` directory
- Follow conventional commits: `feat:`, `fix:`, `docs:`, `refactor:`, `test:`, `chore:`

## CI

```bash
uv run ruff check .
uv run ruff format --check .
uv run pytest
uv run mypy dataplane/src api/src sandbox/src
```
