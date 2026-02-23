from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

import click
import structlog

structlog.configure(
    processors=[
        structlog.contextvars.merge_contextvars,
        structlog.processors.add_log_level,
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.dev.ConsoleRenderer(),
    ],
)

log = structlog.get_logger()


@click.group()
def cli() -> None:
    """ai-v2-dataplane: ETL pipeline for Postgres+pgvector."""
    pass


@cli.command()
@click.option("--source", "-s", multiple=True, help="Specific sources to sync")
def sync(source: tuple[str, ...]) -> None:
    """Run full or per-source sync (extract → transform → embed)."""
    from .config import Settings
    from .pipeline import run_sync

    settings = Settings()
    sources = list(source) if source else None

    results = asyncio.run(run_sync(settings, sources))

    total = sum(r.records_written for r in results)
    click.echo(f"\nSync complete: {len(results)} sources, {total} records written")
    for r in results:
        click.echo(f"  {r.source}: {r.records_written} records ({r.duration_ms}ms)")
        for kind, count in sorted(r.kinds.items()):
            click.echo(f"    {kind}: {count}")


@cli.command()
@click.option("--source", "-s", default=None, help="Filter by source")
@click.option("--batch-size", default=100, help="Records per embedding batch")
def embed(source: str | None, batch_size: int) -> None:
    """Generate/refresh embeddings for raw records."""
    from .config import Settings
    from .db import close_pool, create_pool, fetch
    from .embeddings import EmbeddingService
    from .models import EmbeddingRecord

    settings = Settings()
    if not settings.openai_api_key:
        click.echo("Error: OPENAI_API_KEY not set", err=True)
        sys.exit(1)

    async def _run() -> None:
        pool = await create_pool(settings.database_url)
        svc = EmbeddingService(
            settings.openai_api_key,
            settings.embedding_model,
            settings.embedding_dimensions,
        )

        try:
            # Find records without embeddings
            source_clause = ""
            args: list = []
            if source:
                source_clause = "WHERE r.source = $1"
                args.append(source)

            query = f"""
                SELECT r.source, r.kind, r.external_id,
                       r.data::text AS data_text
                FROM raw_records r
                LEFT JOIN embeddings e
                    ON e.source = r.source
                    AND e.kind = r.kind
                    AND e.source_id = r.external_id
                {source_clause}
                AND e.id IS NULL
                ORDER BY r.fetched_at DESC
            """

            rows = await fetch(pool, query, *args)
            click.echo(f"Found {len(rows)} records without embeddings")

            records: list[EmbeddingRecord] = []
            for row in rows:
                data = json.loads(row["data_text"]) if isinstance(row["data_text"], str) else row["data_text"]
                # Build content string from data
                content_parts: list[str] = []
                for key in ("title", "name", "text", "body", "content", "description", "summary", "snippet"):
                    val = data.get(key)
                    if val and isinstance(val, str):
                        content_parts.append(val)
                if not content_parts:
                    content_parts.append(json.dumps(data)[:2000])

                records.append(
                    EmbeddingRecord(
                        source=row["source"],
                        kind=row["kind"],
                        source_id=row["external_id"],
                        content=" ".join(content_parts)[:8000],
                        metadata={"external_id": row["external_id"]},
                    )
                )

            # Process in batches
            total_stored = 0
            for i in range(0, len(records), batch_size):
                batch = records[i : i + batch_size]
                stored = await svc.embed_and_store(pool, batch)
                total_stored += stored
                click.echo(
                    f"  Embedded batch {i // batch_size + 1}: {stored} records"
                )

            click.echo(f"Embedding complete: {total_stored} records")
        finally:
            await close_pool(pool)

    asyncio.run(_run())


@cli.command()
def status() -> None:
    """Show sync status (record counts, cursor positions)."""
    from .config import Settings
    from .db import close_pool, create_pool, fetch

    settings = Settings()

    async def _run() -> None:
        pool = await create_pool(settings.database_url)
        try:
            # Record counts by source
            rows = await fetch(
                pool,
                """
                SELECT source, kind, COUNT(*) as count
                FROM raw_records
                GROUP BY source, kind
                ORDER BY source, kind
                """,
            )
            click.echo("=== Record Counts ===")
            current_source = ""
            for row in rows:
                if row["source"] != current_source:
                    current_source = row["source"]
                    click.echo(f"\n  {current_source}:")
                click.echo(f"    {row['kind']}: {row['count']}")

            # Cursor positions
            cursors = await fetch(
                pool,
                """
                SELECT source, kind, entity_id, cursor, updated_at
                FROM sync_cursors
                ORDER BY source, kind
                """,
            )
            click.echo("\n=== Sync Cursors ===")
            for row in cursors:
                entity = f"/{row['entity_id']}" if row["entity_id"] else ""
                click.echo(
                    f"  {row['source']}/{row['kind']}{entity}: "
                    f"{row['cursor']} (updated: {row['updated_at']})"
                )

            # Embedding counts
            emb_rows = await fetch(
                pool,
                """
                SELECT source, kind, COUNT(*) as count
                FROM embeddings
                GROUP BY source, kind
                ORDER BY source, kind
                """,
            )
            click.echo("\n=== Embeddings ===")
            for row in emb_rows:
                click.echo(f"  {row['source']}/{row['kind']}: {row['count']}")

        finally:
            await close_pool(pool)

    asyncio.run(_run())


@cli.command()
@click.argument("query")
@click.option("--limit", "-n", default=10, help="Number of results")
@click.option("--source", "-s", default=None, help="Filter by source")
def search(query: str, limit: int, source: str | None) -> None:
    """Test hybrid search (vector + full-text)."""
    from .config import Settings
    from .db import close_pool, create_pool
    from .embeddings import EmbeddingService, hybrid_search

    settings = Settings()
    if not settings.openai_api_key:
        click.echo("Error: OPENAI_API_KEY not set", err=True)
        sys.exit(1)

    async def _run() -> None:
        pool = await create_pool(settings.database_url)
        svc = EmbeddingService(
            settings.openai_api_key,
            settings.embedding_model,
            settings.embedding_dimensions,
        )

        try:
            embeddings = await svc.embed_texts([query])
            query_embedding = embeddings[0]

            results = await hybrid_search(
                pool,
                query,
                query_embedding,
                limit=limit,
                source_filter=source,
            )

            click.echo(f"\nSearch results for: {query}\n")
            for i, r in enumerate(results):
                click.echo(f"--- Result {i + 1} ---")
                click.echo(f"  Source: {r['source']}/{r['kind']}")
                click.echo(f"  ID: {r['source_id']}")
                click.echo(
                    f"  Scores: vec={r['vec_score']:.4f} "
                    f"fts={r['fts_score']:.4f} "
                    f"rrf={r['rrf_score']:.6f}"
                )
                content = r["content"][:200]
                click.echo(f"  Content: {content}...")
                click.echo()
        finally:
            await close_pool(pool)

    asyncio.run(_run())


@cli.command("migrate-from-sqlite")
@click.argument("sqlite_path")
def migrate_from_sqlite(sqlite_path: str) -> None:
    """Import data from existing metronome SQLite DB."""
    import sqlite3

    from .config import Settings
    from .db import close_pool, create_pool

    settings = Settings()
    db_path = Path(sqlite_path)
    if not db_path.exists():
        click.echo(f"Error: SQLite DB not found at {sqlite_path}", err=True)
        sys.exit(1)

    async def _run() -> None:
        pool = await create_pool(settings.database_url)

        try:
            conn = sqlite3.connect(str(db_path))
            conn.row_factory = sqlite3.Row

            # Migrate raw records
            click.echo("Migrating raw_records...")
            cursor = conn.execute(
                "SELECT source, kind, external_id, fetched_at, content_hash, data "
                "FROM raw__records"
            )

            batch: list[tuple] = []
            total = 0
            while True:
                rows = cursor.fetchmany(1000)
                if not rows:
                    break

                async with pool.acquire() as pg:
                    for row in rows:
                        await pg.execute(
                            """
                            INSERT INTO raw_records
                                (source, kind, external_id, fetched_at, content_hash, data)
                            VALUES ($1, $2, $3, $4, $5, $6::jsonb)
                            ON CONFLICT DO NOTHING
                            """,
                            row["source"],
                            row["kind"],
                            row["external_id"],
                            row["fetched_at"],
                            row["content_hash"],
                            row["data"],
                        )
                        total += 1

                click.echo(f"  Migrated {total} records...")

            # Migrate cursors
            click.echo("Migrating sync_cursors...")
            try:
                cursor = conn.execute(
                    "SELECT cursor_key, source, kind, entity_id, cursor, updated_at "
                    "FROM sync_cursors"
                )
                cursor_rows = cursor.fetchall()
                async with pool.acquire() as pg:
                    for row in cursor_rows:
                        await pg.execute(
                            """
                            INSERT INTO sync_cursors
                                (cursor_key, source, kind, entity_id, cursor, updated_at)
                            VALUES ($1, $2, $3, $4, $5, $6)
                            ON CONFLICT DO NOTHING
                            """,
                            row["cursor_key"],
                            row["source"],
                            row["kind"],
                            row["entity_id"],
                            row["cursor"],
                            row["updated_at"],
                        )
            except sqlite3.OperationalError:
                click.echo("  No sync_cursors table found, skipping")

            # Migrate people
            click.echo("Migrating people...")
            try:
                cursor = conn.execute(
                    "SELECT slug, name, email, role, is_direct_report, focus_area "
                    "FROM people"
                )
                people_rows = cursor.fetchall()
                async with pool.acquire() as pg:
                    for row in people_rows:
                        await pg.execute(
                            """
                            INSERT INTO people
                                (slug, name, email, role, is_direct_report, focus_area)
                            VALUES ($1, $2, $3, $4, $5, $6)
                            ON CONFLICT DO NOTHING
                            """,
                            row["slug"],
                            row["name"],
                            row["email"],
                            row["role"],
                            bool(row["is_direct_report"]),
                            row["focus_area"],
                        )
            except sqlite3.OperationalError:
                click.echo("  No people table found, skipping")

            # Migrate entity mappings
            click.echo("Migrating entity_mappings...")
            try:
                cursor = conn.execute(
                    "SELECT source, external_id, person_slug FROM entity_mappings"
                )
                mapping_rows = cursor.fetchall()
                async with pool.acquire() as pg:
                    for row in mapping_rows:
                        await pg.execute(
                            """
                            INSERT INTO entity_mappings
                                (source, external_id, person_slug)
                            VALUES ($1, $2, $3)
                            ON CONFLICT DO NOTHING
                            """,
                            row["source"],
                            row["external_id"],
                            row["person_slug"],
                        )
            except sqlite3.OperationalError:
                click.echo("  No entity_mappings table found, skipping")

            conn.close()
            click.echo(f"\nMigration complete: {total} raw records imported")
        finally:
            await close_pool(pool)

    asyncio.run(_run())


@cli.command()
@click.option("--interval", "-i", default=None, type=int, help="Sync interval in seconds")
def continuous(interval: int | None) -> None:
    """Run continuous sync loop."""
    from .config import Settings
    from .pipeline import run_continuous

    settings = Settings()
    asyncio.run(run_continuous(settings, interval))


if __name__ == "__main__":
    cli()
