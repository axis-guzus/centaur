"""JSON file-based persistence for deals."""

import fcntl
import json
import os
import tempfile
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional
import uuid

from .models import Deal, DealStatus, TermSheet


def _get_store_path() -> Path:
    store_dir = Path(os.getenv("TERMSHEET_STORE_DIR", "/tmp/termsheet"))
    store_dir.mkdir(parents=True, exist_ok=True)
    return store_dir / "deals.json"


@contextmanager
def _store_lock():
    lock_path = _get_store_path().with_suffix(".lock")
    lock_path.touch(exist_ok=True)
    with lock_path.open("r+", encoding="utf-8") as lock_file:
        fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(lock_file.fileno(), fcntl.LOCK_UN)


def _load_deals_unlocked() -> dict[str, dict]:
    store_path = _get_store_path()
    if not store_path.exists():
        return {}
    try:
        with store_path.open(encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return {}


def _save_deals_unlocked(deals: dict[str, dict]) -> None:
    store_path = _get_store_path()
    with tempfile.NamedTemporaryFile(
        mode="w",
        encoding="utf-8",
        dir=store_path.parent,
        prefix=f"{store_path.name}.",
        suffix=".tmp",
        delete=False,
    ) as tmp_file:
        json.dump(deals, tmp_file, indent=2)
        tmp_file.flush()
        os.fsync(tmp_file.fileno())
        temp_path = Path(tmp_file.name)
    os.replace(temp_path, store_path)


def create_deal(
    company_name: str,
    term_sheet: TermSheet,
    requester_user_id: str,
    requester_user_name: str,
    slack_channel: str,
    slack_thread_ts: str,
) -> Deal:
    deal_id = f"TS-{uuid.uuid4().hex[:8].upper()}"
    now = datetime.now(timezone.utc).isoformat()

    deal = Deal(
        id=deal_id,
        company_name=company_name,
        status=DealStatus.DRAFT,
        term_sheet=term_sheet,
        requester_user_id=requester_user_id,
        requester_user_name=requester_user_name,
        slack_channel=slack_channel,
        slack_thread_ts=slack_thread_ts,
        created_at=now,
        updated_at=now,
    )

    with _store_lock():
        deals = _load_deals_unlocked()
        deals[deal_id] = deal.to_dict()
        _save_deals_unlocked(deals)

    return deal


def get_deal(deal_id: str) -> Optional[Deal]:
    with _store_lock():
        deals = _load_deals_unlocked()
    if deal_id not in deals:
        return None
    return Deal.from_dict(deals[deal_id])


def get_deal_by_company(company_name: str) -> Optional[Deal]:
    with _store_lock():
        deals = _load_deals_unlocked()
    company_lower = company_name.lower()
    for deal_data in deals.values():
        if deal_data["company_name"].lower() == company_lower:
            return Deal.from_dict(deal_data)
    return None


def get_deal_by_thread(slack_channel: str, slack_thread_ts: str) -> Optional[Deal]:
    with _store_lock():
        deals = _load_deals_unlocked()
    for deal_data in deals.values():
        if (
            deal_data["slack_channel"] == slack_channel
            and deal_data["slack_thread_ts"] == slack_thread_ts
        ):
            return Deal.from_dict(deal_data)
    return None


def list_deals(status: Optional[DealStatus] = None) -> list[Deal]:
    with _store_lock():
        deals = _load_deals_unlocked()
    result = []
    for deal_data in deals.values():
        if status is None or deal_data["status"] == status.value:
            result.append(Deal.from_dict(deal_data))
    return sorted(result, key=lambda d: d.updated_at, reverse=True)


def update_deal(
    deal_id: str,
    status: Optional[DealStatus] = None,
    term_sheet: Optional[TermSheet] = None,
    approved_by: Optional[str] = None,
    revision_note: Optional[str] = None,
) -> Optional[Deal]:
    with _store_lock():
        deals = _load_deals_unlocked()
        if deal_id not in deals:
            return None

        deal_data = deals[deal_id]
        now = datetime.now(timezone.utc).isoformat()

        if revision_note:
            if "revision_history" not in deal_data:
                deal_data["revision_history"] = []
            deal_data["revision_history"].append(
                {
                    "timestamp": now,
                    "note": revision_note,
                    "previous_status": deal_data["status"],
                }
            )

        if status:
            deal_data["status"] = status.value
            if status == DealStatus.APPROVED:
                deal_data["approved_at"] = now
                deal_data["approved_by"] = approved_by
            elif status == DealStatus.SENT:
                deal_data["sent_at"] = now

        if term_sheet:
            deal_data["term_sheet"] = term_sheet.to_dict()

        deal_data["updated_at"] = now
        deals[deal_id] = deal_data
        _save_deals_unlocked(deals)
        return Deal.from_dict(deal_data)


def delete_deal(deal_id: str) -> bool:
    with _store_lock():
        deals = _load_deals_unlocked()
        if deal_id not in deals:
            return False
        del deals[deal_id]
        _save_deals_unlocked(deals)
        return True
