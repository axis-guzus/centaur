"""Centaur charting helpers — opinionated wrappers around matplotlib.

Every helper either applies one of the visual-signature rules directly
(sentence-case titles, direct labels, source line, source/grey opacity layering)
or hides a piece of matplotlib boilerplate that LLMs reliably forget
(`bbox_inches='tight'`, `plt.close(fig)` after save, SI-suffix tick formatters).

Convention: every helper takes the matplotlib object as its first arg, returns
nothing. They mutate in place.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Iterable

import matplotlib as mpl
import matplotlib.pyplot as plt
import matplotlib.ticker as mticker
from matplotlib.axes import Axes
from matplotlib.figure import Figure

from .style import (
    GREY_MUTED,
    HIGHLIGHT,
    ThemeMode,
    apply as _apply_theme,
    current_mode,
)


# ── Figure construction ─────────────────────────────────────────────────────


def subplots(
    figsize: tuple[float, float] = (8.0, 4.5),
    *,
    nrows: int = 1,
    ncols: int = 1,
    sharex: bool = False,
    sharey: bool = False,
    **kwargs: Any,
) -> tuple[Figure, Any]:
    """Create a figure with the Centaur theme applied.

    Always re-applies the theme so callers don't have to remember; cheap
    (it's just a dict update on rcParams).
    """
    _apply_theme(current_mode())
    fig, ax = plt.subplots(
        nrows=nrows,
        ncols=ncols,
        figsize=figsize,
        sharex=sharex,
        sharey=sharey,
        **kwargs,
    )
    return fig, ax


# ── Titles & source attribution ─────────────────────────────────────────────


def subtitle_title(ax: Axes, title: str, *, subtitle: str | None = None) -> None:
    """Set a sentence-case takeaway title with optional muted subtitle.

    Example::

        cc.subtitle_title(
            ax,
            "ETH outperformed BTC by 38% YTD",
            subtitle="Indexed price, 1 Jan 2026 = 100",
        )
    """
    ax.set_title(title, loc="left", fontweight=600, pad=12)
    if subtitle:
        sub_color = "#A0A0A0" if current_mode() == ThemeMode.DARK else "#666666"
        ax.text(
            0.0,
            1.02,
            subtitle,
            transform=ax.transAxes,
            ha="left",
            va="bottom",
            fontsize=10,
            color=sub_color,
        )


def source_line(fig: Figure, source: str) -> None:
    """Add a "Source: …" line in the bottom-left of the figure.

    The text is muted gray (#7A7A7A on light, #8A8A8A on dark) at 8.5 pt — small
    enough to recede, large enough to read on Slack mobile after downsampling.
    """
    color = "#8A8A8A" if current_mode() == ThemeMode.DARK else "#7A7A7A"
    fig.text(
        0.01,
        0.005,
        source,
        ha="left",
        va="bottom",
        fontsize=8.5,
        color=color,
    )


# ── Spines & gridlines ──────────────────────────────────────────────────────


def despine(ax: Axes, *, all: bool = False) -> None:
    """Remove top/right spines (default Tufte minimum)."""
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    if all:
        for s in ax.spines.values():
            s.set_visible(False)
        ax.set_xticks([])
        ax.set_yticks([])
        ax.grid(False)


# ── Direct labels & highlight-and-grey ──────────────────────────────────────


def direct_label_lines(
    ax: Axes,
    *,
    fontsize: float = 10.0,
    weight: int = 600,
    pad_em: float = 0.4,
) -> None:
    """Replace the legend with end-of-line labels coloured to match each line.

    Use whenever there are ≤ 4 series. The visual signature: line colour = label
    colour, semibold, ~0.4 em right of the line's last x.
    """
    if ax.get_legend() is not None:
        ax.get_legend().remove()
    xmin, xmax = ax.get_xlim()
    width = xmax - xmin
    pad_x = width * pad_em / 100.0
    for line in ax.get_lines():
        label = line.get_label()
        if not label or label.startswith("_"):
            continue
        xs = line.get_xdata()
        ys = line.get_ydata()
        if len(xs) == 0:
            continue
        ax.annotate(
            label,
            xy=(xs[-1], ys[-1]),
            xytext=(pad_x, 0),
            textcoords="offset points",
            color=line.get_color(),
            fontsize=fontsize,
            fontweight=weight,
            va="center",
            ha="left",
            annotation_clip=False,
        )


def highlight_one(
    ax: Axes,
    label: str,
    *,
    color: str | None = None,
    grey: str | None = None,
    lw_focus: float = 2.6,
    lw_grey: float = 1.0,
) -> None:
    """Highlight one line by label; mute every other line in the axes.

    Cheapest meaningful upgrade for any chart with > 2 series: turns a "data
    dump" into a "story". The protagonist colour defaults to the mode-aware
    Centaur primary; muted lines fall back to a cool gray.
    """
    if color is None:
        color = HIGHLIGHT[current_mode()]
    if grey is None:
        grey = GREY_MUTED[current_mode()]
    for line in ax.get_lines():
        if line.get_label() == label:
            line.set_color(color)
            line.set_linewidth(lw_focus)
            line.set_zorder(10)
            line.set_alpha(1.0)
        else:
            line.set_color(grey)
            line.set_linewidth(lw_grey)
            line.set_alpha(0.85)


def with_focus(
    ax: Axes,
    *,
    primary: float = 1.0,
    context: float = 0.4,
    structural: float = 0.15,
) -> None:
    """Apply Manim-style opacity layering across the whole axes.

    Lines at the highest z-order render at ``primary``; everything else at
    ``context``; spines and gridlines at ``structural``. Pairs nicely with
    :func:`highlight_one` (which sets z-order on the protagonist).
    """
    children = ax.get_lines()
    if children:
        zmax = max(line.get_zorder() for line in children)
        for line in children:
            line.set_alpha(primary if line.get_zorder() == zmax else context)
    for spine in ax.spines.values():
        spine.set_alpha(structural)
    ax.grid(True, alpha=structural)


# ── Axis formatters ─────────────────────────────────────────────────────────


def _si_format(value: float, _pos: int | None = None) -> str:
    """Format a number with SI suffix: 1.2k / 3.4M / 5.6B / 7.8T."""
    abs_val = abs(value)
    if abs_val < 1_000:
        # Avoid trailing ".0" for integers; keep 1 dp for floats.
        return f"{value:.0f}" if abs_val == int(abs_val) else f"{value:.2f}"
    if abs_val < 1_000_000:
        return f"{value / 1_000:.1f}k"
    if abs_val < 1_000_000_000:
        return f"{value / 1_000_000:.1f}M"
    if abs_val < 1_000_000_000_000:
        return f"{value / 1_000_000_000:.1f}B"
    return f"{value / 1_000_000_000_000:.1f}T"


def format_yaxis_si(ax: Axes) -> None:
    """Format the y-axis with SI suffixes (1.2k, 3.4M, …)."""
    ax.yaxis.set_major_formatter(mticker.FuncFormatter(_si_format))


def format_xaxis_si(ax: Axes) -> None:
    """Format the x-axis with SI suffixes."""
    ax.xaxis.set_major_formatter(mticker.FuncFormatter(_si_format))


def format_yaxis_pct(ax: Axes, *, decimals: int = 1, signed: bool = False) -> None:
    """Format the y-axis as a percentage. ``signed=True`` adds a leading ``+``."""
    fmt = f"{{x:+.{decimals}f}}%" if signed else f"{{x:.{decimals}f}}%"
    ax.yaxis.set_major_formatter(mticker.StrMethodFormatter(fmt))


def format_yaxis_dollars(ax: Axes) -> None:
    """Format the y-axis as a dollar amount with SI suffix ($1.2k, $3.4M, …)."""

    def _fmt(v: float, _pos: int | None = None) -> str:
        return "$" + _si_format(v, _pos)

    ax.yaxis.set_major_formatter(mticker.FuncFormatter(_fmt))


# ── Annotations ─────────────────────────────────────────────────────────────


def annotate_recession(
    ax: Axes,
    spans: Iterable[tuple],
    *,
    color: str | None = None,
    alpha: float = 0.4,
    label: str | None = None,
) -> None:
    """Shade vertical bands at each ``(start, end)`` tuple.

    The "FRED recession band" primitive — repurposable for crypto winters,
    fork windows, FOMC meetings, ETF approval gates, exchange collapses, etc.
    """
    if color is None:
        color = "#3A3A3A" if current_mode() == ThemeMode.DARK else "#E5E5E5"
    spans = list(spans)
    for x0, x1 in spans:
        ax.axvspan(x0, x1, color=color, alpha=alpha, lw=0, zorder=0)
    if label and spans:
        x0 = spans[0][0]
        ax.annotate(
            label,
            xy=(x0, 1.0),
            xycoords=("data", "axes fraction"),
            xytext=(0, 4),
            textcoords="offset points",
            ha="left",
            va="bottom",
            color="#666666",
            fontsize=9,
        )


# ── Save ────────────────────────────────────────────────────────────────────


def save(
    fig: Figure,
    path: str | Path,
    *,
    dpi: int = 200,
    facecolor: str | None = None,
    bbox_inches: str = "tight",
    pad_inches: float = 0.25,
    metadata: dict[str, str] | None = None,
    close: bool = True,
) -> Path:
    """Save a figure with Centaur defaults and (by default) close it.

    Closing is essential in long-running workers — without it, figures
    accumulate at ~5 MB each and the process OOMs after ~100 charts.
    """
    if facecolor is None:
        facecolor = mpl.rcParams.get("savefig.facecolor", "white")
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(
        p,
        dpi=dpi,
        facecolor=facecolor,
        bbox_inches=bbox_inches,
        pad_inches=pad_inches,
        metadata=metadata or {},
    )
    if close:
        plt.close(fig)
    return p


def save_to_bytes(
    fig: Figure,
    *,
    dpi: int = 200,
    facecolor: str | None = None,
    bbox_inches: str = "tight",
    pad_inches: float = 0.25,
    fmt: str = "png",
    close: bool = True,
) -> bytes:
    """Render a figure to PNG/SVG bytes (no filesystem)."""
    import io

    if facecolor is None:
        facecolor = mpl.rcParams.get("savefig.facecolor", "white")
    buf = io.BytesIO()
    fig.savefig(
        buf,
        format=fmt,
        dpi=dpi,
        facecolor=facecolor,
        bbox_inches=bbox_inches,
        pad_inches=pad_inches,
    )
    if close:
        plt.close(fig)
    return buf.getvalue()
