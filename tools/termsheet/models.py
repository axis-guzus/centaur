"""Data models for term sheet generation and deal tracking."""

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any


class DealStatus(StrEnum):
    DRAFT = "draft"
    PENDING_APPROVAL = "pending_approval"
    APPROVED = "approved"
    SENT = "sent"


class InstrumentType(StrEnum):
    PRICED = "priced"
    SAFE = "safe"
    CONVERTIBLE_NOTE = "convertible_note"


class BoardRights(StrEnum):
    SEAT_AND_OBSERVER = "seat_and_observer"
    SEAT = "seat"
    OBSERVER = "observer"
    NONE = "none"


class TermIntent(StrEnum):
    BALANCED = "balanced"
    FOUNDER_FRIENDLY = "founder_friendly"
    INVESTOR_PROTECTIVE = "investor_protective"
    TOKEN_HEAVY = "token_heavy"


@dataclass
class TokenRights:
    enabled: bool = False
    token_floor_percent: float = 50.0

    def __post_init__(self) -> None:
        if not 0 <= self.token_floor_percent <= 100:
            raise ValueError("token_floor_percent must be between 0 and 100")

    def to_dict(self) -> dict[str, Any]:
        return {
            "enabled": self.enabled,
            "token_floor_percent": self.token_floor_percent,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "TokenRights":
        return cls(
            enabled=data.get("enabled", False),
            token_floor_percent=data.get("token_floor_percent", 50.0),
        )


@dataclass
class TermSheet:
    company_name: str
    investment_amount: float
    instrument_type: InstrumentType

    post_money_valuation: float | None = None
    pre_money_valuation: float | None = None
    valuation_cap: float | None = None
    discount_percent: float | None = None

    series: str | None = None
    option_pool_percent: float = 10.0

    board_rights: BoardRights = BoardRights.OBSERVER
    debt_threshold: float = 1_000_000
    ipo_threshold: float = 100_000_000

    pro_rata_rights: bool = True
    founder_carveout_percent: float = 2.0
    co_investor_language: bool = True
    intent: TermIntent = TermIntent.BALANCED

    liquidation_preference: str = "1x non-participating"
    anti_dilution: str = "broad-based weighted average"

    token_rights: TokenRights = field(default_factory=TokenRights)

    legal_fee_cap: float = 75_000
    nvca_year: int = 2025
    exclusivity_days: int = 45
    governing_law: str = "Delaware"

    custom_terms: str = ""
    founder_name: str = ""
    stage: str = "early"
    is_lead_investor: bool = True
    ownership_percent_override: float | None = None
    co_investor_text: str | None = None
    other_rights_text: str | None = None
    token_rights_text: str | None = None
    vesting_text: str | None = None
    protective_provision_v_text: str | None = None

    def __post_init__(self) -> None:
        if not self.company_name.strip():
            raise ValueError("company_name is required")
        if self.investment_amount <= 0:
            raise ValueError("investment_amount must be greater than 0")

        if self.instrument_type == InstrumentType.PRICED and (
            self.post_money_valuation is None and self.pre_money_valuation is None
        ):
            raise ValueError("priced rounds require pre_money_valuation or post_money_valuation")

        if self.post_money_valuation is not None and self.post_money_valuation <= 0:
            raise ValueError("post_money_valuation must be greater than 0")
        if self.pre_money_valuation is not None and self.pre_money_valuation <= 0:
            raise ValueError("pre_money_valuation must be greater than 0")
        if self.valuation_cap is not None and self.valuation_cap <= 0:
            raise ValueError("valuation_cap must be greater than 0")
        if self.discount_percent is not None and not 0 <= self.discount_percent <= 100:
            raise ValueError("discount_percent must be between 0 and 100")

        for label, value in (
            ("option_pool_percent", self.option_pool_percent),
            ("founder_carveout_percent", self.founder_carveout_percent),
        ):
            if not 0 <= value <= 100:
                raise ValueError(f"{label} must be between 0 and 100")

        if self.debt_threshold <= 0:
            raise ValueError("debt_threshold must be greater than 0")
        if self.ipo_threshold <= 0:
            raise ValueError("ipo_threshold must be greater than 0")
        if self.legal_fee_cap < 0:
            raise ValueError("legal_fee_cap must be greater than or equal to 0")
        if self.exclusivity_days <= 0:
            raise ValueError("exclusivity_days must be greater than 0")
        if self.stage.strip().lower() not in {"early", "growth", "late"}:
            raise ValueError("stage must be one of: early, growth, late")
        if self.ownership_percent_override is not None and not (
            0 <= self.ownership_percent_override <= 100
        ):
            raise ValueError("ownership_percent_override must be between 0 and 100")

    @property
    def ownership_percent(self) -> float | None:
        if self.ownership_percent_override is not None:
            return self.ownership_percent_override
        if self.post_money_valuation and self.post_money_valuation > 0:
            return self.investment_amount / self.post_money_valuation * 100
        if self.pre_money_valuation and self.pre_money_valuation > 0:
            post = self.pre_money_valuation + self.investment_amount
            return self.investment_amount / post * 100
        return None

    @property
    def effective_series(self) -> str:
        return (self.series or "A").strip()

    @property
    def effective_valuation(self) -> float:
        return self.post_money_valuation or self.pre_money_valuation or self.valuation_cap or 0.0

    @property
    def is_seed(self) -> bool:
        return self.effective_series.upper() in {"SEED", "SERIES SEED"}

    @property
    def no_shop_days(self) -> int:
        return self.exclusivity_days

    @no_shop_days.setter
    def no_shop_days(self, value: int) -> None:
        self.exclusivity_days = value

    def to_dict(self) -> dict[str, Any]:
        return {
            "company_name": self.company_name,
            "investment_amount": self.investment_amount,
            "instrument_type": self.instrument_type.value,
            "post_money_valuation": self.post_money_valuation,
            "pre_money_valuation": self.pre_money_valuation,
            "valuation_cap": self.valuation_cap,
            "discount_percent": self.discount_percent,
            "series": self.series,
            "option_pool_percent": self.option_pool_percent,
            "board_rights": self.board_rights.value,
            "debt_threshold": self.debt_threshold,
            "ipo_threshold": self.ipo_threshold,
            "pro_rata_rights": self.pro_rata_rights,
            "founder_carveout_percent": self.founder_carveout_percent,
            "co_investor_language": self.co_investor_language,
            "intent": self.intent.value,
            "liquidation_preference": self.liquidation_preference,
            "anti_dilution": self.anti_dilution,
            "token_rights": self.token_rights.to_dict(),
            "legal_fee_cap": self.legal_fee_cap,
            "nvca_year": self.nvca_year,
            "exclusivity_days": self.exclusivity_days,
            "no_shop_days": self.exclusivity_days,
            "governing_law": self.governing_law,
            "custom_terms": self.custom_terms,
            "founder_name": self.founder_name,
            "stage": self.stage,
            "is_lead_investor": self.is_lead_investor,
            "ownership_percent_override": self.ownership_percent_override,
            "co_investor_text": self.co_investor_text,
            "other_rights_text": self.other_rights_text,
            "token_rights_text": self.token_rights_text,
            "vesting_text": self.vesting_text,
            "protective_provision_v_text": self.protective_provision_v_text,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "TermSheet":
        token_data = data.get("token_rights", {})
        token_rights = (
            TokenRights.from_dict(token_data) if isinstance(token_data, dict) else TokenRights()
        )
        return cls(
            company_name=data["company_name"],
            investment_amount=data["investment_amount"],
            instrument_type=InstrumentType(data.get("instrument_type", "priced")),
            post_money_valuation=data.get("post_money_valuation"),
            pre_money_valuation=data.get("pre_money_valuation"),
            valuation_cap=data.get("valuation_cap"),
            discount_percent=data.get("discount_percent"),
            series=data.get("series"),
            option_pool_percent=data.get("option_pool_percent", 10.0),
            board_rights=BoardRights(data.get("board_rights", "observer")),
            debt_threshold=data.get("debt_threshold", 1_000_000),
            ipo_threshold=data.get("ipo_threshold", 100_000_000),
            pro_rata_rights=data.get("pro_rata_rights", True),
            founder_carveout_percent=data.get("founder_carveout_percent", 2.0),
            co_investor_language=data.get("co_investor_language", True),
            intent=TermIntent(data.get("intent", "balanced")),
            liquidation_preference=data.get("liquidation_preference", "1x non-participating"),
            anti_dilution=data.get("anti_dilution", "broad-based weighted average"),
            token_rights=token_rights,
            legal_fee_cap=data.get("legal_fee_cap", 75_000),
            nvca_year=data.get("nvca_year", 2025),
            exclusivity_days=data.get("exclusivity_days", data.get("no_shop_days", 45)),
            governing_law=data.get("governing_law", "Delaware"),
            custom_terms=data.get("custom_terms", ""),
            founder_name=data.get("founder_name", ""),
            stage=data.get("stage", "early"),
            is_lead_investor=data.get("is_lead_investor", True),
            ownership_percent_override=data.get("ownership_percent_override"),
            co_investor_text=data.get("co_investor_text"),
            other_rights_text=data.get("other_rights_text"),
            token_rights_text=data.get("token_rights_text"),
            vesting_text=data.get("vesting_text"),
            protective_provision_v_text=data.get("protective_provision_v_text"),
        )


@dataclass
class Deal:
    id: str
    company_name: str
    status: DealStatus
    term_sheet: TermSheet
    requester_user_id: str
    requester_user_name: str
    slack_channel: str
    slack_thread_ts: str
    created_at: str
    updated_at: str
    approved_at: str | None = None
    approved_by: str | None = None
    sent_at: str | None = None
    revision_history: list[dict] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "company_name": self.company_name,
            "status": self.status.value,
            "term_sheet": self.term_sheet.to_dict(),
            "requester_user_id": self.requester_user_id,
            "requester_user_name": self.requester_user_name,
            "slack_channel": self.slack_channel,
            "slack_thread_ts": self.slack_thread_ts,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "approved_at": self.approved_at,
            "approved_by": self.approved_by,
            "sent_at": self.sent_at,
            "revision_history": self.revision_history,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Deal":
        return cls(
            id=data["id"],
            company_name=data["company_name"],
            status=DealStatus(data["status"]),
            term_sheet=TermSheet.from_dict(data["term_sheet"]),
            requester_user_id=data["requester_user_id"],
            requester_user_name=data["requester_user_name"],
            slack_channel=data["slack_channel"],
            slack_thread_ts=data["slack_thread_ts"],
            created_at=data["created_at"],
            updated_at=data["updated_at"],
            approved_at=data.get("approved_at"),
            approved_by=data.get("approved_by"),
            sent_at=data.get("sent_at"),
            revision_history=data.get("revision_history", []),
        )
