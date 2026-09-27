"""Tests for task 05: local PDFs (A), statement-only PDFs (B), regions (D), company facts (E) and the agent fixes (F:
approximation check, grounding, dupont tool, compute_metric intermediates). No network, no model calls: the retrieval
module, the LLM client and .env loading are stubbed."""
import importlib.util, json, math, re, sys, types
from pathlib import Path
import pymupdf
import pytest

ROOT = Path(__file__).resolve().parents[1]
YEARS = ["FY2021-22", "FY2022-23", "FY2023-24", "FY2024-25", "FY2025-26"]
LINE_ITEMS = [json.loads(l) for l in open(ROOT / "data/processed/line_items.jsonl")]

@pytest.fixture
def api(monkeypatch):
    monkeypatch.setitem(sys.modules, "search", types.SimpleNamespace(search=lambda *a, **k: [], client=None, COLL="x"))
    monkeypatch.setitem(sys.modules, "agent", types.SimpleNamespace(MODELS=["stub"]))
    for m in ("tools", "main", "regions"): monkeypatch.delitem(sys.modules, m, raising=False)
    for p in ("agent", "api", "analysis"): monkeypatch.syspath_prepend(str(ROOT / "src" / p))
    from fastapi.testclient import TestClient
    import main
    yield main, TestClient(main.app)
    for m in ("tools", "main", "regions"): sys.modules.pop(m, None)

@pytest.fixture
def agent_mod(monkeypatch):
    """src/agent/agent.py with the LLM client and .env loading stubbed (never reads .env, never calls a model)."""
    monkeypatch.setitem(sys.modules, "search", types.SimpleNamespace(search=lambda *a, **k: []))
    monkeypatch.setitem(sys.modules, "ollama", types.SimpleNamespace(Client=lambda **k: None))
    monkeypatch.setitem(sys.modules, "dotenv", types.SimpleNamespace(load_dotenv=lambda *a, **k: None))
    monkeypatch.setenv("OLLAMA_API_KEY", "test")
    monkeypatch.delitem(sys.modules, "tools", raising=False)
    monkeypatch.syspath_prepend(str(ROOT / "src" / "agent"))
    spec = importlib.util.spec_from_file_location("agent_under_test", ROOT / "src/agent/agent.py")
    mod = importlib.util.module_from_spec(spec); spec.loader.exec_module(mod)
    yield mod
    sys.modules.pop("tools", None)

def _walk(x):
    if isinstance(x, dict):
        for v in x.values(): yield from _walk(v)
    elif isinstance(x, list):
        for v in x: yield from _walk(v)
    else: yield x

# ---------- A. local PDFs ----------
def test_pdf_served_inline(api):
    _, c = api
    r = c.get("/api/pdf/FY2025-26")
    assert r.status_code == 200 and r.headers["content-type"] == "application/pdf"
    assert r.headers["content-disposition"].startswith("inline")
    assert r.content[:5] == b"%PDF-" and len(r.content) == (ROOT / "data/raw/TataSteel_FY2025-26.pdf").stat().st_size

def test_pdf_unknown_report_404(api):
    _, c = api
    for rep in ("FY2019-20", "FY2025-26.pdf", "TataSteel_FY2025-26"):
        r = c.get(f"/api/pdf/{rep}")
        assert r.status_code == 404 and "error" in r.json()
    r = c.get("/api/pdf/..%2F..%2F.env")                     # reports are looked up by name only; no path is built
    assert r.status_code == 404 and not r.content.startswith(b"%PDF")

def test_reports_relative_pdf_url_and_official_url(api):
    _, c = api
    body = c.get("/api/reports").json()
    assert [r["fiscal_year"] for r in body] == YEARS[1:]
    for r in body:
        assert r["pdf_url"] == f"/api/pdf/{r['fiscal_year']}"
        assert r["official_url"].startswith("https://www.tatasteel.com/")

def test_citation_urls_are_relative(api):
    main, _ = api
    trace = [{"result": "FY2025-26 Annual Report, consolidated balance sheet, page F143; "
                        "FY2024-25 Annual Report, consolidated risk, page PDF p77"}]
    cites = main.build_citations("... p. F143 ...", trace)
    assert cites == [{"report": "FY2025-26", "section": "consolidated balance sheet", "page_label": "F143",
                      "pdf_page": 421, "pdf_url": "/api/pdf/FY2025-26#page=421"}]
    allc = main.build_citations("no labels", trace)
    assert {c["pdf_url"] for c in allc} == {"/api/pdf/FY2025-26#page=421", "/api/pdf/FY2024-25#page=77"}

# ---------- B. statement-only PDFs ----------
@pytest.mark.parametrize("scope", ["consolidated", "standalone"])
def test_statements_listing(api, scope):
    main, c = api
    body = c.get(f"/api/statements?scope={scope}").json()
    assert body["scope"] == scope and body["years"] == YEARS and main.STATEMENT_PAGE_PROBLEMS == []
    for fy in YEARS:
        rep = "FY2022-23" if fy == "FY2021-22" else fy
        for st in ("profit_and_loss", "balance_sheet", "cash_flow"):
            s = body["statements"][fy][st]
            assert s["report"] == rep and s["url"] == f"/api/statement-pdf?report={rep}&scope={scope}&statement={st}"
            assert len(s["pdf_pages"]) == len(s["page_labels"]) >= 1
            # exactly the pages our line items came from
            assert set(zip(s["pdf_pages"], s["page_labels"])) == {(r["page"], r["page_label"]) for r in LINE_ITEMS
                                                                   if (r["report"], r["scope"], r["statement"]) == (rep, scope, st)}
            assert (s.get("note") == "comparative column of the FY2022-23 report") == (fy == "FY2021-22")

def test_statement_pdf_contains_only_the_statement_pages(api):
    main, c = api
    body = c.get("/api/statements?scope=consolidated").json()["statements"]["FY2025-26"]["profit_and_loss"]
    assert body["page_labels"] == ["F144", "F145"] and body["pdf_pages"] == [422, 423]
    r = c.get(body["url"])
    assert r.status_code == 200 and r.headers["content-type"] == "application/pdf" and r.headers["content-disposition"].startswith("inline")
    doc, src = pymupdf.open(stream=r.content, filetype="pdf"), pymupdf.open(ROOT / "data/raw/TataSteel_FY2025-26.pdf")
    assert doc.page_count == 2
    assert doc.metadata["title"] == "Tata Steel FY2025-26 consolidated statement of profit and loss (F144-F145)"
    for i, p in enumerate(body["pdf_pages"]):              # pages exactly as printed
        assert doc[i].get_text() == src[p - 1].get_text()
    assert "CONSOLIDATED STATEMENT OF PROFIT AND LOSS" in doc[0].get_text()
    assert ("FY2025-26", "consolidated", "profit_and_loss") in main._STATEMENT_PDF_CACHE     # cached in memory
    assert c.get(body["url"]).content == r.content

def test_statement_pdf_single_page_title(api):
    _, c = api
    r = c.get("/api/statement-pdf?report=FY2022-23&scope=standalone&statement=balance_sheet")
    doc = pymupdf.open(stream=r.content, filetype="pdf")
    assert doc.page_count == 1 and doc.metadata["title"] == "Tata Steel FY2022-23 standalone balance sheet (F22)"
    assert "BALANCE SHEET" in doc[0].get_text() and "F22" in doc[0].get_text()

@pytest.mark.parametrize("q", ["report=FY2019-20&scope=consolidated&statement=balance_sheet",
                               "report=FY2025-26&scope=group&statement=balance_sheet",
                               "report=FY2025-26&scope=consolidated&statement=notes"])
def test_statement_pdf_bad_params_404(api, q):
    _, c = api
    r = c.get(f"/api/statement-pdf?{q}")
    assert r.status_code == 404 and "error" in r.json()

# ---------- D. regions ----------
@pytest.fixture
def regions_body(api):
    return api[1].get("/api/regions").json()

def _region(body, key):
    return next(r for r in body["regions"] if r["key"] == key)

def test_regions_reconcile_to_segment_totals(regions_body):
    assert regions_body["years"] == YEARS
    for fy in YEARS:
        for item in ("segment_revenue", "external_revenue", "ebitda"):
            rec = regions_body["reconciliation"][fy][item]
            assert rec["ok"] is True, (fy, item, rec)
            assert abs(rec["regions_sum"] + (rec["eliminations"] or 0) - rec["total"]) <= 0.011

def test_regions_composition_and_absent_years(regions_body):
    keys = [r["key"] for r in regions_body["regions"]]
    assert keys == ["india", "netherlands", "uk", "europe", "south_east_asia", "rest_of_world", "trading"]
    india = _region(regions_body, "india")["values"]
    assert [c["key"] for c in india["FY2021-22"]["components"]] == ["tata_steel_india", "other_indian_operations", "tata_steel_long_products"]
    assert [c["key"] for c in india["FY2025-26"]["components"]] == ["tata_steel_india", "neelachal_ispat_nigam", "other_indian_operations"]
    assert india["FY2025-26"]["ebitda"] == round(33035.63 + 1236.29 + 707.25, 2)
    assert india["FY2021-22"]["segment_revenue"] == round(129021.35 + 21274.90 + 6801.63, 2)
    assert list(_region(regions_body, "europe")["values"]) == ["FY2021-22", "FY2022-23", "FY2023-24"]
    assert list(_region(regions_body, "netherlands")["values"]) == ["FY2024-25", "FY2025-26"]
    assert list(_region(regions_body, "uk")["values"]) == ["FY2024-25", "FY2025-26"]

def test_regions_ratios_computed_in_backend(regions_body):
    uk = _region(regions_body, "uk")["values"]["FY2025-26"]
    assert uk["ebitda"] == -2568.99 and uk["segment_revenue"] == 23332.67 and uk["external_revenue"] == 22383.41
    assert uk["ebitda_margin_pct"] == round(-2568.99 / 23332.67 * 100, 2) == -11.01
    assert uk["share_of_group_external_revenue_pct"] == round(22383.41 / 232139.94 * 100, 2)
    assert uk["share_of_group_ebitda_pct"] == round(-2568.99 / 34847.73 * 100, 2)
    assert uk["sources"] == [{"report": "FY2025-26", "page_label": "F256", "pdf_page": 534, "url": "/api/pdf/FY2025-26#page=534"}]
    tr = _region(regions_body, "trading")["values"]["FY2024-25"]
    assert tr["restated"] == {"other_trade_related_operations": ["ebitda"]}
    for g in regions_body["regions"]:
        for fy, v in g["values"].items():
            assert v["ebitda_margin_pct"] == round(v["ebitda"] / v["segment_revenue"] * 100, 2)
            assert v["sources"] and all(s["url"] == f"/api/pdf/{s['report']}#page={s['pdf_page']}" for s in v["sources"])
    assert all(math.isfinite(x) for x in _walk(regions_body) if isinstance(x, float))

# ---------- E. company facts ----------
_spec = importlib.util.spec_from_file_location("company_facts", ROOT / "src/ingest/company_facts.py")
CF = importlib.util.module_from_spec(_spec); _spec.loader.exec_module(CF)

def test_company_json_matches_verified_build():
    data = json.loads((ROOT / "data/processed/company.json").read_text())
    facts, rows = CF.build()
    assert 3 <= len(data["facts"]) <= 5 and data["facts"] == facts
    assert all(ok for *_, ok in rows)
    for f in data["facts"]:
        assert f["report"] == "FY2025-26" and f["url"] == f"/api/pdf/FY2025-26#page={f['pdf_page']}"
        assert not CF.FORWARD.search(f["text"])

def test_company_fact_verification_rejects_unprinted_values(monkeypatch):
    monkeypatch.setattr(CF, "FACTS", [("Tata Steel has 99,000+ employees across the globe.", 9, "12-13"),
                                      ("Tata Steel operates in Atlantis.", 9, "12-13"),
                                      ("Tata Steel will reach 40 MTPA.", 9, "12-13"),
                                      ("It has 77,000+ employees across the globe.", 9, "12-13")])
    facts, rows = CF.build()
    assert [f["text"] for f in facts] == ["It has 77,000+ employees across the globe."]
    assert [ok for *_, ok in rows] == [False, False, False, True]

def test_company_endpoint(api):
    body = api[1].get("/api/company").json()
    assert body == json.loads((ROOT / "data/processed/company.json").read_text())

# ---------- F. agent fixes ----------
@pytest.mark.parametrize("text", ["ROE of ≈ 11.16%", "margin ~4.69 %", "equity rose by around 12.23%",
                                  "about ₹10,998.02 crore", "roughly 780.59%", "approximately 2.98x"])
def test_approximations_are_flagged(agent_mod, text):
    issues = agent_mod.unsupported_claims(text + " (FY2025-26 AR, p. F143)", [])
    assert any("Approximate figures" in i for i in issues)

def test_exact_figures_not_flagged(agent_mod):
    ok = "ROE was 11.16% (FY2025-26 AR, p. F143). This is about Tata Steel's equity, around the Group."
    assert not any("Approximate" in i for i in agent_mod.unsupported_claims(ok, []))
    assert "24. Never write approximations" in agent_mod.SYSTEM and "25. DuPont" in agent_mod.SYSTEM

def test_calculate_operands_are_not_grounding_evidence(agent_mod):
    res = {"results": [{"expression": "232139.94/290324.455", "result": 0.799588}]}
    pools = (set(), set())
    agent_mod.collect(agent_mod.grounding_view("calculate", res), pools)
    assert agent_mod.grounded(0.7996, False, pools)                  # the result counts
    assert not agent_mod.grounded(290324.46, False, pools)           # a hand-computed operand does not
    pools2 = (set(), set())
    agent_mod.collect(agent_mod.grounding_view("get_financials", {"x": "290324.455"}), pools2)
    assert agent_mod.grounded(290324.46, False, pools2) and agent_mod.grounded(290324.45, False, pools2)

def test_dupont_tool_returns_every_intermediate(agent_mod):
    import tools
    assert tools.FUNCS["dupont"] is tools.dupont and any(s["function"]["name"] == "dupont" for s in tools.SCHEMAS)
    r = tools.dupont(["FY2025-26"])
    y = r["results"]["FY2025-26"]
    assert y["inputs"]["average_total_assets"] == pytest.approx((301254.11 + 279394.80) / 2)
    assert y["inputs"]["average_total_equity"] == pytest.approx((103780.45 + 91352.78) / 2)
    t = y["three_step"]
    assert t["roe_pct"] == pytest.approx(10885.82 / ((103780.45 + 91352.78) / 2) * 100, abs=1e-4)
    assert t["product_check_pct"] == pytest.approx(t["roe_pct"], abs=1e-3)
    assert y["five_step"]["product_check_pct"] == pytest.approx(t["roe_pct"], abs=1e-3)
    eq = y["equity_change"]           # the numbers the failing answer had computed by hand
    assert eq["other_equity"]["change"] == 10998.02 and eq["other_equity"]["change_pct"] == 12.23
    assert eq["non_controlling_interests"]["change"] == 1429.65 and eq["total_equity"]["change"] == 12427.67
    assert "| **ROE** (profit for the year / average total equity) | **11.16%** |" in r["table"]
    pools = (set(), set())
    agent_mod.collect(agent_mod.grounding_view("dupont", r), pools)
    for v in (10998.02, 12.23, 1429.65, 780.59, 11.16, 0.7996, 2.9757, 290324.46, 97566.62, 7.70):
        assert agent_mod.grounded(v, False, pools), v

def test_dupont_edge_cases(agent_mod):
    import tools
    r = tools.dupont(["FY2021-22"])
    assert "error" in r["results"]["FY2021-22"]                       # average basis needs FY2020-21
    r = tools.dupont(["FY2023-24"], basis="year_end")["results"]["FY2023-24"]
    assert r["five_step"]["tax_burden_x"] is None and "note" in r["five_step"]     # pre-tax loss year

def test_compute_metric_returns_avg_intermediates(agent_mod):
    import tools
    r = tools.compute_metric("profit_for_the_year / avg(total_equity) * 100", fiscal_years=["FY2025-26"])
    assert r["intermediates"]["FY2025-26"]["avg(total_equity)"] == pytest.approx(97566.615)
    assert "avg(total_equity) = 97,566.615" in r["table"]
