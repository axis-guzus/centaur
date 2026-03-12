from __future__ import annotations

from asyncpg import Pool
from prometheus_client import (
    CONTENT_TYPE_LATEST,
    Counter,
    Gauge,
    Histogram,
    generate_latest,
)

HTTP_REQUESTS_TOTAL = Counter(
    "http_requests_total",
    "Total HTTP requests served by the API.",
    ["method", "path", "status"],
)
HTTP_REQUEST_DURATION_SECONDS = Histogram(
    "http_request_duration_seconds",
    "HTTP request latency in seconds.",
    ["method", "path"],
)
HTTP_REQUESTS_IN_PROGRESS = Gauge(
    "http_requests_in_progress",
    "Number of in-flight HTTP requests.",
)

AGENT_SESSIONS_ACTIVE = Gauge(
    "agent_sessions_active",
    "Number of running sandbox sessions.",
)
AGENT_EXECUTIONS_TOTAL = Counter(
    "agent_executions_total",
    "Total completed agent executions.",
    ["harness", "status"],
)
AGENT_EXECUTION_DURATION_SECONDS = Histogram(
    "agent_execution_duration_seconds",
    "Agent execution duration in seconds.",
    ["harness", "status"],
)


def observe_http_request(method: str, path: str, status: int, duration_s: float) -> None:
    HTTP_REQUESTS_TOTAL.labels(method=method, path=path, status=str(status)).inc()
    HTTP_REQUEST_DURATION_SECONDS.labels(method=method, path=path).observe(duration_s)


def record_agent_execution(harness: str, status: str, duration_s: float) -> None:
    AGENT_EXECUTIONS_TOTAL.labels(harness=harness, status=status).inc()
    AGENT_EXECUTION_DURATION_SECONDS.labels(harness=harness, status=status).observe(duration_s)


async def refresh_runtime_metrics(pool: Pool) -> None:
    active_sessions = await pool.fetchval(
        "SELECT COUNT(*) FROM sandbox_sessions WHERE state = 'running'"
    )
    AGENT_SESSIONS_ACTIVE.set(int(active_sessions or 0))


async def render_metrics(pool: Pool) -> bytes:
    await refresh_runtime_metrics(pool)
    return generate_latest()


__all__ = [
    "AGENT_EXECUTION_DURATION_SECONDS",
    "AGENT_EXECUTIONS_TOTAL",
    "AGENT_SESSIONS_ACTIVE",
    "CONTENT_TYPE_LATEST",
    "HTTP_REQUESTS_IN_PROGRESS",
    "observe_http_request",
    "record_agent_execution",
    "render_metrics",
]
