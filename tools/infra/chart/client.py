"""Chart tool: render common charts to base64 PNGs for Slack upload."""

from __future__ import annotations

import base64
from typing import Any

import pandas as pd
from centaur_charts.router import ChartIntent, chart_router
from centaur_charts.style import ThemeMode


class ChartClient:
    """Chart builder. Public API is intentionally one method: render_chart."""

    def render_chart(
        self,
        chart_type: str,
        data: list[dict[str, Any]],
        title: str = "",
        question: str = "",
        protagonist: str | None = None,
        subtitle: str | None = None,
        source: str = "",
        theme_mode: str = "light",
        x: str | None = None,
        y: str | list[str] | None = None,
        extras: dict[str, Any] | None = None,
    ) -> str:
        """Render a chart and return base64-encoded PNG bytes.

        Args:
            chart_type: Free-form type: line, bar, top, indexed_line, scatter,
                candlestick, drawdown, heatmap, sparkline, etc. Aliases are
                normalized by the router.
            data: Row-oriented records suitable for ``pandas.DataFrame``.
            title: Sentence-case takeaway title.
            question: Optional source question / intent.
            protagonist: Optional series/category to highlight.
            subtitle: Optional units/baseline/range subtitle.
            source: Optional source line.
            theme_mode: light | dark | editorial.
            x/y: Optional column hints; otherwise first/numeric columns are used.
            extras: Optional handler-specific settings.
        """
        if not data:
            return ""

        intent = ChartIntent(
            question=question,
            chart_type=chart_type,
            protagonist=protagonist,
            takeaway_title=title,
            subtitle=subtitle,
            source=source,
            theme_mode=ThemeMode(theme_mode.lower()),
            x=x,
            y=y,
            extras=extras or {},
        )
        artifact = chart_router(intent, pd.DataFrame(data))
        return base64.b64encode(artifact.png_bytes).decode("utf-8")


def _client() -> ChartClient:
    return ChartClient()
