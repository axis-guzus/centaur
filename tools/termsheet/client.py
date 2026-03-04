"""Termsheet tool client — document generation, deal tracking, and legal doc versioning."""

import hashlib
import json
import mimetypes
import re
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from .clause_db import build_clause_plan
from .doc_store import (
    create_document,
    create_version,
    get_current_version,
    get_version_history,
    update_status,
)
from .docx_pipeline import generate_term_sheet_package
from .models import BoardRights, Deal, DealStatus, InstrumentType, TermIntent, TermSheet


class TermsheetClient:
    _DEFAULT_SLACK_MAX_FILE_MB = 50

    @staticmethod
    def _sha256_path(path: Path) -> str:
        digest = hashlib.sha256()
        with path.open("rb") as file_handle:
            while True:
                chunk = file_handle.read(1024 * 1024)
                if not chunk:
                    break
                digest.update(chunk)
        return digest.hexdigest()

    @staticmethod
    def _coerce_term_sheet(term_sheet: TermSheet | dict) -> TermSheet:
        if isinstance(term_sheet, TermSheet):
            return term_sheet
        if isinstance(term_sheet, dict):
            return TermSheet.from_dict(term_sheet)
        raise TypeError("term_sheet must be a TermSheet or JSON object")

    @staticmethod
    def _safe_artifact_stem(company_name: str) -> str:
        stem = re.sub(r"[^A-Za-z0-9._-]+", "_", company_name).strip("._-")
        return stem or "TermSheet"

    @staticmethod
    def _artifact_path(output_dir: Path, filename: str) -> Path:
        path = (output_dir / filename).resolve()
        if output_dir not in path.parents and path != output_dir:
            raise ValueError("Artifact path escapes output directory")
        return path

    def create_term_sheet(self, **kwargs) -> TermSheet:
        """Create a term sheet and apply intent-aware defaults."""
        ts = TermSheet(**kwargs)
        supplied = set(kwargs)

        if "debt_threshold" not in supplied and ts.instrument_type == InstrumentType.PRICED:
            if ts.investment_amount >= 25_000_000:
                ts.debt_threshold = 5_000_000
            elif ts.investment_amount <= 8_000_000 and ts.intent == TermIntent.FOUNDER_FRIENDLY:
                ts.debt_threshold = 500_000
            else:
                ts.debt_threshold = 1_000_000

        if "ipo_threshold" not in supplied and ts.is_seed:
            ts.ipo_threshold = 50_000_000

        if ts.intent == TermIntent.FOUNDER_FRIENDLY:
            if "founder_carveout_percent" not in supplied:
                ts.founder_carveout_percent = 5.0
            if "board_rights" not in supplied:
                ts.board_rights = BoardRights.OBSERVER
        elif ts.intent == TermIntent.INVESTOR_PROTECTIVE:
            if "founder_carveout_percent" not in supplied:
                ts.founder_carveout_percent = 2.0
            if "board_rights" not in supplied:
                ts.board_rights = BoardRights.SEAT_AND_OBSERVER
        elif ts.intent == TermIntent.TOKEN_HEAVY:
            ts.token_rights.enabled = True
            if "token_rights" not in supplied:
                ts.token_rights.token_floor_percent = max(ts.token_rights.token_floor_percent, 50.0)

        clause_plan = build_clause_plan(ts)
        selected = clause_plan.get("selected", {})
        if "protective_provision_v_text" not in supplied:
            ts.protective_provision_v_text = selected.get("protective_provision_v_text")
        if "other_rights_text" not in supplied and selected.get("other_rights_text"):
            ts.other_rights_text = selected.get("other_rights_text")
        if ts.other_rights_text and "stock initially" not in ts.other_rights_text.lower():
            carveout_percent = f"{ts.founder_carveout_percent:g}"
            ts.other_rights_text = (
                f"{ts.other_rights_text.rstrip('.')} In each case, with exclusions for transfers to affiliates "
                f"and for estate planning or the transfer or sale of up to {carveout_percent}% "
                "of the stock initially subject to these provisions."
            )
        if "token_rights_text" not in supplied and selected.get("token_rights_text"):
            ts.token_rights_text = selected.get("token_rights_text")
        if "vesting_text" not in supplied and selected.get("vesting_text"):
            ts.vesting_text = selected.get("vesting_text")

        return ts

    def explain_clause_plan(self, term_sheet: TermSheet | dict) -> dict[str, Any]:
        """Return the selected stage-aware clause defaults and rationale."""
        ts = self._coerce_term_sheet(term_sheet)
        return build_clause_plan(ts)

    def generate_text(self, term_sheet: TermSheet | dict) -> str:
        """Generate a plain-text term sheet."""
        from .generator import generate_term_sheet_text

        return generate_term_sheet_text(self._coerce_term_sheet(term_sheet))

    def generate_docx(self, term_sheet: TermSheet | dict, template_file: str | None = None) -> bytes:
        """Generate a .docx term sheet from the Paradigm template."""
        ts = self._coerce_term_sheet(term_sheet)
        if ts.instrument_type != InstrumentType.PRICED:
            raise ValueError("DOCX generation currently supports priced rounds only")
        package = generate_term_sheet_package(
            ts,
            template_path=template_file,
            include_pdf=False,
        )
        return package.clean_docx

    def generate_document_package(
        self,
        term_sheet: TermSheet | dict,
        output_dir: str,
        previous_docx_file: str | None = None,
        include_pdf: bool = True,
        write_manifest: bool = True,
        slack_channel: str | None = None,
        slack_thread_ts: str | None = None,
        slack_max_file_mb: int = _DEFAULT_SLACK_MAX_FILE_MB,
    ) -> dict[str, Any]:
        """Generate clean/redline DOCX (+ optional PDF), validate fidelity, and write artifacts."""
        ts = self._coerce_term_sheet(term_sheet)
        if ts.instrument_type != InstrumentType.PRICED:
            raise ValueError("Document package generation currently supports priced rounds only")
        previous_docx: bytes | None = None
        if previous_docx_file:
            previous_docx = Path(previous_docx_file).read_bytes()

        package = generate_term_sheet_package(
            ts,
            previous_docx=previous_docx,
            include_pdf=include_pdf,
        )

        out = Path(output_dir).resolve()
        out.mkdir(parents=True, exist_ok=True)
        stem = self._safe_artifact_stem(ts.company_name)

        artifacts: dict[str, Any] = {}

        clean_path = self._artifact_path(out, f"{stem}_Term_Sheet_Clean.docx")
        clean_path.write_bytes(package.clean_docx)
        artifacts["clean_docx"] = str(clean_path)

        if package.redline_docx is not None:
            redline_path = self._artifact_path(out, f"{stem}_Term_Sheet_Redline.docx")
            redline_path.write_bytes(package.redline_docx)
            artifacts["redline_docx"] = str(redline_path)
        if package.clean_pdf is not None:
            pdf_path = self._artifact_path(out, f"{stem}_Term_Sheet_Clean.pdf")
            pdf_path.write_bytes(package.clean_pdf)
            artifacts["clean_pdf"] = str(pdf_path)
        if package.redline_pdf is not None:
            redline_pdf_path = self._artifact_path(out, f"{stem}_Term_Sheet_Redline.pdf")
            redline_pdf_path.write_bytes(package.redline_pdf)
            artifacts["redline_pdf"] = str(redline_pdf_path)

        if write_manifest:
            manifest = self._build_delivery_manifest(
                artifacts=artifacts,
                fidelity_report=package.fidelity_report,
                slack_channel=slack_channel,
                slack_thread_ts=slack_thread_ts,
                slack_max_file_mb=slack_max_file_mb,
            )
            manifest_path = self._artifact_path(out, f"{stem}_Term_Sheet_Delivery_Manifest.json")
            manifest_path.write_text(json.dumps(manifest, indent=2))
            artifacts["delivery_manifest_json"] = str(manifest_path)
            artifacts["delivery_ready"] = bool(manifest.get("delivery_ready"))
            artifacts["fidelity_passed"] = bool(manifest.get("fidelity", {}).get("passed"))

        return artifacts

    @staticmethod
    def _slack_file_preflight(path: Path, max_file_mb: int) -> dict[str, Any]:
        exists = path.exists()
        size_bytes = path.stat().st_size if exists else 0
        extension = path.suffix.lower()
        mime_type = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
        sha256 = ""
        if exists:
            sha256 = TermsheetClient._sha256_path(path)
        allowed_extensions = {".docx", ".pdf"}
        max_bytes = max_file_mb * 1024 * 1024
        sendable = (
            exists
            and size_bytes > 0
            and extension in allowed_extensions
            and size_bytes <= max_bytes
        )
        return {
            "path": str(path),
            "filename": path.name,
            "extension": extension,
            "mime_type": mime_type,
            "size_bytes": size_bytes,
            "sha256": sha256,
            "max_allowed_bytes": max_bytes,
            "sendable_to_slack": sendable,
        }

    def _build_delivery_manifest(
        self,
        *,
        artifacts: dict[str, Any],
        fidelity_report: dict[str, Any],
        slack_channel: str | None,
        slack_thread_ts: str | None,
        slack_max_file_mb: int,
    ) -> dict[str, Any]:
        file_keys = ("clean_docx", "redline_docx", "clean_pdf", "redline_pdf")
        files = [
            self._slack_file_preflight(Path(artifacts[key]), slack_max_file_mb)
            for key in file_keys
            if isinstance(artifacts.get(key), str)
        ]
        all_sendable = all(item["sendable_to_slack"] for item in files) if files else False
        return {
            "generated_at": datetime.now(UTC).isoformat(),
            "fidelity": fidelity_report,
            "slack_delivery": {
                "channel": slack_channel,
                "thread_ts": slack_thread_ts,
                "max_file_mb": slack_max_file_mb,
                "files": files,
                "all_sendable": all_sendable,
            },
            "delivery_ready": bool(fidelity_report.get("passed")) and all_sendable,
        }

    def generate_email(self, term_sheet: TermSheet, dri_name: str | None = None) -> str:
        """Generate a draft email for a term sheet."""
        from .generator import generate_draft_email

        return generate_draft_email(term_sheet, dri_name=dri_name or "")

    def create_deal(
        self,
        company_name: str,
        term_sheet: TermSheet,
        requester_user_id: str,
        requester_user_name: str = "",
        slack_channel: str = "",
        slack_thread_ts: str = "",
    ) -> Deal:
        """Create and persist a new deal.

        Args:
            company_name: Company name for the deal.
            term_sheet: The term sheet data.
            requester_user_id: Slack user ID of the requester.
            requester_user_name: Slack username of the requester.
            slack_channel: Slack channel ID.
            slack_thread_ts: Slack thread timestamp.
        """
        from .store import create_deal

        return create_deal(
            company_name=company_name,
            term_sheet=term_sheet,
            requester_user_id=requester_user_id,
            requester_user_name=requester_user_name,
            slack_channel=slack_channel,
            slack_thread_ts=slack_thread_ts,
        )

    def list_deals(self, status: DealStatus | None = None) -> list[Deal]:
        from .store import list_deals

        return list_deals(status)

    def get_deal(self, identifier: str) -> Deal | None:
        from .store import get_deal, get_deal_by_company

        return get_deal(identifier) or get_deal_by_company(identifier)

    def get_deal_by_thread(self, channel: str, thread_ts: str) -> Deal | None:
        from .store import get_deal_by_thread

        return get_deal_by_thread(channel, thread_ts)

    def update_deal(
        self,
        deal_id: str,
        status: DealStatus | None = None,
        term_sheet: TermSheet | None = None,
        approved_by: str | None = None,
        revision_note: str | None = None,
    ) -> Deal | None:
        from .store import update_deal

        return update_deal(
            deal_id=deal_id,
            status=status,
            term_sheet=term_sheet,
            approved_by=approved_by,
            revision_note=revision_note,
        )

    def approve_deal(self, deal_id: str, approved_by: str) -> Deal | None:
        return self.update_deal(
            deal_id=deal_id,
            status=DealStatus.APPROVED,
            approved_by=approved_by,
            revision_note=f"Approved by {approved_by}",
        )

    def submit_for_approval(self, deal_id: str) -> Deal | None:
        return self.update_deal(
            deal_id=deal_id,
            status=DealStatus.PENDING_APPROVAL,
            revision_note="Submitted for approval",
        )

    def mark_sent(self, deal_id: str) -> Deal | None:
        return self.update_deal(
            deal_id=deal_id,
            status=DealStatus.SENT,
            revision_note="Marked as sent",
        )

    def delete_deal(self, deal_id: str) -> bool:
        from .store import delete_deal

        return delete_deal(deal_id)

    def create_legal_document(
        self,
        *,
        document_type: str,
        title: str,
        company_name: str = "",
        deal_id: str | None = None,
        slack_thread_key: str | None = None,
        requester_id: str | None = None,
        playbook_id: str | None = None,
        terms: dict | None = None,
        metadata: dict | None = None,
    ) -> dict:
        return create_document(
            document_type=document_type,
            title=title,
            company_name=company_name or None,
            deal_id=deal_id,
            slack_thread_key=slack_thread_key,
            requester_id=requester_id,
            playbook_id=playbook_id,
            terms=terms or {},
            metadata=metadata or {},
        )

    def create_legal_version(
        self,
        *,
        document_id: str,
        terms: dict,
        content_text: str,
        source_file_url: str | None = None,
        source_file_hash: str | None = None,
        diff_summary: str | None = None,
        diff_details: dict | list[dict] | None = None,
        compliance_report: dict | None = None,
        requested_by: str | None = None,
        request_text: str | None = None,
    ) -> dict:
        return create_version(
            document_id=document_id,
            terms=terms,
            content_text=content_text,
            source_file_url=source_file_url,
            source_file_hash=source_file_hash,
            diff_summary=diff_summary,
            diff_details=diff_details,
            compliance_report=compliance_report,
            requested_by=requested_by,
            request_text=request_text,
        )

    def get_current_legal_version(self, document_id: str) -> dict | None:
        return get_current_version(document_id)

    def get_legal_version_history(self, document_id: str) -> list[dict]:
        return get_version_history(document_id)

    def update_legal_document_status(
        self,
        *,
        document_id: str,
        status: str,
        actor_id: str | None = None,
        details: dict | None = None,
    ) -> dict | None:
        return update_status(
            document_id=document_id,
            status=status,
            actor_id=actor_id,
            details=details,
        )


def _client() -> TermsheetClient:
    return TermsheetClient()
