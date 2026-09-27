# Claude Code task 06 — Frontend changes from the UI review (Edith)

Read first: `docs/claude_code/TASK_04_frontend.md` (Rule 1: build on her design — reuse her classes, variables, card
styles, Icon; append CSS; never restyle/delete except as listed), `docs/API_CONTRACT.md` (new endpoints: `/api/pdf/{report}`,
`/api/statements?scope=`, `/api/statement-pdf`, `/api/regions`, `/api/company`; scores now include FY2021-22), and the
current code in `frontend/src`. Inspect real responses with curl (backend at http://127.0.0.1:8000, Vite at :5173).
Rules still apply: never compute financial figures in the frontend; show API values exactly; Indian digit grouping.
Numbers below are the review item numbers.

## Global
- (12) Remove every em dash (—) from visible text: rewrite with commas/colons/full stops, wording otherwise unchanged.
  Missing values show "n/a" (not "—"), with a tooltip explaining why.
- (26, 31) Standard years wording wherever years/coverage are described (footer, Home hero note, Ask welcome, Sources):
  "Figures cover FY2021-22 to FY2025-26, taken from Tata Steel's four annual reports (FY2022-23 to FY2025-26; FY2021-22
  from the comparative column of the FY2022-23 report)." Wherever FY2021-22 appears as a column/point, add a small info
  marker with tooltip "From the FY2022-23 report's comparative column". Where FY2021-22 has no value (Piotroski, Beneish,
  its YoY), show "n/a" with tooltip "Needs FY2020-21, which is outside the four reports".
- (1) All PDF links use the API's relative `pdf_url`s (they now point to `/api/pdf/...`, served locally).

## Home
- (11) The hero (badge, headline, paragraph, both buttons, note, art card with its floating cards) must fit on ONE screen
  at 100% browser zoom on a 1366x768 and 1920x1080 viewport, without scrolling. Change ONLY sizes/spacing of the hero
  (e.g. clamp() based on viewport height); no text or element changes; nothing else on the site changes size.
- (6) "Tata Steel at a glance": a year dropdown (FY2022-23..FY2025-26, default FY2025-26); all 5 tiles update to that
  year (values and the API's YoY). Heading shows the selected year.
- (7) Above the tiles: "About Tata Steel" — the facts from `/api/company`, each with a small page link.
- (8) "How its financials look in <year>": 3-5 short factual bullets built ONLY from API values for the selected year
  (revenue and its YoY, profit and its YoY, net debt, Altman zone, Piotroski) — templated wording, no invented narrative.
- (9) Close the section with one line: Edith can explain any of these — trends, ratios, DuPont, composite scores, segment
  and region performance, audit matters or an overall verdict — with every figure cited (rewrite without em dashes).
- (10) "Try asking": keep ONLY these two chips: "Run a DuPont analysis of Tata Steel's consolidated ROE for FY2025-26."
  and "How has Tata Steel's consolidated profit for the year changed from FY2022-23 to FY2025-26?"

## Ask Edith
- (13, 17) The sidebar fills the whole left side at full height alongside the chat panel (no short box with an inner
  scroll hiding content); the chat panel is taller (fills the viewport below the page title). "Recent conversations" must
  be visible at 100% zoom without zooming out.
- (14) Exactly 6 suggestions, short labels that send the full question:
  "Profit trend, FY23 to FY26" → "How has Tata Steel's consolidated profit for the year changed from FY2022-23 to FY2025-26?";
  "DuPont analysis of ROE" → "Run a DuPont analysis of Tata Steel's consolidated ROE for FY2025-26.";
  "Altman, Piotroski, Beneish" → "What are Tata Steel's Altman Z'', Piotroski F and Beneish M scores for FY2025-26?";
  "India vs Netherlands vs UK" → "Compare the EBITDA of Tata Steel's India, Netherlands and UK segments in FY2024-25 and FY2025-26.";
  "Overall verdict" → "Give an overall verdict on Tata Steel's financial health in FY2025-26.";
  "Can it predict FY2027-28?" → "What will Tata Steel's revenue be in FY2027-28?" (hint: Edith refuses what the reports can't answer).
- (18) Bigger, readable fonts across the sidebar (suggestions, "What Edith will show", recent conversation titles).
- (19) Fix the overlap: nothing may draw over the "Hide sidebar" button when the sidebar content scrolls.
- (16) Answer tables fit the chat panel width (wrap long cells, no clipped columns; horizontal scroll only as a last resort).
- (20) Link "Review evaluation design" → "See evaluation results".
- (4) Waiting hint: "Usually 10-60 seconds; the first question may take 2-3 minutes."

## Dashboard
- (22) Control bar: Reporting basis (existing), a Year dropdown (FY2021-22..FY2025-26, default FY2025-26) replacing the
  single "Annual" Period button, and (30) a Region dropdown. The caption reads e.g. "Showing consolidated view · FY2022-23".
  Year drives every card: metric cards (value + YoY vs previous year; FY2021-22 YoY "n/a"), the chart (full 5-year trend,
  selected year highlighted), ratios (selected year value; bars and sparklines stay), scores and segments (selected year
  column highlighted), health summary (selected year).
- (30) Region: "All regions" (default) + India, Netherlands, UK, Europe, South-East Asia, Rest of the world from
  `/api/regions`. Selecting a region shows a region view card (revenue, EBITDA, EBITDA margin, share of group revenue and
  EBITDA for the selected year, and a 5-year trend in her chart style, with sources). Group-level cards (balance sheet,
  cash flow, ratios, net debt, scores) show a small note "Group-level only: the reports don't break this down by region".
  Europe exists only FY2021-22..FY2023-24; Netherlands/UK from FY2024-25 — show "n/a" otherwise.
- (23) Composite scores: add the FY2021-22 column (Altman value; Piotroski/Beneish "n/a" with the reason).
- (24) Remove the "Every figure is verified" card; Statement coverage takes the full width.
- (33) Statement coverage: chips for FY2021-22..FY2025-26 from `/api/statements?scope=<basis>`; each opens ONLY that
  statement (`url` → `/api/statement-pdf...`), following the basis toggle; FY2021-22 tooltip as above.
- (27) Statement coverage: same green-blue gradient but noticeably lighter; apply the same lighter gradient to the 4 KPI
  cards and the control bar; adjust text colours for contrast (dark text if the tint is light).
- (25) Financial performance + Financial ratios: larger, readable text everywhere (axis labels, legend, subtitle, ratio
  names, values, captions, larger sparklines); the chart fills its card height (no empty space below it).
- (28) Chart: one solid colour for the line and points; the selected year's point in a distinct accent from her palette,
  larger, with its value label on the chart; legend "<item>" and "Selected year: <FY>"; hover shows value and source.

## Evaluation
- (29) Larger text, especially explanatory text (measure descriptions, status text, category table, chips, review queue,
  "How the evaluation works"); headings scaled in proportion.
- (5) Future-tense copy → present/past ("How answer quality is tested", "What is assessed").

## Sources
- (32) Larger text, especially explanatory text. (31) Add an FY2021-22 card next to the four reports: "FY2021-22: figures
  from the comparative column of the FY2022-23 report", linking to that report. Report cards open `pdf_url` (local copy);
  show `official_url` as a small secondary link "tatasteel.com".

## Done means
`npm run build` and `npm run lint` pass; headless-Chrome screenshots at 1366x768 and 1920x1080 (100% zoom) of every page
confirm: hero fits one screen, sidebar full height with recent conversations visible, no em dashes anywhere (grep the
rendered text), year and region dropdowns update the cards, statement chips return application/pdf. At most 3 real
/api/ask calls. Report per item number: done / partially / not done, with notes.

## Boundaries
Edit only `frontend/`. No backend changes, no git, no Docker, never read `.env`.
