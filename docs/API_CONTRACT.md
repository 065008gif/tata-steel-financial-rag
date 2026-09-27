# API contract addendum

Everything in Section 5 of the frontend brief remains valid and unchanged. This file only ADDS one optional endpoint.

## `GET /api/scores?scope=<consolidated|standalone>`
Composite scores for FY2021-22 to FY2025-26.
```json
{
  "scope": "consolidated",
  "years": ["FY2021-22", "FY2022-23", "FY2023-24", "FY2024-25", "FY2025-26"],
  "scores": {
    "altman_z":    {"FY2025-26": {"score": 0.9604, "interpretation": "distress", "x2_numerator": "retained_earnings", "components": {"X1": -0.081833, "...": "..."}, "inputs": {"...": "..."}, "proxies": ["..."], "missing": []}},
    "piotroski_f": {"FY2025-26": {"score": 8, "interpretation": "strong", "components": {"F1_roa_positive": {"signal": 1, "current": 0.036, "comparison": 0.0}, "...": "..."}}},
    "beneish_m":   {"FY2025-26": {"score": -2.9793, "interpretation": "unlikely manipulator", "components": {"DSRI": 0.87, "...": "..."}}}
  }
}
```
- The label field is `interpretation` for all three scores (for Altman it holds the zone: `safe`, `grey` or `distress`).
  There is no `zone` field.
- `score` may be `null`, with a `reason`, when inputs are missing.
- **FY2021-22:** Altman Z'' is computed (single year; figures from the FY2022-23 report's comparative column, retained
  earnings from its "Other equity" note): consolidated 2.7197 (`safe`), standalone 3.2455 (`safe`). Piotroski F and
  Beneish M compare a year with the prior year, so for FY2021-22 they return `"score": null` with
  `"reason": "needs FY2020-21, which is outside the four reports"`. Show them as "—".
- Altman zones: `safe` (> 2.60), `grey` (1.10–2.60), `distress` (< 1.10). Piotroski: `strong` (8–9), `average` (5–7), `weak` (0–4).
  Beneish: M > -1.78 = `possible earnings manipulation flag`.
- Suggested (optional) UI: a "Scores" card or tab on the Dashboard, with one row per score and one column per year, showing the zone or interpretation label.
- Full formulas and every proxy: `docs/SCORES.md`.

## Additions (conversation memory, net debt, segments)

### `POST /api/ask` — optional `history` for follow-up questions
```json
{"question": "And in FY2023-24?",
 "history": [{"role": "user", "content": "What was the consolidated current ratio in FY2025-26?"},
             {"role": "assistant", "content": "<previous answer_markdown>"}]}
```
- `history` is optional (default `[]`); send the earlier turns of the current chat, oldest first, max 20 messages
  (the agent uses the last 8). The response shape is unchanged. The agent re-fetches every figure; history only resolves
  what "it" / "that year" refers to.

### `GET /api/metrics` — new metric `net_debt`
- `unit: "INR crore"`, `higher_is_better: false`. Net debt = non-current + current borrowings + lease liabilities
  - cash and cash equivalents - other bank balances - current investments.

### `GET /api/segments`
```json
{"unit": "INR crore", "years": ["FY2021-22", "...", "FY2025-26"],
 "items": ["segment_revenue", "segment_results"],
 "note": "Segment results = segment EBITDA (before exceptional items, interest, tax and depreciation). ...",
 "segments": [{"key": "tata_steel_india", "name": "Tata Steel India",
               "values": {"FY2025-26": {"segment_revenue": 1.0, "segment_results": 33035.63}},
               "sources": {"FY2025-26": {"report": "FY2025-26", "page_label": "F256", "pdf_page": 534}},
               "restated": {"FY2022-23": ["segment_results"]}}],
 "eliminations": {"...same shape..."}, "totals": {"...same shape..."}}
```
- A segment may have values only for some years (Tata Steel Europe until FY2023-24, then Netherlands and UK from
  FY2024-25; Tata Steel Long Products merged into Tata Steel India). Show missing years as "—", never zero.
- Suggested UI: a "Segments" card on the Dashboard with a table (rows = segments, columns = years) and a toggle between
  revenue and results; mark restated values.

## Additions (task 05: local PDFs, statement PDFs, regions, company facts)

### Links to the source PDFs are now relative (`/api/pdf/...`)
tatasteel.com blocks deep links (HTTP 403), so the API serves its own copies of the four reports. Every `pdf_url` the API
returns is now relative:
- `POST /api/ask` → `citations[].pdf_url` = `"/api/pdf/FY2025-26#page=421"` (no page known → `"/api/pdf/FY2025-26"`).
- `GET /api/reports` → `pdf_url` = `"/api/pdf/FY2025-26"`, plus a new `official_url` (the tatasteel.com link, for reference only):
  ```json
  {"fiscal_year": "FY2022-23", "title": "116th Integrated Report & Annual Accounts 2022-23",
   "official_url": "https://www.tatasteel.com/media/18370/tata-steel-ir-2022-23.pdf", "pdf_url": "/api/pdf/FY2022-23", "pages": 597}
  ```
- `GET /api/segments` → each `sources[fy]` gains `url`, e.g. `{"report": "FY2025-26", "page_label": "F256", "pdf_page": 534, "url": "/api/pdf/FY2025-26#page=534"}`.
- `/api/regions` and `/api/company` (below) also give `url`s in this form.

Open them as normal links (`<a href target="_blank">`); the browser's PDF viewer honours `#page=`.

### `GET /api/pdf/{report}`
`report` is `FY2022-23` … `FY2025-26`. Returns the whole report: `200`, `Content-Type: application/pdf`,
`Content-Disposition: inline; filename="TataSteel_FY2025-26.pdf"` (about 35 MB). Unknown report → `404 {"error": "..."}`.

### `GET /api/statements?scope=<consolidated|standalone>`
Where each primary statement is printed, for every fiscal year, with a link to a statement-only PDF (Dashboard
"Statement coverage"). Each year uses its own report; FY2021-22 uses the FY2022-23 report (comparative column).
Real response (excerpt):
```json
{"scope": "consolidated",
 "years": ["FY2021-22", "FY2022-23", "FY2023-24", "FY2024-25", "FY2025-26"],
 "statements": {
   "FY2021-22": {
     "profit_and_loss": {"report": "FY2022-23", "page_labels": ["F142", "F143"], "pdf_pages": [435, 436],
                         "url": "/api/statement-pdf?report=FY2022-23&scope=consolidated&statement=profit_and_loss",
                         "note": "comparative column of the FY2022-23 report"},
     "balance_sheet": {"...": "same shape"}, "cash_flow": {"...": "same shape"}},
   "FY2025-26": {
     "profit_and_loss": {"report": "FY2025-26", "page_labels": ["F144", "F145"], "pdf_pages": [422, 423],
                         "url": "/api/statement-pdf?report=FY2025-26&scope=consolidated&statement=profit_and_loss"},
     "...": "..."}}}
```
- Statement keys: `profit_and_loss`, `balance_sheet`, `cash_flow`. `note` is present only for FY2021-22.
- The pages come from the page map and are validated at start-up: contiguous, each with a printed label, and exactly
  the pages the extracted statement line items came from (all 24 report/scope/statement combinations pass).

### `GET /api/statement-pdf?report=<FY>&scope=<consolidated|standalone>&statement=<profit_and_loss|balance_sheet|cash_flow>`
A new small PDF containing only that primary statement's pages (the statement itself, not the notes), copied
unchanged from the report. `200`, `application/pdf`, `Content-Disposition: inline; filename="TataSteel_FY2025-26_consolidated_profit_and_loss_F144-F145.pdf"`.
PDF title metadata, e.g. `"Tata Steel FY2025-26 consolidated statement of profit and loss (F144-F145)"` or
`"Tata Steel FY2022-23 standalone balance sheet (F22)"`. Built once per combination and cached in memory.
Errors: unknown report, scope or statement → `404 {"error": "..."}`; PyMuPDF missing on the server → `503 {"error": "..."}`.
Use the `url` from `/api/statements` rather than building it.

### `GET /api/regions`
Regions for the Dashboard region filter, summed from the consolidated segment note (each year from the latest report
presenting it). All arithmetic is done in the backend.

| key | Segments summed | Years |
|---|---|---|
| `india` | Tata Steel India + Neelachal Ispat Nigam + Other Indian Operations + Tata Steel Long Products (where present) | FY2021-22 … FY2025-26 |
| `netherlands` | Tata Steel Netherlands operations | FY2024-25, FY2025-26 |
| `uk` | Tata Steel UK operations | FY2024-25, FY2025-26 |
| `europe` | Tata Steel Europe (before the split into Netherlands and UK) | FY2021-22 … FY2023-24 |
| `south_east_asia` | South-East Asian operations | all |
| `rest_of_world` | Rest of the world | all |
| `trading` | Other trade related operations | all |

Real response (excerpt):
```json
{"unit": "INR crore", "years": ["FY2021-22", "...", "FY2025-26"],
 "note": "EBITDA = segment results before exceptional items, interest, tax and depreciation. Group totals are the Total column ...",
 "regions": [{"key": "uk", "name": "United Kingdom", "segments": ["tata_steel_uk"],
   "values": {"FY2025-26": {
     "segment_revenue": 23332.67, "external_revenue": 22383.41, "ebitda": -2568.99,
     "ebitda_margin_pct": -11.01, "share_of_group_external_revenue_pct": 9.64, "share_of_group_ebitda_pct": -7.37,
     "components": [{"key": "tata_steel_uk", "name": "Tata Steel UK operations", "segment_revenue": 23332.67,
                     "external_revenue": 22383.41, "ebitda": -2568.99}],
     "sources": [{"report": "FY2025-26", "page_label": "F256", "pdf_page": 534, "url": "/api/pdf/FY2025-26#page=534"}],
     "restated": {}}}}],
 "group_totals": {"FY2025-26": {"segment_revenue": 232139.94, "external_revenue": 232139.94, "ebitda": 34847.73,
                                "eliminations": {"segment_revenue": -60455.94, "external_revenue": 0.0, "ebitda": -831.94}}},
 "reconciliation": {"FY2025-26": {"ebitda": {"regions_sum": 35679.67, "eliminations": -831.94, "sum": 34847.73, "total": 34847.73, "ok": true}, "...": "..."}}}
```
- `ebitda_margin_pct` = ebitda / segment_revenue × 100; `share_of_group_external_revenue_pct` = external_revenue / group
  external revenue × 100; `share_of_group_ebitda_pct` = ebitda / group EBITDA × 100 (group = the note's Total column,
  after inter-segment eliminations, so EBITDA shares do not add up to exactly 100%, and a loss-making region has a negative share).
- A year in which a region did not exist is **absent** from `values` (not zero): show "—".
- `restated`: `{segment_key: [items]}` for components restated versus an earlier report (e.g. trading FY2024-25 `["ebitda"]`).
- `reconciliation[fy][item].ok` is `true` for every year and item (regions + eliminations = printed Total, to 0.01).
- Segment assets, liabilities and "addition to non-current assets" are printed on the page after the segment table
  but are not included yet: adding them needs a re-run of the segment extractor that rewrites `data/processed/segments.json`.

### `GET /api/company`
"About Tata Steel" facts for the Home page, from the FY2025-26 report's corporate overview. Every number and proper
noun in each statement was checked against the text of its cited page (`src/ingest/company_facts.py`).
```json
{"title": "About Tata Steel",
 "source": "FY2025-26 Integrated Report & Annual Accounts, corporate overview (Highlights of the Year, Corporate Portrait)",
 "facts": [{"text": "Tata Steel is a globally diversified integrated steel producer with a combined steelmaking capacity of 36 MTPA across India, the Netherlands, the UK and Thailand.",
            "report": "FY2025-26", "page_label": "10-11", "pdf_page": 8, "url": "/api/pdf/FY2025-26#page=8"}]}
```
- 5 facts. `page_label` is the pair of printed page numbers on the two-page spread (the overview pages are spreads).
- `404 {"error": "..."}` if `data/processed/company.json` has not been built.
