"""Unit tests for ProxySafeConnection's multi-statement-free reset.

The per-sandbox iron-proxy rejects multi-statement queries. asyncpg's default
connection reset joins several statements into one simple-query string, so the
tool-server's proxied pool must run each reset statement on its own. These tests
exercise the reset logic via a duck-typed self (asyncpg.Connection uses
``__slots__``, so a real subclass instance can't be hand-constructed in a test).
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest

from api.db import ProxySafeConnection

# The reset commands asyncpg joins with newlines for a fully-capable server.
_DEFAULT_RESET = (
    "SELECT pg_advisory_unlock_all();\n"
    "CLOSE ALL;\n"
    "UNLISTEN *;\n"
    "RESET ALL;"
)


class _StubConnection:
    """Provides the three members ProxySafeConnection.reset depends on."""

    def __init__(self, reset_query: str):
        self._reset_query = reset_query
        self.reset_called = False
        self.executed: list[str] = []

    async def _reset(self) -> None:
        self.reset_called = True

    def get_reset_query(self) -> str:
        return self._reset_query

    async def execute(self, query: str, *args, **kwargs) -> None:
        self.executed.append(query)


async def _run_reset(stub: _StubConnection, *, timeout: float | None = None) -> None:
    # Bind the unbound coroutine to the duck-typed stub.
    await ProxySafeConnection.reset(stub, timeout=timeout)


@pytest.mark.asyncio
async def test_reset_runs_each_statement_individually():
    stub = _StubConnection(_DEFAULT_RESET)
    await _run_reset(stub)

    assert stub.reset_called
    assert stub.executed == [
        "SELECT pg_advisory_unlock_all();",
        "CLOSE ALL;",
        "UNLISTEN *;",
        "RESET ALL;",
    ]


@pytest.mark.asyncio
async def test_reset_never_emits_a_multi_statement_query():
    stub = _StubConnection(_DEFAULT_RESET)
    await _run_reset(stub)

    for query in stub.executed:
        assert "\n" not in query
        # A single statement carries at most its own trailing semicolon.
        assert query.count(";") <= 1


@pytest.mark.asyncio
async def test_reset_with_empty_query_executes_nothing():
    stub = _StubConnection("")
    await _run_reset(stub)

    assert stub.reset_called
    assert stub.executed == []


@pytest.mark.asyncio
async def test_reset_honors_timeout_path():
    # Exercises the asyncio.wait_for branch; the work completes well under it.
    stub = _StubConnection(_DEFAULT_RESET)
    await _run_reset(stub, timeout=5.0)

    assert len(stub.executed) == 4
