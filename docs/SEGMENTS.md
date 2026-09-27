# Segment results (all years)

Segment revenue and segment results for every reported segment, FY2021-22 to FY2025-26, taken from the consolidated
**"Segment reporting"** note of each annual report. All figures are in INR crore. Every value is verified on its PDF page.

Segment **"results"** are the report's *"Segment results before exceptional items, interest, tax and depreciation"*,
which means they are **segment EBITDA**. Per note (i) of the segment note, the CODM reviews profit before finance
income/cost, depreciation and amortisation, share of profit of joint ventures and associates, tax, and exceptional items.

## Pipeline
| Step | File | Output |
|---|---|---|
| Extraction and checks | `src/ingest/segments.py` | `data/processed/segments.json` plus the printed check table |
| Latest-report view and restated flags | `src/analysis/segments.py` → `get_segments(fiscal_years=None, items=None)` | dict, one value per segment, year and item, with source page |
| Agent tool | `get_segments(fiscal_years, items)` in `src/agent/tools.py` | data, a markdown table and a `Sources:` line |
| API | `GET /api/segments` in `src/api/main.py` | `{unit, years, items, note, segments: [{key, name, values, sources, restated}], eliminations, totals}` |
| Tests | `tests/test_segments.py` (23 tests) | |

Items: `external_revenue`, `inter_segment_revenue`, `segment_revenue` (the "Total Revenue" row) and `segment_results`.

## Sources
| Report | PDF page | Page label | Years on page | Segment columns |
|---|---|---|---|---|
| FY2022-23 | 551 | F258 | FY2022-23, FY2021-22 | 7 + eliminations + total |
| FY2023-24 | 538 | F250 | FY2023-24, FY2022-23 | 7 + eliminations + total |
| FY2024-25 | 513 | F259 | FY2024-25, FY2023-24 | 7 + eliminations + total |
| FY2025-26 | 534 | F256 | FY2025-26, FY2024-25 | 8 + eliminations + total |

## Layout and layout differences
All four reports use the same layout:
- Segments are columns. The last two columns are inter-segment eliminations and Total.
- Each item is two stacked rows with no year labels. The first row is the report's year and the second is the prior year.
- Row labels can be split across lines. For example, "Segment results before exceptional items, interest, tax and depreciation" spans 3–4 lines.

The plain-text extraction cannot be read in token order, because some cells are blank and others hold "-". The
extractor therefore uses pymupdf word coordinates:
- Numbers are right-aligned, so each is placed in the column whose cluster of right edges it falls into.
- Header phrases are merged into the same columns where their x-ranges overlap.
- Each item takes the numeric lines between its label and the next item's label. Exactly two lines are required.

Differences between reports:
| Report | Segment columns (as printed) | Other differences |
|---|---|---|
| FY2022-23 | Tata Steel India, **Tata Steel Long Products**, Other Indian operations, **Tata Steel Europe**, Other trade related operations, South-East Asian operations, Rest of the world | External-revenue cell of the eliminations column is **blank** in both years (not "-"). It is omitted, not zero-filled. |
| FY2023-24 | Tata Steel India, **Neelachal Ispat Nigam Limited**, Other Indian operations, Tata Steel Europe, … | Long Products merged into Tata Steel India; NINL shown separately. FY2022-23 restated on that basis. The prior-year **inter-segment revenue Total cell is blank** (see Unresolved). |
| FY2024-25 | as FY2023-24 ("Other Indian Operations", "Rest Of the world" capitalised differently) | FY2023-24 restated (Tata Steel India, Other Indian operations, eliminations) |
| FY2025-26 | Tata Steel Europe **split into "Tata Steel Netherlands operations" and "Tata Steel UK operations"**; label "Inter segment revenue" (no hyphen); 10 columns | FY2024-25 restated into Netherlands and UK (note (v): "Previous years have accordingly been restated") |

Segment names are kept as printed. A normalised `key` matches segments across reports (`tata_steel_india`,
`tata_steel_long_products`, `neelachal_ispat_nigam`, `other_indian_operations`, `tata_steel_europe`,
`tata_steel_netherlands`, `tata_steel_uk`, `other_trade_related_operations`, `south_east_asian_operations`,
`rest_of_the_world`). Segments that exist only in some years stay separate and are never mapped onto another
segment. For example, Tata Steel Europe (to FY2023-24) is not combined with Netherlands and UK (from FY2024-25).

## Checks (`.venv/bin/python src/ingest/segments.py`)
- **(a)** Every value, in Indian format, is present in the whitespace-normalised pymupdf text of its cited page. A "-" cell is a "-" token in its column.
- **(b)** Segments plus eliminations equal the printed Total, for each item and year (to 0.01).
- **(c)** Total external revenue equals consolidated `revenue_from_operations` of the same report and year in `financials_by_report.json` (to 0.01).
- **(d)** Extra check: external plus inter-segment revenue equals segment revenue, for every column and year (to 0.01).

A value that fails any check is left out and listed as unresolved.

| Report | Year | (a) on page | (b) sum = total | (c) = revenue from operations | (d) ext + inter = revenue |
|---|---|---|---|---|---|
| FY2022-23 | FY2022-23 | 35/35 | 4/4 | 1/1 | 9/9 |
| FY2022-23 | FY2021-22 | 35/35 | 4/4 | 1/1 | 9/9 |
| FY2023-24 | FY2023-24 | 36/36 | 4/4 | 1/1 | 9/9 |
| FY2023-24 | FY2022-23 | 35/35 | 3/3 (Total cell blank for inter-segment revenue) | 1/1 | 9/9 |
| FY2024-25 | FY2024-25 | 36/36 | 4/4 | 1/1 | 9/9 |
| FY2024-25 | FY2023-24 | 36/36 | 4/4 | 1/1 | 9/9 |
| FY2025-26 | FY2025-26 | 40/40 | 4/4 | 1/1 | 10/10 |
| FY2025-26 | FY2024-25 | 40/40 | 4/4 | 1/1 | 10/10 |
| **All** | | **293/293** | **31/31** | **8/8** | **74/74** |

## Latest report per year and restatements
`get_segments` takes each year from the **latest report that presents it**:

| Year | Report used |
|---|---|
| FY2021-22 | FY2022-23 |
| FY2022-23 | FY2023-24 |
| FY2023-24 | FY2024-25 |
| FY2024-25 | FY2025-26 |
| FY2025-26 | FY2025-26 |

A value is flagged `restated` when another report prints the same segment key, year and item with a different value.
The other reports' values are kept in `as_reported`.

Restatements found (segment results):
| Segment | Year | Used value (report) | Earlier value (report) |
|---|---|---|---|
| Tata Steel India | FY2022-23 | 28,753.76 (FY2023-24) | 28,174.58 (FY2022-23): Long Products merged in, NINL separated |
| Other Indian operations | FY2022-23 | 761.27 (FY2023-24) | 1,107.90 (FY2022-23) |
| Tata Steel India | FY2023-24 | 31,166.78 (FY2024-25) | 31,004.44 (FY2023-24) |
| Other Indian operations | FY2023-24 | 607.97 (FY2024-25) | 912.86 (FY2023-24) |
| Other trade related operations | FY2024-25 | 123.90 (FY2025-26) | 137.47 (FY2024-25) |
| Inter-segment eliminations | FY2022-23 / FY2023-24 / FY2024-25 | (837.57) / (1,972.49) / (277.71) | (765.17) / (2,115.04) / (273.03) |

Total segment results are unchanged by every restatement.

Some segment-years are printed only in an older report, because the later report re-segmented that year. These are
returned separately as `superseded` and are not mixed into the time series:
- **Tata Steel Long Products FY2022-23** (FY2022-23 report, F258): external revenue 7,117.87, segment revenue 8,991.78, results (613.08).
- **Tata Steel Europe FY2024-25** (FY2024-25 report, F259): external revenue 76,375.26, segment revenue 76,416.15, results (3,327.07).
  - The FY2025-26 split gives external revenue of Netherlands 53,119.23 + UK 23,256.04 = 76,375.27 (0.01 rounding).
  - The split gives results of 825.38 + (4,134.20) = (3,308.82). The 18.25 difference moved to other trade related operations (−13.57) and eliminations (−4.68).

## Results table (all years)
Each year comes from the latest report presenting it. `*` = restated versus an earlier report. `-` = segment not
reported for that year. Negative values are shown with a minus sign; the reports print them in brackets.

| Segment results (EBITDA before exceptional items) (INR crore) | FY2021-22 | FY2022-23 | FY2023-24 | FY2024-25 | FY2025-26 |
|---|---|---|---|---|---|
| Tata Steel India | 51,456.30 | 28,753.76* | 31,166.78* | 28,217.36 | 33,035.63 |
| Neelachal Ispat Nigam Limited | - | -773.23 | 52.88 | 1,067.17 | 1,236.29 |
| Other Indian Operations | 546.79 | 761.27* | 607.97* | 548.20 | 707.25 |
| Tata Steel Netherlands operations | - | - | - | 825.38 | 2,721.52 |
| Tata Steel UK operations | - | - | - | -4,134.20 | -2,568.99 |
| Other trade related operations | 39.40 | 168.49 | 1,144.08 | 123.90* | 610.79 |
| South-East Asian Operations | 1,255.26 | 473.64 | 109.53 | 131.61 | 774.55 |
| Rest of the world | -382.98 | -480.91 | -94.65 | -699.91 | -837.37 |
| Tata Steel Europe | 12,163.85 | 4,632.06 | -7,612.44 | - | - |
| Tata Steel Long Products | 1,288.31 | - | - | - | - |
| Inter segment eliminations | -2,537.35 | -837.57* | -1,972.49* | -277.71* | -831.94 |
| **Total** | 63,829.58 | 32,697.51 | 23,401.66 | 25,801.80 | 34,847.73 |

| Segment revenue (total) (INR crore) | FY2021-22 | FY2022-23 | FY2023-24 | FY2024-25 | FY2025-26 |
|---|---|---|---|---|---|
| Tata Steel India | 1,29,021.35 | 1,42,913.32* | 1,40,932.65* | 1,32,516.66 | 1,39,720.22 |
| Neelachal Ispat Nigam Limited | - | 1,645.55 | 5,505.43 | 5,701.07 | 5,281.59 |
| Other Indian Operations | 21,274.90 | 10,921.59* | 10,381.98* | 10,265.82 | 12,943.95 |
| Tata Steel Netherlands operations | - | - | - | 56,889.14 | 61,354.84 |
| Tata Steel UK operations | - | - | - | 24,990.13 | 23,332.67 |
| Other trade related operations | 60,123.91 | 73,973.53 | 56,681.06 | 45,611.46 | 39,561.96 |
| South-East Asian Operations | 11,481.81 | 8,731.44 | 7,227.88 | 7,472.45 | 8,605.46 |
| Rest of the world | 739.38 | 648.77 | 1,329.89 | 1,422.34 | 1,795.19 |
| Tata Steel Europe | 90,022.96 | 90,300.39 | 78,144.00 | - | - |
| Tata Steel Long Products | 6,801.63 | - | - | - | - |
| Inter segment eliminations | -75,506.77 | -85,781.90* | -71,032.11* | -66,326.56* | -60,455.94 |
| **Total** | 2,43,959.17 | 2,43,352.69 | 2,29,170.78 | 2,18,542.51 | 2,32,139.94 |

| External revenue (INR crore) | FY2021-22 | FY2022-23 | FY2023-24 | FY2024-25 | FY2025-26 |
|---|---|---|---|---|---|
| Tata Steel India | 1,16,868.15 | 1,32,825.39* | 1,30,258.95* | 1,24,305.88 | 1,30,676.61 |
| Neelachal Ispat Nigam Limited | - | 559.38 | 1,653.32 | 383.18 | 357.68 |
| Other Indian Operations | 16,509.91 | 8,044.55* | 8,422.09* | 7,987.14 | 10,200.00 |
| Tata Steel Netherlands operations | - | - | - | 53,119.23 | 58,346.42 |
| Tata Steel UK operations | - | - | - | 23,256.04 | 22,383.41 |
| Other trade related operations | 2,874.64 | 3,041.32 | 2,502.85 | 1,279.33 | 245.86 |
| South-East Asian Operations | 11,109.24 | 8,076.87 | 6,892.74 | 6,789.38 | 8,134.77 |
| Rest of the world | 739.34 | 648.77 | 1,329.89 | 1,422.34 | 1,795.19 |
| Tata Steel Europe | 89,811.59 | 90,156.41 | 78,110.94 | - | - |
| Tata Steel Long Products | 6,046.30 | - | - | - | - |
| **Total** (= consolidated revenue from operations) | 2,43,959.17 | 2,43,352.69 | 2,29,170.78 | 2,18,542.51 | 2,32,139.94 |

Sources: FY2022-23 Annual Report, consolidated segment reporting note, page F258; FY2023-24 Annual Report, page F250;
FY2024-25 Annual Report, page F259; FY2025-26 Annual Report, page F256.

## Unresolved
- **FY2023-24 report, FY2022-23 column, inter-segment revenue, Total:** the cell is blank on page F250. The FY2022-23
  report prints "-" for the same cell. The value is omitted, not set to zero, and check (b) could not be run for that
  item and year. The segment and elimination values in that row still pass (a) and (d).
