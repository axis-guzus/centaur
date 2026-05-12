---
name: slack-history-gap-search
description: Use when the user wants historical company context from Slack and the answer should combine indexed company context with newer Slack messages that have not been projected yet. First search company_context for Slack history, then use company_context.latest_date to find the latest indexed Slack timestamp, then use slack.search_messages with an after:YYYY-MM-DD filter to find newer matching Slack messages.
---

# Slack History Gap Search

Use this skill when the task is about Slack history and the best answer should blend:

- Indexed historical context already stored in `company_context`
- Newer matching Slack messages that may exist after the latest indexed Slack date

## Workflow

1. Search indexed history first with `company_context.search`.
2. Restrict that search to Slack unless the user explicitly wants another source.
3. Call `company_context.latest_date(source="slack")` to find the latest indexed Slack timestamp.
4. If `latest_date` is present, derive a Slack search modifier `after:YYYY-MM-DD` from that timestamp and run `slack.search_messages`.
5. If `latest_date` is absent, treat the company-context index as empty for Slack and run `slack.search_messages` without an `after:` cutoff.
6. Coalesce the indexed and newer Slack results into one combined answer.

## Tool Usage

Use `company_context.search` first:

```python
company_context.search(
    query="<user query>",
    source="slack",
    limit=10,
)
```

Use `company_context.read_document` when a hit looks important and you need the full thread or day summary.

Use `company_context.latest_date` to get the Slack cutoff:

```python
company_context.latest_date(source="slack")
```

Then search for newer Slack messages:

```python
slack.search_messages(
    query="<user query> after:YYYY-MM-DD",
    max_results=10,
)
```

If the user already specified Slack search modifiers like `in:#channel` or `from:@name`, preserve them when adding the `after:` filter.

## Coalescing Rules

- Produce one merged narrative, not two sections.
- Start from the indexed context, then fold in newer Slack matches as updates, confirmations, or contradictions.
- Deduplicate overlapping points when the newer Slack matches repeat information already captured in indexed history.
- Preserve provenance in-line when it matters, for example by saying a point came from indexed historical context or from newer Slack messages after the cutoff.
- Prefer the newer Slack match when it materially updates or corrects an older indexed point.

## Output Rules

- Say what the indexed cutoff is when you use one.
- Do not present newer Slack matches as if they came from `company_context`.
- Prefer concise synthesis over dumping raw hits.
- Provide links wherever available:
  - use document `url` from `company_context` results when present
  - use `permalink` from `slack.search_messages` when present
- If there are no indexed hits but there are newer Slack messages, say that the historical index had no matches and synthesize from the newer Slack results.
- If there are indexed hits but no newer Slack matches, say that nothing newer than the indexed cutoff matched.

## Heuristics

- Prefer `source_updated_at` / `latest_date` as the freshness boundary.
- If `company_context.search` returns broad day-level summaries, open the most relevant document with `company_context.read_document` before summarizing it.
- Keep newer Slack details focused on net-new information rather than repeating indexed history verbatim.
