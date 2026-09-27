"""Regions for the Dashboard region filter, built from the segment data (src/analysis/segments.py).

A region is the sum of one or more reported segments, each year taken from the latest report presenting it:
  india            Tata Steel India + Neelachal Ispat Nigam + Other Indian Operations + Tata Steel Long Products (where present)
  netherlands      Tata Steel Netherlands operations (from FY2024-25)
  uk               Tata Steel UK operations (from FY2024-25)
  europe           Tata Steel Europe (until FY2023-24, before the split into Netherlands and UK)
  south_east_asia  South-East Asian operations
  rest_of_world    Rest of the world
  trading          Other trade related operations
Per region and year: segment_revenue, external_revenue, ebitda (segment results), ebitda_margin_pct
(= ebitda / segment_revenue x 100), share_of_group_external_revenue_pct and share_of_group_ebitda_pct (group totals =
the Total column of the segment note), the component segments, sources and restated flags. A year in which none of
a region's segments was reported is absent (never zero). All arithmetic is done here, never in the frontend.
Reconciliation: regions + inter-segment eliminations = the printed Total, per item and year (`reconcile`).
"""
import segments as SEG

REGIONS = [  # key, name, component segment keys
    ("india", "India", ["tata_steel_india", "neelachal_ispat_nigam", "other_indian_operations", "tata_steel_long_products"]),
    ("netherlands", "Netherlands", ["tata_steel_netherlands"]),
    ("uk", "United Kingdom", ["tata_steel_uk"]),
    ("europe", "Europe (Tata Steel Europe, until FY2023-24)", ["tata_steel_europe"]),
    ("south_east_asia", "South-East Asia", ["south_east_asian_operations"]),
    ("rest_of_world", "Rest of the world", ["rest_of_the_world"]),
    ("trading", "Other trade related operations", ["other_trade_related_operations"])]
ITEMS = [("segment_revenue", "segment_revenue"), ("external_revenue", "external_revenue"), ("ebitda", "segment_results")]

def _pdf_url(report, pdf_page=None):
    return f"/api/pdf/{report}" + (f"#page={pdf_page}" if pdf_page else "")

def _pct(a, b):
    return None if a is None or not b else round(a / b * 100, 2)

def get_regions(data=None):
    """{"unit", "years", "note", "regions": [{key, name, segments, values: {fy: {...}}}], "group_totals", "reconciliation"}"""
    r = SEG.get_segments(items=["external_revenue", "segment_revenue", "segment_results"], data=data)
    by_key = {s["key"]: s for s in r["segments"]}
    totals = r["totals"]["values"]
    elim = (r["eliminations"] or {}).get("values", {})
    regions = []
    for key, name, comps in REGIONS:
        values = {}
        for fy in r["years"]:
            present = [c for c in comps if fy in by_key.get(c, {}).get("values", {})]
            if not present: continue                          # region did not exist that year: absent, not zero
            cells = {c: by_key[c]["values"][fy] for c in present}
            row = {}
            for out, src in ITEMS:
                vs = [cells[c][src]["value"] for c in present if src in cells[c]]
                row[out] = round(sum(vs), 2) if len(vs) == len(present) else None
            tot = totals.get(fy, {})
            row["ebitda_margin_pct"] = _pct(row["ebitda"], row["segment_revenue"])
            row["share_of_group_external_revenue_pct"] = _pct(row["external_revenue"], tot.get("external_revenue", {}).get("value"))
            row["share_of_group_ebitda_pct"] = _pct(row["ebitda"], tot.get("segment_results", {}).get("value"))
            row["components"] = [{"key": c, "name": by_key[c]["name"],
                                  **{out: cells[c][src]["value"] for out, src in ITEMS if src in cells[c]}} for c in present]
            srcs = {(v["report"], v["page_label"], v["pdf_page"]) for c in present for v in cells[c].values()}
            row["sources"] = [{"report": rep, "page_label": lab, "pdf_page": pg, "url": _pdf_url(rep, pg)}
                              for rep, lab, pg in sorted(srcs)]
            restated = {c: [out for out, src in ITEMS if cells[c].get(src, {}).get("restated")] for c in present}
            row["restated"] = {c: its for c, its in restated.items() if its}
            values[fy] = row
        if values:
            regions.append({"key": key, "name": name, "segments": comps, "values": values})
    group = {fy: {"segment_revenue": t.get("segment_revenue", {}).get("value"),
                  "external_revenue": t.get("external_revenue", {}).get("value"),
                  "ebitda": t.get("segment_results", {}).get("value"),
                  "eliminations": {out: elim.get(fy, {}).get(src, {}).get("value") for out, src in ITEMS}}
             for fy, t in totals.items()}
    return {"unit": "INR crore", "years": r["years"],
            "note": "EBITDA = segment results before exceptional items, interest, tax and depreciation. Group totals are "
                    "the Total column of the consolidated segment note, after inter-segment eliminations, so regional "
                    "EBITDA shares need not add up to 100%. Each year from the latest report presenting it.",
            "regions": regions, "group_totals": group, "reconciliation": reconcile(regions, group, r["years"])}

def reconcile(regions, group, years):
    """Per year and item: sum of regions + eliminations vs the printed Total (to 0.01)."""
    out = {}
    for fy in years:
        row = {}
        for out_key, _ in ITEMS:
            vals = [g["values"][fy][out_key] for g in regions if fy in g["values"]]
            total, el = group.get(fy, {}).get(out_key), group.get(fy, {}).get("eliminations", {}).get(out_key)
            if total is None or any(v is None for v in vals):
                row[out_key] = {"ok": None}; continue
            s = round(sum(vals) + (el or 0.0), 2)
            row[out_key] = {"regions_sum": round(sum(vals), 2), "eliminations": el, "sum": s, "total": total,
                            "ok": abs(s - total) <= 0.011}
        out[fy] = row
    return out
