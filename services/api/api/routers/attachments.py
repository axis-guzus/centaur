"""Attachments router — download attachments from sandbox agents."""

from __future__ import annotations

import structlog
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import Response

from api.deps import verify_api_key

log = structlog.get_logger()

router = APIRouter(
    prefix="/agent/attachments",
    tags=["attachments"],
    dependencies=[Depends(verify_api_key)],
)


@router.get("")
async def list_attachments(request: Request, thread_key: str):
    """List attachment metadata for a thread."""
    pool = request.app.state.db_pool
    rows = await pool.fetch(
        "SELECT id, thread_key, message_id, name, mime_type, created_at "
        "FROM attachments WHERE thread_key = $1 ORDER BY created_at",
        thread_key,
    )
    return [
        {
            "id": row["id"],
            "name": row["name"],
            "mime_type": row["mime_type"],
            "message_id": row["message_id"],
            "created_at": row["created_at"].isoformat() if row["created_at"] else None,
        }
        for row in rows
    ]


@router.get("/{attachment_id}/download")
async def download_attachment(request: Request, attachment_id: str):
    """Download attachment raw bytes."""
    pool = request.app.state.db_pool
    row = await pool.fetchrow(
        "SELECT data, mime_type, name FROM attachments WHERE id = $1",
        attachment_id,
    )
    if not row:
        raise HTTPException(status_code=404, detail="Attachment not found")
    return Response(
        content=row["data"],
        media_type=row["mime_type"],
        headers={"Content-Disposition": f'attachment; filename="{row["name"]}"'},
    )
