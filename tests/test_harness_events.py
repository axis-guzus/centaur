from __future__ import annotations

from api.harness_events import normalize_harness_event


def test_codex_fallback_tool_call_id_is_stable_across_started_completed() -> None:
    started = {
        "type": "item.started",
        "item": {
            "type": "mcp_tool_call",
            "tool": "read_file",
            "arguments": {"path": "src/api/agent.py"},
        },
    }
    completed = {
        "type": "item.completed",
        "item": {
            "type": "mcp_tool_call",
            "tool": "read_file",
            "arguments": {"path": "src/api/agent.py"},
            "result": "ok",
        },
    }

    started_events = normalize_harness_event("codex", started)
    completed_events = normalize_harness_event("codex", completed)

    started_id = started_events[0]["message"]["content"][0]["id"]
    completed_id = completed_events[0]["content"][0]["tool_use_id"]
    assert started_id
    assert started_id == completed_id


def test_amp_tool_result_without_linkage_is_dropped() -> None:
    raw_event = {
        "type": "user",
        "message": {"content": [{"type": "tool_result", "content": "ok"}]},
    }
    assert normalize_harness_event("amp", raw_event) == []


def test_pi_tool_execution_start_without_id_gets_stable_fallback() -> None:
    raw_event = {
        "type": "tool_execution_start",
        "toolName": "search",
        "args": {"query": "status"},
    }
    events = normalize_harness_event("pi-mono", raw_event)
    tool_id = events[0]["message"]["content"][0]["id"]
    assert tool_id.startswith("tool-call-")


def test_pi_tool_result_without_linkage_is_dropped() -> None:
    raw_event = {
        "type": "tool_execution_end",
        "result": {"content": [{"type": "text", "text": "ok"}]},
        "isError": False,
    }
    assert normalize_harness_event("pi-mono", raw_event) == []


def test_codex_stringified_arguments_and_tool_use_id_alias_are_supported() -> None:
    started = {
        "type": "item.started",
        "item": {
            "type": "tool_call",
            "toolName": "read_file",
            "toolUseId": "toolu_42",
            "arguments": '{"path":"src/api/app.py"}',
        },
    }
    events = normalize_harness_event("codex", started)
    content = events[0]["message"]["content"][0]

    assert content["id"] == "toolu_42"
    assert content["name"] == "read_file"
    assert content["input"] == {"path": "src/api/app.py"}


def test_codex_reasoning_item_updated_emits_reasoning_event() -> None:
    updated = {
        "type": "item.updated",
        "item": {"type": "reasoning", "thinking": "Checking edge cases"},
    }
    assert normalize_harness_event("codex", updated) == [
        {"type": "reasoning", "text": "Checking edge cases"}
    ]
