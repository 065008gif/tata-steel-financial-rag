"""FastAPI backend implementing the API contract in the frontend brief (Section 5).

Endpoints: /api/health, /api/ask, /api/financials, /api/items, /api/metrics, /api/scores, /api/segments, /api/regions,
/api/statements, /api/statement-pdf, /api/pdf/{report}, /api/company, /api/evaluation, /api/reports.
Run from the repo root:  uvicorn main:app --app-dir src/api --host 0.0.0.0 --port 8000
"""
import json, re, sys, time, uuid
from pathlib import Path
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, Response
from typing import List, Literal
from pydantic import BaseModel, Field

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src" / "agent")); sys.path.insert(0, str(ROOT / "src" / "retrieval"))
import agent as A
from tools import FIN, ITEMS as LINE_ITEMS, YEARS, compute_metric, get_financials
from search import client as qdrant, COLL
sys.path.insert(0, str(ROOT / "src" / "analysis"))
from scores import SCORE_YEARS, all_scores

app = FastAPI(title="Tata Steel Financial Analysis RAG", version="1.0.0")
app.add_middleware(CORSMiddleware, allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
                   allow_methods=["*"], allow_headers=["*"])

REPORTS = [
    {"fiscal_year": "FY2022-23", "title": "116th Integrated Report & Annual Accounts 2022-23", "official_url": "https://www.tatasteel.com/media/18370/tata-steel-ir-2022-23.pdf"},
    {"fiscal_year": "FY2023-24", "title": "117th Integrated Report & Annual Accounts 2023-24", "official_url": "https://www.tatasteel.com/media/21244/integrated-report-and-annual-accounts-fy2023-24.pdf"},
    {"fiscal_year": "FY2024-25", "title": "118th Integrated Report & Annual Accounts 2024-25", "official_url": "https://www.tatasteel.com/media/23973/fy25-integratedreport.pdf"},
    {"fiscal_year": "FY2025-26", "title": "119th Integrated Report & Annual Accounts 2025-26", "official_url": "https://www.tatasteel.com/media/25904/tatasteel-iar-2025-26.pdf"}]
for r in REPORTS: r["pdf_url"] = f"/api/pdf/{r['fiscal_year']}"     # served locally: tatasteel.com blocks deep links (HTTP 403)
PDF_PATH = {r["fiscal_year"]: ROOT / "data/raw" / f"TataSteel_{r['fiscal_year']}.pdf" for r in REPORTS}
PAGE_MAPS = {r["fiscal_year"]: json.loads((ROOT / "data/interim" / f"page_map_{r['fiscal_year']}.json").read_text()) for r in REPORTS}
for r in REPORTS: r["pages"] = len(PAGE_MAPS[r["fiscal_year"]])
LABEL_TO_PDF = {fy: {p["label"]: p["page"] for p in pm if p["label"]} for fy, pm in PAGE_MAPS.items()}

def pdf_url(report, pdf_page=None):
    """Relative link to the locally served report, opening at pdf_page (1-based) if given."""
    return f"/api/pdf/{report}" + (f"#page={pdf_page}" if pdf_page else "")
SRC_RE = re.compile(r"(FY\d{4}-\d{2}) Annual Report, ([^,]+?), pages? (F\d{1,3}|PDF p\d+)")
METRICS = [  # key, name, formula, unit, decimals, higher_is_better
    ("current_ratio", "Current ratio", "total_current_assets / total_current_liabilities", "x", 2, True),
    ("debt_to_equity", "Debt-to-equity", "(non_current_borrowings + current_borrowings) / total_equity", "x", 2, False),
    ("interest_coverage", "Interest coverage", "(profit_before_tax + finance_costs) / finance_costs", "x", 2, True),
    ("net_profit_margin", "Net profit margin", "profit_for_the_year / revenue_from_operations * 100", "%", 2, True),
    ("ebitda_margin", "EBITDA margin",
     "(profit_before_exceptional_and_tax + finance_costs + depreciation_amortisation - other_income) / revenue_from_operations * 100", "%", 2, True),
    ("roe", "Return on equity (avg equity)", "profit_for_the_year / avg(total_equity) * 100", "%", 2, True),
    ("net_debt", "Net debt (borrowings + leases - cash, bank balances and current investments)",
     "non_current_borrowings + current_borrowings + non_current_lease_liabilities + current_lease_liabilities"
     " - cash_and_cash_equivalents - other_bank_balances - current_investments", "INR crore", 2, False)]

class HistoryMessage(BaseModel):
    role: Literal["user", "assistant"]
    content: str = Field(..., max_length=20000)

class AskRequest(BaseModel):
    question: str = Field(..., min_length=3, max_length=2000)
    history: List[HistoryMessage] = Field(default_factory=list, max_length=20)

@app.exception_handler(Exception)
async def unhandled(request, exc):
    return JSONResponse(status_code=500, content={"error": f"Internal error: {exc}"})

def describe(t):
    a, n = t["args"], t["tool"]
    if n == "get_financials":
        items = a.get("items"); items = ", ".join(items) if isinstance(items, list) else items
        return f"Fetched {items} ({a.get('scope') or 'consolidated'})"
    if n == "compute_metric": return f"Computed {a.get('formula')}"
    if n == "breakdown": return f"Broke down {a.get('total')} from {a.get('from_year')} to {a.get('to_year')}"
    if n == "search_documents": return f'Searched the reports for "{a.get("query")}"' + (f" in {a['report']}" if a.get("report") else "")
    if n == "get_line_items": return f'Looked up "{a.get("query")}"'
    if n == "calculate": return f"Calculated {a.get('expression')}"
    if n == "dupont": return f"DuPont analysis of ROE ({a.get('scope') or 'consolidated'}, {a.get('basis') or 'average'} basis)"
    return json.dumps(a)[:150]

def build_citations(answer, trace):
    found = {}
    for t in trace:
        for rep, sec, pg in SRC_RE.findall(t.get("result", "")):
            label, pdf = (None, int(pg[5:])) if pg.startswith("PDF p") else (pg, LABEL_TO_PDF.get(rep, {}).get(pg))
            key = (rep, label or f"p{pdf}")
            if key not in found:
                found[key] = {"report": rep, "section": sec.strip(), "page_label": label, "pdf_page": pdf,
                              "pdf_url": pdf_url(rep, pdf) if rep in PDF_PATH else None}
    cited = [c for c in found.values() if c["page_label"] and re.search(rf"\b{c['page_label']}\b", answer)]
    return cited or list(found.values())[:8]

@app.get("/api/health")
def health():
    try: pts = qdrant.count(COLL).count
    except Exception: pts = None
    return {"status": "ok" if pts else "degraded", "llm_model": A.MODELS[0], "index_points": pts,
            "reports": [r["fiscal_year"] for r in REPORTS], "version": "1.0.0"}

@app.post("/api/ask")
def ask(req: AskRequest):
    t0 = time.time()
    try:
        _, info = A.ask(req.question, verbose=False, history=[m.model_dump() for m in req.history])
    except Exception as e:
        return JSONResponse(status_code=503, content={"error": f"The AI model is temporarily unavailable: {str(e)[:200]}"})
    body = info.get("answer_body") or "I could not complete this analysis within the step limit."
    total, unverified, warnings = info.get("total", 0), info.get("unverified", []), info.get("warnings", [])
    status = "not_applicable" if total == 0 else ("verified" if not unverified and not warnings else "partially_verified")
    return {"id": str(uuid.uuid4()), "question": req.question, "answer_markdown": body,
            "verification": {"status": status, "figures_grounded": info.get("grounded", 0), "figures_total": total,
                             "unverified_figures": unverified, "warnings": warnings},
            "citations": build_citations(body, info.get("trace", [])),
            "steps": [{"tool": t["tool"], "description": describe(t)} for t in info.get("trace", [])],
            "model": A.MODELS[0], "elapsed_seconds": round(time.time() - t0, 1)}

@app.get("/api/financials")
def financials(items: str, scope: str = "consolidated"):
    sc = "standalone" if scope == "standalone" else "consolidated"
    r = get_financials([k.strip() for k in items.split(",") if k.strip()], scope=sc)
    out = {k: {"description": v["description"],
               "values": {fy: {"value": x["value"], "source": x["source"], "restated": bool(x.get("restated"))} for fy, x in v["values"].items()},
               "yoy_changes": [{"from": c["from"], "to": c["to"], "change": c["change"], "change_pct": c["change_pct"],
                                "restated_basis": "prior_year_as_presented" in c} for c in v["yoy_changes"]]}
           for k, v in r["items"].items()}
    return {"scope": sc, "unit": "INR crore", "years": YEARS, "items": out, "unknown_items": r.get("unknown_items", [])}

@app.get("/api/items")
def items():
    return {sc: [{"key": k, "description": v["description"]} for k, v in sorted(FIN[sc].items())] for sc in ("consolidated", "standalone")}

@app.get("/api/metrics")
def metrics(scope: str = "consolidated"):
    sc = "standalone" if scope == "standalone" else "consolidated"
    out = []
    for key, name, formula, unit, dec, hib in METRICS:
        r = compute_metric(formula, scope=sc, fiscal_years=YEARS, decimals=4)
        out.append({"key": key, "name": name, "formula": formula, "unit": unit, "decimals": dec,
                    "higher_is_better": hib, "values": r.get("values", {fy: None for fy in YEARS})})
    return {"scope": sc, "years": YEARS, "metrics": out}

@app.get("/api/scores")
def scores(scope: str = "consolidated"):
    sc = "standalone" if scope == "standalone" else "consolidated"
    return all_scores(sc, SCORE_YEARS)

@app.get("/api/segments")
def segments():
    from segments import get_segments as segment_data
    r = segment_data()
    def row(s):
        return {"key": s["key"], "name": s["name"],
                "values": {fy: {i: c["value"] for i, c in v.items()} for fy, v in s["values"].items()},
                "sources": {fy: {**{k: next(iter(v.values()))[k] for k in ("report", "page_label", "pdf_page")},
                                 "url": pdf_url(next(iter(v.values()))["report"], next(iter(v.values()))["pdf_page"])}
                            for fy, v in s["values"].items()},
                "restated": {fy: [i for i, c in v.items() if c["restated"]] for fy, v in s["values"].items() if any(c["restated"] for c in v.values())}}
    return {"unit": r["unit"], "years": r["years"], "items": r["items"], "note": r["note"],
            "segments": [row(s) for s in r["segments"]], "eliminations": row(r["eliminations"]), "totals": row(r["totals"])}

@app.get("/api/regions")
def regions():
    from regions import get_regions
    return get_regions()

# ---------- local PDFs and statement-only PDFs ----------
STATEMENTS = {"profit_and_loss": "statement of profit and loss", "balance_sheet": "balance sheet",
              "cash_flow": "statement of cash flows"}
SCOPES = ("consolidated", "standalone")

def _statement_pages():
    """{(report, scope, statement): [(pdf_page, label)]} from the page map, validated: pages contiguous, every page
    printed-labelled, and exactly the pages the extracted line items (line_items.jsonl) came from."""
    from_items = {}
    for r in LINE_ITEMS:
        from_items.setdefault((r["report"], r["scope"], r["statement"]), set()).add((r["page"], r["page_label"]))
    out, problems = {}, []
    for rep, pm in PAGE_MAPS.items():
        for sc in SCOPES:
            for st in STATEMENTS:
                pages = sorted((p["page"], p["label"]) for p in pm if p["scope"] == sc and p["statement"] == st)
                nums = [p for p, _ in pages]
                if not pages or any(not lab for _, lab in pages) or nums != list(range(nums[0], nums[-1] + 1)):
                    problems.append(f"{rep} {sc} {st}: page map gives {pages}"); continue
                if set(pages) != from_items.get((rep, sc, st), set()):
                    problems.append(f"{rep} {sc} {st}: page map {pages} != line-item pages {sorted(from_items.get((rep, sc, st), []))}"); continue
                out[(rep, sc, st)] = pages
    return out, problems

STATEMENT_PAGES, STATEMENT_PAGE_PROBLEMS = _statement_pages()
_STATEMENT_PDF_CACHE = {}

def _err(code, msg):
    return JSONResponse(status_code=code, content={"error": msg})

@app.get("/api/pdf/{report}")
def report_pdf(report: str):
    path = PDF_PATH.get(report)
    if not path or not path.exists(): return _err(404, f"unknown report '{report}'; available: {', '.join(PDF_PATH)}")
    return FileResponse(path, media_type="application/pdf",
                        headers={"Content-Disposition": f'inline; filename="{path.name}"'})

def statement_url(report, scope, statement):
    return f"/api/statement-pdf?report={report}&scope={scope}&statement={statement}"

@app.get("/api/statements")
def statements(scope: str = "consolidated"):
    sc = "standalone" if scope == "standalone" else "consolidated"
    out = {}
    for fy in YEARS:
        rep = fy if fy in PDF_PATH else "FY2022-23"          # FY2021-22 only exists as the FY2022-23 comparative column
        row = {}
        for st in STATEMENTS:
            pages = STATEMENT_PAGES.get((rep, sc, st))
            if not pages: row[st] = None; continue
            row[st] = {"report": rep, "page_labels": [lab for _, lab in pages], "pdf_pages": [p for p, _ in pages],
                       "url": statement_url(rep, sc, st)}
            if rep != fy: row[st]["note"] = "comparative column of the FY2022-23 report"
        out[fy] = row
    return {"scope": sc, "years": YEARS, "statements": out}

@app.get("/api/statement-pdf")
def statement_pdf(report: str, scope: str, statement: str):
    if report not in PDF_PATH: return _err(404, f"unknown report '{report}'")
    if scope not in SCOPES: return _err(404, f"unknown scope '{scope}'; use consolidated or standalone")
    if statement not in STATEMENTS: return _err(404, f"unknown statement '{statement}'; use {', '.join(STATEMENTS)}")
    key = (report, scope, statement)
    pages = STATEMENT_PAGES.get(key)
    if not pages: return _err(404, f"no validated pages for {report} {scope} {statement}")
    if key not in _STATEMENT_PDF_CACHE:
        try: import pymupdf
        except ImportError: return _err(503, "PDF extraction is unavailable on this server (PyMuPDF is not installed)")
        src = pymupdf.open(PDF_PATH[report])
        for p, lab in pages:                                  # the printed label must be on the page itself
            if not re.search(rf"\b{lab}\b", src[p - 1].get_text()):
                return _err(500, f"page {p} of the {report} report does not show label {lab}")
        label = pages[0][1] if len(pages) == 1 else f"{pages[0][1]}-{pages[-1][1]}"
        out = pymupdf.open()
        out.insert_pdf(src, from_page=pages[0][0] - 1, to_page=pages[-1][0] - 1)
        out.set_metadata({"title": f"Tata Steel {report} {scope} {STATEMENTS[statement]} ({label})",
                          "author": "Tata Steel Limited", "subject": f"From the {report} Integrated Report & Annual Accounts, pages {label}"})
        _STATEMENT_PDF_CACHE[key] = (out.tobytes(garbage=3, deflate=True), label)
    data, label = _STATEMENT_PDF_CACHE[key]
    return Response(content=data, media_type="application/pdf",
                    headers={"Content-Disposition": f'inline; filename="TataSteel_{report}_{scope}_{statement}_{label}.pdf"'})

@app.get("/api/company")
def company():
    path = ROOT / "data/processed/company.json"
    if not path.exists(): return _err(404, "company facts not built; run src/ingest/company_facts.py")
    return json.loads(path.read_text())

@app.get("/api/evaluation")
def evaluation():
    runs = sorted((ROOT / "eval/results").glob("run_*.json"))
    full = [r for r in runs if len(json.loads(r.read_text()).get("records", [])) >= 25]   # ignore partial test runs
    runs = full or runs
    if not runs: return {"available": False}
    data, st = json.loads(runs[-1].read_text()), runs[-1].stem[4:]
    keep = ("id", "category", "question", "numeric", "citation", "mentions", "abstention_ok", "grounded", "seconds")
    return {"available": True, "run_at": f"{st[:4]}-{st[4:6]}-{st[6:8]}T{st[9:11]}:{st[11:13]}:00",
            "summary": data["summary"], "records": [{k: r.get(k) for k in keep} for r in data["records"]]}

@app.get("/api/reports")
def reports():
    return REPORTS
