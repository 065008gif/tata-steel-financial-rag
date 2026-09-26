"""FastAPI backend implementing the API contract in the frontend brief (Section 5).

Endpoints: /api/health, /api/ask, /api/financials, /api/items, /api/metrics, /api/scores, /api/evaluation, /api/reports.
Run from the repo root:  uvicorn main:app --app-dir src/api --host 0.0.0.0 --port 8000
"""
import json, re, sys, time, uuid
from pathlib import Path
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src" / "agent")); sys.path.insert(0, str(ROOT / "src" / "retrieval"))
import agent as A
from tools import FIN, YEARS, compute_metric, get_financials
from search import client as qdrant, COLL
sys.path.insert(0, str(ROOT / "src" / "analysis"))
from scores import SCORE_YEARS, all_scores

app = FastAPI(title="Tata Steel Financial Analysis RAG", version="1.0.0")
app.add_middleware(CORSMiddleware, allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
                   allow_methods=["*"], allow_headers=["*"])

REPORTS = [
    {"fiscal_year": "FY2022-23", "title": "116th Integrated Report & Annual Accounts 2022-23", "pdf_url": "https://www.tatasteel.com/media/18370/tata-steel-ir-2022-23.pdf"},
    {"fiscal_year": "FY2023-24", "title": "117th Integrated Report & Annual Accounts 2023-24", "pdf_url": "https://www.tatasteel.com/media/21244/integrated-report-and-annual-accounts-fy2023-24.pdf"},
    {"fiscal_year": "FY2024-25", "title": "118th Integrated Report & Annual Accounts 2024-25", "pdf_url": "https://www.tatasteel.com/media/23973/fy25-integratedreport.pdf"},
    {"fiscal_year": "FY2025-26", "title": "119th Integrated Report & Annual Accounts 2025-26", "pdf_url": "https://www.tatasteel.com/media/25904/tatasteel-iar-2025-26.pdf"}]
PAGE_MAPS = {r["fiscal_year"]: json.loads((ROOT / "data/interim" / f"page_map_{r['fiscal_year']}.json").read_text()) for r in REPORTS}
for r in REPORTS: r["pages"] = len(PAGE_MAPS[r["fiscal_year"]])
LABEL_TO_PDF = {fy: {p["label"]: p["page"] for p in pm if p["label"]} for fy, pm in PAGE_MAPS.items()}
URL = {r["fiscal_year"]: r["pdf_url"] for r in REPORTS}
SRC_RE = re.compile(r"(FY\d{4}-\d{2}) Annual Report, ([^,]+?), pages? (F\d{1,3}|PDF p\d+)")
METRICS = [  # key, name, formula, unit, decimals, higher_is_better
    ("current_ratio", "Current ratio", "total_current_assets / total_current_liabilities", "x", 2, True),
    ("debt_to_equity", "Debt-to-equity", "(non_current_borrowings + current_borrowings) / total_equity", "x", 2, False),
    ("interest_coverage", "Interest coverage", "(profit_before_tax + finance_costs) / finance_costs", "x", 2, True),
    ("net_profit_margin", "Net profit margin", "profit_for_the_year / revenue_from_operations * 100", "%", 2, True),
    ("ebitda_margin", "EBITDA margin",
     "(profit_before_exceptional_and_tax + finance_costs + depreciation_amortisation - other_income) / revenue_from_operations * 100", "%", 2, True),
    ("roe", "Return on equity (avg equity)", "profit_for_the_year / avg(total_equity) * 100", "%", 2, True)]

class AskRequest(BaseModel):
    question: str = Field(..., min_length=3, max_length=2000)

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
    return json.dumps(a)[:150]

def build_citations(answer, trace):
    found = {}
    for t in trace:
        for rep, sec, pg in SRC_RE.findall(t.get("result", "")):
            label, pdf = (None, int(pg[5:])) if pg.startswith("PDF p") else (pg, LABEL_TO_PDF.get(rep, {}).get(pg))
            key = (rep, label or f"p{pdf}")
            if key not in found:
                found[key] = {"report": rep, "section": sec.strip(), "page_label": label, "pdf_page": pdf,
                              "pdf_url": f"{URL[rep]}#page={pdf}" if pdf and rep in URL else URL.get(rep)}
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
        _, info = A.ask(req.question, verbose=False)
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

@app.get("/api/evaluation")
def evaluation():
    runs = sorted((ROOT / "eval/results").glob("run_*.json"))
    if not runs: return {"available": False}
    data, st = json.loads(runs[-1].read_text()), runs[-1].stem[4:]
    keep = ("id", "category", "question", "numeric", "citation", "mentions", "abstention_ok", "grounded", "seconds")
    return {"available": True, "run_at": f"{st[:4]}-{st[4:6]}-{st[6:8]}T{st[9:11]}:{st[11:13]}:00",
            "summary": data["summary"], "records": [{k: r.get(k) for k in keep} for r in data["records"]]}

@app.get("/api/reports")
def reports():
    return REPORTS
