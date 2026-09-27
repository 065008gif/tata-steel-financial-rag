"""Segment revenue and results for every year, from data/processed/segments.json (src/ingest/segments.py).

Each year is taken from the LATEST report that presents it (the prior-year column of a report is restated where the
segment structure changed). Segments are matched across reports by their normalised key only; a segment that exists
in some years only (Tata Steel Long Products, Tata Steel Europe before its split into Netherlands and UK) is kept as
its own segment and never mapped onto another one. A value is flagged `restated` when the same segment key, year and
item is printed with a different value in another report; the other reports' values are listed in `as_reported`.
Segment-years printed only in an older report (e.g. Tata Steel Europe FY2024-25, later split) go to `superseded`.
Segment "results" are segment EBITDA: results before exceptional items, interest, tax and depreciation.
"""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DATA = ROOT / "data/processed/segments.json"
YEARS = ["FY2021-22", "FY2022-23", "FY2023-24", "FY2024-25", "FY2025-26"]
ITEMS = ["external_revenue", "inter_segment_revenue", "segment_revenue", "segment_results"]
ITEM_LABELS = {"external_revenue": "External revenue", "inter_segment_revenue": "Inter-segment revenue",
               "segment_revenue": "Segment revenue (total)",
               "segment_results": "Segment results (EBITDA before exceptional items)"}
TOL = 0.005

def load(path=DATA):
    return json.loads(Path(path).read_text())

def _columns(rec):
    """(key, name, {item: value}) for every column of one report-year, totals and eliminations included."""
    cols = [(v["key"], name, {i: v[i] for i in ITEMS if i in v}) for name, v in rec["segments"].items()]
    if rec.get("eliminations"): cols.append(("eliminations", rec.get("eliminations_name", "Inter-segment eliminations"), rec["eliminations"]))
    cols.append(("total", "Total", rec.get("totals", {})))
    return cols

def get_segments(fiscal_years=None, items=None, data=None):
    """{"years", "items", "unit", "segments": [{key, name, values: {fy: {item: {value, report, page_label, pdf_page,
    restated, as_reported?}}}}], "totals": {...same shape...}, "eliminations": {...}, "superseded": [...]}"""
    data = load() if data is None else data
    fys = [fy for fy in YEARS if not fiscal_years or fy in fiscal_years]
    its = [i for i in ITEMS if not items or i in items]
    reports = sorted(data)
    seen = {}                                  # (key, fy, item) -> {report: value}, from every report
    for rep in reports:
        for fy, rec in data[rep].items():
            for key, _, vals in _columns(rec):
                for i, v in vals.items(): seen.setdefault((key, fy, i), {})[rep] = v
    rows, order = {}, []
    for fy in reversed(fys):                   # latest year first: its report's column order and names lead
        rep = next((r for r in reversed(reports) if fy in data[r]), None)
        if rep is None: continue
        rec = data[rep][fy]
        for key, name, vals in _columns(rec):
            if key not in rows:                # name as printed in the latest report that has this segment
                rows[key] = {"key": key, "name": name, "values": {}}; order.append(key)
            cell = {}
            for i in its:
                if i not in vals: continue
                others = {r: v for r, v in seen[(key, fy, i)].items() if r != rep}
                changed = {r: v for r, v in others.items() if abs(v - vals[i]) > TOL}
                cell[i] = {"value": vals[i], "report": rep, "page_label": rec["page_label"], "pdf_page": rec["pdf_page"],
                           "restated": bool(changed)}
                if changed: cell[i]["as_reported"] = changed
            if cell: rows[key]["values"][fy] = cell
    for r in rows.values(): r["values"] = {fy: r["values"][fy] for fy in fys if fy in r["values"]}
    segs = [rows[k] for k in order if k not in ("total", "eliminations")]
    superseded = []                            # segment-years an older report printed but the latest one no longer has
    for fy in fys:
        latest = next((r for r in reversed(reports) if fy in data[r]), None)
        for rep in reports:
            if rep == latest or fy not in data[rep]: continue
            for key, name, vals in _columns(data[rep][fy]):
                if fy in rows.get(key, {}).get("values", {}): continue
                superseded.append({"key": key, "name": name, "fiscal_year": fy, "report": rep,
                                   "page_label": data[rep][fy]["page_label"], "pdf_page": data[rep][fy]["pdf_page"],
                                   "values": {i: vals[i] for i in its if i in vals}, "latest_report": latest})
    return {"years": fys, "items": its, "unit": "INR crore",
            "note": "Segment results = segment EBITDA (before exceptional items, interest, tax and depreciation). "
                    "Each year from the latest report presenting it.",
            "segments": segs, "eliminations": rows.get("eliminations"), "totals": rows.get("total"),
            "superseded": superseded}
