"""Thread viewer API.

Live threads are streamed from in-memory sessions via SSE.
Historical/completed threads are read from Postgres.
"""

from __future__ import annotations

import asyncio
import json
from typing import Annotated, Any

import asyncpg
from fastapi import APIRouter, Depends, HTTPException, Request
from starlette.responses import StreamingResponse

from api.agent import get_session_state, session_items_snapshot
from api.deps import get_pool, verify_ui_or_api_key

router = APIRouter(
    prefix="/api/threads",
    tags=["threads"],
    dependencies=[Depends(verify_ui_or_api_key)],
)


def _build_live_detail(key: str, session: dict[str, Any]) -> dict[str, Any]:
    """Build thread detail from an in-memory session."""
    return {
        "slack_thread_key": key,
        "container_id": session["container_id"][:12],
        "harness": session["harness"],
        "agent_thread_id": session.get("agent_thread_id"),
        "state": session["state"],
        "created_at": session["created_at"],
        "last_activity": session["last_activity"],
        "turns": session.get("turns", []),
        "thread_name": session.get("thread_name"),
    }


@router.get("")
async def list_threads(
    pool: Annotated[asyncpg.Pool, Depends(get_pool)],
) -> dict[str, Any]:
    """List all agent sessions with summary info."""
    rows = await pool.fetch(
        """
        SELECT
            s.slack_thread_key,
            s.container_id,
            s.harness,
            s.agent_thread_id,
            s.state,
            s.thread_name,
            extract(epoch from s.created_at)    AS created_at,
            extract(epoch from s.last_activity) AS last_activity,
            coalesce(tc.turn_count, 0)          AS turn_count,
            coalesce(lt.result, '')              AS last_result,
            coalesce(ft.first_message, '')       AS first_message
        FROM agent_sessions s
        LEFT JOIN LATERAL (
            SELECT count(*) AS turn_count
            FROM agent_turns t WHERE t.slack_thread_key = s.slack_thread_key
        ) tc ON true
        LEFT JOIN LATERAL (
            SELECT t.result
            FROM agent_turns t
            WHERE t.slack_thread_key = s.slack_thread_key
            ORDER BY t.turn_id DESC LIMIT 1
        ) lt ON true
        LEFT JOIN LATERAL (
            SELECT t.user_message AS first_message
            FROM agent_turns t
            WHERE t.slack_thread_key = s.slack_thread_key
            ORDER BY t.turn_id ASC LIMIT 1
        ) ft ON true
        ORDER BY s.last_activity DESC
        """
    )
    pg_keys: set[str] = set()
    threads = []
    for r in rows:
        key = r["slack_thread_key"]
        pg_keys.add(key)
        live = get_session_state(key)
        live_turns = live.get("turns", []) if live else []
        live_first_message = ""
        live_last_result = ""
        if live_turns:
            live_first_message = str(live_turns[0].get("user_message") or "")
            live_last_result = str(live_turns[-1].get("result") or "")
        threads.append(
            {
                "slack_thread_key": key,
                "container_id": r["container_id"][:12],
                "harness": live["harness"] if live else r["harness"],
                "agent_thread_id": live.get("agent_thread_id") if live else r["agent_thread_id"],
                "state": live["state"] if live else r["state"],
                "created_at": float(r["created_at"]),
                "last_activity": live["last_activity"] if live else float(r["last_activity"]),
                "turn_count": len(live_turns) if live else r["turn_count"],
                "last_result": (live_last_result if live_last_result else (r["last_result"] or ""))[:200],
                "first_message": (
                    live_first_message if live_first_message else (r["first_message"] or "")
                )[:200],
                "thread_name": live.get("thread_name") if live else r.get("thread_name"),
            }
        )
    for key, live in session_items_snapshot():
        if key not in pg_keys:
            first_msg = ""
            last_result = ""
            if live.get("turns"):
                first_msg = live["turns"][0].get("user_message", "")
                last_result = live["turns"][-1].get("result", "")
            threads.append(
                {
                    "slack_thread_key": key,
                    "container_id": live["container_id"][:12],
                    "harness": live["harness"],
                    "agent_thread_id": live.get("agent_thread_id"),
                    "state": live["state"],
                    "created_at": live["created_at"],
                    "last_activity": live["last_activity"],
                    "turn_count": len(live.get("turns", [])),
                    "last_result": last_result[:200],
                    "first_message": first_msg[:200],
                    "thread_name": live.get("thread_name"),
                }
            )
    threads.sort(key=lambda t: t.get("last_activity") or 0, reverse=True)
    return {"threads": threads, "count": len(threads)}


async def _fetch_pg_detail(pool: asyncpg.Pool, key: str) -> dict[str, Any]:
    """Read full thread detail from Postgres. Raises HTTPException(404) if not found."""
    row = await pool.fetchrow(
        """
        SELECT
            slack_thread_key,
            container_id,
            harness,
            agent_thread_id,
            state,
            thread_name,
            extract(epoch from created_at)    AS created_at,
            extract(epoch from last_activity) AS last_activity
        FROM agent_sessions
        WHERE slack_thread_key = $1
        """,
        key,
    )
    if not row:
        raise HTTPException(status_code=404, detail=f"Thread '{key}' not found")

    turn_rows = await pool.fetch(
        """
        SELECT
            turn_id,
            user_message,
            events,
            result,
            extract(epoch from started_at)  AS started_at,
            extract(epoch from finished_at) AS finished_at,
            exit_code,
            timed_out,
            duration_s
        FROM agent_turns
        WHERE slack_thread_key = $1
        ORDER BY turn_id
        """,
        key,
    )

    turns = []
    for t in turn_rows:
        events_raw = t["events"]
        if isinstance(events_raw, str):
            events_raw = json.loads(events_raw)
        turns.append(
            {
                "turn_id": t["turn_id"],
                "user_message": t["user_message"],
                "events": events_raw,
                "result": t["result"],
                "started_at": float(t["started_at"]) if t["started_at"] else None,
                "finished_at": float(t["finished_at"]) if t["finished_at"] else None,
                "exit_code": t["exit_code"],
                "timed_out": t["timed_out"],
                "duration_s": float(t["duration_s"]),
            }
        )

    return {
        "slack_thread_key": row["slack_thread_key"],
        "container_id": row["container_id"][:12],
        "harness": row["harness"],
        "agent_thread_id": row["agent_thread_id"],
        "state": row["state"],
        "thread_name": row.get("thread_name"),
        "created_at": float(row["created_at"]),
        "last_activity": float(row["last_activity"]),
        "turns": turns,
    }


@router.get("/detail")
async def get_thread(
    key: str,
    pool: Annotated[asyncpg.Pool, Depends(get_pool)],
) -> dict[str, Any]:
    """Get full thread detail. Prefers live in-memory data, falls back to PG."""
    session = get_session_state(key)
    if not session and not key.startswith("slack:"):
        session = get_session_state(f"slack:{key}")
        if session:
            key = f"slack:{key}"

    if session:
        return _build_live_detail(key, session)

    try:
        return await _fetch_pg_detail(pool, key)
    except HTTPException:
        if not key.startswith("slack:"):
            try:
                return await _fetch_pg_detail(pool, f"slack:{key}")
            except HTTPException:
                pass
        raise


# SSE comment keepalive sent when no data for this many seconds (prevents proxy timeouts)
_SSE_KEEPALIVE_INTERVAL_S = 15


@router.get("/stream")
async def stream_thread(
    request: Request,
    key: str,
    pool: Annotated[asyncpg.Pool, Depends(get_pool)],
) -> StreamingResponse:
    """SSE stream of thread updates. Live sessions stream from memory;
    historical threads send a single snapshot from Postgres."""

    async def generate():
        nonlocal key
        # If not in memory, send PG snapshot immediately and close
        session = get_session_state(key)
        if not session and not key.startswith("slack:"):
            session = get_session_state(f"slack:{key}")
            if session:
                key = f"slack:{key}"

        if not session:
            try:
                detail = await _fetch_pg_detail(pool, key)
                yield f"data: {json.dumps(detail, default=str)}\n\n"
            except HTTPException:
                if not key.startswith("slack:"):
                    try:
                        detail = await _fetch_pg_detail(pool, f"slack:{key}")
                        yield f"data: {json.dumps(detail, default=str)}\n\n"
                        return
                    except HTTPException:
                        pass
                # Emit a normal message event so EventSource.onmessage receives it.
                yield f"data: {json.dumps({'error': 'not_found'})}\n\n"
            return

        last_event_count = -1
        last_state = ""
        ticks_since_data = 0

        while True:
            if await request.is_disconnected():
                break

            session = get_session_state(key)
            if not session:
                break

            total_events = sum(len(t.get("events", [])) for t in session.get("turns", []))
            state = session.get("state", "")

            if total_events != last_event_count or state != last_state:
                detail = _build_live_detail(key, session)
                yield f"data: {json.dumps(detail, default=str)}\n\n"
                last_event_count = total_events
                last_state = state
                ticks_since_data = 0
            else:
                ticks_since_data += 1

            # Keep stream open for idle threads so the UI does not churn on reconnect.
            # Keepalive: send SSE comment when no data for 15s (prevents proxy timeouts)
            if ticks_since_data * 0.3 >= _SSE_KEEPALIVE_INTERVAL_S:
                yield ":keepalive\n\n"
                ticks_since_data = 0

            await asyncio.sleep(0.3)

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
