from __future__ import annotations

import subprocess
from pathlib import Path

import asyncpg
import structlog

log = structlog.get_logger()

MIGRATIONS_DIR = Path(__file__).resolve().parent.parent / "db" / "migrations"


async def create_pool(database_url: str) -> asyncpg.Pool:
    run_migrations(database_url)
    pool = await asyncpg.create_pool(
        database_url,
        min_size=2,
        max_size=10,
        command_timeout=60,
    )
    assert pool is not None
    return pool


async def close_pool(pool: asyncpg.Pool) -> None:
    await pool.close()


def run_migrations(database_url: str) -> None:
    """Run pending dbmate migrations. Idempotent — safe to call on every startup."""
    if not MIGRATIONS_DIR.exists():
        log.warning("migrations_dir_missing", path=str(MIGRATIONS_DIR))
        return
    # dbmate's Go pq driver requires explicit sslmode for non-SSL connections
    dbmate_url = database_url
    if "sslmode=" not in dbmate_url:
        sep = "&" if "?" in dbmate_url else "?"
        dbmate_url += f"{sep}sslmode=disable"
    try:
        result = subprocess.run(
            ["dbmate", "--url", dbmate_url, "--migrations-dir", str(MIGRATIONS_DIR), "--no-dump-schema", "up"],
            capture_output=True,
            text=True,
            timeout=30,
        )
        if result.returncode != 0:
            log.error("dbmate_failed", stderr=result.stderr.strip(), returncode=result.returncode)
            raise RuntimeError(f"dbmate migration failed: {result.stderr.strip()}")
        if result.stderr.strip():
            for line in result.stderr.strip().splitlines():
                log.info("dbmate", output=line)
        log.info("migrations_applied")
    except FileNotFoundError:
        log.warning("dbmate_not_found", msg="dbmate binary not in PATH, skipping migrations")
