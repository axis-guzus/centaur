"""Time-series and slope/dumbbell handlers.

Every handler takes ``(intent: ChartIntent, data: pd.DataFrame) -> Figure`` and
inherits the Centaur visual signature via ``cc.subplots`` and the helpers in
``centaur_charts.helpers``.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
from matplotlib.figure import Figure

from .. import helpers as cc
from ..style import GREY_MUTED, current_mode
from ._common import (
    apply_protagonist,
    apply_title_and_subtitle,
    color_for_label,
    colors_for_labels,
    cycle_color,
    is_datelike,
    maybe_dates,
    resolve_x,
    resolve_y,
    setup_date_axis,
)


def line_handler(intent, data: pd.DataFrame) -> Figure:
    """Single-series line. Default for "trend" / "history" / "over time"."""
    x_col = resolve_x(intent.x, data)
    y_cols = resolve_y(intent.y, data, x_col)
    y_col = y_cols[0]

    x = maybe_dates(data[x_col])
    y = data[y_col].astype(float).to_numpy()

    label = intent.protagonist or y_col
    color = color_for_label(label)

    fig, ax = cc.subplots(figsize=(8.0, 4.5))
    ax.plot(x, y, color=color, linewidth=2.0, zorder=10)
    ax.fill_between(x, y, np.nanmin(y), color=color, alpha=0.08, zorder=0)
    apply_title_and_subtitle(ax, intent)
    if is_datelike(x):
        setup_date_axis(ax)
    cc.format_yaxis_si(ax)
    return fig


def multi_line_handler(intent, data: pd.DataFrame) -> Figure:
    """Multi-line. Highlights ``intent.protagonist`` if set."""
    x_col = resolve_x(intent.x, data)
    y_cols = resolve_y(intent.y, data, x_col)

    x = maybe_dates(data[x_col])

    fig, ax = cc.subplots(figsize=(8.0, 4.5))
    for i, col in enumerate(y_cols):
        ax.plot(
            x,
            data[col].astype(float).to_numpy(),
            color=color_for_label(col) if intent.protagonist else cycle_color(i),
            linewidth=2.0,
            label=col,
        )

    apply_title_and_subtitle(ax, intent)
    apply_protagonist(ax, intent)
    if not intent.protagonist:
        cc.direct_label_lines(ax)
    if is_datelike(x):
        setup_date_axis(ax)
    cc.format_yaxis_si(ax)
    return fig


def indexed_line_handler(intent, data: pd.DataFrame) -> Figure:
    """Indexed/rebased line. Each series rebased to 100 at the first data point.

    The right way to compare instruments — never dual-axis.
    """
    x_col = resolve_x(intent.x, data)
    y_cols = resolve_y(intent.y, data, x_col)

    x = maybe_dates(data[x_col])
    base_row = data.iloc[0]

    fig, ax = cc.subplots(figsize=(8.0, 4.5))
    for i, col in enumerate(y_cols):
        base = float(base_row[col]) if base_row[col] else 1.0
        rebased = data[col].astype(float).to_numpy() / base * 100.0
        ax.plot(
            x,
            rebased,
            color=color_for_label(col) if intent.protagonist else cycle_color(i),
            linewidth=2.0,
            label=col,
        )
    ax.axhline(
        100,
        color=GREY_MUTED[current_mode()],
        linewidth=0.8,
        linestyle="--",
        zorder=0,
    )

    apply_title_and_subtitle(ax, intent)
    apply_protagonist(ax, intent)
    if not intent.protagonist:
        cc.direct_label_lines(ax)
    if is_datelike(x):
        setup_date_axis(ax)
    # Show ticks as +/- % from the 100 baseline.
    import matplotlib.ticker as mticker

    ax.yaxis.set_major_formatter(
        mticker.FuncFormatter(lambda v, _: f"{v - 100:+.0f}%" if v != 100 else "0%")
    )
    return fig


def slope_handler(intent, data: pd.DataFrame) -> Figure:
    """Slope graph between exactly two time points. Falls back gracefully if
    the data has more — uses first and last."""
    x_col = resolve_x(intent.x, data)
    y_cols = resolve_y(intent.y, data, x_col)
    if data.shape[0] < 2:
        return _empty_message_figure(intent, "Need at least 2 rows for a slope graph")

    first = data.iloc[0]
    last = data.iloc[-1]

    fig, ax = cc.subplots(figsize=(8.0, 4.5))
    for i, col in enumerate(y_cols):
        c = color_for_label(col) if intent.protagonist else cycle_color(i)
        a, b = float(first[col]), float(last[col])
        ax.plot([0, 1], [a, b], color=c, linewidth=2.4, marker="o", markersize=6)
        ax.annotate(
            f"{col}: {a:.1f}",
            xy=(0, a),
            xytext=(-8, 0),
            textcoords="offset points",
            ha="right",
            va="center",
            fontsize=10,
            color=c,
            fontweight=600,
        )
        ax.annotate(
            f"{b:.1f}",
            xy=(1, b),
            xytext=(8, 0),
            textcoords="offset points",
            ha="left",
            va="center",
            fontsize=10,
            color=c,
            fontweight=600,
        )

    ax.set_xlim(-0.4, 1.4)
    ax.set_xticks([0, 1])
    ax.set_xticklabels([str(first[x_col]), str(last[x_col])])
    ax.spines["bottom"].set_visible(False)
    ax.tick_params(axis="x", length=0)
    ax.grid(False)
    apply_title_and_subtitle(ax, intent)
    return fig


def dumbbell_handler(intent, data: pd.DataFrame) -> Figure:
    """Dumbbell plot: two values per category, gap is the story.

    Expected columns: ``[label, before, after]`` or ``intent.extras["before"]``
    / ``intent.extras["after"]`` to override.
    """
    if data.shape[1] < 3:
        return _empty_message_figure(intent, "Need 3 columns: label, before, after")
    label_col = str(data.columns[0])
    before_col = intent.extras.get("before") or str(data.columns[1])
    after_col = intent.extras.get("after") or str(data.columns[2])

    df = data.copy()
    df = df.sort_values(after_col, ascending=True)
    labels = df[label_col].astype(str).tolist()
    before = df[before_col].astype(float).to_numpy()
    after = df[after_col].astype(float).to_numpy()

    fig, ax = cc.subplots(figsize=(8.0, max(4.5, 0.4 * len(labels) + 1.5)))
    y = np.arange(len(labels))
    grey = GREY_MUTED[current_mode()]
    for yi, b, a in zip(y, before, after):  # noqa: B905
        ax.plot([b, a], [yi, yi], color=grey, linewidth=2.0, zorder=2)
    ax.scatter(before, y, color=cycle_color(0), s=60, zorder=3, label=before_col)
    ax.scatter(after, y, color=cycle_color(1), s=60, zorder=4, label=after_col)
    ax.set_yticks(y)
    ax.set_yticklabels(labels)
    ax.legend(loc="lower right", frameon=False)
    apply_title_and_subtitle(ax, intent)
    cc.format_xaxis_si(ax)
    return fig


def lollipop_handler(intent, data: pd.DataFrame) -> Figure:
    """Lollipop / horizontal-bar with low ink. Same data shape as bar."""
    label_col = resolve_x(intent.x, data)
    y_cols = resolve_y(intent.y, data, label_col)
    value_col = y_cols[0]

    df = data.sort_values(value_col, ascending=True)
    labels = df[label_col].astype(str).tolist()
    values = df[value_col].astype(float).to_numpy()
    colors = colors_for_labels(labels)

    fig, ax = cc.subplots(figsize=(8.0, max(4.5, 0.4 * len(labels) + 1.5)))
    y = np.arange(len(labels))
    grey = GREY_MUTED[current_mode()]
    ax.hlines(y, 0, values, color=grey, linewidth=1.4, zorder=1)
    ax.scatter(values, y, color=colors, s=80, zorder=2)
    ax.set_yticks(y)
    ax.set_yticklabels(labels)
    cc.format_xaxis_si(ax)
    apply_title_and_subtitle(ax, intent)
    return fig


def area_handler(intent, data: pd.DataFrame) -> Figure:
    """Single-series area chart."""
    x_col = resolve_x(intent.x, data)
    y_cols = resolve_y(intent.y, data, x_col)
    y_col = y_cols[0]
    x = maybe_dates(data[x_col])
    y = data[y_col].astype(float).to_numpy()
    color = color_for_label(intent.protagonist or y_col)

    fig, ax = cc.subplots(figsize=(8.0, 4.5))
    ax.fill_between(x, y, np.nanmin(y), color=color, alpha=0.25, zorder=2)
    ax.plot(x, y, color=color, linewidth=2.0, zorder=3)
    apply_title_and_subtitle(ax, intent)
    if is_datelike(x):
        setup_date_axis(ax)
    cc.format_yaxis_si(ax)
    return fig


def stacked_area_handler(intent, data: pd.DataFrame) -> Figure:
    """Stacked area: composition over time. ≤ 5 components recommended."""
    x_col = resolve_x(intent.x, data)
    y_cols = resolve_y(intent.y, data, x_col)
    if len(y_cols) > 5:
        # Aggregate the smallest into "Other" — protect against component spam.
        sums = {c: float(data[c].sum()) for c in y_cols}
        sorted_cols = sorted(sums, key=lambda k: sums[k], reverse=True)
        keep, rest = sorted_cols[:5], sorted_cols[5:]
        if rest:
            data = data.copy()
            data["Other"] = data[rest].sum(axis=1)
            y_cols = keep + ["Other"]

    x = maybe_dates(data[x_col])
    series = [data[c].astype(float).to_numpy() for c in y_cols]
    colors = colors_for_labels(y_cols)
    fig, ax = cc.subplots(figsize=(8.0, 4.5))
    ax.stackplot(x, *series, labels=y_cols, colors=colors, edgecolor="white", linewidth=0.5)
    ax.legend(loc="upper left", frameon=False, fontsize=9)
    apply_title_and_subtitle(ax, intent)
    if is_datelike(x):
        setup_date_axis(ax)
    cc.format_yaxis_si(ax)
    return fig


# ── tiny utility — used by handlers that need to give up gracefully ──


def _empty_message_figure(intent, msg: str) -> Figure:
    fig, ax = cc.subplots(figsize=(8.0, 4.5))
    for s in ax.spines.values():
        s.set_visible(False)
    ax.set_xticks([])
    ax.set_yticks([])
    ax.grid(False)
    title = intent.takeaway_title or intent.chart_type.replace("_", " ").title()
    ax.text(0.5, 0.6, title, ha="center", va="center", fontsize=14, fontweight=600, color="#333333")
    ax.text(0.5, 0.42, msg, ha="center", va="center", fontsize=10, color="#888888")
    return fig
