from __future__ import annotations

import json
from typing import Any
from unittest.mock import AsyncMock, patch

import pytest
import pytest_asyncio


class FakeCtx:
    def __init__(self, db_pool):
        self._pool = db_pool
        self.run_id = "wfr-test-slack-sync"
        self.logs: list[tuple[str, dict[str, Any]]] = []

    def log(self, msg: str, **kwargs: Any) -> None:
        self.logs.append((msg, kwargs))


class FakeSlackClient:
    def __init__(
        self,
        *,
        channels: list[dict[str, Any]] | None = None,
        users: list[dict[str, Any]] | None = None,
        messages: list[dict[str, Any]] | None = None,
        replies: dict[str, list[dict[str, Any]]] | None = None,
        sync_state: dict[str, Any] | None = None,
    ) -> None:
        self.channels = channels or []
        self.users = users or []
        self.messages = messages or []
        self.replies = replies or {}
        self.sync_state = sync_state or {
            "cursor": None,
            "watermark": "3000000.000000",
            "oldest": None,
            "latest": None,
        }
        self.history_calls: list[dict[str, Any]] = []
        self.reply_calls: list[dict[str, Any]] = []
        self.list_bot_channels_calls = 0
        self.list_users_calls = 0

    def list_bot_channels(self, limit: int = 200, force_refresh: bool = False) -> list[dict]:
        self.list_bot_channels_calls += 1
        return [
            ch
            for ch in self.channels
            if not ch.get("is_private") and ch.get("is_member", True)
        ][:limit]

    def list_users(self, limit: int = 200) -> list[dict]:
        self.list_users_calls += 1
        return self.users[:limit]

    def sync_channel_history(
        self,
        channel: str,
        state: dict[str, Any] | None = None,
        limit: int = 200,
        lookback_days: int = 30,
        oldest: str | int | float | None = None,
        latest: str | int | float | None = None,
    ) -> dict[str, Any]:
        self.history_calls.append({
            "channel": channel,
            "state": state,
            "limit": limit,
            "lookback_days": lookback_days,
            "oldest": oldest,
            "latest": latest,
        })
        return {
            "channel": channel,
            "channel_id": channel,
            "messages": self.messages,
            "count": len(self.messages),
            "has_more": False,
            "next_cursor": None,
            "sync_state": self.sync_state,
        }

    def get_thread_replies_page(
        self,
        channel: str,
        thread_ts: str,
        limit: int = 200,
        cursor: str | None = None,
        oldest: str | int | float | None = None,
        latest: str | int | float | None = None,
        inclusive: bool = True,
    ) -> dict[str, Any]:
        self.reply_calls.append({
            "channel": channel,
            "thread_ts": thread_ts,
            "limit": limit,
            "cursor": cursor,
            "oldest": oldest,
            "latest": latest,
            "inclusive": inclusive,
        })
        messages = self.replies.get(thread_ts, [])
        return {
            "channel_id": channel,
            "thread_ts": thread_ts,
            "messages": messages,
            "count": len(messages),
            "has_more": False,
            "next_cursor": None,
        }


@pytest_asyncio.fixture(autouse=True)
async def _clear_slack_sync_tables(db_pool):
    await db_pool.execute(
        "TRUNCATE TABLE slack_sync_checkpoints, slack_sync_messages, slack_sync_runs, "
        "slack_sync_users, slack_sync_channels CASCADE",
    )
    yield


def _public_channel() -> dict[str, Any]:
    return {
        "id": "C_PUBLIC",
        "name": "ai-agent",
        "is_private": False,
        "is_archived": False,
        "is_member": True,
        "topic": "Agents",
        "purpose": "Testing",
        "member_count": 10,
    }


def _private_channel() -> dict[str, Any]:
    return {
        "id": "G_PRIVATE",
        "name": "private-room",
        "is_private": True,
        "is_archived": False,
        "is_member": True,
    }


def _root_message() -> dict[str, Any]:
    return {
        "channel_id": "C_PUBLIC",
        "timestamp": "3000000.000000",
        "thread_ts": "3000000.000000",
        "user_id": "U1",
        "user": "alice",
        "text": "root",
        "permalink": "https://slack.com/archives/C_PUBLIC/p3000000000000",
        "reply_count": 1,
        "reply_users": ["U2"],
        "latest_reply": "3000001.000000",
        "type": "message",
    }


def _reply_message() -> dict[str, Any]:
    return {
        "channel_id": "C_PUBLIC",
        "timestamp": "3000001.000000",
        "thread_ts": "3000000.000000",
        "user_id": "U2",
        "user": "bob",
        "text": "reply",
        "permalink": "https://slack.com/archives/C_PUBLIC/p3000001000000",
        "reply_count": 0,
        "type": "message",
    }


@pytest.mark.asyncio
async def test_slack_etl_disabled_noops_without_run_row(db_pool, monkeypatch):
    from workflows import slack_sync

    await db_pool.execute(
        "INSERT INTO slack_sync_channels (channel_id, channel_name, is_member) "
        "VALUES ('C_OLD', 'old-channel', TRUE)",
    )
    fake = FakeSlackClient(channels=[_public_channel()])
    ctx = FakeCtx(db_pool)
    monkeypatch.setenv("SLACK_ETL_ENABLED", "false")

    with patch.object(slack_sync, "_client", return_value=fake):
        result = await slack_sync.handler(slack_sync.Input(), ctx)

    assert result["status"] == "skipped"
    assert result["reason"] == "slack_etl_disabled"
    assert fake.list_bot_channels_calls == 0
    assert fake.list_users_calls == 0
    assert await db_pool.fetchval("SELECT COUNT(*) FROM slack_sync_runs") == 0
    assert await db_pool.fetchval(
        "SELECT is_member FROM slack_sync_channels WHERE channel_id = 'C_OLD'",
    ) is True


@pytest.mark.asyncio
async def test_no_bot_member_channels_noops_without_run_row(db_pool):
    from workflows import slack_sync

    await db_pool.execute(
        "INSERT INTO slack_sync_channels (channel_id, channel_name, is_member) "
        "VALUES ('C_OLD', 'old-channel', TRUE)",
    )
    fake = FakeSlackClient(channels=[])
    ctx = FakeCtx(db_pool)

    with patch.object(slack_sync, "_client", return_value=fake):
        result = await slack_sync.handler(slack_sync.Input(), ctx)

    assert result["status"] == "skipped"
    assert result["reason"] == "no_bot_member_channels"
    assert await db_pool.fetchval("SELECT COUNT(*) FROM slack_sync_runs") == 0
    assert await db_pool.fetchval(
        "SELECT is_member FROM slack_sync_channels WHERE channel_id = 'C_OLD'",
    ) is False


@pytest.mark.asyncio
async def test_syncs_bot_member_public_channels(
    db_pool,
):
    from workflows import slack_sync

    fake = FakeSlackClient(
        channels=[_public_channel(), _private_channel()],
        users=[{
            "id": "U1",
            "name": "alice",
            "real_name": "Alice Example",
            "display_name": "Alice",
            "is_bot": False,
        }],
        messages=[_root_message()],
        replies={"3000000.000000": [_root_message(), _reply_message()]},
    )
    ctx = FakeCtx(db_pool)

    with patch.object(slack_sync, "_client", return_value=fake):
        result = await slack_sync.handler(slack_sync.Input(), ctx)

    assert result["status"] == "completed"
    assert result["channels_synced"] == 1
    assert result["channels_skipped"] == 0
    assert result["messages_upserted"] == 1
    assert result["replies_upserted"] == 1

    channel = await db_pool.fetchrow(
        "SELECT channel_name, is_member FROM slack_sync_channels WHERE channel_id = 'C_PUBLIC'",
    )
    assert channel is not None
    assert channel["channel_name"] == "ai-agent"
    assert channel["is_member"] is True
    assert await db_pool.fetchval(
        "SELECT COUNT(*) FROM slack_sync_channels WHERE channel_id = 'G_PRIVATE'",
    ) == 0

    user = await db_pool.fetchrow(
        "SELECT real_name, display_name FROM slack_sync_users WHERE user_id = 'U1'",
    )
    assert user is not None
    assert user["real_name"] == "Alice Example"
    assert user["display_name"] == "Alice"

    messages = await db_pool.fetch(
        "SELECT message_ts, thread_ts, parent_message_ts, text FROM slack_sync_messages "
        "ORDER BY message_ts",
    )
    assert [row["message_ts"] for row in messages] == ["3000000.000000", "3000001.000000"]
    assert messages[1]["thread_ts"] == "3000000.000000"
    assert messages[1]["parent_message_ts"] == "3000000.000000"

    checkpoint = await db_pool.fetchrow(
        "SELECT watermark_ts, thread_lookback_days FROM slack_sync_checkpoints "
        "WHERE channel_id = 'C_PUBLIC'",
    )
    assert checkpoint is not None
    assert checkpoint["watermark_ts"] == "3000000.000000"
    assert checkpoint["thread_lookback_days"] == 3

    run = await db_pool.fetchrow(
        "SELECT status, channels_requested, channels_skipped FROM slack_sync_runs WHERE run_id = $1",
        result["run_id"],
    )
    assert run is not None
    assert run["status"] == "completed"
    assert json.loads(run["channels_requested"])[0]["channel_id"] == "C_PUBLIC"
    assert json.loads(run["channels_skipped"]) == []


@pytest.mark.asyncio
async def test_incremental_oldest_uses_thread_lookback(db_pool):
    from workflows import slack_sync

    await db_pool.execute(
        "INSERT INTO slack_sync_channels (channel_id, channel_name, is_member) "
        "VALUES ('C_PUBLIC', 'ai-agent', TRUE)",
    )
    await db_pool.execute(
        "INSERT INTO slack_sync_checkpoints (channel_id, watermark_ts, thread_lookback_days) "
        "VALUES ('C_PUBLIC', '3000000.000000', 3)",
    )
    fake = FakeSlackClient(channels=[_public_channel()], messages=[], replies={})
    ctx = FakeCtx(db_pool)

    with patch.object(slack_sync, "_client", return_value=fake):
        await slack_sync.handler(slack_sync.Input(), ctx)

    assert fake.history_calls[0]["oldest"] == "2740800.000000"


@pytest.mark.asyncio
async def test_failed_write_does_not_advance_watermark(db_pool):
    from workflows import slack_sync

    fake = FakeSlackClient(channels=[_public_channel()], messages=[_root_message()])
    ctx = FakeCtx(db_pool)

    with (
        patch.object(slack_sync, "_client", return_value=fake),
        patch.object(
            slack_sync,
            "_upsert_messages",
            new=AsyncMock(side_effect=RuntimeError("write failed")),
        ),
    ):
        result = await slack_sync.handler(slack_sync.Input(), ctx)

    assert result["status"] == "failed"
    checkpoint = await db_pool.fetchrow(
        "SELECT watermark_ts, last_error FROM slack_sync_checkpoints "
        "WHERE channel_id = 'C_PUBLIC'",
    )
    assert checkpoint is not None
    assert checkpoint["watermark_ts"] is None
    assert checkpoint["last_error"] == "write failed"
