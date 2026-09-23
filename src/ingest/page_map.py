"""Stage 1: classify every page of each annual report by section, scope and statement type.

Reads text by visual position (top and bottom strips of each page), because the PDF's
internal text order does not match the visual order in older reports.
Writes data/interim/page_map_<FY>.json and prints a summary per report.
"""
import json, re, glob
from pathlib import Path
import pymupdf

OUT = Path("data/interim"); OUT.mkdir(parents=True, exist_ok=True)

# Checked in order against the page's top strip only. Notes first, because a notes page
# can mention statement names; cash flow also matches its first line item, since some
# years place the title outside the top strip.
TITLES = [
    ("auditor_report", r"independent auditor.s report"),
    ("notes", r"notes forming part of the"),
    ("balance_sheet", r"balance sheet as at"),
    ("profit_and_loss", r"statement of profit and loss"),
    ("changes_in_equity", r"statement of changes in equity"),
    ("cash_flow", r"statement of cash flows|cash flows from operating activities"),
]
STATEMENTS = {"balance_sheet", "profit_and_loss", "changes_in_equity", "cash_flow", "notes"}
LABEL = re.compile(r"^(?:\d{1,3}\s+)?F(\d{1,3})\b")

def norm(s):
    return " ".join(s.split())

def zones(page):
    """Return (title text, footer text, full page text), read by visual position.

    Title: short blocks in the top 16% of the page (tall blocks are merged tables, ignored).
    Footer: blocks in the bottom 6%, where every year prints the running footer and F-label.
    """
    h = page.rect.height
    blocks = sorted(page.get_text("blocks"), key=lambda b: (b[1], b[0]))
    title = " ".join(norm(b[4]) for b in blocks if b[1] < h * 0.16 and (b[3] - b[1]) < 50)
    footer = " ".join(norm(b[4]) for b in blocks if b[1] > h * 0.94)
    full = norm(" ".join(b[4] for b in blocks))
    return title, footer, full

def classify(pdf_path):
    doc = pymupdf.open(pdf_path)
    pages, scope, current = [], None, None
    for i, page in enumerate(doc):
        title, footer, full = zones(page)
        head, low = title.lower(), full.lower()
        m = re.search(r"\bF(\d{1,3})\b", footer)
        label = f"F{m.group(1)}" if m else None
        if label:
            section = "financial_statements"
        elif "statutory reports" in (head + " " + footer.lower()):
            section = "statutory_reports"
        else:
            section = "integrated_report"
        statement, page_scope = None, None
        if section == "financial_statements":
            if "report on the audit of the consolidated financial statements" in low:
                scope = "consolidated"
            found = next((name for name, pat in TITLES if re.search(pat, head)), None)
            current = found or current or "fs_other"
            statement = current
            page_scope = scope or ("standalone" if statement in STATEMENTS or statement == "auditor_report" else None)
        pages.append(dict(page=i + 1, label=label, section=section, scope=page_scope, statement=statement))
    return pages

for path in sorted(glob.glob("data/raw/*.pdf")):
    fy = Path(path).stem.split("_")[-1]
    pages = classify(path)
    (OUT / f"page_map_{fy}.json").write_text(json.dumps(pages, indent=1))
    counts = {}
    for p in pages:
        counts[p["section"]] = counts.get(p["section"], 0) + 1
    print(f"\n{fy}: {len(pages)} pages | " + ", ".join(f"{k}={v}" for k, v in counts.items()))
    runs = []
    for p in pages:
        if p["section"] != "financial_statements":
            continue
        key = (p["scope"], p["statement"])
        if runs and runs[-1][0] == key:
            runs[-1][2], runs[-1][4] = p["page"], p["label"]
        else:
            runs.append([key, p["page"], p["page"], p["label"], p["label"]])
    for (scope, stmt), a, b, la, lb in runs:
        print(f"  {str(scope):13} {stmt:18} pages {a}-{b}  ({la}-{lb})")
