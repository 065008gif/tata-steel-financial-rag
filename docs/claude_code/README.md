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
