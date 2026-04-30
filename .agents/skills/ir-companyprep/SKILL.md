---
name: ir-companyprep
description: "Creates IR company prep Google Docs for portfolio companies. Triggers ONLY on explicit command: 'ir-companyprep <Company Name>'. Generates a Google Doc artifact using python-docx with investment summary, financing history, key metrics, and thesis, sourced from Shift, BigQuery, StandardMetrics, and CoinGecko. DO NOT USE when running the invest persona (--invest) — the invest persona handles diligence in-thread with its own Phase 1 / Phase 2 flow, not via a Google Doc artifact. DO NOT USE for general 'brief me on X' or 'diligence on X' requests — this skill is exclusively for the 'ir-companyprep <Name>' IR-meeting-preparation workflow."
---

# IR Company Prep Memo

Creates a pre-populated Google Doc for IR meetings using python-docx to clone and fill the template with proper formatting.

## Centaur Translation Layer

This skill was ported from the ops repo. In Centaur, translate the original command references onto Centaur tools instead of trying to run them literally.

- Treat `reshift db` as `call paradigmdb db_query` or a more specific `paradigmdb` method when one exists.
- Treat `reshift bq` as `call paradigmdb bq_query`.
- Use `call discover paradigmdb` before first use if you need the exact method signature.
- Use `call discover gsuite` before creating or updating the memo in Google Docs or Drive.
- Prefer `call coingecko` and `call defillama` over raw web requests when those tools cover the needed data.

## Trigger

```
ir-companyprep <Company Name>
ir-companyprep top <N>              # Top N by MV across all funds
ir-companyprep top <N> <Fund>       # Top N by MV for a specific fund (PF, P1, P2)
```

### Batch Mode (top N)

When triggered with `top`, query BQ for the largest positions by current market value:

```bash
reshift bq "SELECT organizationName, fundName, SUM(holdingMarketValue) as total_mv FROM daily_performance_view WHERE day = (SELECT MAX(day) FROM daily_performance_view) AND fundName = '<Fund Name>' AND holdingMarketValue > 0 GROUP BY organizationName, fundName ORDER BY total_mv DESC LIMIT <N>;" -n <N>
```

If no fund specified, get top N across all funds:

```bash
reshift bq "SELECT organizationName, SUM(holdingMarketValue) as total_mv FROM daily_performance_view WHERE day = (SELECT MAX(day) FROM daily_performance_view) AND holdingMarketValue > 0 GROUP BY organizationName ORDER BY total_mv DESC LIMIT <N>;" -n <N>
```

Then generate a memo for each company sequentially, sharing the link after each one.

## Target Folder

All generated docs go to: `1SPLOVDjwNq6L4Ck7D8xavNY-lcSyi_4z`

## CRITICAL RULES

1. **Cost basis ALWAYS from BQ `daily_performance_view.grossinvestedcapital`** — NEVER compute from shares × price
2. **Check ALL funds** — PF, P1, P2 — the company may have investments across multiple funds
3. **Aggregate token symbol variations** — e.g., HYPE + HYPE_HYPERCORE + HYPE_HYPEREVM
4. **Use today's date** for current values; use the most recent `day` in BQ that has data
5. **TVL from DefiLlama** — always use `call defillama tvl` for TVL data
6. **Detect position type first** (Step 2c) — `MEMO_TYPE` controls which sections to include, which columns to use, and which data sources to query. Do not guess the type; derive it from BQ data.
7. **Financing History**: show actual TWAP date ranges (not "Various"), NO total row. Column headers and table structure vary by `MEMO_TYPE` (see Step 4c).
8. **Key Metrics**: omit for `token_only`; use EODHD for `public_equity`; use StandardMetrics for `equity_only` and `equity_token`
9. **Token Position section**: include only for `token_only` and `equity_token`
10. **Investment Thesis**: include for all types except `token_only` — only include for `token_only` if a specific position memo exists in investmemos
11. **Keep with next**: apply `keepNext` paragraph property to ALL section headers so they don't split from their tables across pages

## Data Gathering

### Step 1: Look Up Company

```bash
reshift db "SELECT id, name, description, \"founderName\", \"homepageUrl\", category, \"foundedOn\" FROM \"Organization\" WHERE LOWER(name) LIKE LOWER('%<Company>%') AND deleted_at IS NULL LIMIT 5;"
```

Then build a robust Company Overview description from three sources in priority order:

1. **investmemos** — search for the company memo to extract the core description, sector framing, and founding context:
```bash
call investmemos search_memos '{"query": "<Company>", "limit": 5}'
# Then read the most relevant memo:
call investmemos read_memo '{"memo": "<memo_id_or_name>", "max_chars": 4000}'
```

2. **Company website** — read the homepage for current product framing and positioning:
```bash
call read_web_page '{"url": "<homepageUrl from Shift>"}'
```

3. **Shift description** — use as fallback or to fill gaps.

Synthesize into a 1-2 sentence description that reflects the company's current positioning. Prefer memo language for the investment angle, website language for product/market framing. If sources conflict, prefer the most recent.

### Step 2: Get Investment Summary (BQ)

**CRITICAL**: Total Cost = `grossinvestedcapital`, NOT shares × price.

```bash
reshift bq "SELECT fundName, assetName, assetType, assetTicker, holding, holdingMarketValue, grossinvestedcapital, grossrealizedvalue FROM daily_performance_view WHERE LOWER(organizationName) LIKE LOWER('%<Company>%') AND day = (SELECT MAX(day) FROM daily_performance_view WHERE LOWER(organizationName) LIKE LOWER('%<Company>%')) ORDER BY fundName, assetName;" -n 50
```

Compute per fund and total:
- **Total Cost**: SUM of `grossinvestedcapital`
- **Current Mkt Value**: SUM of `holdingMarketValue`
- **Realized**: SUM of `grossrealizedvalue` **+ dividends/interest** (see Step 2b)
- **MOIC**: (SUM(holdingMarketValue) + Realized) / SUM(grossinvestedcapital)

### Step 2b: Get Dividend & Interest Payments

**CRITICAL**: `grossrealizedvalue` in `daily_performance_view` does NOT include dividend or interest payments. These are tracked as separate `DIVIDEND_PAYMENT` or `INTEREST_PAYMENT` transactions in `transactions_csv`. Always query and add them to the Realized column.

```bash
reshift bq "SELECT fund, SUM(CASE WHEN assetName = 'USD' THEN assetQuantity ELSE 0 END) as total_payments, COUNT(*) as num_payments FROM transactions_csv WHERE LOWER(assetNames) LIKE LOWER('%<Company>%') AND type IN ('DIVIDEND_PAYMENT', 'INTEREST_PAYMENT') AND assetName = 'USD' GROUP BY fund ORDER BY fund;" -n 10
```

Add these amounts to `grossrealizedvalue` when computing the **Realized** column and **MOIC**:
- **Realized** = `grossrealizedvalue` + dividend/interest payments
- If no dividend/interest payments found, Realized = `grossrealizedvalue`

### Step 2c: Detect Position Type

Using the BQ results from Step 2, determine which of the four memo formats to use. This drives all conditional logic downstream.

| Type | Detection rule |
|------|---------------|
| **Public Equity** | `assetType = EQUITY` AND `assetTicker` IN (`COIN`, `HOOD`) |
| **Equity Only** | `assetType` rows are ALL `EQUITY`, not public |
| **Token Only** | `assetType` rows are ALL `TOKEN` |
| **Equity + Token** | Both `EQUITY` and `TOKEN` rows present |

Set `MEMO_TYPE` to one of: `public_equity`, `equity_only`, `token_only`, `equity_token`. All steps below reference this variable.

### Step 3: Get Entry & Current Valuation

```bash
reshift db "SELECT ov.\"timestamp\", ov.value FROM \"OrganizationValuation\" ov WHERE ov.\"organizationId\" LIKE '<orgId_prefix>%' ORDER BY ov.\"timestamp\" ASC;" -n 20
```

### Step 4: Financing History

Query BOTH Shift and BQ transactions_csv, then cross-reference. **If they differ, default to transactions_csv as the source of truth.**

**Step 4a: Get Shift financing rounds (may be incomplete or inaccurate)**

```bash
reshift db "SELECT r.name, r.series, r.date, r.\"postMoneyValuation\", r.\"pricePerShare\", f.\"shortName\" AS fund, p.shares FROM \"EquityFinancingRound\" r JOIN \"EquityFinancingParticipation\" p ON p.\"equityFinancingRoundId\" = r.id JOIN \"Fund\" f ON f.id = p.\"fundId\" WHERE r.\"organizationId\" LIKE '<orgId_prefix>%' ORDER BY r.date ASC;" -n 30
```

**Step 4b: Get BQ transactions_csv (source of truth for amounts and dates)**

Get individual transactions for detailed history:
```bash
reshift bq "SELECT fund, assetName, executedDate, type, ROUND(assetQuantity, 2) as qty, ROUND(assetPriceInUSD, 4) as price, ROUND(assetQuantity * assetPriceInUSD, 2) as amount FROM transactions_csv WHERE (LOWER(assetNames) LIKE LOWER('%<Company>%') OR LOWER(assetName) LIKE LOWER('%<ticker>%')) AND assetName NOT LIKE '%USD%' ORDER BY fund, executedDate;" -n 50
```

Also get summary aggregates:
```bash
reshift bq "SELECT fund, assetName, type, MIN(executedDate) as first_date, MAX(executedDate) as last_date, COUNT(*) as num_trades, ROUND(SUM(assetQuantity * assetPriceInUSD) / NULLIF(SUM(assetQuantity), 0), 2) as avg_price, ROUND(SUM(assetQuantity * assetPriceInUSD), 2) as total_amount FROM transactions_csv WHERE (LOWER(assetNames) LIKE LOWER('%<Company>%') OR LOWER(assetName) LIKE LOWER('%<ticker>%')) AND assetName NOT LIKE '%USD%' GROUP BY fund, assetName, type ORDER BY fund, type, assetName;" -n 30
```

**Step 4c: Cross-reference and resolve conflicts**

**CRITICAL — each data source is authoritative for different things:**

For **equity rounds** (PRIVATE_INVESTMENT):
- **Round name, date, and valuation**: Use Shift `EquityFinancingRound` — it has the canonical round metadata (series name, round date, post-money valuation) that transactions_csv lacks
- **Amount invested**: Use `SUM(assetQuantity * assetPriceInUSD)` from transactions_csv, NOT Shift's `shares * pricePerShare`
- **Rounds with no new capital** (e.g., re-pricings, share class conversions): Still include in the financing table if they appear in Shift — note "$0 (re-pricing)" in the amount column to show the valuation step-up
- **If Shift has rounds not in transactions_csv**: Include with "TBD" for amount, flag to user
- **If transactions_csv has entries not in Shift**: Include them — transactions_csv is authoritative for amounts

For **open market token purchases** (TRADE, TWAP):
- **Dates**: Use actual `executedDate` range from transactions_csv (Shift has no round-level data for these)
- **Price**: Use avg `assetPriceInUSD` from transactions_csv
- Group related transactions (e.g., same fund/asset/type within a short window) into logical entries

**Never fabricate round dates.** If transactions_csv shows a different execution date than Shift's round date, use Shift's round date for the financing table (it reflects the official round close date). Only use transactions_csv dates for open market purchases where no Shift round exists.

For the financing table — column structure varies by `MEMO_TYPE`:

- **`equity_only` / `public_equity`**: `Round | Date | Fund | Amount Invested | Valuation | Instrument`
- **`token_only`**: `Type | Date | Fund | Amount Invested | Avg. Cost/Token | Instrument`
- **`equity_token`**: Merge all rows chronologically into one table: `Round/Type | Date | Fund | Amount Invested | Valuation / Avg. Cost | Instrument`. Equity rows show post-money valuation; token rows show avg cost per token in the same column. Sort all rows by date ascending.

Rules that apply to all types:
- **Date column**: For equity rounds, use the round date from `EquityFinancingRound`. For token purchases, show actual TWAP date ranges (e.g., "02/2025 – 03/2026"), not "Various"
- **NO total row** — the per-fund summary table in Investment Summary handles totals
- Exclude CONVERSION_IN/CONVERSION_OUT transactions (these are reclassifications, not new capital)

### Step 5: Token Position (if applicable)

**Skip entirely for `equity_only` and `public_equity`.** Only run for `token_only` and `equity_token`.

Use `coingecko search` / `coingecko coin` for price/mkt cap/FDV.

**TVL**: Always use DefiLlama:
```bash
call defillama tvl '{"protocol": "<protocol_slug>"}'
```

Check `StakingOverride` for staking data and VEST transactions for vesting.

**Sources line**: Add below the token table in 8pt grey text:
`Sources: CoinGecko (price, mkt cap, FDV), DefiLlama (TVL), Shift/BQ (holdings, cost basis), StakingOverride (staking)`

### Step 6: Investment Thesis & MIQs

Use `investmemos` as the primary source. Search for the company memo, read it, and extract the investment thesis and MIQs directly:

```bash
call investmemos search_memos '{"query": "<Company>", "limit": 5}'
# Then read the most relevant memo:
call investmemos read_memo '{"memo": "<memo_id_or_name>", "max_chars": 12000}'
```

If the memo contains explicit MIQs, use them verbatim. If not, use `build_miq_context` to surface the most relevant thesis threads:

```bash
call investmemos build_miq_context '{"opportunity": "<Company>", "miqs": ["<MIQ 1>", "<MIQ 2>", "<MIQ 3>"], "memos_per_miq": 2, "excerpt_chars": 1200}'
```

**Fallback** — if no memo found in investmemos, query Shift notes directly:
```bash
reshift db "SELECT n.id, n.title, n.\"noteType\", n.created_at FROM \"Notes\" n JOIN \"_NotesToOrganization\" no ON no.\"A\" = n.id JOIN \"Organization\" o ON o.id = no.\"B\" WHERE LOWER(o.name) = '<company_lower>' ORDER BY n.created_at DESC LIMIT 10;"
```
Read relevant notes with `reshift db` to get note text (HTML), strip tags with `regexp_replace(notes, E'<[^>]+>', '', 'g')`.

**`token_only` exception**: For token-only positions, the Investment Thesis section is omitted by default — open market purchases typically don't have a formal investment memo. Include it ONLY if `investmemos search_memos` returns a memo that is specifically about this token position (not a general crypto/market memo). If no specific memo is found, remove the Investment Thesis section entirely from the document.

**IMPORTANT**: For all other types, if no thesis source is found anywhere, write "No investment thesis notes found — please add manually" in the document.

### Step 7: Key Metrics

Use the format that fits the metric. For a single latest value, keep text. For ≥3 historical periods of the same metric (ARR, revenue, TVL, DAU, volume, retention, margin), use a tiny inline PNG sparkline (60-80 pt wide, 18-24 pt tall) in the Trend column so the reader can see trajectory at a glance. For mixed-unit company metrics, do **not** force a combined chart; use the table plus per-row sparklines where history exists.

Generate each sparkline with the chart tool:

```bash
call chart render_chart '{"chart_type": "sparkline", "data": [{"period": "<period>", "value": <value>}, ...], "x": "period", "y": "value", "protagonist": "<metric_name>", "title": "<metric_name> trend"}'
```

Upload the returned PNG bytes and insert via `gsuite drive_upload` + `gsuite docs_insert_inline_image`. Keep a short numeric delta only when it adds decision-useful context (for example, "+18% QoQ").

Key Metrics source depends on `MEMO_TYPE`:

**`equity_only` / `equity_token`** — use StandardMetrics:
```bash
reshift db "SELECT m.category, m.value, m.date, m.cadence, m.detailed_source FROM \"StandardMetricsMetrics\" m JOIN \"StandardMetricsCompany\" c ON c.id = m.\"smCompanyId\" WHERE LOWER(c.name) LIKE LOWER('%<Company>%') AND m.archived = false ORDER BY m.category, m.date DESC;" -n 100
```

**`token_only`** — **omit Key Metrics section entirely.** Remove the section header and table from the document.

**`public_equity`** — use EODHD for public financial data. Run `call discover eodhd` to get the exact method signatures, then pull:
- Revenue, net income, EPS (most recent quarter + YoY trend)
- Stock price performance (vs. entry price)
- Market cap, P/E, P/S ratios
- Trading volume

```bash
call eodhd fundamentals '{"ticker": "<TICKER>", "exchange": "US"}'
```

Populate the Key Metrics table with the most relevant public financials. Label source as "EODHD" in the Source column.

### Step 8: Expectations

Build the Expectations section in two layers:

**Layer 1 — investmemos baseline (original thesis expectations)**

Search for any PORTCO_REVIEW, update memos, or follow-on memos that describe how the investment is tracking vs. thesis:

```bash
call investmemos search_memos '{"query": "<Company> performance update", "limit": 5}'
call investmemos search_memos '{"query": "<Company> portco review", "limit": 5}'
```

Read the most relevant results to extract: what was expected at investment, what key milestones were set, and any recorded thesis updates.

**Layer 2 — Shift notes for updated performance context**

Query PORTCO_REVIEW / PORTCO_UPDATE notes for the most recent performance commentary:

```bash
reshift db "SELECT n.id, n.title, n.\"noteType\", n.created_at FROM \"Notes\" n JOIN \"_NotesToOrganization\" no ON no.\"A\" = n.id JOIN \"Organization\" o ON o.id = no.\"B\" WHERE LOWER(o.name) = '<company_lower>' AND n.\"noteType\" IN ('PORTCO_REVIEW', 'PORTCO_UPDATE') ORDER BY n.created_at DESC LIMIT 5;"
```

**When both layers are sparse, also search Slack** for supplementary investment team commentary:

```bash
call slack search_messages '{"query": "<Company>", "channels": ["investment-talk", "portfolio-gtm", "research", "analyzooors"], "max_results": 10}'
```

Synthesize: use the investmemos baseline to frame what was expected, then layer in Shift notes and Slack to describe current performance vs. those expectations.

**IMPORTANT**: The Expectations section should ONLY focus on how the company is performing vs. the original investment thesis. Do NOT include:
- Finance/valuation team operational commentary (valuation discrepancies, portco info requests)
- IR reporting issues
- Talent/recruiting discussions

Only include investment team perspectives on the company's actual performance, market position, product traction, and competitive dynamics relative to what was expected at time of investment.

## Document Generation

**IMPORTANT**: Do NOT use `gsuite docs create --content` (produces plain text with no formatting). Instead, use python-docx to clone the template and fill it, then upload via the Google Drive API with MIME type conversion.

### Template Location

Download the template first:
```bash
gsuite -a svc_ai@paradigm.xyz drive export "1CE1xLuUzLYttRnpqBOCntOwUX3I85SD1vomSFG-43IY" -f docx -o /tmp/ir_template.docx
```

### Formatting Rules

1. **All font colors must be BLACK** (`RGBColor(0, 0, 0)`) — the template has grey #666666, override everything
2. **All body text must be 9pt** — Company Overview identifier/description lines and Investment Summary lines are 9pt. Thesis, Key Questions, and Expectations body text are 10pt. Table cell text is 9pt. Title is 14pt, section headers are 10pt bold.
3. **Section headers**: The template already has bottom borders (`pBdr > bottom` with `val=single, sz=4, color=333333`) on all section headers (Company Overview, Investment Summary, Token Position (if applicable), Investment Thesis, Paradigm Financing History, Key Metrics, Expectations). Do NOT re-add borders; just preserve them. Headers are bold, black.
4. **No excess blank space**: Remove all blank paragraphs between sections. Each section flows directly: Header (with bottom border) → body content → next header. No extra blank lines.
5. **Company Overview**: identifier line (Name · Sector · URL · Founders) on one line, description on a **separate** line below
6. **Investment Summary**: header with bottom border, then summary line (`Funds · Asset · MOIC · Wt...`), then per-fund table with borders. The summary line includes portfolio weight (`Wt: X.X%`). The per-fund table has **5 columns**: `Fund | Total Cost | Current Mkt Value | Realized | MOIC` (the template now includes a Realized column).
7. **Token Position**: Include only for `token_only` and `equity_token`. Remove the section header and table entirely for `equity_only` and `public_equity` — do NOT leave a "No token position." placeholder. When included: token table (7-col, 9pt, borders) with columns `Token | Price at Entry | Current Price | Mkt Cap at Entry | Current Mkt Cap | FDV | TVL` + Sources line (8pt grey).
8. **All tables**: must have visible borders (`tblBorders` with single/4/000000 for top, left, bottom, right, insideH, insideV). Remove all background shading. All cell text 9pt. Bold header row. Bold Total row if present. **Tables must be full page width** (`tblW` w=5000, type=pct).
9. **Financing History table**: NO subtotal/total rows, NO background shading, all text 9pt font. Column structure by type:
   - `equity_only` / `public_equity`: `Round | Date | Fund | Amount Invested | Valuation | Instrument`
   - `token_only`: `Type | Date | Fund | Amount Invested | Avg. Cost/Token | Instrument`
   - `equity_token`: `Round/Type | Date | Fund | Amount Invested | Valuation / Avg. Cost | Instrument` — all rows merged and sorted chronologically by date
10. **Key Metrics table**: omit entirely for `token_only` (remove header + table). For `public_equity`, populate with EODHD data (revenue, net income, EPS, stock performance). For `equity_only` and `equity_token`, use StandardMetrics.
11. **Keep with next**: apply `keepNext` to all section headers so they stay with their tables across page breaks
12. **Upload as .docx** with Google Docs MIME type conversion for native Google Doc

### Python Generation Pattern

```python
from docx import Document
from docx.shared import Pt, RGBColor
from copy import deepcopy

doc = Document('/tmp/ir_template.docx')
BLACK = RGBColor(0, 0, 0)
NSMAP_W = 'http://schemas.openxmlformats.org/wordprocessingml/2006/main'

def set_cell_text(cell, text, bold=None):
    para = cell.paragraphs[0]
    if para.runs:
        para.runs[0].text = text
        para.runs[0].font.color.rgb = BLACK
        if bold is not None:
            para.runs[0].bold = bold
        for run in para.runs[1:]:
            run.text = ""

def set_para_text(para, text):
    if para.runs:
        para.runs[0].text = text
        para.runs[0].font.color.rgb = BLACK
        for run in para.runs[1:]:
            run.text = ""

def remove_para(para):
    para._element.getparent().remove(para._element)

def remove_all_shading(table):
    for el in table._tbl.iter(f'{{{NSMAP_W}}}shd'):
        el.getparent().remove(el)

# 1. Set ALL text to black
for para in doc.paragraphs:
    for run in para.runs:
        run.font.color.rgb = BLACK
for table in doc.tables:
    for row in table.rows:
        for cell in row.cells:
            for para in cell.paragraphs:
                for run in para.runs:
                    run.font.color.rgb = BLACK

# 2. Remove blank paragraphs
for i in reversed(range(len(doc.paragraphs))):
    if doc.paragraphs[i].text.strip() == '':
        remove_para(doc.paragraphs[i])

# 3. Fill paragraphs by finding them by content
# After removing blank paragraphs, the paragraph indices shift. Find paragraphs
# by matching text content rather than hardcoded indices.
# Title (P0): "IR Company Prep Memo: <Company>  ·  <Date>"
# Company Overview header (P1): keep as-is (already has bottom border from template)
# Overview identifier (P2): "<Name> · <Sector> · <URL>. Founded by <Names>."
# Overview description (P3): "<1-2 sentence description>"
# Investment Summary header (P4): keep as-is (already has bottom border from template)
# Summary line (P5): "Funds: <Funds>  ·  Asset: <Type>  ·  MOIC: <X.Xx>x  ·  Wt: <X.X>%  Entry Valuation: $<X>  ·  Current Valuation: $<X>"
# Token Position header (P6): "Token Position (if applicable)" — keep as-is
# Token body (P7): "Staked: <Y/N>  ·  Vesting: <Details>" or "No token position."
# Investment Thesis header (P8): keep as-is
# Thesis body (P9): 10pt text
# Key Questions (P10): 10pt text
# Paradigm Financing History header (P11): keep as-is
# Key Metrics header (P12): keep as-is
# Expectations header (P13): keep as-is
# Expectations body (P14): 10pt text

# 4. Fill Investment Summary table (Table 0) — template has 5 cols:
# Fund | Total Cost | Current Mkt Value | Realized | MOIC
# Add rows with deepcopy as needed for multiple funds, bold Total row

# 5. Fill Token Position table (Table 1) — template has 7 cols:
# Token | Price at Entry | Current Price | Mkt Cap at Entry | Current Mkt Cap | FDV | TVL
# Remove token table if no token (find 7-col table, remove its XML element)

# 6. Financing History table (Table 2):
# - For token purchases: rename "Valuation" header to "Avg. Cost/Token", show TWAP date ranges
# - For equity rounds: keep "Valuation" column and MM/YYYY dates
# - Add/remove rows as needed. NO total rows
# - remove_all_shading(fin_table), set all fonts to Pt(9)

# 7. Key Metrics table (Table 3): fill and remove shading
# - OMIT entirely for open market token purchases (remove header paragraph + table)

# 8. Sources line: add after token table in 8pt grey
# "Sources: CoinGecko (price, mkt cap, FDV), DefiLlama (TVL), Shift/BQ (holdings, cost basis), StakingOverride (staking)"

# 9. Keep with next: template already has borders on headers; just add keepNext
# for p in doc.paragraphs:
#     if p is a section header:
#         pPr = p._element.get_or_add_pPr()
#         etree.SubElement(pPr, f'{{{W}}}keepNext')

# 10. Final pass: ensure ALL text black, ALL shading removed
```

### Upload & Share

Upload with Google Drive API for native Google Doc conversion:

```python
import json
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload

with open("/root/.config/gsuite/tokens/svc_ai@paradigm.xyz.json") as f:
    token_data = json.load(f)

creds = Credentials(
    token=token_data.get("token"),
    refresh_token=token_data.get("refresh_token"),
    token_uri=token_data.get("token_uri", "https://oauth2.googleapis.com/token"),
    client_id=token_data.get("client_id"),
    client_secret=token_data.get("client_secret"),
    scopes=token_data.get("scopes")
)

service = build('drive', 'v3', credentials=creds)
file_metadata = {
    'name': 'IR Company Prep Memo: <Company> [MM/DD/YYYY]',  # Use today's date
    'mimeType': 'application/vnd.google-apps.document',
}
media = MediaFileUpload('/tmp/<company>_ir_prep.docx',
    mimetype='application/vnd.openxmlformats-officedocument.wordprocessingml.document',
    resumable=True)
file = service.files().create(body=file_metadata, media_body=media, fields='id, webViewLink').execute()
```

Then share and transfer ownership:
```bash
gsuite -a svc_ai@paradigm.xyz drive share "<doc_id>" "lindsay@paradigm.xyz"
gsuite -a svc_ai@paradigm.xyz drive transfer-ownership "<doc_id>" "lindsay@paradigm.xyz"
```

After uploading, copy the doc into the target folder (Shared Drive):
```python
service.files().copy(
    fileId='<doc_id>',
    body={
        'name': 'IR Company Prep Memo: <Company> [MM/DD/YYYY]',
        'parents': ['1SPLOVDjwNq6L4Ck7D8xavNY-lcSyi_4z']
    },
    supportsAllDrives=True,
    fields='id, webViewLink'
).execute()
```
Note: Moving files into a Shared Drive is restricted by domain policy; use `files().copy()` instead.

## Document Structure

Structure varies by `MEMO_TYPE`. All types share the same header block and Investment Summary. Differences are noted per section.

### Shared header (all types)

```
IR Company Prep Memo: <Company> [MM/DD/YYYY]  ·  <Date>    [bold, 14pt, Inter]

Company Overview                               [bold, Inter, bottom border]
<Name> · <Sector> · <URL>. Founded by <Names>. [9pt, Inter]
<1-2 sentence description on its own line.>    [9pt, Inter, not bold]

Investment Summary                             [bold, Inter, bottom border]
Funds: <Funds>  ·  Asset: <Type>  ·  MOIC: <X.Xx>x  ·  Wt: <X.X>%  Entry Valuation: $<X>  ·  Current Valuation: $<X>

┌──────┬────────────┬───────────────────┬──────────┬───────┐
│ Fund │ Total Cost │ Current Mkt Value │ Realized │ MOIC  │  ← bold header
├──────┼────────────┼───────────────────┼──────────┼───────┤
│ PF   │ $X.XM      │ $X.XM             │ $X.XM    │ X.Xx  │
│ Total│ $X.XM      │ $X.XM             │ $X.XM    │ X.Xx  │  ← bold
└──────┴────────────┴───────────────────┴──────────┴───────┘
```

---

### `equity_only`

```
[Shared header above]

Investment Thesis                              [bold, Inter, bottom border]
<Distilled thesis from investmemos>
Key Questions: <MIQ 1>  ·  <MIQ 2>  ·  <MIQ 3>

Paradigm Financing History                     [bold, Inter, bottom border]
┌──────────┬─────────┬──────┬─────────────┬───────────┬────────────┐
│ Round    │ Date    │ Fund │ Amt Invested│ Valuation │ Instrument │
├──────────┼─────────┼──────┼─────────────┼───────────┼────────────┤
│ Series A │ 06/2022 │ PF   │ $20.0M      │ $200M     │ Pref Equity│
└──────────┴─────────┴──────┴─────────────┴───────────┴────────────┘

Key Metrics                                    [bold, Inter, bottom border]
┌──────────────┬──────────────┬─────────┬──────────────┬──────────────────┐
│ Metric       │ Latest Value │ Period  │ Trend        │ Source           │
│ Revenue / ARR│ $X.XM        │ Q1 2026 │ Up (X% QoQ)  │ Standard Metrics │
└──────────────┴──────────────┴─────────┴──────────────┴──────────────────┘

Expectations                                   [bold, Inter, bottom border]
<Performance vs. thesis>
```

---

### `equity_token`

```
[Shared header above]

Token Position (if applicable)                 [bold, Inter, bottom border]
Staked: <Y/N>  ·  Vesting: <Details>
┌────────┬────────────────┬───────────────┬──────────────────┬─────────────────┬──────┬──────┐
│ Token  │ Price at Entry │ Current Price │ Mkt Cap at Entry │ Current Mkt Cap │ FDV  │ TVL  │
└────────┴────────────────┴───────────────┴──────────────────┴─────────────────┴──────┴──────┘
Sources: CoinGecko (price, mkt cap, FDV), DefiLlama (TVL), Shift/BQ (holdings, cost basis)  [8pt grey]

Investment Thesis                              [bold, Inter, bottom border]
<Distilled thesis from investmemos>
Key Questions: <MIQ 1>  ·  <MIQ 2>  ·  <MIQ 3>

Paradigm Financing History                     [bold, Inter, bottom border]
[All rows merged chronologically — equity rounds and token purchases in one table]
┌──────────────┬──────────────────┬──────┬─────────────┬───────────────────┬────────────┐
│ Round/Type   │ Date             │ Fund │ Amt Invested│ Valuation/Avg Cost│ Instrument │
├──────────────┼──────────────────┼──────┼─────────────┼───────────────────┼────────────┤
│ Series A     │ 06/2022          │ PF   │ $20.0M      │ $200M             │ Pref Equity│
│ TWAP Purchase│ 01/2024–03/2024  │ PF   │ $50.0M      │ $1.24             │ TOKEN      │
└──────────────┴──────────────────┴──────┴─────────────┴───────────────────┴────────────┘

Key Metrics                                    [bold, Inter, bottom border]
┌──────────────┬──────────────┬─────────┬──────────────┬──────────────────┐
│ Metric       │ Latest Value │ Period  │ Trend        │ Source           │
└──────────────┴──────────────┴─────────┴──────────────┴──────────────────┘

Expectations                                   [bold, Inter, bottom border]
<Performance vs. thesis>
```

---

### `token_only`

```
[Shared header above]

Token Position (if applicable)                 [bold, Inter, bottom border]
Staked: <Y/N>  ·  Vesting: <Details>
┌────────┬────────────────┬───────────────┬──────────────────┬─────────────────┬──────┬──────┐
│ Token  │ Price at Entry │ Current Price │ Mkt Cap at Entry │ Current Mkt Cap │ FDV  │ TVL  │
└────────┴────────────────┴───────────────┴──────────────────┴─────────────────┴──────┴──────┘
Sources: CoinGecko (price, mkt cap, FDV), DefiLlama (TVL), Shift/BQ (holdings, cost basis)  [8pt grey]

[Investment Thesis — include ONLY if specific position memo found in investmemos]

Paradigm Financing History                     [bold, Inter, bottom border]
┌───────────────┬──────────────────┬──────┬─────────────┬────────────────┬────────────┐
│ Type          │ Date             │ Fund │ Amt Invested│ Avg. Cost/Token│ Instrument │
├───────────────┼──────────────────┼──────┼─────────────┼────────────────┼────────────┤
│ TWAP Purchase │ 02/2025–03/2026  │ PF   │ $355.4M     │ $24.57         │ HYPE       │
└───────────────┴──────────────────┴──────┴─────────────┴────────────────┴────────────┘

[Key Metrics — OMIT entirely]

Expectations                                   [bold, Inter, bottom border]
<Performance vs. thesis>
```

---

### `public_equity`

```
[Shared header above]

Investment Thesis                              [bold, Inter, bottom border]
<Distilled thesis from investmemos>
Key Questions: <MIQ 1>  ·  <MIQ 2>  ·  <MIQ 3>

Paradigm Financing History                     [bold, Inter, bottom border]
┌──────────┬─────────┬──────┬─────────────┬───────────┬────────────┐
│ Round    │ Date    │ Fund │ Amt Invested│ Valuation │ Instrument │
└──────────┴─────────┴──────┴─────────────┴───────────┴────────────┘

Key Metrics                                    [bold, Inter, bottom border]
┌──────────────┬──────────────┬─────────┬──────────────┬────────┐
│ Metric       │ Latest Value │ Period  │ Trend        │ Source │
│ Revenue      │ $X.XB        │ Q1 2026 │ Up (X% YoY)  │ EODHD  │
│ Net Income   │ $X.XM        │ Q1 2026 │ Up (X% YoY)  │ EODHD  │
│ EPS          │ $X.XX        │ Q1 2026 │ Up           │ EODHD  │
│ Market Cap   │ $X.XB        │ Today   │ —            │ EODHD  │
│ Stock Perf   │ +X% vs entry │ Since purchase│ —     │ EODHD  │
└──────────────┴──────────────┴─────────┴──────────────┴────────┘

Expectations                                   [bold, Inter, bottom border]
<Performance vs. thesis>
```

## Handling Missing Data

- **NEVER guess or infer uncertain data** — if a value cannot be confirmed from a reliable source, put "TBD" in the document and flag it in the response to the user
- **Valuation data**: Only use valuations from `OrganizationValuation` if the timestamp aligns with the transaction date. If timestamps don't match, put "TBD" and flag it
- **No StandardMetrics data**: Leave metric rows as "N/A" with source "Not available"
- **No token position**: Set text to "No token position" and remove the token table
- **No Shift notes for thesis**: Note "No investment thesis notes found in Shift — please add manually"
- **No valuation data**: Put "TBD" in the document
- **Company not found**: Ask the user to confirm the company name

## Formatting Guidelines

- Dollar amounts: `$X.XM` or `$X.XB` (e.g., $5.2M, $1.3B)
- MOIC: Two decimal places (e.g., 3.45x)
- Dates: MM/YYYY for financing history, full date for document title
- Percentages: One decimal place (e.g., 45.2%)# Session Context

- **Date/Time**: 2026-04-23 19:15:35 UTC
- **Thread ID**: deploy-ir-1776971735
- **Platform**: dev

---
