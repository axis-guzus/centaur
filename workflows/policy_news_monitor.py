import json
import feedparser
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from api.workflow_engine import WorkflowContext

WORKFLOW_NAME = "policy_news_monitor"

SLACK_CHANNEL = "C0ASR4NFLPR"
LOOKBACK_MINUTES = 20  # slightly wider than 15 to avoid gaps at cycle boundaries

RSS_FEEDS = [
    {"name": "Politico - Congress", "url": "https://rss.politico.com/congress.xml"},
    {"name": "Politico - Politics", "url": "https://rss.politico.com/politics-news.xml"},
    {"name": "Politico - Defense", "url": "https://rss.politico.com/defense.xml"},
    {"name": "Politico - Morning Tech", "url": "https://rss.politico.com/morningtech.xml"},
    {"name": "The Hill - News", "url": "https://thehill.com/news/feed/"},
    {"name": "The Hill - Technology", "url": "https://thehill.com/policy/technology/feed/"},
    {"name": "The Hill - Finance", "url": "https://thehill.com/business/feed/"},
    {"name": "The Hill - Defense", "url": "https://thehill.com/policy/defense/feed/"},
    {"name": "Axios", "url": "https://www.axios.com/feeds/feed.rss"},
    {"name": "Semafor", "url": "https://semafor.com/rss.xml"},
    {"name": "Roll Call", "url": "https://www.rollcall.com/feed/"},
    {"name": "CoinDesk", "url": "https://www.coindesk.com/arc/outboundfeeds/rss/"},
    {"name": "The Block", "url": "https://www.theblock.co/rss.xml"},
    {"name": "Wired", "url": "https://www.wired.com/feed/rss"},
    {"name": "Breaking Defense", "url": "https://breakingdefense.com/feed/"},
    {"name": "Defense One", "url": "https://defenseone.com/rss/all"},
    {"name": "Defense News", "url": "https://www.defensenews.com/arc/outboundfeeds/rss/"},
    {"name": "Nextgov/FCW", "url": "https://www.nextgov.com/rss/all/"},
    {"name": "Reuters", "url": "https://www.reutersagency.com/feed/"},
    {"name": "Washington Post - Politics", "url": "https://feeds.washingtonpost.com/rss/politics"},
    {"name": "New York Times - Politics", "url": "https://rss.nytimes.com/services/xml/rss/nyt/Politics.xml"},
    {"name": "Wall Street Journal", "url": "https://feeds.a.dj.com/rss/RSSWorldNews.xml"},
    {"name": "Financial Times", "url": "https://www.ft.com/rss/home"},
]

EDITORIAL_BRIEF = """
You are a policy analyst working for Paradigm, a crypto and emerging technology investment firm.
Your job is to surface stories that matter to our policy and government affairs team — things that
signal regulatory shifts, legislative movement, or a senior official taking a new public position
that could affect our portfolio or advocacy work.

TOPICS WE TRACK:

- Crypto & digital assets (highest priority): Market structure legislation (our primary legislative
  fight right now), stablecoin legislation, DeFi regulation, SEC/CFTC jurisdiction and enforcement,
  crypto tax policy, digital asset bills moving through Congress.

- AI policy: AI regulation and governance, foundation model policy, AI safety legislation,
  algorithmic accountability, AI use in government.

- Prediction markets: Kalshi, Polymarket, CFTC event contracts, international developments
  (UK FCA, EU) when they have US implications.

- Defense tech & robotics: Autonomous weapons policy, defense AI, robotics regulation —
  policy, defense procurement, and regulatory angles all count. Ignore pure product launches.

- Technology in politics: How parties, campaigns, or PACs are adopting or rejecting AI, crypto,
  or emerging tech — when it signals how tech-forward the political environment will be.
  Ignore fundraising totals and general horse-race coverage.

KEY ACTORS TO ALWAYS FLAG: SEC, CFTC, OCC, FinCEN, OFAC, Treasury, Senate Banking Committee,
House Financial Services Committee (HFSC), Senate Agriculture Committee, Senate Intel Committee.
Flag any markup, floor vote, or reconciliation bill touching our topics.
Include op-eds or commentary from senior current or former government officials.

IGNORE: Crypto price movements, NFT culture, product launches with no policy angle, prediction
market product commentary, earnings reports.

URGENCY BAR: A story is Urgent if it involves a committee markup, a floor vote, a new enforcement
action, or a senior official making a first-time public statement on one of our issues.
Everything else is Standard.
"""

AGENT_PROMPT_TEMPLATE = """
{brief}

Here are {n} articles published in the last {lookback} minutes across Paradigm's policy news feeds:

{articles}

For each article that passes the editorial filter above:

1. Query the policy-gigabrain skill for any relevant context on the story's topic, bill, or actors
   (prior Hill intel, bill status, agency positions, team meeting notes).
2. Write a "why it matters" line in policy operator style, connecting directly to Paradigm's
   legislative agenda. Ground it only in what the article explicitly states plus any context
   returned by the gigabrain. Do not infer beyond those two sources. If the policy significance
   is genuinely unclear, write "Significance unclear — worth monitoring."
3. Post the story to Slack channel {channel} in exactly this format:

[Topic][Urgency]
Headline
Source | Published
Why it matters: <your line>
Reason for inclusion: <specific quote, vote, or action from the article>
<url>

If no articles pass the filter, post nothing.
"""


def fetch_recent_articles() -> list[dict]:
    cutoff = datetime.now(timezone.utc) - timedelta(minutes=LOOKBACK_MINUTES)
    articles = []
    seen_urls = set()

    for feed in RSS_FEEDS:
        try:
            parsed = feedparser.parse(feed["url"])
            for entry in parsed.entries[:20]:
                url = getattr(entry, "link", "")
                if not url or url in seen_urls:
                    continue

                published = None
                if hasattr(entry, "published_parsed") and entry.published_parsed:
                    published = datetime(*entry.published_parsed[:6], tzinfo=timezone.utc)
                elif hasattr(entry, "updated_parsed") and entry.updated_parsed:
                    published = datetime(*entry.updated_parsed[:6], tzinfo=timezone.utc)

                if published and published < cutoff:
                    continue

                seen_urls.add(url)
                articles.append({
                    "source": feed["name"],
                    "title": getattr(entry, "title", "").strip(),
                    "summary": getattr(entry, "summary", "")[:500].strip(),
                    "url": url,
                    "published": str(published) if published else "unknown",
                })
        except Exception:
            pass

    return articles


@dataclass
class Input:
    pass


async def handler(inp: Input, ctx: WorkflowContext) -> dict:
    run = 0
    while True:
        articles = await ctx.step(f"fetch_{run}", fetch_recent_articles)

        if articles:
            prompt = AGENT_PROMPT_TEMPLATE.format(
                brief=EDITORIAL_BRIEF,
                n=len(articles),
                lookback=LOOKBACK_MINUTES,
                articles=json.dumps(articles, indent=2),
                channel=SLACK_CHANNEL,
            )
            await ctx.run_agent(f"analyze_{run}", text=prompt)

        await ctx.sleep(f"wait_{run}", timedelta(minutes=15))
        run += 1
