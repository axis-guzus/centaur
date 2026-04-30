"""Route chart requests to matplotlib handlers and return Slack-ready PNGs."""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass, field
from typing import Any

import pandas as pd
from .helpers import save_to_bytes, source_line
from .style import ThemeMode, apply

# Chart-emit telemetry — single log line per render so we can track what gets
# emitted across the fleet. Uses structlog in the API container, stdlib
# logging in the sandbox / tests.
try:
    import structlog  # type: ignore[import-not-found]

    _log = structlog.get_logger().bind(service="centaur_charts")
except ImportError:  # pragma: no cover
    _log = logging.getLogger("centaur_charts")


def _emit_chart_log(artifact: "ChartArtifact") -> None:
    """Single log line per chart render for fleet telemetry."""
    if os.environ.get("CENTAUR_CHARTS_DISABLE_TELEMETRY"):
        return
    try:
        _log.info("chart_emitted", handler=artifact.handler, chart_type=artifact.chart_type, theme=artifact.intent.theme_mode.value, width=artifact.width, height=artifact.height, png_bytes=len(artifact.png_bytes))
    except Exception:  # noqa: BLE001 — telemetry never crashes the render
        pass


@dataclass
class ChartIntent:
    """Normalized chart request."""

    question: str = ""
    chart_type: str = ""
    protagonist: str | None = None
    takeaway_title: str = ""
    subtitle: str | None = None
    annotations: list[dict] = field(default_factory=list)
    source: str = ""
    theme_mode: ThemeMode = ThemeMode.LIGHT
    x: str | None = None
    y: str | list[str] | None = None
    extras: dict[str, Any] = field(default_factory=dict)


@dataclass
class ChartArtifact:
    """Rendered chart image plus metadata."""

    png_bytes: bytes
    width: int
    height: int
    alt_text: str
    handler: str
    chart_type: str
    intent: ChartIntent


_ALIASES: dict[str, str] = {
    "trend": "line",
    "history": "line",
    "over_time": "line",
    "time_series": "line",
    "timeseries": "line",
    "line_chart": "line",
    "lineplot": "line",
    "multi_line": "multi_line",
    "multiline": "multi_line",
    "indexed_line": "indexed_line",
    "rebased": "indexed_line",
    "indexed": "indexed_line",
    "compare_versus": "indexed_line",
    "vs": "indexed_line",
    "versus": "indexed_line",
    "slope_graph": "slope",
    "slope_chart": "slope",
    "dumbbell_chart": "dumbbell",
    "lollipop_chart": "lollipop",
    "area_chart": "area",
    "ranking": "horizontal_bar",
    "rank": "horizontal_bar",
    "top": "horizontal_bar",
    "biggest": "horizontal_bar",
    "horizontal_bar": "horizontal_bar",
    "h_bar": "horizontal_bar",
    "barh": "horizontal_bar",
    "vertical_bar": "vertical_bar",
    "v_bar": "vertical_bar",
    "column": "vertical_bar",
    "bar": "horizontal_bar",
    "bar_chart": "horizontal_bar",
    "grouped_bar": "grouped_bar",
    "stacked_bar": "stacked_bar",
    "stack": "stacked_bar",
    "100_percent_stacked_bar": "stacked_bar_100",
    "share": "stacked_bar_100",
    "composition": "stacked_bar_100",
    "mix": "stacked_bar_100",
    "diverging_bar": "diverging_bar",
    "deviation": "diverging_bar",
    "bullet": "bullet",
    "bullet_chart": "bullet",
    "distribution": "histogram",
    "spread": "histogram",
    "histogram": "histogram",
    "hist": "histogram",
    "density": "kde",
    "kde": "kde",
    "box_plot": "box",
    "boxplot": "box",
    "box": "box",
    "violin_plot": "violin",
    "violin": "violin",
    "raincloud": "raincloud",
    "ridgeline": "ridgeline",
    "joy_plot": "ridgeline",
    "ecdf": "ecdf",
    "qq": "qq",
    "lorenz": "lorenz",
    "relationship": "scatter",
    "correlation": "scatter",
    "scatter": "scatter",
    "scatterplot": "scatter",
    "bubble": "bubble",
    "hexbin": "hexbin",
    "hex_bin": "hexbin",
    "correlation_matrix": "correlation_heatmap",
    "correlation_heatmap": "correlation_heatmap",
    "connected_scatter": "connected_scatter",
    "stacked_area": "stacked_area",
    "treemap": "treemap",
    "waffle": "waffle",
    "waterfall": "waterfall",
    "pie": "pie",
    "donut": "pie",
    "doughnut": "pie",
    "heatmap": "heatmap",
    "calendar_heatmap": "calendar_heatmap",
    "candle": "candlestick",
    "candlestick": "candlestick",
    "candles": "candlestick",
    "ohlc": "candlestick",
    "drawdown": "drawdown",
    "underwater": "drawdown",
    "cumulative_returns": "cumulative_returns",
    "returns_curve": "cumulative_returns",
    "returns_histogram": "returns_histogram",
    "risk_return": "risk_return",
    "risk_return_scatter": "risk_return",
    "rolling_stat": "rolling_stat",
    "volume_profile": "volume_profile",
    "choropleth": "choropleth",
    "geographic": "choropleth",
    "by_country": "choropleth",
    "by_state": "choropleth",
    "proportional_symbol": "proportional_symbol_map",
    "hex_cartogram": "hex_cartogram",
    "tile_cartogram": "hex_cartogram",
    "network": "force_directed",
    "force_directed": "force_directed",
    "graph": "force_directed",
    "adjacency": "adjacency_matrix",
    "adjacency_matrix": "adjacency_matrix",
    "arc_diagram": "arc",
    "arc": "arc",
    "small_multiples": "small_multiples",
    "facet": "small_multiples",
    "faceted": "small_multiples",
    "sparkline": "sparkline",
    "kpi": "kpi_tile",
    "kpi_tile": "kpi_tile",
    "kpi_card": "kpi_tile",
    "big_number": "big_number_with_sparkline",
    "big_number_with_sparkline": "big_number_with_sparkline",
    "headline": "big_number_with_sparkline",
}


def normalize_chart_type(name: str) -> str:
    """Turn free-form chart names into canonical handler keys."""
    s = (name or "").strip().lower().replace(" ", "_").replace("-", "_")
    return _ALIASES.get(s, s)


_HANDLERS: dict[str, "Handler"] | None = None


def _load_handlers() -> dict[str, "Handler"]:
    global _HANDLERS
    if _HANDLERS is None:
        from .handlers import REGISTRY  # type: ignore[import-not-found]

        _HANDLERS = REGISTRY
    return _HANDLERS


Handler = "callable[[ChartIntent, pd.DataFrame], Figure]"  # type: ignore[name-defined]


def _should_downgrade(data: pd.DataFrame, chart_type: str) -> str | None:
    """Return a safer handler key when the requested chart is a poor fit."""
    if chart_type in {"kpi_tile", "big_number_with_sparkline"}:
        return None  # explicit; user wants this

    n = len(data)
    if n == 0:
        return "kpi_tile"
    if n == 1:
        return "kpi_tile"

    if chart_type == "pie" and n > 3:
        return "horizontal_bar"

    return None


def chart_router(
    intent: ChartIntent,
    data: pd.DataFrame,
    *,
    alt_text: str | None = None,
) -> ChartArtifact:
    """Render a chart intent to a PNG artifact."""
    apply(intent.theme_mode)
    canonical = normalize_chart_type(intent.chart_type)
    intent.chart_type = canonical
    downgrade = _should_downgrade(data, canonical)
    if downgrade is not None:
        canonical = downgrade
        intent.chart_type = canonical
    handlers = _load_handlers()
    handler = handlers.get(canonical) or handlers.get("line")
    if handler is None:
        raise RuntimeError(
            "No matplotlib handlers are registered. Did you import "
            "centaur_charts.handlers?"
        )

    fig = handler(intent, data)
    if intent.source:
        source_line(fig, intent.source if intent.source.lower().startswith("source:") else f"Source: {intent.source}")
    png = save_to_bytes(fig, dpi=200, fmt="png")
    width = int(fig.get_size_inches()[0] * 200)
    height = int(fig.get_size_inches()[1] * 200)
    artifact = ChartArtifact(
        png_bytes=png,
        width=width,
        height=height,
        alt_text=alt_text or _build_alt_text(intent, data, canonical),
        handler=handler.__name__,
        chart_type=canonical,
        intent=intent,
    )
    _emit_chart_log(artifact)
    return artifact


def _build_alt_text(intent: ChartIntent, data: pd.DataFrame, canonical: str) -> str:
    """Generate accessible alt text from intent + data shape.

    Falls back to ``"<chart_type> with N rows of data"`` when the intent has
    no takeaway. Slack uses this for screen-readers and search indexing.
    """
    head = intent.takeaway_title or canonical.replace("_", " ").title()
    n = len(data)
    cols = ", ".join(map(str, list(data.columns)[:4])) if not data.empty else ""
    extra = f" ({n} rows: {cols})" if cols else f" ({n} rows)"
    return f"{head}{extra}"
