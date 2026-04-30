"""Composition / part-to-whole / heatmap handlers."""

from __future__ import annotations

import numpy as np
import pandas as pd
from matplotlib.figure import Figure

from .. import helpers as cc
from ..style import GAIN_LOSS, current_mode
from ._common import (
    apply_title_and_subtitle,
    colors_for_labels,
    cycle_color,
    is_datelike,
    maybe_dates,
    resolve_x,
    resolve_y,
    setup_date_axis,
)


def treemap_handler(intent, data: pd.DataFrame) -> Figure:
    """Treemap. Falls back to horizontal bar if squarify isn't available."""
    try:
        import squarify  # type: ignore[import-not-found]
    except ImportError:
        from .comparison import horizontal_bar_handler

        return horizontal_bar_handler(intent, data)

    label_col = resolve_x(intent.x, data)
    y_cols = resolve_y(intent.y, data, label_col)
    value_col = y_cols[0]
    df = data.sort_values(value_col, ascending=False)
    sizes = df[value_col].astype(float).to_numpy()
    sizes = sizes[sizes > 0]
    labels = df[label_col].astype(str).tolist()[: len(sizes)]
    colors = colors_for_labels(labels)
    norm = squarify.normalize_sizes(sizes, 100, 100)
    rects = squarify.squarify(norm, 0, 0, 100, 100)

    fig, ax = cc.subplots(figsize=(8.0, 4.5))
    for rect, color, label, size in zip(rects, colors, labels, sizes):  # noqa: B905
        ax.add_patch(
            __mpl_rect(rect["x"], rect["y"], rect["dx"], rect["dy"], color)
        )
        if rect["dx"] * rect["dy"] >= 50:  # only label larger rects
            ax.text(
                rect["x"] + rect["dx"] / 2,
                rect["y"] + rect["dy"] / 2,
                f"{label}\n{size:,.0f}",
                ha="center",
                va="center",
                fontsize=9,
                fontweight=600,
                color="white",
            )
    for s in ax.spines.values():
        s.set_visible(False)
    ax.set_xticks([])
    ax.set_yticks([])
    ax.set_xlim(0, 100)
    ax.set_ylim(0, 100)
    ax.grid(False)
    ax.set_aspect("auto")
    apply_title_and_subtitle(ax, intent)
    return fig


def __mpl_rect(x: float, y: float, w: float, h: float, color: str):
    from matplotlib.patches import Rectangle

    return Rectangle((x, y), w, h, facecolor=color, edgecolor="white", linewidth=1.2)


def waterfall_handler(intent, data: pd.DataFrame) -> Figure:
    """Waterfall — sequential adds/subtracts to a running total."""
    label_col = resolve_x(intent.x, data)
    y_cols = resolve_y(intent.y, data, label_col)
    value_col = y_cols[0]

    labels = data[label_col].astype(str).tolist()
    deltas = data[value_col].astype(float).to_numpy()
    cumulative = np.cumsum(deltas)
    bottoms = np.concatenate([[0], cumulative[:-1]])
    gl = GAIN_LOSS[current_mode()]
    colors = [gl["gain"] if d >= 0 else gl["loss"] for d in deltas]

    fig, ax = cc.subplots(figsize=(8.0, 4.5))
    x = np.arange(len(labels))
    ax.bar(x, deltas, bottom=bottoms, color=colors, edgecolor="none")
    # Connector lines between bars
    for i in range(len(labels) - 1):
        ax.plot([i + 0.4, i + 1 - 0.4], [cumulative[i], cumulative[i]], color="#888888", linewidth=0.8)
    # Total bar at the end
    ax.bar([len(labels)], [cumulative[-1]], bottom=[0], color=cycle_color(0), edgecolor="none")

    ax.set_xticks(np.append(x, [len(labels)]))
    ax.set_xticklabels(labels + ["Total"], rotation=30, ha="right")
    cc.format_yaxis_si(ax)
    apply_title_and_subtitle(ax, intent)
    return fig


def pie_handler(intent, data: pd.DataFrame) -> Figure:
    """Pie chart — only when n ≤ 3 (router downgrades larger pies to bar)."""
    label_col = resolve_x(intent.x, data)
    y_cols = resolve_y(intent.y, data, label_col)
    value_col = y_cols[0]
    df = data.copy()
    df = df[df[value_col].astype(float) > 0].sort_values(value_col, ascending=False)
    labels = df[label_col].astype(str).tolist()
    values = df[value_col].astype(float).to_numpy()
    if values.size == 0:
        from .timeseries import _empty_message_figure

        return _empty_message_figure(intent, "No positive values to chart")

    colors = colors_for_labels(labels)

    fig, ax = cc.subplots(figsize=(8.0, 4.5))
    for s in ax.spines.values():
        s.set_visible(False)
    ax.set_xticks([])
    ax.set_yticks([])
    ax.grid(False)
    ax.set_aspect("equal")
    wedges, _, autotexts = ax.pie(
        values,
        labels=None,
        colors=colors,
        autopct=lambda p: f"{p:.0f}%" if p >= 5 else "",
        startangle=90,
        counterclock=False,
        wedgeprops={"edgecolor": "white", "linewidth": 1.4},
        textprops={"color": "white", "fontsize": 10, "fontweight": 600},
    )
    ax.legend(
        wedges,
        [f"{lab} — {val / values.sum() * 100:.1f}%" for lab, val in zip(labels, values)],  # noqa: B905
        loc="center left",
        bbox_to_anchor=(1.02, 0.5),
        frameon=False,
        fontsize=10,
    )
    apply_title_and_subtitle(ax, intent)
    return fig


def heatmap_handler(intent, data: pd.DataFrame) -> Figure:
    """Generic heatmap. Expects a wide DataFrame: index = rows, columns = cols.

    Use ``intent.extras["diverging"]`` = True for diverging palette
    (RdBu_r centered at 0), otherwise sequential viridis.
    """
    matrix = data.select_dtypes(include="number")
    diverging = bool(intent.extras.get("diverging"))
    cmap = "RdBu_r" if diverging else "viridis"
    if diverging:
        vmax = float(np.nanmax(np.abs(matrix.values))) if matrix.size > 0 else 1.0
        vmin = -vmax
    else:
        vmin, vmax = float(np.nanmin(matrix.values)), float(np.nanmax(matrix.values))

    fig, ax = cc.subplots(figsize=(8.0, max(4.5, 0.35 * len(matrix.index) + 2.0)))
    im = ax.imshow(matrix.values, cmap=cmap, vmin=vmin, vmax=vmax, aspect="auto")
    ax.set_xticks(range(len(matrix.columns)))
    ax.set_xticklabels(matrix.columns, rotation=30, ha="right")
    ax.set_yticks(range(len(matrix.index)))
    ax.set_yticklabels([str(i) for i in matrix.index])
    fig.colorbar(im, ax=ax)
    ax.grid(False)
    apply_title_and_subtitle(ax, intent)
    return fig


def calendar_heatmap_handler(intent, data: pd.DataFrame) -> Figure:
    """Calendar heatmap. Falls back to scatter on date if `july` not installed."""
    try:
        import july  # type: ignore[import-not-found]

        date_col = resolve_x(intent.x, data)
        y_cols = resolve_y(intent.y, data, date_col)
        value_col = y_cols[0]
        dates = pd.to_datetime(data[date_col]).dt.date.tolist()
        values = data[value_col].astype(float).tolist()
        fig = july.heatmap(
            dates=dates,
            data=values,
            cmap="viridis",
            colorbar=True,
            month_grid=True,
            horizontal=True,
            value_label=False,
            title=intent.takeaway_title or None,
            fontfamily="sans-serif",
        )
        return fig.get_figure() if hasattr(fig, "get_figure") else fig
    except ImportError:
        # Fall back to a basic line on date.
        x_col = resolve_x(intent.x, data)
        y_cols = resolve_y(intent.y, data, x_col)
        x = maybe_dates(data[x_col])
        y = data[y_cols[0]].astype(float).to_numpy()
        fig, ax = cc.subplots(figsize=(8.0, 4.5))
        ax.plot(x, y, color=cycle_color(0), linewidth=2.0)
        if is_datelike(x):
            setup_date_axis(ax)
        cc.format_yaxis_si(ax)
        apply_title_and_subtitle(ax, intent)
        return fig
