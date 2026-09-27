"""'About Tata Steel' facts for the Home page, from the corporate overview pages of the FY2025-26 report.

Each statement is written in plain words from one PDF page and cites it (report, printed page label, 1-based PDF
page, local URL). The overview pages are two-page spreads, so the printed label is the pair printed on the spread
(e.g. "10-11"); the pair must appear on the page. Verification: every number (digits, with a trailing "+" if written)
and every proper noun (capitalised word not opening a sentence, plus acronyms) in a statement must appear in the
whitespace-normalised pymupdf text of its cited page. A ✓/✗ table is printed; a statement with any ✗ is dropped.
No forward-looking claims (targets, plans, "will").
Output: data/processed/company.json
"""
import json, re, sys
from pathlib import Path
import pymupdf

ROOT = Path(__file__).resolve().parents[2]
REPORT = "FY2025-26"
PDF = ROOT / "data/raw" / f"TataSteel_{REPORT}.pdf"
OUT = ROOT / "data/processed/company.json"

FACTS = [  # (statement, pdf_page, printed page label of the spread)
    ("Tata Steel is a globally diversified integrated steel producer with a combined steelmaking capacity of 36 MTPA "
     "across India, the Netherlands, the UK and Thailand.", 8, "10-11"),
    ("In India it makes steel at Jamshedpur and Gamharia in Jharkhand, Kalinganagar and Meramandali in Odisha, and at "
     "an Electric Arc Furnace (EAF) plant in Ludhiana, Punjab, and it runs captive coal, iron ore, chromite and "
     "manganese mines.", 9, "12-13"),
    ("Tata Steel Nederland makes flat steel at IJmuiden (7 MTPA) for automotive, construction, packaging and heavy "
     "equipment customers; Tata Steel Thailand runs three EAF plants with a combined capacity of 1.7 MTPA.", 9, "12-13"),
    ("It has 77,000+ employees across the globe, and Tata Steel Minerals Canada operates iron ore assets in Labrador "
     "and Northern Quebec, Canada.", 9, "12-13"),
    ("In the year covered by the 2025-26 report, Tata Steel Consolidated produced 31.67 MT of steel and delivered "
     "31.97 MT, with a turnover of ₹2,32,140 crore and EBITDA of ₹34,848 crore.", 5, "4-5"),
]
FORWARD = re.compile(r"\b(will|plans?|target(?:s|ed)?|aims?|expects?|intends?|going to|by 20\d\d)\b", re.I)
SKIP = {"In", "It", "The", "A", "An", "With", "Its", "And"}   # ordinary words when they open a sentence or clause
NUM_WORDS = r"\b(?:one|two|three|four|five|six|seven|eight|nine|ten|eleven|twelve)\b"

def norm(s):
    return re.sub(r"\s+", " ", s).replace("‑", "-").strip()

def tokens(statement):
    """Numbers and proper nouns that must be found on the page."""
    nums = re.findall(r"\d{4}-\d{2}|\d[\d,]*(?:\.\d+)?\+?", statement) + re.findall(NUM_WORDS, statement, re.I)
    names = [w for w in re.findall(r"\b[A-Z][A-Za-z]*\b", statement) if w not in SKIP]
    return list(dict.fromkeys(nums)), list(dict.fromkeys(names))

def on_page(tok, text):
    if tok.isalpha(): return re.search(rf"\b{tok}\b", text, re.I) is not None     # number words ("three")
    return re.search(rf"(?<![\w.,]){re.escape(tok)}(?![\w]|[.,]\d)", text) is not None

def build():
    doc = pymupdf.open(PDF)
    rows, facts = [], []
    for statement, pg, label in FACTS:
        text = norm(doc[pg - 1].get_text())
        a, b = label.split("-")
        checks = [(f"page label {label}", bool(re.search(rf"\b(?:{a} {b}|{b} {a})\b", text)))]
        nums, names = tokens(statement)
        checks += [(t, on_page(t, text)) for t in nums + names]
        checks.append(("no forward-looking wording", not FORWARD.search(statement)))
        ok = all(c for _, c in checks)
        rows.append((statement, pg, label, checks, ok))
        if ok:
            facts.append({"text": statement, "report": REPORT, "page_label": label, "pdf_page": pg,
                          "url": f"/api/pdf/{REPORT}#page={pg}"})
    return facts, rows

if __name__ == "__main__":
    facts, rows = build()
    for i, (statement, pg, label, checks, ok) in enumerate(rows, 1):
        print(f"\n[{i}] {'✓ kept' if ok else '✗ dropped'}  (PDF p{pg}, printed pages {label})\n    {statement}")
        for t, c in checks: print(f"      {'✓' if c else '✗'} {t}")
    print(f"\n{len(facts)} of {len(rows)} statements verified")
    if not 3 <= len(facts) <= 5: sys.exit("expected 3-5 verified statements; company.json not written")
    OUT.write_text(json.dumps({"title": "About Tata Steel", "source": f"{REPORT} Integrated Report & Annual Accounts, "
                               "corporate overview (Highlights of the Year, Corporate Portrait)", "facts": facts}, indent=2,
                              ensure_ascii=False) + "\n")
    print(f"written to {OUT.relative_to(ROOT)}")
