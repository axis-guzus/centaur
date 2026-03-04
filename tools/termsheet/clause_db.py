"""Stage-aware clause defaults for termsheet generation."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .models import TermSheet

_STAGE_VALUES = {"early", "growth", "late"}


def _stage_bucket(ts: TermSheet) -> str:
    stage = ts.stage.strip().lower()
    if stage in _STAGE_VALUES:
        return stage
    series = ts.effective_series.upper()
    if series in {"SEED", "SERIES SEED", "A", "B", "SERIES A", "SERIES B"}:
        return "early"
    if series in {"C", "D", "E", "SERIES C", "SERIES D", "SERIES E"}:
        return "growth"
    return "late"


def _meaningful_owner(ts: TermSheet) -> bool:
    cfg = _clause_defaults().get("meaningful_owner", {})
    ownership_min = float(cfg.get("ownership_percent_min", 8.0))
    investment_min = float(cfg.get("investment_amount_min", 10_000_000))
    ownership = ts.ownership_percent
    if ownership is not None and ownership >= ownership_min:
        return True
    return ts.investment_amount >= investment_min


def _policy() -> dict[str, Any]:
    path = Path(__file__).resolve().parents[2] / "docs" / "legal_policy_v1.json"
    return json.loads(path.read_text())


def _clause_defaults() -> dict[str, Any]:
    return _policy().get("clause_defaults", {})


def build_clause_plan(ts: TermSheet) -> dict[str, Any]:
    stage = _stage_bucket(ts)
    meaningful_owner = _meaningful_owner(ts)
    lead = bool(ts.is_lead_investor)
    policy_defaults = _clause_defaults()

    protective_v_text = str(
        policy_defaults.get("base", {}).get(
            "protective_provision_v_text",
            "any interested or related party transactions other than transactions entered into in the ordinary course of business on an arm's-length basis and benefits made available to all employees",
        )
    )
    other_rights_text = None
    token_rights_text = None
    vesting_text = None
    rationale_parts = ["default_controls"]
    stage_profiles = policy_defaults.get("stage_profiles", {})

    if stage == "late" and (not lead or not meaningful_owner):
        late_profile = stage_profiles.get("late_minority", {})
        protective_v_text = str(
            late_profile.get("protective_provision_v_text", protective_v_text)
        )
        other_rights_text = late_profile.get("other_rights_text")
        rationale_parts.append("late_stage_minority_calibration")
    elif stage == "growth" and lead and meaningful_owner:
        growth_profile = stage_profiles.get("growth_lead", {})
        protective_v_text = str(
            growth_profile.get("protective_provision_v_text", protective_v_text)
        )
        rationale_parts.append("growth_stage_lead_controls")

    intent = ts.intent.value
    overlay = policy_defaults.get("intent_overlays", {}).get(intent, {})
    if overlay:
        if overlay.get("protective_provision_v_text"):
            protective_v_text = str(overlay.get("protective_provision_v_text"))
        if overlay.get("other_rights_text") and other_rights_text is None:
            other_rights_text = str(overlay.get("other_rights_text"))
        if overlay.get("token_rights_text"):
            token_rights_text = str(overlay.get("token_rights_text"))
        if overlay.get("vesting_text"):
            vesting_text = str(overlay.get("vesting_text"))
        rationale_parts.append(f"{intent}_style")

    return {
        "context": {
            "stage": stage,
            "intent": intent,
            "is_lead_investor": lead,
            "meaningful_owner": meaningful_owner,
        },
        "selected": {
            "protective_provision_v_text": protective_v_text,
            "other_rights_text": other_rights_text,
            "token_rights_text": token_rights_text,
            "vesting_text": vesting_text,
        },
        "rationale": ",".join(rationale_parts),
    }
