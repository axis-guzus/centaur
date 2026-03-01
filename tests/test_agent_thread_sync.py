from __future__ import annotations

from api import agent
from api.agent import (
    _MAX_SLACK_MESSAGE_CHARS,
    _SLACK_TRUNCATED_SUFFIX,
    _slack_thread_parts,
    _thread_name_from_user_message,
    _truncate_slack_message,
    reap_stale_running_sessions,
)


def test_slack_thread_parts_accepts_canonical_channel_key() -> None:
    assert _slack_thread_parts("C12345678:1730843413.123456") == ("C12345678", "1730843413.123456")


def test_slack_thread_parts_accepts_slack_prefixed_key() -> None:
    assert _slack_thread_parts("slack:C12345678:1730843413.123456") == (
        "C12345678",
        "1730843413.123456",
    )


def test_slack_thread_parts_rejects_non_slack_like_channel_key() -> None:
    assert _slack_thread_parts("test:e2e-1") is None


def test_slack_thread_parts_rejects_non_thread_ts_shape() -> None:
    assert _slack_thread_parts("C12345678:not-a-slack-thread-ts") is None


def test_truncate_slack_message_keeps_short_content() -> None:
    text = "short message"
    assert _truncate_slack_message(text) == text


def test_truncate_slack_message_applies_consistent_limit_and_suffix() -> None:
    text = "x" * (_MAX_SLACK_MESSAGE_CHARS + 200)
    truncated = _truncate_slack_message(text)
    assert len(truncated) <= _MAX_SLACK_MESSAGE_CHARS
    assert truncated.endswith(_SLACK_TRUNCATED_SUFFIX)


def test_thread_name_from_user_message_strips_context_and_mentions() -> None:
    message = (
        "<@U123>\n"
        "---\n"
        "@assistant please investigate why thread streaming fails in prod and summarize"
    )
    thread_name = _thread_name_from_user_message(message)
    assert thread_name == "please investigate why thread streaming fails in prod and su"
    assert thread_name is not None and len(thread_name) <= 60


def test_reap_stale_running_sessions_marks_idle_without_active_turn(monkeypatch) -> None:
    key = "C12345678:1730843413.123456"
    session = {
        "container_id": "abc123",
        "harness": "codex",
        "agent_thread_id": None,
        "state": "running",
        "created_at": 1000.0,
        "last_activity": 1000.0,
        "turns": [{"turn_id": 1, "finished_at": 1001.0}],
        "thread_name": None,
    }
    persisted: list[tuple[str, dict[str, object]]] = []
    monkeypatch.setattr(
        agent,
        "_persist_session",
        lambda sess, thread_key: persisted.append((thread_key, dict(sess))),
    )
    agent.set_session_state(key, dict(session))
    try:
        result = reap_stale_running_sessions(stale_after_s=600, now_ts=1700.0)
        assert result["reaped"] == 1
        assert key in result["thread_keys"]
        live = agent.get_session_state(key)
        assert live is not None
        assert live["state"] == "idle"
        assert persisted and persisted[0][0] == key
    finally:
        agent.pop_session_state(key)


def test_reap_stale_running_sessions_skips_when_turn_is_active(monkeypatch) -> None:
    key = "C87654321:1730843413.654321"
    session = {
        "container_id": "def456",
        "harness": "codex",
        "agent_thread_id": None,
        "state": "running",
        "created_at": 1000.0,
        "last_activity": 1000.0,
        "turns": [{"turn_id": 1, "finished_at": None}],
        "thread_name": None,
    }
    persisted: list[tuple[str, dict[str, object]]] = []
    monkeypatch.setattr(
        agent,
        "_persist_session",
        lambda sess, thread_key: persisted.append((thread_key, dict(sess))),
    )
    agent.set_session_state(key, dict(session))
    try:
        result = reap_stale_running_sessions(stale_after_s=600, now_ts=1700.0)
        assert result["reaped"] == 0
        live = agent.get_session_state(key)
        assert live is not None
        assert live["state"] == "running"
        assert persisted == []
    finally:
        agent.pop_session_state(key)
