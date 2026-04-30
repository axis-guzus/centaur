"""Distribution / density / range handlers."""

from __future__ import annotations

import numpy as np
import pandas as pd
from matplotlib.figure import Figure

from .. import helpers as cc
from ..style import HIGHLIGHT, current_mode
from ._common import apply_title_and_subtitle


def histogram_handler(intent, data: pd.DataFrame) -> Figure:
    """Histogram of a single numeric column."""
    col = intent.y if isinstance(intent.y, str) else str(data.select_dtypes(include="number").columns[0])
    values = data[col].dropna().astype(float).to_numpy()
    bins = int(intent.extras.get("bins", min(50, max(10, int(np.sqrt(len(values)))))))

    fig, ax = cc.subplots(figsize=(8.0, 4.5))
    ax.hist(values, bins=bins, color=HIGHLIGHT[current_mode()], edgecolor="white", linewidth=0.5)
    median = float(np.median(values))
    ax.axvline(median, color="#666666", linewidth=1.0, linestyle="--", zorder=5)
    ax.text(
        median,
        ax.get_ylim()[1] * 0.95,
        f"median {median:.2f}",
        ha="left",
        va="top",
        color="#666666",
        fontsize=9,
        rotation=0,
    )
    cc.format_yaxis_si(ax)
    apply_title_and_subtitle(ax, intent)
    return fig


def kde_handler(intent, data: pd.DataFrame) -> Figure:
    """Kernel density estimate (smooth histogram). Falls back to histogram if scipy is unavailable."""
    col = intent.y if isinstance(intent.y, str) else str(data.select_dtypes(include="number").columns[0])
    values = data[col].dropna().astype(float).to_numpy()
    try:
        from scipy.stats import gaussian_kde

        kde = gaussian_kde(values)
        xs = np.linspace(values.min(), values.max(), 256)
        ys = kde(xs)
        fig, ax = cc.subplots(figsize=(8.0, 4.5))
        ax.fill_between(xs, ys, color=HIGHLIGHT[current_mode()], alpha=0.2)
        ax.plot(xs, ys, color=HIGHLIGHT[current_mode()], linewidth=2.0)
        cc.format_yaxis_si(ax)
        apply_title_and_subtitle(ax, intent)
        return fig
    except ImportError:
        return histogram_handler(intent, data)


def box_handler(intent, data: pd.DataFrame) -> Figure:
    """Box plot — compare distributions across groups.

    Expected shape: a ``group`` column + a ``value`` column. Falls back to a
    single box of the first numeric column if no group is provided.
    """
    if data.shape[1] >= 2 and not pd.api.types.is_numeric_dtype(data.iloc[:, 0]):
        group_col = str(data.columns[0])
        value_col = intent.y if isinstance(intent.y, str) else str(data.select_dtypes(include="number").columns[0])
        groups = data.groupby(group_col, sort=False)
        labels = [str(g) for g, _ in groups]
        series = [g[1][value_col].dropna().astype(float).to_numpy() for g in groups]
    else:
        col = intent.y if isinstance(intent.y, str) else str(data.select_dtypes(include="number").columns[0])
        labels = [col]
        series = [data[col].dropna().astype(float).to_numpy()]

    fig, ax = cc.subplots(figsize=(8.0, 4.5))
    bp = ax.boxplot(
        series,
        labels=labels,
        patch_artist=True,
        widths=0.6,
        medianprops={"color": "#D55E00", "linewidth": 1.6},
        flierprops={"marker": "o", "markersize": 3, "markerfacecolor": "#888888", "markeredgecolor": "#888888"},
    )
    for patch, _label in zip(bp["boxes"], labels):  # noqa: B905
        patch.set_facecolor("#C8CDD3")
        patch.set_edgecolor("#333333")
    cc.format_yaxis_si(ax)
    apply_title_and_subtitle(ax, intent)
    return fig


def violin_handler(intent, data: pd.DataFrame) -> Figure:
    """Violin plot. Falls back to box if seaborn isn't available."""
    try:
        import seaborn as sns

        if data.shape[1] >= 2 and not pd.api.types.is_numeric_dtype(data.iloc[:, 0]):
            group_col = str(data.columns[0])
            value_col = intent.y if isinstance(intent.y, str) else str(data.select_dtypes(include="number").columns[0])
            fig, ax = cc.subplots(figsize=(8.0, 4.5))
            sns.violinplot(data=data, x=group_col, y=value_col, ax=ax, inner="quartile", color=HIGHLIGHT[current_mode()])
            cc.format_yaxis_si(ax)
            apply_title_and_subtitle(ax, intent)
            return fig
    except ImportError:
        pass
    return box_handler(intent, data)


def ridgeline_handler(intent, data: pd.DataFrame) -> Figure:
    """Ridgeline / joy plot. Best > 6 ordered groups. Falls back to box otherwise."""
    try:
        import joypy  # type: ignore[import-not-found]

        if data.shape[1] >= 2:
            group_col = str(data.columns[0])
            value_col = intent.y if isinstance(intent.y, str) else str(data.select_dtypes(include="number").columns[0])
            fig, _axes = joypy.joyplot(
                data,
                by=group_col,
                column=value_col,
                colormap=None,
                figsize=(8.0, max(4.5, 0.45 * data[group_col].nunique() + 1.5)),
                fade=True,
                overlap=0.6,
                grid=False,
                linecolor="#333333",
            )
            apply_title_and_subtitle(fig.axes[0], intent)
            return fig
    except ImportError:
        pass
    return box_handler(intent, data)


def ecdf_handler(intent, data: pd.DataFrame) -> Figure:
    """Empirical CDF — best for percentile / inequality questions."""
    col = intent.y if isinstance(intent.y, str) else str(data.select_dtypes(include="number").columns[0])
    values = np.sort(data[col].dropna().astype(float).to_numpy())
    n = len(values)
    fig, ax = cc.subplots(figsize=(8.0, 4.5))
    ax.plot(values, np.arange(1, n + 1) / n * 100, color=HIGHLIGHT[current_mode()], linewidth=2.0)
    ax.set_ylim(0, 100)
    cc.format_yaxis_pct(ax, decimals=0)
    apply_title_and_subtitle(ax, intent)
    return fig


def lorenz_handler(intent, data: pd.DataFrame) -> Figure:
    """Lorenz curve + Gini in subtitle. For concentration / inequality."""
    col = intent.y if isinstance(intent.y, str) else str(data.select_dtypes(include="number").columns[0])
    values = data[col].dropna().astype(float).sort_values().to_numpy()
    n = len(values)
    if n == 0:
        from .timeseries import _empty_message_figure

        return _empty_message_figure(intent, "No data")
    cum = np.insert(np.cumsum(values) / values.sum(), 0, 0)
    x = np.linspace(0, 1, n + 1)
    # Gini = 1 - 2 * area-under-Lorenz
    gini = 1.0 - 2.0 * np.trapz(cum, x)

    fig, ax = cc.subplots(figsize=(8.0, 4.5))
    ax.plot(x * 100, cum * 100, color=HIGHLIGHT[current_mode()], linewidth=2.0, zorder=10)
    ax.plot([0, 100], [0, 100], color="#888888", linewidth=0.8, linestyle="--", zorder=5)
    ax.fill_between(x * 100, cum * 100, x * 100, color=HIGHLIGHT[current_mode()], alpha=0.15, zorder=2)
    ax.set_xlabel("Cumulative population (%)")
    ax.set_ylabel("Cumulative share (%)")
    ax.set_xlim(0, 100)
    ax.set_ylim(0, 100)
    intent.subtitle = (intent.subtitle or "") + (f" · Gini = {gini:.3f}" if intent.subtitle else f"Gini = {gini:.3f}")
    apply_title_and_subtitle(ax, intent)
    return fig
