# Claude Code task 05 — Backend changes from the UI review

Context: FastAPI backend in `src/api/main.py`; agent in `src/agent/`; scores `src/analysis/scores.py`; segments
`src/analysis/segments.py`; data in `data/processed/` and `data/interim/page_map_<FY>.json`; PDFs in
`data/raw/TataSteel_<FY>.pdf` (four reports FY2022-23..FY2025-26; FY2021-22 figures are the comparative column of the
FY2022-23 report). The backend runs in Docker at http://127.0.0.1:8000 (old code; do not restart it). Python: `.venv/bin/python`.
Read `README.md`, `docs/API_CONTRACT.md`, `docs/SCORES.md`, `docs/SEGMENTS.md` first. All existing tests must keep passing.

## A. Serve our local PDFs (tatasteel.com blocks deep links with HTTP 403)
- `GET /api/pdf/{report}` → the local PDF inline (`application/pdf`, `Content-Disposition: inline`); 404 for unknown reports.
- Every `pdf_url` the API returns (citations in `/api/ask`, `/api/reports`, and any `sources` with pages) becomes relative:
  `/api/pdf/{report}#page={pdf_page}` (no page → `/api/pdf/{report}`). `/api/reports` also returns `official_url`
  (the tatasteel.com link) for reference.

## B. Statement-only PDFs (Dashboard "Statement coverage")
- `GET /api/statements?scope=consolidated|standalone` → for each fiscal year FY2021-22..FY2025-26 and each of
  `profit_and_loss`, `balance_sheet`, `cash_flow`: `{report, page_labels, pdf_pages, url}` where `url` is the endpoint below.
  FY2021-22 uses the FY2022-23 report and says `"note": "comparative column of the FY2022-23 report"`.
- `GET /api/statement-pdf?report=&scope=&statement=` → a NEW small PDF (PyMuPDF `insert_pdf`) containing ONLY that primary
  statement's pages for that report and scope (from the page map; the statement itself, not the notes), pages exactly as
  printed; title metadata like "Tata Steel FY2025-26 consolidated statement of profit and loss (F144)". Cache in memory.
  Validate every page choice against the page map and the pages our line items came from (`data/processed/line_items.jsonl`).

## C. FY2021-22 in composite scores
- Scores cover FY2021-22..FY2025-26. Altman Z'' is computed for FY2021-22 (single year: its figures from the FY2022-23
  report; retained earnings from `retained_earnings.json`). Piotroski F and Beneish M for FY2021-22 return `score: null`
  with `reason: "needs FY2020-21, which is outside the four reports"`. Update `/api/scores`, the agent tool, tests, SCORES.md.

## D. Regions (Dashboard region filter)
- `GET /api/regions` → regions and years from the segment data: `india` (Tata Steel India + Neelachal Ispat Nigam +
  Other Indian Operations + Tata Steel Long Products where present), `netherlands`, `uk`, `europe` (until FY2023-24, before
  the split), `south_east_asia`, `rest_of_world`, `trading` ("Other trade related operations"). For each region and year:
  `segment_revenue`, `external_revenue`, `ebitda` (segment results), `ebitda_margin_pct` = ebitda / segment_revenue × 100,
  `share_of_group_external_revenue_pct`, `share_of_group_ebitda_pct` (group totals from the segment note), the component
  segments summed, sources (report, page_label, pdf_page, url) and restated flags. All arithmetic in the backend.
  Years where a region did not exist → absent (not zero).
- Check whether the segment note also reports segment assets, liabilities or capital expenditure; add them ONLY if every
  value can be verified on its page like the existing items (otherwise report that you skipped them and why).

## E. "About Tata Steel" facts (Home page)
- `src/ingest/company_facts.py` → NEW `data/processed/company.json`: 3-5 short factual statements (what Tata Steel does,
  where it operates, scale such as capacity/employees if stated), written in plain words from the FY2025-26 report's
  corporate overview pages, each with `report`, `page_label`, `pdf_page`, `url`. Verification: every number and proper
  noun in a statement must appear on its cited page's text (print a ✓/✗ table; drop any ✗). No forward-looking claims.
- `GET /api/company` → that JSON.

## F. Agent fixes
- Rule: never write approximations ("≈", "~", "around", "about", "roughly") for figures; state the exact computed value
  (e.g. 2,810.36 crore, 34.81%). Add to the system prompt; the claims check should flag "≈"/"~" next to a number.
- DuPont: the question "Run a DuPont analysis of Tata Steel's consolidated ROE for FY2025-26." came back partially
  verified (113/120) with unmatched 12.06, 12.23, 780.73, 1429.65, 10998.02. Reproduce it by calling the agent in Python
  (`.venv/bin/python`, `sys.path` src/agent, `agent.ask(...)`; it loads its key itself — never print or read .env),
  find why those numbers were not in the tool results (e.g. intermediate values the model computed itself, or values a
  tool computes but does not return), and fix the root cause in the tools/prompt so DuPont answers are fully verified.
  At most 4 agent calls in total for this section. Report the before/after.

## G. Docs and tests
- `docs/API_CONTRACT.md`: fix Altman's label field (`interpretation`, not `zone`); document A-E (request/response).
- Tests for A-E in `tests/` (no network, no agent calls in tests). `.venv/bin/python -m pytest tests/ -q` passes.

## Done means
All tests pass; report files changed, the company-facts verification table, the regions check (region totals reconcile
to the segment totals per year), the DuPont before/after, and anything skipped.

## Boundaries
- Edit only `src/`, `tests/`, `docs/` and create `data/processed/company.json` (no other `data/` changes).
- Do not touch `frontend/` or `eval/`. No git, no Docker. Never read or print `.env`.
