"""Extract segment revenue and segment results from the consolidated "Segment reporting" note of every report.

Layout (all four reports): segments are COLUMNS (last two: inter-segment eliminations, total); each item is two
stacked rows without year labels - first row = the report's year, second row = the prior year. Cells can be blank
(no token at all) or "-" (nil), so values are placed in columns by position, not by order: the words of the table
(pymupdf "words") are grouped into lines by y, numeric tokens into columns by their right edge (numbers are right-
aligned), and the header phrases above the table into the same columns by overlapping x-ranges.
Rows: the numeric lines between an item's label ("External revenue", "Inter(-)segment revenue", "Total Revenue",
"Segment results ...") and the next label; exactly two per item are required.

Checks, printed as a table (a value failing any check is left out and listed as unresolved, never guessed):
  (a) every value, in Indian format, is present in the whitespace-normalised pymupdf text of its cited page
      ("-" cells are present as a "-" token in that column; blank cells are omitted, not zero-filled)
  (b) sum of segments + eliminations == printed total, per item and year (to 0.01)
  (c) total external revenue == consolidated revenue_from_operations of that report and year in
      financials_by_report.json (to 0.01)
  (d) extra: external + inter-segment revenue == segment (total) revenue, per column and year (to 0.01)
Output: data/processed/segments.json
  {report: {fiscal_year: {"segments": {name: {"key", item: value}}, "totals": {item: value},
                          "eliminations": {item: value}, "pdf_page", "page_label", "unit", "eliminations_name",
                          "blank_cells": ["item / column" printed empty - omitted, not zero-filled]}}}
"""
import json, re
from pathlib import Path
import pymupdf

ROOT = Path(__file__).resolve().parents[2]
RAW, INTERIM, PROC = ROOT / "data/raw", ROOT / "data/interim", ROOT / "data/processed"
OUT = PROC / "segments.json"
REPORTS = ["FY2022-23", "FY2023-24", "FY2024-25", "FY2025-26"]
ITEMS = ["external_revenue", "inter_segment_revenue", "segment_revenue", "segment_results"]
LABELS = [("external_revenue", re.compile(r"^External revenue", re.I)),
          ("inter_segment_revenue", re.compile(r"^Inter[\s-]?segment revenue", re.I)),
          ("segment_revenue", re.compile(r"^Total Revenue", re.I)),
          ("segment_results", re.compile(r"^Segment results", re.I))]
END = re.compile(r"^Reconciliation", re.I)
NUM = re.compile(r"^(\()?(\d{1,3}(?:,\d{2})*,?\d{0,3}\.\d{2})(\))?$|^-$")
KEYS = [(r"^tata steel india", "tata_steel_india"), (r"^tata steel long products", "tata_steel_long_products"),
        (r"^neelachal ispat nigam", "neelachal_ispat_nigam"), (r"^other indian operations", "other_indian_operations"),
        (r"^tata steel europe", "tata_steel_europe"), (r"^tata steel netherlands", "tata_steel_netherlands"),
        (r"^tata steel uk", "tata_steel_uk"), (r"^other trade related", "other_trade_related_operations"),
        (r"^south-east asian", "south_east_asian_operations"), (r"^rest of the world", "rest_of_the_world"),
        (r"^inter-?\s?segment eliminations", "eliminations"), (r"^total$", "total")]
TOL = 0.011

def norm(s):
    return re.sub(r"\s+", " ", s).strip()

def inr(v):
    """Indian number format as printed in the reports: 1,00,920.21; negatives in brackets."""
    i, d = f"{abs(v):.2f}".split(".")
    if len(i) > 3:
        head, parts = i[:-3], []
        while len(head) > 2: parts.insert(0, head[-2:]); head = head[:-2]
        if head: parts.insert(0, head)
        i = ",".join(parts + [i[-3:]])
    s = i + "." + d
    return f"({s})" if v < 0 else s

def num(tok):
    m = NUM.match(tok)
    if not m: return None
    if tok == "-": return 0.0
    v = float(m.group(2).replace(",", ""))
    return -v if m.group(1) else v

def seg_key(name):
    n = name.lower()
    for pat, key in KEYS:
        if re.search(pat, n): return key
    return re.sub(r"[^a-z0-9]+", "_", n).strip("_")

def fy_prior(fy):
    a = int(fy[2:6]) - 1
    return f"FY{a}-{str(a + 1)[2:]}"

def find_page(doc, pmap):
    """1-based consolidated notes page holding the segment revenue/results table."""
    pages = [p["page"] for p in pmap if p["scope"] == "consolidated" and p["statement"] == "notes"
             and "Segment reporting" in (t := doc[p["page"] - 1].get_text()) and "Segment results" in t
             and "External revenue" in t]
    return pages

def lines_of(page):
    """Words grouped into lines (y within 2.5pt), each line sorted by x: [(y, [(x0, x1, text)])]."""
    words = sorted(page.get_text("words"), key=lambda w: (w[3], w[0]))
    lines = []
    for x0, y0, x1, y1, t, *_ in words:
        if lines and abs(lines[-1][0] - y1) <= 2.5: lines[-1][1].append((x0, x1, t))
        else: lines.append([y1, [(x0, x1, t)]])
    return [(y, sorted(ws)) for y, ws in lines]

def parse(page):
    """Returns ({item: [row_report_year, row_prior_year]} with rows as {column_name: value}, columns, problems)."""
    lines = lines_of(page)
    txt = [" ".join(w[2] for w in ws) for _, ws in lines]
    top = next(k for k, t in enumerate(txt) if "reportable segments" in t)
    unit = next(k for k in range(top, len(txt)) if re.search(r"crore\)", txt[k]))
    first = next(k for k in range(unit, len(txt)) if re.match(r"Segment revenue", txt[k]))
    end = next(k for k in range(first, len(txt)) if END.match(txt[k]))
    # numeric columns: cluster right edges of numeric tokens in the table body
    body = lines[first:end]
    label_right = min(w[0] for _, ws in body for w in ws if num(w[2]) is not None) - 5
    edges = sorted(w[1] for _, ws in body for w in ws if num(w[2]) is not None)
    cols = [[edges[0]]]
    for e in edges[1:]:
        (cols[-1].append(e) if e - cols[-1][-1] <= 12 else cols.append([e]))
    col_x = [max(c) for c in cols]
    # header phrases (words on a line with gaps < 5pt), merged into columns when their x-ranges overlap
    phrases = []
    for y, ws in lines[unit + 1:first]:
        for x0, x1, t in ws:
            if x0 < label_right: continue
            if phrases and phrases[-1][0] == y and x0 - phrases[-1][2] < 5:
                phrases[-1][2] = x1; phrases[-1][3].append(t)
            else: phrases.append([y, x0, x1, [t]])
    groups = []
    for ph in phrases:
        hit = [g for g in groups if ph[1] <= g["x1"] + 1 and ph[2] >= g["x0"] - 1]
        g = {"x0": ph[1], "x1": ph[2], "parts": [ph]}
        for h in hit:
            groups.remove(h); g["x0"] = min(g["x0"], h["x0"]); g["x1"] = max(g["x1"], h["x1"]); g["parts"] += h["parts"]
        groups.append(g)
    groups.sort(key=lambda g: g["x1"])
    problems = []
    if len(groups) != len(col_x):
        return {}, [], [f"{len(groups)} header columns but {len(col_x)} numeric columns"]
    names = []
    for g, cx in zip(groups, col_x):
        if not -6 <= cx - g["x1"] <= 10: problems.append(f"header '{g['parts']}' not aligned with numbers at x={cx:.0f}")
        words = [t for ph in sorted(g["parts"], key=lambda p: (p[0], p[1])) for t in ph[3]]
        names.append(re.sub(r"(\w)- (\w)", r"\1-\2", " ".join(words)))
    # rows: numeric lines between one item label and the next
    anchors = []
    for k in range(first, end):
        label = " ".join(w[2] for w in lines[k][1] if w[1] < label_right)
        for item, pat in LABELS:
            if pat.match(label): anchors.append((lines[k][0], item))
    if [a[1] for a in anchors] != ITEMS:
        return {}, names, problems + [f"item labels found {[a[1] for a in anchors]}"]
    out = {}
    for i, (ay, item) in enumerate(anchors):
        ny = anchors[i + 1][0] - 3 if i + 1 < len(anchors) else lines[end][0] - 3
        rows = []
        for y, ws in body:
            if not ay - 3 <= y < ny: continue
            nums = [w for w in ws if w[0] >= label_right]
            if not nums: continue
            row = {}
            for x0, x1, t in nums:
                v = num(t)
                c = min(range(len(col_x)), key=lambda j: abs(col_x[j] - x1))
                if v is None or abs(col_x[c] - x1) > 8 or names[c] in row:
                    problems.append(f"{item}: cannot place token '{t}' at x={x1:.0f}"); continue
                row[names[c]] = (v, t)
            rows.append(row)
        if len(rows) != 2: problems.append(f"{item}: expected 2 stacked rows, found {len(rows)}")
        out[item] = rows
    return out, names, problems

def extract():
    fin = json.loads((PROC / "financials_by_report.json").read_text())
    out, checks, unresolved = {}, [], []
    for rep in REPORTS:
        doc = pymupdf.open(RAW / f"TataSteel_{rep}.pdf")
        pmap = json.loads((INTERIM / f"page_map_{rep}.json").read_text())
        labels = {p["page"]: p["label"] for p in pmap}
        pages = find_page(doc, pmap)
        if len(pages) != 1:
            unresolved.append(f"{rep}: expected one segment table page, found {pages}"); continue
        pno = pages[0]
        text = norm(doc[pno - 1].get_text())
        rows, names, problems = parse(doc[pno - 1])
        if problems:
            unresolved += [f"{rep}: {p}" for p in problems]; continue
        seg_names = [n for n in names if seg_key(n) not in ("eliminations", "total")]
        elim = next(n for n in names if seg_key(n) == "eliminations")
        total = next(n for n in names if seg_key(n) == "total")
        for r, fy in enumerate((rep, fy_prior(rep))):
            vals = {item: {n: rows[item][r][n][0] for n in names if n in rows[item][r]} for item in ITEMS}
            bad = set()   # (item, column) left out
            # (a) present on page
            for item in ITEMS:
                for n, (v, tok) in rows[item][r].items():
                    ok = tok == "-" or inr(v) in text
                    checks.append((rep, fy, "a", f"{item} / {n}", tok, ok))
                    if not ok: bad.add((item, n)); unresolved.append(f"{rep} {fy} {item} {n}: {tok} not on page {pno}")
            # (b) segments + eliminations == total
            for item in ITEMS:
                if total not in vals[item]:
                    unresolved.append(f"{rep} {fy} {item}: total cell blank on page {labels.get(pno)} - no total to check")
                    continue
                s = sum(vals[item].get(n, 0.0) for n in seg_names + [elim])
                ok = abs(s - vals[item][total]) <= TOL
                checks.append((rep, fy, "b", f"{item}: sum {inr(s)} vs total", inr(vals[item][total]), ok))
                if not ok:
                    bad |= {(item, n) for n in names}
                    unresolved.append(f"{rep} {fy} {item}: segments + eliminations {inr(s)} != total {inr(vals[item][total])}")
            # (c) total external revenue == consolidated revenue from operations
            ref = fin[rep]["consolidated"].get("revenue_from_operations", {}).get("values", {}).get(fy, {}).get("value")
            ext = vals["external_revenue"].get(total)
            ok = ref is not None and ext is not None and abs(ref - ext) <= TOL
            checks.append((rep, fy, "c", f"external revenue total vs revenue_from_operations {inr(ref) if ref is not None else 'n/a'}",
                           inr(ext) if ext is not None else "n/a", ok))
            if not ok:
                bad |= {("external_revenue", n) for n in names}
                unresolved.append(f"{rep} {fy}: external revenue total != consolidated revenue from operations")
            # (d) external + inter-segment == segment revenue, per column
            for n in names:
                if n not in vals["segment_revenue"]: continue
                s = vals["external_revenue"].get(n, 0.0) + vals["inter_segment_revenue"].get(n, 0.0)
                ok = abs(s - vals["segment_revenue"][n]) <= TOL
                checks.append((rep, fy, "d", f"external + inter-segment = revenue / {n}", inr(vals["segment_revenue"][n]), ok))
                if not ok:
                    bad |= {(i, n) for i in ("external_revenue", "inter_segment_revenue", "segment_revenue")}
                    unresolved.append(f"{rep} {fy} {n}: external + inter-segment {inr(s)} != segment revenue")
            rec = {"segments": {}, "totals": {}, "eliminations": {}, "pdf_page": pno, "page_label": labels.get(pno),
                   "unit": "INR crore", "eliminations_name": elim,
                   "blank_cells": [f"{item} / {n}" for item in ITEMS for n in names if n not in vals[item]]}
            for n in names:
                d = {item: vals[item][n] for item in ITEMS if n in vals[item] and (item, n) not in bad}
                if n == total: rec["totals"] = d
                elif n == elim: rec["eliminations"] = d
                else: rec["segments"][n] = {"key": seg_key(n), **d}
            out.setdefault(rep, {})[fy] = rec
    return out, checks, unresolved

if __name__ == "__main__":
    out, checks, unresolved = extract()
    OUT.write_text(json.dumps(out, indent=2) + "\n")
    print("checks: (a) value on cited page  (b) segments + eliminations = total  "
          "(c) external revenue total = revenue from operations  (d) external + inter-segment = segment revenue\n")
    print(f"{'report':<10} {'year':<10} {'chk':<3} {'value':>13}  ok  what")
    for rep, fy, c, what, v, ok in checks:
        print(f"{rep:<10} {fy:<10} {c:<3} {v:>13}  {'✓' if ok else '✗'}   {what}")
    for c in "abcd":
        cs = [x for x in checks if x[2] == c]
        print(f"check ({c}): {sum(x[-1] for x in cs)} of {len(cs)} passed")
    print(f"\npages: " + "; ".join(f"{rep} p{v[rep]['pdf_page']} ({v[rep]['page_label']})" for rep, v in out.items()))
    print(f"written to {OUT.relative_to(ROOT)}")
    print("unresolved:", "none" if not unresolved else "")
    for u in unresolved: print("  -", u)
