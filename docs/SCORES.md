# Composite financial scores

Altman Z'' (book-equity), Piotroski F-score and Beneish M-score for Tata Steel, consolidated and standalone,
FY2021-22 to FY2025-26 (FY2025-26 = year ended 31 March 2026). FY2021-22 has Altman Z'' only (see below). All inputs are canonical statement items in
INR crore from `data/processed/financials.json` and `data/processed/financials_by_report.json`, plus retained
earnings from `data/processed/retained_earnings.json` (built by `src/ingest/retained_earnings.py`).

- Code: `src/analysis/scores.py` (`altman_z`, `piotroski_f`, `beneish_m`, `all_scores`), pure functions that read the JSON directly.
- Agent tool: `compute_scores(score, fiscal_years=None, scope="consolidated")` in `src/agent/tools.py`.
- API: `GET /api/scores?scope=consolidated|standalone`.
- Tests: `.venv/bin/python -m pytest tests/test_scores.py -q`.

Every result carries the score, its zone or interpretation, every component, every input (value, source page, and
basis), the `proxies` list, any `fallbacks`, and `missing`. If an input is unavailable or a denominator is zero,
the score is `None` and a `reason` is given. The code never raises and never guesses a value.

## Which report each value comes from

- **Altman Z''** uses a single year, so it takes values from `financials.json` (the latest report that contains the year),
  and retained earnings from `retained_earnings.json` under the same latest-report rule.
- **Piotroski F and Beneish M** compare year t with t-1. Both years come from the **report of year t**, which
  presents t-1 as a comparative (restated where applicable). If that report lacks an item, the code falls back to
  `financials.json` and records it in `fallbacks`. In practice, the only fallback is Piotroski's beginning-of-year
  assets for t-1 (total_assets of t-2), because report t does not contain year t-2. One exception: the standalone
  FY2024-25 report includes a third balance sheet, so it does contain t-2.

## FY2021-22

FY2021-22 appears in the reports only as the comparative column of the FY2022-23 report.
- **Altman Z''** uses a single year, so it is computed. All six statement inputs come from the FY2022-23 report
  (consolidated balance sheet F140-F141 and profit and loss F142; standalone F22-F23). Retained earnings come from the
  "Other equity" note of the same report (consolidated F198: 55,647.79; standalone F73: 76,498.67). Every input was
  checked against the text of its PDF page (`tests/test_scores.py::test_fy2021_22_altman_from_fy2022_23_report`).
- **Piotroski F and Beneish M** compare year t with t-1 as presented in the report of year t. There is no FY2021-22 report,
  and no report contains FY2020-21. So both return `score: null`, with `reason: "needs FY2020-21, which is outside the
  four reports"`.

| Scope | X1 | X2 | X3 | X4 | Z'' |
|---|---|---|---|---|---|
| Consolidated | 0.0065 | 0.1950 | 0.1951 | 0.6956 | **2.7197 (safe)** |
| Standalone | -0.1008 | 0.3446 | 0.2112 | 1.2991 | **3.2455 (safe)** |

FY2021-22 was a record-profit year (consolidated profit before tax 50,226.87), so X3 is more than twice its FY2022-23
value (0.0852). This is why consolidated Z'' falls from the safe zone in FY2021-22 to the grey zone in FY2022-23.

## Altman Z'' (book-equity version)

| Component | Formula |
|---|---|
| X1 | (total_current_assets - total_current_liabilities) / total_assets |
| X2 | retained_earnings / total_assets |
| X3 | (profit_before_tax + finance_costs) / total_assets |
| X4 | total_equity / (total_assets - total_equity) |

Z'' = 6.56·X1 + 3.26·X2 + 6.72·X3 + 1.05·X4. Zones: > 2.60 **safe**; 1.10–2.60 **grey**; < 1.10 **distress**.

Proxies:
- **X4 uses book equity.** The market value of equity is not in the reports. This is why the book-equity Z''
  variant is used, not the original market-value Z.
- **X3 approximates EBIT as PBT + finance costs.** PBT is after exceptional items, so exceptional items are
  included in EBIT.

### X2: retained earnings

X2 uses the actual retained earnings, not other equity. Under Ind AS, other equity also contains the securities
premium, general reserve, OCI reserves and other reserves, and these are not accumulated earnings.

- **Source.** `src/ingest/retained_earnings.py` reads the "Other equity" note of every report and scope, section
  "A. Retained earnings". This is a movement table (opening balance, profit, remeasurement, dividend, transfers,
  closing balance). The script takes the "Balance at the end of the year" row for the report year and its comparative
  year, giving FY2021-22 to FY2025-26.
- **Checks.** Each column must satisfy opening + movements = closing. Each value, in Indian format, must be present
  in the pymupdf text of its cited page. All 16 values (4 reports × 2 scopes × 2 years) pass both checks. A value
  that fails is left out and listed as unresolved.
- **Which value is used.** For year t, the value comes from the latest report that contains t. Each result records
  it as the input `retained_earnings[t]`, with its page, and sets `x2_numerator: "retained_earnings"`.
- **Fallback.** If no page-verified retained earnings exist for a year and scope, X2 uses other_equity as before.
  This is recorded in `proxies` and `fallbacks` and sets `x2_numerator: "other_equity"`. With the current data, no
  year uses the fallback.
- **Restatements (standalone).** Retained earnings were restated after the amalgamations of subsidiaries into Tata
  Steel. FY2022-23 was 85,970.98 in the FY2022-23 report and 86,491.20 in the FY2023-24 report. FY2023-24 was
  86,727.36 in the FY2023-24 report and 1,00,380.17 in the FY2024-25 report. The latest-report rule picks the
  restated figures.
- **Basis mismatch (standalone FY2022-23).** Standalone total assets for FY2022-23 come from the third balance
  sheet in the FY2024-25 report. The retained-earnings note in that report only covers FY2024-25 and FY2023-24, so
  retained earnings come from the FY2023-24 report. The result discloses this in `proxies`. The FY2024-25 report
  gives an opening balance for FY2023-24 of 89,292.09, which is the restated FY2022-23 closing balance. The script
  does not extract it. Using it would raise X2 by about 0.011 and Z'' by about 0.04, and the zone stays safe.

#### Before and after: other-equity proxy vs retained earnings

| Scope | Year | Other equity | Retained earnings (report, page) | X2 proxy | X2 actual | Z'' proxy | Z'' actual |
|---|---|---|---|---|---|---|---|
| Consolidated | FY2022-23 | 1,01,860.86 | 48,166.32 (FY2023-24, F198) | 0.3537 | 0.1672 | 2.0859 (grey) | 1.4781 (grey) |
| Consolidated | FY2023-24 | 90,788.32 | 34,815.73 (FY2024-25, F204) | 0.3320 | 0.1273 | 1.1056 (grey) | **0.4383 (distress)** |
| Consolidated | FY2024-25 | 89,922.19 | 33,698.53 (FY2025-26, F197) | 0.3218 | 0.1206 | 1.5226 (grey) | **0.8666 (distress)** |
| Consolidated | FY2025-26 | 1,00,920.21 | 39,674.80 (FY2025-26, F197) | 0.3350 | 0.1317 | 1.6232 (grey) | **0.9604 (distress)** |
| Standalone | FY2022-23 | 1,37,787.55 | 86,491.20 (FY2023-24, F77) | 0.5637 | 0.3539 | 3.5850 (safe) | 2.9008 (safe) |
| Standalone | FY2023-24 | 1,39,980.87 | 1,00,380.17 (FY2024-25, F78) | 0.5646 | 0.4049 | 3.5297 (safe) | 3.0090 (safe) |
| Standalone | FY2024-25 | 1,25,483.34 | 1,09,729.39 (FY2025-26, F73) | 0.4938 | 0.4318 | 2.7248 (safe) | **2.5227 (grey)** |
| Standalone | FY2025-26 | 1,34,284.71 | 1,21,545.86 (FY2025-26, F73) | 0.4923 | 0.4456 | 2.5646 (grey) | 2.4124 (grey) |

**Why the conclusion changes.** Consolidated retained earnings are only about 37–47% of consolidated other
equity. The rest is other reserves (securities premium, general reserve, OCI and others). Consolidated retained
earnings were also reduced by large pension remeasurement losses: 13,304.45 crore in FY2022-23 and 6,224.84 crore
in FY2023-24, according to the note. X2 therefore falls by about 0.19–0.20, which cuts Z'' by 3.26 × that, or about
0.61–0.67. Z'' was already in the grey zone, and this drop moves consolidated FY2023-24, FY2024-25 and FY2025-26
below 1.10, into the distress zone. Standalone retained earnings are a much larger share of other equity (63–91%).
The standalone scores fall less, but FY2024-25 drops from the safe zone to the grey zone.

## Piotroski F-score (0–9)

Beginning-of-year assets for year t are total_assets of t-1. Each signal is reported as 1/0 together with the two
values it compares.

| # | Signal (1 if true) |
|---|---|
| F1 | ROA_t = profit_for_the_year_t / total_assets_{t-1} > 0 |
| F2 | net_cash_from_operating_t > 0 |
| F3 | ROA_t > ROA_{t-1}, where ROA_{t-1} = profit_{t-1} / total_assets_{t-2} |
| F4 | CFO_t / total_assets_{t-1} > ROA_t |
| F5 | non_current_borrowings / total_assets (year-end, each year) decreased |
| F6 | current ratio (total_current_assets / total_current_liabilities) increased |
| F7 | equity_share_capital did not increase |
| F8 | gross margin (revenue_from_operations - cost_of_materials_consumed) / revenue_from_operations increased |
| F9 | asset turnover revenue_from_operations / total_assets_{t-1} increased (t-1 uses total_assets_{t-2}) |

Interpretation: 8–9 **strong**, 5–7 **average**, 0–4 **weak**.

Proxies and disclosures:
- **Gross margin (F8) counts only cost of materials consumed.** Purchases of stock-in-trade and changes in
  inventories are not canonical items, so the margin is overstated in level terms. Only its direction matters
  for F8.
- **total_assets_{t-2} is missing for FY2022-23.** No report contains FY2020-21. So for FY2022-23, ROA_{t-1} and
  asset turnover_{t-1} (F3, F9) divide by total_assets of FY2021-22 (year-end) instead of beginning-of-year
  assets, and the output discloses this.
- **F7 applies a strict "did not increase" rule.** Consolidated share capital moved from 1,221.21 to 1,221.24
  (FY2022-23) and from 1,221.24 to 1,247.44 (FY2023-24). Both count as increases.

## Beneish M-score (8-variable)

| Index | Formula |
|---|---|
| DSRI | (trade_receivables / revenue)_t / (…)_{t-1} |
| GMI | gross_margin_{t-1} / gross_margin_t (same gross-margin proxy) |
| AQI | [1 - (total_current_assets + PPE + non_current_investments) / total_assets]_t / […]_{t-1} |
| SGI | revenue_t / revenue_{t-1} |
| DEPI | [dep / (dep + PPE)]_{t-1} / [dep / (dep + PPE)]_t |
| SGAI | (other_expenses / revenue)_t / (…)_{t-1} |
| LVGI | [(total_current_liabilities + non_current_borrowings) / total_assets]_t / […]_{t-1} |
| TATA | (profit_for_the_year_t - net_cash_from_operating_t) / total_assets_t |

M = -4.84 + 0.920·DSRI + 0.528·GMI + 0.404·AQI + 0.892·SGI + 0.115·DEPI - 0.172·SGAI + 4.679·TATA - 0.327·LVGI.
M > -1.78 means **possible earnings manipulation flag**; otherwise **unlikely manipulator**.

Revenue means revenue_from_operations, dep means depreciation_amortisation, and PPE means property_plant_equipment.

Proxies:
- **GMI uses the same gross-margin proxy as Piotroski F8.**
- **SGAI uses other expenses in place of SG&A.** The Ind AS statement of profit and loss is presented by nature
  and has no SG&A line.
- **AQI treats everything outside current assets, PPE and non-current investments as "soft" assets.** That
  includes capital work-in-progress, goodwill, other intangibles, deferred tax and other non-current assets. When capital
  work-in-progress is commissioned into PPE, AQI falls. The low FY2025-26 AQI in both scopes coincides with a
  large rise in PPE (consolidated: 1,25,215.17 to 1,49,878.21).
- **LVGI uses current liabilities plus non-current borrowings** as total debt.

## Results (produced by `all_scores`)

### Consolidated

FY2021-22: Altman Z'' 2.7197 (safe); Piotroski F and Beneish M null (need FY2020-21).

| Score | FY2022-23 | FY2023-24 | FY2024-25 | FY2025-26 |
|---|---|---|---|---|
| Altman Z'' | 1.4781 (grey) | 0.4383 (distress) | 0.8666 (distress) | 0.9604 (distress) |
| Piotroski F | 3 (weak) | 3 (weak) | 8 (strong) | 8 (strong) |
| Beneish M | -2.9170 (unlikely manipulator) | -3.2359 (unlikely manipulator) | -2.9533 (unlikely manipulator) | -2.9793 (unlikely manipulator) |

| Component | FY2022-23 | FY2023-24 | FY2024-25 | FY2025-26 |
|---|---|---|---|---|
| Z: X1 | -0.0371 | -0.1020 | -0.0634 | -0.0818 |
| Z: X2 | 0.1672 | 0.1273 | 0.1206 | 0.1317 |
| Z: X3 | 0.0852 | 0.0233 | 0.0564 | 0.0768 |
| Z: X4 | 0.5752 | 0.5107 | 0.4858 | 0.5255 |
| M: DSRI | 0.6759 | 0.8055 | 0.8806 | 0.8800 |
| M: GMI | 1.1826 | 0.9111 | 0.9885 | 0.9530 |
| M: AQI | 1.0674 | 0.9967 | 1.0577 | 0.8488 |
| M: SGI | 0.9975 | 0.9417 | 0.9536 | 1.0622 |
| M: DEPI | 0.9964 | 0.9844 | 0.9640 | 1.0401 |
| M: SGAI | 1.0536 | 1.1345 | 0.9512 | 0.9974 |
| M: LVGI | 1.0906 | 1.0622 | 1.0091 | 0.9636 |
| M: TATA | -0.0472 | -0.0922 | -0.0728 | -0.0803 |
| F: F1_roa_positive | 1 | 0 | 1 | 1 |
| F: F2_cfo_positive | 1 | 1 | 1 | 1 |
| F: F3_roa_improved | 0 | 0 | 1 | 1 |
| F: F4_accruals | 1 | 1 | 1 | 1 |
| F: F5_leverage_decreased | 0 | 0 | 0 | 1 |
| F: F6_current_ratio_increased | 0 | 0 | 1 | 0 |
| F: F7_no_new_equity | 0 | 0 | 1 | 1 |
| F: F8_gross_margin_increased | 0 | 1 | 1 | 1 |
| F: F9_asset_turnover_increased | 0 | 0 | 1 | 1 |

### Standalone

FY2021-22: Altman Z'' 3.2455 (safe); Piotroski F and Beneish M null (need FY2020-21).

| Score | FY2022-23 | FY2023-24 | FY2024-25 | FY2025-26 |
|---|---|---|---|---|
| Altman Z'' | 2.9008 (safe) | 3.0090 (safe) | 2.5227 (grey) | 2.4124 (grey) |
| Piotroski F | 3 (weak) | 4 (weak) | 5 (average) | 7 (average) |
| Beneish M | -2.2613 (unlikely manipulator) | -3.4646 (unlikely manipulator) | -2.7433 (unlikely manipulator) | -2.8691 (unlikely manipulator) |

| Component | FY2022-23 | FY2023-24 | FY2024-25 | FY2025-26 |
|---|---|---|---|---|
| Z: X1 | -0.0456 | -0.0519 | -0.0818 | -0.1112 |
| Z: X2 | 0.3539 | 0.4049 | 0.4318 | 0.4456 |
| Z: X3 | 0.0985 | 0.0952 | 0.0903 | 0.0970 |
| Z: X4 | 1.3188 | 1.3237 | 0.9948 | 0.9878 |
| M: DSRI | 1.0219 | 0.6355 | 1.0433 | 0.9884 |
| M: GMI | 1.2501 | 0.8804 | 0.9827 | 1.0163 |
| M: AQI | 1.1321 | 0.7170 | 1.0170 | 0.6112 |
| M: SGI | 0.9999 | 0.9865 | 0.9403 | 1.0544 |
| M: DEPI | 0.9727 | 1.0034 | 0.9716 | 1.0329 |
| M: SGAI | 1.0663 | 1.1136 | 1.0011 | 1.0360 |
| M: LVGI | 0.9927 | 1.0354 | 1.1886 | 1.0101 |
| M: TATA | 0.0054 | -0.0917 | -0.0390 | -0.0583 |
| F: F1_roa_positive | 1 | 1 | 1 | 1 |
| F: F2_cfo_positive | 1 | 1 | 1 | 1 |
| F: F3_roa_improved | 0 | 0 | 0 | 1 |
| F: F4_accruals | 0 | 1 | 1 | 1 |
| F: F5_leverage_decreased | 0 | 0 | 0 | 1 |
| F: F6_current_ratio_increased | 1 | 0 | 0 | 0 |
| F: F7_no_new_equity | 0 | 0 | 1 | 1 |
| F: F8_gross_margin_increased | 0 | 1 | 1 | 0 |
| F: F9_asset_turnover_increased | 0 | 0 | 0 | 1 |

Reading the results:
- **Altman Z''.** Consolidated is in the grey zone in FY2022-23 (1.4781) and in the distress zone from FY2023-24
  on. The low point is FY2023-24 (0.4383, the loss year), followed by a partial recovery to 0.9604 in FY2025-26.
  Standalone is in the safe zone in FY2022-23 and FY2023-24 and in the grey zone from FY2024-25 on. X1 is negative
  throughout because current liabilities exceed current assets. See "X2: retained earnings" for how these
  results compare with the earlier other-equity proxy.
- **Piotroski F.** The consolidated score rises from 3 (weak) in FY2022-23 and FY2023-24 to 8 (strong) in
  FY2024-25 and FY2025-26, as profitability, margins and turnover recover.
- **Beneish M.** Every year and scope is below -1.78, so none is flagged. The highest value is standalone
  FY2022-23 (-2.2613), the only year with positive accruals (TATA > 0).
- **These are screening scores**, calibrated on other samples: the US for Beneish, and emerging-market
  non-manufacturers for Z''. With the proxies above, read them as directional indicators, not as audit
  conclusions.
