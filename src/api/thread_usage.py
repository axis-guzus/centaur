from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Literal, TypedDict

UsageQuality = Literal["authoritative", "estimated"]
UsageBreakdown = Literal["known", "unknown"]


class ThreadTokenUsage(TypedDict):
    total_tokens: int
    input_tokens: int | None
    output_tokens: int | None
    cost_usd: float | None
    quality: UsageQuality
    breakdown: UsageBreakdown
    models: list[str]


@dataclass(frozen=True)
class ModelPricing:
    input_cost_per_million: float
    output_cost_per_million: float


@dataclass(frozen=True)
class EventTokenUsage:
    total_tokens: int
    input_tokens: int | None
    output_tokens: int | None
    cost_usd: float | None
    model: str | None
    estimated: bool
    breakdown_known: bool
    can_estimate_cost: bool


@dataclass
class _TurnTokenUsage:
    total_tokens: int = 0
    known_input_tokens: int = 0
    known_output_tokens: int = 0
    cost_usd: float = 0.0
    authoritative: bool = False
    estimated: bool = False
    has_usage: bool = False
    cost_complete: bool = True
    breakdown_known: bool = True
    models: set[str] = field(default_factory=set)

    def apply(self, usage: EventTokenUsage, *, authoritative: bool) -> None:
        if authoritative:
            self.total_tokens = 0
            self.known_input_tokens = 0
            self.known_output_tokens = 0
            self.cost_usd = 0.0
            self.authoritative = True
            self.estimated = False
            self.has_usage = False
            self.cost_complete = True
            self.breakdown_known = True
            self.models.clear()
        elif self.authoritative:
            return

        self.total_tokens += usage.total_tokens
        self.estimated = self.estimated or usage.estimated
        self.has_usage = True

        if usage.breakdown_known and usage.input_tokens is not None and usage.output_tokens is not None:
            self.known_input_tokens += usage.input_tokens
            self.known_output_tokens += usage.output_tokens
        else:
            self.breakdown_known = False

        if usage.model:
            self.models.add(usage.model)

        if usage.cost_usd is None and usage.total_tokens > 0:
            self.cost_complete = False
        elif self.cost_complete:
            self.cost_usd += usage.cost_usd


_MODEL_SNAPSHOT_SUFFIX_RE = re.compile(r"-(?:20\d{2}-\d{2}-\d{2}|20\d{6})$")
_MODEL_PRICING_RULES: tuple[tuple[tuple[str, ...], ModelPricing], ...] = (
    (("gpt-5.4",), ModelPricing(2.5, 15.0)),
    (
        (
            "gpt-5.3-codex",
            "gpt-5.2-codex",
            "gpt-5.3-chat-latest",
            "gpt-5.2-chat-latest",
            "gpt-5.3",
            "gpt-5.2",
        ),
        ModelPricing(1.75, 14.0),
    ),
    (("gpt-5.1-codex-mini",), ModelPricing(0.25, 2.0)),
    (
        (
            "gpt-5-codex",
            "gpt-5.1-codex",
            "gpt-5.1-codex-max",
            "gpt-5-chat-latest",
            "gpt-5.1-chat-latest",
            "gpt-5",
            "gpt-5.1",
        ),
        ModelPricing(1.25, 10.0),
    ),
    (
        ("claude-opus-4-6", "claude-opus-4-5", "opus-4-6", "opus-4-5"),
        ModelPricing(5.0, 25.0),
    ),
    (
        (
            "claude-opus-4-1",
            "claude-opus-4-0",
            "claude-opus-4",
            "opus-4-1",
            "opus-4-0",
            "opus-4",
        ),
        ModelPricing(15.0, 75.0),
    ),
    (("claude-3-opus",), ModelPricing(15.0, 75.0)),
    (
        (
            "claude-sonnet-4-6",
            "claude-sonnet-4-5",
            "claude-sonnet-4",
            "sonnet-4-6",
            "sonnet-4-5",
            "sonnet-4",
        ),
        ModelPricing(3.0, 15.0),
    ),
    (("claude-haiku-4-5", "haiku-4-5"), ModelPricing(1.0, 5.0)),
    (("claude-haiku-3-5", "haiku-3-5", "3-5-haiku"), ModelPricing(0.8, 4.0)),
    (("claude-haiku-3", "haiku-3", "3-haiku"), ModelPricing(0.25, 1.25)),
)


def _coerce_non_negative_int(value: Any) -> int:
    if isinstance(value, bool):
        return 0
    if isinstance(value, (int, float)) and value >= 0:
        return int(value)
    return 0


def normalize_model_name(model: str | None) -> str | None:
    if not model:
        return None
    normalized = str(model).strip().lower()
    if not normalized:
        return None
    normalized = normalized.rsplit("/", 1)[-1]
    normalized = _MODEL_SNAPSHOT_SUFFIX_RE.sub("", normalized)
    return normalized or None


def resolve_model_pricing(model: str | None) -> ModelPricing | None:
    normalized = normalize_model_name(model)
    if not normalized:
        return None
    for aliases, pricing in _MODEL_PRICING_RULES:
        if normalized in aliases:
            return pricing
    return None


def estimate_usage_cost_usd(model: str | None, input_tokens: int, output_tokens: int) -> float | None:
    if input_tokens == 0 and output_tokens == 0:
        return None
    pricing = resolve_model_pricing(model)
    if not pricing:
        return None
    input_cost = (input_tokens / 1_000_000) * pricing.input_cost_per_million
    output_cost = (output_tokens / 1_000_000) * pricing.output_cost_per_million
    return round(input_cost + output_cost, 6)


def _extract_explicit_cost_usd(payload: dict[str, Any]) -> float | None:
    direct_keys = ("cost_usd", "total_cost_usd", "costUSD")
    for key in direct_keys:
        value = payload.get(key)
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            return round(float(value), 6)

    model_usage = payload.get("modelUsage")
    if isinstance(model_usage, dict):
        total_cost = 0.0
        found_cost = False
        for entry in model_usage.values():
            if not isinstance(entry, dict):
                continue
            value = entry.get("costUSD")
            if isinstance(value, (int, float)) and not isinstance(value, bool):
                total_cost += float(value)
                found_cost = True
        if found_cost:
            return round(total_cost, 6)

    return None


def extract_usage_from_payload(payload: dict[str, Any]) -> EventTokenUsage | None:
    explicit_input_tokens = _coerce_non_negative_int(payload.get("input_tokens"))
    prompt_input_tokens = _coerce_non_negative_int(payload.get("prompt_tokens"))
    base_input_tokens = explicit_input_tokens if explicit_input_tokens > 0 else prompt_input_tokens
    cached_input_tokens = (
        _coerce_non_negative_int(payload.get("cached_input_tokens"))
        + _coerce_non_negative_int(payload.get("cache_read_input_tokens"))
        + _coerce_non_negative_int(payload.get("cache_creation_input_tokens"))
    )
    explicit_output_tokens = _coerce_non_negative_int(payload.get("output_tokens"))
    completion_output_tokens = _coerce_non_negative_int(payload.get("completion_tokens"))
    output_tokens = (
        explicit_output_tokens if explicit_output_tokens > 0 else completion_output_tokens
    )
    input_tokens = base_input_tokens + cached_input_tokens
    explicit_cost_usd = _extract_explicit_cost_usd(payload)

    if input_tokens > 0 or output_tokens > 0:
        total_tokens = input_tokens + output_tokens
        return EventTokenUsage(
            total_tokens=total_tokens,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            cost_usd=explicit_cost_usd,
            model=None,
            estimated=False,
            breakdown_known=True,
            can_estimate_cost=cached_input_tokens == 0 and explicit_cost_usd is None,
        )

    total_tokens = _coerce_non_negative_int(payload.get("total_tokens"))
    if total_tokens <= 0:
        return None

    return EventTokenUsage(
        total_tokens=total_tokens,
        input_tokens=None,
        output_tokens=None,
        cost_usd=explicit_cost_usd,
        model=None,
        estimated=True,
        breakdown_known=False,
        can_estimate_cost=False,
    )


def extract_event_token_usage(event: dict[str, Any]) -> tuple[EventTokenUsage | None, bool]:
    event_type = str(event.get("type") or "")
    if event_type == "subagent":
        return None, False

    message = event.get("message")
    usage_payload: dict[str, Any] | None = None
    if isinstance(message, dict) and isinstance(message.get("usage"), dict):
        usage_payload = message.get("usage")
    elif isinstance(event.get("usage"), dict):
        usage_payload = event.get("usage")
    if not isinstance(usage_payload, dict):
        return None, False

    usage = extract_usage_from_payload(usage_payload)
    if usage is None:
        return None, False

    raw_model = None
    if isinstance(message, dict):
        raw_model = message.get("model")
    if raw_model is None:
        raw_model = event.get("model")
    model = normalize_model_name(str(raw_model or "").strip() or None)
    cost_usd = None
    if usage.cost_usd is not None:
        cost_usd = usage.cost_usd
    elif (
        usage.can_estimate_cost
        and usage.breakdown_known
        and usage.input_tokens is not None
        and usage.output_tokens is not None
    ):
        cost_usd = estimate_usage_cost_usd(model, usage.input_tokens, usage.output_tokens)

    authoritative = bool(event.get("authoritative")) or event_type == "turn.completed"
    return (
        EventTokenUsage(
            total_tokens=usage.total_tokens,
            input_tokens=usage.input_tokens,
            output_tokens=usage.output_tokens,
            cost_usd=cost_usd,
            model=model,
            estimated=usage.estimated,
            breakdown_known=usage.breakdown_known,
            can_estimate_cost=usage.can_estimate_cost,
        ),
        authoritative,
    )


def count_usage_events(events: list[dict[str, Any]]) -> int:
    count = 0
    for event in events:
        if not isinstance(event, dict):
            continue
        usage, _ = extract_event_token_usage(event)
        if usage is not None:
            count += 1
    return count


class ThreadTokenUsageAccumulator:
    def __init__(self) -> None:
        self._turns: dict[int, _TurnTokenUsage] = {}

    def apply_event(self, turn_id: int, event: dict[str, Any]) -> bool:
        usage, authoritative = extract_event_token_usage(event)
        if usage is None:
            return False
        turn_usage = self._turns.setdefault(turn_id, _TurnTokenUsage())
        turn_usage.apply(usage, authoritative=authoritative)
        return True

    def extend_turn(self, turn_id: int, events: list[dict[str, Any]]) -> None:
        for event in events:
            if isinstance(event, dict):
                self.apply_event(turn_id, event)

    def snapshot(self) -> ThreadTokenUsage | None:
        turn_usages = [
            usage for usage in self._turns.values() if usage.has_usage and usage.total_tokens > 0
        ]
        if not turn_usages:
            return None

        total_tokens = sum(usage.total_tokens for usage in turn_usages)
        quality: UsageQuality = (
            "authoritative"
            if all(usage.authoritative and not usage.estimated for usage in turn_usages)
            else "estimated"
        )
        breakdown: UsageBreakdown = (
            "known" if all(usage.breakdown_known for usage in turn_usages) else "unknown"
        )
        models = sorted({model for usage in turn_usages for model in usage.models})

        cost_usd: float | None
        if all(usage.cost_complete for usage in turn_usages):
            cost_usd = round(sum(usage.cost_usd for usage in turn_usages), 6)
        else:
            cost_usd = None

        input_tokens: int | None
        output_tokens: int | None
        if breakdown == "known":
            input_tokens = sum(usage.known_input_tokens for usage in turn_usages)
            output_tokens = sum(usage.known_output_tokens for usage in turn_usages)
        else:
            input_tokens = None
            output_tokens = None

        return {
            "total_tokens": total_tokens,
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "cost_usd": cost_usd,
            "quality": quality,
            "breakdown": breakdown,
            "models": models,
        }


def summarize_turn_token_usage(events: list[dict[str, Any]]) -> ThreadTokenUsage | None:
    accumulator = ThreadTokenUsageAccumulator()
    accumulator.extend_turn(1, events)
    return accumulator.snapshot()


def summarize_thread_token_usage(turns: list[dict[str, Any]]) -> ThreadTokenUsage | None:
    accumulator = ThreadTokenUsageAccumulator()
    for turn in turns:
        turn_id = _coerce_non_negative_int(turn.get("turn_id"))
        if turn_id <= 0:
            continue
        events_raw = turn.get("events")
        events = events_raw if isinstance(events_raw, list) else []
        accumulator.extend_turn(turn_id, events)
    return accumulator.snapshot()
