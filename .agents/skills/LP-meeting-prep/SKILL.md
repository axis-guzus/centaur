---
name: LP-meeting-prep
description: "Generates a pre-meeting briefing memo for a client or prospect meeting. Use when asked to prepare a briefing, write a meeting brief, prep for a meeting, or summarize who we're meeting with."
---

# Pre-Meeting Briefing Memo

Researches and writes a structured briefing memo before a client or prospect meeting.

## When To Use

Use when the user asks to:
- "prep a briefing for my meeting with X"
- "write a briefing memo for [name/org]"
- "help me prep for my meeting with X"
- "who are we meeting with tomorrow?"
- "briefing note for [name]"

## Inputs Needed

Ask the user if not already provided:
- **Who** is the meeting with? (person name + organization)
- **When** is the meeting? (date/time)
- **Where** — Zoom or in-person?

If the user says "check my calendar" or "you figure it out," use Google Calendar to find the next upcoming meeting and infer the details.

## Approach: Fast, Parallel, Draft First

**HARD TIME BUDGET: 5 minutes total. At 4 minutes, STOP researching and write the memo with whatever you have — even if some sections are sparse.**

Rules (not suggestions):
- **Fire ALL lookups in a single parallel tool-call batch.** Do not wait for one to finish before starting the next. Do not chain. One batch, many tools.
- **One attempt per lookup. No retries. No follow-ups.** If a tool errors, returns nothing, or returns partial data, move on. Do not investigate. Do not refine the query. Do not try an alternate source unless the original explicitly failed with an auth or 404 error and an alternate is named in the step below.
- **Do not think between tool calls.** No interpretation, summarization, or planning in between. Fire the batch, wait, collect, write.
- **Do not do "nice to have" deep dives.** If you catch yourself considering a follow-up search, stop and write the memo.
- **If any single tool takes longer than 90 seconds, abandon it.** Write "not available" for that section and proceed.

**Critical lookups that must NOT be abandoned or written off as "unknown":**
- **Calendar invite (Step 1)** — must be queried; if it errors, retry once
- **Attio meeting history (Step 2f)** — must be queried; if it errors, retry once. Do NOT write "Prior meetings: none" simply because Attio was slow or returned partial data — the cost of missing a prior meeting (e.g. a 2019 introductory call) is high enough to justify a retry.

For all other lookups, the abandon-after-90s rule applies.

**Hard cap on tool calls:** No more than **15 total tool calls** across the entire task (calendar + websearch + Attio queries + Slack/Gmail combined). If you hit 15, stop researching and write the memo with what you have. This prevents runaway exploration. A normal run uses 8–12 tool calls.

Budget guideline: calendar lookup ~30s, parallel lookup batch ~2min, memo assembly ~1min. Anything beyond that is over-research.

## Entity Precision

**Always be precise about which organization you are researching.** Many LPs operate under a parent brand with distinct subsidiaries — these are different entities with different relationships, attendees, and investment mandates. For example, Mubadala Capital Solutions is a distinct platform from Mubadala Capital and from Mubadala Investment Company. When searching for prior meetings, relationship data, and sizing, search specifically for the named entity (e.g. "Mubadala Capital Solutions") — do not conflate results from the broader parent organization unless explicitly relevant. Note any parent/subsidiary relationship in the LP overview section.

## Steps

### 1. Pull the calendar event

**CRITICAL — query the user's calendar, not the agent's own.** The Centaur agent runs under the `svc_ai@paradigm.xyz` service account. The `gsuite.calendar_events` method defaults `calendar_id` to `"primary"`, which is svc_ai's own (empty) calendar. **Always explicitly pass `calendar_id` set to a known calendar ID**. Without this, the lookup silently returns zero events.

**NEVER use `gsuite.calendar_list` (or any "is this calendar visible" check) to decide whether Centaur can read a calendar.** Some calendars (notably Paradigm IR) are accessible via `gsuite.calendar_events` even though they don't appear in `calendar_list`. Treat absence from `calendar_list` as meaningless. Always query `calendar_events` directly against the known calendar ID.

**Known calendar IDs to query for LP meeting lookups (in this order):**
1. **Paradigm IR** — `c_f7f190412d9e371ce1b93530a918db7f89499c640f5133c5cdac01cbfe244dd0@group.calendar.google.com`. This is the canonical IR calendar where most LP meetings are scheduled. Always check this first.
2. **The user's calendar** — e.g. `pam@paradigm.xyz`, `lindsay@paradigm.xyz`. Use the email of whoever invoked the skill.
3. **Other Paradigm attendees' calendars** — only if the meeting wasn't found on (1) or (2). Query by `<email>@paradigm.xyz`.

**How to query each calendar:**
- Set `time_min` and `time_max` with **explicit America/Los_Angeles offsets**, e.g. `time_min="2026-04-28T00:00:00-07:00"`, `time_max="2026-04-29T00:00:00-07:00"`. Do NOT call `gsuite.calendar_get_timezone` on the Paradigm IR calendar — it's not in svc_ai's subscribed list and the call will fail. Hardcode the LA offset (or whatever local TZ matches the meeting).
- First call `calendar_events` **with `query`** set to the LP's name or short alias (e.g. `query="GEM"`, `query="Mubadala"`, `query="Oxford"`).
- If the query call returns no results, call `calendar_events` **again without the `query` parameter** and inspect every event title in the window — the meeting may be titled differently (e.g. "Gem Investments" vs "GEM"). Match by company name appearing anywhere in the event summary.
- Once an event matches, stop searching and use it.

**Note on private events:** Events marked "[Private event]" on a Paradigm attendee's personal calendar will not surface their title/details even with read access — they are only fully visible to the calendar owner. If a meeting can't be found on Paradigm IR or the user's own calendar, and the only candidates on co-attendees' calendars are private, fall through to the no-calendar fallback below.

**Fallback if NO calendar event can be found anywhere:** Do NOT silently invent meeting time, format, or attendees. Instead:
1. Render the time/date line as: `[Meeting format and time not found on calendar — building briefing from CRM and tracker context]` instead of fabricated values.
2. Skip the address line.
3. Populate Paradigm attendees from the most-likely-source heuristic (Slack/Gmail thread context, P3 tracker "owner" column, or known relationship lead from Attio) — and add a parenthetical: `(inferred — no invite found)`.
4. Populate LP attendees from CRM-tracker / email-thread context — same parenthetical.
5. Continue with all other sections (LP overview, investments, prior meetings, etc.) normally — those don't depend on the invite.
6. Add a note at the very top of the memo: `Note: No calendar invite was found for this meeting. Time, format, and attendees below are inferred from CRM/tracker context. Confirm with the meeting organizer before relying on them.`

Search Google Calendar for the meeting to confirm:
- Date and time — always convert to Pacific Time (PT). For in-person meetings, also show the meeting's local time alongside PT (format: "9:00 AM BST / 1:00 AM PT"). For Zoom meetings, show PT only.
- For in-person meetings: also pull the **location/address** from the calendar event's location field. Render it as a Google Maps hyperlink (URL format: `https://www.google.com/maps/search/?api=1&query=<URL-encoded-address>`).
- Zoom link or location (in-person)
- Paradigm attendees — **list EVERY @paradigm.xyz email on the invite regardless of RSVP status** (accepted, needsAction, tentative, declined all count). Do not limit to only "accepted" responses; people often attend without formally accepting. **Always use the person's full first + last name** (e.g. "Matt Huang", "Alana Palmedo"), not a partial display name or first-name-only. Resolve from email address or Google Directory if the calendar entry is incomplete.
- LP/prospect attendees — **list EVERY external email on the invite regardless of RSVP status**, and always use the person's full first + last name. **Use exactly the people on the calendar invite — do not substitute, drop, or add attendees based on what you know about the org's leadership or who you think "should" be there. The invite is the source of truth.**

**Filtering rules — apply ONLY after the full attendee list is collected:**
- **Paradigm side:** Exclude Holly Morgan-Winsdale, Nicki Lardieri, and any `ir@paradigm.xyz` / "Investor Relations" group alias — they are EAs/scheduling aliases, not meeting participants. Do NOT exclude anyone else on the Paradigm side — keep all other @paradigm.xyz attendees even if their RSVP is not "accepted."
- **LP/client side:** If any external attendee appears to be an EA or scheduler (e.g., they coordinated logistics with Holly or Nicki rather than being a substantive meeting participant), exclude them from LP attendees. Use email or calendar context to identify schedulers when ambiguous.

### 2. Run remaining lookups in parallel

Simultaneously look up:

**a. Organization research** — Search the internet for the specific entity's website. Write 3–5 sentences describing the business in substantive detail: what they actually do, investment mandate and strategies, asset classes covered, and any notable scale/AUM figures.

**Write with confidence, not hedges.** Do not use phrases like "appears to be", "seems to", "suggests", or "the relevant lens is" — write direct factual statements about the entity. If the distinction between the specific entity and the parent platform is relevant, state it as a fact (e.g. "MCS is the fund-investments platform within Mubadala Capital, distinct from the parent Mubadala Investment Company"), not as inference. The description must be about the specific named entity, not the parent — if you find yourself writing mostly about the parent, re-anchor to the subsidiary.

**Inclusion rules:**
- **Ownership structure:** Only include if it is prominently featured on the client org's own website (e.g. "wholly owned by X" displayed on their About page). If their site does not highlight ownership, leave it out.
- **Recent news:** Only include if it is a very big deal — examples: new CIO or senior management change, major M&A, large fund close, regulatory/legal headline. Skip routine news, partnerships, product launches, etc.

Example of the right shape when ownership and news both qualify: "Mubadala Capital Solutions is an alternative asset manager wholly owned by Mubadala Investment Company that manages capital on behalf of third-party investors. The platform invests across [asset classes] through both direct investments and fund-of-funds strategies. It was founded in [year] and has [AUM/deployed capital figure]." Substitute actual facts for the entity you're researching.

**b. LP relationship data** — Query `paradigmdb` using `db_tables` then `db_query` to find, **for this specific LP entity**:
- Total commitments across all Paradigm funds ($)
- Total NAV + unfunded across all Paradigm funds ($)
- Relationship-level TVPI (across all funds)
- For each individual fund (Paradigm Fund / "PF", Paradigm One / "P1", Paradigm Two / "P2", Paradigm Three / "P3"): commitment ($), NAV + unfunded ($), and TVPI

If not found in `paradigmdb`, try `addepar` (`list_entities` then portfolio data). Only include funds where the LP has actual exposure — omit any sub-bullet for a fund the LP is not invested in.

**c. P3 fundraising tracker — read the LP row.** Use `gsuite.sheets_read` on spreadsheet_id `1ZeYXnEjTEEDpJuLuYevgO8Xhj-H7tx7JnwcSU4a-X1A`, range_notation `"P3 Tracker!A20:T200"` (row 20 is the header). Find the row where column B (Investor) matches the LP. Capture and use:
- **H** Ticket Low, **I** Ticket High — sizing range
- **J** P3 Probability, **K** IOI Status — firmness signal. If J shows "Closed" or K shows "Closed"/"Final" with a confirmed amount, the sizing is NOT an estimate.
- **P** Prior Meetings (free-text touchpoint log, e.g. `"2/27 @ 1pm\n3/25 LS email\n4/3 call\n4/28 AP/MH/LS final diligence meeting with Matt Libel/Ryan"`)
- **Q** Next Meeting, **R** Last Mtg, **T** Notes/Action Item — pre-meeting context

**How to use these (cross-check, not primary):**
- Sizing: this IS the primary source — use H/I/J/K directly.
- **Prior meetings: Attio (step f) is the primary source.** Use column P only as a CROSS-CHECK. If column P contains a meeting that Attio does not, surface it in the prior-meetings list with annotation `(per P3 tracker — not in Attio)`, and add a one-line flag to yourself in the memo's footer like `Data gap: Attio missing tracker-recorded touchpoint(s) on [date(s)] — flag for IR ops.` This makes the data pipeline gap visible rather than papering over it.
- Purpose / Proposed Agenda: column T and column Q are useful supplements to Slack/Gmail context — fold them in if they add substance.
- Attendee inference: if the calendar lookup fails AND column P (or Q) has a same-day entry naming attendees, use it for the inferred-attendee fallback.

**This spreadsheet will be deprecated after June.** Once Attio is fully accurate, the cross-check from columns P/Q/R/T should be removed and only sizing (H/I/J/K) — or its successor source — should remain. The annotations and footer flag exist precisely to surface the Attio gaps that need closing before deprecation.

**d. Purpose and agenda** — Search Slack and Gmail for recent threads mentioning the specific organization name or attendee names. Look for why this meeting is happening and any pre-discussed agenda.

**e. LP attendee research** — For each external attendee: find their LinkedIn profile URL, title, and prior organizations/roles. If LinkedIn is not found, search public bios on the organization's website, speaker profiles, conference pages, and press mentions — and link to whichever of those is the best available source. Do NOT explicitly note that LinkedIn was not found; simply use the best profile URL you have.

**The URL must actually point to something about that specific person** — a LinkedIn profile, a bio page, a conference speaker page, or a press article that features them. Do NOT link to the organization's generic homepage or "About" page as a fallback. If no person-specific URL can be found, render the name as plain text (no link) rather than linking to the org homepage.

**Also do a quick Google News search for each attendee** (one search per person, `"<name>" <org>`). **Always capture substantive third-party content that helps understand the person** — e.g., podcast interviews, in-depth profiles, conference talks, magazine/newspaper feature articles, or interviews where they discuss their views, strategy, or background. Include as a sub-bullet under the person's name with a short description and link.

**Quality bar — what counts:**
- ✅ Podcast interview where they discuss their investment philosophy (e.g. Money Maze interview with the OUem CIO)
- ✅ Profile piece in the FT, WSJ, Bloomberg, Institutional Investor, or similar
- ✅ Recorded conference talk or fireside chat
- ✅ Long-form interview on the org's own site if it covers their views/background substantively
- ❌ Press releases or PR announcements (e.g. "X promoted to CIO")
- ❌ LinkedIn posts
- ❌ Routine news mentions
- ❌ Anything that just restates a fact already in the LP overview — the sub-bullet must add NEW context beyond what's covered above

**Always prefer text/transcript over audio or video where both exist.** For the same content (e.g. a podcast episode), prefer the transcript, blog summary, or write-up — text is much faster to scan ahead of a meeting than listening to a 60-minute podcast. Concrete example: for the Money Maze podcast with Neamul Mohsin, link to the blog write-up at `https://www.moneymazepodcast.com/blog/neamul-mohsin` rather than the audio episode page. Only link to the audio/video if no text version exists.

If you find something good, **always include it** — these articles are extremely valuable for meeting prep. If nothing substantive exists for an attendee, skip the sub-bullet entirely (do not pad).

**f. Meeting history** — Look up the organization in Attio and pull its **complete** associated interactions list. This Attio query is **mandatory and critical** — do not skip it, shorten it, or accept a partial response. Attio is the canonical record of meetings; if it errors, retry once before giving up. Use **this specific entity** (not the broader parent organization unless they are the same). Do not cross-reference Google Calendar, Granola, or Notion separately — the Attio record links to those.

**How to query Attio for meeting history:**
- Use `query_records` on the `companies` object filtered by name to get the org's record ID. If the canonical name returns `[]`, try the short alias (e.g. "OUem" instead of "Oxford University Endowment Management").
- Then use **`list_meetings`** filtered by that company record (or by the linked person records) to get the full meeting list. This is the canonical method — do NOT scrape rollup fields.
- For threads/emails (only if you need them for the relationship-history pieces), use `list_threads` and `get_thread`. For call transcripts, `list_call_recordings` and `get_call_transcript`.

**Paradigm-side name resolution:**
- Call `list_workspace_members` once to get a UUID-to-name mapping for all Paradigm members.
- Resolve every Paradigm `workspace_member_id` you encounter to a real name (Matt Huang, Alana Palmedo, etc.) before writing the memo.
- Do NOT output raw UUIDs in the final memo, and do NOT fall back to "+ Paradigm" — name resolution is now reliable, so always use the actual name.

**What counts as a "meeting":** Any entry that represents a real-time conversation — in-person meetings, Zoom calls, scheduled phone calls, Granola-recorded meetings, dial-ins. Exclude only entries that are clearly email threads or asynchronous message exchanges with no live component. When ambiguous, include it.

**Pull the FULL history for lookup, but DISPLAY only the 3 most recent.** Query Attio for all interactions going back years. Older meetings still matter for the lookup (they inform the relationship-history bullet below), but the displayed meeting list is capped at 3.

**Prior meetings list — 3 most recent only:** Output the **3 most recent prior in-person/Zoom/scheduled-phone meetings between Paradigm and the org**, regardless of who on either side attended. Sort newest to oldest, take the top 3, and STOP. Do not list older meetings even if Attio has them. For each of the 3:
- Date
- Who from the org
- Who from Paradigm — **always identify by name** (Matt Huang, Alana Palmedo, etc.). Never write "+ Paradigm" as a placeholder. If the Attio record is vague, open the linked notes/Granola transcript/calendar event to find the specific names. Only write "+ Paradigm attendees not recorded" as a last resort.
- 1–2 sentence summary of key focus areas, pulled from Attio notes or Granola notes if available. Skip if no notes exist.

**Relationship bullet:** After the 3-meetings list, add ONE bullet that ALWAYS starts with the literal question, **with only the question portion bolded (not the answer)**: **"Have Paradigm attendees previously connected with the LP attendees?"** followed by a one-line summary in plain (non-bold) text that pulls from the FULL Attio history (not just the 3 displayed). Use one of these answer shapes:
- Met 3+ times in person/Zoom/phone: `"Yes, many times; last meeting [date]"`
- Met once or twice in person/Zoom/phone: `"Yes, [N] time(s); last meeting [date]"`
- No live meetings, but email/correspondence on file: `"Yes, but only email"`
- No connection at all: `"No"`

This is about whether THIS upcoming meeting's specific Paradigm attendees have connected with THIS upcoming meeting's specific LP attendees — not the broader org-to-org history.

**Fallbacks:**
- If live meetings exist → list them per above.
- If no live meetings exist → "**Prior meetings:** none".

### 3. Assemble the memo

Output the briefing in exactly this format:

---

**[Client/Prospect Name]**

[Zoom or In-Person] at [Time, Day Month Year]
[For in-person meetings ONLY, add this line: [Address](Google Maps URL). For Zoom meetings, omit this line entirely.]

**Purpose:**
- [Use only as many bullets as there is substance for — 1 bullet is fine if that's all the context supports. Do NOT pad with generic "mutual intro" or "overview of Paradigm" filler. If you can only write generic filler, use a single bullet, or write "unknown — no pre-meeting context found in Slack/Gmail".]

**Proposed agenda:**
- [Same rule — match bullet count to actual substance. If no clear agenda was pre-discussed, write a single bullet or "unknown". Do NOT invent a multi-bullet agenda from thin air.]

**Paradigm attendees:**
- [Name]
- [Name]

**LP overview and relationship:**
- [3–5 sentence substantive description of the entity: ownership, mandate, strategies, asset classes, scale, notable news]
- Existing Paradigm investments:
  - Total commitments / NAV+unfunded: [$ total commitments across all funds] / [$ total NAV + unfunded across all funds] (TVPI: [relationship-level TVPI])
    - PF: [$ commitment] / [$ NAV + unfunded] (TVPI: [PF TVPI])
    - P1: [$ commitment] / [$ NAV + unfunded] (TVPI: [P1 TVPI])
    - P2: [$ commitment] / [$ NAV + unfunded] (TVPI: [P2 TVPI])
    - P3: [$ commitment] / [$ NAV + unfunded] (TVPI: [P3 TVPI])
  - (Omit any fund-level sub-bullet for funds the LP is not invested in. If the LP has no existing investments at all, replace this entire block with a single line: "Existing Paradigm investments: none")
- Potential sizing: [amount from spreadsheet, note if firm or estimate, OR "unknown" if not found]

**LP attendees:**
- [Hyperlinked Name](best available profile URL) ([prior org / time there if available])
  - [Optional sub-bullet — only if a substantive news article, interview, podcast, or profile piece exists: short description and link]

**Prior meetings:** (3 most recent in-person, Zoom, or scheduled phone calls per Attio)
- [Most recent date] — [who from org] + [who from Paradigm by name]
  - [1–2 sentence summary of key focus areas from Attio or Granola notes, if notes exist. Omit this sub-bullet if no notes are available.]
- [Second most recent date] — [who from org] + [who from Paradigm by name]
  - [1–2 sentence summary if notes available]
- [Third most recent date] — [who from org] + [who from Paradigm by name]
  - [1–2 sentence summary if notes available]
- **Have Paradigm attendees previously connected with the LP attendees?** [Answer in plain (non-bold) text: "Yes, many times; last meeting [date]" / "Yes, [N] time(s); last meeting [date]" / "Yes, but only email" / "No"]

(Fallback: if no live meetings exist → "**Prior meetings:** none" — but still include the "Have Paradigm attendees previously connected with the LP attendees?" bullet with the appropriate answer.)

---

## Output Rules

- Keep it tight — this is a memo, not a report
- **Meeting times:** Always show Pacific Time (PT) — convert from whatever timezone the calendar event is stored in. Use "PT" as the label (e.g. "11:30 AM PT"). For in-person meetings, also show the meeting's local time before PT (e.g. "9:00 AM BST / 1:00 AM PT"). For Zoom meetings, show PT only.
- Hyperlink LP attendee names to their best available public profile (LinkedIn preferred; fall back to org bio page, speaker profile, or press article). Do not mention the absence of LinkedIn.
- **Use concise fallback language** when data is missing:
  - No existing Paradigm investments → "none"
  - No potential sizing found → "unknown"
  - No prior meetings found → "none"
  - Do NOT write "not found in [source]" in the final memo — that is internal research language
- If sizing is confirmed (closed or IOI), do NOT label it as an estimate
- Do not invent meeting notes or relationship history — only include what you find
