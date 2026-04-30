"""Centaur chart theme — rcParams + palettes.

The defaults here are tuned for Slack-mobile readability: 16:9 figsize, 200 DPI
on export, sans-serif sentence-case titles flush left, no top/right spines,
horizontal-only gridlines, Okabe-Ito categorical palette (colorblind-safe),
viridis sequential, RdBu_r diverging.

Three modes ship out of the box:
    - ``light``     — cool near-white background (#F8F9FA), the default.
    - ``dark``      — near-black with a hint of blue (#0F1115); brightened cycle.
    - ``editorial`` — off-white (#F5F4F0) with a serif title for long-form work.

Apply once per script; the Centaur charting skill calls :func:`apply` for you.
"""

from __future__ import annotations

from collections.abc import Callable
from enum import Enum

import matplotlib as mpl


class ThemeMode(str, Enum):
    """Supported visual modes."""

    LIGHT = "light"
    DARK = "dark"
    EDITORIAL = "editorial"


# ── Palettes ────────────────────────────────────────────────────────────────

# Okabe-Ito (Wong, 2011) — colorblind-safe categorical default.
OKABE_ITO: tuple[str, ...] = (
    "#0072B2",  # blue
    "#D55E00",  # vermilion
    "#009E73",  # bluish green
    "#CC79A7",  # reddish purple
    "#F0E442",  # yellow
    "#56B4E9",  # sky blue
    "#E69F00",  # orange
    "#000000",  # black
)

# Brightened variant for dark mode — sky-blue-led, Bloomberg-amber accent.
OKABE_ITO_DARK: tuple[str, ...] = (
    "#56B4E9",
    "#FFA028",
    "#14F195",
    "#CC79A7",
    "#F0E442",
    "#E69F00",
    "#D55E00",
    "#F0F0F0",
)

# The single "highlight" colors used by helpers.highlight_one when callers
# don't pass an explicit color: brand-anchor blue (light) / sky-blue (dark).
HIGHLIGHT = {
    ThemeMode.LIGHT: "#0072B2",
    ThemeMode.DARK: "#56B4E9",
    ThemeMode.EDITORIAL: "#0F5499",  # FT-deep-blue
}

# "Cool gray rest" for non-protagonist series.
GREY_MUTED = {
    ThemeMode.LIGHT: "#C8CDD3",
    ThemeMode.DARK: "#4A4F55",
    ThemeMode.EDITORIAL: "#B5B0A8",
}

# Gain / loss semantic colors. Two tiers per mode: TradingView-style green/red
# (default) and a colorblind-safe blue/coral alternative.
GAIN_LOSS = {
    ThemeMode.LIGHT: {"gain": "#26A69A", "loss": "#EF5350",
                       "gain_cvd": "#118AB2", "loss_cvd": "#EF476F"},
    ThemeMode.DARK: {"gain": "#26C9B5", "loss": "#FF6B68",
                       "gain_cvd": "#56B4E9", "loss_cvd": "#FF6B6B"},
    ThemeMode.EDITORIAL: {"gain": "#2C7A7B", "loss": "#C53030",
                       "gain_cvd": "#0F5499", "loss_cvd": "#B31147"},
}


# ── rcParams ────────────────────────────────────────────────────────────────


def _light_theme() -> dict:
    return {
        # Figure & save
        "figure.figsize": (8.0, 4.5),                 # 16:9, Slack-perfect
        "figure.dpi": 150,
        "figure.facecolor": "#F8F9FA",
        "figure.edgecolor": "#F8F9FA",
        "figure.constrained_layout.use": True,
        "savefig.dpi": 200,                           # 1600×900 PNG by default
        "savefig.bbox": "tight",
        "savefig.pad_inches": 0.25,
        "savefig.facecolor": "#F8F9FA",
        "savefig.format": "png",
        "svg.fonttype": "none",                       # editable SVG text
        "pdf.fonttype": 42,                           # TrueType embedding
        "ps.fonttype": 42,
        # Fonts — Inter primary, IBM Plex Sans next, Source Sans 3 fallback,
        # then DejaVu Sans which always ships with matplotlib.
        "font.family": "sans-serif",
        "font.sans-serif": [
            "Inter",
            "IBM Plex Sans",
            "Source Sans 3",
            "Source Sans Pro",
            "DejaVu Sans",
            "Liberation Sans",
            "Helvetica",
            "Arial",
        ],
        "font.size": 11.0,
        "font.monospace": [
            "JetBrains Mono",
            "IBM Plex Mono",
            "DejaVu Sans Mono",
            "Menlo",
            "monospace",
        ],
        "mathtext.fontset": "custom",
        "mathtext.rm": "DejaVu Sans",
        "mathtext.it": "DejaVu Sans:italic",
        "mathtext.bf": "DejaVu Sans:bold",
        # Axes
        "axes.titlelocation": "left",
        "axes.titlepad": 12.0,
        "axes.titlesize": 13.0,
        "axes.titleweight": 600,
        "axes.labelpad": 6.0,
        "axes.labelsize": 10.5,
        "axes.labelcolor": "#333333",
        "axes.facecolor": "#F8F9FA",
        "axes.edgecolor": "#333333",
        "axes.linewidth": 0.8,
        "axes.spines.top": False,
        "axes.spines.right": False,
        "axes.spines.left": True,
        "axes.spines.bottom": True,
        "axes.grid": True,
        "axes.grid.axis": "y",                        # horizontal-only
        "axes.axisbelow": True,
        "axes.formatter.use_mathtext": True,
        "axes.formatter.useoffset": False,
        "axes.unicode_minus": True,
        "axes.prop_cycle": mpl.cycler("color", list(OKABE_ITO)),
        # Grid
        "grid.color": "#E5E7EB",
        "grid.linestyle": "-",
        "grid.linewidth": 0.6,
        "grid.alpha": 1.0,
        # Ticks — y-axis ticks suppressed so gridlines do the work.
        "xtick.color": "#555555",
        "xtick.labelcolor": "#333333",
        "xtick.labelsize": 9.5,
        "xtick.direction": "out",
        "xtick.major.size": 3.0,
        "xtick.major.width": 0.8,
        "xtick.minor.visible": False,
        "ytick.color": "#555555",
        "ytick.labelcolor": "#333333",
        "ytick.labelsize": 9.5,
        "ytick.direction": "out",
        "ytick.major.size": 0.0,
        "ytick.major.width": 0.0,
        "ytick.minor.visible": False,
        # Legend (rarely used — direct-labelling is the default)
        "legend.frameon": False,
        "legend.fontsize": 9.5,
        "legend.handlelength": 1.5,
        "legend.handletextpad": 0.6,
        "legend.borderpad": 0.4,
        "legend.columnspacing": 1.2,
        "legend.labelspacing": 0.5,
        # Lines / patches
        "lines.linewidth": 2.0,
        "lines.markersize": 6.0,
        "lines.solid_capstyle": "round",
        "lines.dash_capstyle": "round",
        "patch.linewidth": 0.5,
        "patch.edgecolor": "white",
        "patch.force_edgecolor": True,
        # Misc
        "errorbar.capsize": 3.0,
        "image.cmap": "viridis",
        "image.interpolation": "nearest",
        "date.autoformatter.year": "%Y",
        "date.autoformatter.month": "%b %Y",
        "date.autoformatter.day": "%d %b",
        "date.autoformatter.hour": "%H:%M",
        "date.autoformatter.minute": "%H:%M",
    }


def _dark_theme() -> dict:
    base = _light_theme()
    base.update(
        {
            "figure.facecolor": "#0F1115",
            "figure.edgecolor": "#0F1115",
            "savefig.facecolor": "#0F1115",
            "axes.facecolor": "#0F1115",
            "axes.edgecolor": "#4A4F55",
            "axes.labelcolor": "#E0E0E0",
            "text.color": "#F0F0F0",
            "xtick.color": "#8B9098",
            "ytick.color": "#8B9098",
            "xtick.labelcolor": "#C0C5CB",
            "ytick.labelcolor": "#C0C5CB",
            "grid.color": "#2D3137",
            "axes.prop_cycle": mpl.cycler("color", list(OKABE_ITO_DARK)),
            "image.cmap": "magma",
        }
    )
    return base


def _editorial_theme() -> dict:
    base = _light_theme()
    base.update(
        {
            "figure.facecolor": "#F5F4F0",
            "savefig.facecolor": "#F5F4F0",
            "axes.facecolor": "#F5F4F0",
            "font.family": "serif",
            "font.serif": [
                "Playfair Display",
                "Source Serif 4",
                "Source Serif Pro",
                "DejaVu Serif",
            ],
            "axes.titleweight": 700,
        }
    )
    return base


THEMES: dict[ThemeMode, Callable[[], dict]] = {
    ThemeMode.LIGHT: _light_theme,
    ThemeMode.DARK: _dark_theme,
    ThemeMode.EDITORIAL: _editorial_theme,
}

_current_mode: ThemeMode = ThemeMode.LIGHT


def apply(mode: ThemeMode | str = ThemeMode.LIGHT) -> None:
    """Apply the Centaur theme as the current matplotlib rcParams.

    Idempotent — call as often as you want; subsequent calls just refresh the
    current mode. The Centaur charting skill calls this for you before every
    handler, so user code rarely needs to call it directly.
    """
    global _current_mode
    if isinstance(mode, str):
        mode = ThemeMode(mode.lower())
    _current_mode = mode
    builder = THEMES[mode]
    mpl.rcParams.update(builder())


def set_mode(mode: ThemeMode | str) -> None:
    """Alias for :func:`apply` for callers who think in modes."""
    apply(mode)


def current_mode() -> ThemeMode:
    """Return the most-recently applied :class:`ThemeMode`."""
    return _current_mode


def get_palette(name: str = "categorical") -> tuple[str, ...]:
    """Return a palette by role.

    Supported names:
      - ``"categorical"`` / ``"qualitative"`` — Okabe-Ito (mode-aware).
      - ``"highlight"``                       — single protagonist colour.
      - ``"grey"`` / ``"muted"``              — non-protagonist series colour.
    """
    name = name.lower()
    if name in ("categorical", "qualitative"):
        return OKABE_ITO_DARK if _current_mode == ThemeMode.DARK else OKABE_ITO
    if name == "highlight":
        return (HIGHLIGHT[_current_mode],)
    if name in ("grey", "gray", "muted"):
        return (GREY_MUTED[_current_mode],)
    if name in ("gain_loss", "gainloss"):
        gl = GAIN_LOSS[_current_mode]
        return (gl["gain"], gl["loss"])
    raise ValueError(f"Unknown palette: {name!r}")
