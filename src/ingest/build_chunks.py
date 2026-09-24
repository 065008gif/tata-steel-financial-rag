"""Stage 4: build retrieval chunks from all four reports.

  statement_table - each primary statement page as a clean markdown table, from verified line items
  note_table      - Docling tables from notes / auditor report / other FS pages, tagged with note title
  fs_text         - narrative paragraphs inside the FS section (policies, key audit matters, contingencies)
  narrative       - integrated report and statutory report pages (MD&A, risk, strategy, Directors' Report)
Output: data/processed/chunks.jsonl
"""
import json, re
from collections import defaultdict, Counter
from pathlib import Path
import pymupdf
from docling_core.types.doc import DoclingDocument, TableItem, TextItem, SectionHeaderItem

INTERIM, PROC = Path("data/interim"), Path("data/processed")
PRIMARY = {"balance_sheet", "profit_and_loss", "cash_flow"}
NOTE_TITLE = re.compile(r"^\d{1,2}[A-Z]?\.\s+\S")
NOISE = re.compile(r"^(?:\d{1,3}\s*)?F\d{1,3}$|annual accounts 20\d\d|^financial statements$|^notes forming part", re.I)
MAX_WORDS, TABLE_ROWS = 450, 40
TOPICS = [("risk", r"\brisk"), ("mdna", r"management discussion|md&a"), ("directors_report", r"board.s report|directors.? report"),
          ("governance", r"corporate governance"), ("sustainability", r"sustainab|brsr|climate|emission|decarboni"),
          ("strategy", r"strateg|outlook|capital allocation"), ("segments", r"netherlands|united kingdom|\buk\b|thailand|segment")]

def prior(fy): y = int(fy[2:6]); return f"FY{y - 1}-{str(y)[2:]}"
def topics(s): s = s.lower(); return [k for k, rx in TOPICS if re.search(rx, s)] or ["general"]
def narrative_topics(title, text):
    t = topics(title + " " + text[:400])
    if "risk" in t and not re.search(r"risk", title, re.I) and text.lower().count("risk") < 3: t.remove("risk")
    return t or ["general"]

def inr(v):
    i, d = f"{abs(v):.2f}".split(".")
    if len(i) > 3:
        head, parts = i[:-3], []
        while len(head) > 2: parts.insert(0, head[-2:]); head = head[:-2]
        if head: parts.insert(0, head)
        i = ",".join(parts + [i[-3:]])
    return ("-" if v < 0 else "") + i + "." + d

chunks = []

# 1) statement_table chunks from verified line items
recs = [json.loads(l) for l in open(PROC / "line_items.jsonl")]
groups = defaultdict(list)
for r in recs: groups[(r["report"], r["scope"], r["statement"], r["page"], r["page_label"])].append(r)
for (rep, sc, st, pg, lab), rs in groups.items():
    years = sorted({r["fiscal_year"] for r in rs}, reverse=True)
    rows = {}
    for r in rs: rows.setdefault((r["path"], r["line_item"]), {})[r["fiscal_year"]] = r["value"]
    flag = " | contains restated comparatives" if any(r["differs_from_original"] or r["restated"] for r in rs) else ""
    lines = [f"Tata Steel | {sc.title()} {st.replace('_', ' ').title()} | {rep} Annual Report | page {lab} (PDF p{pg}) | Rs crore{flag}", "",
             "| Line item | " + " | ".join(years) + " |", "|" + "---|" * (len(years) + 1)]
    for (path, item), vals in rows.items():
        lines.append(f"| {(path + ' > ' if path else '') + item} | " + " | ".join(inr(vals[y]) if y in vals else "" for y in years) + " |")
    chunks.append(dict(type="statement_table", report=rep, fiscal_years=years, scope=sc, section=st, note="",
                       topics=["financials"], page=pg, page_label=lab, text="\n".join(lines)))

for path in sorted(INTERIM.glob("docling_FY*.json")):
    rep = path.stem.split("_")[1]
    pm = {p["page"]: p for p in json.loads((INTERIM / f"page_map_{rep}.json").read_text())}

    # 2) note_table and 3) fs_text chunks from Docling
    doc = DoclingDocument.load_from_json(path)
    note, sub, last_stmt, paras = "", "", None, []
    scope_name = lambda m: (m.get("scope") or "standalone & group").title()
    for item, _ in doc.iterate_items():
        if not getattr(item, "prov", None): continue
        pg = item.prov[0].page_no
        meta = pm.get(pg, {})
        stmt = meta.get("statement")
        if stmt in PRIMARY: continue
        if stmt != last_stmt: note, sub, last_stmt = "", "", stmt
        if isinstance(item, TableItem):
            md = item.export_to_markdown(doc=doc).replace("(I crore)", "(Rs crore)")
            if len(md) < 40 or not re.search(r"\d", md) or "sd/-" in md or "DIN:" in md: continue
            label = " > ".join(x for x in (note, sub) if x)
            head = (f"Tata Steel | {scope_name(meta)} {stmt} | {label} | {rep} Annual Report | "
                    f"page {meta.get('label')} (PDF p{pg}) | Rs crore unless stated")
            tl = md.split("\n")
            for i in range(0, max(1, len(tl) - 2), TABLE_ROWS):
                part = "\n".join(tl[:2] + tl[2 + i: 2 + i + TABLE_ROWS])
                chunks.append(dict(type="note_table", report=rep, fiscal_years=[rep, prior(rep)], scope=meta.get("scope"),
                                   section=stmt, note=label, topics=["financials"], page=pg,
                                   page_label=meta.get("label"), text=head + "\n\n" + part))
        elif isinstance(item, TextItem):
            t = " ".join(item.text.split())
            if not t or NOISE.search(t): continue
            if stmt == "notes" and NOTE_TITLE.match(t) and len(t) < 120:
                note, sub = re.sub(r"\s*\(contd\.?\)", "", t, flags=re.I), ""
            elif isinstance(item, SectionHeaderItem):
                sub, t = re.sub(r"\s*\(contd\.?\)", "", t, flags=re.I), "## " + t
            paras.append((note, stmt, pg, meta, t, sub))
    buf, words = [], 0
    def flush():
        global buf, words
        n_words = sum(len(b[4].split()) for b in buf)
        if buf and n_words >= 12:
            n, st, pg0, m = buf[0][0], buf[0][1], buf[0][2], buf[0][3]
            label = n or next((b[5] for b in buf if b[5]), "")
            body = " ".join(b[4] for b in buf)
            chunks.append(dict(type="fs_text", report=rep, fiscal_years=[rep, prior(rep)], scope=m.get("scope"),
                               section=st, note=label, topics=topics(label + " " + body[:400]), page=pg0,
                               page_label=m.get("label"),
                               text=f"Tata Steel | {scope_name(m)} {st} | {label} | {rep} Annual Report | "
                                    f"page {m.get('label')} (PDF p{pg0})\n\n{body}"))
        buf, words = [], 0
    for p in paras:
        if buf and ((p[0], p[1]) != (buf[0][0], buf[0][1]) or words > MAX_WORDS): flush()
        buf.append(p); words += len(p[4].split())
    flush()

    # 4) narrative chunks from non-FS pages (PyMuPDF, visual reading order)
    pdf = pymupdf.open(f"data/raw/TataSteel_{rep}.pdf")
    for p in pm.values():
        if p["section"] == "financial_statements": continue
        page = pdf[p["page"] - 1]
        w = " ".join(b[4] for b in page.get_text("blocks")).split()
        if len(w) < 40: continue
        h = page.rect.height
        title = " ".join(" ".join(b[4].split()) for b in sorted(page.get_text("blocks"), key=lambda b: (b[1], b[0]))
                         if b[1] < h * 0.16 and (b[3] - b[1]) < 50)[:150]
        for i in range(0, len(w), MAX_WORDS):
            piece = " ".join(w[i:i + MAX_WORDS + 50])
            chunks.append(dict(type="narrative", report=rep, fiscal_years=[rep], scope=None, section=p["section"], note=title,
                               topics=narrative_topics(title, piece), page=p["page"], page_label=None,
                               text=f"Tata Steel | {rep} Annual Report | {p['section'].replace('_', ' ')} | {title} | PDF p{p['page']}\n\n{piece}"))

for i, c in enumerate(chunks): c["chunk_id"] = i
with open(PROC / "chunks.jsonl", "w") as f:
    for c in chunks: f.write(json.dumps(c) + "\n")

print(f"{len(chunks)} chunks written to data/processed/chunks.jsonl\n")
cnt = Counter((c["report"], c["type"]) for c in chunks)
for rep in sorted({c["report"] for c in chunks}):
    print(f"  {rep}: " + ", ".join(f"{t}={cnt[(rep, t)]}" for t in ("statement_table", "note_table", "fs_text", "narrative")))
wl = [len(c["text"].split()) for c in chunks]
print(f"\nWords per chunk: min {min(wl)}, median {sorted(wl)[len(wl)//2]}, max {max(wl)}")
print(f"Note tables with a note title: {sum(1 for c in chunks if c['type']=='note_table' and c['note'])}/{sum(1 for c in chunks if c['type']=='note_table')}")
print(f"Narrative chunks tagged 'risk': {sum(1 for c in chunks if c['type']=='narrative' and 'risk' in c['topics'])}")
samples = [
    ("statement_table", lambda c: c["type"] == "statement_table"),
    ("note_table: consolidated borrowings", lambda c: c["type"] == "note_table" and c["scope"] == "consolidated" and "borrowing" in c["note"].lower()),
    ("fs_text: consolidated key audit matters", lambda c: c["type"] == "fs_text" and c["scope"] == "consolidated" and c["section"] == "auditor_report" and "key audit matter" in c["text"].lower()),
    ("narrative: risk", lambda c: c["type"] == "narrative" and "risk" in c["topics"]),
]
for name, cond in samples:
    c = next((c for c in chunks if c["report"] == "FY2025-26" and cond(c)), None)
    print(f"\n===== SAMPLE {name} =====\n" + (c["text"][:600] if c else "NOT FOUND"))
notes = sorted({c["note"] for c in chunks if c["report"] == "FY2025-26" and c["scope"] == "consolidated" and c["type"] == "note_table"})
print(f"\nFY2025-26 consolidated note-table titles ({len(notes)} distinct), first 15:")
for n in notes[:15]: print("  ", n[:100])
