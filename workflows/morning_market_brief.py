"""Workflow: delivers a dense morning market brief to Slack every trading day."""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass, field
from typing import Any
from zoneinfo import ZoneInfo

from api.workflow_engine import WorkflowContext

WORKFLOW_NAME = "morning_market_brief"


@dataclass
class Input:
    equities: list[str] = field(default_factory=lambda: ["MSTR", "COIN", "HOOD", "NVDA", "MARA"])
    slack_channel: str = "morning-brief"
    timezone: str = "America/New_York"
    run_hour: int = 7
    run_minute: int = 30
    max_iterations: int = 0  # 0 = run forever


BRIEF_PROMPT = """SPEED IS CRITICAL. Post to Slack within 3 minutes. Do NOT visit individual stock pages.

STEP 1 - Do exactly 3 searches + 1 chart-data pull in parallel:
a) "site:finance.yahoo.com top market news today"
b) "BTC ETH SOL price funding rates ETF flows today"
c) "MSTR COIN HOOD NVDA MARA stock price today"
d) call coingecko get_market_chart for BTC, ETH, SOL (24h, vs USD) — needed for the indexed-line chart in step 2.

STEP 2 - Choose the lead format based on signal. The user reads the brief on Slack mobile.

(2a) If BTC/ETH/SOL have meaningful divergence (>1% spread between leader and laggard) or a clear intraday story, post an indexed-line chart of BTC/ETH/SOL last 24h, rebased to 100 at session open, before the prose. Use the chart tool — it applies the shared Centaur chart theme + brand-aware colours:
  call chart render_chart '{{"chart_type": "indexed_line", "data": [{{"date": "...", "BTC": 100, "ETH": 98, "SOL": 103}}, ...], "title": "<LEADER> led the majors over 24h", "x": "date", "y": ["BTC", "ETH", "SOL"], "protagonist": "<LEADER>"}}'
  Then call slack upload_file with title="<LEADER> led the day +Xpts vs <LAGGARD>", alt_text describing the move.
  If crypto is flat or data is stale, do NOT post this chart. Say "Crypto: range-bound, no material catalysts."

(2b) If there are >=3 meaningful movers across crypto + equities, post a horizontal bar of % moves for the top 6 movers. Sorted descending. Use:
  call chart render_chart '{{"chart_type": "top", "data": [{{"label": "<asset>", "value": <pct>}}, ...], "title": "Today's biggest movers", "x": "label", "y": "value"}}'
  Then upload to Slack with alt_text.
  If there are only 1-2 meaningful movers, skip the bar and use BIG MOVES bullets only.

(2c) THEN write the prose brief. RULES:

SIGNAL OVER COMPLETENESS:
- Brief must be readable in 90 seconds, not 5 minutes
- ONLY include items that moved meaningfully or have a clear catalyst today
- SKIP any asset/ticker/section that did not move >1% (crypto/equities) or >1 stdev (rates/FX/vol)
- If nothing material in a section, write "no material moves" and move on. Do NOT pad.
- Lead with biggest moves
- NEVER include items just to fill space

CITE SOURCES in [brackets] for every number. Flag stale data. Use charts for comparisons and trends; use compact text/code-block tables only when exact values are the point.

STRUCTURE:

BIG MOVES - 3-5 bullets max. Only items that materially moved or have a clear driver. For each: asset, exact move with source, why it matters in one line.

CRYPTO - Only if real signal. Otherwise: "Crypto: range-bound, no material catalysts."

MACRO - Only if real driver. Otherwise: "Macro: quiet session."

EQUITIES - Only tickers from {equities} that moved >2% or have a real catalyst. Skip the rest entirely.

HEADLINES - Top 3-5 headlines that actually matter today. Cite source.

NEXT 24H - Only events with plausible market impact, ranked by importance. ET times.

BOTTOM LINE (always include - exactly 3 lines):
- The one thing that matters most today:
- What I am watching first at the open:
- What would make me change my mind:

STYLE: Brutal selection. If in doubt, leave it out. Numbers and levels over adjectives. No throat-clearing.

STEP 3 - Post to Slack channel "morning-brief" using the slack tool send_message method. The chart files from steps 2a/2b should already be in the same thread — write the prose as a follow-up message that references them ("Above: BTC led, ETH lagged. Read:")."""


async def handler(inp: Input, ctx: WorkflowContext) -> dict[str, Any]:
    """Run the morning market brief on a daily loop."""

    equities_str = ", ".join(inp.equities)
    prompt = BRIEF_PROMPT.format(equities=equities_str)
    iteration = 0

    while True:
        iteration += 1
        tz = ZoneInfo(inp.timezone)
        now = dt.datetime.now(dt.timezone.utc).astimezone(tz)

        # Skip weekends (Saturday=5, Sunday=6)
        next_run = now.replace(
            hour=inp.run_hour,
            minute=inp.run_minute,
            second=0,
            microsecond=0,
        )
        if next_run <= now:
            next_run += dt.timedelta(days=1)

        await ctx.sleep(f"wait_{iteration}", next_run - now)

        # Run the agent to gather data and produce the brief
        result = await ctx.run_agent(
            f"brief_{iteration}",
            text=prompt,
        )

        # Post to Slack if configured
        if inp.slack_channel and isinstance(result, dict):
            result_text = result.get("result_text", "")
            if result_text:
                date_str = dt.datetime.now(dt.timezone.utc).astimezone(tz).strftime("%Y-%m-%d")
                await ctx.run_agent(
                    f"post_slack_{iteration}",
                    text=(
                        f"Post the following morning market brief to the #{inp.slack_channel} "
                        f"Slack channel. Use the slack tool. Title it 'Morning Market Brief — {date_str}'.\n\n"
                        f"{result_text}"
                    ),
                )

        if inp.max_iterations > 0 and iteration >= inp.max_iterations:
            return {
                "status": "done",
                "iterations": iteration,
                "last_result": result,
            }
