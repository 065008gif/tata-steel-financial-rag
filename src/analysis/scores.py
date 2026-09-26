"""Composite financial scores over the verified statement data: Altman Z'' (book-equity), Piotroski F, Beneish M.

Pure functions, no agent or API dependency. Each score returns score, zone/interpretation, components, every
input with its value and source, the proxies used, and `missing` (score None with a reason; never raises).
Year-pair rule: formulas comparing t with t-1 take both years from the report of year t (financials_by_report.json),
which presents t-1 as a comparative (restated where applicable); financials.json is only a recorded fallback.
"""
import json, math
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
FIN = json.loads((ROOT / "data/processed/financials.json").read_text())
FIN_REP = json.loads((ROOT / "data/processed/financials_by_report.json").read_text())
_RE_PATH = ROOT / "data/processed/retained_earnings.json"
RE = json.loads(_RE_PATH.read_text()) if _RE_PATH.exists() else {}
YEARS = ["FY2021-22", "FY2022-23", "FY2023-24", "FY2024-25", "FY2025-26"]
SCORE_YEARS = ["FY2022-23", "FY2023-24", "FY2024-25", "FY2025-26"]

GM_PROXY = ("Gross margin = (revenue_from_operations - cost_of_materials_consumed) / revenue_from_operations; excludes "
            "purchases of stock-in-trade and changes in inventories, which are not canonical items.")

def prev_fy(fy):
    i = YEARS.index(fy) if fy in YEARS else -1
    return YEARS[i - 1] if i > 0 else None

class _Inputs:
    """Collects the inputs a score uses, with value, source and basis, and records what is missing."""
    def __init__(self, scope, report=None):
        self.scope, self.report = scope, report
        self.inputs, self.missing, self.fallbacks = {}, [], []

    def get(self, key, fy, required=True):
        """Value of key for fy: from the report `self.report` if set, else (or if absent there) from financials.json.
        An unavailable input is recorded in `missing` unless required=False."""
        if fy is None:
            if required: self.missing.append(f"{key}: fiscal year not available")
            return None
        name = f"{key}[{fy}]"
        if name in self.inputs: return self.inputs[name]["value"]
        v, basis = None, None
        if self.report:
            v = FIN_REP.get(self.report, {}).get(self.scope, {}).get(key, {}).get("values", {}).get(fy)
            basis = f"as presented in the {self.report} report"
        if v is None:
            v = FIN.get(self.scope, {}).get(key, {}).get("values", {}).get(fy)
            if v is not None:
                basis = "financials.json (latest report containing the year)"
                if self.report: self.fallbacks.append(f"{name}: not in the {self.report} report; used financials.json")
        if v is None or not isinstance(v.get("value"), (int, float)) or not math.isfinite(v["value"]):
            if required: self.missing.append(f"{name}: not available for scope {self.scope}")
            return None
        rec = {"item": key, "fiscal_year": fy, "value": v["value"], "source": v["source"], "basis": basis}
        if v.get("restated"): rec.update(restated=True, originally_reported=v.get("originally_reported"))
        self.inputs[name] = rec
        return v["value"]

def _div(a, b):
    if a is None or b is None or b == 0: return None
    r = a / b
    return r if math.isfinite(r) else None

def _r(x, d=6):
    return None if x is None else round(x, d)

def _result(score_name, fy, scope, ins, basis, proxies, score=None, label=None, components=None, extra=None):
    out = {"score_name": score_name, "fiscal_year": fy, "scope": scope, "basis": basis, "score": score,
           "interpretation": label, "components": components or {}, "inputs": ins.inputs, "proxies": proxies,
           "fallbacks": ins.fallbacks, "missing": ins.missing}
    if extra: out.update(extra)
    return out


# ---------- Altman Z'' (book-equity version) ----------
ALTMAN_W = {"X1": 6.56, "X2": 3.26, "X3": 6.72, "X4": 1.05}

def altman_zone(z):
    if z is None: return None
    return "safe" if z > 2.60 else ("grey" if z >= 1.10 else "distress")

def retained_earnings(fy, scope="consolidated"):
    """Page-verified retained earnings (closing balance) for fy from the LATEST report containing it, or None.
    Returns (report, record) from retained_earnings.json."""
    for rep in sorted(RE, reverse=True):
        rec = RE[rep].get(scope, {}).get(fy)
        if rec and rec.get("verified_on_page") and isinstance(rec.get("value"), (int, float)) and math.isfinite(rec["value"]):
            return rep, rec
    return None

def altman_z(fy, scope="consolidated"):
    """Z'' = 6.56 X1 + 3.26 X2 + 6.72 X3 + 1.05 X4, single year, values from financials.json (latest report).
    X2 = retained earnings / total assets; falls back to other_equity (recorded) if retained earnings are unavailable."""
    proxies = ["X4 uses book equity (total_equity) instead of market value of equity, which is not in the reports; "
               "this is the Z'' book-equity variant.",
               "X3 EBIT = profit_before_tax + finance_costs (after exceptional items)."]
    ins = _Inputs(scope)
    ta, te = ins.get("total_assets", fy), ins.get("total_equity", fy)
    ca, cl = ins.get("total_current_assets", fy), ins.get("total_current_liabilities", fy)
    pbt, fc = ins.get("profit_before_tax", fy), ins.get("finance_costs", fy)
    found = retained_earnings(fy, scope)
    if found:
        rep, rec = found
        re_v, x2_basis = rec["value"], "retained_earnings"
        ins.inputs[f"retained_earnings[{fy}]"] = {
            "item": "retained_earnings", "fiscal_year": fy, "value": re_v,
            "source": f"{rep} Annual Report, {scope} note 'Other equity' (A. Retained earnings, balance at the end "
                      f"of the year), page {rec['page_label']}",
            "basis": "retained_earnings.json (latest report containing the year)"}
        ta_rep = FIN.get(scope, {}).get("total_assets", {}).get("values", {}).get(fy, {}).get("report")
        if ta_rep and ta_rep != rep:
            proxies.append(f"Retained earnings for {fy} are from the {rep} report, total assets from the {ta_rep} report "
                           f"(the latest report containing each); the {ta_rep} report does not give {fy} closing "
                           f"retained earnings, so the two may be on different (restated) bases.")
    else:
        x2_basis = "other_equity"
        re_v = ins.get("other_equity", fy)
        proxies.insert(0, "X2 uses other_equity as a proxy for retained earnings: no page-verified retained earnings "
                          f"for {fy} ({scope}) in retained_earnings.json.")
        ins.fallbacks.append(f"retained_earnings[{fy}]: not available for scope {scope}; X2 uses other_equity")
    basis = "single year; latest reported values (financials.json, retained_earnings.json)"
    extra = {"x2_numerator": x2_basis}
    if ins.missing:
        return _result("altman_z", fy, scope, ins, basis, proxies, extra={**extra, "reason": "missing inputs: " + "; ".join(ins.missing)})
    x = {"X1": _div(ca - cl, ta), "X2": _div(re_v, ta), "X3": _div(pbt + fc, ta), "X4": _div(te, ta - te)}
    bad = [k for k, v in x.items() if v is None]
    if bad:
        ins.missing.append(f"division by zero in {', '.join(bad)}")
        return _result("altman_z", fy, scope, ins, basis, proxies, components={k: _r(v) for k, v in x.items()},
                       extra={**extra, "reason": "; ".join(ins.missing)})
    z = sum(ALTMAN_W[k] * v for k, v in x.items())
    return _result("altman_z", fy, scope, ins, basis, proxies, round(z, 4), altman_zone(z), {k: _r(v) for k, v in x.items()},
                   {**extra, "thresholds": "> 2.60 safe; 1.10-2.60 grey; < 1.10 distress", "weights": ALTMAN_W})


# ---------- Piotroski F-score ----------
def piotroski_label(f):
    if f is None: return None
    return "strong" if f >= 8 else ("average" if f >= 5 else "weak")

def piotroski_f(fy, scope="consolidated"):
    """Nine binary signals for year t vs t-1; t and t-1 from the report of year t."""
    proxies = ["Signal 8 gross margin: " + GM_PROXY,
               "Signal 5 leverage uses year-end non_current_borrowings / year-end total_assets of each year."]
    t1 = prev_fy(fy)
    ins = _Inputs(scope, report=fy)
    basis = f"{fy} vs {t1}, both as presented in the {fy} report"
    if t1 is None or fy not in FIN_REP:
        ins.missing.append(f"no {fy} report with {t1 or 'prior-year'} comparatives")
        return _result("piotroski_f", fy, scope, ins, basis, proxies, extra={"reason": "; ".join(ins.missing)})
    g = lambda k, y: ins.get(k, y)
    ta_t, ta_1 = g("total_assets", fy), g("total_assets", t1)
    ni_t, ni_1 = g("profit_for_the_year", fy), g("profit_for_the_year", t1)
    cfo_t = g("net_cash_from_operating", fy)
    ncb_t, ncb_1 = g("non_current_borrowings", fy), g("non_current_borrowings", t1)
    ca_t, ca_1 = g("total_current_assets", fy), g("total_current_assets", t1)
    cl_t, cl_1 = g("total_current_liabilities", fy), g("total_current_liabilities", t1)
    sc_t, sc_1 = g("equity_share_capital", fy), g("equity_share_capital", t1)
    rev_t, rev_1 = g("revenue_from_operations", fy), g("revenue_from_operations", t1)
    cm_t, cm_1 = g("cost_of_materials_consumed", fy), g("cost_of_materials_consumed", t1)
    # t-2 is normally not in report t (financials.json fallback, recorded); if absent everywhere, use t-1 and disclose
    t2 = prev_fy(t1)
    ta_2 = ins.get("total_assets", t2, required=False)
    if ta_2 is None and ta_1 is not None:
        ta_2 = ta_1
        proxies.append(f"total_assets for {t2 or f'FY{int(t1[2:6]) - 1}-{t1[4:6]}'} is unavailable, so ROA and asset turnover for "
                       f"{t1} (signals 3 and 9) use total_assets of {t1} instead of beginning-of-year assets.")
    if ins.missing:
        return _result("piotroski_f", fy, scope, ins, basis, proxies, extra={"reason": "missing inputs: " + "; ".join(ins.missing)})
    roa_t, roa_1 = _div(ni_t, ta_1), _div(ni_1, ta_2)
    cfo_a = _div(cfo_t, ta_1)
    lev_t, lev_1 = _div(ncb_t, ta_t), _div(ncb_1, ta_1)
    cr_t, cr_1 = _div(ca_t, cl_t), _div(ca_1, cl_1)
    gm_t, gm_1 = _div(rev_t - cm_t, rev_t), _div(rev_1 - cm_1, rev_1)
    at_t, at_1 = _div(rev_t, ta_1), _div(rev_1, ta_2)
    spec = [  # key, description, current, comparison, test
        ("F1_roa_positive", "ROA_t = profit_t / total_assets_{t-1} > 0", roa_t, 0.0, lambda a, b: a > b),
        ("F2_cfo_positive", "CFO_t > 0", cfo_t, 0.0, lambda a, b: a > b),
        ("F3_roa_improved", "ROA_t > ROA_{t-1}", roa_t, roa_1, lambda a, b: a > b),
        ("F4_accruals", "CFO_t / total_assets_{t-1} > ROA_t", cfo_a, roa_t, lambda a, b: a > b),
        ("F5_leverage_decreased", "non_current_borrowings / total_assets decreased", lev_t, lev_1, lambda a, b: a < b),
        ("F6_current_ratio_increased", "current ratio increased", cr_t, cr_1, lambda a, b: a > b),
        ("F7_no_new_equity", "equity_share_capital did not increase", sc_t, sc_1, lambda a, b: a <= b),
        ("F8_gross_margin_increased", "gross margin (proxy) increased", gm_t, gm_1, lambda a, b: a > b),
        ("F9_asset_turnover_increased", "revenue / beginning total_assets increased", at_t, at_1, lambda a, b: a > b)]
    signals, bad = {}, []
    for key, desc, a, b, test in spec:
        if a is None or b is None:
            bad.append(key); signals[key] = {"description": desc, "signal": None, "current": _r(a), "comparison": _r(b)}
        else:
            signals[key] = {"description": desc, "signal": int(test(a, b)), "current": _r(a), "comparison": _r(b)}
    if bad:
        ins.missing.append(f"division by zero in {', '.join(bad)}")
        return _result("piotroski_f", fy, scope, ins, basis, proxies, components=signals, extra={"reason": "; ".join(ins.missing)})
    f = sum(s["signal"] for s in signals.values())
    return _result("piotroski_f", fy, scope, ins, basis, proxies, f, piotroski_label(f), signals,
                   {"thresholds": "8-9 strong; 5-7 average; 0-4 weak"})


# ---------- Beneish M-score (8-variable) ----------
BENEISH_W = {"DSRI": 0.920, "GMI": 0.528, "AQI": 0.404, "SGI": 0.892, "DEPI": 0.115, "SGAI": -0.172, "TATA": 4.679, "LVGI": -0.327}
BENEISH_C = -4.84

def beneish_label(m):
    if m is None: return None
    return "possible earnings manipulation flag" if m > -1.78 else "unlikely manipulator"

def beneish_m(fy, scope="consolidated"):
    """M = -4.84 + 0.920 DSRI + 0.528 GMI + 0.404 AQI + 0.892 SGI + 0.115 DEPI - 0.172 SGAI + 4.679 TATA - 0.327 LVGI."""
    proxies = ["GMI gross margin: " + GM_PROXY,
               "SGAI uses other_expenses as a proxy for SG&A (SG&A is not presented separately under Ind AS).",
               "AQI hard assets = total_current_assets + property_plant_equipment + non_current_investments "
               "(capital work-in-progress, goodwill and other intangibles count as 'soft' assets).",
               "LVGI leverage = (total_current_liabilities + non_current_borrowings) / total_assets."]
    t1 = prev_fy(fy)
    ins = _Inputs(scope, report=fy)
    basis = f"{fy} vs {t1}, both as presented in the {fy} report"
    if t1 is None or fy not in FIN_REP:
        ins.missing.append(f"no {fy} report with {t1 or 'prior-year'} comparatives")
        return _result("beneish_m", fy, scope, ins, basis, proxies, extra={"reason": "; ".join(ins.missing)})
    v = {}
    for k in ("trade_receivables", "revenue_from_operations", "cost_of_materials_consumed", "total_current_assets",
              "property_plant_equipment", "non_current_investments", "total_assets", "depreciation_amortisation",
              "other_expenses", "total_current_liabilities", "non_current_borrowings"):
        v[k] = (ins.get(k, fy), ins.get(k, t1))
    ni, cfo = ins.get("profit_for_the_year", fy), ins.get("net_cash_from_operating", fy)
    if ins.missing:
        return _result("beneish_m", fy, scope, ins, basis, proxies, extra={"reason": "missing inputs: " + "; ".join(ins.missing)})
    def per(i, fn):
        return fn({k: x[i] for k, x in v.items()})
    rec = lambda d: _div(d["trade_receivables"], d["revenue_from_operations"])
    gm = lambda d: _div(d["revenue_from_operations"] - d["cost_of_materials_consumed"], d["revenue_from_operations"])
    aq = lambda d: (None if _div(d["total_current_assets"] + d["property_plant_equipment"] + d["non_current_investments"], d["total_assets"]) is None
                    else 1 - (d["total_current_assets"] + d["property_plant_equipment"] + d["non_current_investments"]) / d["total_assets"])
    dep = lambda d: _div(d["depreciation_amortisation"], d["depreciation_amortisation"] + d["property_plant_equipment"])
    sga = lambda d: _div(d["other_expenses"], d["revenue_from_operations"])
    lev = lambda d: _div(d["total_current_liabilities"] + d["non_current_borrowings"], d["total_assets"])
    ratios = {"receivables_to_revenue": rec, "gross_margin": gm, "soft_asset_share": aq, "depreciation_rate": dep,
              "other_expenses_to_revenue": sga, "leverage": lev}
    underlying = {n: {"current": _r(per(0, fn)), "prior": _r(per(1, fn))} for n, fn in ratios.items()}
    c, p = {n: per(0, fn) for n, fn in ratios.items()}, {n: per(1, fn) for n, fn in ratios.items()}
    idx = {"DSRI": _div(c["receivables_to_revenue"], p["receivables_to_revenue"]),
           "GMI": _div(p["gross_margin"], c["gross_margin"]),
           "AQI": _div(c["soft_asset_share"], p["soft_asset_share"]),
           "SGI": _div(v["revenue_from_operations"][0], v["revenue_from_operations"][1]),
           "DEPI": _div(p["depreciation_rate"], c["depreciation_rate"]),
           "SGAI": _div(c["other_expenses_to_revenue"], p["other_expenses_to_revenue"]),
           "LVGI": _div(c["leverage"], p["leverage"]),
           "TATA": _div(ni - cfo, v["total_assets"][0])}
    bad = [k for k, x in idx.items() if x is None]
    comps = {k: _r(x) for k, x in idx.items()}
    if bad:
        ins.missing.append(f"undefined (division by zero) in {', '.join(bad)}")
        return _result("beneish_m", fy, scope, ins, basis, proxies, components=comps,
                       extra={"reason": "; ".join(ins.missing), "underlying_ratios": underlying})
    m = BENEISH_C + sum(BENEISH_W[k] * x for k, x in idx.items())
    return _result("beneish_m", fy, scope, ins, basis, proxies, round(m, 4), beneish_label(m), comps,
                   {"thresholds": "M > -1.78 possible earnings manipulation flag; otherwise unlikely manipulator",
                    "weights": BENEISH_W, "constant": BENEISH_C, "underlying_ratios": underlying})


SCORES = {"altman_z": altman_z, "piotroski_f": piotroski_f, "beneish_m": beneish_m}

def _safe(fn, fy, scope):
    """Never raise: an unexpected error becomes score None with a reason."""
    try: return fn(fy, scope)
    except Exception as e:
        return {"score_name": fn.__name__, "fiscal_year": fy, "scope": scope, "score": None, "interpretation": None,
                "components": {}, "inputs": {}, "proxies": [], "fallbacks": [], "missing": [f"error: {e}"], "reason": f"error: {e}"}

def all_scores(scope="consolidated", fiscal_years=None):
    """Every score for every requested year (default FY2022-23..FY2025-26)."""
    fys = list(fiscal_years or SCORE_YEARS)
    return {"scope": scope, "years": fys, "scores": {n: {fy: _safe(fn, fy, scope) for fy in fys} for n, fn in SCORES.items()}}
