"""Handler registry for the Centaur chart router.

Each handler is a parameterized matplotlib function over chart-kit helpers.
Adding a new chart type is one new handler + one alias entry in
``centaur_charts.router._ALIASES`` — no new pattern file, no new prompt
section.

Handlers are imported lazily from this module's ``__init__`` so the router
can resolve them without circular imports.
"""

from __future__ import annotations

from . import comparison, composition, distribution, finance, layout, relationship, timeseries

# The registry — maps canonical chart type → handler callable.
# Keep these names in sync with the alias table in router.py.
REGISTRY = {
    # time-series family
    "line": timeseries.line_handler,
    "multi_line": timeseries.multi_line_handler,
    "indexed_line": timeseries.indexed_line_handler,
    "slope": timeseries.slope_handler,
    "dumbbell": timeseries.dumbbell_handler,
    "lollipop": timeseries.lollipop_handler,
    "area": timeseries.area_handler,
    "stacked_area": timeseries.stacked_area_handler,
    # comparison / ranking
    "horizontal_bar": comparison.horizontal_bar_handler,
    "vertical_bar": comparison.vertical_bar_handler,
    "grouped_bar": comparison.grouped_bar_handler,
    "stacked_bar": comparison.stacked_bar_handler,
    "stacked_bar_100": comparison.stacked_bar_100_handler,
    "diverging_bar": comparison.diverging_bar_handler,
    "bullet": comparison.bullet_handler,
    # distribution
    "histogram": distribution.histogram_handler,
    "kde": distribution.kde_handler,
    "box": distribution.box_handler,
    "violin": distribution.violin_handler,
    "ridgeline": distribution.ridgeline_handler,
    "ecdf": distribution.ecdf_handler,
    "lorenz": distribution.lorenz_handler,
    # relationship
    "scatter": relationship.scatter_handler,
    "bubble": relationship.bubble_handler,
    "hexbin": relationship.hexbin_handler,
    "correlation_heatmap": relationship.correlation_heatmap_handler,
    "connected_scatter": relationship.connected_scatter_handler,
    # composition
    "treemap": composition.treemap_handler,
    "waterfall": composition.waterfall_handler,
    "pie": composition.pie_handler,
    "heatmap": composition.heatmap_handler,
    "calendar_heatmap": composition.calendar_heatmap_handler,
    # finance
    "candlestick": finance.candlestick_handler,
    "drawdown": finance.drawdown_handler,
    "cumulative_returns": finance.cumulative_returns_handler,
    "returns_histogram": finance.returns_histogram_handler,
    "risk_return": finance.risk_return_handler,
    "rolling_stat": finance.rolling_stat_handler,
    # layout primitives
    "sparkline": layout.sparkline_handler,
    "kpi_tile": layout.kpi_tile_handler,
    "big_number_with_sparkline": layout.big_number_with_sparkline_handler,
    "small_multiples": layout.small_multiples_handler,
}

__all__ = ["REGISTRY"]
