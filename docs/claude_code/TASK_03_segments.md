# Claude Code task 03 — Segment results for all years (extraction, verification, tool, endpoint)

## Why
The frontend needs segment performance (Tata Steel India, Netherlands, UK, and the other reported segments) for every
year, and the agent needs exact segment figures instead of searching note tables. Segment data is in the consolidated
"Segment reporting" note of each annual report.

## Data available (read-only)
- PDFs `data/raw/TataSteel_FY2022-23.pdf` … `TataSteel_FY2025-26.pdf`; page maps `data/interim/page_map_<FY>.json`
  (per PDF page: `label` like "F256", `section`, `scope`, `statement`); chunks `data/processed/chunks.jsonl`.
- Verified statements: `data/processed/financials_by_report.json` (e.g. consolidated `revenue_from_operations`).
- Known layout (FY2025-26 report, PDF page 534, label F256): segments are COLUMNS; each item is given as TWO STACKED ROWS
  with no year labels — first row = the report's year, second row = the prior year; a row label may be split across the two
  rows (e.g. "Segment results" / "before exceptional items, interest, tax and depreciation:"). Other years may differ in
  segment names, column count and page — inspect every report.
- Known values (FY2025-26 report): external revenue total 2,32,139.94 (FY2025-26) and 2,18,542.51 (FY2024-25);
  segment results FY2025-26: Tata Steel India 33,035.63, Netherlands 2,721.52, UK (2,568.99), total 34,847.73;
  FY2024-25 India 28,217.36, Netherlands 825.38, UK (4,134.20), total 25,801.80.
- PyMuPDF is installed (`import pymupdf`). Python: `.venv/bin/python`. Indian number format; brackets = negative.

## Deliverables
1. `src/ingest/segments.py` → NEW file `data/processed/segments.json`:
   `{report: {fiscal_year: {"segments": {name: {"external_revenue", "inter_segment_revenue", "segment_revenue",
   "segment_results"}}, "totals": {...same items...}, "eliminations"/"unallocated" where present, "pdf_page", "page_label"}}}`
   for every report (FY2022-23..FY2025-26) and both of its years (FY2021-22..FY2025-26). Keep segment names as printed and
   add a normalised `key` (e.g. "tata_steel_india", "tata_steel_netherlands", "tata_steel_uk"); segments that exist only in
   some years (e.g. merged or renamed ones) must be kept, not forced into another segment.
   Mandatory checks, printed as a table: (a) every value found in its cited page's text; (b) sum of segments plus
   eliminations/unallocated equals the printed total for each item; (c) total external revenue equals consolidated
   revenue_from_operations for that report and year in financials_by_report.json (to 0.01). Anything failing is left out
   and listed as unresolved — never guessed.
2. `src/analysis/segments.py`: `get_segments(fiscal_years=None, items=None)` using the LATEST report containing each year,
   with source page per value and a `restated` flag where the same segment/year differs between reports.
3. Agent tool in `src/agent/tools.py`, appended in the existing style (like `compute_scores`): `get_segments(fiscal_years,
   items)` returning the data plus a ready-to-paste markdown table and a sources line. Register in FUNCS and SCHEMAS; the
   description must say segment "results" are EBITDA before exceptional items (segment EBITDA). Do not change other tools.
4. `GET /api/segments` in `src/api/main.py` → `{"years": [...], "segments": [{"key", "name", "values": {fy: {item: value}},
   "sources": {fy: {"report", "page_label", "pdf_page"}}}], "totals": {...}}`. Add only this endpoint.
5. `tests/test_segments.py`: the known values above; check (a)-(c) for all reports; restated-flag logic; no NaN.
6. `docs/SEGMENTS.md`: sources, layout differences found per year, checks, and the results table (all years).

## Done means
`.venv/bin/python src/ingest/segments.py` prints the check table with every included value passing;
`.venv/bin/python -m pytest tests/ -q` passes (all existing tests too). Report: files changed, check table, pytest output,
the segment-results table for all years, and anything unresolved.

## Boundaries
- You may CREATE `src/ingest/segments.py`, `src/analysis/segments.py`, `data/processed/segments.json`,
  `tests/test_segments.py`, `docs/SEGMENTS.md`. Only APPEND to `src/agent/tools.py` and only ADD the endpoint in `src/api/main.py`.
- Do not read, modify or run anything in `frontend/`. Do not modify other files under `data/`, `eval/`, `.env` (do not
  read it), `qdrant_storage/`, `.cache/`. No git, no Docker, no Ollama/agent calls.
