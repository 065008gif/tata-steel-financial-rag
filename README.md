# Financial Analysis RAG — Tata Steel (FY2022-23 to FY2025-26)

A retrieval-augmented financial analysis assistant built on Tata Steel Limited's official Integrated Reports & Annual
Accounts for FY2022-23, FY2023-24, FY2024-25 and FY2025-26 (comparative columns also give FY2021-22). It answers
single-year lookups, multi-year trends, ratio computations, year-over-year comparisons, DuPont analysis, segment
results, risk and narrative questions, and an overall financial-health verdict — citing the report, statement and page
for every figure, verifying every number against the source data, and refusing questions the reports cannot answer.

**Team:** Backend — Akshit Kansal · Frontend — teammate (see `frontend/`)

## Results (final evaluation, 32 questions — details in `eval/EVALUATION_NOTES.md`)

| Tier | Result |
|---|---|
| Filtered retrieval (search only) | Hit Rate@4 = 1.00, MRR = 1.00 |
| Numeric accuracy | 24/24 numeric questions fully correct; 60/60 expected numbers found |
| Source pages retrieved / cited | 26/26 questions / 55 of 56 expected pages cited |
| Abstention (forecasts, other companies, years not covered) | 32/32 |
| Automatic numeric grounding (calculator inputs not trusted) | 31/32 answers fully grounded |
| Ground-truth check | all 118 answer-key input figures found printed on their cited PDF pages |
| Average latency / tool calls | 10 s / 2.6 |

## Architecture

| Stage | Script | What it does |
|---|---|---|
| 0. Download | `scripts/download_reports.sh` | Fetches the four official PDFs from tatasteel.com into `data/raw/` |
| 1. Page map | `src/ingest/page_map.py` | Tags every page with section, scope (standalone/consolidated), statement type and printed label (e.g. F143), reading text by visual position |
| 2. Notes tables | `src/ingest/run_docling.py` | Docling (TableFormer, OCR off) over all financial-statement pages, ~2.8 s/page |
| 3. Statements | `src/ingest/line_items.py`, `statement_lines.py` | Coordinate-based extraction of balance sheet, P&L and cash flow (Docling merged rows on dense single-page statements). Checks: total assets = equity + liabilities (17/17), section subtotals (68/68). Handles 3-column restated statements, unlabelled subtotals and restatements across reports |
| 4. Canonical items | `src/analysis/canonical.py` | ~40 standard items (one exact row per item/scope/year), per-report values for same-basis year-over-year changes |
| 5. Chunks | `src/ingest/build_chunks.py` | statement tables, note tables (with note titles), notes text, narrative pages with topic tags (risk, MD&A, strategy...) |
| 6. Index | `src/index/build_index.py` | Qdrant: dense `BAAI/bge-base-en-v1.5` + sparse BM25, fused with RRF, filters on report/year/scope/section/type/topic |
| 7. Agent | `src/agent/agent.py`, `tools.py` | Ollama Cloud `gpt-oss:120b` (fallback `gemma4:31b`) with tools `get_financials`, `compute_metric`, `breakdown`, `compute_scores`, `get_line_items`, `search_documents`, `list_risk_disclosures`, `calculate`; numeric grounding, claims check, self-review |
| 8. API | `src/api/main.py` | FastAPI, endpoints below |
| 9. Evaluation | `eval/build_questions.py`, `eval/run_eval.py` | 27-question set with PDF-verified answer key; tiered scoring |

## Repository layout
scripts/ download script, benchmarks, model bake-off
src/ingest/ page map, Docling runner, statement extraction, chunk builder
src/analysis/ canonical financial items
src/index/ Qdrant index builder
src/retrieval/ hybrid search
src/agent/ agent loop + tools
src/api/ FastAPI app
eval/ questions, runner, results, evaluation notes
frontend/ React + Vite frontend (teammate)
Dockerfile, docker-compose.yml, requirements-api.txt
`data/`, `qdrant_storage/`, `.cache/` and `.env` are generated or private and not committed.

## Running

**Prerequisites:** Docker with Compose, and an Ollama Cloud API key in `.env`:
OLLAMA_API_KEY=your_ollama_cloud_key_here

**Backend (Qdrant + API):**
docker compose up -d --build qdrant backend
curl http://localhost:8000/api/health
**Full stack with the frontend and a public Cloudflare quick tunnel** (after the frontend is merged):
docker compose --profile full up -d --build
docker compose logs tunnel | grep trycloudflare.com # the public URL
**Stop (and remove containers, which hold the API key):** `docker compose down`

**Local development without Docker:** Python 3.11 environment, `pip install -r requirements-api.txt`, a running Qdrant on
`localhost:6333`, then `uvicorn main:app --app-dir src/api --port 8000`.

### Rebuilding the data from scratch
**Offline model loading:** the backend runs with `HF_HUB_OFFLINE=1`, so it never depends on the network at start-up. fastembed
0.8.1's bm25 model lists `tamil.txt` and `mock.file` as required, but the published `Qdrant/bm25` repository does not contain
them, so an offline load fails. After the first (online) model download, create them as empty files in the bm25 snapshot
folder (`.cache/fastembed/models--Qdrant--bm25/snapshots/<id>/`); the index uses English stopwords only, so they are never read.

The ingestion stages need the full environment (Docling, PyMuPDF, PyTorch CPU) in addition to `requirements-api.txt`:
bash scripts/download_reports.sh
python src/ingest/page_map.py
python src/ingest/run_docling.py # ~35 min for all four reports
python src/ingest/line_items.py # prints balance and subtotal checks
python src/analysis/canonical.py # prints item coverage
python src/ingest/build_chunks.py
python src/index/build_index.py # ~10 min on CPU (Qdrant must be running)
python eval/build_questions.py # answer key + PDF cross-check
python eval/run_eval.py # full evaluation

## API reference

Base path `/api`. JSON in and out. Money in **INR crore**. Fiscal years are `"FY2021-22"` … `"FY2025-26"`
(FY2025-26 = year ended 31 March 2026). Scope is `"consolidated"` (default) or `"standalone"`. Any number may be `null`.
All examples below are **real responses captured from the running API**.

### `GET /api/health`
```json
{
  "status": "ok",
  "llm_model": "gpt-oss:120b",
  "index_points": 4393,
  "reports": [
    "FY2022-23",
    "FY2023-24",
    "FY2024-25",
    "FY2025-26"
  ],
  "version": "1.0.0"
}
```
`status` is `"ok"` when the search index is reachable, otherwise `"degraded"`.

### `POST /api/ask`
Request: `{"question": string}` (3–2000 characters). Response time 5–240 s; clients should allow 300 s.

| Field | Type | Meaning |
|---|---|---|
| `id` | string (UUID) | Answer id |
| `question` | string | Echo of the question |
| `answer_markdown` | string | GitHub-flavoured Markdown (tables, lists). Render as-is; never alter numbers |
| `verification.status` | `"verified"` \| `"partially_verified"` \| `"not_applicable"` | `not_applicable` when the answer has no figures (e.g. a refusal) |
| `verification.figures_grounded` / `figures_total` | int | Numbers in the answer matched to source data |
| `verification.unverified_figures` | number[] | Figures that could not be matched |
| `verification.warnings` | string[] | e.g. unsupported claims |
| `citations[]` | object[] | `report`, `section`, `page_label` (e.g. `"F143"`, or `null` for narrative pages), `pdf_page`, `pdf_url` (opens at that page) |
| `steps[]` | object[] | `tool`, `description` — how the answer was produced |
| `model` | string | LLM used |
| `elapsed_seconds` | number | Server time taken |

Example request:
curl -X POST http://localhost:8000/api/ask -H "Content-Type: application/json"
-d '{"question": "What were Tata Steel'"'"'s consolidated current borrowings as at 31 March 2026?"}'
Actual response:
```json
{
  "id": "0bca22dc-3bf6-463b-8661-ac301bdb6a8a",
  "question": "What were Tata Steel's consolidated current borrowings as at 31 March 2026?",
  "answer_markdown": "**Consolidated current borrowings (as at 31 March 2026)**  \n\n- **₹ 21,202.72 crore**  \n\nSource: Tata Steel Limited, FY 2025‑26 Annual Report, Consolidated Balance Sheet, page F143.",
  "verification": {
    "status": "verified",
    "figures_grounded": 1,
    "figures_total": 1,
    "unverified_figures": [],
    "warnings": []
  },
  "citations": [
    {
      "report": "FY2025-26",
      "section": "consolidated balance sheet",
      "page_label": "F143",
      "pdf_page": 421,
      "pdf_url": "https://www.tatasteel.com/media/25904/tatasteel-iar-2025-26.pdf#page=421"
    }
  ],
  "steps": [
    {
      "tool": "get_financials",
      "description": "Fetched current_borrowings (consolidated)"
    }
  ],
  "model": "gpt-oss:120b",
  "elapsed_seconds": 7.3
}
```

### `GET /api/financials?items=<comma-separated keys>&scope=<scope>`
Exact values for canonical items, each with its source page, plus year-over-year changes computed in code on a
same-report basis (`restated_basis: true` when a figure was restated or reclassified between reports).
```json
{
  "scope": "consolidated",
  "unit": "INR crore",
  "years": [
    "FY2021-22",
    "FY2022-23",
    "FY2023-24",
    "FY2024-25",
    "FY2025-26"
  ],
  "items": {
    "current_borrowings": {
      "description": "Current borrowings",
      "values": {
        "FY2021-22": {
          "value": 24064.61,
          "source": "FY2022-23 Annual Report, consolidated balance sheet, page F141",
          "restated": false
        },
        "FY2022-23": {
          "value": 26571.37,
          "source": "FY2023-24 Annual Report, consolidated balance sheet, page F145",
          "restated": false
        },
        "FY2023-24": {
          "value": 29997.19,
          "source": "FY2024-25 Annual Report, consolidated balance sheet, page F151",
          "restated": false
        },
        "FY2024-25": {
          "value": 20412.0,
          "source": "FY2025-26 Annual Report, consolidated balance sheet, page F143",
          "restated": false
        },
        "FY2025-26": {
          "value": 21202.72,
          "source": "FY2025-26 Annual Report, consolidated balance sheet, page F143",
          "restated": false
        }
      },
      "yoy_changes": [
        {
          "from": "FY2021-22",
          "to": "FY2022-23",
          "change": 2506.76,
          "change_pct": 10.42,
          "restated_basis": false
        },
        {
          "from": "FY2022-23",
          "to": "FY2023-24",
          "change": 3425.82,
          "change_pct": 12.89,
          "restated_basis": false
        },
        {
          "from": "FY2023-24",
          "to": "FY2024-25",
          "change": -9585.19,
          "change_pct": -31.95,
          "restated_basis": false
        },
        {
          "from": "FY2024-25",
          "to": "FY2025-26",
          "change": 790.72,
          "change_pct": 3.87,
          "restated_basis": false
        }
      ]
    }
  },
  "unknown_items": []
}
```

### `GET /api/items`
The available canonical item keys and descriptions (excerpt):
```json
{
  "consolidated": [
    {
      "key": "capital_work_in_progress",
      "description": "Capital work-in-progress"
    },
    {
      "key": "cash_and_cash_equivalents",
      "description": "Cash and cash equivalents"
    }
  ],
  "standalone": [
    {
      "key": "capital_work_in_progress",
      "description": "Capital work-in-progress"
    },
    {
      "key": "cash_and_cash_equivalents",
      "description": "Cash and cash equivalents"
    }
  ]
}
```

### `GET /api/metrics?scope=<scope>`
Six key metrics for every year: `current_ratio`, `debt_to_equity`, `interest_coverage` (unit `"x"`),
`net_profit_margin`, `ebitda_margin`, `roe` (unit `"%"`), computed from the verified statements (excerpt):
```json
{
  "scope": "consolidated",
  "years": [
    "FY2021-22",
    "FY2022-23",
    "FY2023-24",
    "FY2024-25",
    "FY2025-26"
  ],
  "metrics": [
    {
      "key": "current_ratio",
      "name": "Current ratio",
      "formula": "total_current_assets / total_current_liabilities",
      "unit": "x",
      "decimals": 2,
      "higher_is_better": true,
      "values": {
        "FY2021-22": 1.0206,
        "FY2022-23": 0.8901,
        "FY2023-24": 0.7165,
        "FY2024-25": 0.7944,
        "FY2025-26": 0.7456
      }
    }
  ]
}
```

### `GET /api/scores?scope=<scope>`
Altman Z'' (book equity, actual retained earnings), Piotroski F and Beneish M for FY2022-23 to FY2025-26. Shape and fields: `docs/API_CONTRACT.md`; formulas and proxies: `docs/SCORES.md`.

### `GET /api/evaluation`
The latest evaluation run (excerpt; `{"available": false}` if none exists):
```json
{
  "available": true,
  "run_at": "2026-09-26T18:17:00",
  "summary": {
    "tier1_filtered_retrieval": {
      "hit_rate@4": 1.0,
      "mrr": 1.0
    },
    "numeric_questions_fully_correct": "20/20",
    "expected_numbers_found": "54/54",
    "source_pages_retrieved": "21/21 questions",
    "expected_pages_cited": "43/45",
    "abstention_correct": "27/27",
    "answers_fully_grounded": "25/27",
    "avg_seconds": 14,
    "avg_tool_calls": 4.0
  },
  "records": [
    {
      "id": "A1",
      "category": "lookup",
      "question": "What was Tata Steel's consolidated revenue from operations in FY2025-26?",
      "numeric": "1/1",
      "citation": "1/1",
      "mentions": null,
      "abstention_ok": true,
      "grounded": "1/1",
      "seconds": 11
    }
  ]
}
```

### `GET /api/reports`
The four source PDFs (excerpt):
```json
[
  {
    "fiscal_year": "FY2022-23",
    "title": "116th Integrated Report & Annual Accounts 2022-23",
    "pdf_url": "https://www.tatasteel.com/media/18370/tata-steel-ir-2022-23.pdf",
    "pages": 597
  }
]
```

### Errors
- Validation (HTTP 422, FastAPI format): `{"detail": [{"loc": ["body","question"], "msg": "String should have at least 3 characters", ...}]}`
- Model unavailable (HTTP 503) or internal error (HTTP 500): `{"error": "message"}`

### Notes for the frontend
- Call relative paths (`/api/...`). In development the Vite dev server proxies `/api` to `http://localhost:8000`;
  in production nginx proxies `/api/` to `http://backend:8000` (the Compose service name) with a 300 s timeout.
- CORS allows `http://localhost:5173`.

## Key design decisions
- **The LLM never does arithmetic or table layout.** Figures come from verified statement data; ratios, changes and
  component breakdowns are computed in code (`compute_metric`, `breakdown`, `get_financials`), and the model writes the interpretation.
- **Every number is checked.** Before an answer is returned, every figure in it must match a value the tools returned
  (exact or rounded, sign-aware); unsupported figures or claims are sent back to the model to fix.
- **Restatements are tracked.** Values come from the latest report containing each year; the originally reported value is kept and flagged.
- **Changes compare like with like.** Year-over-year changes use both years as presented in the later report, so
  reclassifications are not mistaken for business changes (e.g. FY24 trade payables).
- **Hybrid retrieval with metadata filters**, and deliberate abstention outside the reports' scope.

Limitations and every error the evaluation uncovered, with its root cause and fix, are documented in
`eval/EVALUATION_NOTES.md`.

## Development process
Two AI tools were used with a deliberate split. A conversational assistant (Claude, chat) guided environment setup,
design decisions, the step-by-step build of the ingestion pipeline, index, agent and API, all failure diagnosis, and the
independent verification of every result. The agentic coding tool **Claude Code** built a complete, well-specified component
on its own: the composite scores module (Altman Z'', Piotroski F, Beneish M), with its agent tool, API endpoint, 32 tests and
documentation. It worked from a written brief with strict boundaries, and its output was then verified independently
(re-run tests, hand-recomputed scores, signal-by-signal checks, live API check). Details: `docs/claude_code/README.md`.

Composite scores: `docs/SCORES.md` · API addendum (`GET /api/scores`): `docs/API_CONTRACT.md`
