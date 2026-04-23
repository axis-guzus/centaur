"""Workflow: monitors SF conference rooms and alerts #sf-ops-team on double-bookings."""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass
from typing import Any

import httpx

from api.workflow_engine import WorkflowContext

WORKFLOW_NAME = "room_conflict_monitor"

ROOM_EMAILS = {
    "paradigm.xyz_188fm3e1sqa38h6alb7s452fnlu6q6gb74oj0c9o6co3ad9p6k@resource.calendar.google.com",
    "paradigm.xyz_188boiki4jtm2js3n7uq5mfr58k6q6gb74o34cpl70s32chi70@resource.calendar.google.com",
    "paradigm.xyz_188f57ur7em5cimjkten5t7idbboi6ga64sjgd9k6cq36c9p@resource.calendar.google.com",
    "paradigm.xyz_188234cm1s0e2iovm8o8dorookjbi6ga70s32dhn6cpjad1m@resource.calendar.google.com",
    "c_1885pkq3qntfegbci3c612ki3eh6e@resource.calendar.google.com",
    "c_1880lsqsr6ks8irlkssgnfar0if02@resource.calendar.google.com",
}


@dataclass
class Input:
    slack_channel: str = "sf-ops-team"
    check_interval_seconds: int = 60
    lookahead_days: int = 7
    max_iterations: int = 0  # 0 = run forever


def _parse_dt(value: str) -> dt.datetime:
    """Parse ISO datetime string, handling timezone offsets."""
    # Python 3.9 fromisoformat doesn't handle trailing Z
    value = value.replace("Z", "+00:00")
    return dt.datetime.fromisoformat(value)


def _events_overlap(a: dict, b: dict) -> bool:
    a_start = _parse_dt(a["start"])
    a_end = _parse_dt(a["end"])
    b_start = _parse_dt(b["start"])
    b_end = _parse_dt(b["end"])
    return a_start < b_end and a_end > b_start


async def _call_tool(client: httpx.AsyncClient, tool: str, method: str, params: dict) -> Any:
    r = await client.post(f"http://api:8000/tools/{tool}/{method}", json=params, timeout=30)
    r.raise_for_status()
    return r.json()


async def _fetch_room_bookings(lookahead_days: int) -> dict[str, dict[str, dict]]:
    """
    Fetch events from all accessible user calendars.
    Returns: {room_email -> {event_id -> event_data}}
    """
    now = dt.datetime.now(dt.timezone.utc)
    time_min = now.isoformat()
    time_max = (now + dt.timedelta(days=lookahead_days)).isoformat()

    room_events: dict[str, dict[str, dict]] = {r: {} for r in ROOM_EMAILS}

    async with httpx.AsyncClient() as client:
        calendars = await _call_tool(client, "gsuite", "calendar_list", {})

        for cal in calendars or []:
            cal_id = cal.get("id", "")
            if not cal_id:
                continue
            try:
                events = await _call_tool(client, "gsuite", "calendar_events", {
                    "calendar_id": cal_id,
                    "time_min": time_min,
                    "time_max": time_max,
                    "max_results": 100,
                })
            except Exception:
                continue

            for event in events or []:
                attendees = event.get("attendees") or []
                for att in attendees:
                    att_email = (att.get("email") or "").lower()
                    if att_email in ROOM_EMAILS:
                        event_id = event.get("id", "")
                        if not event_id:
                            continue
                        # Deduplicate: same event may appear on multiple calendars
                        if event_id not in room_events[att_email]:
                            organizer = event.get("organizer") or {}
                            room_events[att_email][event_id] = {
                                "id": event_id,
                                "summary": event.get("summary") or "(no title)",
                                "start": event.get("start") or "",
                                "end": event.get("end") or "",
                                "organizer_name": organizer.get("displayName") or organizer.get("email") or "Unknown",
                                "room_name": att.get("displayName") or att_email,
                            }

    return room_events


async def handler(inp: Input, ctx: WorkflowContext) -> dict[str, Any]:
    seen_conflict_keys: list[str] = []
    prev_event_ids: set[str] = set()
    iteration = 0

    while True:
        iteration += 1

        room_bookings: dict[str, dict[str, dict]] = await ctx.step(
            f"fetch_{iteration}",
            lambda: _fetch_room_bookings(inp.lookahead_days),
        )

        # All event IDs in this snapshot
        current_ids: set[str] = {
            eid
            for bookings in room_bookings.values()
            for eid in bookings
        }
        new_event_ids = current_ids - prev_event_ids

        for room_email, bookings in room_bookings.items():
            events = list(bookings.values())
            for i, a in enumerate(events):
                for b in events[i + 1:]:
                    if not a["start"] or not b["start"]:
                        continue
                    if not _events_overlap(a, b):
                        continue

                    id1, id2 = sorted([a["id"], b["id"]])
                    key = f"{room_email}::{id1}|{id2}"
                    if key in seen_conflict_keys:
                        continue

                    # Newer event is the one just added (if determinable)
                    if a["id"] in new_event_ids and b["id"] not in new_event_ids:
                        newer, older = a, b
                    elif b["id"] in new_event_ids and a["id"] not in new_event_ids:
                        newer, older = b, a
                    else:
                        newer, older = a, b  # both new or both old; order arbitrarily

                    room_name = newer.get("room_name") or older.get("room_name") or room_email
                    start_str = newer["start"]
                    end_str = newer["end"]
                    try:
                        start_dt = _parse_dt(start_str).astimezone(
                            dt.timezone(dt.timedelta(hours=-7))
                        )
                        end_dt = _parse_dt(end_str).astimezone(
                            dt.timezone(dt.timedelta(hours=-7))
                        )
                        time_label = (
                            f"{start_dt.strftime('%A, %b %-d')} "
                            f"{start_dt.strftime('%-I:%M %p')} – "
                            f"{end_dt.strftime('%-I:%M %p')} PT"
                        )
                    except Exception:
                        time_label = f"{start_str} – {end_str}"

                    msg = (
                        f"🚨 *Room Conflict Detected*\n"
                        f"*Room:* {room_name}\n"
                        f"*New booking by:* {newer['organizer_name']}\n"
                        f"*Event:* \"{newer['summary']}\"\n"
                        f"*Time:* {time_label}\n"
                        f"*Conflicts with:* \"{older['summary']}\" "
                        f"(organized by {older['organizer_name']})"
                    )

                    captured_key = key
                    captured_msg = msg

                    async def send_alert(m: str = captured_msg, k: str = captured_key) -> dict:
                        async with httpx.AsyncClient() as c:
                            await _call_tool(c, "slack", "send_message", {
                                "channel": inp.slack_channel,
                                "text": m,
                            })
                        return {"alerted": k}

                    await ctx.step(f"alert_{captured_key[:50]}", send_alert)
                    seen_conflict_keys.append(captured_key)

        prev_event_ids = current_ids

        if inp.max_iterations > 0 and iteration >= inp.max_iterations:
            return {"status": "done", "iterations": iteration}

        await ctx.sleep(
            f"wait_{iteration}",
            dt.timedelta(seconds=inp.check_interval_seconds),
        )
