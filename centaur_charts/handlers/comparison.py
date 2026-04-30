"""Bar / lollipop / bullet handlers — ranking and comparison."""

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
    resolve_x,
    resolve_y,
)


def horizontal_bar_handler(intent, data: pd.DataFrame) -> Figure:
    """Horizontal bar, sorted descending. Default for "ranking" / "top N"."""
    label_col = resolve_x(intent.x, data)
    y_cols = resolve_y(intent.y, data, label_col)
    value_col = y_cols[0]

    df = data.copy()
    df = df.sort_values(value_col, ascending=True)
    labels = df[label_col].astype(str).tolist()
    values = df[value_col].astype(float).to_numpy()
    colors = colors_for_labels(labels)

    fig, ax = cc.subplots(figsize=(8.0, max(4.5, 0.4 * len(labels) + 1.5)))
    y_pos = np.arange(len(labels))
    ax.barh(y_pos, values, color=colors, edgecolor="none")
    ax.set_yticks(y_pos)
    ax.set_yticklabels(labels)
    ax.tick_params(axis="y", length=0)
    ax.spines["left"].set_visible(False)
    ax.grid(axis="x", which="major")
    ax.grid(axis="y", which="major", visible=False)
    cc.format_xaxis_si(ax)
    apply_title_and_subtitle(ax, intent)
    return fig


def vertical_bar_handler(intent, data: pd.DataFrame) -> Figure:
    """Vertical bar (column). Use when labels are short and ordering is the story."""
    label_col = resolve_x(intent.x, data)
    y_cols = resolve_y(intent.y, data, label_col)
    value_col = y_cols[0]

    df = data.copy()
    labels = df[label_col].astype(str).tolist()
    values = df[value_col].astype(float).to_numpy()
    colors = colors_for_labels(labels)

    fig, ax = cc.subplots(figsize=(8.0, 4.5))
    x_pos = np.arange(len(labels))
    ax.bar(x_pos, values, color=colors, edgecolor="none")
    ax.set_xticks(x_pos)
    ax.set_xticklabels(labels, rotation=30 if max(len(s) for s in labels) > 4 else 0, ha="right")
    cc.format_yaxis_si(ax)
    apply_title_and_subtitle(ax, intent)
    return fig


def grouped_bar_handler(intent, data: pd.DataFrame) -> Figure:
    """Grouped bar — categories on x, ≤ 4 series side-by-side."""
    label_col = resolve_x(intent.x, data)
    y_cols = resolve_y(intent.y, data, label_col)
    if not y_cols:
        from .timeseries import _empty_message_figure

        return _empty_message_figure(intent, "Need ≥ 1 numeric column")

    labels = data[label_col].astype(str).tolist()
    n_groups = len(labels)
    n_series = len(y_cols)
    width = 0.8 / max(n_series, 1)
    x_base = np.arange(n_groups)

    fig, ax = cc.subplots(figsize=(8.0, 4.5))
    for i, col in enumerate(y_cols):
        offset = (i - (n_series - 1) / 2) * width
        ax.bar(
            x_base + offset,
            data[col].astype(float).to_numpy(),
            width=width,
            label=col,
            color=cycle_color(i),
            edgecolor="none",
        )
    ax.set_xticks(x_base)
    ax.set_xticklabels(labels, rotation=30 if max(len(s) for s in labels) > 4 else 0, ha="right")
    ax.legend(loc="upper right", frameon=False, fontsize=9)
    cc.format_yaxis_si(ax)
    apply_title_and_subtitle(ax, intent)
    return fig


def stacked_bar_handler(intent, data: pd.DataFrame) -> Figure:
    """Stacked bar (absolute) — total + ≤ 5 components per category."""
    label_col = resolve_x(intent.x, data)
    y_cols = resolve_y(intent.y, data, label_col)
    if len(y_cols) > 5:

        # Soft warning via subtitle: stacking > 5 segments is hard to read.
        intent.subtitle = (intent.subtitle + " · " if intent.subtitle else "") + "limited to top 5 components"
        sums = {c: float(data[c].sum()) for c in y_cols}
        keep = sorted(sums, key=lambda k: sums[k], reverse=True)[:5]
        rest = [c for c in y_cols if c not in keep]
        if rest:
            data = data.copy()
            data["Other"] = data[rest].sum(axis=1)
            y_cols = keep + ["Other"]

    labels = data[label_col].astype(str).tolist()
    n_groups = len(labels)
    x = np.arange(n_groups)

    fig, ax = cc.subplots(figsize=(8.0, 4.5))
    bottom = np.zeros(n_groups)
    for i, col in enumerate(y_cols):
        vals = data[col].astype(float).to_numpy()
        ax.bar(x, vals, bottom=bottom, label=col, color=cycle_color(i), edgecolor="none")
        bottom = bottom + vals

    ax.set_xticks(x)
    ax.set_xticklabels(labels, rotation=30 if max(len(s) for s in labels) > 4 else 0, ha="right")
    ax.legend(loc="upper right", frameon=False, fontsize=9)
    cc.format_yaxis_si(ax)
    apply_title_and_subtitle(ax, intent)
    return fig


def stacked_bar_100_handler(intent, data: pd.DataFrame) -> Figure:
    """100 % stacked bar — composition share across categories."""
    label_col = resolve_x(intent.x, data)
    y_cols = resolve_y(intent.y, data, label_col)

    pct = data[y_cols].astype(float)
    totals = pct.sum(axis=1).replace(0, np.nan)
    pct = pct.div(totals, axis=0).fillna(0) * 100.0

    labels = data[label_col].astype(str).tolist()
    n_groups = len(labels)
    x = np.arange(n_groups)

    fig, ax = cc.subplots(figsize=(8.0, 4.5))
    bottom = np.zeros(n_groups)
    for i, col in enumerate(y_cols):
        vals = pct[col].to_numpy()
        ax.bar(x, vals, bottom=bottom, label=col, color=cycle_color(i), edgecolor="none")
        bottom = bottom + vals
    ax.set_xticks(x)
    ax.set_xticklabels(labels, rotation=30 if max(len(s) for s in labels) > 4 else 0, ha="right")
    ax.set_ylim(0, 100)
    cc.format_yaxis_pct(ax, decimals=0)
    ax.legend(loc="upper right", frameon=False, fontsize=9)
    apply_title_and_subtitle(ax, intent)
    return fig


def diverging_bar_handler(intent, data: pd.DataFrame) -> Figure:
    """Diverging bar — values around zero (or any baseline)."""
    label_col = resolve_x(intent.x, data)
    y_cols = resolve_y(intent.y, data, label_col)
    value_col = y_cols[0]
    baseline = float(intent.extras.get("baseline", 0.0))

    df = data.copy()
    df["__delta"] = df[value_col].astype(float) - baseline
    df = df.sort_values("__delta", ascending=True)
    labels = df[label_col].astype(str).tolist()
    deltas = df["__delta"].to_numpy()
    gl = GAIN_LOSS[current_mode()]
    colors = [gl["gain"] if v >= 0 else gl["loss"] for v in deltas]

    fig, ax = cc.subplots(figsize=(8.0, max(4.5, 0.4 * len(labels) + 1.5)))
    y = np.arange(len(labels))
    ax.barh(y, deltas, color=colors, edgecolor="none")
    ax.axvline(0, color="#666666", linewidth=0.8)
    ax.set_yticks(y)
    ax.set_yticklabels(labels)
    ax.tick_params(axis="y", length=0)
    ax.spines["left"].set_visible(False)
    cc.format_xaxis_si(ax)
    ax.grid(axis="x", which="major")
    ax.grid(axis="y", which="major", visible=False)
    apply_title_and_subtitle(ax, intent)
    return fig


def bullet_handler(intent, data: pd.DataFrame) -> Figure:
    """Bullet chart — KPI vs target with qualitative bands.

    Expected: ``[label, actual, target]`` or extras:
      ``intent.extras = {"actual": "...", "target": "...", "bands": [low, mid]}``
    """
    if data.shape[1] < 3:
        from .timeseries import _empty_message_figure

        return _empty_message_figure(intent, "Need 3 columns: label, actual, target")
    label_col = str(data.columns[0])
    actual_col = intent.extras.get("actual") or str(data.columns[1])
    target_col = intent.extras.get("target") or str(data.columns[2])

    labels = data[label_col].astype(str).tolist()
    actual = data[actual_col].astype(float).to_numpy()
    target = data[target_col].astype(float).to_numpy()

    fig, ax = cc.subplots(figsize=(8.0, max(4.5, 0.5 * len(labels) + 1.5)))
    y = np.arange(len(labels))
    # Faint band: 0 → 1.2× target.
    ax.barh(y, target * 1.2, color="#E5E7EB", edgecolor="none", height=0.7, zorder=1)
    # Actual.
    ax.barh(y, actual, color=cycle_color(0), edgecolor="none", height=0.4, zorder=3)
    # Target marker.
    ax.scatter(target, y, marker="|", color="#1A1A1A", s=400, linewidths=2.4, zorder=4, label=target_col)

    ax.set_yticks(y)
    ax.set_yticklabels(labels)
    ax.tick_params(axis="y", length=0)
    ax.spines["left"].set_visible(False)
    cc.format_xaxis_si(ax)
    apply_title_and_subtitle(ax, intent)
    return fig
