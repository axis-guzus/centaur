.PHONY: install lint fmt test migrate sync api etl clean \
       deploy deploy-api deploy-bot deploy-etl deploy-agent deploy-all \
       logs logs-api logs-bot logs-etl \
       ps pull restart stop agent-build ssh

# ---------------------------------------------------------------------------
# Local development
# ---------------------------------------------------------------------------

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

agent-build:
	$(RUN) docker build -t agent2:latest sandbox/

clean:
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name .pytest_cache -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name .mypy_cache -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name .ruff_cache -exec rm -rf {} + 2>/dev/null || true

# ---------------------------------------------------------------------------
# Local / Remote toggle
#
#   make ps          → local docker compose
#   make ps R=1      → remote (deploy host)
# ---------------------------------------------------------------------------

DEPLOY_HOST := ubuntu@206.223.235.69
DEPLOY_DIR  := ~/github/paradigmxyz/ai_v2

ifdef R
  RUN = ssh $(DEPLOY_HOST) "cd $(DEPLOY_DIR) &&
  RUN_END = "
else
  RUN =
  RUN_END =
endif

# ---------------------------------------------------------------------------
# Docker operations (local by default, R=1 for remote)
# ---------------------------------------------------------------------------

ps:
	@$(RUN) docker compose ps --format 'table {{.Name}}\t{{.Status}}'$(RUN_END)

up:
	@$(RUN) docker compose up -d$(RUN_END)

down:
	@$(RUN) docker compose down$(RUN_END)

restart:
	@$(RUN) docker compose restart $(SVC)$(RUN_END)

stop:
	@$(RUN) docker compose stop $(SVC)$(RUN_END)

# Logs — TAIL=50 (default), FOLLOW=1 to tail
TAIL ?= 50
FOLLOW_FLAG := $(if $(FOLLOW),-f,)

logs:
	@$(RUN) docker compose logs --tail $(TAIL) $(FOLLOW_FLAG) $(SVC)$(RUN_END)

logs-api:
	@$(RUN) docker compose logs api --tail $(TAIL) $(FOLLOW_FLAG)$(RUN_END)

logs-bot:
	@$(RUN) docker compose logs slackbot --tail $(TAIL) $(FOLLOW_FLAG)$(RUN_END)

logs-etl:
	@$(RUN) docker compose logs etl --tail $(TAIL) $(FOLLOW_FLAG)$(RUN_END)

# Build + restart a service
build:
	@$(RUN) docker compose up -d --build $(SVC)$(RUN_END)

# ---------------------------------------------------------------------------
# Deploy (always remote)
# ---------------------------------------------------------------------------

pull:
	@echo "⬇️  Pulling latest..."
	@ssh $(DEPLOY_HOST) "cd $(DEPLOY_DIR) && git pull --ff-only"

deploy: pull
	@echo "🚀 Deploying API + slackbot..."
	@ssh $(DEPLOY_HOST) "cd $(DEPLOY_DIR) && docker compose up -d --build api slackbot"

deploy-api: pull
	@echo "🚀 Deploying API..."
	@ssh $(DEPLOY_HOST) "cd $(DEPLOY_DIR) && docker compose up -d --build api"

deploy-bot: pull
	@echo "🚀 Deploying slackbot..."
	@ssh $(DEPLOY_HOST) "cd $(DEPLOY_DIR) && docker compose up -d --build slackbot"

deploy-etl: pull
	@echo "🚀 Deploying ETL..."
	@ssh $(DEPLOY_HOST) "cd $(DEPLOY_DIR) && docker compose up -d --build etl"

deploy-agent: pull
	@echo "🚀 Building agent image..."
	@ssh $(DEPLOY_HOST) "cd $(DEPLOY_DIR) && docker build -t agent2:latest sandbox/"

deploy-all: pull
	@echo "🚀 Deploying all services + agent image..."
	@ssh $(DEPLOY_HOST) "cd $(DEPLOY_DIR) && docker compose up -d --build && docker build -t agent2:latest sandbox/"

# SSH into the deploy host
ssh:
	@ssh $(DEPLOY_HOST)
