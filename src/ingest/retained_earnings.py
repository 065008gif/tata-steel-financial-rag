"""Extract the retained-earnings closing balance from the "Other equity" note of every report and scope.

For each report (FY2022-23..FY2025-26) and scope, finds the notes page(s) that contain the note "Other equity" with
the "A. Retained earnings" movement table, and parses that table only (up to "B. Items of other comprehensive income").
It keeps the "Balance at the end of the year" row for the report year and its comparative year.
Checks per column: opening balance + movements == closing balance (to 0.01 crore). Verification: the value, in Indian
format, must be present in the whitespace-normalised pymupdf text of its cited page; unverifiable values are left out.
Output: data/processed/retained_earnings.json
  {report: {scope: {fiscal_year: {value, pdf_page, page_label, method, verified_on_page}}}}
"""
import json, re
from pathlib import Path
import pymupdf

ROOT = Path(__file__).resolve().parents[2]
RAW, INTERIM, OUT = ROOT / "data/raw", ROOT / "data/interim", ROOT / "data/processed/retained_earnings.json"
REPORTS = ["FY2022-23", "FY2023-24", "FY2024-25", "FY2025-26"]
SCOPES = ["standalone", "consolidated"]
NUM = re.compile(r"^(\()?(\d{1,3}(?:,\d{2})*,?\d{0,3}\.\d{2})(\))?$|^-$")
YEAR_END = re.compile(r"March 31, (20\d\d)")
START = re.compile(r"movement in retained earnings", re.I)
END = re.compile(r"^B\.\s*$|^Items of other comprehensive income", re.I)
METHOD = ("Other equity note, A. Retained earnings movement table, 'Balance at the end of the year' row; "
          "column checked: opening + movements = closing")

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

def fy_of(year_end):
    y = int(year_end)
    return f"FY{y - 1}-{str(y)[2:]}"

def verified(doc, page, value):
    return inr(value) in norm(doc[page - 1].get_text())

def find_pages(doc, pmap, scope):
    """1-based notes pages of `scope` holding the Other equity note's retained-earnings movement table."""
    return [p["page"] for p in pmap if p["scope"] == scope and p["statement"] == "notes"
            and "Other equity" in (t := doc[p["page"] - 1].get_text()) and START.search(t)]

def parse(doc, page):
    """Parse the retained-earnings movement table starting on `page` (continuing onto the next page if needed).
    Returns ({fy: closing}, closing_page, problems)."""
    lines, owner = [], []
    for p in (page, page + 1):
        if p > len(doc): break
        for ln in doc[p - 1].get_text().splitlines():
            lines.append(ln.strip()); owner.append(p)
    i = next(k for k, ln in enumerate(lines) if START.search(ln))
    j = next((k for k in range(i + 1, len(lines)) if END.search(lines[k])), None)
    if j is None: return {}, None, ["end of the retained earnings table not found"]
    body, bowner = lines[i:j], owner[i:j]
    years = [fy_of(y) for y in YEAR_END.findall(" ".join(body[:12]))]
    if len(years) != 2: return {}, None, [f"expected 2 year columns, found {years}"]
    rows, label = [], []
    k = 0
    while k < len(body):
        a = num(body[k])
        if a is not None and k + 1 < len(body) and num(body[k + 1]) is not None:
            rows.append((" ".join(label), a, num(body[k + 1]), bowner[k])); label = []; k += 2
        else:
            if body[k] and not YEAR_END.search(body[k]): label.append(body[k])
            k += 1
    problems = []
    if not rows or not re.search(r"beginning of the year", rows[0][0], re.I):
        problems.append("first row is not the opening balance")
    closing = [r for r in rows if re.search(r"Balance at the end of the year", r[0], re.I)]
    if len(closing) != 1 or closing[0] is not rows[-1]:
        problems.append(f"expected one closing row at the end, found {len(closing)}")
    if problems: return {}, None, problems
    for c, fy in ((1, years[0]), (2, years[1])):
        total = sum(r[c] for r in rows[:-1])
        if abs(total - rows[-1][c]) > 0.011:
            problems.append(f"{fy}: opening + movements = {total:.2f} != closing {rows[-1][c]:.2f}")
    return {years[0]: rows[-1][1], years[1]: rows[-1][2]}, rows[-1][3], problems

def extract():
    out, table, unresolved = {}, [], []
    for rep in REPORTS:
        doc = pymupdf.open(RAW / f"TataSteel_{rep}.pdf")
        pmap = json.loads((INTERIM / f"page_map_{rep}.json").read_text())
        labels = {p["page"]: p["label"] for p in pmap}
        for scope in SCOPES:
            pages = find_pages(doc, pmap, scope)
            if len(pages) != 1:
                unresolved.append(f"{rep} {scope}: expected one retained-earnings page, found {pages}"); continue
            vals, cpage, problems = parse(doc, pages[0])
            if problems:
                unresolved.append(f"{rep} {scope}: " + "; ".join(problems)); continue
            for fy, v in vals.items():
                ok = verified(doc, cpage, v)
                table.append((rep, scope, fy, inr(v), labels.get(cpage), cpage, ok))
                if not ok:
                    unresolved.append(f"{rep} {scope} {fy}: {inr(v)} not found on page {cpage}"); continue
                out.setdefault(rep, {}).setdefault(scope, {})[fy] = {
                    "value": v, "pdf_page": cpage, "page_label": labels.get(cpage), "method": METHOD,
                    "verified_on_page": True}
    return out, table, unresolved

if __name__ == "__main__":
    out, table, unresolved = extract()
    OUT.write_text(json.dumps(out, indent=2) + "\n")
    print(f"{'report':<10} {'scope':<13} {'year':<10} {'value':>12}  {'page':<6} {'pdf_p':>5}  found")
    for rep, scope, fy, v, lab, p, ok in table:
        print(f"{rep:<10} {scope:<13} {fy:<10} {v:>12}  {lab or '-':<6} {p:>5}  {'✓' if ok else '✗'}")
    print(f"\n{sum(t[-1] for t in table)} of {len(table)} values verified; written to {OUT.relative_to(ROOT)}")
    print("unresolved:", "none" if not unresolved else "")
    for u in unresolved: print("  -", u)
