from __future__ import annotations

import pytest

from api.harness_events import normalize_harness_event
from api.thread_usage import estimate_usage_cost_usd, summarize_thread_token_usage


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


@pytest.mark.parametrize(
    ("harness", "raw_event", "expected_quality", "expected_model", "expected_cost"),
    [
        (
            "amp",
            {
                "type": "assistant",
                "message": {
                    "content": [{"type": "text", "text": "hello"}],
                    "usage": {"input_tokens": 120, "output_tokens": 30},
                    "model": "claude-sonnet-4-20250514",
                },
            },
            "estimated",
            "claude-sonnet-4",
            0.00081,
        ),
        (
            "claude-code",
            {
                "type": "assistant",
                "message": {
                    "content": [{"type": "text", "text": "hello"}],
                    "usage": {"input_tokens": 120, "output_tokens": 30},
                    "model": "claude-sonnet-4-20250514",
                },
            },
            "estimated",
            "claude-sonnet-4",
            0.00081,
        ),
        (
            "eng",
            {
                "type": "assistant",
                "message": {
                    "content": [{"type": "text", "text": "hello"}],
                    "usage": {"input_tokens": 120, "output_tokens": 30},
                    "model": "claude-sonnet-4-20250514",
                },
            },
            "estimated",
            "claude-sonnet-4",
            0.00081,
        ),
        (
            "legal",
            {
                "type": "assistant",
                "message": {
                    "content": [{"type": "text", "text": "hello"}],
                    "usage": {"input_tokens": 120, "output_tokens": 30},
                    "model": "claude-sonnet-4-20250514",
                },
            },
            "estimated",
            "claude-sonnet-4",
            0.00081,
        ),
        (
            "codex",
            {
                "type": "turn.completed",
                "message": {
                    "usage": {"input_tokens": 120, "output_tokens": 30},
                    "model": "gpt-5.3-codex",
                },
            },
            "authoritative",
            "gpt-5.3-codex",
            0.00063,
        ),
        (
            "pi-mono",
            {
                "type": "message_end",
                "message": {
                    "role": "assistant",
                    "model": "claude-haiku-3-5-20241022",
                    "usage": {"input_tokens": 120, "output_tokens": 30},
                    "content": [
                        {"type": "thinking", "thinking": "hmm"},
                        {"type": "text", "text": "hello"},
                    ],
                },
            },
            "estimated",
            "claude-haiku-3-5",
            0.000216,
        ),
    ],
)
def test_supported_harness_normalization_preserves_usage_for_thread_summary(
    harness: str,
    raw_event: dict,
    expected_quality: str,
    expected_model: str,
    expected_cost: float,
) -> None:
    normalized = normalize_harness_event(harness, raw_event)

    usage = summarize_thread_token_usage([{"turn_id": 1, "events": normalized}])

    assert usage == {
        "total_tokens": 150,
        "input_tokens": 120,
        "output_tokens": 30,
        "cost_usd": expected_cost,
        "quality": expected_quality,
        "breakdown": "known",
        "models": [expected_model],
    }


def test_authoritative_turn_completed_overrides_partial_usage() -> None:
    turns = [
        {
            "turn_id": 1,
            "events": [
                {
                    "type": "assistant",
                    "message": {
                        "usage": {"input_tokens": 100, "output_tokens": 20},
                        "model": "claude-sonnet-4-20250514",
                    },
                },
                {
                    "type": "turn.completed",
                    "message": {
                        "usage": {"input_tokens": 150, "output_tokens": 50},
                        "model": "claude-sonnet-4-20250514",
                    },
                },
            ],
        }
    ]

    assert summarize_thread_token_usage(turns) == {
        "total_tokens": 200,
        "input_tokens": 150,
        "output_tokens": 50,
        "cost_usd": 0.0012,
        "quality": "authoritative",
        "breakdown": "known",
        "models": ["claude-sonnet-4"],
    }


def test_total_only_payload_is_estimated_and_has_no_cost() -> None:
    turns = [
        {
            "turn_id": 1,
            "events": [
                {
                    "type": "turn.completed",
                    "message": {
                        "usage": {"total_tokens": 61},
                        "model": "claude-sonnet-4-6",
                    },
                }
            ],
        }
    ]

    assert summarize_thread_token_usage(turns) == {
        "total_tokens": 61,
        "input_tokens": None,
        "output_tokens": None,
        "cost_usd": None,
        "quality": "estimated",
        "breakdown": "unknown",
        "models": ["claude-sonnet-4-6"],
    }


def test_multiple_models_sum_costs_and_report_models() -> None:
    turns = [
        {
            "turn_id": 1,
            "events": [
                {
                    "type": "turn.completed",
                    "message": {
                        "usage": {"input_tokens": 1_000_000, "output_tokens": 1_000_000},
                        "model": "claude-opus-4-6",
                    },
                }
            ],
        },
        {
            "turn_id": 2,
            "events": [
                {
                    "type": "turn.completed",
                    "message": {
                        "usage": {"input_tokens": 1_000_000, "output_tokens": 500_000},
                        "model": "gpt-5.3-codex",
                    },
                }
            ],
        },
    ]

    assert summarize_thread_token_usage(turns) == {
        "total_tokens": 3_500_000,
        "input_tokens": 2_000_000,
        "output_tokens": 1_500_000,
        "cost_usd": 38.75,
        "quality": "authoritative",
        "breakdown": "known",
        "models": ["claude-opus-4-6", "gpt-5.3-codex"],
    }


def test_subagent_usage_is_excluded() -> None:
    turns = [
        {
            "turn_id": 1,
            "events": [
                {
                    "type": "subagent",
                    "input_tokens": 999,
                    "output_tokens": 111,
                    "total_tokens": 1110,
                    "model": "claude-opus-4-6",
                }
            ],
        }
    ]

    assert summarize_thread_token_usage(turns) is None


@pytest.mark.parametrize(
    ("model", "expected_cost"),
    [
        ("claude-opus-4-6", 0.03),
        ("claude-sonnet-4-20250514", 0.018),
        ("claude-haiku-3-5", 0.0048),
        ("gpt-5.3-codex", 0.01575),
        ("gpt-5.4-2026-03-05", 0.0175),
        ("gpt-5.3-chat-latest", 0.01575),
        ("gpt-5.2", 0.01575),
        ("openai/gpt-5.1-codex-max", 0.01125),
    ],
)
def test_supported_model_pricing_aliases(model: str, expected_cost: float) -> None:
    assert estimate_usage_cost_usd(model, 1_000, 1_000) == expected_cost
