.PHONY: install lint test migrate sync api etl agent-clone agent-build fmt clean

install:
	uv sync

lint:
	uv run ruff check .
	uv run ruff format --check .

fmt:
	uv run ruff check --fix .
	uv run ruff format .

test:
	uv run pytest

migrate:
	uv run alembic -c migrations/alembic.ini upgrade head

sync:
	uv run ai-v2 sync

api:
	uv run ai-v2 serve

etl:
	uv run ai-v2 continuous

agent-clone:
	plugins/agent/clone-repos.sh

agent-build:
	docker build -t agent2:latest plugins/agent/

clean:
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name .pytest_cache -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name .mypy_cache -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name .ruff_cache -exec rm -rf {} + 2>/dev/null || true
