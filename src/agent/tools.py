"""Agent tools: verified line-item lookup, hybrid document search, exact calculator."""
import ast, json, operator, sys
from pathlib import Path
from rapidfuzz import fuzz, process
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "retrieval"))
from search import search

ROOT = Path(__file__).resolve().parents[2]
ITEMS = [json.loads(l) for l in open(ROOT / "data/processed/line_items.jsonl")]

def _list(x):
    return None if x in (None, "", []) else (x if isinstance(x, list) else [x])

def get_line_items(query, scope="consolidated", statement=None, fiscal_years=None, limit=5):
    """Exact figures from the verified primary statements (preferred = latest report containing each year)."""
    fys = _list(fiscal_years)
    pool = [r for r in ITEMS if r["preferred"] and r["scope"] == scope
            and (not statement or r["statement"] == statement) and (not fys or r["fiscal_year"] in fys)]
    names = {}
    for r in pool:
        key = f'{r["statement"]}: {r["path"] + " > " if r["path"] else ""}{r["line_item"]}'
        names.setdefault(key, []).append(r)
    out = []
    for name, score, _ in process.extract(query, list(names), scorer=fuzz.WRatio, limit=int(limit)):
        vals = []
        for r in sorted(names[name], key=lambda r: r["fiscal_year"]):
            v = {"fiscal_year": r["fiscal_year"], "value_inr_crore": r["value"],
                 "source": f'{r["report"]} Annual Report, {r["scope"]} {r["statement"].replace("_", " ")}, page {r["page_label"]}'}
            if r["differs_from_original"]:
                v.update(restated=True, originally_reported=r["original_value"])
            vals.append(v)
        out.append({"line_item": name, "match_score": round(score), "values": vals})
    return out

def search_documents(query, report=None, scope=None, types=None, topic=None, k=6):
    """Hybrid search over notes, auditor report, narrative (MD&A, risk, strategy) and statement tables."""
    pts = search(query, k=int(k), report=report, scope=scope, types=_list(types), topic=topic)
    return [{"source": f'{p.payload["report"]} Annual Report, {p.payload["scope"] or ""} {p.payload["section"]}, '
                       f'page {p.payload.get("page_label") or "PDF p" + str(p.payload["page"])}',
             "title": p.payload["note"], "text": p.payload["text"][:2500]} for p in pts]

OPS = {ast.Add: operator.add, ast.Sub: operator.sub, ast.Mult: operator.mul, ast.Div: operator.truediv,
       ast.Pow: operator.pow, ast.USub: operator.neg, ast.UAdd: operator.pos}
def calculate(expression):
    """Safe exact arithmetic: numbers, + - * / ** and parentheses only."""
    def ev(n):
        if isinstance(n, ast.Constant) and isinstance(n.value, (int, float)): return n.value
        if isinstance(n, ast.BinOp): return OPS[type(n.op)](ev(n.left), ev(n.right))
        if isinstance(n, ast.UnaryOp): return OPS[type(n.op)](ev(n.operand))
        raise ValueError("only numbers and + - * / ** ( ) are allowed")
    return {"expression": expression, "result": round(ev(ast.parse(expression.replace(",", ""), mode="eval").body), 6)}

FUNCS = {"get_line_items": get_line_items, "search_documents": search_documents, "calculate": calculate}
YEARS = ["FY2021-22", "FY2022-23", "FY2023-24", "FY2024-25", "FY2025-26"]
REPORTS = ["FY2022-23", "FY2023-24", "FY2024-25", "FY2025-26"]
SCHEMAS = [
    {"type": "function", "function": {"name": "get_line_items",
     "description": "Get exact, verified figures (INR crore) for a line item from the balance sheet, profit and loss or cash flow statement, for every available year, with source page. Use for ALL primary-statement numbers.",
     "parameters": {"type": "object", "properties": {
         "query": {"type": "string", "description": "Line item name, e.g. 'Total current liabilities', 'Revenue from operations', 'Finance costs'"},
         "scope": {"type": "string", "enum": ["consolidated", "standalone"], "description": "Default consolidated"},
         "statement": {"type": "string", "enum": ["balance_sheet", "profit_and_loss", "cash_flow"]},
         "fiscal_years": {"type": "array", "items": {"type": "string", "enum": YEARS}}},
         "required": ["query"]}}},
    {"type": "function", "function": {"name": "search_documents",
     "description": "Search the annual reports' notes to accounts, auditor's report, segment information, MD&A, risk management and strategy pages. Returns passages with source pages.",
     "parameters": {"type": "object", "properties": {
         "query": {"type": "string"},
         "report": {"type": "string", "enum": REPORTS, "description": "Which annual report to search"},
         "scope": {"type": "string", "enum": ["consolidated", "standalone"]},
         "types": {"type": "array", "items": {"type": "string", "enum": ["statement_table", "note_table", "fs_text", "narrative"]}},
         "topic": {"type": "string", "enum": ["risk", "mdna", "directors_report", "governance", "sustainability", "strategy", "segments"]}},
         "required": ["query"]}}},
    {"type": "function", "function": {"name": "calculate",
     "description": "Evaluate arithmetic exactly. Use for EVERY ratio, difference, percentage, average and growth rate.",
     "parameters": {"type": "object", "properties": {
         "expression": {"type": "string", "description": "e.g. (72265.11 / 96917.64) or (301254.11 - 279394.80) / 279394.80 * 100"}},
         "required": ["expression"]}}},
]
