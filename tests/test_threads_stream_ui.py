from __future__ import annotations

import os

os.environ.setdefault("DATABASE_URL", "postgresql://user:pass@localhost:5432/test")

from api.routers.threads import _raw_item_call_id, _ui_stream_chunks_for_event


def test_item_updated_tool_call_does_not_mark_completion() -> None:
    event = {
        "type": "item.updated",
        "item": {
            "type": "mcp_tool_call",
            "tool": "read_file",
            "arguments": {"path": "src/api/agent.py"},
        },
    }

    chunks = _ui_stream_chunks_for_event(1, 0, event, {}, {})
    assert chunks == []


def test_missing_tool_ids_pair_started_and_completed_without_collision() -> None:
    pending_ids: dict[tuple[int, str], list[str]] = {}
    call_counters: dict[tuple[int, str], int] = {}
    base_item = {
        "type": "mcp_tool_call",
        "tool": "read_file",
        "arguments": {"path": "src/api/agent.py"},
    }

    started_1 = _ui_stream_chunks_for_event(
        7,
        1,
        {"type": "item.started", "item": dict(base_item)},
        pending_ids,
        call_counters,
    )
    started_2 = _ui_stream_chunks_for_event(
        7,
        2,
        {"type": "item.started", "item": dict(base_item)},
        pending_ids,
        call_counters,
    )
    completed_1 = _ui_stream_chunks_for_event(
        7,
        3,
        {"type": "item.completed", "item": {**base_item, "result": "first"}},
        pending_ids,
        call_counters,
    )
    completed_2 = _ui_stream_chunks_for_event(
        7,
        4,
        {"type": "item.completed", "item": {**base_item, "result": "second"}},
        pending_ids,
        call_counters,
    )

    start_id_1 = started_1[0]["toolCallId"]
    start_id_2 = started_2[0]["toolCallId"]
    done_id_1 = completed_1[0]["toolCallId"]
    done_id_2 = completed_2[0]["toolCallId"]

    assert start_id_1 != start_id_2
    assert done_id_1 == start_id_1
    assert done_id_2 == start_id_2


def test_missing_started_event_uses_event_scoped_fallback_id() -> None:
    # Simulates live_only attach in the middle of a run.
    event = {
        "type": "item.completed",
        "item": {
            "type": "mcp_tool_call",
            "tool": "read_file",
            "arguments": {"path": "src/api/agent.py"},
            "result": "ok",
        },
    }

    chunks = _ui_stream_chunks_for_event(3, 11, event, {}, {})
    assert chunks[0]["type"] == "tool-output-available"
    assert chunks[0]["toolCallId"].endswith("-e11")


def test_raw_item_call_id_with_explicit_id_is_passthrough() -> None:
    item = {"type": "mcp_tool_call", "id": "tool_abc123"}
    call_id = _raw_item_call_id(item, 1, event_type="item.started", pending_ids={}, call_counters={})
    assert call_id == "tool_abc123"
