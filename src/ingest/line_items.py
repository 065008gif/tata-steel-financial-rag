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
    lines = []
    for pg in pages:
        for t, v in page_lines(doc, pg):
            if lines and lines[-1][0] == pg:
                _, pt, pv = lines[-1]
                if not t.strip() and v and not pv:                 # values on their own line -> label above
                    lines[-1] = (pg, pt, v); continue
                if t[:1].islower() and (not pv or not v):         # wrapped label continuation
                    lines[-1] = (pg, pt + " " + t, pv or v); continue
            lines.append((pg, t, v))
    restated = "restated" in " ".join(t.lower() for _, t, _ in lines[:25])
    K = min(3, max((len(v) for _, _, v in lines), default=0))       # number of value columns (2, or 3 if restated)
    full = [v for _, _, v in lines if len(v) == K]
    if K < 2 or not full: return [], [], {"error": f"no {K}-value lines"}
    cx = [statistics.median(v[i][0] for v in full) for i in range(K)]
    order = [fy_of(end - i) for i in range(K)]                       # leftmost column = current year
    for _, t, _ in lines[:20]:
        ys = [int(y) for y in re.findall(r"20\d\d", t)]
        if len(ys) >= 2 and re.search(r"march|april", t, re.I):
            if ys[0] < ys[1]: order.reverse()
            break
    cur = fy_of(end)
    recs, checks, stack, sums, stopped, prev = [], [], [], {}, set(), ""
    stats = {"columns": K, "restated": restated, "partial_rows": 0, "extra_values": 0, "unlabelled_subtotals": 0}
    for pg, t, vals in lines:
        if pg in stopped: continue
        if STOP.match(t): stopped.add(pg); continue
        toks = [w for w in t.split() if not MARKER.match(w)]
        while toks and REF.match(toks[-1]): toks.pop()
        label, synthetic = " ".join(toks).strip(" :"), False
        if not label:
            if not vals: continue
            label, synthetic = f"Unlabelled subtotal (after: {prev})", True
            stats["unlabelled_subtotals"] += 1
        if IGNORE.match(label): continue
        if not vals:
            if TOP.match(label): stack, sums = [label], {}
            else: stack = stack[:1] + [label]
            continue
        if len(vals) > K: stats["extra_values"] += 1; vals = vals[-K:]
        if len(vals) == K:
            assigned = {order[i]: vals[i][1] for i in range(K)}
        else:
            stats["partial_rows"] += 1
            assigned = {order[min(range(K), key=lambda k: abs(x - cx[k]))]: sv for x, sv in vals}
        parsed = {fy: parse_num(sv) for fy, sv in assigned.items()}
        for fy, v in parsed.items():
            if v is not None:
                recs.append(dict(report=report, fiscal_year=fy, scope=scope, statement=stmt, page=pg,
                                 page_label=labels.get(pg), path=" > ".join(stack), line_item=label, value=v,
                                 unit="INR crore", restated=restated and fy != cur, synthetic_label=synthetic,
                                 source="coordinate"))
        if synthetic: continue
        prev = label
        low, sec = label.lower(), (stack[0].lower() if stack else "")
        if low.startswith("total") and not low.startswith("total outstanding dues"):
            if sec in CHECK and low == f"total {sec}":
                for fy, v in parsed.items():
                    if v is not None:
                        sm = round(sums.get(fy, 0.0), 2)
                        checks.append((f"{report} | {scope:12} | {fy} | {label}", sm, v, abs(sm - v) < 0.02))
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

# Restatement handling: prefer the latest report containing each year (comparable basis),
# and flag any value that differs from the year's own original report.
latest, original = {}, {}
for r in records:
    k = (r["scope"], r["statement"], r["fiscal_year"])
    latest[k] = max(latest.get(k, ""), r["report"])
own = {r["fiscal_year"] for r in records if r["report"] == r["fiscal_year"]}
for r in records:
    ok_report = r["report"] == r["fiscal_year"] or (r["fiscal_year"] not in own and r["report"] == min(
        x["report"] for x in records if x["fiscal_year"] == r["fiscal_year"]))
    if ok_report:
        original[(r["scope"], r["statement"], r["fiscal_year"], r["path"], r["line_item"])] = r["value"]
n_diff = 0
for r in records:
    r["preferred"] = r["report"] == latest[(r["scope"], r["statement"], r["fiscal_year"])]
    o = original.get((r["scope"], r["statement"], r["fiscal_year"], r["path"], r["line_item"]))
    r["original_value"] = o
    r["differs_from_original"] = o is not None and abs(o - r["value"]) > 0.01
    n_diff += r["differs_from_original"]
print(f"Restatement pass: {sum(r['preferred'] for r in records)} preferred records, {n_diff} differ from original report")

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
