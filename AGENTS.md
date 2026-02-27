# AI v2 — Dev Instructions

## Code Conventions

- Python 3.11+, `uv` for deps, `ruff` for lint/format (line-length=100)
- All imports at top of file, never inside functions
- Absolute imports only: `from shared.X`, `from api.X`, `from etl.X` — no relative imports
- All secrets via env vars, never hardcode
- `asyncpg` for Postgres, `pgvector` for embeddings
- Query `raw_records` JSONB directly — no staging/mart views
- Conventional commits: `feat:`, `fix:`, `docs:`, `refactor:`, `test:`, `chore:`

## Lint & Test

```bash
make lint             # ruff check + format --check
make fmt              # auto-fix
make test             # pytest
uv run mypy src/api src/etl src/shared
```

## Plugin Conventions

Every plugin: `plugins/<name>/` with `client.py` (class + `_client()` factory), `pyproject.toml` (`[tool.ai-v2-plugin] module = "client.py"`), optional `cli.py`.

- `client.py`: NO `load_dotenv()`. Secrets via `os.getenv()` or `secret()`.
- `cli.py`: YES `load_dotenv()` at top. Thin typer wrapper.
- Methods starting with `_` or lifecycle methods are excluded from registration.
- Secrets resolution: plugin `.env` → root `.env` → environment variables.

## Agent Sandbox Architecture

1 Slack thread = 1 Docker container. The API spawns sibling containers (via Docker socket) running harness CLIs (amp, claude-code, codex). Inside the container, the harness calls back to the API via `curl` over the REST API — **NOT MCP**. MCP is only served at `/mcp` for external 3rd-party clients.

Key files:
```
src/api/agent.py          # AgentClient: spawn, execute, status, stop, interrupt
src/api/routers/agent.py  # REST routes at /agent/*
sandbox/
  Dockerfile              # Image: Ubuntu 24.04 + uv + gh + node + rust + amp
  entrypoint.sh           # Writes harness configs, signals readiness
  SYSTEM_PROMPT.md        # Baked in as ~/AGENTS.md — tells harness to curl the API
```

Container → API connectivity:
- Container joins `ai_v2_default` Docker network → API reachable at `http://api:8000`
- Entrypoint injects `AI_V2_API_URL` and `AI_V2_API_KEY` env vars
- SYSTEM_PROMPT instructs the harness: `curl -H "Authorization: Bearer $AI_V2_API_KEY" $AI_V2_API_URL/plugins/{plugin}/{tool}`
- Agent image MUST be tagged `agent2:latest` (not `agent:latest`)

## E2E Testing (without Slack)

This is how to test the full agent loop locally — no Slack required.

### 1. Bring up the stack

```bash
docker compose up -d postgres api    # API + Postgres
docker build -t agent2:latest sandbox/  # rebuild agent image after sandbox/ changes
source .env
```

### 2. Execute a message (auto-spawns container)

```bash
curl -s -X POST http://localhost:8000/agent/execute \
  -H "Authorization: Bearer $API_SECRET_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "slack_thread_key": "test:e2e-1",
    "message": "find me the last 10 messages in the #investing slack channel",
    "harness": "amp"
  }'
```

This spawns a container on the Docker network, runs `amp -x "..."` inside it, and amp uses `curl` to call the API's REST endpoints (search, plugins, query) to answer.

### 3. Follow-up (same container, same session)

```bash
curl -s -X POST http://localhost:8000/agent/execute \
  -H "Authorization: Bearer $API_SECRET_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "slack_thread_key": "test:e2e-1",
    "message": "now summarize the key topics"
  }'
```

### 4. Inspect

```bash
curl -s "http://localhost:8000/agent/status?key=test:e2e-1" \
  -H "Authorization: Bearer $API_SECRET_KEY" | jq
```

### 5. Clean up

```bash
curl -s -X POST http://localhost:8000/agent/stop \
  -H "Authorization: Bearer $API_SECRET_KEY" \
  -H "Content-Type: application/json" \
  -d '{"slack_thread_key": "test:e2e-1"}'
```

### Debugging connectivity

If the agent can't reach the API, exec into the container and test:

```bash
# find container ID
docker ps --filter label=agent2=true
# test connectivity from inside
docker exec <container_id> curl -s -H "Authorization: Bearer $AI_V2_API_KEY" http://api:8000/health
```

## Deployment

```bash
make deploy           # pull + rebuild API + slackbot
make deploy-agent     # pull + rebuild agent2:latest image
make deploy-all       # pull + rebuild everything

# Or manually:
make ssh              # ssh ubuntu@206.223.235.69
# Remote operations with R=1:
make ps R=1           # docker compose ps on remote
make logs-api R=1     # API logs on remote
```
