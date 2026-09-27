"""Tests for segment extraction (src/ingest/segments.py), get_segments (src/analysis/segments.py), the agent tool and
GET /api/segments: known values, checks (a)-(c) for every report, restated-flag logic, no NaN."""
import importlib.util, json, math, sys, types
from pathlib import Path
import pymupdf
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src" / "analysis"))
import segments as SA

_spec = importlib.util.spec_from_file_location("ingest_segments", ROOT / "src/ingest/segments.py")
SI = importlib.util.module_from_spec(_spec); _spec.loader.exec_module(SI)

DATA = json.loads((ROOT / "data/processed/segments.json").read_text())
FIN = json.loads((ROOT / "data/processed/financials_by_report.json").read_text())
REPORTS = ["FY2022-23", "FY2023-24", "FY2024-25", "FY2025-26"]

def _seg(rep, fy, key):
    return next(v for v in DATA[rep][fy]["segments"].values() if v["key"] == key)

def _walk(x):
    if isinstance(x, dict):
        for v in x.values(): yield from _walk(v)
    elif isinstance(x, list):
        for v in x: yield from _walk(v)
    else: yield x

# ---------- known values (FY2025-26 report, page F256) ----------
def test_known_values_fy2025_26_report():
    r = DATA["FY2025-26"]
    assert r["FY2025-26"]["page_label"] == "F256" and r["FY2025-26"]["pdf_page"] == 534
    assert r["FY2025-26"]["totals"]["external_revenue"] == 232139.94
    assert r["FY2024-25"]["totals"]["external_revenue"] == 218542.51
    for fy, want in {"FY2025-26": {"tata_steel_india": 33035.63, "tata_steel_netherlands": 2721.52, "tata_steel_uk": -2568.99},
                     "FY2024-25": {"tata_steel_india": 28217.36, "tata_steel_netherlands": 825.38, "tata_steel_uk": -4134.20}}.items():
        for key, v in want.items(): assert _seg("FY2025-26", fy, key)["segment_results"] == v
    assert r["FY2025-26"]["totals"]["segment_results"] == 34847.73
    assert r["FY2024-25"]["totals"]["segment_results"] == 25801.80

def test_every_report_and_both_years_present():
    for rep in REPORTS:
        prior = f"FY{int(rep[2:6]) - 1}-{rep[4:6]}"
        assert set(DATA[rep]) == {rep, prior}
        for rec in DATA[rep].values():
            assert rec["segments"] and rec["totals"]["segment_results"] and rec["totals"]["external_revenue"]

def test_segments_kept_as_printed_not_merged():
    assert {v["key"] for v in DATA["FY2022-23"]["FY2021-22"]["segments"].values()} >= {"tata_steel_long_products", "tata_steel_europe"}
    assert "tata_steel_europe" in {v["key"] for v in DATA["FY2024-25"]["FY2024-25"]["segments"].values()}
    keys25 = {v["key"] for v in DATA["FY2025-26"]["FY2024-25"]["segments"].values()}
    assert {"tata_steel_netherlands", "tata_steel_uk"} <= keys25 and "tata_steel_europe" not in keys25

# ---------- checks (a)-(c) for all reports ----------
@pytest.mark.parametrize("rep", REPORTS)
def test_a_values_on_cited_page(rep):
    doc = pymupdf.open(ROOT / f"data/raw/TataSteel_{rep}.pdf")
    for fy, rec in DATA[rep].items():
        text = SI.norm(doc[rec["pdf_page"] - 1].get_text())
        assert rec["page_label"] in text
        cols = list(rec["segments"].values()) + [rec["totals"], rec["eliminations"]]
        for col in cols:
            for item in SI.ITEMS:
                if item in col and col[item] != 0: assert SI.inr(col[item]) in text, (rep, fy, item, col[item])

@pytest.mark.parametrize("rep", REPORTS)
def test_b_segments_plus_eliminations_equal_total(rep):
    for fy, rec in DATA[rep].items():
        for item in SI.ITEMS:
            if item not in rec["totals"]: continue
            s = sum(v.get(item, 0.0) for v in rec["segments"].values()) + rec["eliminations"].get(item, 0.0)
            assert abs(s - rec["totals"][item]) <= 0.011, (rep, fy, item)

@pytest.mark.parametrize("rep", REPORTS)
def test_c_external_revenue_equals_revenue_from_operations(rep):
    for fy, rec in DATA[rep].items():
        ref = FIN[rep]["consolidated"]["revenue_from_operations"]["values"][fy]["value"]
        assert abs(rec["totals"]["external_revenue"] - ref) <= 0.01, (rep, fy)

def test_extraction_reruns_clean():
    out, checks, unresolved = SI.extract()
    assert out == DATA
    assert checks and all(c[-1] for c in checks)
    assert {c[2] for c in checks} == {"a", "b", "c", "d"}
    assert unresolved == ["FY2023-24 FY2022-23 inter_segment_revenue: total cell blank on page F250 - no total to check"]

# ---------- get_segments: latest report per year, restated flag ----------
def test_latest_report_used_per_year():
    r = SA.get_segments()
    assert r["years"] == SA.YEARS
    tsi = next(s for s in r["segments"] if s["key"] == "tata_steel_india")["values"]
    assert {fy: c["segment_results"]["report"] for fy, c in tsi.items()} == {
        "FY2021-22": "FY2022-23", "FY2022-23": "FY2023-24", "FY2023-24": "FY2024-25", "FY2024-25": "FY2025-26", "FY2025-26": "FY2025-26"}
    assert tsi["FY2022-23"]["segment_results"]["value"] == 28753.76 and tsi["FY2022-23"]["segment_results"]["page_label"] == "F250"
    assert r["totals"]["values"]["FY2025-26"]["segment_results"]["value"] == 34847.73

def test_restated_flag_real_data():
    r = SA.get_segments()
    tsi = next(s for s in r["segments"] if s["key"] == "tata_steel_india")["values"]
    c = tsi["FY2022-23"]["segment_results"]
    assert c["restated"] and c["as_reported"] == {"FY2022-23": 28174.58}
    assert not tsi["FY2024-25"]["segment_results"]["restated"]               # 28,217.36 in both reports
    assert not tsi["FY2021-22"]["segment_results"]["restated"]               # only one report has it
    sup = {(x["key"], x["fiscal_year"]) for x in r["superseded"]}
    assert sup == {("tata_steel_europe", "FY2024-25"), ("tata_steel_long_products", "FY2022-23")}

def _rec(val, label):
    return {"segments": {"Seg A": {"key": "seg_a", "segment_results": val}, "Seg B": {"key": "seg_b", "segment_results": 1.0}},
            "totals": {"segment_results": val + 1.0}, "eliminations": {}, "pdf_page": 1, "page_label": label}

def test_restated_flag_synthetic():
    data = {"FY2024-25": {"FY2024-25": _rec(10.0, "F1"), "FY2023-24": _rec(5.0, "F1")},
            "FY2025-26": {"FY2025-26": _rec(20.0, "F2"), "FY2024-25": _rec(12.5, "F2")}}
    data["FY2025-26"]["FY2024-25"]["segments"]["Seg B"]["segment_results"] = 1.0
    r = SA.get_segments(data=data)
    a = next(s for s in r["segments"] if s["key"] == "seg_a")["values"]
    b = next(s for s in r["segments"] if s["key"] == "seg_b")["values"]
    assert a["FY2024-25"]["segment_results"] == {"value": 12.5, "report": "FY2025-26", "page_label": "F2", "pdf_page": 1,
                                                 "restated": True, "as_reported": {"FY2024-25": 10.0}}
    assert not a["FY2025-26"]["segment_results"]["restated"] and not a["FY2023-24"]["segment_results"]["restated"]
    assert not b["FY2024-25"]["segment_results"]["restated"]
    assert r["totals"]["values"]["FY2024-25"]["segment_results"]["restated"]
    assert set(r["years"]) == set(SA.YEARS) and "FY2021-22" not in a

def test_filters():
    r = SA.get_segments(["FY2025-26"], ["segment_results"])
    assert r["years"] == ["FY2025-26"] and r["items"] == ["segment_results"]
    assert all(set(s["values"]) <= {"FY2025-26"} and all(set(v) == {"segment_results"} for v in s["values"].values())
               for s in r["segments"])

# ---------- no NaN ----------
def test_no_nan():
    for data in (DATA, SA.get_segments()):
        for v in _walk(data):
            if isinstance(v, float): assert math.isfinite(v)

# ---------- agent tool and API endpoint (retrieval and LLM modules stubbed: no Qdrant, no model calls) ----------
@pytest.fixture
def stubbed(monkeypatch):
    monkeypatch.setitem(sys.modules, "search", types.SimpleNamespace(search=lambda *a, **k: [], client=None, COLL="x"))
    monkeypatch.setitem(sys.modules, "agent", types.SimpleNamespace(MODELS=["stub"]))
    for m in ("tools", "main"): monkeypatch.delitem(sys.modules, m, raising=False)
    for p in ("agent", "api"): monkeypatch.syspath_prepend(str(ROOT / "src" / p))
    yield
    for m in ("tools", "main"): sys.modules.pop(m, None)

def test_agent_tool(stubbed):
    import tools
    assert tools.FUNCS["get_segments"] is tools.get_segments
    schema = next(s for s in tools.SCHEMAS if s["function"]["name"] == "get_segments")["function"]
    assert "EBITDA" in schema["description"] and "results" in schema["description"]
    r = tools.get_segments(["FY26", "2024-25"], ["ebitda"])
    assert r["years"] == ["FY2024-25", "FY2025-26"] and r["items"] == ["segment_results"]
    assert "| Tata Steel India | 28,217.36 | 33,035.63 |" in r["table"]
    assert "| Tata Steel UK operations | -4,134.20 | -2,568.99 |" in r["table"]
    assert "| **Total** | 25,801.80 | 34,847.73 |" in r["table"]
    assert r["sources"] == "Sources: FY2025-26 Annual Report, consolidated segment reporting note, page F256"
    assert any("Tata Steel Europe FY2024-25" in n for n in r["notes"])
    assert tools.get_segments()["items"] == ["segment_revenue", "segment_results"]

def test_api_endpoint(stubbed):
    from fastapi.testclient import TestClient
    import main
    body = TestClient(main.app).get("/api/segments").json()
    assert body["years"] == SA.YEARS
    uk = next(s for s in body["segments"] if s["key"] == "tata_steel_uk")
    assert uk["values"]["FY2025-26"]["segment_results"] == -2568.99
    assert uk["sources"]["FY2025-26"] == {"report": "FY2025-26", "page_label": "F256", "pdf_page": 534,
                                          "url": "/api/pdf/FY2025-26#page=534"}
    assert body["totals"]["values"]["FY2021-22"]["external_revenue"] == 243959.17
    assert body["totals"]["sources"]["FY2021-22"]["report"] == "FY2022-23"
    assert "segment_results" in body["eliminations"]["restated"]["FY2024-25"]
    assert all(set(s) >= {"key", "name", "values", "sources"} for s in body["segments"])
