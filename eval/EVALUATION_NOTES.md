# Evaluation notes — final run (eval/results/run_20260927_0136.json)

## Automatic scores (30 questions)
| Tier | Result |
|---|---|
| 1. Filtered retrieval (search only, correct filters) | Hit Rate@4 = 1.00, MRR = 1.00 |
| 2a. Numeric accuracy | 22/22 numeric questions fully correct; 57/57 expected numbers found |
| 2b. Source pages retrieved / cited | 24/24 questions retrieved the expected pages; 48/53 expected pages cited |
| 2c. Abstention | 30/30 (all 3 out-of-scope traps refused; no valid question wrongly refused) |
| 2d. Grounding (automatic numeric verification) | 30/30 answers fully grounded |
| Average latency / tool calls | 11 s / 2.9 |

Answer key: every expected number was derived from the verified statement data, and all 114 raw input figures were
cross-checked against the text of their cited PDF pages (114/114 found).

## Hand-graded (qualitative) questions
| ID | Grade | Notes |
|---|---|---|
| F1 segment EBITDA | Correct | India 33,035.63 / Netherlands 2,721.52 / UK (2,568.99) ₹ crore, note 43 (F256); segments sum to 34,847.73 and reconcile to profit before exceptional items and tax 17,001.15. |
| G1 risk evolution | Correct method, unreliable conclusions | Compares named risks from the Integrated Report risk sections (after adding list_risk_disclosures), but called risks "new in FY26" that FY23 also discusses (regulatory risk: 3 FY23 chunks; employee well-being: 8; R&D: 12) and misreported its own search results. |
| G2 UK losses | Partial | Correct segment figures (UK -4,134.20 → -2,568.99, +1,565.21) and UK government support; but attributed India's new labour-code charge to the UK, linked exceptional provisions to segment results (which exclude them), and omitted the electric-arc-furnace transition despite 32 FY26 chunks discussing it. |
| G3 key audit matters | Correct | Both KAMs (litigation/contingent liabilities; carrying amount of PPE and goodwill of the Tata Steel Nederland CGU), p. F131. |
| I1 verdict | Correct, fully grounded | Covers liquidity, leverage, profitability and cash flow. |
| E2 Altman Z'' | Correct | FY2024-25 0.8666 / FY2025-26 0.9604, distress zone (actual retained earnings; see below). |
| E3 Piotroski F | Correct | FY2025-26 score 8, strong. |
| E4 Beneish M | Correct | FY2025-26 -2.9793, no manipulation flag. |

## Errors found by the evaluation, traced to their true source
| Symptom | Looked like | Actual source | Fix |
|---|---|---|---|
| F1 said segment EBITDA is not disclosed | Reasoning error | (1) Measure is labelled "segment results before exceptional items, interest, tax and depreciation"; (2) search tool truncated chunks at 2,500 chars and the row sat at char 3,416; (3) stacked two-year rows with a split label pointed the model at the prior year | Rule on equivalent measures; table compaction (10,889 → 2,570 chars); stacked-row repair stamps each row with its fiscal year (verified: FY26 external revenue total = 2,32,139.94) |
| A5 gave FY2024-25 inventories for "31 March 2024" | Wrong number | Date-to-fiscal-year mapping | Fiscal-year convention in prompt and in get_financials output |
| E1 scored 2/6 | Wrong numbers | Scorer: answer gave 81.636% for 0.8164x | Scorer compares x100 / ÷100 in both directions; prompt rule: multiples as "0.82x" |
| H2, H4 "failed" abstention | Hallucination | Scorer: refusal phrasings ("cannot be provided", "cannot supply") not recognised | Broader refusal detector |
| Unverified "-31", "-26", "-35,064", "157.51" | Ungrounded numbers | Checker: dates ("31-Mar-2024"), bare year ranges ("2025-26"), punctuation dashes, and "Ind AS"-style pattern eating "was 49" | Date/range-aware, attached-sign-only, word-bounded patterns |
| Answers with no page citations | — | Tables pasted from compute_metric had no pages; model omitted citations | Sources line on every metric table; claims check rejects figures without a page |
| E2 gave Altman 3.31 / 3.27 | Wrong number | Agent computed its own score, mixing the original 5-variable Altman Z into Z'' | Rule 21 + claims check: Altman/Piotroski/Beneish must come from compute_scores |
| E2 cited retained earnings of 39,674.80 | Discrepancy | The scores module used other equity as a disclosed proxy for retained earnings; the actual figure is ~40% of it | Claude Code task 02: page-verified retained earnings (16/16); consolidated Z'' moves from grey to distress for FY24-FY26 |
| E1 unverified "1254.11", "3780.45" | Ungrounded numbers | Checker: numbers written with lakh spacing ("3 01 254.11") | Joins Indian space-grouped digits |

## Known limitations
- Numeric grounding proves every number exists in the retrieved sources; it cannot prove a real number sits in the right
  sentence. Structured tools (get_financials, compute_metric, breakdown) minimise this by computing and laying out tables in code.
- Narrative synthesis across long sections (risk evolution, management explanations) is the weakest area (G1, G2).
- EBITDA margin uses the stated definition (PBEIT + finance costs + D&A - other income); Tata Steel's segment EBITDA
  excludes finance income and JV share instead (FY26: 14.96% vs 15.01%).
