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


BRIEF_PROMPT = """Act as my institutional morning market-color analyst.

Audience: a professional trader at Paradigm.
Goal: give me a dense, no-fluff morning brief that helps me understand what is happening across crypto, macro, and my equities watchlist, and what actually matters for today's tape.

Use the freshest available verified information. Timestamp the brief clearly in ET and UTC. Separate facts from interpretation. Prioritize signal over noise, positioning over headlines, and catalysts over generic recap language.

My watchlists

Crypto focus:
BTC, ETH, SOL, majors, crypto beta, perp funding, spot/perp basis, options skew and term structure, ETF flows, stablecoin flows, open interest, liquidations, exchange flows, major unlocks, relevant on-chain or protocol-specific developments.

Macro focus:
US 2y, US 10y, real yields, DXY, USDJPY, CNH, gold, oil, VIX, SPX, NDX, credit spreads, central-bank expectations, major economic data, fiscal/political developments that matter for risk assets.

Equities of interest:
{equities}

Give me the output in this exact structure:

1) Top line
Give me 5-8 bullets on the only things I need to know before the day starts.
For each bullet, include:
- what happened
- why it matters
- whether it is regime-relevant or just noise

2) Cross-asset dashboard
Make a compact table with:
- asset
- latest level
- overnight / 24h move
- 5d move
- one-line interpretation

Include at minimum:
BTC, ETH, SOL, total crypto beta proxy, BTC funding, BTC/ETH basis, BTC/ETH ATM IV, DXY, US 2y, US 10y, real yields, SPX futures, NQ futures, VIX, gold, oil, USDJPY.

Flag anything that is a statistically large move versus recent realized behavior.

3) Crypto color
Cover:
- price action and internals: whether spot or perp-led, OI change, liquidations, funding, basis, options skew, major strikes/expiries, ETF flow context
- flow/read-through: stablecoin mint/burn, exchange inflows/outflows, treasury or whale activity only if it actually matters
- sector and token color: majors, L1s, DeFi, memecoins, AI, infra, restaking, or other sectors only where volume/catalyst is real
- idiosyncratic developments: listings/delistings, legal/regulatory headlines, governance votes, launches, hacks/exploits, unlocks, treasury announcements, exchange issues

End this section with:
"What matters most for crypto today" in 3 bullets.

4) Macro color
Give me:
- overnight recap across Asia, Europe, and US premarket
- the main macro driver of the session
- what rates/FX/commodities are saying
- whether this looks like a liquidity day, growth scare, inflation scare, policy relief, squeeze, or idiosyncratic crypto session
- how macro is feeding into crypto beta, vol, and correlation today

5) Equities of interest
For each ticker in {equities}, give me:
- premarket or recent move
- the driver
- why it matters for crypto / risk sentiment / market structure
- relevant catalysts, earnings, guidance, legal/policy issues, financing, or positioning only if relevant today
- key levels only when they matter

6) What changed since yesterday?
Give me 3-5 deltas that would actually change priors or positioning.
Do not repeat stale narratives unless something genuinely changed.

7) Calendar and catalysts for the next 24 hours
List exact times in ET.
Include only things with plausible market impact:
- economic data
- central-bank speakers
- Treasury supply / auctions
- major earnings
- token unlocks
- ETF decisions or flows
- court rulings / regulatory deadlines
- governance votes
- major expiries / rebalances / conferences

Rank by expected impact.

8) Positioning and variant perception
Tell me:
- what the market appears to believe
- what is underpriced or over-discounted
- what consensus is leaning on
- what would invalidate consensus

9) Trade framing
Give me:
- base case for today
- bull case
- bear case
- the levels and triggers that matter
- what flow or macro confirmation I'd need to lean harder
- any clean cross-asset expressions or hedges that make sense

No forced trade ideas. Only include setups with an actual catalyst, dislocation, or positioning edge.

10) Bottom line
End with exactly these three lines:
- The one thing that matters most today:
- What I'm watching first at the open:
- What would make me change my mind:

Style rules:
- Be concise, specific, skeptical, and useful.
- No basic explanations.
- No generic recap language.
- Prefer numbers, levels, flows, and catalysts over adjectives.
- Explicitly say when something is noise.
- Explicitly say when data is stale or unverified.
- Mention source names next to non-obvious claims.
- Keep the whole brief tight enough to read in 5 minutes.
- Don't bury the lede.

Use all available tools (websearch, crypto data sources, etc.) to gather the freshest data you can. Verify numbers across sources where possible."""


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
