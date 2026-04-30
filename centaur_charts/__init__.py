"""Centaur charting kit — matplotlib defaults, helpers, and routing.

Standard usage::

    import centaur_charts as cc

    cc.apply()                       # install the Centaur theme
    fig, ax = cc.subplots()          # 16:9, 200 DPI on save

    ax.plot(df.index, df["BTC"], label="BTC")
    ax.plot(df.index, df["ETH"], label="ETH")
    cc.highlight_one(ax, "ETH")
    cc.direct_label_lines(ax)
    cc.format_yaxis_dollars(ax)
    cc.subtitle_title(ax, "ETH led BTC by 38% YTD",
                      subtitle="Indexed price, 1 Jan 2026 = 100")
    cc.source_line(fig, "Source: CoinGecko · 30 Apr 2026")
    cc.save(fig, "out.png")

The package's job is to make the *default* chart an expert chart — every fact
inside a Slack mobile preview, no hover required, brand-aware colours, sane
DPI, sentence-case takeaway titles.
"""

from .helpers import (
    annotate_recession,
    despine,
    direct_label_lines,
    format_xaxis_si,
    format_yaxis_dollars,
    format_yaxis_pct,
    format_yaxis_si,
    highlight_one,
    save,
    save_to_bytes,
    source_line,
    subplots,
    subtitle_title,
    with_focus,
)
from .style import (
    GAIN_LOSS,
    GREY_MUTED,
    HIGHLIGHT,
    OKABE_ITO,
    OKABE_ITO_DARK,
    ThemeMode,
    apply,
    current_mode,
    get_palette,
    set_mode,
)
from .router import ChartArtifact, ChartIntent, chart_router

__all__ = [
    # theme
    "apply",
    "set_mode",
    "current_mode",
    "ThemeMode",
    "get_palette",
    # palettes
    "OKABE_ITO",
    "OKABE_ITO_DARK",
    "HIGHLIGHT",
    "GREY_MUTED",
    "GAIN_LOSS",
    # helpers
    "subplots",
    "subtitle_title",
    "source_line",
    "despine",
    "direct_label_lines",
    "highlight_one",
    "with_focus",
    "format_yaxis_si",
    "format_xaxis_si",
    "format_yaxis_pct",
    "format_yaxis_dollars",
    "annotate_recession",
    "save",
    "save_to_bytes",
    # router
    "chart_router",
    "ChartIntent",
    "ChartArtifact",
]

__version__ = "0.1.0"
