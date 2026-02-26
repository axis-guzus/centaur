.PHONY: install lint test migrate sync api etl agent-clone agent-build fmt clean deploy

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

DEPLOY_HOST := ubuntu@206.223.235.69
DEPLOY_DIR  := ~/github/paradigmxyz/ai_v2

deploy:
	@echo "🔐 Authenticating with 1Password (Touch ID)..."
	@OP_SA_TOKEN=$$(op read "op://AI-V2/OP_SA_TOKEN/password") && \
	API_KEY=$$(op read "op://AI-V2/API_SECRET_KEY/password") && \
	echo "🚀 Deploying to $(DEPLOY_HOST)..." && \
	ssh $(DEPLOY_HOST) "\
		cd $(DEPLOY_DIR) && \
		git pull --ff-only && \
		OP_SERVICE_ACCOUNT_TOKEN='$$OP_SA_TOKEN' \
		API_SECRET_KEY='$$API_KEY' \
		docker compose up -d --build api etl && \
		docker build -t tempo-agent:latest plugins/agent/ && \
		echo '✅ deployed'"
