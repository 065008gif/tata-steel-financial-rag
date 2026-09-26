"""Map verified line items to canonical financial items: exactly one row per item, scope and year.

Fuzzy names let the agent pick the wrong 'Borrowings' row (current vs non-current). Each canonical item is
defined by statement + hierarchy path + label pattern; multi-row items (trade payables) are summed with their
components shown. Output: data/processed/financials.json, plus a coverage table.
"""
import json, re
from collections import defaultdict
from pathlib import Path

PROC = Path("data/processed")
YEARS = ["FY2021-22", "FY2022-23", "FY2023-24", "FY2024-25", "FY2025-26"]
BS, PL, CF = "balance_sheet", "profit_and_loss", "cash_flow"
RULES = [  # key, statement, path regex (None = any), label regex, description
    ("total_assets", BS, None, r"^total assets$", "Total assets"),
    ("total_equity", BS, None, r"^total equity$", "Total equity"),
    ("total_non_current_assets", BS, None, r"^total non-current assets$", "Total non-current assets"),
    ("total_current_assets", BS, None, r"^total current assets$", "Total current assets"),
    ("total_non_current_liabilities", BS, None, r"^total non-current liabilities$", "Total non-current liabilities"),
    ("total_current_liabilities", BS, None, r"^total current liabilities$", "Total current liabilities"),
    ("property_plant_equipment", BS, r"^non-current assets", r"^property, plant and equipment", "Property, plant and equipment"),
    ("capital_work_in_progress", BS, r"^non-current assets", r"^capital work-in-progress", "Capital work-in-progress"),
    ("goodwill", BS, r"^non-current assets", r"^goodwill", "Goodwill"),
    ("non_current_investments", BS, r"^non-current assets", r"^investments$", "Non-current investments"),
    ("inventories", BS, r"^current assets", r"^inventories$", "Inventories"),
    ("current_investments", BS, r"^current assets", r"^investments$", "Current investments"),
    ("trade_receivables", BS, r"^current assets", r"^trade receivables", "Trade receivables"),
    ("cash_and_cash_equivalents", BS, r"^current assets", r"^cash and cash equivalents", "Cash and cash equivalents"),
    ("other_bank_balances", BS, r"^current assets", r"^other balances with banks", "Other balances with banks"),
    ("equity_share_capital", BS, None, r"^equity share capital", "Equity share capital"),
    ("other_equity", BS, None, r"^other equity", "Other equity"),
    ("non_controlling_interests", BS, None, r"^non-controlling interests$", "Non-controlling interests"),
    ("non_current_borrowings", BS, r"^non-current liabilities", r"^borrowings$", "Non-current borrowings"),
    ("current_borrowings", BS, r"^current liabilities", r"^borrowings$", "Current borrowings"),
    ("non_current_lease_liabilities", BS, r"^non-current liabilities", r"^lease liabilities$", "Non-current lease liabilities"),
    ("current_lease_liabilities", BS, r"^current liabilities", r"^lease liabilities$", "Current lease liabilities"),
    ("revenue_from_operations", PL, None, r"^revenue from operations", "Revenue from operations"),
    ("other_income", PL, None, r"^other income", "Other income"),
    ("total_income", PL, None, r"^total income", "Total income"),
    ("cost_of_materials_consumed", PL, None, r"^cost of materials consumed", "Cost of materials consumed"),
    ("employee_benefits_expense", PL, None, r"^employee benefits? expense", "Employee benefits expense"),
    ("finance_costs", PL, None, r"^finance costs", "Finance costs"),
    ("depreciation_amortisation", PL, None, r"^depreciation and amorti[sz]ation", "Depreciation and amortisation expense"),
    ("other_expenses", PL, None, r"^other expenses", "Other expenses"),
    ("total_expenses", PL, None, r"^total expenses", "Total expenses"),
    ("exceptional_items", PL, None, r"^total exceptional items$|^exceptional items( \(net\))?$", "Exceptional items (net)"),
    ("profit_before_exceptional_and_tax", PL, None, r"before exceptional items and tax", "Profit/(loss) before exceptional items and tax"),
    ("profit_before_tax", PL, None, r"^profit/?\s?\(?loss\)? before tax(es)?\s*(\(.*\))?$|^profit before tax(es)?\s*(\(.*\))?$", "Profit/(loss) before tax"),
    ("tax_expense", PL, None, r"^total tax expense|^tax expense", "Tax expense"),
    ("profit_for_the_year", PL, None, r"^profit/?\s?\(?loss\)? for the (year|period)\s*(\(.*\))?$|^profit for the year\s*(\(.*\))?$", "Profit/(loss) for the year"),
    ("net_cash_from_operating", CF, None, r"^net cash (from|generated).*operating activities", "Net cash from operating activities"),
    ("net_cash_from_investing", CF, None, r"^net cash.*investing activities", "Net cash from/(used in) investing activities"),
    ("net_cash_from_financing", CF, None, r"^net cash.*financing activities", "Net cash from/(used in) financing activities"),
    ("purchase_of_capital_assets", CF, None, r"^purchase of capital assets", "Purchase of capital assets (capex)"),
]
SUMS = [("trade_payables", BS, r"trade payables$", "Trade payables (MSE dues + other creditors + acceptances)")]

recs = [json.loads(l) for l in open(PROC / "line_items.jsonl")]
pref = [r for r in recs if r["preferred"] and not r.get("synthetic_label")]
cite = lambda r: f'{r["report"]} Annual Report, {r["scope"]} {r["statement"].replace("_", " ")}, page {r["page_label"]}'
out = defaultdict(dict)
for key, st, prx, irx, desc in RULES:
    for r in pref:
        if r["statement"] != st or (prx and not re.search(prx, r["path"].lower())) or not re.search(irx, r["line_item"].lower()):
            continue
        slot = out[r["scope"]].setdefault(key, {"description": desc, "values": {}})["values"]
        if r["fiscal_year"] in slot: continue
        v = {"value": r["value"], "source": cite(r), "line_item": r["line_item"]}
        if r["differs_from_original"]: v.update(restated=True, originally_reported=r["original_value"])
        slot[r["fiscal_year"]] = v
for key, st, prx, desc in SUMS:
    groups = defaultdict(list)
    for r in pref:
        if r["statement"] == st and re.search(prx, r["path"].lower()): groups[(r["scope"], r["fiscal_year"])].append(r)
    for (sc, fy), rs in groups.items():
        out[sc].setdefault(key, {"description": desc, "values": {}})["values"][fy] = {
            "value": round(sum(r["value"] for r in rs), 2), "source": cite(rs[0]) + f" (sum of {len(rs)} rows)",
            "components": {r["line_item"]: r["value"] for r in rs}}
(PROC / "financials.json").write_text(json.dumps(out, indent=1))

keys = [k for k, *_ in RULES] + [k for k, *_ in SUMS]
for sc in ("consolidated", "standalone"):
    print(f"\n{sc.upper()} coverage ('.' = found, 'X' = MISSING)          " + "  ".join(y[2:6] for y in YEARS))
    for k in keys:
        vals = out[sc].get(k, {}).get("values", {})
        print(f"  {k:32} " + "  ".join(" .  " if y in vals else " X  " for y in YEARS))
fy = "FY2025-26"
print(f"\nSpot check, consolidated {fy}:")
for k in ("current_borrowings", "non_current_borrowings", "trade_payables", "inventories", "revenue_from_operations", "profit_for_the_year"):
    v = out["consolidated"].get(k, {}).get("values", {}).get(fy)
    print(f"  {k:26} {v['value'] if v else 'MISSING':>12}  {v.get('components', '') if v else ''}")
