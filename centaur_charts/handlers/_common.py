"""Shared helpers across handler modules.

Keeps the per-handler files thin and consistent.
"""

from __future__ import annotations

from typing import Any, Iterable

import matplotlib.dates as mdates
import numpy as np
import pandas as pd
from matplotlib.axes import Axes

from ..crypto import color_for, palette_for
from ..helpers import direct_label_lines, highlight_one, subtitle_title
from ..style import HIGHLIGHT, OKABE_ITO, current_mode


def first_two_columns(data: pd.DataFrame) -> tuple[str, str]:
    """Return ``(x_col, y_col)`` — the first two columns by position."""
    if data.shape[1] < 2:
        raise ValueError("Need at least 2 columns to chart")
    return str(data.columns[0]), str(data.columns[1])


def maybe_dates(series: pd.Series) -> pd.Series:
    """Best-effort coerce a series to datetime; return original on failure."""
    if pd.api.types.is_datetime64_any_dtype(series):
        return series
    if not pd.api.types.is_string_dtype(series):
        return series
    sample = series.dropna().astype(str).head(20)
    if sample.empty or not sample.str.contains(r"\d{4}-\d{1,2}-\d{1,2}|\d{1,2}/\d{1,2}/\d{2,4}", regex=True).any():
        return series
    parsed = pd.to_datetime(series, errors="coerce")
    if parsed.isna().any():
        return series
    return parsed


def is_datelike(series: pd.Series) -> bool:
    return pd.api.types.is_datetime64_any_dtype(series)


def resolve_x(intent_x: str | None, data: pd.DataFrame) -> str:
    if intent_x and intent_x in data.columns:
        return intent_x
    return str(data.columns[0])


def resolve_y(
    intent_y: str | list[str] | None,
    data: pd.DataFrame,
    x_col: str,
) -> list[str]:
    """Resolve y-column hint; fall back to all numeric columns ≠ x_col."""
    if isinstance(intent_y, str) and intent_y in data.columns:
        return [intent_y]
    if isinstance(intent_y, list):
        return [c for c in intent_y if c in data.columns]
    numeric_cols = data.select_dtypes(include="number").columns.tolist()
    return [c for c in numeric_cols if c != x_col] or [str(data.columns[1])]


def color_for_label(label: str) -> str:
    """Brand colour if recognised, else Centaur primary."""
    return color_for(label) or HIGHLIGHT[current_mode()]


def colors_for_labels(labels: Iterable[str]) -> list[str]:
    return palette_for(list(labels))


def setup_date_axis(ax: Axes, max_ticks: int = 6) -> None:
    """Apply a sane date locator + ConciseDateFormatter to the x-axis."""
    locator = mdates.AutoDateLocator(maxticks=max_ticks)
    ax.xaxis.set_major_locator(locator)
    ax.xaxis.set_major_formatter(mdates.ConciseDateFormatter(locator))


def apply_title_and_subtitle(ax: Axes, intent: Any) -> None:
    """Apply ``ChartIntent.takeaway_title`` (+ optional subtitle) to the axes."""
    title = (
        intent.takeaway_title
        or intent.question
        or intent.chart_type.replace("_", " ").title()
    )
    subtitle_title(ax, title, subtitle=intent.subtitle)


def apply_protagonist(ax: Axes, intent: Any, default: str | None = None) -> None:
    """If a protagonist line label is set, highlight + grey the rest."""
    label = intent.protagonist or default
    if not label:
        return
    if any(line.get_label() == label for line in ax.get_lines()):
        highlight_one(ax, label)
        direct_label_lines(ax)


def safe_categories(values: pd.Series) -> list[str]:
    """Coerce a categorical column to display strings."""
    return [str(v) for v in values]


def annotate_endpoints(ax: Axes, x: np.ndarray, y: np.ndarray, *, fmt: str = "{:.0f}") -> None:
    """Annotate the first and last data point with their values."""
    if len(y) == 0:
        return
    ax.annotate(
        fmt.format(float(y[-1])),
        xy=(x[-1], y[-1]),
        xytext=(4, 0),
        textcoords="offset points",
        ha="left",
        va="center",
        fontsize=10,
        fontweight=600,
        color=ax.get_lines()[-1].get_color() if ax.get_lines() else "#333333",
    )


def cycle_color(idx: int) -> str:
    return OKABE_ITO[idx % len(OKABE_ITO)]
