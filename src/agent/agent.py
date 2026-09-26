"""Financial analysis agent: Ollama Cloud LLM + tool loop, with an automatic numeric grounding check.

Every number in the final answer must match a number returned by a tool (line items, calculator, or
retrieved passages), within rounding. Unsupported numbers are sent back to the model to fetch or remove.
"""
import json, math, os, re, sys
from pathlib import Path
from dotenv import load_dotenv
from ollama import Client
sys.path.insert(0, str(Path(__file__).resolve().parent))
from tools import FUNCS, SCHEMAS

load_dotenv(Path(__file__).resolve().parents[2] / ".env")
client = Client(host="https://ollama.com", headers={"Authorization": "Bearer " + os.environ["OLLAMA_API_KEY"]})
MODELS = ["gpt-oss:120b", "gemma4:31b"]

SYSTEM = """You are a senior financial analyst assistant for Tata Steel Limited. You answer ONLY from Tata Steel's annual
reports for FY2022-23, FY2023-24, FY2024-25 and FY2025-26 (comparative columns also give FY2021-22 figures).

RULES
1. Every number you state must come from a tool result. Use get_financials FIRST for balance sheet, profit and loss and cash flow
   figures (exact rows for every year plus exact year-on-year changes); use get_line_items only for items it lacks. Use search_documents for notes, segments, borrowings detail, risks, management commentary and auditor matters.
2. NEVER do arithmetic in your head. Use calculate for every ratio, difference, percentage, average and growth rate.
   Batch all calculations into ONE calculate call, separated by ';'.
3. Default to CONSOLIDATED figures unless the user asks for standalone. Always say which you used.
4. Cite every figure: report, statement or section, and page, e.g. (FY2025-26 AR, consolidated balance sheet, p. F143).
5. If a value is marked restated, use the restated value and mention the originally reported figure.
6. If the answer is not in these reports (another company, a year before FY2021-22, forecasts or future values),
   say so clearly and do not guess.
7. Interpret: explain what the numbers mean and what drove them, not just the numbers.
8. If a tool returns no useful result, rephrase or use fewer filters and try again. Only after an unfiltered
   search_documents also finds nothing may you say you could not find it - phrase it as "I could not find this
   in the reports", never "the report does not contain". Never conclude absence from a filtered search.
9. To explain what drove a change, FIRST fetch the underlying line items (e.g. inventories, trade receivables,
   current borrowings, trade payables) with ONE get_financials call, and quote its yoy_changes exactly, sign included. Never quote approximate figures you have not retrieved,
   and never attribute causes (e.g. a borrowing surge) that no retrieved source states.
10. When listing items from a document (e.g. key audit matters), list each item exactly once and count accurately.
11. Never attribute reasons to management, MD&A, commentary or "the report" unless you retrieved that passage with
    search_documents in this conversation, and cite its page. Do not put tool names or bracket tags like 【...】 in answers.
12. Use compute_metric for every ratio or derived metric across years (write the formula; the tool computes it), including
    percentage changes of ratios. Present figures by pasting the 'table' / 'changes_table' returned by get_financials and
    compute_metric VERBATIM; never retype numbers into a table of your own. In prose, copy numbers exactly from those tables.

STANDARD DEFINITIONS (state the definition you used)
- Current ratio = Total current assets / Total current liabilities
- Total debt = non_current_borrowings + current_borrowings (lease liabilities shown separately if relevant)
- Debt-to-equity = Total debt / Total equity
- Net profit margin = Profit for the year / Revenue from operations
- Interest coverage = (Profit before tax + Finance costs) / Finance costs
- ROE = Profit for the year / Average total equity (average of opening and closing)
- YoY change % = (Current - Prior) / Prior * 100
Answer in clear prose with a small table where it helps."""

# ---------- numeric grounding ----------
IGNORE = re.compile(
    r"FY\s?'?\d{2,4}(?:\s?[-–‑—]\s?\d{2,4})?|\bF\d{1,3}\b|(?:pp?\.|page|PDF p)\s?\d+(?:\s?[-–‑—]\s?F?\d+)?|"
    r"Note\s+\d+[A-Za-z]?(?:\([a-z]\))?|(?:ISA|Ind AS|SA|AS|Section|Schedule)\s?\d+|\b(?:19|20)\d{2}\b|\d+(?:st|nd|rd|th)\b",
    re.I)

SIGNED = re.compile(r"(?:(?<![\w.])([+\-–−])\s?)?(\d[\d,]*(?:\.\d+)?)")

def numbers_in(text, signed=False):
    """Numbers in text (years, pages, notes, small counters ignored). signed=True -> [(value, had_explicit_sign)]."""
    t = re.sub(r"(?<=\d)[\s\u00a0\u202f\u2009](?=\d{3}(?:\D|$))", "", str(text))
    t = IGNORE.sub(" ", t)
    out = []
    for m in SIGNED.finditer(t):
        s = m.group(2).rstrip(",")
        try: v = float(s.replace(",", ""))
        except ValueError: continue
        if not ("." in s or v >= 13): continue
        neg = m.group(1) in ("-", "–", "−")
        out.append(((-v if neg else v), m.group(1) is not None) if signed else v)
    return out

def collect(obj, pools):
    """Add every number a tool returned to (signed pool, absolute pool). '(1,147.04)' counts as negative."""
    sgn, ab = pools
    if isinstance(obj, bool): return
    if isinstance(obj, (int, float)):
        sgn.add(float(obj)); ab.add(abs(float(obj)))
    elif isinstance(obj, str):
        for v, _ in numbers_in(obj, signed=True): sgn.add(v); ab.add(abs(v))
        for m in re.finditer(r"\((\d[\d,]*\.\d+)\)", obj):
            v = float(m.group(1).replace(",", "")); sgn.add(-v); ab.add(v)
    elif isinstance(obj, dict):
        for v in obj.values(): collect(v, pools)
    elif isinstance(obj, list):
        for v in obj: collect(v, pools)

def close(v, c):
    """v equals c (or c as a percentage/fraction) exactly, or rounded/truncated to 0-2 decimals."""
    for x in (c, c * 100, c / 100):
        if x == v: return True
        for d in (0, 1, 2, 3, 4):
            if round(x, d) == v or math.trunc(x * 10 ** d) / 10 ** d == v: return True
    return False

def grounded(v, explicit_sign, pools):
    sgn, ab = pools
    if explicit_sign: return any(close(v, c) for c in sgn)        # '+7,638' must match a +7,638 source
    return any(close(abs(v), c) for c in ab)

CLAIMS = [(r"inventor", "inventories"), (r"receivable", "trade_receivables"), (r"borrowing", "current_borrowings / non_current_borrowings"),
          (r"payable", "trade_payables"), (r"\bcash and cash equivalents\b|\bcash balance", "cash_and_cash_equivalents")]
DOC_ATTR = re.compile(r"management discussion|md&a|commentary|management (notes|cites|highlights|says|attribut|state)|"
                      r"report (notes|states|highlights|cites|mentions|attributes)|according to (the )?(report|management)", re.I)

def unsupported_claims(answer, trace):
    """Rule-based check for claims without evidence: document attributions without a search, drivers never fetched."""
    fetched = " ".join(json.dumps(t["args"]).lower() for t in trace)
    issues = []
    if DOC_ATTR.search(answer) and not any(t["tool"] == "search_documents" for t in trace):
        issues.append("You attribute statements to MD&A/commentary/management but never retrieved a passage with search_documents.")
    for rx, item in CLAIMS:
        if re.search(rx, answer, re.I) and not re.search(rx, fetched):
            issues.append(f"You discuss '{rx.split('|')[0].strip(chr(92) + 'b')}' but never retrieved it (use get_financials: {item}).")
    return issues

def chat(msgs, use_tools=True):
    last = None
    for m in MODELS:
        try:
            return client.chat(model=m, messages=msgs, tools=SCHEMAS if use_tools else None, options={"temperature": 0.1})
        except Exception as e:
            last = e
            print(f"  [model {m} failed: {str(e)[:100]}]", flush=True)
    raise last

def finish(answer, nums, bad, trace, fixes, note=""):
    n_ok = len([n for n in nums if n not in bad])
    footer = f"\n\n---\nVerification: {n_ok}/{len(nums)} figures grounded in source data."
    if bad: footer += f"\n⚠ Could not verify: {bad}"
    if note: footer += f"\n⚠ {note}"
    return answer + footer, {"trace": trace, "grounded": n_ok, "total": len(nums), "unverified": bad, "fix_rounds": fixes}

def ask(question, max_steps=24, max_fixes=2, verbose=True):
    msgs = [{"role": "system", "content": SYSTEM}, {"role": "user", "content": question}]
    trace, pools, fixes, last = [], (set(), set()), 0, None
    collect(question, pools)
    for step in range(max_steps):
        final_step = step == max_steps - 1
        if step == max_steps - 3:
            msgs.append({"role": "user", "content": "You are close to the step limit. Stop calling tools unless essential "
                         "and write the complete final answer now, using only the data already retrieved."})
        r = chat(msgs, use_tools=not final_step)
        msgs.append(r.message)
        if r.message.tool_calls and not final_step:
            for c in r.message.tool_calls:
                name, args = c.function.name, dict(c.function.arguments)
                try: result = FUNCS[name](**args)
                except Exception as e: result = {"error": str(e)}
                collect(result, pools)
                trace.append({"tool": name, "args": args})
                if verbose: print(f"  -> {name}({json.dumps(args)[:140]})", flush=True)
                msgs.append({"role": "tool", "tool_name": name, "content": json.dumps(result, ensure_ascii=False)[:12000]})
            continue
        answer = r.message.content or ""
        found = numbers_in(answer, signed=True)
        nums = [v for v, _ in found]
        bad = sorted({v for v, ex in found if not grounded(v, ex, pools)})
        issues = unsupported_claims(answer, trace)
        last = (answer, nums, bad)
        if (bad or issues) and fixes < max_fixes and not final_step:
            fixes += 1
            if verbose: print(f"  [verification: {len(bad)} unsupported numbers {bad[:6]}, {len(issues)} unsupported claims -> asking model to fix]", flush=True)
            msg = "VERIFICATION FAILED. "
            if bad: msg += f"These numbers in your answer do not match any tool result: {bad}. "
            if issues: msg += "Unsupported claims: " + " ".join(issues) + " "
            msg += ("Retrieve the evidence with tools (get_financials, get_line_items, search_documents, calculate) or remove "
                    "the claim. Then give the complete corrected answer.")
            msgs.append({"role": "user", "content": msg})
            continue
        return finish(answer, nums, bad, trace, fixes, note=("Unsupported claims: " + " ".join(issues)) if issues else "")
    if last: return finish(*last, trace, fixes, note="Step limit reached; this is the last draft.")
    return "I could not complete this analysis within the step limit.", {"trace": trace, "grounded": 0, "total": 0, "unverified": [], "fix_rounds": fixes}

if __name__ == "__main__":
    answer, _ = ask(" ".join(sys.argv[1:]))
    print("\n" + answer)
