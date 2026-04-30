"""Scatter / bubble / hexbin / correlation-heatmap handlers."""

from __future__ import annotations

import numpy as np
import pandas as pd
from matplotlib.figure import Figure

from .. import helpers as cc
from ..style import HIGHLIGHT, current_mode
from ._common import apply_title_and_subtitle, color_for_label, resolve_x, resolve_y


def scatter_handler(intent, data: pd.DataFrame) -> Figure:
    """Scatter of two numeric columns + optional regression line."""
    x_col = resolve_x(intent.x, data)
    y_cols = resolve_y(intent.y, data, x_col)
    y_col = y_cols[0]
    x = data[x_col].astype(float).to_numpy()
    y = data[y_col].astype(float).to_numpy()
    color = color_for_label(intent.protagonist or y_col)

    fig, ax = cc.subplots(figsize=(8.0, 4.5))
    ax.scatter(x, y, color=color, s=30, alpha=0.6, edgecolors="none", zorder=10)
    if len(x) > 1:
        z = np.polyfit(x, y, 1)
        p = np.poly1d(z)
        x_line = np.linspace(np.nanmin(x), np.nanmax(x), 100)
        ax.plot(x_line, p(x_line), color="#888888", linewidth=1.4, linestyle="--", zorder=11)
    ax.set_xlabel(x_col)
    ax.set_ylabel(y_col)
    cc.format_xaxis_si(ax)
    cc.format_yaxis_si(ax)
    apply_title_and_subtitle(ax, intent)
    return fig


def bubble_handler(intent, data: pd.DataFrame) -> Figure:
    """Scatter + size dimension. Expects ≥ 3 numeric columns: x, y, size."""
    if data.select_dtypes(include="number").shape[1] < 3:
        from .timeseries import _empty_message_figure

        return _empty_message_figure(intent, "Need ≥ 3 numeric columns: x, y, size")
    num_cols = list(data.select_dtypes(include="number").columns)
    x_col = intent.x if isinstance(intent.x, str) and intent.x in num_cols else num_cols[0]
    y_col = (intent.y if isinstance(intent.y, str) and intent.y in num_cols else num_cols[1])
    size_col = intent.extras.get("size", num_cols[2])

    x = data[x_col].astype(float).to_numpy()
    y = data[y_col].astype(float).to_numpy()
    s_raw = data[size_col].astype(float).to_numpy()
    s_norm = (s_raw - np.nanmin(s_raw)) / (np.nanmax(s_raw) - np.nanmin(s_raw) + 1e-9)
    sizes = 30 + s_norm * 800

    fig, ax = cc.subplots(figsize=(8.0, 4.5))
    ax.scatter(
        x,
        y,
        s=sizes,
        color=HIGHLIGHT[current_mode()],
        alpha=0.55,
        edgecolors="white",
        linewidths=0.6,
        zorder=10,
    )
    ax.set_xlabel(x_col)
    ax.set_ylabel(y_col)
    cc.format_xaxis_si(ax)
    cc.format_yaxis_si(ax)
    apply_title_and_subtitle(ax, intent)
    return fig


def hexbin_handler(intent, data: pd.DataFrame) -> Figure:
    """Hexbin density. Use when scatter would overplot (n > ~5k)."""
    x_col = resolve_x(intent.x, data)
    y_cols = resolve_y(intent.y, data, x_col)
    y_col = y_cols[0]

    fig, ax = cc.subplots(figsize=(8.0, 4.5))
    hb = ax.hexbin(
        data[x_col].astype(float),
        data[y_col].astype(float),
        gridsize=int(intent.extras.get("gridsize", 30)),
        cmap="viridis",
        mincnt=1,
    )
    cb = fig.colorbar(hb, ax=ax)
    cb.set_label("Count", fontsize=9)
    ax.set_xlabel(x_col)
    ax.set_ylabel(y_col)
    apply_title_and_subtitle(ax, intent)
    return fig


def correlation_heatmap_handler(intent, data: pd.DataFrame) -> Figure:
    """Pairwise correlation heatmap, diverging RdBu_r symmetric around 0."""
    numeric = data.select_dtypes(include="number")
    if numeric.shape[1] < 2:
        from .timeseries import _empty_message_figure

        return _empty_message_figure(intent, "Need ≥ 2 numeric columns")
    corr = numeric.corr()

    fig, ax = cc.subplots(figsize=(8.0, max(4.5, 0.4 * len(corr.columns) + 2.5)))
    im = ax.imshow(corr.values, cmap="RdBu_r", vmin=-1, vmax=1, aspect="auto")
    ax.set_xticks(range(len(corr.columns)))
    ax.set_yticks(range(len(corr.columns)))
    ax.set_xticklabels(corr.columns, rotation=30, ha="right")
    ax.set_yticklabels(corr.columns)
    # Annotate cells with values when matrix is small.
    if len(corr.columns) <= 12:
        for i in range(len(corr.columns)):
            for j in range(len(corr.columns)):
                v = corr.iat[i, j]
                ax.text(
                    j,
                    i,
                    f"{v:.2f}",
                    ha="center",
                    va="center",
                    color="white" if abs(v) > 0.5 else "#333333",
                    fontsize=8,
                )
    cb = fig.colorbar(im, ax=ax, ticks=[-1, -0.5, 0, 0.5, 1])
    cb.ax.tick_params(labelsize=9)
    apply_title_and_subtitle(ax, intent)
    ax.grid(False)
    return fig


def connected_scatter_handler(intent, data: pd.DataFrame) -> Figure:
    """Connected scatter — two paired time series with explicit progression."""
    x_col = resolve_x(intent.x, data)
    y_cols = resolve_y(intent.y, data, x_col)
    if len(y_cols) < 2:
        from .timeseries import _empty_message_figure

        return _empty_message_figure(intent, "Need 2 numeric columns")
    y1, y2 = y_cols[0], y_cols[1]
    x = data[y1].astype(float).to_numpy()
    y = data[y2].astype(float).to_numpy()
    fig, ax = cc.subplots(figsize=(8.0, 4.5))
    ax.plot(x, y, color="#888888", linewidth=1.0, zorder=2)
    ax.scatter(x, y, color=HIGHLIGHT[current_mode()], s=40, edgecolors="white", linewidths=0.6, zorder=10)
    # Annotate first/last points with the x-column label (often a date).
    label_col = x_col
    for idx in [0, len(x) - 1]:
        ax.annotate(
            str(data[label_col].iloc[idx]),
            xy=(x[idx], y[idx]),
            xytext=(6, 4),
            textcoords="offset points",
            fontsize=9,
            fontweight=600,
        )
    ax.set_xlabel(y1)
    ax.set_ylabel(y2)
    cc.format_xaxis_si(ax)
    cc.format_yaxis_si(ax)
    apply_title_and_subtitle(ax, intent)
    return fig
