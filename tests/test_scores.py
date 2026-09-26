"""Tests for src/analysis/scores.py: formulas on synthetic data (hand-computed), then checks on the real data."""
import json, math, sys
from pathlib import Path
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
    monkeypatch.setattr(scores, "FIN", fin)
    monkeypatch.setattr(scores, "FIN_REP", rep)
    return fin, rep


# ---------- formula tests (synthetic) ----------
def test_altman_formula(synthetic):
    r = scores.altman_z(T)
    # X1 = 100/1000, X2 = 350/1000, X3 = 100/1000, X4 = 400/600
    assert r["components"] == pytest.approx({"X1": 0.1, "X2": 0.35, "X3": 0.1, "X4": 0.666667}, abs=1e-6)
    # 6.56*0.1 + 3.26*0.35 + 6.72*0.1 + 1.05*0.666667 = 0.656 + 1.141 + 0.672 + 0.7 = 3.169
    assert r["score"] == pytest.approx(3.169, abs=1e-4)
    assert r["interpretation"] == "safe"
    assert r["missing"] == [] and r["proxies"]
    assert r["inputs"]["total_assets[FY2025-26]"]["source"].startswith("FY2025-26 Annual Report")

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
    assert r["inputs"]["total_assets[FY2025-26]"]["value"] == 301254.11
    assert r["inputs"]["total_equity[FY2025-26]"]["value"] == 103780.45
    assert r["components"]["X4"] == pytest.approx(103780.45 / 197473.66, abs=1e-4)
    assert r["components"]["X4"] == pytest.approx(0.525544, abs=1e-4)
    assert r["components"]["X1"] == pytest.approx(-0.081833, abs=1e-4)
    assert isinstance(r["score"], float) and r["interpretation"] in ("safe", "grey", "distress")

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
        assert res["years"] == ["FY2022-23", "FY2023-24", "FY2024-25", "FY2025-26"]
        for per_year in res["scores"].values():
            for r in per_year.values():
                assert r["score"] is not None, r.get("reason")
                assert all(i["source"] for i in r["inputs"].values())

def test_real_year_pair_rule():
    r = scores.beneish_m("FY2025-26", "consolidated")
    for rec in r["inputs"].values():
        assert rec["basis"] == "as presented in the FY2025-26 report"
        assert rec["source"].startswith("FY2025-26 Annual Report")
