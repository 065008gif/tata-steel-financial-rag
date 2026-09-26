# Claude Code task 01 — Composite financial scores (Altman Z'', Piotroski F, Beneish M)

## Context
Repository: a financial-analysis RAG over Tata Steel's annual reports FY2022-23..FY2025-26 (comparatives give FY2021-22).
Verified statement data is in `data/processed/financials.json` (latest-report values) and
`data/processed/financials_by_report.json` (values as presented in each report). Structure:
`{scope: {item_key: {"description", "values": {fiscal_year: {"value", "source", ...}}}}}` and, by report,
`{report: {scope: {item_key: {...}}}}`. Scopes: "consolidated", "standalone". Units: INR crore.
Fiscal year "FY2025-26" = year ended 31 March 2026. Read `src/analysis/canonical.py` for item definitions and
`src/agent/tools.py` for the existing tool pattern (FUNCS / SCHEMAS, `_inr` formatting, `compute_metric`).
Python: always use `.venv/bin/python`.

## Available item keys (use only these)
total_assets, total_equity, total_current_assets, total_current_liabilities, total_non_current_liabilities,
property_plant_equipment, non_current_investments, current_investments, trade_receivables, equity_share_capital,
other_equity, non_current_borrowings, current_borrowings, revenue_from_operations, cost_of_materials_consumed,
depreciation_amortisation, other_expenses, finance_costs, profit_before_tax, profit_for_the_year,
net_cash_from_operating.

## Year-pair rule
Any formula comparing year t with t-1 must take BOTH years from the report of year t
(`financials_by_report.json[t]`), which presents t-1 as a comparative (restated where applicable). Fall back to
`financials.json` only if the report lacks the item, and record that fallback in the output.

## Scores to implement
1. **Altman Z'' (book-equity version, used because market value of equity is not in the reports)**
   X1 = (total_current_assets - total_current_liabilities) / total_assets
   X2 = other_equity / total_assets            (PROXY for retained earnings — disclose)
   X3 = (profit_before_tax + finance_costs) / total_assets   (EBIT)
   X4 = total_equity / (total_assets - total_equity)          (book equity / total liabilities)
   Z'' = 6.56*X1 + 3.26*X2 + 6.72*X3 + 1.05*X4
   Zones: > 2.60 "safe"; 1.10–2.60 "grey"; < 1.10 "distress".
2. **Piotroski F-score (0–9)** for year t vs t-1, beginning-of-year assets = total_assets of t-1:
   1 ROA_t = profit_for_the_year_t / total_assets_{t-1} > 0
   2 CFO_t = net_cash_from_operating_t > 0
   3 ROA_t > ROA_{t-1}  (ROA_{t-1} uses total_assets_{t-2}; if unavailable, use total_assets_{t-1} and disclose)
   4 CFO_t / total_assets_{t-1} > ROA_t
   5 non_current_borrowings / total_assets decreased
   6 current ratio (total_current_assets / total_current_liabilities) increased
   7 equity_share_capital did not increase
   8 gross margin (revenue_from_operations - cost_of_materials_consumed) / revenue_from_operations increased
     (PROXY: excludes purchases of stock-in-trade and inventory changes — disclose)
   9 asset turnover revenue_from_operations / total_assets_{t-1} increased
   Report each signal as 1/0 with its two values. Interpretation: 8–9 strong, 5–7 average, 0–4 weak.
3. **Beneish M-score (8-variable)** for year t vs t-1:
   DSRI = (trade_receivables/revenue)_t / (…)_{t-1}
   GMI  = gross_margin_{t-1} / gross_margin_t   (same gross margin proxy)
   AQI  = [1 - (total_current_assets + property_plant_equipment + non_current_investments)/total_assets]_t / [same]_{t-1}
   SGI  = revenue_t / revenue_{t-1}
   DEPI = [dep/(dep + PPE)]_{t-1} / [dep/(dep + PPE)]_t   (dep = depreciation_amortisation, PPE = property_plant_equipment)
   SGAI = (other_expenses/revenue)_t / (…)_{t-1}          (PROXY for SG&A — disclose)
   LVGI = [(total_current_liabilities + non_current_borrowings)/total_assets]_t / [same]_{t-1}
   TATA = (profit_for_the_year_t - net_cash_from_operating_t) / total_assets_t
   M = -4.84 + 0.920*DSRI + 0.528*GMI + 0.404*AQI + 0.892*SGI + 0.115*DEPI - 0.172*SGAI + 4.679*TATA - 0.327*LVGI
   Interpretation: M > -1.78 "possible earnings manipulation flag"; otherwise "unlikely manipulator".

## Deliverables
1. `src/analysis/scores.py` — pure functions `altman_z(fy, scope)`, `piotroski_f(fy, scope)`, `beneish_m(fy, scope)`,
   `all_scores(scope, fiscal_years)`. Each returns a dict: score, zone/interpretation, every component with its value,
   every input with value and `source` string, a `proxies` list, and `missing` (inputs unavailable → score None with
   a reason; never raise, never guess). Must NOT import `src/agent/agent.py` (it needs an API key). Load JSON directly.
2. Agent tool in `src/agent/tools.py`, appended in the existing style (like `list_risk_disclosures`):
   `compute_scores(score, fiscal_years=None, scope="consolidated")` with score in {"altman_z","piotroski_f","beneish_m","all"},
   returning the dicts plus a ready-to-paste markdown `table` (use `_inr`-style formatting; components to 4 decimals)
   and a `sources` line with report pages. Register in FUNCS and SCHEMAS. Do not change any existing tool.
3. API endpoint in `src/api/main.py`: `GET /api/scores?scope=consolidated` → `{"scope", "years", "scores": {"altman_z":
   {fy: {...}}, "piotroski_f": {...}, "beneish_m": {...}}}` for FY2022-23..FY2025-26. Do not change existing endpoints.
4. Tests in `tests/test_scores.py` (install pytest into .venv if needed: `.venv/bin/pip install pytest`):
   - Formula tests with small synthetic inputs and hand-computed expected results (monkeypatch/inject the data).
   - Real-data checks (consolidated, FY2025-26): total_assets = 301254.11, total_equity = 103780.45, so
     X4 = 103780.45 / 197473.66 = 0.525544 (±1e-4); X1 = (72265.11 - 96917.64) / 301254.11 = -0.081833 (±1e-4).
   - Piotroski is an integer 0–9 for FY2023-24..FY2025-26; Beneish returns a float for FY2023-24..FY2025-26;
     no NaN/inf anywhere; missing inputs give None with a reason, not an exception.
5. `docs/SCORES.md` — formulas, thresholds, every proxy and why it is needed, and the results table
   (consolidated and standalone, FY2022-23..FY2025-26) produced by running the code.

## Done means
`.venv/bin/python -m pytest tests/test_scores.py -q` passes, and running
`.venv/bin/python -c "import sys; sys.path.insert(0,'src/analysis'); from scores import all_scores; import json; print(json.dumps(all_scores('consolidated'), indent=1)[:3000])"`
prints the scores. Report back: files changed, test output, and the consolidated results table.

## Boundaries
- Do not modify anything under `data/`, `eval/`, `qdrant_storage/`, `.cache/`, or `.env`; do not read `.env`.
- Do not run the agent or call the Ollama API; do not run git commit/push (the human reviews and commits).
- Do not restart Docker containers. No changes outside the deliverable files listed above.
