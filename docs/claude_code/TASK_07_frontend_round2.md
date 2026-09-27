# Claude Code task 07 — Frontend review round 2: readability, full-height Ask layout, no bare "n/a"

Read `docs/claude_code/TASK_04_frontend.md` (Rule 1: build on her design; reuse her classes/variables/Icon; append CSS) and
`docs/claude_code/TASK_06_frontend_review.md`. Edit only `frontend/`. Backend at http://127.0.0.1:8000, Vite at :5173.
The owner's main complaint: text is far too small everywhere. Fix it measurably.

## 1-3, 6-8. Readability (site-wide, measured)
At 100% browser zoom, on 1366x768 AND 1920x1080, every visible text element must meet these MINIMUM computed font sizes:
- Regular body text (paragraphs, bullets, fact sentences, descriptions, table cells, answer text, list items): >= 18px,
  line-height about 1.6. (Today many are ~13-15px: raise them by about 2 font sizes.)
- Secondary text (captions, source lines, chips/badges, legends, axis labels, dropdowns, toggles, footnotes): >= 15px.
- Tiny uppercase eyebrow labels (e.g. "LIVE FROM THE REPORTS"): >= 13px.
- Bold text grows too, but less, keeping hierarchy: card titles >= 22px, section headings larger than card titles,
  KPI/metric values >= 30px, score values in tables >= 18px.
- Exception: the Home hero (item 11 of task 06) must STILL fit on one screen at 1366x768 and 1920x1080; keep its current
  scaling (do not enlarge the hero headline); its paragraph/note may grow only while it still fits.
Scope: Home (esp. "Tata Steel at a glance": About facts + page chips, subtitle, year dropdown, "How its financials look"
bullets, the Edith line, "Try asking"), Ask Edith (sidebar, welcome, chat header, messages, tables, badges, citations,
steps, input), Dashboard (control bar labels/toggles/dropdowns/caption, KPI cards, region view, chart, ratios, composite
scores table incl. descriptions and chips, health summary incl. button, segments table incl. headers/toggle/footnote,
statement coverage), Evaluation, Sources ("How it works" cards, composite-scores and segments boxes — split long paragraphs
into short points without changing wording — report cards, limitations), footer. Give tables more room (full width, wrap
descriptions) so bigger text is not squeezed. Layout, content and colours stay the same.
VERIFY with a headless-Chrome script: collect computed font-size of every visible text node on every page at both
viewports (including the Ask page with one answer rendered, and the Dashboard with a region selected) and list any node
below its minimum; fix until none remain. Report the counts.

## 2. Ask Edith: app-style full-height layout
- The sidebar starts DIRECTLY under the dark header and fills the whole left side down to the bottom of the viewport
  (like ChatGPT/Claude), with no white space above it. Right column: the "Ask Edith" eyebrow, title and subtitle (kept,
  smaller margins), then the chat panel filling the remaining height. The page title no longer pushes the sidebar down.
- Sidebar content and order unchanged; everything in it readable (sizes above); if it overflows the viewport the sidebar
  itself scrolls, with "Hide sidebar" never overlapped.
- Keep the footer below the app area (reachable by scrolling), or hide it on this page only if the full-height layout
  requires it — your choice, state which.

## 4. Ask Edith chat area
- "Hello, I'm Edith." much larger; welcome paragraph and info bullets at body size; the welcome block fills the panel
  (e.g. centred with a max-width) instead of sitting small in a corner. Chat header, avatar, input, placeholder, footnote
  and Send button bigger. Welcome bullet "Answers usually take 10-60 seconds." → "Answers usually take 10-60 seconds;
  the first question may take 2-3 minutes."

## 5. No bare "n/a"
Replace every visible bare "n/a" with a short grey reason (4-5 words) in place of the value (tooltip may add detail):
- UK or Netherlands before FY2024-25 → "Reported within Europe then"
- Europe from FY2024-25 → "Split into Netherlands and UK"
- Tata Steel Long Products after FY2021-22 → "Merged into Tata Steel India"
- Any other segment/region absent in a year → "Not a segment that year"
- FY2021-22 year-on-year change (and ROE/averages needing FY2020-21) → "No FY2020-21 data"
- Piotroski F / Beneish M for FY2021-22 → "Needs FY2020-21 data"
- A figure the reports do not give → "Not in the reports"
- Evaluation page: questions with nothing to check → "Nothing to check"
Region view: when the selected region did not exist in the selected year, show a clear note at the top of the card, e.g.
"The UK was reported within Tata Steel Europe until FY2023-24", with a button "View Europe for FY2022-23" that switches
the Region dropdown (and the reverse for Europe in FY2024-25+: buttons for Netherlands / UK). No empty stat boxes.
Grep the rendered text of every page: no standalone "n/a" may remain.

## Done means
`npm run build` and `npm run lint` pass; the font-size audit reports zero nodes below minimum on every page at both
viewports; hero still fits one screen at both; Ask sidebar full height with no space above; no bare "n/a". At most 1 real
/api/ask call. Report per item 1-8: done / partially / not done, with notes and the audit counts.

## Boundaries
Edit only `frontend/`. No backend changes, no git, no Docker, never read `.env`.
