# Composite financial scores

Altman Z'' (book-equity), Piotroski F-score and Beneish M-score for Tata Steel, consolidated and standalone,
FY2022-23 to FY2025-26 (FY2025-26 = year ended 31 March 2026). All inputs are canonical statement items in
INR crore from `data/processed/financials.json` and `data/processed/financials_by_report.json`.

- Code: `src/analysis/scores.py` (`altman_z`, `piotroski_f`, `beneish_m`, `all_scores`), pure functions that read the JSON directly.
- Agent tool: `compute_scores(score, fiscal_years=None, scope="consolidated")` in `src/agent/tools.py`.
- API: `GET /api/scores?scope=consolidated|standalone`.
- Tests: `.venv/bin/python -m pytest tests/test_scores.py -q`.

Every result carries the score, its zone or interpretation, every component, every input (value, source page, and
basis), the `proxies` list, any `fallbacks`, and `missing`. If an input is unavailable or a denominator is zero,
the score is `None` and a `reason` is given. The code never raises and never guesses a value.

## Which report each value comes from

- **Altman Z''** uses a single year, so it takes values from `financials.json` (the latest report that contains the year).
- **Piotroski F and Beneish M** compare year t with t-1. Both years come from the **report of year t**, which
  presents t-1 as a comparative (restated where applicable). If that report lacks an item, the code falls back to
  `financials.json` and records it in `fallbacks`. In practice, the only fallback is Piotroski's beginning-of-year
  assets for t-1 (total_assets of t-2), because report t does not contain year t-2. One exception: the standalone
  FY2024-25 report includes a third balance sheet, so it does contain t-2.

## Altman Z'' (book-equity version)

| Component | Formula |
|---|---|
| X1 | (total_current_assets - total_current_liabilities) / total_assets |
| X2 | other_equity / total_assets |
| X3 | (profit_before_tax + finance_costs) / total_assets |
| X4 | total_equity / (total_assets - total_equity) |

Z'' = 6.56·X1 + 3.26·X2 + 6.72·X3 + 1.05·X4. Zones: > 2.60 **safe**; 1.10–2.60 **grey**; < 1.10 **distress**.

Proxies:
- **X2 uses other equity in place of retained earnings.** Retained earnings are not a canonical item. Under Ind AS,
  "other equity" includes retained earnings plus other reserves (securities premium, OCI reserves, and so on).
- **X4 uses book equity.** The market value of equity is not in the reports. This is why the book-equity Z''
  variant is used, not the original market-value Z.
- **X3 approximates EBIT as PBT + finance costs.** PBT is after exceptional items, so exceptional items are
  included in EBIT.

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

| Score | FY2022-23 | FY2023-24 | FY2024-25 | FY2025-26 |
|---|---|---|---|---|
| Altman Z'' | 2.0859 (grey) | 1.1056 (grey) | 1.5226 (grey) | 1.6232 (grey) |
| Piotroski F | 3 (weak) | 3 (weak) | 8 (strong) | 8 (strong) |
| Beneish M | -2.9170 (unlikely manipulator) | -3.2359 (unlikely manipulator) | -2.9533 (unlikely manipulator) | -2.9793 (unlikely manipulator) |

| Component | FY2022-23 | FY2023-24 | FY2024-25 | FY2025-26 |
|---|---|---|---|---|
| Z: X1 | -0.0371 | -0.1020 | -0.0634 | -0.0818 |
| Z: X2 | 0.3537 | 0.3320 | 0.3218 | 0.3350 |
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

| Score | FY2022-23 | FY2023-24 | FY2024-25 | FY2025-26 |
|---|---|---|---|---|
| Altman Z'' | 3.5850 (safe) | 3.5297 (safe) | 2.7248 (safe) | 2.5646 (grey) |
| Piotroski F | 3 (weak) | 4 (weak) | 5 (average) | 7 (average) |
| Beneish M | -2.2613 (unlikely manipulator) | -3.4646 (unlikely manipulator) | -2.7433 (unlikely manipulator) | -2.8691 (unlikely manipulator) |

| Component | FY2022-23 | FY2023-24 | FY2024-25 | FY2025-26 |
|---|---|---|---|---|
| Z: X1 | -0.0456 | -0.0519 | -0.0818 | -0.1112 |
| Z: X2 | 0.5637 | 0.5646 | 0.4938 | 0.4923 |
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
- **Altman Z''.** Consolidated stays in the grey zone in every year, with the low point in FY2023-24 (the loss
  year). Standalone is in the safe zone until FY2024-25 and moves into the grey zone in FY2025-26 (2.5646). X1 is
  negative throughout because current liabilities exceed current assets.
- **Piotroski F.** The consolidated score rises from 3 (weak) in FY2022-23 and FY2023-24 to 8 (strong) in
  FY2024-25 and FY2025-26, as profitability, margins and turnover recover.
- **Beneish M.** Every year and scope is below -1.78, so none is flagged. The highest value is standalone
  FY2022-23 (-2.2613), the only year with positive accruals (TATA > 0).
- **These are screening scores**, calibrated on other samples: the US for Beneish, and emerging-market
  non-manufacturers for Z''. With the proxies above, read them as directional indicators, not as audit
  conclusions.
