# Claude Code task 02 — Replace the retained-earnings proxy in Altman Z'' with actual retained earnings

## Why
`src/analysis/scores.py` computes Altman X2 = other_equity / total_assets as a PROXY for retained earnings.
Other equity also includes securities premium, general reserve, OCI and other reserves. During evaluation the agent
found actual retained earnings in the "Other equity" note (consolidated FY2025-26 appears to be 39,674.80 and FY2024-25
33,698.53 INR crore, versus other equity 1,00,920.21). With X2 = 0.1317 instead of 0.3350, FY2025-26 Z'' falls from
1.6232 (grey) to about 0.96 (distress) — the proxy changes the conclusion, so the real figure must be used.
Treat the two figures above as UNVERIFIED leads; your extraction must establish the true values from the PDFs.

## Data available (read-only)
- PDFs: `data/raw/TataSteel_FY2022-23.pdf` … `TataSteel_FY2025-26.pdf`
- Page maps: `data/interim/page_map_<FY>.json` (per PDF page: `label` like "F197", `section`, `scope`, `statement`)
- Docling output: `data/interim/docling_<FY>.json`; chunks: `data/processed/chunks.jsonl` (note tables with `note` titles,
  e.g. "20. Other equity ...", with `report`, `scope`, `page`, `page_label`)
- Existing verified data: `data/processed/financials.json`, `financials_by_report.json`
- PyMuPDF is installed in `.venv` (`import pymupdf`). Python: always `.venv/bin/python`.
- Indian number format: 1,00,920.21; negatives in brackets (1,234.56); the ₹ sign may be extracted as the letter "I".

## Deliverables
1. `src/ingest/retained_earnings.py` — for each report (FY2022-23..FY2025-26) and scope (standalone, consolidated), find
   the "Other equity" note and extract the RETAINED EARNINGS closing balance for the report's year AND its comparative
   (prior) year, giving FY2021-22..FY2025-26. Beware: the note may be a movement table (opening balance, profit, OCI,
   dividends, transfers, closing balance) or a summary table; you need the year-end closing balance of retained earnings
   only, not other reserves or the total. Layout may differ between years and scopes — inspect each.
   Writes a NEW file `data/processed/retained_earnings.json`:
   `{report: {scope: {fiscal_year: {"value", "pdf_page", "page_label", "method", "verified_on_page": true/false}}}}`
   Verification (mandatory): the value, in Indian format, must be found in the text of its cited PDF page
   (pymupdf `page.get_text()`, whitespace-normalised). Print a table: report, scope, year, value, page label, found ✓/✗.
   Any value that cannot be verified must be left out (not guessed) and listed as unresolved.
2. `src/analysis/scores.py` — Altman X2 = retained_earnings / total_assets, taking retained earnings for year t from the
   LATEST report containing year t (same rule as financials.json), with its source. If unavailable for a year/scope,
   fall back to the other_equity proxy and record that in `proxies` and `fallbacks`. Remove the proxy note where no longer
   used. Do not change Piotroski or Beneish.
3. `tests/test_scores.py` — update expectations; add tests that (a) every value in retained_earnings.json with
   verified_on_page=true is literally present on its cited page, (b) Altman FY2025-26 consolidated uses retained earnings
   (not other equity) and recomputes Z'' consistently from its components, (c) the fallback path works when retained
   earnings is missing. All existing tests for Piotroski and Beneish must still pass.
4. `docs/SCORES.md` — replace the X2 proxy section; add a before/after table (other-equity proxy vs retained earnings)
   of X2, Z'' and zone for both scopes and all years, and a short explanation of why the conclusion changes.

## Done means
- `.venv/bin/python src/ingest/retained_earnings.py` prints the verification table with every included value ✓.
- `.venv/bin/python -m pytest tests/test_scores.py -q` passes.
- Report back: files changed, the verification table, pytest output, and the before/after Altman table.

## Boundaries
- You may CREATE `data/processed/retained_earnings.json` and `src/ingest/retained_earnings.py`. Do not modify or delete any
  other file under `data/`. Do not modify `eval/`, `.env` (do not read it), `qdrant_storage/`, `.cache/`.
- Only edit `src/analysis/scores.py`, `tests/test_scores.py`, `docs/SCORES.md` besides the two new files.
- No git commands, no Ollama/agent calls, no Docker commands.
