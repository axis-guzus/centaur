FROM python:3.11-slim

RUN apt-get update && apt-get install -y --no-install-recommends curl \
    && rm -rf /var/lib/apt/lists/*

COPY --from=ghcr.io/astral-sh/uv:0.7 /uv /uvx /usr/local/bin/

ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy

WORKDIR /app

COPY centaur_sdk/ centaur_sdk/
COPY services/secrets/pyproject.toml ./
RUN sed -i 's|path = "../../centaur_sdk"|path = "centaur_sdk"|' pyproject.toml \
    && rm -f uv.lock
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --no-install-project --no-dev

COPY services/secrets/secret_manager/ secret_manager/

EXPOSE 8100
CMD ["/app/.venv/bin/uvicorn", "secret_manager.app:app", "--host", "0.0.0.0", "--port", "8100"]
