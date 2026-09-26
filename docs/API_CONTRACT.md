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
