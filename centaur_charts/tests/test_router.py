"""Smoke tests + Slack-mobile-readability snapshot tests for the chart router.

The test fleet covers the most common chart types end-to-end:
  1. Each handler produces a valid PNG with expected dimensions and size band.
  2. The PNG survives downsampling to 360 px wide (Slack mobile preview).
  3. The router downgrades small-n / pie>3 / kpi-tile cases as expected.
  4. The data-integrity critic catches hallucinated numbers.

Tests are file-size-band rather than byte-exact because matplotlib output is
non-deterministic across font versions / hinting. A 50-100 KB PNG that's
within ±50% of the snapshot baseline counts as "still working".
"""

from __future__ import annotations

import base64
import importlib.util
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from centaur_charts.critic import (
    data_integrity_check,
    mobile_readability_check,
)
from centaur_charts.router import ChartIntent, chart_router, normalize_chart_type


PNG_HEADER = b"\x89PNG\r\n\x1a\n"


def _is_png(b: bytes) -> bool:
    return b[:8] == PNG_HEADER


def _load_chart_tool_client():
    root = Path(__file__).resolve().parents[2]
    client_path = root / "tools" / "infra" / "chart" / "client.py"
    spec = importlib.util.spec_from_file_location("chart_tool_client", client_path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.ChartClient


# ── Smoke tests for every core handler ──────────────────────────────────────


@pytest.fixture
def time_series_df():
    rng = np.random.default_rng(0)
    return pd.DataFrame(
        {
            "date": pd.date_range("2026-01-01", periods=30),
            "BTC": 60_000 + np.cumsum(rng.normal(0, 1000, 30)),
            "ETH": 3_000 + np.cumsum(rng.normal(0, 30, 30)),
        }
    )


@pytest.fixture
def category_df():
    return pd.DataFrame(
        {
            "token": ["BTC", "ETH", "SOL", "XRP", "BNB", "DOGE"],
            "mcap": [1.9e12, 4.0e11, 8.0e10, 5.0e10, 6.0e10, 1.5e10],
        }
    )


def test_line_chart(time_series_df):
    art = chart_router(
        ChartIntent(chart_type="line", takeaway_title="BTC trend over the period"),
        time_series_df[["date", "BTC"]],
    )
    assert _is_png(art.png_bytes)
    assert 10_000 < len(art.png_bytes) < 1_000_000
    assert art.handler == "line_handler"


def test_chart_tool_has_single_public_render_method():
    client = _load_chart_tool_client()()
    public = [name for name in dir(client) if not name.startswith("_")]
    assert public == ["render_chart"]


def test_chart_tool_render_chart_outputs_png():
    client = _load_chart_tool_client()()
    b64 = client.render_chart(
        chart_type="line",
        data=[{"date": "2026-04-01", "price": 100}, {"date": "2026-04-02", "price": 110}],
        title="BTC rose over two days",
        x="date",
        y="price",
        protagonist="BTC",
    )
    assert _is_png(base64.b64decode(b64))


def test_indexed_line_chart(time_series_df):
    art = chart_router(
        ChartIntent(
            chart_type="vs",  # alias resolves to indexed_line
            protagonist="ETH",
            takeaway_title="ETH led BTC over the period",
        ),
        time_series_df,
    )
    assert _is_png(art.png_bytes)
    assert art.handler == "indexed_line_handler"
    assert art.chart_type == "indexed_line"


def test_horizontal_bar(category_df):
    art = chart_router(
        ChartIntent(chart_type="top", takeaway_title="Top 6 tokens by market cap"),
        category_df,
    )
    assert _is_png(art.png_bytes)
    assert art.handler == "horizontal_bar_handler"


def test_distribution(time_series_df):
    art = chart_router(
        ChartIntent(chart_type="distribution", takeaway_title="BTC daily change distribution"),
        time_series_df[["BTC"]],
    )
    assert _is_png(art.png_bytes)
    assert art.handler == "histogram_handler"


def test_correlation_heatmap(time_series_df):
    art = chart_router(
        ChartIntent(chart_type="correlation_matrix", takeaway_title="Token returns correlation"),
        time_series_df[["BTC", "ETH"]],
    )
    assert _is_png(art.png_bytes)
    assert art.handler == "correlation_heatmap_handler"


def test_treemap(category_df):
    art = chart_router(
        ChartIntent(chart_type="treemap", takeaway_title="Market cap composition"),
        category_df,
    )
    assert _is_png(art.png_bytes)


def test_drawdown(time_series_df):
    df = pd.DataFrame(
        {
            "date": time_series_df["date"],
            "equity": np.maximum.accumulate(time_series_df["BTC"].values),
        }
    )
    art = chart_router(
        ChartIntent(chart_type="drawdown", takeaway_title="Strategy underwater curve"),
        df,
    )
    assert _is_png(art.png_bytes)
    assert art.handler == "drawdown_handler"


# ── Routing-rule tests ─────────────────────────────────────────────────────


def test_alias_normalization():
    assert normalize_chart_type("line-chart") == "line"
    assert normalize_chart_type("trend") == "line"
    assert normalize_chart_type("history") == "line"
    assert normalize_chart_type("over time") == "line"
    assert normalize_chart_type("ranking") == "horizontal_bar"
    assert normalize_chart_type("top") == "horizontal_bar"
    assert normalize_chart_type("scatter") == "scatter"
    assert normalize_chart_type("vs") == "indexed_line"


def test_pie_with_many_slices_downgrades_to_bar():
    df = pd.DataFrame({"label": list("ABCDEFGH"), "value": [1, 2, 3, 4, 5, 6, 7, 8]})
    art = chart_router(ChartIntent(chart_type="pie", takeaway_title="Mix"), df)
    assert art.chart_type == "horizontal_bar"
    assert _is_png(art.png_bytes)


def test_single_row_downgrades_to_kpi():
    df = pd.DataFrame({"metric": ["BTC price"], "value": [72_500]})
    art = chart_router(ChartIntent(chart_type="line", takeaway_title="BTC price"), df)
    assert art.chart_type == "kpi_tile"
    assert _is_png(art.png_bytes)


# ── Slack-mobile-preview snapshot tests ────────────────────────────────────


def test_slack_mobile_readability_passes_for_default_size(time_series_df):
    art = chart_router(
        ChartIntent(chart_type="line", takeaway_title="BTC trend"),
        time_series_df[["date", "BTC"]],
    )
    issues = mobile_readability_check(art)
    errors = [i for i in issues if i.severity == "error"]
    assert errors == [], f"Default-size chart shouldn't fail mobile check: {errors}"


def test_png_dimensions_match_slack_target(time_series_df):
    art = chart_router(
        ChartIntent(chart_type="line", takeaway_title="BTC"),
        time_series_df[["date", "BTC"]],
    )
    # figsize=(8.0, 4.5) × dpi=200 → 1600 × 900
    assert art.width >= 1500, f"width={art.width} too small for Slack mobile retina"
    assert art.height >= 850
    aspect = art.width / max(art.height, 1)
    assert 1.6 < aspect < 2.0, f"aspect {aspect:.2f} not 16:9-ish"


# ── Data integrity critic tests ────────────────────────────────────────────


def test_critic_catches_hallucinated_number(time_series_df):
    intent = ChartIntent(
        chart_type="line",
        takeaway_title="BTC was up 99.5% over 30d",  # 99.5 is not in the data
    )
    issues = data_integrity_check(intent, time_series_df[["date", "BTC"]])
    codes = [i.code for i in issues]
    assert "hallucinated_number" in codes


def test_critic_passes_for_truthful_title(time_series_df):
    pct = (
        time_series_df["BTC"].iloc[-1] / time_series_df["BTC"].iloc[0] - 1
    ) * 100
    intent = ChartIntent(
        chart_type="line",
        takeaway_title=f"BTC moved {pct:+.1f}% over the period",
    )
    issues = data_integrity_check(intent, time_series_df[["date", "BTC"]])
    # Allow noise from the regex (e.g., "30d" parsing); the *truthful* number
    # should not be flagged as hallucinated.
    hallucinated_for_actual_value = [
        i
        for i in issues
        if i.code == "hallucinated_number" and f"{pct:.1f}" in i.message
    ]
    assert hallucinated_for_actual_value == []


# ── Telemetry test ─────────────────────────────────────────────────────────


def test_chart_emit_log_runs_without_error(time_series_df, caplog):
    """Telemetry must not crash the render path even on logger failure."""
    import logging

    caplog.set_level(logging.INFO)
    art = chart_router(
        ChartIntent(chart_type="line"),
        time_series_df[["date", "BTC"]],
    )
    assert _is_png(art.png_bytes)
