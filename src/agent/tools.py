"""Agent tools: verified line-item lookup, hybrid document search, exact calculator.

All arguments from the LLM are normalised (case, wording, year formats), and searches relax their
filters step by step when nothing matches, so a badly-phrased filter can never silently return nothing.
"""
import ast, json, operator, re, sys
from pathlib import Path
from rapidfuzz import fuzz, process, utils
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "retrieval"))
from search import search

ROOT = Path(__file__).resolve().parents[2]
ITEMS = [json.loads(l) for l in open(ROOT / "data/processed/line_items.jsonl")]
YEARS = ["FY2021-22", "FY2022-23", "FY2023-24", "FY2024-25", "FY2025-26"]
REPORTS = ["FY2022-23", "FY2023-24", "FY2024-25", "FY2025-26"]
TYPES = ["statement_table", "note_table", "fs_text", "narrative"]
TOPICS = ["risk", "mdna", "directors_report", "governance", "sustainability", "strategy", "segments"]
SECTIONS = ["auditor_report", "notes", "fs_other", "balance_sheet", "profit_and_loss", "cash_flow",
            "changes_in_equity", "integrated_report", "statutory_reports"]

# ---------- argument normalisation ----------
def norm_scope(x):
    x = str(x or "").lower()
    if "stand" in x: return "standalone"
    if "consol" in x or "group" in x: return "consolidated"
    return None

def norm_statement(x):
    x = str(x or "").lower()
    if "balance" in x: return "balance_sheet"
    if "cash" in x: return "cash_flow"
    if any(w in x for w in ("profit", "loss", "p&l", "income statement")): return "profit_and_loss"
    return None

def norm_fy(x):
    """'FY2025-26', 'FY2025-26 Annual Report', '2025-26', 'FY26' -> 'FY2025-26'; bare 2025 -> year ending Mar-2025."""
    s = str(x or "")
    m = re.search(r"(20\d\d)\s*[-–/]\s*(\d{2,4})", s)
    if m: a = int(m.group(1)); return f"FY{a}-{str(a + 1)[2:]}"
    m = re.search(r"FY\s*'?(\d{2})\b", s, re.I)
    if m: e = 2000 + int(m.group(1)); return f"FY{e - 1}-{str(e)[2:]}"
    m = re.search(r"(20\d\d)", s)
    if m: e = int(m.group(1)); return f"FY{e - 1}-{str(e)[2:]}"
    return None

def _list(x):
    if x in (None, "", []): return []
    return x if isinstance(x, list) else [x]

def norm_types(x):
    out = []
    for t in _list(x):
        t = str(t).lower()
        if t in TYPES: out.append(t)
        elif "narrat" in t or "commentary" in t or "md&a" in t: out.append("narrative")
        elif "note" in t: out += ["note_table", "fs_text"]
        elif "statement" in t: out.append("statement_table")
    return sorted(set(out)) or None

def norm_section(x):
    x = str(x or "").lower()
    if "audit" in x: return "auditor_report"
    if "note" in x: return "notes"
    if "statutory" in x or "directors" in x or "board" in x: return "statutory_reports"
    if "integrated" in x: return "integrated_report"
    return norm_statement(x) or (x if x in SECTIONS else None)

def norm_topic(x):
    x = str(x or "").lower().replace(" ", "_")
    if x in TOPICS: return x
    for t, keys in [("risk", ["risk"]), ("mdna", ["management", "md&a", "mdna"]), ("segments", ["segment"]),
                    ("strategy", ["strateg", "outlook"]), ("sustainability", ["sustain", "esg", "climate"]),
                    ("governance", ["governance"]), ("directors_report", ["director", "board"])]:
        if any(k in x for k in keys): return t
    return None

def _score(a, b, **kw):
    """Word-set match dominates (all query words present), WRatio breaks ties."""
    return 0.7 * fuzz.token_set_ratio(a, b) + 0.3 * fuzz.WRatio(a, b)

# ---------- tools ----------
def get_line_items(query, scope="consolidated", statement=None, fiscal_years=None, limit=5):
    """Exact figures from the verified primary statements (preferred = latest report containing each year).
    Several line items can be requested at once, separated by ';'."""
    if isinstance(query, list) or ";" in str(query):
        qs = query if isinstance(query, list) else [q.strip() for q in str(query).split(";") if q.strip()]
        return {"results": {q: get_line_items(q, scope, statement, fiscal_years, limit=3) for q in qs}}
    sc = norm_scope(scope) or "consolidated"
    st = norm_statement(statement)
    fys = [f for f in (norm_fy(y) for y in _list(fiscal_years)) if f] or None
    def pool(st_, fys_):
        return [r for r in ITEMS if r["preferred"] and r["scope"] == sc and (not st_ or r["statement"] == st_)
                and (not fys_ or r["fiscal_year"] in fys_)]
    rows, relaxed = pool(st, fys), []
    if not rows and st: rows, st, relaxed = pool(None, fys), None, relaxed + ["statement"]
    if not rows and fys: rows, fys, relaxed = pool(st, None), None, relaxed + ["fiscal_years"]
    names = {}
    for r in rows:
        names.setdefault(f'{r["statement"]}: {r["path"] + " > " if r["path"] else ""}{r["line_item"]}', []).append(r)
    out = []
    for name, score, _ in process.extract(str(query), list(names), scorer=_score, processor=utils.default_process, limit=int(limit or 5)):
        vals = []
        for r in sorted(names[name], key=lambda r: r["fiscal_year"]):
            v = {"fiscal_year": r["fiscal_year"], "value_inr_crore": r["value"],
                 "source": f'{r["report"]} Annual Report, {r["scope"]} {r["statement"].replace("_", " ")}, page {r["page_label"]}'}
            if r["differs_from_original"]: v.update(restated=True, originally_reported=r["original_value"])
            vals.append(v)
        out.append({"line_item": name, "match_score": round(score), "values": vals})
    return {"scope_used": sc, "filters_relaxed": relaxed, "available_years": YEARS, "matches": out}

def _compact(text):
    """Collapse the padding Docling puts in markdown tables, so wide tables fit in the context the model sees."""
    return re.sub(r"-{4,}", "---", re.sub(r"[ \t]{2,}", " ", text))

_NUM_CELL = re.compile(r"\(?-?[\d,]+\.\d+\)?|-")

def _fix_stacked(md, report):
    """Repair stacked-year rows in note tables: a numeric row followed by a numeric row whose label is blank or
    continues in lowercase is one item shown for two years (first = report year, second = prior year).
    The split label is merged and each row is stamped with its fiscal year."""
    try:
        y = int(report[2:6]); cur, pri = report, f"FY{y - 1}-{str(y)[2:]}"
    except Exception:
        return md
    lines = md.split("\n")
    def parts(l):
        if not l.startswith("|"): return None
        cells = [c.strip() for c in l.strip().strip("|").split("|")]
        nums = sum(1 for c in cells if _NUM_CELL.fullmatch(c))
        lab_i = next((i for i, c in enumerate(cells) if c and not _NUM_CELL.fullmatch(c)), None)
        return cells, nums, lab_i
    i = 0
    while i < len(lines) - 1:
        a, b = parts(lines[i]), parts(lines[i + 1])
        if a and b and a[1] >= 2 and b[1] >= 2 and a[2] is not None:
            lab_a = a[0][a[2]]
            lab_b = b[0][b[2]] if b[2] is not None and b[2] <= a[2] else ""
            if lab_b == "" or lab_b[:1].islower():
                full = (lab_a + " " + lab_b).strip()
                ca, cb = list(a[0]), list(b[0])
                ca[a[2]] = f"{full} [{cur}]"
                if b[2] is not None and b[2] <= a[2]: cb[b[2]] = f"{full} [{pri}]"
                else: cb[a[2]] = f"{full} [{pri}]"
                lines[i], lines[i + 1] = "| " + " | ".join(ca) + " |", "| " + " | ".join(cb) + " |"
                i += 2; continue
        i += 1
    return "\n".join(lines)

def search_documents(query, report=None, scope=None, types=None, topic=None, section=None, k=6):
    """Hybrid search; relaxes filters step by step until something is found."""
    base = dict(report=norm_fy(report) if report else None, scope=norm_scope(scope), types=norm_types(types),
                topic=norm_topic(topic), section=norm_section(section) or (norm_section(topic) if "audit" in str(topic).lower() else None))
    attempts = [base, {**base, "types": None, "topic": None}, {**base, "types": None, "topic": None, "section": None},
                {"report": base["report"]}]
    for i, f in enumerate(attempts):
        pts = search(str(query), k=int(k or 6), **f)
        if pts:
            return {"filters_used": {a: b for a, b in f.items() if b}, "filters_relaxed": i > 0, "results": [
                {"source": f'{p.payload["report"]} Annual Report, {p.payload["scope"] or ""} {p.payload["section"]}, '
                           f'page {p.payload.get("page_label") or "PDF p" + str(p.payload["page"])}',
                 "title": p.payload["note"], "text": _fix_stacked(_compact(p.payload["text"]), p.payload["report"])[:5000]} for p in pts]}
    return {"results": [], "note": "Nothing found even with only the report filter. Try different wording."}

OPS = {ast.Add: operator.add, ast.Sub: operator.sub, ast.Mult: operator.mul, ast.Div: operator.truediv,
       ast.Pow: operator.pow, ast.USub: operator.neg, ast.UAdd: operator.pos}
def calculate(expression):
    """Safe exact arithmetic: numbers, + - * / ** and parentheses only. Several expressions separated by ';'."""
    if ";" in str(expression):
        out = []
        for e in [e.strip() for e in str(expression).split(";") if e.strip()]:
            try: out.append(calculate(e))
            except Exception as ex: out.append({"expression": e, "error": str(ex)})
        return {"results": out}
    def ev(n):
        if isinstance(n, ast.Constant) and isinstance(n.value, (int, float)): return n.value
        if isinstance(n, ast.BinOp): return OPS[type(n.op)](ev(n.left), ev(n.right))
        if isinstance(n, ast.UnaryOp): return OPS[type(n.op)](ev(n.operand))
        raise ValueError("only numbers and + - * / ** ( ) are allowed")
    return {"expression": expression, "result": round(ev(ast.parse(str(expression).replace(",", ""), mode="eval").body), 6)}

FUNCS = {"get_line_items": get_line_items, "search_documents": search_documents, "calculate": calculate}
SCHEMAS = [
    {"type": "function", "function": {"name": "get_line_items",
     "description": "Get exact, verified figures (INR crore) for a line item from the balance sheet, profit and loss or cash flow statement, for every available year (FY2021-22 to FY2025-26), with source page. Use for ALL primary-statement numbers.",
     "parameters": {"type": "object", "properties": {
         "query": {"type": "string", "description": "Line item name, e.g. 'Revenue from operations'. Request several at once separated by ';', e.g. 'Inventories; Trade receivables; Cash and cash equivalents; Trade payables'"},
         "scope": {"type": "string", "enum": ["consolidated", "standalone"], "description": "Default consolidated"},
         "statement": {"type": "string", "enum": ["balance_sheet", "profit_and_loss", "cash_flow"]},
         "fiscal_years": {"type": "array", "items": {"type": "string", "enum": YEARS}}},
         "required": ["query"]}}},
    {"type": "function", "function": {"name": "search_documents",
     "description": "Search the annual reports: notes to accounts, auditor's report (section=auditor_report), segment information, MD&A, risk management and strategy pages. Returns passages with source pages. Start with few filters.",
     "parameters": {"type": "object", "properties": {
         "query": {"type": "string"},
         "report": {"type": "string", "enum": REPORTS, "description": "Which annual report to search"},
         "scope": {"type": "string", "enum": ["consolidated", "standalone"]},
         "section": {"type": "string", "enum": SECTIONS},
         "types": {"type": "array", "items": {"type": "string", "enum": TYPES}},
         "topic": {"type": "string", "enum": TOPICS}},
         "required": ["query"]}}},
    {"type": "function", "function": {"name": "calculate",
     "description": "Evaluate arithmetic exactly. Use for EVERY ratio, difference, percentage, average and growth rate.",
     "parameters": {"type": "object", "properties": {
         "expression": {"type": "string", "description": "e.g. (72265.11 / 96917.64). Do several at once separated by ';', e.g. '86606.14/97295.13; 70503.59/98403.48; 47249.22-44589.94'"}},
         "required": ["expression"]}}},
]


# ---------- canonical financials (exact rows, yoy changes computed in code) ----------
FIN_PATH = ROOT / "data/processed/financials.json"
FIN = json.loads(FIN_PATH.read_text()) if FIN_PATH.exists() else {}
CANON = sorted({k for sc in FIN.values() for k in sc})
FIN_REP_PATH = ROOT / "data/processed/financials_by_report.json"
FIN_REP = json.loads(FIN_REP_PATH.read_text()) if FIN_REP_PATH.exists() else {}

def get_financials(items, scope="consolidated", fiscal_years=None):
    """Exact canonical statement items for each year, with year-on-year change and % change computed exactly."""
    sc = norm_scope(scope) or "consolidated"
    fys = [f for f in (norm_fy(y) for y in _list(fiscal_years)) if f] or YEARS
    wanted = items if isinstance(items, list) else re.split(r"[;,]", str(items))
    out, unknown = {}, []
    for it in [str(w).strip() for w in wanted if str(w).strip()]:
        key = re.sub(r"[^a-z0-9]+", "_", it.lower()).strip("_")
        if key not in FIN.get(sc, {}):
            best = process.extractOne(it, CANON, scorer=_score, processor=utils.default_process)
            key = best[0] if best and best[1] >= 75 else None
        if not key or key not in FIN.get(sc, {}):
            unknown.append(it); continue
        entry = FIN[sc][key]
        vals = {fy: entry["values"][fy] for fy in fys if fy in entry["values"]}
        ys, changes = sorted(vals), []
        for a, b in zip(ys, ys[1:]):
            rb = FIN_REP.get(b, {}).get(sc, {}).get(key, {}).get("values", {})     # later report holds both years
            same = a in rb and b in rb
            va = rb[a]["value"] if same else vals[a]["value"]
            vb = rb[b]["value"] if same else vals[b]["value"]
            c = {"from": a, "to": b, "change": round(vb - va, 2), "change_pct": round((vb - va) / abs(va) * 100, 2) if va else None,
                 "basis": f"both years as presented in the {b} report" if same else "latest reported values"}
            if same and (abs(va - vals[a]["value"]) > 0.01 or abs(vb - vals[b]["value"]) > 0.01):
                c["prior_year_as_presented"], c["year_as_presented"] = va, vb
            changes.append(c)
        out[key] = {"description": entry["description"], "values": vals, "yoy_changes": changes}
    ys_all = [y for y in fys if any(y in v["values"] for v in out.values())]
    table = "| Item (INR crore) | " + " | ".join(ys_all) + " |\n|---|" + "---|" * len(ys_all) + "\n"
    for v in out.values():
        table += f"| {v['description']} | " + " | ".join(_inr(v["values"][y]["value"]) if y in v["values"] else "n/a" for y in ys_all) + " |\n"
    pairs = list(zip(ys_all, ys_all[1:]))
    changes = "| Change (INR crore, %) | " + " | ".join(f"{a} to {b}" for a, b in pairs) + " |\n|---|" + "---|" * len(pairs) + "\n"
    for v in out.values():
        cells = []
        for a, b in pairs:
            c = next((c for c in v["yoy_changes"] if c["from"] == a and c["to"] == b), None)
            cell = "n/a" if not c else f"{'+' if c['change'] > 0 else ''}{_inr(c['change'])} ({'+' if (c['change_pct'] or 0) > 0 else ''}{c['change_pct']}%)"
            cells.append(cell + ("*" if c and "prior_year_as_presented" in c else ""))
        changes += f"| {v['description']} | " + " | ".join(cells) + " |\n"
    changes += ("\nChanges compare both years as presented in the later year's report. * = a figure was restated or "
                "reclassified in that report, so the change differs from simply subtracting the level values above.\n")
    res = {"scope_used": sc, "unit": "INR crore", "year_convention": "FY2023-24 = year ended 31 March 2024; balance-sheet values for FY2023-24 are as at 31 March 2024.", "table": table, "changes_table": changes, "items": out}
    if unknown: res.update(unknown_items=unknown, available_items=CANON, hint="Use get_line_items for items not listed.")
    return res

FUNCS["get_financials"] = get_financials
SCHEMAS.insert(0, {"type": "function", "function": {"name": "get_financials",
    "description": "PREFERRED for statement figures. Exact, verified values of standard items for every year FY2021-22 to "
                   "FY2025-26, each with source page, plus exact year-on-year change and % change. Items: " + ", ".join(CANON),
    "parameters": {"type": "object", "properties": {
        "items": {"type": "array", "items": {"type": "string", "enum": CANON}, "description": "One or more items"},
        "scope": {"type": "string", "enum": ["consolidated", "standalone"]},
        "fiscal_years": {"type": "array", "items": {"type": "string", "enum": YEARS}}},
        "required": ["items"]}}})


def _inr(v):
    """Indian digit grouping: 232139.94 -> 2,32,139.94"""
    i, d = f"{abs(v):.2f}".split(".")
    if len(i) > 3:
        head, parts = i[:-3], []
        while len(head) > 2: parts.insert(0, head[-2:]); head = head[:-2]
        if head: parts.insert(0, head)
        i = ",".join(parts + [i[-3:]])
    return ("-" if v < 0 else "") + i + "." + d

def compute_metric(formula, name=None, scope="consolidated", fiscal_years=None, decimals=4):
    """Evaluate a formula over canonical items for every year, exactly. avg(x) = mean of this and previous
    year-end; prev(x) = previous year. Returns a ready-to-paste table with inputs, results and sources."""
    sc = norm_scope(scope) or "consolidated"
    fys = [f for f in (norm_fy(y) for y in _list(fiscal_years)) if f] or YEARS
    try: tree = ast.parse(str(formula), mode="eval")
    except SyntaxError as e: return {"error": f"formula syntax error: {e}"}
    names = sorted({n.id for n in ast.walk(tree) if isinstance(n, ast.Name) and n.id not in ("avg", "prev")})
    missing = [n for n in names if n not in FIN.get(sc, {})]
    if missing: return {"error": f"unknown items {missing}", "available_items": CANON}
    prev_fy = lambda fy: YEARS[YEARS.index(fy) - 1] if fy in YEARS and YEARS.index(fy) > 0 else None
    def val(key, fy):
        v = FIN[sc][key]["values"].get(fy) if fy else None
        return None if v is None else v["value"]
    def ev(n, fy):
        if isinstance(n, ast.Constant) and isinstance(n.value, (int, float)): return n.value
        if isinstance(n, ast.Name): return val(n.id, fy)
        if isinstance(n, ast.Call) and getattr(n.func, "id", "") in ("avg", "prev") and len(n.args) == 1:
            cur, pv = ev(n.args[0], fy), ev(n.args[0], prev_fy(fy))
            if n.func.id == "prev": return pv
            return None if cur is None or pv is None else (cur + pv) / 2
        if isinstance(n, ast.BinOp):
            a, b = ev(n.left, fy), ev(n.right, fy)
            if a is None or b is None or (isinstance(n.op, ast.Div) and b == 0): return None
            return OPS[type(n.op)](a, b)
        if isinstance(n, ast.UnaryOp):
            a = ev(n.operand, fy); return None if a is None else OPS[type(n.op)](a)
        raise ValueError("use item names, numbers, + - * / ** ( ), avg(item), prev(item)")
    label = name or str(formula)
    try: results = {fy: ev(tree.body, fy) for fy in fys}
    except ValueError as e: return {"error": str(e)}
    uses_prev = any(isinstance(n, ast.Call) for n in ast.walk(tree))
    header = ("| Fiscal year | " + " | ".join(names) + (" | (prior year-end used for avg/prev)" if uses_prev else "")
              + f" | {label} | Change vs prior year | % change |")
    rows = [header, "|---|" + "---|" * (len(names) + (4 if uses_prev else 3))]
    sources = {}
    for fy in fys:
        cells = [_inr(val(k, fy)) if val(k, fy) is not None else "n/a" for k in names]
        if uses_prev:
            cells.append(", ".join(f"{k}: {_inr(val(k, prev_fy(fy)))}" for k in names if val(k, prev_fy(fy)) is not None) or "n/a")
        r = results[fy]
        cells.append("n/a" if r is None else f"{r:.{int(decimals)}f}")
        i = fys.index(fy)
        pr = results.get(fys[i - 1]) if i > 0 else None
        if r is None or pr is None: cells += ["n/a", "n/a"]
        else: cells += [f"{r - pr:+.{int(decimals)}f}", f"{(r - pr) / abs(pr) * 100:+.2f}%" if pr else "n/a"]
        rows.append(f"| {fy} | " + " | ".join(cells) + " |")
        sources[fy] = {k: FIN[sc][k]["values"][fy]["source"] for k in names if fy in FIN[sc][k]["values"]}
    by_fy = {}
    for fy_, d in sources.items():
        for s_ in d.values():
            by_fy.setdefault(fy_, set()).add(s_.split(" Annual Report")[0] + " AR p. " + s_.split("page ")[-1])
    src_line = "Sources: " + "; ".join(f"{fy_}: {', '.join(sorted(v))}" for fy_, v in by_fy.items())
    return {"metric": label, "formula": str(formula), "scope_used": sc, "table": "\n".join(rows) + "\n\n" + src_line,
            "values": {fy: (None if r is None else round(r, int(decimals))) for fy, r in results.items()}, "sources": sources}

FUNCS["compute_metric"] = compute_metric
SCHEMAS.insert(1, {"type": "function", "function": {"name": "compute_metric",
    "description": "PREFERRED for ratios and derived metrics across years. Evaluates a formula over get_financials item names "
                   "for every year exactly and returns a ready-to-paste table (inputs, results, sources). Formula may use item "
                   "names, numbers, + - * / ( ), avg(item) = average of this and previous year-end, prev(item) = previous year. "
                   "Examples: 'total_current_assets / total_current_liabilities'; '(non_current_borrowings + current_borrowings) "
                   "/ total_equity'; 'profit_for_the_year / avg(total_equity) * 100'.",
    "parameters": {"type": "object", "properties": {
        "formula": {"type": "string"}, "name": {"type": "string", "description": "e.g. 'Current ratio'"},
        "scope": {"type": "string", "enum": ["consolidated", "standalone"]},
        "fiscal_years": {"type": "array", "items": {"type": "string", "enum": YEARS}},
        "decimals": {"type": "integer", "description": "Default 4"}},
        "required": ["formula"]}}})


# ---------- breakdown: every component's contribution to a change in a total ----------
BREAKDOWN = {"total_current_assets": ("balance_sheet", "current assets"),
             "total_current_liabilities": ("balance_sheet", "current liabilities"),
             "total_non_current_assets": ("balance_sheet", "non-current assets"),
             "total_non_current_liabilities": ("balance_sheet", "non-current liabilities"),
             "total_expenses": ("profit_and_loss", "expenses"),
             "total_income": ("profit_and_loss", "income")}
_k = lambda s: re.sub(r"[^a-z0-9]+", " ", str(s).lower()).strip()

def breakdown(total, from_year, to_year, scope="consolidated"):
    """All components of a statement total for two years (both from the later year's report), with each
    component's change and share of the total change. Checks the components add up to the reported total."""
    sc = norm_scope(scope) or "consolidated"
    key = total if total in BREAKDOWN else (process.extractOne(str(total), list(BREAKDOWN), scorer=_score, processor=utils.default_process) or [None])[0]
    if key not in BREAKDOWN: return {"error": f"unknown total '{total}'", "available_totals": list(BREAKDOWN)}
    st, prefix = BREAKDOWN[key]
    a, b = norm_fy(from_year), norm_fy(to_year)
    if not a or not b: return {"error": "give from_year and to_year, e.g. FY2024-25 and FY2025-26"}
    rep = b if b in REPORTS else REPORTS[-1]
    comps, pages, reported = {}, set(), {}
    desc = FIN[sc][key]["description"].lower()
    for r in ITEMS:
        if r["report"] != rep or r["scope"] != sc or r["statement"] != st or r["fiscal_year"] not in (a, b): continue
        if r["line_item"].lower() == desc: reported[r["fiscal_year"]] = r["value"]; continue
        if not _k(r["path"]).startswith(_k(prefix)) or r.get("synthetic_label"): continue
        if r["line_item"].lower().startswith("total") and not r["line_item"].lower().startswith("total outstanding dues"): continue
        name = r["line_item"]
        c = comps.setdefault((_k(r["path"]), _k(name)), {"component": (r["path"].split(" > ", 1)[1] + " > " if " > " in r["path"] else "") + name, "values": {}})
        c["values"][r["fiscal_year"]] = -r["value"] if name.lower().startswith("less") else r["value"]
        pages.add(r["page_label"])
    if a not in reported or b not in reported:
        return {"error": f"{rep} report does not contain both {a} and {b}; use consecutive years"}
    rows = sorted([(c["component"], c["values"].get(a, 0.0), c["values"].get(b, 0.0)) for c in comps.values()],
                  key=lambda x: -abs(x[2] - x[1]))
    tchg = round(reported[b] - reported[a], 2)
    table = (f"| Component of {FIN[sc][key]['description']} | {a} | {b} | Change | % change (own YoY) | Contribution to total change |\n"
             "|---|---|---|---|---|---|\n")
    for name, va, vb in rows:
        ch = round(vb - va, 2)
        pct = f"{ch / abs(va) * 100:+.2f}%" if va else "n/a"
        share = f"{ch / tchg * 100:+.1f}%" if tchg else "n/a"
        table += f"| {name} | {_inr(va)} | {_inr(vb)} | {'+' if ch > 0 else ''}{_inr(ch)} | {pct} | {share} |\n"
    tpct = f"{tchg / abs(reported[a]) * 100:+.2f}%" if reported[a] else "n/a"
    table += f"| {FIN[sc][key]['description']} (reported) | {_inr(reported[a])} | {_inr(reported[b])} | {'+' if tchg > 0 else ''}{_inr(tchg)} | {tpct} | 100% |\n"
    sa, sb = round(sum(x[1] for x in rows), 2), round(sum(x[2] for x in rows), 2)
    return {"total": key, "scope_used": sc, "from": a, "to": b, "source": f"{rep} Annual Report, {sc} {st.replace('_', ' ')}, pages {', '.join(sorted(p for p in pages if p))}",
            "table": table, "components_reconcile_to_reported_total": abs(sa - reported[a]) < 0.05 and abs(sb - reported[b]) < 0.05}

FUNCS["breakdown"] = breakdown
SCHEMAS.insert(2, {"type": "function", "function": {"name": "breakdown",
    "description": "Explain a change in a statement total: returns EVERY component of the total for two years with its change "
                   "and share of the total change (largest first), as a ready-to-paste table. Totals: " + ", ".join(BREAKDOWN),
    "parameters": {"type": "object", "properties": {
        "total": {"type": "string", "enum": list(BREAKDOWN)},
        "from_year": {"type": "string", "enum": YEARS}, "to_year": {"type": "string", "enum": YEARS},
        "scope": {"type": "string", "enum": ["consolidated", "standalone"]}},
        "required": ["total", "from_year", "to_year"]}}})


# ---------- risk sections, for risk-evolution questions ----------
CHUNKS = [json.loads(l) for l in open(ROOT / "data/processed/chunks.jsonl")]

def list_risk_disclosures(report):
    """Every risk-tagged narrative page of one report (page, title, short excerpt), for side-by-side comparison."""
    rep = norm_fy(report)
    rows = sorted((c for c in CHUNKS if c["report"] == rep and c["type"] == "narrative" and "risk" in c["topics"]), key=lambda c: c["page"])
    out, seen = [], set()
    for c in rows:
        if c["page"] in seen: continue
        seen.add(c["page"])
        out.append({"pdf_page": c["page"], "section": c["section"], "title": (c["note"] or "")[:120],
                    "excerpt": _compact(c["text"].split("\n\n", 1)[-1])[:350]})
    return {"report": rep, "risk_pages": out[:30],
            "note": "Risk-related pages of this report. Use search_documents with a specific risk name to read more or to check another report."}

FUNCS["list_risk_disclosures"] = list_risk_disclosures
SCHEMAS.append({"type": "function", "function": {"name": "list_risk_disclosures",
    "description": "List every risk-related page (risk management, key risks, regulatory/financial/ESG risks) of ONE annual report, "
                   "with titles and excerpts. Call it once per report when comparing how risks changed between years.",
    "parameters": {"type": "object", "properties": {"report": {"type": "string", "enum": REPORTS}}, "required": ["report"]}}})


# ---------- composite scores: Altman Z'' (book equity), Piotroski F, Beneish M ----------
sys.path.insert(0, str(ROOT / "src" / "analysis"))
import scores as S

SCORE_NAMES = {"altman_z": "Altman Z'' (book equity)", "piotroski_f": "Piotroski F-score", "beneish_m": "Beneish M-score (8-variable)"}
COMPONENT_LABELS = {
    "X1": "X1 (current assets - current liabilities) / total assets", "X2": "X2 other equity / total assets",
    "X3": "X3 (PBT + finance costs) / total assets", "X4": "X4 total equity / (total assets - total equity)",
    "DSRI": "DSRI receivables-to-sales index", "GMI": "GMI gross margin index", "AQI": "AQI asset quality index",
    "SGI": "SGI sales growth index", "DEPI": "DEPI depreciation index", "SGAI": "SGAI other-expenses (SG&A proxy) index",
    "LVGI": "LVGI leverage index", "TATA": "TATA total accruals / total assets"}
_INR_SIGNALS = ("F2_cfo_positive", "F7_no_new_equity")    # compared amounts are INR crore, not ratios

def norm_score(x):
    x = str(x or "all").lower()
    if "altman" in x or x in ("z", "z''", "zscore", "z_score"): return "altman_z"
    if "piotroski" in x or x in ("f", "fscore", "f_score"): return "piotroski_f"
    if "beneish" in x or x in ("m", "mscore", "m_score"): return "beneish_m"
    if x in ("all", "any", "every", "*"): return "all"
    return None

def _score_table(name, res, fys):
    """Markdown table for one score: components (4 decimals), score, interpretation, then inputs (INR crore)."""
    rows = [f"| {SCORE_NAMES[name]} | " + " | ".join(fys) + " |", "|---|" + "---|" * len(fys)]
    comp_keys = next((list(r["components"]) for r in res.values() if r["components"]), [])
    for k in comp_keys:
        cells = []
        for fy in fys:
            c = res[fy]["components"].get(k)
            if c is None: cells.append("n/a")
            elif name == "piotroski_f":
                f = _inr if k in _INR_SIGNALS else (lambda v: f"{v:.4f}")
                cells.append("n/a" if c["signal"] is None or c["current"] is None or c["comparison"] is None
                             else f"{c['signal']} ({f(c['current'])} vs {f(c['comparison'])})")
            else: cells.append(f"{c:.4f}")
        label = res[next(iter(res))]["components"].get(k, {}).get("description", k) if name == "piotroski_f" else COMPONENT_LABELS.get(k, k)
        rows.append(f"| {(k.split('_')[0] + ' ' + label) if name == 'piotroski_f' else label} | " + " | ".join(cells) + " |")
    fmt = (lambda v: str(v)) if name == "piotroski_f" else (lambda v: f"{v:.4f}")
    rows.append(f"| **Score** | " + " | ".join("n/a" if res[fy]["score"] is None else f"**{fmt(res[fy]['score'])}**" for fy in fys) + " |")
    rows.append(f"| Interpretation | " + " | ".join(res[fy]["interpretation"] or "n/a" for fy in fys) + " |")
    rel = {0: "t", 1: "t-1", 2: "t-2"}
    inputs = {}
    for fy in fys:
        for rec in res[fy]["inputs"].values():
            lag = S.YEARS.index(fy) - S.YEARS.index(rec["fiscal_year"])
            cell = _inr(rec["value"]) + ("*" if rec.get("restated") else "")
            inputs.setdefault((rec["item"], lag), {})[fy] = cell
    for (item, lag), cells in inputs.items():
        rows.append(f"| {item} [{rel.get(lag, lag)}] (INR crore) | " + " | ".join(cells.get(fy, "n/a") for fy in fys) + " |")
    return "\n".join(rows)

def compute_scores(score="all", fiscal_years=None, scope="consolidated"):
    """Altman Z'' (book equity), Piotroski F and Beneish M for each year, with every component, input and source,
    proxies disclosed, plus a ready-to-paste markdown table."""
    sc = norm_scope(scope) or "consolidated"
    key = norm_score(score)
    if not key: return {"error": f"unknown score '{score}'", "available_scores": list(SCORE_NAMES) + ["all"]}
    fys = [f for f in (norm_fy(y) for y in _list(fiscal_years)) if f in S.YEARS] or S.SCORE_YEARS
    fys = sorted(set(fys), key=S.YEARS.index)
    names = list(SCORE_NAMES) if key == "all" else [key]
    out = {n: S.all_scores(sc, fys)["scores"][n] for n in names}
    tables, notes, pages = [], [], {}
    for n in names:
        tables.append(_score_table(n, out[n], fys))
        for fy in fys:
            r = out[n][fy]
            if r["score"] is None: notes.append(f"{SCORE_NAMES[n]} {fy}: not computed ({r.get('reason') or '; '.join(r['missing'])})")
            notes += [f"{SCORE_NAMES[n]} {fy}: fallback: {f}" for f in r["fallbacks"]]
            for rec in r["inputs"].values():
                m = re.search(r"(FY\d{4}-\d{2}) Annual Report.*page (\S+)", rec["source"])
                if m: pages.setdefault(m.group(1), set()).add(m.group(2))
        proxies = dict.fromkeys(p for fy in fys for p in out[n][fy]["proxies"])
        notes += [f"{SCORE_NAMES[n]} proxy: {p}" for p in proxies]
    sources = "Sources: " + "; ".join(f"{rep} AR p. {', '.join(sorted(p))}" for rep, p in sorted(pages.items()))
    table = ("\n\n".join(tables) + "\n\nt = the scored year, t-1 = prior year; two-year scores take both years from the "
             "report of year t. * = restated in that report.\n\n" + sources)
    return {"score": key, "scope_used": sc, "unit": "INR crore", "years": fys,
            "year_convention": "FY2025-26 = year ended 31 March 2026.",
            "thresholds": {"altman_z": "> 2.60 safe; 1.10-2.60 grey; < 1.10 distress",
                           "piotroski_f": "8-9 strong; 5-7 average; 0-4 weak",
                           "beneish_m": "M > -1.78 possible earnings manipulation flag; otherwise unlikely manipulator"},
            "scores": out, "table": table, "sources": sources, "notes": notes}

FUNCS["compute_scores"] = compute_scores
SCHEMAS.append({"type": "function", "function": {"name": "compute_scores",
    "description": "Composite scores computed exactly from the verified statements: Altman Z'' (book-equity version; "
                   "safe/grey/distress), Piotroski F-score (0-9, nine signals) and Beneish M-score (8-variable earnings-"
                   "manipulation screen). Returns every component and input with sources, the proxies used, and a "
                   "ready-to-paste table. Use for questions on bankruptcy risk, financial strength or earnings quality.",
    "parameters": {"type": "object", "properties": {
        "score": {"type": "string", "enum": list(SCORE_NAMES) + ["all"], "description": "Default all"},
        "fiscal_years": {"type": "array", "items": {"type": "string", "enum": S.SCORE_YEARS}},
        "scope": {"type": "string", "enum": ["consolidated", "standalone"]}},
        "required": ["score"]}}})
