"""Shared test fixtures for API integration tests.

Spins up an ephemeral Postgres instance on the host for the test session,
runs migrations, and provides an httpx client against the real app.
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import tempfile
import time
from pathlib import Path

import httpx
import pytest
import pytest_asyncio


def pytest_configure(config):
    config.addinivalue_line("markers", "sandbox: requires running sandbox container")


@pytest.fixture(scope="session")
def pg():
    """Start an ephemeral Postgres on a random port, yield the DSN, tear down after."""
    tmpdir = tempfile.mkdtemp(prefix="centaur-test-pg-")
    port = 15432

    try:
        subprocess.run(
            ["initdb", "-D", tmpdir, "--no-locale", "-E", "UTF8"],
            check=True,
            capture_output=True,
        )
        subprocess.run(
            [
                "pg_ctl", "-D", tmpdir, "-o", f"-p {port} -k {tmpdir}",
                "-l", f"{tmpdir}/pg.log", "start",
            ],
            check=True,
            capture_output=True,
        )
        for _ in range(30):
            r = subprocess.run(
                ["pg_isready", "-h", tmpdir, "-p", str(port)],
                capture_output=True,
            )
            if r.returncode == 0:
                break
            time.sleep(0.1)
        else:
            raise RuntimeError("Postgres did not start in time")

        subprocess.run(
            ["createdb", "-h", tmpdir, "-p", str(port), "centaur_test"],
            check=True,
            capture_output=True,
        )

        dsn = f"postgresql://localhost:{port}/centaur_test?host={tmpdir}"
        yield dsn

    finally:
        subprocess.run(
            ["pg_ctl", "-D", tmpdir, "stop", "-m", "immediate"],
            capture_output=True,
        )
        shutil.rmtree(tmpdir, ignore_errors=True)


def _extract_up_sql(path: Path) -> str:
    """Extract the ``-- migrate:up`` section from a dbmate-style migration file."""
    text = path.read_text()
    match = re.search(r"-- migrate:up\s*\n(.*?)(?=-- migrate:down|$)", text, re.DOTALL)
    if not match:
        raise ValueError(f"No '-- migrate:up' section found in {path}")
    return match.group(1).strip()


@pytest.fixture(scope="session")
def run_migrations(pg):
    """Run all migration SQL files against the ephemeral Postgres."""
    migrations_dir = Path(__file__).resolve().parent.parent / "db" / "migrations"
    # Parse tmpdir from DSN: postgresql://localhost:15432/centaur_test?host=/tmp/...
    tmpdir = pg.split("?host=")[1]
    port = "15432"

    for migration_file in sorted(migrations_dir.glob("*.sql")):
        up_sql = _extract_up_sql(migration_file)
        subprocess.run(
            ["psql", "-h", tmpdir, "-p", port, "-d", "centaur_test", "-c", up_sql],
            check=True,
            capture_output=True,
        )


@pytest.fixture(scope="session")
def _setup_env(pg, run_migrations):
    """Set env vars before any app code is imported."""
    os.environ["DATABASE_URL"] = pg
    os.environ["API_SECRET_KEY"] = "test-secret-key"


@pytest.fixture(scope="session")
def app(_setup_env):
    """Import and return the real FastAPI app (after env is configured)."""
    from api.app import app as real_app

    return real_app


@pytest_asyncio.fixture
async def client(app):
    """Async httpx client with lifespan-managed app state (db_pool etc.)."""
    from asgi_lifespan import LifespanManager

    async with LifespanManager(app) as manager:
        transport = httpx.ASGITransport(app=manager.app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
            yield c


@pytest.fixture
def api_key():
    """Return the test API key."""
    return os.environ["API_SECRET_KEY"]


@pytest_asyncio.fixture
async def db_pool(app):
    """Yield the live asyncpg pool from the running app."""
    from asgi_lifespan import LifespanManager

    async with LifespanManager(app) as manager:
        yield manager.app.state.db_pool
