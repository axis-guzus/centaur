"""Legal playbook checks for Paradigm workflows."""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class CheckRule:
    id: str
    label: str
    severity: str
    required_any: tuple[str, ...] = ()
    required_all: tuple[str, ...] = ()
    forbidden: tuple[str, ...] = ()
    document_types: tuple[str, ...] = ()
    requires_token_relevance: bool = False


def _load_policy() -> dict[str, Any]:
    policy_path = Path(__file__).resolve().parents[2] / "docs" / "legal_policy_v1.json"
    return json.loads(policy_path.read_text())


def _check_from_policy(raw: dict[str, Any]) -> CheckRule:
    return CheckRule(
        id=str(raw["id"]),
        label=str(raw["label"]),
        severity=str(raw.get("severity", "RED_LINE")),
        required_any=tuple(str(x).lower() for x in raw.get("required_any", [])),
        required_all=tuple(str(x).lower() for x in raw.get("required_all", [])),
        forbidden=tuple(str(x).lower() for x in raw.get("forbidden", [])),
        document_types=tuple(str(x).lower() for x in raw.get("document_types", [])),
        requires_token_relevance=bool(raw.get("requires_token_relevance", False)),
    )


_TOKEN_SIGNAL_RE = re.compile(r"\b(token|crypto|web3|blockchain|defi|dao|warrant)\b", re.IGNORECASE)
_WHITESPACE_RE = re.compile(r"\s+")


def _normalize_text(value: str) -> str:
    return _WHITESPACE_RE.sub(" ", value.lower()).strip()


def _contains_fragment(text: str, fragment: str) -> bool:
    normalized_fragment = _normalize_text(fragment)
    if not normalized_fragment:
        return False
    escaped = re.escape(normalized_fragment).replace(r"\ ", r"\s+")
    return bool(re.search(rf"(?:^|[^a-z0-9]){escaped}(?:$|[^a-z0-9])", text))


def _is_token_relevant(text: str, document_type: str) -> bool:
    if document_type == "token_warrant":
        return True
    return bool(_TOKEN_SIGNAL_RE.search(text))


class LegalPlaybookClient:
    """Expose Paradigm playbook checks and scoring for legal mode."""

    def __init__(self) -> None:
        self._policy = _load_policy()
        self._policy_path = Path(__file__).resolve().parents[2] / "docs" / "legal_policy_v1.json"
        self._playbook_path = Path(__file__).resolve().parent / "paradigm-playbook.md"
        self._checks = tuple(
            _check_from_policy(item) for item in self._policy.get("compliance_rules", [])
        )

    def _knowledge_path(self) -> Path:
        return self._policy_path.parent / "legal_knowledge_base.json"

    def _load_knowledge_base(self) -> dict[str, Any]:
        kb_path = self._knowledge_path()
        if not kb_path.exists():
            raise FileNotFoundError(f"knowledge base file not found: {kb_path}")
        return json.loads(kb_path.read_text())

    @staticmethod
    def _truncate_payload(payload: dict[str, Any], max_chars: int) -> dict[str, Any]:
        if max_chars <= 0:
            return payload
        serialized = json.dumps(payload, ensure_ascii=False)
        if len(serialized) <= max_chars:
            return payload
        return {
            "truncated": True,
            "max_chars": max_chars,
            "content_preview": serialized[:max_chars],
        }

    @staticmethod
    def _safe_format_template(template: str, values: dict[str, Any]) -> str:
        class _SafeDict(dict):
            def __missing__(self, key: str) -> str:
                return f"<{key}>"

        return template.format_map(_SafeDict(**values))

    def get_policy_version(self) -> dict[str, Any]:
        """Return version metadata for policy-as-data traceability."""
        playbook_bytes = self._playbook_path.read_bytes()
        policy_bytes = self._policy_path.read_bytes()
        return {
            "policy_version": self._policy.get("version", "unknown"),
            "policy_sha256": hashlib.sha256(policy_bytes).hexdigest(),
            "policy_path": str(self._policy_path),
            "playbook_sha256": hashlib.sha256(playbook_bytes).hexdigest(),
            "playbook_path": str(self._playbook_path),
            "check_count": len(self._checks),
            "red_line_count": len(self.get_red_lines()),
        }

    def get_red_lines(self) -> list[dict[str, str]]:
        """Return Paradigm's 16 red lines."""
        return [dict(item) for item in self._policy.get("red_lines", [])]

    def get_nice_to_haves(self) -> list[str]:
        """Return Paradigm's nice-to-have negotiation points."""
        return [str(item) for item in self._policy.get("nice_to_haves", [])]

    def get_standard_terms(self, document_type: str = "term_sheet") -> dict[str, Any]:
        """Return default terms for a document type."""
        doc_type = document_type.strip().lower()
        defaults = self._policy.get("standard_terms", {})
        if doc_type in defaults:
            return dict(defaults[doc_type])
        return {
            "document_type": doc_type,
            "message": "No explicit defaults configured; use playbook red lines + NVCA baseline.",
        }

    def get_diligence_checklist(self) -> list[dict[str, Any]]:
        """Return the diligence checklist from policy data."""
        checklist = self._policy.get("diligence_checklist", [])
        return [dict(item) for item in checklist if isinstance(item, dict)]

    def get_negotiation_priorities(self) -> list[dict[str, Any]]:
        """Return Ben-priority negotiation order used by legal mode."""
        return [dict(item) for item in self._policy.get("negotiation_priorities", [])]

    def get_financing_process(self) -> dict[str, Any]:
        """Return lifecycle steps from term-sheet to close/fund."""
        return dict(self._policy.get("financing_process", {}))

    def get_clause_defaults(self) -> dict[str, Any]:
        """Return git-committed clause defaults used by termsheet generation."""
        return dict(self._policy.get("clause_defaults", {}))

    def get_knowledge(
        self,
        topics: str = "",
        inject_level: str = "",
        max_chars: int = 0,
    ) -> dict[str, Any]:
        """Return domain knowledge sections filtered by comma-separated topic keys.

        Available topics: nvca, market_norms, stage_norms, ai_companies, crypto,
        law_firms, defined_terms, ma_exit, securities_law, delaware_dgcl, tax,
        corporate_ops, venture_ops, employment_ip, crypto_split, internal_canonical,
        internal_corpus_index.
        inject_level can be: system_evergreen or lookup_dynamic.
        Pass empty string or 'all' to get everything (large).
        """
        kb_path = self._knowledge_path()
        if not kb_path.exists():
            return {"error": "knowledge base file not found", "path": str(kb_path)}
        kb = self._load_knowledge_base()
        requested_set = {t.strip().lower() for t in topics.split(",") if t.strip()}
        requested = sorted(requested_set)
        classification = kb.get("knowledge_classification", {})
        level_filter = inject_level.strip().lower()

        if (not requested_set or "all" in requested_set) and not level_filter:
            return self._truncate_payload(kb, max_chars)

        result: dict[str, Any] = {}
        for key, value in kb.items():
            if not isinstance(value, dict):
                continue
            section_topic = value.get("topic", "")
            if requested_set and "all" not in requested_set and section_topic not in requested_set:
                continue
            if level_filter and str(classification.get(key, "")).lower() != level_filter:
                continue
            result[key] = value
        if not result:
            available_topics = sorted(
                {
                    str(value.get("topic", "")).strip()
                    for value in kb.values()
                    if isinstance(value, dict) and str(value.get("topic", "")).strip()
                }
            )
            return {
                "available_topics": available_topics,
                "requested": requested,
                "inject_level": level_filter or "all",
                "matched": 0,
            }
        payload = {
            "version": kb.get("version", "unknown"),
            "requested_topics": requested if requested else ["all"],
            "inject_level": level_filter or "all",
            "sections": result,
        }
        return self._truncate_payload(payload, max_chars)

    def get_knowledge_catalog(self) -> dict[str, Any]:
        """Return available topic sections, classifications, and pack definitions."""
        kb = self._load_knowledge_base()
        sections: dict[str, Any] = {}
        for key, value in kb.items():
            if not isinstance(value, dict):
                continue
            topic = value.get("topic")
            if not topic:
                continue
            sections[key] = {
                "topic": topic,
                "inject_level": kb.get("knowledge_classification", {}).get(key, "unknown"),
            }
        return {
            "version": kb.get("version", "unknown"),
            "sections": sections,
            "pack_index": kb.get("pack_index", {}),
        }

    def get_knowledge_pack(self, pack_id: str, max_chars: int = 7000) -> dict[str, Any]:
        """Return a deterministic knowledge pack by pack id."""
        kb = self._load_knowledge_base()
        packs = kb.get("pack_index", {})
        pack = packs.get(pack_id)
        if not isinstance(pack, dict):
            return {"error": "unknown_pack_id", "pack_id": pack_id, "available_packs": list(packs)}

        refs = [str(item) for item in pack.get("section_refs", [])]
        missing_section_refs = [ref for ref in refs if ref not in kb]
        sections = {ref: kb.get(ref) for ref in refs if ref in kb}
        payload = {
            "pack_id": pack_id,
            "metadata": pack,
            "sections": sections,
            "missing_section_refs": missing_section_refs,
        }
        return self._truncate_payload(payload, max_chars)

    def get_knowledge_plan(
        self,
        workflow: str = "draft",
        phase: str = "retrieval",
        deal_profile: dict[str, Any] | None = None,
        max_dynamic_packs: int = 2,
        max_dynamic_chars: int = 5000,
    ) -> dict[str, Any]:
        """Build deterministic evergreen+dynamic knowledge loading plan."""
        kb = self._load_knowledge_base()
        runtime = kb.get("knowledge_runtime", {})
        packs = kb.get("pack_index", {})
        profile = deal_profile or {}
        profile = {**profile, "workflow": workflow}

        fallback_pack_ids = [str(x) for x in runtime.get("fallback_pack_ids", ["pk_nvca_core"])]
        selected_pack_ids = list(fallback_pack_ids)
        for rule in runtime.get("deterministic_pack_rules", []):
            if not isinstance(rule, dict):
                continue
            cond = rule.get("if", {})
            if not isinstance(cond, dict):
                continue
            if all(profile.get(k) == v for k, v in cond.items()):
                selected_pack_ids.extend(str(x) for x in rule.get("add_pack_ids", []))

        unique_pack_ids: list[str] = []
        for pack_id in selected_pack_ids:
            if pack_id not in unique_pack_ids and pack_id in packs:
                unique_pack_ids.append(pack_id)

        ranked_pack_ids = sorted(
            unique_pack_ids,
            key=lambda pack_id: (
                int((packs.get(pack_id, {}) or {}).get("deterministic_rank", 10_000)),
                pack_id,
            ),
        )
        primary_pack_ids = ranked_pack_ids[: max(1, max_dynamic_packs)]
        contingency_pack_ids = ranked_pack_ids[max(1, max_dynamic_packs) :]

        templates = self._policy.get("workflow_matrix", {}).get("retrieval_query_templates", [])
        search_queries = [
            self._safe_format_template(str(template), profile)
            for template in templates
            if isinstance(template, str)
        ]
        source_precedence = self._policy.get("meta", {}).get("source_precedence", [])
        conflict_resolution = self._policy.get("workflow_matrix", {}).get("conflict_resolution", {})
        canonical_input_protocol = self._policy.get("meta", {}).get("canonical_input_protocol", {})
        canonical_inputs = self._policy.get("meta", {}).get("canonical_inputs", [])

        plan = {
            "workflow": workflow,
            "phase": phase,
            "deal_profile": profile,
            "system_evergreen_calls": runtime.get("system_evergreen_calls", []),
            "lookup_dynamic": {
                "primary_pack_ids": primary_pack_ids,
                "contingency_pack_ids": contingency_pack_ids,
                "max_dynamic_packs": max_dynamic_packs,
                "max_dynamic_chars": max_dynamic_chars,
            },
            "search_queries": search_queries,
            "source_precedence": source_precedence,
            "conflict_resolution": conflict_resolution,
            "canonical_input_protocol": canonical_input_protocol,
            "canonical_inputs": canonical_inputs,
            "knowledge_base_version": kb.get("version", "unknown"),
            "knowledge_runtime_version": runtime.get("version", "unknown"),
        }
        plan_hash = hashlib.sha256(
            json.dumps(plan, sort_keys=True, ensure_ascii=False).encode("utf-8")
        ).hexdigest()[:16]
        plan["plan_hash"] = plan_hash
        return plan

    def score_quality(
        self,
        *,
        total_claims: int,
        verified_claims: int,
        errors: int = 0,
        gaps: int = 0,
    ) -> dict[str, Any]:
        """Compute QA confidence score used by review-check flow."""
        safe_total = max(total_claims, 1)
        base = (verified_claims / safe_total) * 100.0
        score = max(0.0, base - (2 * errors) - (1 * gaps))
        return {
            "score": round(score, 2),
            "threshold": 85.0,
            "passes_threshold": score >= 85.0,
            "inputs": {
                "total_claims": total_claims,
                "verified_claims": verified_claims,
                "errors": errors,
                "gaps": gaps,
            },
        }

    def get_closing_checklist(self) -> dict[str, Any]:
        """Return the financing closing checklist (pre-closing, closing, post-closing)."""
        return dict(self._policy.get("closing_checklist", {}))

    def get_cross_document_checks(self) -> list[dict[str, Any]]:
        """Return cross-document consistency check pairs."""
        checks = self._policy.get("cross_document_consistency_checks", [])
        return [dict(item) for item in checks if isinstance(item, dict)]

    def get_deal_precedents(self) -> list[dict[str, Any]]:
        """Return Paradigm's named deal precedents with key provisions."""
        precedents = self._policy.get("deal_precedents", [])
        return [dict(item) for item in precedents if isinstance(item, dict)]

    def get_paradigm_checks(self) -> list[dict[str, str]]:
        """Return the 16 Paradigm-specific compliance checks for every review."""
        return [
            {"id": rule.id, "label": rule.label, "severity": rule.severity} for rule in self._checks
        ]

    def check_compliance(
        self, document_text: str, document_type: str = "term_sheet"
    ) -> dict[str, Any]:
        """Evaluate document text against Paradigm checks and red lines."""
        doc_type = _normalize_text(document_type) or "unknown"
        text = _normalize_text(document_text)
        token_relevant = _is_token_relevant(text, doc_type)
        calibration = self._policy.get("compliance_calibration", {})
        late_stage_relax_rule_id = str(calibration.get("late_stage_relax_rule_id", "blocking_rights"))
        late_stage_signals = tuple(
            str(item).lower() for item in calibration.get("late_stage_signals", [])
        )
        non_lead_signals = tuple(
            str(item).lower() for item in calibration.get("non_lead_signals", [])
        )
        checks: list[dict[str, Any]] = []
        for rule in self._checks:
            if rule.document_types and doc_type not in rule.document_types:
                checks.append(
                    {
                        "id": rule.id,
                        "label": rule.label,
                        "severity": rule.severity,
                        "status": "not_applicable",
                        "rationale": f"not_applicable: rule scoped to {list(rule.document_types)}",
                        "missing_required_all": [],
                        "missing_required_any": [],
                        "forbidden_terms_found": [],
                    }
                )
                continue

            if rule.requires_token_relevance and not token_relevant:
                checks.append(
                    {
                        "id": rule.id,
                        "label": rule.label,
                        "severity": rule.severity,
                        "status": "not_applicable",
                        "rationale": "not_applicable: token terms are not relevant for this document",
                        "missing_required_all": [],
                        "missing_required_any": [],
                        "forbidden_terms_found": [],
                    }
                )
                continue

            has_required_all = all(_contains_fragment(text, fragment) for fragment in rule.required_all)
            has_required_any = True
            if rule.required_any:
                has_required_any = any(_contains_fragment(text, fragment) for fragment in rule.required_any)
            has_forbidden = any(_contains_fragment(text, fragment) for fragment in rule.forbidden)
            if rule.id == "section_220":
                has_forbidden = has_forbidden or bool(
                    re.search(r"\bwaiv(?:e|er|ing)\b.{0,50}\b(section\s*220|220)\b", text)
                )
            conditional_relax = (
                rule.id == late_stage_relax_rule_id
                and not (has_required_all and has_required_any)
                and any(_contains_fragment(text, signal) for signal in late_stage_signals)
                and any(_contains_fragment(text, signal) for signal in non_lead_signals)
            )
            passed = ((has_required_all and has_required_any) and not has_forbidden) or conditional_relax
            rationale = (
                "pass: conditionally acceptable for non-lead late-stage minority position"
                if conditional_relax
                else ("pass" if passed else "fail")
            )
            checks.append(
                {
                    "id": rule.id,
                    "label": rule.label,
                    "severity": rule.severity,
                    "status": "pass" if passed else "fail",
                    "rationale": rationale,
                    "missing_required_all": [
                        fragment for fragment in rule.required_all if not _contains_fragment(text, fragment)
                    ],
                    "missing_required_any": [
                        fragment for fragment in rule.required_any if not _contains_fragment(text, fragment)
                    ],
                    "forbidden_terms_found": [
                        fragment for fragment in rule.forbidden if _contains_fragment(text, fragment)
                    ],
                }
            )

        evaluated_checks = [c for c in checks if c["status"] in {"pass", "fail"}]
        failed = [c for c in evaluated_checks if c["status"] == "fail"]
        not_applicable_count = len(checks) - len(evaluated_checks)
        score = self.score_quality(
            total_claims=len(evaluated_checks),
            verified_claims=len(evaluated_checks) - len(failed),
            errors=len(failed),
            gaps=not_applicable_count,
        )
        return {
            "document_type": doc_type,
            "failed_count": len(failed),
            "passed_count": len(evaluated_checks) - len(failed),
            "not_applicable_count": not_applicable_count,
            "checks": checks,
            "red_lines": self.get_red_lines(),
            "policy_version": self.get_policy_version(),
            "quality": score,
        }

    def read_playbook_markdown(self) -> str:
        """Return the canonical playbook markdown text."""
        return self._playbook_path.read_text()


def _client() -> LegalPlaybookClient:
    return LegalPlaybookClient()
