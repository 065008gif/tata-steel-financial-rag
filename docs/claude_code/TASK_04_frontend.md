# Claude Code task 04 — Connect the "Edith" frontend to the real backend and complete it

## Rule 1 (most important): build on the existing design
`frontend/` is a teammate's React app ("Edith"): `src/App.jsx` (Header, HomePage, AskPage, DashboardPage, EvaluationPage,
Footer, Icon, Brand, StatusPill, SectionHeading) and `src/App.css`. Its look is final: dark green header/footer, teal→blue
gradient accents, pastel cards, the fonts, spacing, radii, shadows, animations, the Icon set.
- PRESERVE every existing section, component, class name and style unless this brief explicitly says to change it.
- NEW elements must reuse her existing classes, CSS variables, colours, card styles and Icon component so they look like the
  same author built them. Add new CSS at the END of App.css (or a new CSS file imported after it), reusing her variables.
- Do not restyle, reorder or delete her sections. Only the texts listed below change. Keep her copy everywhere else.
- You may move code into new files (e.g. `src/api.js`, `src/components/*.jsx`) when App.jsx would grow too large, but keep
  her components recognisable and her page structure (state-based page switching) unchanged.

## The backend (running now at http://127.0.0.1:8000, Docker; do not modify it)
Read `src/api/main.py`, `docs/API_CONTRACT.md`, `README.md` (API reference with real responses), `docs/SCORES.md`,
`docs/SEGMENTS.md`, `eval/EVALUATION_NOTES.md`. Endpoints: `/api/health`, `POST /api/ask` (with optional `history`),
`/api/financials?items=&scope=`, `/api/items`, `/api/metrics?scope=`, `/api/scores?scope=`, `/api/segments`,
`/api/evaluation`, `/api/reports`. Inspect real responses with curl before coding against them.
- Money is INR crore. Display with Indian grouping (`toLocaleString("en-IN")`, 2 decimals), negatives with a minus sign.
- NEVER compute financial figures in the frontend (no ratios, sums, growth %). Show values and changes exactly as the API
  returns them. Scaling bar widths / chart coordinates for display is fine.
- `null` values show as "—" with a tooltip "Not reported". Restated values (`restated_basis` / `restated`) get a small "R"
  marker with a tooltip.
- Only years/items the API returns exist. There is NO quarterly data.

## Technical setup
- `vite.config.js`: add a dev proxy `/api` → `http://127.0.0.1:8000`. All calls use relative paths (`/api/...`).
- `src/api.js`: one client; `ask()` uses AbortController with a 300 s timeout and supports cancel; errors surface as
  friendly messages (backend `{"error": ...}`; 422 `detail[0].msg`; network down → "Edith's backend is not reachable").
- Add `react-markdown` + `remark-gfm` (answer tables). No chart library: drive her own SVG chart style with real data.
- Remove unused `react-router-dom` only if nothing uses it; remove unused Vite template assets (react.svg, vite.svg) only
  if unreferenced. `index.html` title → "Edith · Tata Steel Financial Analysis".
- Deployment: `frontend/Dockerfile` (node:22 build → nginx:alpine serving `dist/`) and `frontend/nginx.conf`
  (SPA fallback to index.html; `location /api/ { proxy_pass http://backend:8000; proxy_read_timeout 300s;
  proxy_send_timeout 300s; }`). `docker-compose.yml` already defines `frontend` and `tunnel` under profile "full";
  change it only if needed for these files to work.

## Header / global
- Add a small live backend status dot in the header (green "Live" / grey "Offline" from `/api/health`, polled every 60 s).
- Add a nav entry "Sources" for the new Sources page (below). The footer link "Sources & limitations" goes there.
- Footer text: keep the disclaimer (research/education, not investment advice); replace "prototype / connected and
  checked sources" wording with accurate text: figures come from Tata Steel's FY2022-23 to FY2025-26 annual reports and
  are verified against the source pages.

## Home
- Keep hero, trust strip, feature cards, workflow timeline, Tata Steel section, CTA band.
- Hero note → "Live · Figures from Tata Steel's four annual reports (FY2022-23 to FY2025-26), each linked to its source page."
- Anchor the floating "TATA STEEL" wordmark to the hero art card (it currently floats alone mid-hero).
- Feature card 03 text → present tense (data is available now).
- "Annual and quarterly reporting" → "Four annual reports, FY2022-23 to FY2025-26".
- ADD under the hero: "Tata Steel at a glance (FY2025-26, consolidated)" — 5 KPI tiles from the API: Revenue from
  operations and Profit for the year (`/api/financials`, with the API's YoY %), Net debt (`/api/metrics` net_debt),
  Altman Z'' with its zone, Piotroski F with its interpretation (`/api/scores`). Each tile: value, small label, source hint.
- ADD a "Try asking" row of 6 question chips (from the list below); clicking opens Ask Edith and sends it.

## Ask Edith (most important)
- Keep the layout: sidebar (hide/show, New conversation, suggestions, "What Edith will show", Recent conversations), chat
  panel, avatar, composer.
- Make it a real conversation: a scrolling thread of user/assistant messages; each new question is sent to `POST /api/ask`
  with `history` = the previous turns of this conversation (user questions and assistant `answer_markdown`, oldest first,
  max 20). Clear the input after sending; Enter sends, Shift+Enter = newline; auto-scroll to the newest message.
- Assistant message, reusing her evidence-card style:
  - `answer_markdown` rendered with react-markdown + remark-gfm (tables styled to match her design, horizontally scrollable).
  - Verification badge from `verification`: "Verified · N/N figures" (green), "Partially verified · N/M" (amber, list
    `unverified_figures`), or "No figures to verify" (neutral) for refusals/narrative answers. Show `warnings` if any.
  - Citations: chips "FY2025-26 · consolidated balance sheet · F143" that open `pdf_url` in a new tab (it opens the page).
    Her "Supporting evidence" card becomes the citations panel.
  - Collapsible "How this answer was produced" listing `steps` (tool descriptions), plus model and elapsed seconds.
  - Copy-answer button.
- While waiting: her typing/skeleton style, elapsed-seconds counter, "Usually 10-60 seconds" hint, and a Cancel button.
- Errors: friendly message in the thread with a Retry button.
- "Recent conversations": store whole conversations for the session (in React state); clicking one restores its thread.
  "New conversation" starts an empty thread (history resets).
- Replace her 4 suggestions with grouped suggested questions (keep her suggestion-item style; the list can scroll):
  - Lookups: "What was Tata Steel's consolidated revenue from operations in FY2025-26?" ·
    "What were Tata Steel's consolidated current borrowings as at 31 March 2026?"
  - Trends: "How has Tata Steel's consolidated profit for the year changed from FY2022-23 to FY2025-26?" ·
    "What is the trend in Tata Steel's consolidated current ratio from FY2022-23 to FY2025-26?"
  - Ratios: "Run a DuPont analysis of Tata Steel's consolidated ROE for FY2025-26." ·
    "What was Tata Steel's consolidated debt-to-equity ratio in FY2025-26?"
  - Scores: "What are Tata Steel's Altman Z'', Piotroski F and Beneish M scores for FY2025-26?"
  - Segments: "Compare the EBITDA of Tata Steel's India, Netherlands and UK segments in FY2024-25 and FY2025-26."
  - Audit & risk: "What were the key audit matters in Tata Steel's FY2025-26 consolidated audit report?"
  - Verdict: "Give an overall verdict on Tata Steel's financial health in FY2025-26."
  - Try to trick it: "What will Tata Steel's revenue be in FY2027-28?" (label it: Edith refuses what the reports can't answer)
  - Also show a hint that follow-ups work, e.g. after a lookup: "And in FY2023-24?"
- Welcome message: keep "Hello, I'm Edith." Replace the prototype callout with: what Edith covers (four annual reports,
  consolidated and standalone, FY2021-22 to FY2025-26), that every figure is verified and cited, that follow-up questions
  work, and that answers take 10-60 seconds. Composer footnote → "Answers are verified against the source pages".
- Keep "What Edith will show" (accurate); Status row → "Verified / partially verified, with each figure checked".

## Dashboard
- Keep: the reporting-basis toggle (Consolidated/Standalone — make it drive every card), the metric-card design, the chart
  card, the ratios card, the two dark cards. REMOVE only the "Quarterly" button (keep "Annual"). Remove the "Illustrative
  layout only" tag and the fake curves/"Chart preview" overlay once real data renders.
- Metric cards (from `/api/financials`, latest year value + the API's YoY change): Revenue from operations, Profit for the
  year, Operating cash flow (net_cash_from_operating), and Net debt (`/api/metrics` net_debt; no YoY since the API gives
  none — show a mini 5-year sparkline instead). Clicking a card selects it for the chart.
- Chart: the selected item's 5 years (FY2021-22…FY2025-26) in her exact chart style (gradient line/area, gridlines,
  x-axis labels = fiscal years, y-axis labels in INR crore, point markers with hover values).
- Ratios card: all 6 metrics from `/api/metrics` (current ratio, debt to equity, interest coverage, net profit margin,
  EBITDA margin, ROE): latest value with unit ("x" / "%"), her bar (scaled for display), and a tiny 5-year trend.
- ADD "Composite scores" card (`/api/scores`, follows the basis toggle): Altman Z'' (zone chip; distress shown clearly),
  Piotroski F (0-9), Beneish M (flag / no flag) for each year, one-line meaning each, link to "How these are calculated"
  (Sources page). Note that Altman uses actual retained earnings (see docs/SCORES.md).
- ADD "Segments" card (`/api/segments`, consolidated only — say so): rows = segments, columns = years, toggle Revenue ↔
  EBITDA (segment results), "—" where a segment didn't exist that year, R marker for restated, note on Europe → Netherlands
  + UK and Long Products → India.
- ADD "Financial health summary" card: a short factual list built only from API values (Altman zone, Piotroski, current
  ratio, D/E, net debt, latest profit) — no invented narrative — plus a button "Ask Edith for the full verdict" that opens
  Ask Edith and sends the verdict question.
- "Statement coverage" card: keep; for each statement show the report years with links to the PDFs (`/api/reports`).
- Dark notice card "No financial figures are loaded" → "Every figure is verified": figures come from the reported
  statements, balance-sheet identity and subtotals are checked, restatements are marked, sources are one click away.
- Widen the inner-page container (Dashboard, Evaluation, Ask, Sources) so content uses the screen (e.g. max ~1200 px),
  keeping her responsive behaviour.

## Evaluation (`/api/evaluation`)
- Keep all her sections. Status ring → the real headline (numeric questions fully correct), with the run date.
- Measure cards → real values: Numeric accuracy (numeric questions fully correct; expected numbers found), Citation
  correctness (expected pages cited), Groundedness (answers fully grounded), Retrieval quality (Hit Rate@4 / MRR),
  Abstention (correct). Use the exact figures the API returns.
- "Results by question category": categories and pass counts from the run's records (lookup, trend, ratio, yoy,
  composite, segment, follow_up, narrative, risk_evolution, scope_trap, abstain, verdict...), filter chips from them.
- "Flagged-answer review": the known limitations, in her queue style — G1 risk evolution (correct method, unreliable
  conclusions) and G2 UK losses (partial), taken from eval/EVALUATION_NOTES.md (static text is fine for these two).
- "How the evaluation will work" → "How the evaluation works": 32 questions across categories, an answer key checked
  against the PDF pages (118/118 figures found), four tiers, run automatically.

## NEW page: Sources & methodology (nav "Sources"; footer link goes here)
- The four reports (`/api/reports`): title, fiscal year, link to the PDF.
- How it works (her card style): parse the statements → verify (balance identity, subtotals, restatements) → index
  (hybrid search) → answer (tools compute every number) → check (every figure matched to its source) → cite.
- Composite scores and segments: short explanation, proxies, and that they were built with Claude Code and independently
  verified (docs/claude_code/README.md).
- Limitations (honest): annual data only; narrative comparison across long sections is the weakest area; answers take
  10-60 s; research/education use only.

## Done means
- `cd frontend && npm run build` succeeds and `npm run lint` has no errors.
- With the Vite dev server (already running on http://127.0.0.1:5173; restart it only if needed), every page loads real
  data via the proxy: verify with curl through 5173 (e.g. `/api/health`, `/api/metrics`, `/api/scores`, `/api/segments`)
  and by checking the browser console has no errors if you can.
- You may send AT MOST 5 real questions to `/api/ask` to test the chat, including one follow-up with `history`.
- `docker build` is NOT required (no Docker commands); just write the Dockerfile and nginx.conf correctly.
- Report: files changed/added, a per-page list of what was kept / connected / changed / added, anything you could not do,
  and any backend gap you found (describe it; do not change the backend).

## Boundaries
- Edit only inside `frontend/` (and `docker-compose.yml` only if strictly needed for the frontend service).
- Do NOT modify `src/`, `eval/`, `data/`, `tests/`, `docs/` (except creating nothing there), `.env` (do not read it).
- No git commands, no Docker commands. npm install/build/lint/dev are allowed.
