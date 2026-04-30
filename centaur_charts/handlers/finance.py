"""Finance / crypto chart handlers — candle, drawdown, returns, risk-return."""

from __future__ import annotations

import numpy as np
import pandas as pd
from matplotlib.figure import Figure

from .. import helpers as cc
from ..crypto import color_for, palette_for
from ..style import GAIN_LOSS, GREY_MUTED, HIGHLIGHT, current_mode
from ._common import (
    apply_title_and_subtitle,
    is_datelike,
    maybe_dates,
    resolve_x,
    resolve_y,
    setup_date_axis,
)


def candlestick_handler(intent, data: pd.DataFrame) -> Figure:
    """Candle + volume two-panel. Expects: date, open, high, low, close, volume?"""
    required = {"open", "high", "low", "close"}
    cols_lower = {c.lower(): c for c in data.columns}
    if not required.issubset(cols_lower.keys()):
        from .timeseries import _empty_message_figure

        return _empty_message_figure(intent, "Need columns: open, high, low, close (volume optional)")
    o, h, low_col, c = (cols_lower[k] for k in ("open", "high", "low", "close"))
    date_col = intent.x or (cols_lower.get("date") or str(data.columns[0]))
    has_volume = "volume" in cols_lower

    df = data.copy()
    df[date_col] = maybe_dates(df[date_col])
    n = len(df)
    x = np.arange(n)
    opens = df[o].astype(float).to_numpy()
    highs = df[h].astype(float).to_numpy()
    lows = df[low_col].astype(float).to_numpy()
    closes = df[c].astype(float).to_numpy()

    gl = GAIN_LOSS[current_mode()]
    gain, loss = gl["gain"], gl["loss"]

    if has_volume:
        import matplotlib.gridspec as gridspec

        fig = (
            __import__("matplotlib.pyplot", fromlist=["figure"]).figure(figsize=(8.0, 5.5))
        )
        gs = gridspec.GridSpec(2, 1, height_ratios=[3, 1], hspace=0.05)
        ax = fig.add_subplot(gs[0])
        vol_ax = fig.add_subplot(gs[1], sharex=ax)
        # Re-apply theme to fig manually since we didn't go through cc.subplots
        cc.subplots(figsize=(0.1, 0.1))[1].figure.clf()
    else:
        fig, ax = cc.subplots(figsize=(8.0, 4.5))
        vol_ax = None

    body_w = 0.7
    from matplotlib.patches import Rectangle

    for i in range(n):
        col = gain if closes[i] >= opens[i] else loss
        ax.plot([x[i], x[i]], [lows[i], highs[i]], color=col, linewidth=0.9, zorder=2)
        top = max(opens[i], closes[i])
        bot = min(opens[i], closes[i])
        height = max(top - bot, (highs.max() - lows.min()) * 0.001)
        ax.add_patch(Rectangle((x[i] - body_w / 2, bot), body_w, height, facecolor=col, edgecolor="none", zorder=3))

    if vol_ax is not None:
        vols = df[cols_lower["volume"]].astype(float).to_numpy()
        vol_colors = [gain if closes[i] >= opens[i] else loss for i in range(n)]
        vol_ax.bar(x, vols, color=vol_colors, alpha=0.7, edgecolor="none")
        cc.format_yaxis_si(vol_ax)
        vol_ax.set_ylabel("Volume", fontsize=9, color="#666666")
        vol_ax.tick_params(axis="x", labelbottom=False)
        for s in ("top", "right"):
            vol_ax.spines[s].set_visible(False)

    cc.format_yaxis_dollars(ax)
    # x-axis labels on bottom-most axis
    bottom_ax = vol_ax or ax
    step = max(n // 6, 1)
    tick_idx = list(range(0, n, step))
    if tick_idx and tick_idx[-1] != n - 1:
        tick_idx.append(n - 1)
    bottom_ax.set_xticks(tick_idx)
    bottom_ax.set_xticklabels([str(df[date_col].iloc[i])[:10] for i in tick_idx], rotation=0)
    bottom_ax.set_xlim(-0.5, n - 0.5)
    apply_title_and_subtitle(ax, intent)
    return fig


def drawdown_handler(intent, data: pd.DataFrame) -> Figure:
    """Underwater equity curve — drawdown from running peak."""
    x_col = resolve_x(intent.x, data)
    y_cols = resolve_y(intent.y, data, x_col)
    value_col = y_cols[0]
    x = maybe_dates(data[x_col])
    v = data[value_col].astype(float).to_numpy()
    peak = np.maximum.accumulate(v)
    dd = (v - peak) / peak  # negative percentage
    gl = GAIN_LOSS[current_mode()]
    fig, ax = cc.subplots(figsize=(8.0, 4.5))
    ax.fill_between(x, dd * 100, 0, color=gl["loss"], alpha=0.35, zorder=3)
    ax.plot(x, dd * 100, color=gl["loss"], linewidth=1.6, zorder=4)
    ax.axhline(0, color="#666666", linewidth=0.8, zorder=5)
    cc.format_yaxis_pct(ax, decimals=0)
    if is_datelike(x):
        setup_date_axis(ax)
    max_dd = float(dd.min()) * 100 if len(dd) else 0.0
    intent.subtitle = (intent.subtitle or "") + (f" · max DD {max_dd:.1f}%" if intent.subtitle else f"max DD {max_dd:.1f}%")
    apply_title_and_subtitle(ax, intent)
    return fig


def cumulative_returns_handler(intent, data: pd.DataFrame) -> Figure:
    """Cumulative returns — indexed line of (1 + r).cumprod() - 1."""
    x_col = resolve_x(intent.x, data)
    y_cols = resolve_y(intent.y, data, x_col)
    x = maybe_dates(data[x_col])

    fig, ax = cc.subplots(figsize=(8.0, 4.5))
    for i, col in enumerate(y_cols):
        r = data[col].astype(float).to_numpy()
        cum = (1.0 + r).cumprod() - 1.0
        ax.plot(x, cum * 100, color=color_for(col) or HIGHLIGHT[current_mode()], linewidth=2.0, label=col)
    ax.axhline(0, color=GREY_MUTED[current_mode()], linewidth=0.8, linestyle="--", zorder=0)
    cc.format_yaxis_pct(ax, signed=True, decimals=0)
    if is_datelike(x):
        setup_date_axis(ax)
    cc.direct_label_lines(ax)
    apply_title_and_subtitle(ax, intent)
    return fig


def returns_histogram_handler(intent, data: pd.DataFrame) -> Figure:
    """Histogram of returns + median annotation."""
    col = intent.y if isinstance(intent.y, str) else str(data.select_dtypes(include="number").columns[0])
    r = data[col].dropna().astype(float).to_numpy() * 100
    bins = int(intent.extras.get("bins", min(80, max(20, int(np.sqrt(len(r)))))))
    fig, ax = cc.subplots(figsize=(8.0, 4.5))
    ax.hist(r, bins=bins, color=HIGHLIGHT[current_mode()], edgecolor="white", linewidth=0.5)
    median = float(np.median(r))
    ax.axvline(median, color="#666666", linewidth=1.0, linestyle="--")
    ax.set_xlabel("Return (%)")
    cc.format_yaxis_si(ax)
    apply_title_and_subtitle(ax, intent)
    return fig


def risk_return_handler(intent, data: pd.DataFrame) -> Figure:
    """Risk-return scatter — annualized vol on x, annualized return on y.

    Expected columns: ``[label, vol, ret]`` (any names; first 3 cols).
    """
    if data.shape[1] < 3:
        from .timeseries import _empty_message_figure

        return _empty_message_figure(intent, "Need columns: label, vol, return")
    label_col, vol_col, ret_col = data.columns[:3]
    labels = data[label_col].astype(str).tolist()
    vols = data[vol_col].astype(float).to_numpy() * 100
    rets = data[ret_col].astype(float).to_numpy() * 100
    colors = palette_for(labels)
    fig, ax = cc.subplots(figsize=(8.0, 4.5))
    ax.scatter(vols, rets, color=colors, s=120, edgecolors="white", linewidths=0.6, zorder=10)
    for label_, x_, y_ in zip(labels, vols, rets):  # noqa: B905
        ax.annotate(label_, (x_, y_), xytext=(5, 5), textcoords="offset points", fontsize=9, fontweight=600)
    ax.axhline(0, color="#666666", linewidth=0.8)
    ax.set_xlabel("Annualized vol (%)")
    ax.set_ylabel("Annualized return (%)")
    cc.format_xaxis_si(ax)
    cc.format_yaxis_pct(ax, signed=True, decimals=0)
    apply_title_and_subtitle(ax, intent)
    return fig


def rolling_stat_handler(intent, data: pd.DataFrame) -> Figure:
    """Rolling statistic — typically rolling vol/Sharpe/correlation over time."""
    x_col = resolve_x(intent.x, data)
    y_cols = resolve_y(intent.y, data, x_col)
    window = int(intent.extras.get("window", 30))
    x = maybe_dates(data[x_col])
    fig, ax = cc.subplots(figsize=(8.0, 4.5))
    for i, col in enumerate(y_cols):
        rolled = data[col].astype(float).rolling(window).mean().to_numpy()
        ax.plot(x, rolled, color=color_for(col) or HIGHLIGHT[current_mode()], linewidth=2.0, label=col)
    if is_datelike(x):
        setup_date_axis(ax)
    cc.format_yaxis_si(ax)
    cc.direct_label_lines(ax)
    apply_title_and_subtitle(ax, intent)
    return fig
