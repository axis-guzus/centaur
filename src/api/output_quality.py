from __future__ import annotations

import re
import threading
import time
from dataclasses import dataclass

_CODE_FENCE_RE = re.compile(r"```[\s\S]*?```")
_INLINE_CODE_RE = re.compile(r"`[^`\n]+`")
_MARKDOWN_LINK_RE = re.compile(r"\[[^\]\n]+\]\([^)]+\)")
_SLACK_LINK_RE = re.compile(r"<https?://[^>|]+(?:\|[^>]+)?>")
_URL_RE = re.compile(r"https?://[^\s<>()]+")
_MENTION_RE = re.compile(r"<@[A-Z0-9]+>")
_DOUBLE_QUOTE_RE = re.compile(r'"[^"\n]{8,}"')
_NUMBER_RE = re.compile(r"\b\d[\d,]*(?:\.\d+)?%?\b")

_LEADING_CHATBOT_RE = re.compile(
    r"^\s*(great question!?|thanks for (the )?(question|context)\.?|happy to help\.?)\s*",
    re.IGNORECASE,
)
_TRAILING_CHATBOT_RE = re.compile(
    r"^\s*(i hope this helps[.!]?|let me know if you'd like.*|let me know if you would like.*|"
    r"feel free to ask.*|happy to dive deeper.*)\s*$",
    re.IGNORECASE,
)
_GENERIC_CONCLUSION_RE = re.compile(
    r"^\s*(in conclusion,\s*)?(the future looks bright\.?|exciting times lie ahead\.?)\s*$",
    re.IGNORECASE,
)

_PHRASE_RULES: list[tuple[str, re.Pattern[str], str]] = [
    ("phrase.in_order_to", re.compile(r"\bIn order to\b"), "To"),
    ("phrase.due_to_fact", re.compile(r"\bDue to the fact that\b"), "Because"),
    ("phrase.important_note", re.compile(r"\bIt is important to note that\b[,]?\s*", re.IGNORECASE), ""),
    ("phrase.should_be_noted", re.compile(r"\bIt should be noted that\b[,]?\s*", re.IGNORECASE), ""),
    ("phrase.worth_noting", re.compile(r"\bIt'?s worth noting that\b[,]?\s*", re.IGNORECASE), ""),
    ("phrase.additionally", re.compile(r"^\s*Additionally,\s*", re.IGNORECASE | re.MULTILINE), "Also, "),
    ("phrase.furthermore", re.compile(r"^\s*Furthermore,\s*", re.IGNORECASE | re.MULTILINE), "Also, "),
    ("phrase.moreover", re.compile(r"^\s*Moreover,\s*", re.IGNORECASE | re.MULTILINE), "Also, "),
    ("phrase.in_conclusion", re.compile(r"^\s*In conclusion,\s*", re.IGNORECASE | re.MULTILINE), ""),
    ("hedge.could_potentially", re.compile(r"\bcould potentially\b", re.IGNORECASE), "could"),
    ("hedge.might_potentially", re.compile(r"\bmight potentially\b", re.IGNORECASE), "might"),
    ("hedge.could_possibly", re.compile(r"\bcould possibly\b", re.IGNORECASE), "could"),
    ("hedge.may_potentially", re.compile(r"\bmay potentially\b", re.IGNORECASE), "may"),
]

_metrics_lock = threading.Lock()
_metrics: dict[str, int] = {
    "total": 0,
    "applied": 0,
    "skipped": 0,
    "error": 0,
    "changed": 0,
    "latency_ms_total": 0,
}


@dataclass(frozen=True)
class OutputQualityResult:
    text: str
    changed: bool
    status: str
    rule_hits: tuple[str, ...]
    latency_ms: int


def get_output_quality_metrics() -> dict[str, int]:
    with _metrics_lock:
        return dict(_metrics)


def _record_metrics(result: OutputQualityResult) -> None:
    with _metrics_lock:
        _metrics["total"] += 1
        _metrics["latency_ms_total"] += max(0, result.latency_ms)
        if result.changed:
            _metrics["changed"] += 1
        status = result.status if result.status in {"applied", "skipped", "error"} else "error"
        _metrics[status] += 1


def _protect_spans(text: str) -> tuple[str, dict[str, str]]:
    protected: dict[str, str] = {}
    idx = 0

    def protect_with(pattern: re.Pattern[str], current: str) -> str:
        nonlocal idx

        def replace(match: re.Match[str]) -> str:
            nonlocal idx
            token = f"__OQ_SPAN_{idx}__"
            idx += 1
            protected[token] = match.group(0)
            return token

        return pattern.sub(replace, current)

    for pattern in (
        _CODE_FENCE_RE,
        _INLINE_CODE_RE,
        _MARKDOWN_LINK_RE,
        _SLACK_LINK_RE,
        _URL_RE,
        _MENTION_RE,
        _DOUBLE_QUOTE_RE,
    ):
        text = protect_with(pattern, text)

    return text, protected


def _restore_spans(text: str, protected: dict[str, str]) -> str:
    restored = text
    for token, original in protected.items():
        restored = restored.replace(token, original)
    return restored


def _trim_chatbot_wrappers(text: str) -> tuple[str, list[str]]:
    hits: list[str] = []
    lines = text.splitlines()
    while lines and _LEADING_CHATBOT_RE.match(lines[0]):
        lines.pop(0)
        hits.append("wrapper.leading")
    while lines and _TRAILING_CHATBOT_RE.match(lines[-1]):
        lines.pop()
        hits.append("wrapper.trailing")
    while lines and _GENERIC_CONCLUSION_RE.match(lines[-1]):
        lines.pop()
        hits.append("wrapper.generic_conclusion")
    return "\n".join(lines), hits


def _normalize_spacing(text: str) -> str:
    text = re.sub(r"[ \t]+\n", "\n", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def _rewrite_text(text: str) -> tuple[str, list[str]]:
    rewritten, hits = _trim_chatbot_wrappers(text)
    for rule_name, pattern, replacement in _PHRASE_RULES:
        updated, count = pattern.subn(replacement, rewritten)
        if count > 0:
            hits.append(rule_name)
            rewritten = updated
    rewritten = _normalize_spacing(rewritten)
    return rewritten, hits


def _extract_tokens(text: str, pattern: re.Pattern[str]) -> list[str]:
    return pattern.findall(text)


def _is_safe_rewrite(before: str, after: str) -> bool:
    if _extract_tokens(before, _MENTION_RE) != _extract_tokens(after, _MENTION_RE):
        return False
    if _extract_tokens(before, _URL_RE) != _extract_tokens(after, _URL_RE):
        return False
    return _extract_tokens(before, _NUMBER_RE) == _extract_tokens(after, _NUMBER_RE)


def apply_output_quality(text: str) -> OutputQualityResult:
    started = time.perf_counter()
    if not text.strip():
        result = OutputQualityResult(
            text=text,
            changed=False,
            status="skipped",
            rule_hits=(),
            latency_ms=0,
        )
        _record_metrics(result)
        return result
    if text.lstrip().startswith("❌"):
        result = OutputQualityResult(
            text=text,
            changed=False,
            status="skipped",
            rule_hits=("error_passthrough",),
            latency_ms=0,
        )
        _record_metrics(result)
        return result

    status = "skipped"
    try:
        protected_text, protected_spans = _protect_spans(text)
        rewritten_text, hits = _rewrite_text(protected_text)
        restored_text = _restore_spans(rewritten_text, protected_spans)
        if restored_text != text and not _is_safe_rewrite(text, restored_text):
            restored_text = text
            hits.append("safety.revert")
        changed = restored_text != text
        if changed:
            status = "applied"
        latency_ms = max(0, int((time.perf_counter() - started) * 1000))
        result = OutputQualityResult(
            text=restored_text,
            changed=changed,
            status=status,
            rule_hits=tuple(hits),
            latency_ms=latency_ms,
        )
        _record_metrics(result)
        return result
    except Exception:
        latency_ms = max(0, int((time.perf_counter() - started) * 1000))
        result = OutputQualityResult(
            text=text,
            changed=False,
            status="error",
            rule_hits=("pipeline.error",),
            latency_ms=latency_ms,
        )
        _record_metrics(result)
        return result
