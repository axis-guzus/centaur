"""Layout-primitive handlers — sparkline, KPI tile, big-number, small multiples."""

from __future__ import annotations

import numpy as np
import pandas as pd
from matplotlib.figure import Figure

from .. import helpers as cc
from ..crypto import color_for
from ..style import GAIN_LOSS, current_mode
from ._common import (
    apply_title_and_subtitle,
    color_for_label,
    cycle_color,
    is_datelike,
    maybe_dates,
    resolve_x,
    resolve_y,
    setup_date_axis,
)


def sparkline_handler(intent, data: pd.DataFrame) -> Figure:
    """Sparkline — tiny line, no spines, no ticks. ~400×100 PNG."""
    x_col = resolve_x(intent.x, data)
    y_cols = resolve_y(intent.y, data, x_col)
    y_col = y_cols[0]
    x = maybe_dates(data[x_col])
    y = data[y_col].astype(float).to_numpy()
    color = color_for_label(intent.protagonist or y_col)

    fig, ax = cc.subplots(figsize=(2.0, 0.5))
    ax.plot(x, y, color=color, linewidth=1.4)
    cc.despine(ax, all=True)
    return fig


def kpi_tile_handler(intent, data: pd.DataFrame) -> Figure:
    """KPI tile — single big number + label + optional delta. ~600×240 PNG.

    Data shape (flexible):
        * Empty / single row → use ``intent.takeaway_title`` as the label and
          the first numeric column as the value.
        * Two rows → first = previous, second = current; show a delta.
    """
    fig, ax = cc.subplots(figsize=(3.0, 1.2))
    cc.despine(ax, all=True)

    label = intent.takeaway_title or (str(data.iloc[0, 0]) if not data.empty else "—")
    if data.empty:
        value: float | None = None
    else:
        numeric = data.select_dtypes(include="number")
        value = float(numeric.iloc[-1, 0]) if numeric.shape[1] > 0 else None

    delta_pct: float | None = None
    if data.shape[0] >= 2:
        numeric = data.select_dtypes(include="number")
        if numeric.shape[1] > 0:
            prev = float(numeric.iloc[0, 0]) or None
            curr = float(numeric.iloc[-1, 0])
            if prev:
                delta_pct = (curr - prev) / prev * 100.0

    if value is None:
        ax.text(0.5, 0.5, "—", ha="center", va="center", fontsize=36, fontweight=600, color="#888888")
    else:
        ax.text(
            0.5,
            0.62,
            _format_big(value),
            ha="center",
            va="center",
            fontsize=32,
            fontweight=700,
            color="#1A1A1A",
        )
        ax.text(
            0.5,
            0.18,
            label,
            ha="center",
            va="center",
            fontsize=11,
            color="#666666",
        )
        if delta_pct is not None:
            gl = GAIN_LOSS[current_mode()]
            color = gl["gain"] if delta_pct >= 0 else gl["loss"]
            sign = "+" if delta_pct >= 0 else ""
            ax.text(
                0.95,
                0.92,
                f"{sign}{delta_pct:.1f}%",
                ha="right",
                va="top",
                fontsize=12,
                fontweight=600,
                color=color,
            )
    return fig


def big_number_with_sparkline_handler(intent, data: pd.DataFrame) -> Figure:
    """Big number + small sparkline below. The "Bloomberg headline metric" tile.

    Data shape: ``[date, value]``. Last value drives the big number; the full
    series drives the sparkline.
    """
    if data.shape[0] == 0 or data.select_dtypes(include="number").shape[1] == 0:
        return kpi_tile_handler(intent, data)

    x_col = resolve_x(intent.x, data)
    y_cols = resolve_y(intent.y, data, x_col)
    y_col = y_cols[0]
    x = maybe_dates(data[x_col])
    y = data[y_col].astype(float).to_numpy()

    color = color_for_label(intent.protagonist or y_col)
    delta = (y[-1] - y[0]) / y[0] * 100.0 if len(y) >= 2 and y[0] else 0.0
    gl = GAIN_LOSS[current_mode()]
    delta_color = gl["gain"] if delta >= 0 else gl["loss"]
    sign = "+" if delta >= 0 else ""

    import matplotlib.gridspec as gridspec

    fig = (
        __import__("matplotlib.pyplot", fromlist=["figure"])
        .figure(figsize=(4.0, 2.0))
    )
    gs = gridspec.GridSpec(2, 1, height_ratios=[2, 1], hspace=0.0)
    big_ax = fig.add_subplot(gs[0])
    spark_ax = fig.add_subplot(gs[1])

    cc.despine(big_ax, all=True)
    cc.despine(spark_ax, all=True)

    big_ax.text(
        0.5,
        0.55,
        _format_big(y[-1]),
        ha="center",
        va="center",
        fontsize=28,
        fontweight=700,
        color="#1A1A1A",
    )
    big_ax.text(
        0.5,
        0.18,
        intent.takeaway_title or y_col,
        ha="center",
        va="center",
        fontsize=10,
        color="#666666",
    )
    big_ax.text(
        0.95,
        0.95,
        f"{sign}{delta:.1f}%",
        ha="right",
        va="top",
        fontsize=11,
        fontweight=600,
        color=delta_color,
    )
    spark_ax.plot(x, y, color=color, linewidth=1.6)
    return fig


def small_multiples_handler(intent, data: pd.DataFrame) -> Figure:
    """Small multiples (faceted lines) — one panel per series.

    Use when there are too many series to overlay (> 6). Default layout: a
    grid that's roughly square; up to ``intent.extras["max_panels"]`` panels.
    """
    x_col = resolve_x(intent.x, data)
    y_cols = resolve_y(intent.y, data, x_col)
    max_panels = int(intent.extras.get("max_panels", 12))
    y_cols = y_cols[:max_panels]
    n = len(y_cols)
    if n == 0:
        from .timeseries import _empty_message_figure

        return _empty_message_figure(intent, "Need ≥ 1 numeric column")

    cols = int(np.ceil(np.sqrt(n)))
    rows = int(np.ceil(n / cols))
    fig, axes = cc.subplots(
        nrows=rows,
        ncols=cols,
        sharex=True,
        sharey=False,
        figsize=(8.0, max(4.5, 1.4 * rows + 1.5)),
    )
    axes_flat = np.array(axes).reshape(-1)
    x = maybe_dates(data[x_col])
    for i, col in enumerate(y_cols):
        ax = axes_flat[i]
        c = color_for(col) or cycle_color(i)
        y = data[col].astype(float).to_numpy()
        ax.plot(x, y, color=c, linewidth=1.6)
        ax.fill_between(x, y, np.nanmin(y), color=c, alpha=0.08)
        ax.set_title(col, loc="left", fontsize=10, fontweight=600, pad=4)
        cc.format_yaxis_si(ax)
        if is_datelike(x):
            setup_date_axis(ax, max_ticks=3)
    # Hide extra panels.
    for j in range(n, len(axes_flat)):
        axes_flat[j].set_visible(False)
    apply_title_and_subtitle(axes_flat[0], intent)
    return fig


# ── tiny utility: human-readable big number ──


def _format_big(value: float) -> str:
    abs_v = abs(value)
    if abs_v >= 1e12:
        return f"{value / 1e12:.2f}T"
    if abs_v >= 1e9:
        return f"{value / 1e9:.2f}B"
    if abs_v >= 1e6:
        return f"{value / 1e6:.2f}M"
    if abs_v >= 1e3:
        return f"{value / 1e3:.1f}k"
    if abs_v >= 1:
        return f"{value:,.2f}"
    return f"{value:.4f}"
