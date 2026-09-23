"""Stage 3: extract clean, verified line items from the primary statements (BS, P&L, cash flow).

Uses the coordinate line reader: Docling merged and shifted rows on dense single-page
statements (e.g. FY23 standalone balance sheet), while these pages have a simple
label-plus-value-columns layout. Docling is kept for the notes tables.
Checks: Total assets == Total equity and liabilities; section items sum to their Total row.
Output: data/processed/line_items.jsonl
"""
import json, re, statistics, sys
from pathlib import Path
import pymupdf
sys.path.insert(0, str(Path(__file__).parent))
from statement_lines import page_lines

INTERIM, OUT = Path("data/interim"), Path("data/processed")
OUT.mkdir(parents=True, exist_ok=True)
PRIMARY = ("balance_sheet", "profit_and_loss", "cash_flow")
MARKER = re.compile(r"^\((?:[ivxlc]{1,5}|[a-zA-Z])\)$|^(?:I|II|III|IV|V|VI|VII|VIII|IX|X)$")
REF = re.compile(r"^(?:F\d{1,3}|\d{1,3})$")
IGNORE = re.compile(r"^(?:consolidated )?(?:balance sheet|statement of)|^(?:as at|year ended|for the year|note|march 31|particulars)|^\(?i crore\)?$", re.I)
STOP = re.compile(r"^(?:notes forming part|in terms of our report|for and on behalf)", re.I)
TOP = re.compile(r"^(?:non-current assets|current assets|equity|non-current liabilities|current liabilities|assets|"
                 r"income|expenses|other comprehensive income|.*cash flows? (?:from|used in))", re.I)
CHECK = {"non-current assets", "current assets", "non-current liabilities", "current liabilities"}

def fy_of(end_year): return f"FY{end_year - 1}-{str(end_year)[2:]}"

def parse_num(s):
    s = s.strip().replace("\u2212", "-")
    if s in {"-", "–", "—"}: return 0.0
    neg = s.startswith("(") and s.endswith(")")
    try: v = float(s.strip("()").replace(",", ""))
    except ValueError: return None
    return -v if neg else v

def extract(doc, report, scope, stmt, pages, labels):
    end = int(report[2:6]) + 1
    cur_fy, pri_fy = fy_of(end), fy_of(end - 1)
    lines = []
    for pg in pages:
        for t, v in page_lines(doc, pg):
            if lines and not lines[-1][2] and t[:1].islower() and lines[-1][0] == pg:   # wrapped label
                t = lines.pop()[1] + " " + t
            lines.append((pg, t, v))
    swap = False
    for _, t, _ in lines[:20]:
        ys = [int(y) for y in re.findall(r"20\d\d", t)]
        if len(ys) >= 2 and "march" in t.lower():
            swap = ys[0] < ys[1]; break
    order = [pri_fy, cur_fy] if swap else [cur_fy, pri_fy]
    two = [v for _, _, v in lines if len(v) == 2]
    if not two: return [], [], {"error": "no two-value lines"}
    cx = [statistics.median(v[0][0] for v in two), statistics.median(v[1][0] for v in two)]
    recs, checks, stats, stack, sums, stopped = [], [], {"one_value": 0, "multi_value": 0}, [], {}, set()
    for pg, t, vals in lines:
        if pg in stopped: continue
        if STOP.match(t): stopped.add(pg); continue
        toks = [w for w in t.split() if not MARKER.match(w)]
        while toks and REF.match(toks[-1]): toks.pop()
        label = " ".join(toks).strip(" :")
        if not label or IGNORE.match(label): continue
        if not vals:
            if TOP.match(label): stack, sums = [label], {}
            else: stack = stack[:1] + [label]
            continue
        if len(vals) > 2: stats["multi_value"] += 1; vals = vals[-2:]
        if len(vals) == 2:
            assigned = {order[0]: vals[0][1], order[1]: vals[1][1]}
        else:
            stats["one_value"] += 1
            x, s = vals[0]
            assigned = {order[0 if abs(x - cx[0]) <= abs(x - cx[1]) else 1]: s}
        parsed = {fy: parse_num(s) for fy, s in assigned.items()}
        for fy, v in parsed.items():
            if v is not None:
                recs.append(dict(report=report, fiscal_year=fy, scope=scope, statement=stmt, page=pg,
                                 page_label=labels.get(pg), path=" > ".join(stack), line_item=label,
                                 value=v, unit="INR crore", source="coordinate"))
        low, sec = label.lower(), (stack[0].lower() if stack else "")
        if low.startswith("total"):
            if sec in CHECK and low == f"total {sec}":
                for fy, v in parsed.items():
                    if v is not None:
                        s = round(sums.get(fy, 0.0), 2)
                        checks.append((f"{report} | {scope:12} | {fy} | {label}", s, v, abs(s - v) < 0.02))
            stack = [] if sec and sec in low else stack[:1]
            if not stack: sums = {}
        elif sec in CHECK:
            for fy, v in parsed.items():
                if v is not None: sums[fy] = sums.get(fy, 0.0) + v
    return recs, checks, stats

records, checks = [], []
print("EXTRACTION SUMMARY (records | one-value lines | >2-value lines):")
for path in sorted(Path("data/raw").glob("TataSteel_FY*.pdf")):
    report = path.stem.split("_")[1]
    pm = json.loads((INTERIM / f"page_map_{report}.json").read_text())
    labels = {p["page"]: p["label"] for p in pm}
    doc = pymupdf.open(path)
    for scope in ("standalone", "consolidated"):
        for stmt in PRIMARY:
            pages = [p["page"] for p in pm if p["scope"] == scope and p["statement"] == stmt]
            if not pages:
                print(f"  {report} {scope:12} {stmt:16} NO PAGES FOUND"); continue
            r, c, s = extract(doc, report, scope, stmt, pages, labels)
            records += r; checks += c
            print(f"  {report} {scope:12} {stmt:16} pages {pages[0]}-{pages[-1]}: {len(r):4} | {s}")

with open(OUT / "line_items.jsonl", "w") as f:
    for r in records: f.write(json.dumps(r) + "\n")
print(f"\n{len(records)} records written to data/processed/line_items.jsonl")

print("\nBALANCE SHEET IDENTITY (Total assets vs Total equity and liabilities):")
for rep, sc, fy in sorted({(r["report"], r["scope"], r["fiscal_year"]) for r in records if r["statement"] == "balance_sheet"}):
    get = lambda name: next((r["value"] for r in records if (r["report"], r["scope"], r["fiscal_year"]) == (rep, sc, fy)
                             and r["statement"] == "balance_sheet" and r["line_item"].lower() == name), None)
    ta, tel = get("total assets"), get("total equity and liabilities")
    ok = "OK" if ta is not None and tel is not None and abs(ta - tel) < 0.02 else "MISMATCH"
    print(f"  {rep} report | {sc:12} | {fy}: {ta} vs {tel}  {ok}")

passed = sum(1 for c in checks if c[3])
print(f"\nSECTION SUBTOTAL CHECKS: {passed}/{len(checks)} passed")
for name, s, v, ok in checks:
    if not ok: print(f"  FAIL {name}: items sum {s} vs stated {v}")
