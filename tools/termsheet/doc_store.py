"""Postgres-backed legal document store with versioning and audit logs."""

from __future__ import annotations

import asyncio
import json
import os
import uuid
from typing import Any

import asyncpg


def _database_url() -> str:
    url = os.getenv("DATABASE_URL", "").strip()
    if not url:
        raise RuntimeError("DATABASE_URL is required for legal document storage")
    return url


async def _with_conn() -> asyncpg.Connection:
    return await asyncpg.connect(_database_url())


async def _ensure_tables(conn: asyncpg.Connection) -> None:
    await conn.execute(
        """
        CREATE TABLE IF NOT EXISTS legal_documents (
            id               TEXT PRIMARY KEY,
            document_type    TEXT NOT NULL,
            company_name     TEXT,
            title            TEXT NOT NULL,
            status           TEXT NOT NULL DEFAULT 'draft',
            current_version  INT NOT NULL DEFAULT 0,
            deal_id          TEXT,
            slack_thread_key TEXT,
            requester_id     TEXT,
            playbook_id      TEXT,
            terms            JSONB NOT NULL DEFAULT '{}'::jsonb,
            metadata         JSONB NOT NULL DEFAULT '{}'::jsonb,
            created_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at       TIMESTAMPTZ NOT NULL DEFAULT now()
        );
        """
    )
    await conn.execute(
        """
        CREATE TABLE IF NOT EXISTS legal_document_versions (
            id                BIGSERIAL PRIMARY KEY,
            document_id       TEXT NOT NULL REFERENCES legal_documents(id) ON DELETE CASCADE,
            version           INT NOT NULL,
            terms             JSONB NOT NULL DEFAULT '{}'::jsonb,
            content_text      TEXT NOT NULL,
            source_file_url   TEXT,
            source_file_hash  TEXT,
            diff_summary      TEXT,
            diff_details      JSONB,
            compliance_report JSONB,
            requested_by      TEXT,
            request_text      TEXT,
            created_at        TIMESTAMPTZ NOT NULL DEFAULT now(),
            UNIQUE (document_id, version)
        );
        """
    )
    await conn.execute(
        """
        CREATE TABLE IF NOT EXISTS legal_audit_log (
            id          BIGSERIAL PRIMARY KEY,
            document_id TEXT NOT NULL REFERENCES legal_documents(id) ON DELETE CASCADE,
            action      TEXT NOT NULL,
            actor_id    TEXT,
            details     JSONB NOT NULL DEFAULT '{}'::jsonb,
            created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
        );
        """
    )


async def _create_document_async(
    *,
    document_type: str,
    title: str,
    company_name: str | None = None,
    deal_id: str | None = None,
    slack_thread_key: str | None = None,
    requester_id: str | None = None,
    playbook_id: str | None = None,
    terms: dict[str, Any] | None = None,
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    conn = await _with_conn()
    try:
        await _ensure_tables(conn)
        document_id = f"DOC-{uuid.uuid4().hex[:8].upper()}"
        await conn.execute(
            """
            INSERT INTO legal_documents (
                id, document_type, company_name, title, status,
                current_version, deal_id, slack_thread_key, requester_id,
                playbook_id, terms, metadata
            )
            VALUES (
                $1, $2, $3, $4, 'draft',
                0, $5, $6, $7,
                $8, $9::jsonb, $10::jsonb
            )
            """,
            document_id,
            document_type,
            company_name,
            title,
            deal_id,
            slack_thread_key,
            requester_id,
            playbook_id,
            json.dumps(terms or {}),
            json.dumps(metadata or {}),
        )
        await _log_action_async(
            conn,
            document_id=document_id,
            action="created",
            actor_id=requester_id,
            details={"title": title, "document_type": document_type},
        )
        row = await conn.fetchrow(
            "SELECT * FROM legal_documents WHERE id = $1",
            document_id,
        )
        return dict(row) if row is not None else {"id": document_id}
    finally:
        await conn.close()


async def _log_action_async(
    conn: asyncpg.Connection,
    *,
    document_id: str,
    action: str,
    actor_id: str | None = None,
    details: dict[str, Any] | None = None,
) -> None:
    await conn.execute(
        """
        INSERT INTO legal_audit_log (document_id, action, actor_id, details)
        VALUES ($1, $2, $3, $4::jsonb)
        """,
        document_id,
        action,
        actor_id,
        json.dumps(details or {}),
    )


async def _create_version_async(
    *,
    document_id: str,
    terms: dict[str, Any],
    content_text: str,
    source_file_url: str | None = None,
    source_file_hash: str | None = None,
    diff_summary: str | None = None,
    diff_details: dict[str, Any] | list[dict[str, Any]] | None = None,
    compliance_report: dict[str, Any] | None = None,
    requested_by: str | None = None,
    request_text: str | None = None,
) -> dict[str, Any]:
    conn = await _with_conn()
    try:
        await _ensure_tables(conn)
        async with conn.transaction():
            current = await conn.fetchrow(
                "SELECT current_version FROM legal_documents WHERE id = $1 FOR UPDATE",
                document_id,
            )
            if current is None:
                raise RuntimeError(f"Document not found: {document_id}")
            version = int(current["current_version"]) + 1
            await conn.execute(
                """
                INSERT INTO legal_document_versions (
                    document_id, version, terms, content_text, source_file_url,
                    source_file_hash, diff_summary, diff_details, compliance_report,
                    requested_by, request_text
                )
                VALUES (
                    $1, $2, $3::jsonb, $4, $5,
                    $6, $7, $8::jsonb, $9::jsonb,
                    $10, $11
                )
                """,
                document_id,
                version,
                json.dumps(terms),
                content_text,
                source_file_url,
                source_file_hash,
                diff_summary,
                json.dumps(diff_details) if diff_details is not None else None,
                json.dumps(compliance_report) if compliance_report is not None else None,
                requested_by,
                request_text,
            )
            await conn.execute(
                """
                UPDATE legal_documents
                SET current_version = $2,
                    terms = $3::jsonb,
                    updated_at = now()
                WHERE id = $1
                """,
                document_id,
                version,
                json.dumps(terms),
            )
            await _log_action_async(
                conn,
                document_id=document_id,
                action="revised",
                actor_id=requested_by,
                details={"version": version, "diff_summary": diff_summary},
            )
            row = await conn.fetchrow(
                """
                SELECT *
                FROM legal_document_versions
                WHERE document_id = $1 AND version = $2
                """,
                document_id,
                version,
            )
            return dict(row) if row is not None else {"document_id": document_id, "version": version}
    finally:
        await conn.close()


async def _get_current_version_async(document_id: str) -> dict[str, Any] | None:
    conn = await _with_conn()
    try:
        await _ensure_tables(conn)
        row = await conn.fetchrow(
            """
            SELECT v.*
            FROM legal_document_versions v
            JOIN legal_documents d ON d.id = v.document_id
            WHERE v.document_id = $1
              AND v.version = d.current_version
            """,
            document_id,
        )
        return dict(row) if row is not None else None
    finally:
        await conn.close()


async def _get_version_history_async(document_id: str) -> list[dict[str, Any]]:
    conn = await _with_conn()
    try:
        await _ensure_tables(conn)
        rows = await conn.fetch(
            """
            SELECT *
            FROM legal_document_versions
            WHERE document_id = $1
            ORDER BY version DESC
            """,
            document_id,
        )
        return [dict(row) for row in rows]
    finally:
        await conn.close()


async def _update_status_async(
    *,
    document_id: str,
    status: str,
    actor_id: str | None = None,
    details: dict[str, Any] | None = None,
) -> dict[str, Any] | None:
    conn = await _with_conn()
    try:
        await _ensure_tables(conn)
        row = await conn.fetchrow(
            """
            UPDATE legal_documents
            SET status = $2,
                updated_at = now()
            WHERE id = $1
            RETURNING *
            """,
            document_id,
            status,
        )
        if row is None:
            return None
        await _log_action_async(
            conn,
            document_id=document_id,
            action=status,
            actor_id=actor_id,
            details=details or {},
        )
        return dict(row)
    finally:
        await conn.close()


def _run(coro: Any) -> Any:
    return asyncio.run(coro)


def create_document(
    *,
    document_type: str,
    title: str,
    company_name: str | None = None,
    deal_id: str | None = None,
    slack_thread_key: str | None = None,
    requester_id: str | None = None,
    playbook_id: str | None = None,
    terms: dict[str, Any] | None = None,
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Create a legal document root record."""
    return _run(
        _create_document_async(
            document_type=document_type,
            title=title,
            company_name=company_name,
            deal_id=deal_id,
            slack_thread_key=slack_thread_key,
            requester_id=requester_id,
            playbook_id=playbook_id,
            terms=terms,
            metadata=metadata,
        )
    )


def create_version(
    *,
    document_id: str,
    terms: dict[str, Any],
    content_text: str,
    source_file_url: str | None = None,
    source_file_hash: str | None = None,
    diff_summary: str | None = None,
    diff_details: dict[str, Any] | list[dict[str, Any]] | None = None,
    compliance_report: dict[str, Any] | None = None,
    requested_by: str | None = None,
    request_text: str | None = None,
) -> dict[str, Any]:
    """Create a new document version and bump current version pointer."""
    return _run(
        _create_version_async(
            document_id=document_id,
            terms=terms,
            content_text=content_text,
            source_file_url=source_file_url,
            source_file_hash=source_file_hash,
            diff_summary=diff_summary,
            diff_details=diff_details,
            compliance_report=compliance_report,
            requested_by=requested_by,
            request_text=request_text,
        )
    )


def get_current_version(document_id: str) -> dict[str, Any] | None:
    """Get the current version row for a document."""
    return _run(_get_current_version_async(document_id))


def get_version_history(document_id: str) -> list[dict[str, Any]]:
    """Get all versions for a document, newest first."""
    return _run(_get_version_history_async(document_id))


def update_status(
    *,
    document_id: str,
    status: str,
    actor_id: str | None = None,
    details: dict[str, Any] | None = None,
) -> dict[str, Any] | None:
    """Update document status and append audit entry."""
    return _run(
        _update_status_async(
            document_id=document_id,
            status=status,
            actor_id=actor_id,
            details=details,
        )
    )
