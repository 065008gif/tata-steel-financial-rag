# Development process: conversational assistant vs Claude Code

The project used two AI tools with a deliberate division of labour.

| Tool | Used for | Why |
|---|---|---|
| **Claude (chat)** | Environment setup; company choice; parsing, chunking and evaluation design; building the ingestion pipeline, index, agent and API step by step; diagnosing every failure from real output; independent verification of all results | These steps needed decisions, investigation of unexpected real-world data (Docling row merges, restatements, reclassifications, stacked-year tables) and one-step-at-a-time verification against the PDFs |
| **Claude Code (agentic, in the terminal)** | Task 01: the composite scores module (Altman Z'', Piotroski F, Beneish M): `src/analysis/scores.py`, the `compute_scores` agent tool, `GET /api/scores`, 32 automated tests, `docs/SCORES.md` | A well-specified, multi-file component with clear formulas and a testable definition of done: the kind of work an agentic tool can plan, implement, test and iterate on autonomously |

## How the hand-off worked
1. The requirements were agreed in chat and written as a self-contained brief: `TASK_01_composite_scores.md` (formulas, data sources, year-pair rule, disclosed proxies, deliverables, tests, definition of done, and strict boundaries: no git, no `.env`, no changes to `data/` or `eval/`, no model calls, no Docker restarts).
2. Claude Code (v2.1.283, Opus 5.5, auto permission mode) completed it in 5 min 48 s. It checked data availability before writing code, fixed an arithmetic error in its own test, and toned down two unverified causal claims in its documentation. It stayed within all boundaries.
3. **Its output was verified independently, not assumed correct:**
   - Re-ran its tests: 32 passed.
   - Recomputed Altman Z'' for FY2025-26 (consolidated) by hand from the verified balance sheet and P&L: X1 -0.081833, X2 0.335000, X3 0.076798, X4 0.525541, Z'' 1.6232, matching exactly. (This check also found that the brief itself had stated X4 as 0.525544; the code's 0.525541 was correct.)
   - Checked all nine Piotroski FY2024-25 signals against known figures (e.g. F5 = 0 because non-current borrowings rose from 51,576.73 to 68,551.81).
   - Rebuilt the Docker backend and confirmed `GET /api/scores` serves the same results.

## Task 02 — replacing a proxy that changed the conclusion
**Trigger:** during evaluation, the agent (answering an Altman question) cited actual retained earnings from the "Other
equity" note, revealing that the scores module's disclosed proxy (other equity as retained earnings) overstated X2 by
about 0.2 for the consolidated group.
**Brief:** `TASK_02_retained_earnings.md`: extract retained earnings for every report, scope and year, verify every value
on its PDF page, switch Altman X2 to it (with a recorded fallback), and update the tests and documentation.
**Claude Code result (3 min 51 s):** `src/ingest/retained_earnings.py` found the "A. Retained earnings" movement table in
all 8 report/scope combinations. It checked opening + movements = closing in every column, and verified all 16 values on
their pages (16/16). Tests grew to 37 (all pass). It also flagged, but did not edit (outside its boundary), an outdated
X2 label in `src/agent/tools.py`, which was then fixed on request.
**Independent verification:** the values were located in the PDFs directly, in the "Balance at the end of the year" row
(e.g. FY2025-26 report p. 475: 39,674.80 / 33,698.53; FY2024-25 report p. 458: 33,698.53 / 34,815.73, which chains
correctly to the next year's opening balance). Z'' for FY2025-26 (consolidated) was recomputed by hand as 0.9604
(X2 = 0.131699).
**Impact:** consolidated Altman Z'' moves from the grey zone to the **distress** zone for FY2023-24 (0.4383), FY2024-25
(0.8666) and FY2025-26 (0.9604); standalone FY2024-25 moves from safe to grey. See `docs/SCORES.md`.
