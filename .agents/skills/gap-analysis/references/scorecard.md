# Nightly Scorecard Format

Keep the nightly `ai-v2` post lean but informative.

## Required Fields

- Tasks reviewed
- Below-bar rate (percentage)
- Mean composite score (0-100)
- Top failure modes (up to 3, in plain English, with counts)
- Selected fixes (fix type + title + human narrative + inline gap-thread link)
- PRs opened (with Slack-format links + inline human narrative)
- PRs merged (from recent deploy notifier runs)
- PRs deployed (from recent deploy notifier runs)
- Source threads notified

## Preferred Style

- Bold section headers via Slack mrkdwn (`*Gap Analysis*`, `*Growth Opportunities*`, `*Execution*`)
- One compact summary line with the composite score and below-bar rate
- Use readable bullet glyphs (`•`) for failure modes and selected work items
- Describe failure modes in plain English, not slug form like `verification_miss`
- Keep the gap-thread link inline in the same sentence (for example, `<...|gap thread>`) instead of giving it a separate bullet
- Use Slack user mentions when available in the runtime message, but keep examples in this repo sanitized
- PR links and thread links must use Slack link syntax `<url|text>`, not GitHub-style `[text](url)` (which Slack renders as literal text)
- No deep nesting beyond two levels
- No giant backlog dump
- No raw JSON in the Slack post

## Example

```
*Self Improve Nightly*

Some clean wins, a couple rough edges, and a few upgrades worth shipping.

Reviewed 12 tasks. Mean score: 71/100. Below-bar rate: 25%.

*Gap Analysis*
• Top failure modes
  • The agent skipped or under-verified work before handoff. (3 tasks)
  • The agent answered a different problem than the one the user actually asked. (2 tasks)
• Selected fixes
  • `workflow_fix` Add lint check before delivery in deploy workflows — Arjun hit the same missing-lint pattern twice in code-change tasks, so the deploy workflow needs an explicit lint gate before handoff. <https://slack.com/archives/C123/p1700100000000000|gap thread>
  • `prompt_tweak` Strengthen research-before-action guidance in eng persona — Mina asked for debugging help and the agent moved into edits before reading the relevant files. <https://slack.com/archives/C789/p1700300000000000|gap thread>

*Growth Opportunities*
• Improvements identified: 1
  • `new_persona` Editorial persona for decision memos — Arjun and another teammate both asked for crisper decision briefs in different threads, which points to a reusable stance gap. <https://slack.com/archives/C456/p1700200000000000|gap thread>

*Execution*
• Gap-fix PRs opened
  • <https://github.com/.../42|#42> Add lint check before delivery — Arjun hit the same missing-lint pattern twice in code-change tasks. <https://slack.com/archives/C123/p1700100000000000|gap thread>
• Codify-fix PRs opened
  • <https://github.com/.../43|#43> Editorial persona for decision memos — Repeated request pattern for sharper recommendation-first briefs. <https://slack.com/archives/C456/p1700200000000000|gap thread>
• PRs merged in last 24h: 1
• PRs deployed in last 24h: 1
• Source threads notified in last 24h: 2
```

The runtime Slack post may reference user mentions or first names, what they
asked for, and how the gap surfaced. The inline `gap thread` links point to the
original Slack conversations. Both are only posted to the internal `ai-v2`
channel. They are stripped from the fix packet before the implementing agent
sees it, and must never appear in PR titles, bodies, or commits.
