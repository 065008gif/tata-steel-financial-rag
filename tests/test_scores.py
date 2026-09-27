"""Tests for src/analysis/scores.py: formulas on synthetic data (hand-computed), then checks on the real data."""
import json, math, re, sys
from pathlib import Path
import pymupdf
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src" / "analysis"))
import scores

T, T1, T2 = "FY2025-26", "FY2024-25", "FY2023-24"

def _entry(vals, report):
    return {"description": "synthetic", "values": {fy: {"value": v, "source": f"{report} Annual Report, consolidated "
                                                        f"synthetic, page F1"} for fy, v in vals.items()}}

def _scope(items, report):
    return {k: _entry(v, report) for k, v in items.items()}

# year t / t-1 as presented in the FY2025-26 report; t-2 only in financials.json
REPORT_T = {
    "total_assets": {T: 1100, T1: 1000}, "total_equity": {T: 400, T1: 380},
    "total_current_assets": {T: 500, T1: 400}, "total_current_liabilities": {T: 250, T1: 250},
    "property_plant_equipment": {T: 400, T1: 380}, "non_current_investments": {T: 50, T1: 20},
    "trade_receivables": {T: 120, T1: 100}, "equity_share_capital": {T: 10, T1: 10},
    "other_equity": {T: 390, T1: 370}, "non_current_borrowings": {T: 200, T1: 250},
    "revenue_from_operations": {T: 1200, T1: 1000}, "cost_of_materials_consumed": {T: 600, T1: 550},
    "depreciation_amortisation": {T: 60, T1: 50}, "other_expenses": {T: 240, T1: 180},
    "finance_costs": {T: 20, T1: 25}, "profit_before_tax": {T: 150, T1: 70},
    "profit_for_the_year": {T: 110, T1: 50}, "net_cash_from_operating": {T: 150, T1: 90}}
ALTMAN_T = {"total_assets": {T: 1000}, "total_equity": {T: 400}, "total_current_assets": {T: 300},
            "total_current_liabilities": {T: 200}, "other_equity": {T: 350}, "profit_before_tax": {T: 80},
            "finance_costs": {T: 20}}

@pytest.fixture
def synthetic(monkeypatch):
    fin = {"consolidated": _scope(ALTMAN_T, T)}
    fin["consolidated"]["total_assets"]["values"][T2] = {"value": 900, "source": "FY2024-25 Annual Report, page F9"}
    rep = {T: {"consolidated": _scope(REPORT_T, T)}}
    # retained earnings: T and T1 in the FY2025-26 report, T1 also (differently) in the FY2024-25 report
    re_ = {T: {"consolidated": {T: _re(200, "F20"), T1: _re(180, "F20")}},
           T1: {"consolidated": {T1: _re(170, "F30")}}}
    monkeypatch.setattr(scores, "FIN", fin)
    monkeypatch.setattr(scores, "FIN_REP", rep)
    monkeypatch.setattr(scores, "RE", re_)
    return fin, rep, re_

def _re(v, label):
    return {"value": v, "pdf_page": 1, "page_label": label, "method": "synthetic", "verified_on_page": True}


# ---------- formula tests (synthetic) ----------
def test_altman_formula(synthetic):
    r = scores.altman_z(T)
    # X1 = 100/1000, X2 = retained earnings 200/1000, X3 = 100/1000, X4 = 400/600
    assert r["components"] == pytest.approx({"X1": 0.1, "X2": 0.2, "X3": 0.1, "X4": 0.666667}, abs=1e-6)
    # 6.56*0.1 + 3.26*0.2 + 6.72*0.1 + 1.05*0.666667 = 0.656 + 0.652 + 0.672 + 0.7 = 2.68
    assert r["score"] == pytest.approx(2.68, abs=1e-4)
    assert r["interpretation"] == "safe"
    assert r["missing"] == [] and r["fallbacks"] == [] and r["proxies"]
    assert r["x2_numerator"] == "retained_earnings" and "other_equity[FY2025-26]" not in r["inputs"]
    assert not any("proxy for retained earnings" in p for p in r["proxies"])
    assert r["inputs"]["retained_earnings[FY2025-26]"]["value"] == 200
    assert r["inputs"]["total_assets[FY2025-26]"]["source"].startswith("FY2025-26 Annual Report")

def test_altman_retained_earnings_from_latest_report(synthetic):
    synthetic[0]["consolidated"] = _scope({k: {T1: v[T]} for k, v in ALTMAN_T.items()}, T)
    r = scores.altman_z(T1)
    # FY2024-25 is in both the FY2024-25 (170) and FY2025-26 (180) reports: the latest wins
    assert r["inputs"]["retained_earnings[FY2024-25]"]["value"] == 180
    assert r["inputs"]["retained_earnings[FY2024-25]"]["source"].startswith("FY2025-26 Annual Report")
    assert r["components"]["X2"] == pytest.approx(0.18, abs=1e-6)

def test_altman_falls_back_to_other_equity(synthetic):
    del synthetic[2][T]["consolidated"][T]                    # no retained earnings for FY2025-26 anywhere
    synthetic[2][T1]["consolidated"][T] = dict(_re(999, "F9"), verified_on_page=False)   # unverified: ignored
    r = scores.altman_z(T)
    # X2 = other_equity 350/1000; 0.656 + 1.141 + 0.672 + 0.7 = 3.169
    assert r["components"]["X2"] == pytest.approx(0.35, abs=1e-6)
    assert r["score"] == pytest.approx(3.169, abs=1e-4) and r["interpretation"] == "safe"
    assert r["x2_numerator"] == "other_equity" and r["inputs"]["other_equity[FY2025-26]"]["value"] == 350
    assert "retained_earnings[FY2025-26]" not in r["inputs"]
    assert any("other_equity as a proxy for retained earnings" in p for p in r["proxies"])
    assert any(f.startswith("retained_earnings[FY2025-26]") for f in r["fallbacks"])

@pytest.mark.parametrize("z, zone", [(2.61, "safe"), (2.60, "grey"), (1.10, "grey"), (1.09, "distress"), (None, None)])
def test_altman_zones(z, zone):
    assert scores.altman_zone(z) == zone

def test_piotroski_all_signals(synthetic):
    r = scores.piotroski_f(T)
    # ROA_t = 110/1000 = 0.11 > 0; CFO 150 > 0; ROA_t-1 = 50/900 = 0.0556 < 0.11; CFO/TA = 0.15 > 0.11;
    # leverage 200/1100 = 0.1818 < 0.25; current ratio 2.0 > 1.6; share capital 10 <= 10; gross margin 0.5 > 0.45;
    # asset turnover 1200/1000 = 1.2 > 1000/900 = 1.111
    assert {k: v["signal"] for k, v in r["components"].items()} == {
        "F1_roa_positive": 1, "F2_cfo_positive": 1, "F3_roa_improved": 1, "F4_accruals": 1, "F5_leverage_decreased": 1,
        "F6_current_ratio_increased": 1, "F7_no_new_equity": 1, "F8_gross_margin_increased": 1, "F9_asset_turnover_increased": 1}
    assert r["score"] == 9 and r["interpretation"] == "strong"
    assert r["components"]["F3_roa_improved"]["comparison"] == pytest.approx(50 / 900, abs=1e-6)
    assert r["components"]["F9_asset_turnover_increased"]["current"] == pytest.approx(1.2, abs=1e-6)
    # t-2 assets are not in the FY2025-26 report: the financials.json fallback must be recorded
    assert any("total_assets[FY2023-24]" in f for f in r["fallbacks"])
    assert r["inputs"]["total_assets[FY2024-25]"]["basis"] == "as presented in the FY2025-26 report"

def test_piotroski_weak_signals(synthetic):
    rep = synthetic[1][T]["consolidated"]
    rep["profit_for_the_year"]["values"][T]["value"] = -10      # F1 0, F3 0 (F4 still 1: 0.15 > -0.01)
    rep["equity_share_capital"]["values"][T]["value"] = 12      # F7 0
    rep["cost_of_materials_consumed"]["values"][T]["value"] = 700  # GM 0.4167 < 0.45 -> F8 0
    r = scores.piotroski_f(T)
    assert r["score"] == 5 and r["interpretation"] == "average"   # 9 - F1, F3, F7, F8
    assert [r["components"][k]["signal"] for k in ("F1_roa_positive", "F3_roa_improved", "F4_accruals",
                                                   "F7_no_new_equity", "F8_gross_margin_increased")] == [0, 0, 1, 0, 0]

@pytest.mark.parametrize("f, label", [(9, "strong"), (8, "strong"), (7, "average"), (5, "average"), (4, "weak"), (0, "weak")])
def test_piotroski_labels(f, label):
    assert scores.piotroski_label(f) == label

def test_piotroski_t2_unavailable_uses_t1_and_discloses(synthetic):
    del synthetic[0]["consolidated"]["total_assets"]["values"][T2]
    r = scores.piotroski_f(T)
    assert r["score"] is not None
    assert r["components"]["F3_roa_improved"]["comparison"] == pytest.approx(50 / 1000, abs=1e-6)
    assert any("FY2023-24 is unavailable" in p for p in r["proxies"])

def test_beneish_formula(synthetic):
    r = scores.beneish_m(T)
    expected = {"DSRI": 1.0,                                # (120/1200) / (100/1000)
                "GMI": 0.9,                                 # 0.45 / 0.5
                "AQI": (150 / 1100) / 0.2,                  # [1 - 950/1100] / [1 - 800/1000] = 0.681818
                "SGI": 1.2,                                 # 1200 / 1000
                "DEPI": (50 / 430) / (60 / 460),            # 0.891473
                "SGAI": 0.2 / 0.18,                         # 1.111111
                "LVGI": (450 / 1100) / 0.5,                 # 0.818182
                "TATA": -40 / 1100}                         # (110 - 150) / 1100 = -0.036364
    assert r["components"] == pytest.approx(expected, abs=1e-6)
    # -4.84 + 0.92 + 0.4752 + 0.275455 + 1.0704 + 0.102519 - 0.191111 - 0.170146 - 0.267545
    assert r["score"] == pytest.approx(-2.625228, abs=1e-4)
    assert r["interpretation"] == "unlikely manipulator"
    assert len(r["proxies"]) >= 2 and any("other_expenses" in p for p in r["proxies"])

@pytest.mark.parametrize("m, label", [(-1.77, "possible earnings manipulation flag"), (-1.78, "unlikely manipulator"),
                                      (-2.5, "unlikely manipulator")])
def test_beneish_labels(m, label):
    assert scores.beneish_label(m) == label

def test_report_fallback_is_recorded(synthetic):
    rep = synthetic[1][T]["consolidated"]
    fin = synthetic[0]["consolidated"]
    fin["trade_receivables"] = _entry({T: 120, T1: 100}, T)
    del rep["trade_receivables"]
    r = scores.beneish_m(T)
    assert r["score"] is not None
    assert any("trade_receivables[FY2025-26]" in f for f in r["fallbacks"])
    assert r["inputs"]["trade_receivables[FY2025-26]"]["basis"].startswith("financials.json")


# ---------- missing inputs: None with a reason, never an exception ----------
def test_missing_inputs_give_none(synthetic):
    del synthetic[1][T]["consolidated"]["trade_receivables"]
    del synthetic[0]["consolidated"]["other_equity"]
    synthetic[2].clear()                                       # no retained earnings -> other_equity needed
    b, a = scores.beneish_m(T), scores.altman_z(T)
    for r in (a, b):
        assert r["score"] is None and r["interpretation"] is None and r["missing"] and r["reason"]
    assert "trade_receivables" in b["reason"] and "other_equity" in a["reason"]

def test_missing_report_and_unknown_year(synthetic):
    for fn in (scores.piotroski_f, scores.beneish_m):
        r = fn(T1)            # no FY2024-25 report in the synthetic data
        assert r["score"] is None and r["reason"]
    for fn in (scores.altman_z, scores.piotroski_f, scores.beneish_m):
        assert fn("FY2019-20")["score"] is None
        assert fn(T, "no_such_scope")["score"] is None

def test_zero_denominator_gives_none(synthetic):
    synthetic[0]["consolidated"]["total_equity"]["values"][T]["value"] = 1000   # total_assets - total_equity = 0
    r = scores.altman_z(T)
    assert r["score"] is None and "X4" in r["reason"]
    synthetic[1][T]["consolidated"]["revenue_from_operations"]["values"][T1]["value"] = 0
    b = scores.beneish_m(T)
    assert b["score"] is None and b["reason"]


# ---------- real data ----------
@pytest.fixture(scope="module")
def real():
    return {sc: scores.all_scores(sc) for sc in ("consolidated", "standalone")}

def test_real_altman_consolidated_fy2025_26():
    r = scores.altman_z("FY2025-26", "consolidated")
    ins = r["inputs"]
    assert ins["total_assets[FY2025-26]"]["value"] == 301254.11
    assert ins["total_equity[FY2025-26]"]["value"] == 103780.45
    assert r["components"]["X4"] == pytest.approx(103780.45 / 197473.66, abs=1e-4)
    assert r["components"]["X4"] == pytest.approx(0.525544, abs=1e-4)
    assert r["components"]["X1"] == pytest.approx(-0.081833, abs=1e-4)
    # X2 uses retained earnings (Other equity note, F197), not other equity (1,00,920.21)
    assert r["x2_numerator"] == "retained_earnings" and "other_equity[FY2025-26]" not in ins
    assert ins["retained_earnings[FY2025-26]"]["value"] == 39674.80
    assert "page F197" in ins["retained_earnings[FY2025-26]"]["source"]
    assert r["components"]["X2"] == pytest.approx(39674.80 / 301254.11, abs=1e-6)
    assert not any("proxy for retained earnings" in p for p in r["proxies"]) and r["fallbacks"] == []
    # Z'' recomputed from the raw inputs and from the rounded components agrees with the reported score
    v = lambda k: ins[f"{k}[FY2025-26]"]["value"]
    ta = v("total_assets")
    x = {"X1": (v("total_current_assets") - v("total_current_liabilities")) / ta, "X2": v("retained_earnings") / ta,
         "X3": (v("profit_before_tax") + v("finance_costs")) / ta, "X4": v("total_equity") / (ta - v("total_equity"))}
    assert r["components"] == pytest.approx(x, abs=1e-6)
    z = 6.56 * x["X1"] + 3.26 * x["X2"] + 6.72 * x["X3"] + 1.05 * x["X4"]
    assert r["score"] == pytest.approx(z, abs=1e-4)
    assert r["score"] == pytest.approx(sum(r["weights"][k] * c for k, c in r["components"].items()), abs=1e-4)
    assert r["score"] == pytest.approx(0.9604, abs=1e-4) and r["interpretation"] == "distress"

@pytest.mark.parametrize("scope", ["consolidated", "standalone"])
def test_real_altman_uses_retained_earnings_every_year(real, scope):
    for fy, r in real[scope]["scores"]["altman_z"].items():
        assert r["x2_numerator"] == "retained_earnings" and r["fallbacks"] == [], fy

def _inr(v):
    i, d = f"{abs(v):.2f}".split(".")
    head, tail = i[:-3], i[-3:]
    groups = []
    while head: groups.insert(0, head[-2:]); head = head[:-2]
    s = ",".join(groups + [tail]) + "." + d
    return f"({s})" if v < 0 else s

def test_retained_earnings_values_are_on_their_pages():
    data = json.loads((ROOT / "data/processed/retained_earnings.json").read_text())
    checked, years = 0, {sc: set() for sc in ("consolidated", "standalone")}
    for rep, per_scope in data.items():
        doc = pymupdf.open(ROOT / f"data/raw/TataSteel_{rep}.pdf")
        pmap = {p["page"]: p for p in json.loads((ROOT / f"data/interim/page_map_{rep}.json").read_text())}
        for scope, per_year in per_scope.items():
            for fy, rec in per_year.items():
                if not rec["verified_on_page"]: continue
                text = re.sub(r"\s+", " ", doc[rec["pdf_page"] - 1].get_text())
                assert _inr(rec["value"]) in text, (rep, scope, fy, rec)
                assert "retained earnings" in text.lower() and "Other equity" in text
                assert pmap[rec["pdf_page"]]["label"] == rec["page_label"] and pmap[rec["pdf_page"]]["scope"] == scope
                checked += 1; years[scope].add(fy)
    assert checked == 16
    assert all(ys == {"FY2021-22", *scores.SCORE_YEARS} for ys in years.values())

@pytest.mark.parametrize("scope", ["consolidated", "standalone"])
@pytest.mark.parametrize("fy", ["FY2023-24", "FY2024-25", "FY2025-26"])
def test_real_piotroski_and_beneish(real, scope, fy):
    p, b = real[scope]["scores"]["piotroski_f"][fy], real[scope]["scores"]["beneish_m"][fy]
    assert isinstance(p["score"], int) and 0 <= p["score"] <= 9
    assert all(s["signal"] in (0, 1) for s in p["components"].values()) and len(p["components"]) == 9
    assert isinstance(b["score"], float) and math.isfinite(b["score"])
    assert p["missing"] == [] and b["missing"] == []

def _numbers(x):
    if isinstance(x, dict):
        for v in x.values(): yield from _numbers(v)
    elif isinstance(x, list):
        for v in x: yield from _numbers(v)
    elif isinstance(x, float): yield x

def test_real_no_nan_or_inf(real):
    for res in real.values():
        assert all(math.isfinite(v) for v in _numbers(res))
        json.dumps(res, allow_nan=False)
        assert res["years"] == ["FY2021-22", "FY2022-23", "FY2023-24", "FY2024-25", "FY2025-26"]
        for name, per_year in res["scores"].items():
            for fy, r in per_year.items():
                if fy == "FY2021-22" and name != "altman_z": continue      # needs FY2020-21 (see test below)
                assert r["score"] is not None, r.get("reason")
                assert all(i["source"] for i in r["inputs"].values())

def test_real_year_pair_rule():
    r = scores.beneish_m("FY2025-26", "consolidated")
    for rec in r["inputs"].values():
        assert rec["basis"] == "as presented in the FY2025-26 report"
        assert rec["source"].startswith("FY2025-26 Annual Report")


# ---------- FY2021-22 (only a comparative column of the FY2022-23 report) ----------
@pytest.mark.parametrize("scope, z, zone", [("consolidated", 2.7197, "safe"), ("standalone", 3.2455, "safe")])
def test_fy2021_22_altman_from_fy2022_23_report(scope, z, zone):
    r = scores.altman_z("FY2021-22", scope)
    assert r["score"] == pytest.approx(z, abs=1e-4) and r["interpretation"] == zone
    assert r["x2_numerator"] == "retained_earnings" and r["missing"] == [] and r["fallbacks"] == []
    doc = pymupdf.open(ROOT / "data/raw/TataSteel_FY2022-23.pdf")
    pmap = {p["label"]: p["page"] for p in json.loads((ROOT / "data/interim/page_map_FY2022-23.json").read_text()) if p["label"]}
    for rec in r["inputs"].values():               # every input is from the FY2022-23 report and printed on its page
        assert rec["source"].startswith("FY2022-23 Annual Report"), rec
        label = re.search(r"page (F\d+)", rec["source"]).group(1)
        assert _inr(rec["value"]) in re.sub(r"\s+", " ", doc[pmap[label] - 1].get_text()), rec

@pytest.mark.parametrize("scope", ["consolidated", "standalone"])
def test_fy2021_22_two_year_scores_are_null_with_reason(scope):
    for fn in (scores.piotroski_f, scores.beneish_m):
        r = fn("FY2021-22", scope)
        assert r["score"] is None and r["interpretation"] is None
        assert r["reason"] == "needs FY2020-21, which is outside the four reports"

def test_score_years_cover_fy2021_22():
    assert scores.SCORE_YEARS == ["FY2021-22", "FY2022-23", "FY2023-24", "FY2024-25", "FY2025-26"]
    res = scores.all_scores("consolidated")
    assert res["years"] == scores.SCORE_YEARS and set(res["scores"]["altman_z"]) == set(scores.SCORE_YEARS)
