# API contract addendum

Everything in Section 5 of the frontend brief remains valid and unchanged. This file only ADDS one optional endpoint.

## `GET /api/scores?scope=<consolidated|standalone>`
Composite scores for FY2022-23 to FY2025-26.
```json
{
  "scope": "consolidated",
  "years": ["FY2022-23", "FY2023-24", "FY2024-25", "FY2025-26"],
  "scores": {
    "altman_z":    {"FY2025-26": {"score": 1.6232, "zone": "grey", "components": {"X1": -0.081833, "...": "..."}, "inputs": {"...": "..."}, "proxies": ["..."], "missing": []}},
    "piotroski_f": {"FY2025-26": {"score": 8, "interpretation": "strong", "components": {"F1_roa_positive": {"signal": 1, "current": 0.036, "comparison": 0.0}, "...": "..."}}},
    "beneish_m":   {"FY2025-26": {"score": -2.9793, "interpretation": "unlikely manipulator", "components": {"DSRI": 0.87, "...": "..."}}}
  }
}
```
- `score` may be `null`, with a `reason`, when inputs are missing.
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
