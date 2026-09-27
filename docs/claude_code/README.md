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

## Task 03 — segment results for all years
**Brief:** `TASK_03_segments.md`. **Claude Code result (6 min 58 s):** `src/ingest/segments.py` places every number in its
column by position on the page (cells can be blank or "-", so reading order is unreliable), for all four reports and
both years of each. Checks: value on its page 293/293; segments + eliminations = total 31/31; total external revenue =
consolidated revenue from operations 8/8; external + inter-segment = segment revenue 74/74 (a check it added). It kept
segment changes separate (Europe split into Netherlands and UK; Long Products merged into India), flagged restated values,
and left one blank cell out rather than guessing. 60 tests pass. New `get_segments` tool and `GET /api/segments`.
**Independent verification:** four values located directly on pages of four different reports (e.g. India FY2021-22
51,456.30; Europe FY2023-24 (7,612.44)); the combined latest-report view reconciles to the printed total for all five years;
tests re-run (60/60); the live endpoint checked after a container rebuild.

## Tasks 04-07 — the frontend, built on the teammate's design
The teammate's "Edith" React app was a polished but static prototype (no API calls). Claude Code connected and completed
it in four briefs, each with Rule 1: preserve her design, reuse her classes and variables, append CSS, change only what
the brief lists. Every task was checked with headless-Chrome screenshots, `npm run build` and `npm run lint`.
- **Task 04:** API client and proxy; chat with verification badges, citations and steps; live dashboard (metrics, chart,
  ratios, composite scores, segments); real evaluation page; new Sources page; Dockerfile and nginx config.
- **Task 05 (backend, from the UI review):** local PDF serving (tatasteel.com returned 403), statement-only PDFs, FY2021-22
  Altman, regions, page-verified company facts, a `dupont` tool and stricter grounding (calculator inputs no longer count
  as verified; this exposed a sign error in the EBITDA-margin answer, since fixed).
- **Task 06:** 33 review items: year and region filters, FY2021-22 explained everywhere, no em dashes, readability.
- **Task 07:** measured readability: a font-size audit of 3,003 text nodes found 2,796 below the minimum at 1366x768;
  after the changes, 0 at both 1366x768 and 1920x1080. Full-height chat layout; every missing value shows its reason.
**Independent verification** throughout: re-run tests, on-screen review by the team, and the full 32-question evaluation
(24/24 numeric, 60/60 numbers, 32/32 abstention, 31/32 grounded).
