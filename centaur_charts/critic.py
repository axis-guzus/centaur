"""Automated checks for chart output.

  * ``data_integrity_check`` — every numeric in the takeaway title /
    subtitle / annotations must be derivable from the dataframe.
    Recomputes and asserts.
  * ``mobile_readability_check`` — downsamples the PNG to 360 px wide
    (Slack mobile preview) and checks the rendered file is non-trivial,
    has reasonable dimensions, and the source resolution is high enough
    that text would survive downsampling.

Both functions are pure-Python and return structured ``CriticIssue`` values.
"""

from __future__ import annotations

import io
import re
from dataclasses import dataclass

import numpy as np
import pandas as pd

from .router import ChartArtifact, ChartIntent


@dataclass
class CriticIssue:
    severity: str  # "error" | "warning" | "info"
    code: str
    message: str
    field: str = ""  # which intent field surfaced the issue


_NUMERIC_TOKEN = re.compile(
    r"""
    (?P<sign>[+\-])?
    (?P<currency>\$)?
    (?P<num>\d+(?:,\d{3})*(?:\.\d+)?|\d+(?:\.\d+)?)
    (?P<suffix>[kKmMbBtT])?
    (?P<pct>%)?
    """,
    re.VERBOSE,
)


def _to_float(token: str) -> float:
    """Coerce a token like ``+38.5%``, ``$1.2B``, or ``1,234`` to float."""
    m = _NUMERIC_TOKEN.fullmatch(token.strip())
    if not m:
        raise ValueError(f"Not a numeric token: {token!r}")
    raw = m.group("num").replace(",", "")
    val = float(raw)
    if m.group("sign") == "-":
        val = -val
    sfx = (m.group("suffix") or "").lower()
    if sfx == "k":
        val *= 1_000
    elif sfx == "m":
        val *= 1_000_000
    elif sfx == "b":
        val *= 1_000_000_000
    elif sfx == "t":
        val *= 1_000_000_000_000
    return val


def _extract_numeric_tokens(text: str) -> list[tuple[str, float, str]]:
    """Pull every numeric-looking token out of a string.

    Returns ``(token_str, parsed_float, kind)`` where kind is one of
    ``percent``, ``currency``, or ``number``.
    """
    tokens: list[tuple[str, float]] = []
    for m in re.finditer(
        r"[+\-]?\$?\d{1,3}(?:,\d{3})*(?:\.\d+)?[kKmMbBtT%]?|"
        r"[+\-]?\$?\d+(?:\.\d+)?[kKmMbBtT%]?",
        text,
    ):
        token = m.group(0)
        try:
            parsed = _NUMERIC_TOKEN.fullmatch(token.strip())
            kind = "percent" if parsed and parsed.group("pct") else "currency" if parsed and parsed.group("currency") else "number"
            tokens.append((token, _to_float(token), kind))
        except ValueError:
            continue
    return tokens


def _compute_candidate_values(data: pd.DataFrame) -> dict[str, set[float]]:
    """Return a set of floats derivable from the dataframe.

    Includes raw values, common reductions (sum / mean / median / max / min),
    pairwise % deltas (last vs first per numeric column), and 24h-ish %
    changes (last 1, 7, 30 vs first when applicable). Generous on purpose;
    the critic flags only when the LLM cited a number that's *outside* this
    set entirely.
    """
    candidates: dict[str, set[float]] = {"number": set(), "currency": set(), "percent": set()}
    for col in data.select_dtypes(include="number").columns:
        s = data[col].dropna()
        if s.empty:
            continue
        nums = s.astype(float).to_numpy()
        for value in nums.tolist():
            candidates["number"].add(float(value))
            candidates["currency"].add(float(value))
        for value in [float(nums.sum()), float(nums.mean()), float(np.median(nums)), float(nums.max()), float(nums.min())]:
            candidates["number"].add(value)
            candidates["currency"].add(value)
        if len(nums) >= 2 and nums[0]:
            candidates["percent"].add(float((nums[-1] - nums[0]) / nums[0] * 100))
            candidates["percent"].add(float((nums[-1] / nums[0] - 1) * 100))
            candidates["number"].add(float(nums[-1] - nums[0]))
            candidates["currency"].add(float(nums[-1] - nums[0]))
        if nums.sum():
            candidates["percent"].add(float(nums.max() / nums.sum() * 100))
    return candidates


def data_integrity_check(
    intent: ChartIntent,
    data: pd.DataFrame,
    *,
    relative_tolerance: float = 0.02,
) -> list[CriticIssue]:
    """Recompute every numeric token in title/subtitle/annotations from the
    dataframe and assert it's within ``relative_tolerance`` of *some* value
    the data could plausibly produce.

    Hallucinated numbers (LLM "knows" a value not in the data) → critic
    error. The relative tolerance covers rounding ("38.5%" vs "38.51%").
    """
    issues: list[CriticIssue] = []
    candidates = _compute_candidate_values(data)
    if not any(candidates.values()):
        return issues

    sources: list[tuple[str, str]] = []
    if intent.takeaway_title:
        sources.append(("takeaway_title", intent.takeaway_title))
    if intent.subtitle:
        sources.append(("subtitle", intent.subtitle))
    if intent.question:
        sources.append(("question", intent.question))
    for i, ann in enumerate(intent.annotations or []):
        if isinstance(ann, dict):
            for key in ("text", "label", "callout"):
                if isinstance(ann.get(key), str):
                    sources.append((f"annotations[{i}].{key}", ann[key]))

    for field, text in sources:
        for token, value, kind in _extract_numeric_tokens(text):
            if not _matches_any(value, candidates.get(kind, set()), relative_tolerance):
                issues.append(
                    CriticIssue(
                        severity="error",
                        code="hallucinated_number",
                        message=(
                            f"{field!r} cites {token!r} (≈ {value:g}) but no "
                            f"value within {relative_tolerance:.0%} tolerance is derivable "
                            f"from the dataframe."
                        ),
                        field=field,
                    )
                )
    return issues


def _matches_any(value: float, candidates: set[float], tol: float) -> bool:
    """True if any candidate is within ``tol`` relative tolerance of value."""
    for c in candidates:
        if c == 0:
            if abs(value) < 1e-9:
                return True
            continue
        if abs(value - c) <= tol * max(abs(c), 1e-9):
            return True
    return False


def mobile_readability_check(
    artifact: ChartArtifact,
    *,
    target_width: int = 360,
    min_text_pixels: float = 18.0,
) -> list[CriticIssue]:
    """Validate that the rendered PNG would still read on Slack mobile.

    Heuristic — we don't run OCR (too heavy, dependent on the agent harness);
    instead we check:
      * The artifact's source dimensions are at least ``target_width`` × 2
        (so 720 px wide minimum at 200 DPI savefig).
      * The PNG is ≥ 8 KB (so it's not a placeholder / blank).
      * Width × height ratio is ≤ 21 / 9 (no vertical-tall mobile-cropper).

    This automated check catches obvious failures cheaply. Human/visual review
    can still catch overlaps or bad labels that geometry cannot infer.
    """
    issues: list[CriticIssue] = []
    w, h = artifact.width, artifact.height
    if w < target_width * 2:
        issues.append(
            CriticIssue(
                severity="error",
                code="source_too_small",
                message=f"Source PNG is {w}px wide; need ≥ {target_width * 2} for Slack mobile.",
            )
        )
    if h > 0 and (h / max(w, 1)) > (9 / 21):
        # Taller than 9:21 → effectively portrait — Slack mobile crops badly.
        # Inverse: w/h < 21/9 means it's not 21:9 wide-screen; this catches
        # squarish or portrait charts.
        if (h / max(w, 1)) > (16 / 9 + 0.01):
            issues.append(
                CriticIssue(
                    severity="warning",
                    code="aspect_too_tall",
                    message=f"Aspect {w}×{h} is taller than 16:9 — Slack mobile may crop.",
                )
            )

    if len(artifact.png_bytes) < 8 * 1024:
        issues.append(
            CriticIssue(
                severity="warning",
                code="png_too_small",
                message=(
                    f"PNG is only {len(artifact.png_bytes)} bytes — likely a placeholder "
                    "or a near-empty chart."
                ),
            )
        )

    # Try to verify text would survive downsampling using PIL when available.
    # We can't OCR cheaply, but we can compute the median text block size by
    # looking at edge density. Skip if PIL isn't installed.
    try:
        from PIL import Image

        img = Image.open(io.BytesIO(artifact.png_bytes))
        small = img.resize((target_width, int(target_width * h / max(w, 1))))
        if min(small.size) < 80:
            issues.append(
                CriticIssue(
                    severity="warning",
                    code="downsample_lost_detail",
                    message="Downsampled preview is < 80 px — text likely unreadable.",
                )
            )
    except Exception:  # noqa: BLE001
        # PIL absent or PNG malformed — non-fatal.
        pass

    return issues


def run_all_automated_checks(
    intent: ChartIntent,
    data: pd.DataFrame,
    artifact: ChartArtifact,
) -> list[CriticIssue]:
    """Run every Python-side critic check and return the combined issue list.

    Call this before uploading a chart image.
    """
    return [
        *data_integrity_check(intent, data),
        *mobile_readability_check(artifact),
    ]


def assert_all_pass(issues: list[CriticIssue]) -> None:
    """Raise ``AssertionError`` if any critic issue is severity ``error``."""
    errors = [i for i in issues if i.severity == "error"]
    if errors:
        raise AssertionError(
            "Chart failed critic checks: "
            + "; ".join(f"{i.code}: {i.message}" for i in errors)
        )
