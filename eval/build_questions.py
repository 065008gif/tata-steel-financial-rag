"""Build the evaluation set (eval/questions.json). Expected numbers come from the verified statement data;
every raw input behind them is then cross-checked against the text of its cited PDF page."""
import json, sys
from pathlib import Path
import pymupdf
sys.path.insert(0, "src/agent")
from tools import FIN, compute_metric, _inr

C, S = "consolidated", "standalone"
Y4 = ["FY2022-23", "FY2023-24", "FY2024-25", "FY2025-26"]
Y5 = ["FY2021-22"] + Y4

def inp(key, fy, sc=C):
    v = FIN[sc][key]["values"][fy]
    return {"item": key, "fiscal_year": fy, "scope": sc, "value": v["value"], "report": v["report"],
            "pdf_page": v["pdf_page"], "page_label": v["source"].split("page ")[-1].split(" ")[0],
            "components": v.get("components")}
def val(key, fy, sc=C): return FIN[sc][key]["values"][fy]["value"]
def metric(formula, fys, sc=C, d=4):
    r = compute_metric(formula, scope=sc, fiscal_years=fys, decimals=d)
    return [r["values"][fy] for fy in fys]

Q = []
def add(qid, cat, q, expected=(), inputs=(), must_abstain=False, must_mention=(), sources=(), note=""):
    Q.append(dict(id=qid, category=cat, question=q, expected_numbers=[round(x, 4) for x in expected],
                  inputs=list(inputs), must_abstain=must_abstain, must_mention=list(must_mention),
                  expected_sources=list(sources), note=note))

# A. single-year lookups
add("A1", "lookup", "What was Tata Steel's consolidated revenue from operations in FY2025-26?",
    [val("revenue_from_operations", "FY2025-26")], [inp("revenue_from_operations", "FY2025-26")])
add("A2", "lookup", "What were Tata Steel's consolidated total assets as at 31 March 2026?",
    [val("total_assets", "FY2025-26")], [inp("total_assets", "FY2025-26")])
add("A3", "lookup", "What was Tata Steel's standalone profit for the year in FY2025-26?",
    [val("profit_for_the_year", "FY2025-26", S)], [inp("profit_for_the_year", "FY2025-26", S)])
add("A4", "lookup", "What were Tata Steel's consolidated non-current borrowings as at 31 March 2026?",
    [val("non_current_borrowings", "FY2025-26")], [inp("non_current_borrowings", "FY2025-26")])
add("A5", "lookup", "What were Tata Steel's consolidated inventories as at 31 March 2024?",
    [val("inventories", "FY2023-24")], [inp("inventories", "FY2023-24")])
add("A6", "lookup", "What were Tata Steel's consolidated finance costs in FY2023-24?",
    [val("finance_costs", "FY2023-24")], [inp("finance_costs", "FY2023-24")])
add("A7", "table_grounded", "What were Tata Steel's consolidated trade payables as at 31 March 2026, and what are their components?",
    [val("trade_payables", "FY2025-26")] + list(FIN[C]["trade_payables"]["values"]["FY2025-26"]["components"].values()),
    [inp("trade_payables", "FY2025-26")])
# B. multi-year trends
add("B1", "trend", "Show Tata Steel's consolidated revenue from operations for FY2021-22 to FY2025-26 and describe the trend.",
    [val("revenue_from_operations", y) for y in Y5], [inp("revenue_from_operations", y) for y in Y5])
add("B2", "trend", "How has Tata Steel's consolidated net profit margin changed from FY2022-23 to FY2025-26?",
    metric("profit_for_the_year / revenue_from_operations * 100", Y4, d=2),
    [inp(k, y) for y in Y4 for k in ("profit_for_the_year", "revenue_from_operations")])
add("B3", "trend", "How has Tata Steel's consolidated EBITDA margin moved from FY2022-23 to FY2025-26? Define EBITDA as profit "
    "before exceptional items and tax + finance costs + depreciation and amortisation - other income.",
    metric("(profit_before_exceptional_and_tax + finance_costs + depreciation_amortisation - other_income) / revenue_from_operations * 100", Y4, d=2),
    [inp(k, y) for y in Y4 for k in ("profit_before_exceptional_and_tax", "finance_costs", "depreciation_amortisation", "other_income")])
# C. ratio computation
add("C1", "ratio", "Compute Tata Steel's consolidated current ratio for each year from FY2022-23 to FY2025-26.",
    metric("total_current_assets / total_current_liabilities", Y4),
    [inp(k, y) for y in Y4 for k in ("total_current_assets", "total_current_liabilities")])
add("C2", "ratio", "What was Tata Steel's consolidated debt-to-equity ratio each year from FY2022-23 to FY2025-26?",
    metric("(non_current_borrowings + current_borrowings) / total_equity", Y4),
    [inp(k, y) for y in Y4 for k in ("non_current_borrowings", "current_borrowings", "total_equity")])
add("C3", "ratio", "What was Tata Steel's consolidated interest coverage ratio each year from FY2022-23 to FY2025-26?",
    metric("(profit_before_tax + finance_costs) / finance_costs", Y4),
    [inp(k, y) for y in Y4 for k in ("profit_before_tax", "finance_costs")])
add("C4", "ratio", "What was Tata Steel's consolidated return on equity in FY2025-26, using average equity?",
    metric("profit_for_the_year / avg(total_equity) * 100", ["FY2025-26"], d=2),
    [inp("profit_for_the_year", "FY2025-26"), inp("total_equity", "FY2025-26"), inp("total_equity", "FY2024-25")])
add("C5", "ratio", "Compare Tata Steel's consolidated receivable days in FY2024-25 and FY2025-26 (trade receivables / revenue x 365).",
    metric("trade_receivables / revenue_from_operations * 365", ["FY2024-25", "FY2025-26"], d=2),
    [inp(k, y) for y in ("FY2024-25", "FY2025-26") for k in ("trade_receivables", "revenue_from_operations")])
# D. comparative / year-over-year
tb = lambda y: val("non_current_borrowings", y) + val("current_borrowings", y)
chg = tb("FY2025-26") - tb("FY2024-25")
add("D1", "yoy", "How much did Tata Steel's consolidated total borrowings change between FY2024-25 and FY2025-26, in absolute and percentage terms?",
    [tb("FY2024-25"), tb("FY2025-26"), chg, chg / tb("FY2024-25") * 100],
    [inp(k, y) for y in ("FY2024-25", "FY2025-26") for k in ("non_current_borrowings", "current_borrowings")])
g = lambda sc: (val("revenue_from_operations", "FY2025-26", sc) / val("revenue_from_operations", "FY2024-25", sc) - 1) * 100
add("D2", "yoy", "Compare the growth in standalone and consolidated revenue from operations in FY2025-26. What does the gap suggest?",
    [g(S), g(C)], [inp("revenue_from_operations", y, sc) for sc in (S, C) for y in ("FY2024-25", "FY2025-26")])
# E. composite
dup = []
for y in ("FY2023-24", "FY2025-26"):
    dup += metric("profit_for_the_year / revenue_from_operations * 100", [y], d=2) + metric("revenue_from_operations / avg(total_assets)", [y]) \
         + metric("avg(total_assets) / avg(total_equity)", [y])
add("E1", "composite", "Break down Tata Steel's consolidated ROE for FY2023-24 and FY2025-26 using DuPont analysis "
    "(net margin x asset turnover x equity multiplier, using average assets and equity).", dup,
    [inp(k, y) for y in ("FY2022-23", "FY2023-24", "FY2024-25", "FY2025-26") for k in ("total_assets", "total_equity")])
# F. segments, G. narrative and risk (graded on content, not fixed numbers)
add("F1", "segment", "What was the EBITDA of Tata Steel's India, Netherlands and UK segments in FY2025-26?",
    [33035.63, 2721.52, -2568.99], must_mention=["India", "Netherlands", "UK"],
    sources=[{"report": "FY2025-26", "page_label": "F256"}],
    note="Reported as 'Segment results before exceptional items, interest, tax and depreciation' (segment EBITDA), note 43, "
         "F256; definition F258. Verified: segments sum to 34,847.73 and reconcile to PBEIT 17,001.15.")
add("G1", "risk_evolution", "What new risks appear in Tata Steel's FY2025-26 annual report that were not discussed in the FY2022-23 report?",
    note="Graded by hand against the risk sections of both reports.")
add("G2", "narrative", "How does management explain the losses and restructuring of Tata Steel UK?",
    must_mention=["electric arc furnace"], note="Graded by hand.")
add("G3", "narrative", "What key audit matters did the auditor raise on the FY2025-26 consolidated financial statements?",
    must_mention=["litigation", "Nederland"], sources=[{"report": "FY2025-26", "page_label": "F131"}])
# H. traps
add("H1", "scope_trap", "What was Tata Steel's revenue in FY2025-26?", [val("revenue_from_operations", "FY2025-26")],
    [inp("revenue_from_operations", "FY2025-26")], must_mention=["consolidated"])
add("H2", "abstain", "What will Tata Steel's revenue be in FY2027-28?", must_abstain=True)
add("H3", "abstain", "What was JSW Steel's total debt as at 31 March 2026?", must_abstain=True)
add("H4", "abstain", "What was Tata Steel's revenue from operations in FY2009-10?", must_abstain=True)
# I. verdict
add("I1", "verdict", "Give an overall financial health verdict for Tata Steel (consolidated) across FY2022-23 to FY2025-26, "
    "covering liquidity, leverage, profitability and cash flow.", must_mention=["liquidity", "leverage", "profitab"],
    note="Graded by hand; grounding statistics recorded automatically.")

# E2-E4: composite scores (values from src/analysis/scores.py, independently verified; see docs/claude_code/README.md)
sys.path.insert(0, "src/analysis")
from scores import altman_z, piotroski_f, beneish_m
AZ = ("total_current_assets", "total_current_liabilities", "total_assets", "other_equity", "profit_before_tax", "finance_costs", "total_equity")
add("E2", "composite", "Calculate Tata Steel's consolidated Altman Z'' score for FY2024-25 and FY2025-26 and interpret the zone.",
    [altman_z(y, C)["score"] for y in ("FY2024-25", "FY2025-26")], [inp(k, y) for y in ("FY2024-25", "FY2025-26") for k in AZ],
    must_mention=[(lambda r: r.get("zone") or r.get("interpretation"))(altman_z("FY2025-26", C))])
add("E3", "composite", "What is Tata Steel's consolidated Piotroski F-score for FY2025-26, and what does it indicate?",
    [], [inp(k, y) for y in ("FY2024-25", "FY2025-26") for k in ("profit_for_the_year", "total_assets", "net_cash_from_operating")],
    must_mention=["re:\\b" + str(piotroski_f("FY2025-26", C)["score"]) + "\\s*(/|out of)\\s*9\\b|f.?score[^\\n]{0,60}?\\b" + str(piotroski_f("FY2025-26", C)["score"]) + "\\b", "strong"],
    note="Score is a small integer, so it is checked by pattern (e.g. '8/9' or 'F-score of 8').")
add("E4", "composite", "Compute Tata Steel's consolidated Beneish M-score for FY2025-26. Is there an earnings-manipulation flag?",
    [beneish_m("FY2025-26", C)["score"]], [inp(k, y) for y in ("FY2024-25", "FY2025-26") for k in ("trade_receivables", "revenue_from_operations")],
    must_mention=["unlikely"])
Path("eval/questions.json").write_text(json.dumps(Q, indent=1))
print(f"{len(Q)} questions written to eval/questions.json")
from collections import Counter
print("  by category:", dict(Counter(q["category"] for q in Q)))

# independent cross-check: is each raw input figure printed on its cited PDF page?
docs, checked, bad = {}, 0, []
for q in Q:
    for i in q["inputs"]:
        doc = docs.setdefault(i["report"], pymupdf.open(f"data/raw/TataSteel_{i['report']}.pdf"))
        text = " ".join(doc[i["pdf_page"] - 1].get_text().split())
        vals = list(i["components"].values()) if i["components"] else [i["value"]]
        for v in vals:
            checked += 1
            if _inr(abs(v)) not in text:
                bad.append(f'{q["id"]} {i["item"]} {i["fiscal_year"]} {i["scope"]}: {_inr(v)} not found on PDF p{i["pdf_page"]} ({i["page_label"]}, {i["report"]} report)')
print(f"\nPDF cross-check: {checked - len(bad)}/{checked} input figures found printed on their cited page")
for b in sorted(set(bad)): print("  MISSING:", b)
