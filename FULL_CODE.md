# Edith: full source code

All source files of the financial-rag project in one file (data, results and secrets excluded).

## Contents

1. `src/agent/agent.py`
2. `src/agent/tools.py`
3. `src/analysis/canonical.py`
4. `src/analysis/regions.py`
5. `src/analysis/scores.py`
6. `src/analysis/segments.py`
7. `src/api/main.py`
8. `src/index/build_index.py`
9. `src/ingest/build_chunks.py`
10. `src/ingest/company_facts.py`
11. `src/ingest/line_items.py`
12. `src/ingest/page_map.py`
13. `src/ingest/retained_earnings.py`
14. `src/ingest/run_docling.py`
15. `src/ingest/segments.py`
16. `src/ingest/statement_lines.py`
17. `src/retrieval/search.py`
18. `frontend/Dockerfile`
19. `frontend/index.html`
20. `frontend/nginx.conf`
21. `frontend/package.json`
22. `frontend/src/App.css`
23. `frontend/src/App.jsx`
24. `frontend/src/api.js`
25. `frontend/src/components/AskPage.jsx`
26. `frontend/src/components/DashboardPage.jsx`
27. `frontend/src/components/EvaluationPage.jsx`
28. `frontend/src/components/SourcesPage.jsx`
29. `frontend/src/components/ui.jsx`
30. `frontend/src/index.css`
31. `frontend/src/main.jsx`
32. `frontend/src/readability.css`
33. `frontend/src/useConversations.js`
34. `frontend/vite.config.js`
35. `eval/build_questions.py`
36. `eval/run_eval.py`
37. `tests/test_backend_review.py`
38. `tests/test_scores.py`
39. `tests/test_segments.py`
40. `Dockerfile`
41. `docker-compose.yml`
42. `requirements-api.txt`
43. `scripts/bench_docling.py`
44. `scripts/download_reports.sh`
45. `scripts/model_bakeoff.py`
46. `scripts/test_docling_page.py`
47. `submission/MACHINE_AND_PLATFORM.txt`


---

## `src/agent/agent.py`

```python
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
   Batch all calculations into ONE calculate call, separated by ';'. Write every calculate expression from retrieved
   figures only, e.g. "(279394.80 + 301254.11) / 2" - never type in a number you worked out yourself (an average, a
   difference, a share); such numbers do not count as verified.
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
   current borrowings, trade payables) with ONE get_financials call, and quote its yoy_changes exactly, sign included.
   To explain a change in a total (current assets, current liabilities, expenses...), call breakdown for each pair of
   years and discuss the components with the largest share of the change.
   In breakdown tables, '% change (own YoY)' is the component's own growth and 'Contribution to total change' is its
   share of the total's change. Never report one as the other. Never quote approximate figures you have not retrieved,
   and never attribute causes (e.g. a borrowing surge) that no retrieved source states.
10. When listing items from a document (e.g. key audit matters), list each item exactly once and count accurately.
11. Never attribute reasons to management, MD&A, commentary or "the report" unless you retrieved that passage with
    search_documents in this conversation, and cite its page. Do not put tool names or bracket tags like 【...】 in answers.
12. Use compute_metric for every ratio or derived metric across years (write the formula; the tool computes it), including
    percentage changes of ratios. Present figures by pasting the 'table' / 'changes_table' returned by get_financials and
    compute_metric VERBATIM; never retype numbers into a table of your own. In prose, copy numbers exactly from those tables.
13. Before writing comparative claims ("first time", "highest", "lowest", "only", "record"), check them against the full
    table of values; if a claim is not true for every year shown, do not make it.
14. Fiscal years end on 31 March: FY2023-24 is the year ended 31 March 2024, and balance-sheet values "as at 31 March
    2024" belong to FY2023-24. Convert every date in the question this way before calling tools.
15. Risk evolution questions: FIRST call list_risk_disclosures for EACH report being compared, then use search_documents
    (topic "risk", types ["narrative"]) SEPARATELY for each report. Financial-instrument risk notes (currency, interest,
    credit, liquidity) appear every year and are not enough on their own. For each report
    being compared (queries such as "key risks", "risk management", "principal risks", "emerging risks"). List the named
    risks in each report. Call a risk "new" only if a targeted search of the older report for that specific risk finds no
    discussion of it. Keep business risks (risk management sections) distinct from contingent liabilities (notes).
16. "How does management explain..." questions: search the narrative sections first (types ["narrative"], topics such as
    mdna, strategy, segments, risk) of the relevant reports, then use notes only for supporting figures.
17. Never write approximate figures ("around 7,000", "roughly half"); quote the exact retrieved value.
18. Before saying a measure is not disclosed, check whether the report gives it under another name, and read the relevant
    note's definitions. For example, segment "results" defined as profit before finance cost, depreciation and amortisation,
    exceptional items and tax ARE segment EBITDA; say so and report them under the report's own label.
19. Express multiples (current ratio, debt-to-equity, interest coverage, asset turnover, equity multiplier) as "0.82x",
    and margins, returns and growth rates as percentages.
20. Some note tables have no year columns and give each item as two stacked rows of values (the label may be split across
    them). The FIRST row is the report's current year and the SECOND row is the prior year. Where a total exists, confirm
    the year by reconciling it with the statements (e.g. segment totals against consolidated figures).
21. Altman Z'', Piotroski F and Beneish M scores must come from compute_scores. Never compute them yourself or mix in
    other variants (e.g. the original five-variable Altman Z). Report the tool's score, zone and disclosed proxies.
22. The conversation may include earlier questions and answers. Use them to understand follow-ups ("and FY2023-24?",
    "why?", "compare that with..."), but re-fetch every figure with tools in this turn: numbers from earlier answers are
    not verified sources. If a follow-up is ambiguous, state the interpretation you used.
23. The answer is shown in a chat window that renders Markdown but NOT LaTeX: never use \\( \\) \\[ \\] or commands like
    \\frac. Write any formula in plain text, e.g. "(29,997.19 + 51,576.73) / 92,432.74 = 0.88x". Never mention internal
    tool names (get_financials, calculate, compute_metric, search_documents...); say "computed from the reported figures".
24. Never write approximations for figures: no "≈", "~", "around", "about", "roughly" or "approximately" next to a number.
    Margins, ratios and growth across years: use compute_metric with the REPORTED line items (e.g. the reported profit
    before exceptional items and tax); never rebuild a reported subtotal from other lines (e.g. profit before tax and
    exceptional items), since signs are easy to get wrong. Differences between years: use the change columns that
    get_financials returns. Show percentages with 2 decimals.
    State the exact computed value as the tool returned it (e.g. 2,810.36 crore, 34.81%).
25. DuPont / ROE decomposition questions: call dupont (default average-equity basis, matching the ROE definition below)
    and paste its tables. It returns every intermediate value (average assets and equity, EBIT, each ratio, the product
    check, changes versus the prior year and the composition of the change in equity). Do not compute any other
    intermediate value (a difference, a share, a growth rate) yourself; if you need one it does not return, use calculate.

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
    r"(?<=[×x*/÷])\s?100\b|\b100\s?(?=[×x*])|FY\s?'?\d{2,4}(?:\s?[-–‑—]\s?\d{2,4})?|\b20\d{2}\s?[-–‑—]\s?\d{2,4}\b|\bF\d{1,3}\b|(?:pp?\.|pages?|PDF\s?p(?:age)?\.?)\s?\d+(?:\s?[-–‑—]\s?F?\d+)?|"
    r"Note\s+\d+[A-Za-z]?(?:\([a-z]\))?|\b(?-i:ISA|Ind AS|SA|AS)\s?\d+|\b(?:Section|Schedule)\s+\d+|\b(?:19|20)\d{2}\b|\d+(?:st|nd|rd|th)\b",
    re.I)

DATES = re.compile(r"\b\d{1,2}(?:st|nd|rd|th)?[\s\-–‑]*(?:jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*\.?[\s,\-–‑]*(?:\d{2,4})?"
                   r"|\b(?:jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*\.?\s+\d{1,2}(?:,?\s*\d{4})?|\b\d{4}-\d{2}-\d{2}\b|\b\d{1,2}/\d{1,2}/\d{2,4}\b", re.I)
SIGNED = re.compile(r"(?:(?<![\w.])([+\-–−‑]))?(\d[\d,]*(?:\.\d+)?)")

def numbers_in(text, signed=False):
    """Numbers in text (years, pages, notes, small counters ignored). signed=True -> [(value, had_explicit_sign)]."""
    t = re.sub(r"(?<=\d)[\s\u00a0\u202f\u2009](?=(?:\d{2}[\s\u00a0\u202f\u2009])*\d{3}(?:\D|$))", "", str(text))
    t = DATES.sub(" ", t)
    t = IGNORE.sub(" ", t)
    out = []
    for m in SIGNED.finditer(t):
        s = m.group(2).rstrip(",")
        try: v = float(s.replace(",", ""))
        except ValueError: continue
        if not ("." in s or v >= 13): continue
        neg = m.group(1) in ("-", "–", "−", "‑")
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
    """v equals c (or c as a percentage/fraction) exactly, or rounded/truncated to 0-4 decimals.
    A value exactly half-way (e.g. 290,324.455) matches either rounding (float round() may go either way)."""
    dv = min(len(repr(v).split(".")[1].rstrip("0")) if "." in repr(v) else 0, 4)
    for x in (c, c * 100, c / 100):
        if x == v: return True
        for d in (0, 1, 2, 3, 4):
            if round(x, d) == v or math.trunc(x * 10 ** d) / 10 ** d == v: return True
        if abs(abs(x) - abs(v)) <= 0.5 * 10 ** -dv + 1e-9 and (x >= 0) == (v >= 0): return True
    return False

def grounded(v, explicit_sign, pools):
    sgn, ab = pools
    if explicit_sign: return any(close(v, c) for c in sgn)        # '+7,638' must match a +7,638 source
    return any(close(abs(v), c) for c in ab)

CLAIMS = [(r"inventor", "inventories"), (r"receivable", "trade_receivables"), (r"borrowing", "current_borrowings / non_current_borrowings"),
          (r"payable", "trade_payables"), (r"\bcash and cash equivalents\b|\bcash balance", "cash_and_cash_equivalents")]
DOC_ATTR = re.compile(r"management discussion|md&a|commentary|management (notes|cites|highlights|says|attribut|state)|"
                      r"report (notes|states|highlights|cites|mentions|attributes)|according to (the )?(report|management)", re.I)

APPROX = re.compile(r"(?:≈|~|\b(?:around|about|roughly|approximately|approx\.?))\s*(?:₹|INR|Rs\.?)?\s*[-–−+]?\d", re.I)

def grounding_view(tool, result):
    """What a tool result contributes to the grounding pools. calculate: only its results - the operands the model typed
    into an expression are not evidence (a hand-computed average typed into calculate would otherwise count as verified)."""
    if tool != "calculate" or not isinstance(result, dict): return result
    if "results" in result: return {"results": [grounding_view(tool, r) for r in result["results"]]}
    return {k: v for k, v in result.items() if k != "expression"}

def unsupported_claims(answer, trace):
    """Rule-based check for claims without evidence: document attributions without a search, drivers never fetched."""
    fetched = " ".join(json.dumps(t["args"]).lower() + " " + t.get("result", "").lower() for t in trace)
    issues = []
    if DOC_ATTR.search(answer) and not any(t["tool"] == "search_documents" for t in trace):
        issues.append("You attribute statements to MD&A/commentary/management but never retrieved a passage with search_documents.")
    for rx, item in CLAIMS:
        if re.search(rx, answer, re.I) and not re.search(rx, fetched):
            issues.append(f"You discuss '{rx.split('|')[0].strip(chr(92) + 'b')}' but never retrieved it (use get_financials: {item}).")
    if re.search(r"\d[\d,]*\.\d{2}", answer) and not re.search(r"\bF\d{1,3}\b|PDF\s?p\s?\d|page\s+\d", answer):
        issues.append("Your answer states figures but cites no page. Cite the report and page for every figure "
                      "(e.g. FY2025-26 AR, consolidated profit and loss, p. F144).")
    approx = sorted({m.group(0).strip() for m in APPROX.finditer(answer)})
    if approx:
        issues.append(f"Approximate figures {approx}: never write '≈', '~', 'around', 'about', 'roughly' or 'approximately' "
                      "next to a number. State the exact computed value (e.g. 2,810.36 crore, 34.81%).")
    if re.search(r"altman|piotroski|beneish", answer, re.I) and not any(t["tool"] == "compute_scores" for t in trace):
        issues.append("You discuss Altman/Piotroski/Beneish scores without calling compute_scores. These scores must come "
                      "from compute_scores (verified inputs, defined formulas); never compute or reformulate them yourself.")
    return issues

REVIEW = ("SELF-REVIEW before finalising. Rewrite your answer so that: (1) every cause, reason or attribution "
          "('due to', 'reflecting', 'driven by', 'as the Group...', 'management notes...') is directly supported by a table "
          "or passage you retrieved in this conversation - delete any that is not, instead of guessing; (2) every statement "
          "agrees with the retrieved data (never say an item rose if the table shows it fell); (3) if you explained a change "
          "in a total without calling breakdown, call breakdown now and cover its largest components; (4) cite 'notes' as "
          "notes and 'MD&A' as MD&A, exactly as the source says; (5) keep every number exactly as retrieved. "
          "Output only the complete final answer.")

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
    answer = re.sub(r"【[^】]*】", "", answer)
    n_ok = len([n for n in nums if n not in bad])
    footer = f"\n\n---\nVerification: {n_ok}/{len(nums)} figures grounded in source data."
    if bad: footer += f"\n⚠ Could not verify: {bad}"
    if note: footer += f"\n⚠ {note}"
    return answer + footer, {"trace": trace, "grounded": n_ok, "total": len(nums), "unverified": bad, "fix_rounds": fixes,
                             "answer_body": answer, "warnings": [note] if note else []}

def _history(h):
    """Earlier chat turns (last 8 messages, capped), so follow-up questions can be resolved."""
    out = []
    for m in (h or [])[-8:]:
        r, c = (m.get("role"), str(m.get("content", ""))[:4000]) if isinstance(m, dict) else (None, "")
        if r in ("user", "assistant") and c.strip(): out.append({"role": r, "content": c})
    return out

def ask(question, max_steps=24, max_fixes=2, verbose=True, history=None):
    msgs = [{"role": "system", "content": SYSTEM}] + _history(history) + [{"role": "user", "content": question}]
    trace, pools, fixes, last = [], (set(), set()), 0, None
    reviewed = False
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
                collect(grounding_view(name, result), pools)
                trace.append({"tool": name, "args": args, "result": json.dumps(result, ensure_ascii=False)[:20000]})
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
            msg += ("Retrieve the evidence with tools (get_financials, get_line_items, search_documents, calculate, dupont) or "
                    "remove the claim; a number you computed yourself must come from calculate with an expression written from "
                    "retrieved figures. Then give the complete corrected answer.")
            msgs.append({"role": "user", "content": msg})
            continue
        if not reviewed and not final_step and (not (bad or issues) or fixes >= max_fixes):
            reviewed = True
            if verbose: print("  [self-review pass]", flush=True)
            msgs.append({"role": "user", "content": REVIEW})
            continue
        return finish(answer, nums, bad, trace, fixes, note=("Unsupported claims: " + " ".join(issues)) if issues else "")
    if last: return finish(*last, trace, fixes, note="Step limit reached; this is the last draft.")
    return "I could not complete this analysis within the step limit.", {"trace": trace, "grounded": 0, "total": 0, "unverified": [], "fix_rounds": fixes}

if __name__ == "__main__":
    answer, _ = ask(" ".join(sys.argv[1:]))
    print("\n" + answer)
```

---

## `src/agent/tools.py`

```python
"""Agent tools: verified line-item lookup, hybrid document search, exact calculator.

All arguments from the LLM are normalised (case, wording, year formats), and searches relax their
filters step by step when nothing matches, so a badly-phrased filter can never silently return nothing.
"""
import ast, json, operator, re, sys
from pathlib import Path
from rapidfuzz import fuzz, process, utils
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "retrieval"))
from search import search

ROOT = Path(__file__).resolve().parents[2]
ITEMS = [json.loads(l) for l in open(ROOT / "data/processed/line_items.jsonl")]
YEARS = ["FY2021-22", "FY2022-23", "FY2023-24", "FY2024-25", "FY2025-26"]
REPORTS = ["FY2022-23", "FY2023-24", "FY2024-25", "FY2025-26"]
TYPES = ["statement_table", "note_table", "fs_text", "narrative"]
TOPICS = ["risk", "mdna", "directors_report", "governance", "sustainability", "strategy", "segments"]
SECTIONS = ["auditor_report", "notes", "fs_other", "balance_sheet", "profit_and_loss", "cash_flow",
            "changes_in_equity", "integrated_report", "statutory_reports"]

# ---------- argument normalisation ----------
def norm_scope(x):
    x = str(x or "").lower()
    if "stand" in x: return "standalone"
    if "consol" in x or "group" in x: return "consolidated"
    return None

def norm_statement(x):
    x = str(x or "").lower()
    if "balance" in x: return "balance_sheet"
    if "cash" in x: return "cash_flow"
    if any(w in x for w in ("profit", "loss", "p&l", "income statement")): return "profit_and_loss"
    return None

def norm_fy(x):
    """'FY2025-26', 'FY2025-26 Annual Report', '2025-26', 'FY26' -> 'FY2025-26'; bare 2025 -> year ending Mar-2025."""
    s = str(x or "")
    m = re.search(r"(20\d\d)\s*[-–/]\s*(\d{2,4})", s)
    if m: a = int(m.group(1)); return f"FY{a}-{str(a + 1)[2:]}"
    m = re.search(r"FY\s*'?(\d{2})\b", s, re.I)
    if m: e = 2000 + int(m.group(1)); return f"FY{e - 1}-{str(e)[2:]}"
    m = re.search(r"(20\d\d)", s)
    if m: e = int(m.group(1)); return f"FY{e - 1}-{str(e)[2:]}"
    return None

def _list(x):
    if x in (None, "", []): return []
    return x if isinstance(x, list) else [x]

def norm_types(x):
    out = []
    for t in _list(x):
        t = str(t).lower()
        if t in TYPES: out.append(t)
        elif "narrat" in t or "commentary" in t or "md&a" in t: out.append("narrative")
        elif "note" in t: out += ["note_table", "fs_text"]
        elif "statement" in t: out.append("statement_table")
    return sorted(set(out)) or None

def norm_section(x):
    x = str(x or "").lower()
    if "audit" in x: return "auditor_report"
    if "note" in x: return "notes"
    if "statutory" in x or "directors" in x or "board" in x: return "statutory_reports"
    if "integrated" in x: return "integrated_report"
    return norm_statement(x) or (x if x in SECTIONS else None)

def norm_topic(x):
    x = str(x or "").lower().replace(" ", "_")
    if x in TOPICS: return x
    for t, keys in [("risk", ["risk"]), ("mdna", ["management", "md&a", "mdna"]), ("segments", ["segment"]),
                    ("strategy", ["strateg", "outlook"]), ("sustainability", ["sustain", "esg", "climate"]),
                    ("governance", ["governance"]), ("directors_report", ["director", "board"])]:
        if any(k in x for k in keys): return t
    return None

def _score(a, b, **kw):
    """Word-set match dominates (all query words present), WRatio breaks ties."""
    return 0.7 * fuzz.token_set_ratio(a, b) + 0.3 * fuzz.WRatio(a, b)

# ---------- tools ----------
def get_line_items(query, scope="consolidated", statement=None, fiscal_years=None, limit=5):
    """Exact figures from the verified primary statements (preferred = latest report containing each year).
    Several line items can be requested at once, separated by ';'."""
    if isinstance(query, list) or ";" in str(query):
        qs = query if isinstance(query, list) else [q.strip() for q in str(query).split(";") if q.strip()]
        return {"results": {q: get_line_items(q, scope, statement, fiscal_years, limit=3) for q in qs}}
    sc = norm_scope(scope) or "consolidated"
    st = norm_statement(statement)
    fys = [f for f in (norm_fy(y) for y in _list(fiscal_years)) if f] or None
    def pool(st_, fys_):
        return [r for r in ITEMS if r["preferred"] and r["scope"] == sc and (not st_ or r["statement"] == st_)
                and (not fys_ or r["fiscal_year"] in fys_)]
    rows, relaxed = pool(st, fys), []
    if not rows and st: rows, st, relaxed = pool(None, fys), None, relaxed + ["statement"]
    if not rows and fys: rows, fys, relaxed = pool(st, None), None, relaxed + ["fiscal_years"]
    names = {}
    for r in rows:
        names.setdefault(f'{r["statement"]}: {r["path"] + " > " if r["path"] else ""}{r["line_item"]}', []).append(r)
    out = []
    for name, score, _ in process.extract(str(query), list(names), scorer=_score, processor=utils.default_process, limit=int(limit or 5)):
        vals = []
        for r in sorted(names[name], key=lambda r: r["fiscal_year"]):
            v = {"fiscal_year": r["fiscal_year"], "value_inr_crore": r["value"],
                 "source": f'{r["report"]} Annual Report, {r["scope"]} {r["statement"].replace("_", " ")}, page {r["page_label"]}'}
            if r["differs_from_original"]: v.update(restated=True, originally_reported=r["original_value"])
            vals.append(v)
        out.append({"line_item": name, "match_score": round(score), "values": vals})
    return {"scope_used": sc, "filters_relaxed": relaxed, "available_years": YEARS, "matches": out}

def _compact(text):
    """Collapse the padding Docling puts in markdown tables, so wide tables fit in the context the model sees."""
    return re.sub(r"-{4,}", "---", re.sub(r"[ \t]{2,}", " ", text))

_NUM_CELL = re.compile(r"\(?-?[\d,]+\.\d+\)?|-")

def _fix_stacked(md, report):
    """Repair stacked-year rows in note tables: a numeric row followed by a numeric row whose label is blank or
    continues in lowercase is one item shown for two years (first = report year, second = prior year).
    The split label is merged and each row is stamped with its fiscal year."""
    try:
        y = int(report[2:6]); cur, pri = report, f"FY{y - 1}-{str(y)[2:]}"
    except Exception:
        return md
    lines = md.split("\n")
    def parts(l):
        if not l.startswith("|"): return None
        cells = [c.strip() for c in l.strip().strip("|").split("|")]
        nums = sum(1 for c in cells if _NUM_CELL.fullmatch(c))
        lab_i = next((i for i, c in enumerate(cells) if c and not _NUM_CELL.fullmatch(c)), None)
        return cells, nums, lab_i
    i = 0
    while i < len(lines) - 1:
        a, b = parts(lines[i]), parts(lines[i + 1])
        if a and b and a[1] >= 2 and b[1] >= 2 and a[2] is not None:
            lab_a = a[0][a[2]]
            lab_b = b[0][b[2]] if b[2] is not None and b[2] <= a[2] else ""
            if lab_b == "" or lab_b[:1].islower():
                full = (lab_a + " " + lab_b).strip()
                ca, cb = list(a[0]), list(b[0])
                ca[a[2]] = f"{full} [{cur}]"
                if b[2] is not None and b[2] <= a[2]: cb[b[2]] = f"{full} [{pri}]"
                else: cb[a[2]] = f"{full} [{pri}]"
                lines[i], lines[i + 1] = "| " + " | ".join(ca) + " |", "| " + " | ".join(cb) + " |"
                i += 2; continue
        i += 1
    return "\n".join(lines)

def search_documents(query, report=None, scope=None, types=None, topic=None, section=None, k=6):
    """Hybrid search; relaxes filters step by step until something is found."""
    base = dict(report=norm_fy(report) if report else None, scope=norm_scope(scope), types=norm_types(types),
                topic=norm_topic(topic), section=norm_section(section) or (norm_section(topic) if "audit" in str(topic).lower() else None))
    attempts = [base, {**base, "types": None, "topic": None}, {**base, "types": None, "topic": None, "section": None},
                {"report": base["report"]}]
    for i, f in enumerate(attempts):
        pts = search(str(query), k=int(k or 6), **f)
        if pts:
            return {"filters_used": {a: b for a, b in f.items() if b}, "filters_relaxed": i > 0, "results": [
                {"source": f'{p.payload["report"]} Annual Report, {p.payload["scope"] or ""} {p.payload["section"]}, '
                           f'page {p.payload.get("page_label") or "PDF p" + str(p.payload["page"])}',
                 "title": p.payload["note"], "text": _fix_stacked(_compact(p.payload["text"]), p.payload["report"])[:5000]} for p in pts]}
    return {"results": [], "note": "Nothing found even with only the report filter. Try different wording."}

OPS = {ast.Add: operator.add, ast.Sub: operator.sub, ast.Mult: operator.mul, ast.Div: operator.truediv,
       ast.Pow: operator.pow, ast.USub: operator.neg, ast.UAdd: operator.pos}
def calculate(expression):
    """Safe exact arithmetic: numbers, + - * / ** and parentheses only. Several expressions separated by ';'."""
    if ";" in str(expression):
        out = []
        for e in [e.strip() for e in str(expression).split(";") if e.strip()]:
            try: out.append(calculate(e))
            except Exception as ex: out.append({"expression": e, "error": str(ex)})
        return {"results": out}
    def ev(n):
        if isinstance(n, ast.Constant) and isinstance(n.value, (int, float)): return n.value
        if isinstance(n, ast.BinOp): return OPS[type(n.op)](ev(n.left), ev(n.right))
        if isinstance(n, ast.UnaryOp): return OPS[type(n.op)](ev(n.operand))
        raise ValueError("only numbers and + - * / ** ( ) are allowed")
    return {"expression": expression, "result": round(ev(ast.parse(str(expression).replace(",", ""), mode="eval").body), 6)}

FUNCS = {"get_line_items": get_line_items, "search_documents": search_documents, "calculate": calculate}
SCHEMAS = [
    {"type": "function", "function": {"name": "get_line_items",
     "description": "Get exact, verified figures (INR crore) for a line item from the balance sheet, profit and loss or cash flow statement, for every available year (FY2021-22 to FY2025-26), with source page. Use for ALL primary-statement numbers.",
     "parameters": {"type": "object", "properties": {
         "query": {"type": "string", "description": "Line item name, e.g. 'Revenue from operations'. Request several at once separated by ';', e.g. 'Inventories; Trade receivables; Cash and cash equivalents; Trade payables'"},
         "scope": {"type": "string", "enum": ["consolidated", "standalone"], "description": "Default consolidated"},
         "statement": {"type": "string", "enum": ["balance_sheet", "profit_and_loss", "cash_flow"]},
         "fiscal_years": {"type": "array", "items": {"type": "string", "enum": YEARS}}},
         "required": ["query"]}}},
    {"type": "function", "function": {"name": "search_documents",
     "description": "Search the annual reports: notes to accounts, auditor's report (section=auditor_report), segment information, MD&A, risk management and strategy pages. Returns passages with source pages. Start with few filters.",
     "parameters": {"type": "object", "properties": {
         "query": {"type": "string"},
         "report": {"type": "string", "enum": REPORTS, "description": "Which annual report to search"},
         "scope": {"type": "string", "enum": ["consolidated", "standalone"]},
         "section": {"type": "string", "enum": SECTIONS},
         "types": {"type": "array", "items": {"type": "string", "enum": TYPES}},
         "topic": {"type": "string", "enum": TOPICS}},
         "required": ["query"]}}},
    {"type": "function", "function": {"name": "calculate",
     "description": "Evaluate arithmetic exactly. Use for EVERY ratio, difference, percentage, average and growth rate.",
     "parameters": {"type": "object", "properties": {
         "expression": {"type": "string", "description": "e.g. (72265.11 / 96917.64). Do several at once separated by ';', e.g. '86606.14/97295.13; 70503.59/98403.48; 47249.22-44589.94'"}},
         "required": ["expression"]}}},
]


# ---------- canonical financials (exact rows, yoy changes computed in code) ----------
FIN_PATH = ROOT / "data/processed/financials.json"
FIN = json.loads(FIN_PATH.read_text()) if FIN_PATH.exists() else {}
CANON = sorted({k for sc in FIN.values() for k in sc})
FIN_REP_PATH = ROOT / "data/processed/financials_by_report.json"
FIN_REP = json.loads(FIN_REP_PATH.read_text()) if FIN_REP_PATH.exists() else {}

def get_financials(items, scope="consolidated", fiscal_years=None):
    """Exact canonical statement items for each year, with year-on-year change and % change computed exactly."""
    sc = norm_scope(scope) or "consolidated"
    fys = [f for f in (norm_fy(y) for y in _list(fiscal_years)) if f] or YEARS
    wanted = items if isinstance(items, list) else re.split(r"[;,]", str(items))
    out, unknown = {}, []
    for it in [str(w).strip() for w in wanted if str(w).strip()]:
        key = re.sub(r"[^a-z0-9]+", "_", it.lower()).strip("_")
        if key not in FIN.get(sc, {}):
            best = process.extractOne(it, CANON, scorer=_score, processor=utils.default_process)
            key = best[0] if best and best[1] >= 75 else None
        if not key or key not in FIN.get(sc, {}):
            unknown.append(it); continue
        entry = FIN[sc][key]
        vals = {fy: entry["values"][fy] for fy in fys if fy in entry["values"]}
        ys, changes = sorted(vals), []
        for a, b in zip(ys, ys[1:]):
            rb = FIN_REP.get(b, {}).get(sc, {}).get(key, {}).get("values", {})     # later report holds both years
            same = a in rb and b in rb
            va = rb[a]["value"] if same else vals[a]["value"]
            vb = rb[b]["value"] if same else vals[b]["value"]
            c = {"from": a, "to": b, "change": round(vb - va, 2), "change_pct": round((vb - va) / abs(va) * 100, 2) if va else None,
                 "basis": f"both years as presented in the {b} report" if same else "latest reported values"}
            if same and (abs(va - vals[a]["value"]) > 0.01 or abs(vb - vals[b]["value"]) > 0.01):
                c["prior_year_as_presented"], c["year_as_presented"] = va, vb
            changes.append(c)
        out[key] = {"description": entry["description"], "values": vals, "yoy_changes": changes}
    ys_all = [y for y in fys if any(y in v["values"] for v in out.values())]
    table = "| Item (INR crore) | " + " | ".join(ys_all) + " |\n|---|" + "---|" * len(ys_all) + "\n"
    for v in out.values():
        table += f"| {v['description']} | " + " | ".join(_inr(v["values"][y]["value"]) if y in v["values"] else "n/a" for y in ys_all) + " |\n"
    pairs = list(zip(ys_all, ys_all[1:]))
    changes = "| Change (INR crore, %) | " + " | ".join(f"{a} to {b}" for a, b in pairs) + " |\n|---|" + "---|" * len(pairs) + "\n"
    for v in out.values():
        cells = []
        for a, b in pairs:
            c = next((c for c in v["yoy_changes"] if c["from"] == a and c["to"] == b), None)
            cell = "n/a" if not c else f"{'+' if c['change'] > 0 else ''}{_inr(c['change'])} ({'+' if (c['change_pct'] or 0) > 0 else ''}{c['change_pct']}%)"
            cells.append(cell + ("*" if c and "prior_year_as_presented" in c else ""))
        changes += f"| {v['description']} | " + " | ".join(cells) + " |\n"
    changes += ("\nChanges compare both years as presented in the later year's report. * = a figure was restated or "
                "reclassified in that report, so the change differs from simply subtracting the level values above.\n")
    res = {"scope_used": sc, "unit": "INR crore", "year_convention": "FY2023-24 = year ended 31 March 2024; balance-sheet values for FY2023-24 are as at 31 March 2024.", "table": table, "changes_table": changes, "items": out}
    if unknown: res.update(unknown_items=unknown, available_items=CANON, hint="Use get_line_items for items not listed.")
    return res

FUNCS["get_financials"] = get_financials
SCHEMAS.insert(0, {"type": "function", "function": {"name": "get_financials",
    "description": "PREFERRED for statement figures. Exact, verified values of standard items for every year FY2021-22 to "
                   "FY2025-26, each with source page, plus exact year-on-year change and % change. Items: " + ", ".join(CANON),
    "parameters": {"type": "object", "properties": {
        "items": {"type": "array", "items": {"type": "string", "enum": CANON}, "description": "One or more items"},
        "scope": {"type": "string", "enum": ["consolidated", "standalone"]},
        "fiscal_years": {"type": "array", "items": {"type": "string", "enum": YEARS}}},
        "required": ["items"]}}})


def _inr(v):
    """Indian digit grouping: 232139.94 -> 2,32,139.94"""
    i, d = f"{abs(v):.2f}".split(".")
    if len(i) > 3:
        head, parts = i[:-3], []
        while len(head) > 2: parts.insert(0, head[-2:]); head = head[:-2]
        if head: parts.insert(0, head)
        i = ",".join(parts + [i[-3:]])
    return ("-" if v < 0 else "") + i + "." + d

def compute_metric(formula, name=None, scope="consolidated", fiscal_years=None, decimals=4):
    """Evaluate a formula over canonical items for every year, exactly. avg(x) = mean of this and previous
    year-end; prev(x) = previous year. Returns a ready-to-paste table with inputs, results and sources."""
    sc = norm_scope(scope) or "consolidated"
    fys = [f for f in (norm_fy(y) for y in _list(fiscal_years)) if f] or YEARS
    try: tree = ast.parse(str(formula), mode="eval")
    except SyntaxError as e: return {"error": f"formula syntax error: {e}"}
    names = sorted({n.id for n in ast.walk(tree) if isinstance(n, ast.Name) and n.id not in ("avg", "prev")})
    missing = [n for n in names if n not in FIN.get(sc, {})]
    if missing: return {"error": f"unknown items {missing}", "available_items": CANON}
    prev_fy = lambda fy: YEARS[YEARS.index(fy) - 1] if fy in YEARS and YEARS.index(fy) > 0 else None
    def val(key, fy):
        v = FIN[sc][key]["values"].get(fy) if fy else None
        return None if v is None else v["value"]
    inter = {}                     # avg()/prev() values per year, returned so the model never recomputes them
    def ev(n, fy):
        if isinstance(n, ast.Constant) and isinstance(n.value, (int, float)): return n.value
        if isinstance(n, ast.Name): return val(n.id, fy)
        if isinstance(n, ast.Call) and getattr(n.func, "id", "") in ("avg", "prev") and len(n.args) == 1:
            cur, pv = ev(n.args[0], fy), ev(n.args[0], prev_fy(fy))
            r = pv if n.func.id == "prev" else (None if cur is None or pv is None else (cur + pv) / 2)
            if r is not None: inter.setdefault(fy, {})[ast.unparse(n)] = round(r, 4)
            return r
        if isinstance(n, ast.BinOp):
            a, b = ev(n.left, fy), ev(n.right, fy)
            if a is None or b is None or (isinstance(n.op, ast.Div) and b == 0): return None
            return OPS[type(n.op)](a, b)
        if isinstance(n, ast.UnaryOp):
            a = ev(n.operand, fy); return None if a is None else OPS[type(n.op)](a)
        raise ValueError("use item names, numbers, + - * / ** ( ), avg(item), prev(item)")
    label = name or str(formula)
    try: results = {fy: ev(tree.body, fy) for fy in fys}
    except ValueError as e: return {"error": str(e)}
    uses_prev = any(isinstance(n, ast.Call) for n in ast.walk(tree))
    header = ("| Fiscal year | " + " | ".join(names) + (" | (prior year-end used for avg/prev)" if uses_prev else "")
              + f" | {label} | Change vs prior year | % change |")
    rows = [header, "|---|" + "---|" * (len(names) + (4 if uses_prev else 3))]
    sources = {}
    for fy in fys:
        cells = [_inr(val(k, fy)) if val(k, fy) is not None else "n/a" for k in names]
        if uses_prev:
            cells.append(", ".join([f"{k}: {_inr(val(k, prev_fy(fy)))}" for k in names if val(k, prev_fy(fy)) is not None]
                                   + [f"{e} = {v:,.3f}".rstrip("0").rstrip(".") for e, v in inter.get(fy, {}).items()]) or "n/a")
        r = results[fy]
        cells.append("n/a" if r is None else f"{r:.{int(decimals)}f}")
        i = fys.index(fy)
        pr = results.get(fys[i - 1]) if i > 0 else None
        if r is None or pr is None: cells += ["n/a", "n/a"]
        else: cells += [f"{r - pr:+.{int(decimals)}f}", f"{(r - pr) / abs(pr) * 100:+.2f}%" if pr else "n/a"]
        rows.append(f"| {fy} | " + " | ".join(cells) + " |")
        sources[fy] = {k: FIN[sc][k]["values"][fy]["source"] for k in names if fy in FIN[sc][k]["values"]}
    by_fy = {}
    for fy_, d in sources.items():
        for s_ in d.values():
            by_fy.setdefault(fy_, set()).add(s_.split(" Annual Report")[0] + " AR p. " + s_.split("page ")[-1])
    src_line = "Sources: " + "; ".join(f"{fy_}: {', '.join(sorted(v))}" for fy_, v in by_fy.items())
    out = {"metric": label, "formula": str(formula), "scope_used": sc, "table": "\n".join(rows) + "\n\n" + src_line,
           "values": {fy: (None if r is None else round(r, int(decimals))) for fy, r in results.items()}, "sources": sources}
    if inter: out["intermediates"] = inter
    return out

FUNCS["compute_metric"] = compute_metric
SCHEMAS.insert(1, {"type": "function", "function": {"name": "compute_metric",
    "description": "PREFERRED for ratios and derived metrics across years. Evaluates a formula over get_financials item names "
                   "for every year exactly and returns a ready-to-paste table (inputs, results, sources). Formula may use item "
                   "names, numbers, + - * / ( ), avg(item) = average of this and previous year-end, prev(item) = previous year. "
                   "Examples: 'total_current_assets / total_current_liabilities'; '(non_current_borrowings + current_borrowings) "
                   "/ total_equity'; 'profit_for_the_year / avg(total_equity) * 100'.",
    "parameters": {"type": "object", "properties": {
        "formula": {"type": "string"}, "name": {"type": "string", "description": "e.g. 'Current ratio'"},
        "scope": {"type": "string", "enum": ["consolidated", "standalone"]},
        "fiscal_years": {"type": "array", "items": {"type": "string", "enum": YEARS}},
        "decimals": {"type": "integer", "description": "Default 4"}},
        "required": ["formula"]}}})


# ---------- breakdown: every component's contribution to a change in a total ----------
BREAKDOWN = {"total_current_assets": ("balance_sheet", "current assets"),
             "total_current_liabilities": ("balance_sheet", "current liabilities"),
             "total_non_current_assets": ("balance_sheet", "non-current assets"),
             "total_non_current_liabilities": ("balance_sheet", "non-current liabilities"),
             "total_expenses": ("profit_and_loss", "expenses"),
             "total_income": ("profit_and_loss", "income")}
_k = lambda s: re.sub(r"[^a-z0-9]+", " ", str(s).lower()).strip()

def breakdown(total, from_year, to_year, scope="consolidated"):
    """All components of a statement total for two years (both from the later year's report), with each
    component's change and share of the total change. Checks the components add up to the reported total."""
    sc = norm_scope(scope) or "consolidated"
    key = total if total in BREAKDOWN else (process.extractOne(str(total), list(BREAKDOWN), scorer=_score, processor=utils.default_process) or [None])[0]
    if key not in BREAKDOWN: return {"error": f"unknown total '{total}'", "available_totals": list(BREAKDOWN)}
    st, prefix = BREAKDOWN[key]
    a, b = norm_fy(from_year), norm_fy(to_year)
    if not a or not b: return {"error": "give from_year and to_year, e.g. FY2024-25 and FY2025-26"}
    rep = b if b in REPORTS else REPORTS[-1]
    comps, pages, reported = {}, set(), {}
    desc = FIN[sc][key]["description"].lower()
    for r in ITEMS:
        if r["report"] != rep or r["scope"] != sc or r["statement"] != st or r["fiscal_year"] not in (a, b): continue
        if r["line_item"].lower() == desc: reported[r["fiscal_year"]] = r["value"]; continue
        if not _k(r["path"]).startswith(_k(prefix)) or r.get("synthetic_label"): continue
        if r["line_item"].lower().startswith("total") and not r["line_item"].lower().startswith("total outstanding dues"): continue
        name = r["line_item"]
        c = comps.setdefault((_k(r["path"]), _k(name)), {"component": (r["path"].split(" > ", 1)[1] + " > " if " > " in r["path"] else "") + name, "values": {}})
        c["values"][r["fiscal_year"]] = -r["value"] if name.lower().startswith("less") else r["value"]
        pages.add(r["page_label"])
    if a not in reported or b not in reported:
        return {"error": f"{rep} report does not contain both {a} and {b}; use consecutive years"}
    rows = sorted([(c["component"], c["values"].get(a, 0.0), c["values"].get(b, 0.0)) for c in comps.values()],
                  key=lambda x: -abs(x[2] - x[1]))
    tchg = round(reported[b] - reported[a], 2)
    table = (f"| Component of {FIN[sc][key]['description']} | {a} | {b} | Change | % change (own YoY) | Contribution to total change |\n"
             "|---|---|---|---|---|---|\n")
    for name, va, vb in rows:
        ch = round(vb - va, 2)
        pct = f"{ch / abs(va) * 100:+.2f}%" if va else "n/a"
        share = f"{ch / tchg * 100:+.1f}%" if tchg else "n/a"
        table += f"| {name} | {_inr(va)} | {_inr(vb)} | {'+' if ch > 0 else ''}{_inr(ch)} | {pct} | {share} |\n"
    tpct = f"{tchg / abs(reported[a]) * 100:+.2f}%" if reported[a] else "n/a"
    table += f"| {FIN[sc][key]['description']} (reported) | {_inr(reported[a])} | {_inr(reported[b])} | {'+' if tchg > 0 else ''}{_inr(tchg)} | {tpct} | 100% |\n"
    sa, sb = round(sum(x[1] for x in rows), 2), round(sum(x[2] for x in rows), 2)
    return {"total": key, "scope_used": sc, "from": a, "to": b, "source": f"{rep} Annual Report, {sc} {st.replace('_', ' ')}, pages {', '.join(sorted(p for p in pages if p))}",
            "table": table, "components_reconcile_to_reported_total": abs(sa - reported[a]) < 0.05 and abs(sb - reported[b]) < 0.05}

FUNCS["breakdown"] = breakdown
SCHEMAS.insert(2, {"type": "function", "function": {"name": "breakdown",
    "description": "Explain a change in a statement total: returns EVERY component of the total for two years with its change "
                   "and share of the total change (largest first), as a ready-to-paste table. Totals: " + ", ".join(BREAKDOWN),
    "parameters": {"type": "object", "properties": {
        "total": {"type": "string", "enum": list(BREAKDOWN)},
        "from_year": {"type": "string", "enum": YEARS}, "to_year": {"type": "string", "enum": YEARS},
        "scope": {"type": "string", "enum": ["consolidated", "standalone"]}},
        "required": ["total", "from_year", "to_year"]}}})


# ---------- risk sections, for risk-evolution questions ----------
CHUNKS = [json.loads(l) for l in open(ROOT / "data/processed/chunks.jsonl")]

def list_risk_disclosures(report):
    """Every risk-tagged narrative page of one report (page, title, short excerpt), for side-by-side comparison."""
    rep = norm_fy(report)
    rows = sorted((c for c in CHUNKS if c["report"] == rep and c["type"] == "narrative" and "risk" in c["topics"]), key=lambda c: c["page"])
    out, seen = [], set()
    for c in rows:
        if c["page"] in seen: continue
        seen.add(c["page"])
        out.append({"pdf_page": c["page"], "section": c["section"], "title": (c["note"] or "")[:120],
                    "excerpt": _compact(c["text"].split("\n\n", 1)[-1])[:350]})
    return {"report": rep, "risk_pages": out[:30],
            "note": "Risk-related pages of this report. Use search_documents with a specific risk name to read more or to check another report."}

FUNCS["list_risk_disclosures"] = list_risk_disclosures
SCHEMAS.append({"type": "function", "function": {"name": "list_risk_disclosures",
    "description": "List every risk-related page (risk management, key risks, regulatory/financial/ESG risks) of ONE annual report, "
                   "with titles and excerpts. Call it once per report when comparing how risks changed between years.",
    "parameters": {"type": "object", "properties": {"report": {"type": "string", "enum": REPORTS}}, "required": ["report"]}}})


# ---------- composite scores: Altman Z'' (book equity), Piotroski F, Beneish M ----------
sys.path.insert(0, str(ROOT / "src" / "analysis"))
import scores as S

SCORE_NAMES = {"altman_z": "Altman Z'' (book equity)", "piotroski_f": "Piotroski F-score", "beneish_m": "Beneish M-score (8-variable)"}
COMPONENT_LABELS = {
    "X1": "X1 (current assets - current liabilities) / total assets", "X2": "X2 retained earnings / total assets",
    "X3": "X3 (PBT + finance costs) / total assets", "X4": "X4 total equity / (total assets - total equity)",
    "DSRI": "DSRI receivables-to-sales index", "GMI": "GMI gross margin index", "AQI": "AQI asset quality index",
    "SGI": "SGI sales growth index", "DEPI": "DEPI depreciation index", "SGAI": "SGAI other-expenses (SG&A proxy) index",
    "LVGI": "LVGI leverage index", "TATA": "TATA total accruals / total assets"}
_INR_SIGNALS = ("F2_cfo_positive", "F7_no_new_equity")    # compared amounts are INR crore, not ratios

def norm_score(x):
    x = str(x or "all").lower()
    if "altman" in x or x in ("z", "z''", "zscore", "z_score"): return "altman_z"
    if "piotroski" in x or x in ("f", "fscore", "f_score"): return "piotroski_f"
    if "beneish" in x or x in ("m", "mscore", "m_score"): return "beneish_m"
    if x in ("all", "any", "every", "*"): return "all"
    return None

def _score_table(name, res, fys):
    """Markdown table for one score: components (4 decimals), score, interpretation, then inputs (INR crore)."""
    rows = [f"| {SCORE_NAMES[name]} | " + " | ".join(fys) + " |", "|---|" + "---|" * len(fys)]
    comp_keys = next((list(r["components"]) for r in res.values() if r["components"]), [])
    for k in comp_keys:
        cells = []
        for fy in fys:
            c = res[fy]["components"].get(k)
            if c is None: cells.append("n/a")
            elif name == "piotroski_f":
                f = _inr if k in _INR_SIGNALS else (lambda v: f"{v:.4f}")
                cells.append("n/a" if c["signal"] is None or c["current"] is None or c["comparison"] is None
                             else f"{c['signal']} ({f(c['current'])} vs {f(c['comparison'])})")
            else: cells.append(f"{c:.4f}")
        label = res[next(iter(res))]["components"].get(k, {}).get("description", k) if name == "piotroski_f" else COMPONENT_LABELS.get(k, k)
        rows.append(f"| {(k.split('_')[0] + ' ' + label) if name == 'piotroski_f' else label} | " + " | ".join(cells) + " |")
    fmt = (lambda v: str(v)) if name == "piotroski_f" else (lambda v: f"{v:.4f}")
    rows.append(f"| **Score** | " + " | ".join("n/a" if res[fy]["score"] is None else f"**{fmt(res[fy]['score'])}**" for fy in fys) + " |")
    rows.append(f"| Interpretation | " + " | ".join(res[fy]["interpretation"] or "n/a" for fy in fys) + " |")
    rel = {0: "t", 1: "t-1", 2: "t-2"}
    inputs = {}
    for fy in fys:
        for rec in res[fy]["inputs"].values():
            lag = S.YEARS.index(fy) - S.YEARS.index(rec["fiscal_year"])
            cell = _inr(rec["value"]) + ("*" if rec.get("restated") else "")
            inputs.setdefault((rec["item"], lag), {})[fy] = cell
    for (item, lag), cells in inputs.items():
        rows.append(f"| {item} [{rel.get(lag, lag)}] (INR crore) | " + " | ".join(cells.get(fy, "n/a") for fy in fys) + " |")
    return "\n".join(rows)

def compute_scores(score="all", fiscal_years=None, scope="consolidated"):
    """Altman Z'' (book equity), Piotroski F and Beneish M for each year, with every component, input and source,
    proxies disclosed, plus a ready-to-paste markdown table."""
    sc = norm_scope(scope) or "consolidated"
    key = norm_score(score)
    if not key: return {"error": f"unknown score '{score}'", "available_scores": list(SCORE_NAMES) + ["all"]}
    fys = [f for f in (norm_fy(y) for y in _list(fiscal_years)) if f in S.YEARS] or S.SCORE_YEARS
    fys = sorted(set(fys), key=S.YEARS.index)
    names = list(SCORE_NAMES) if key == "all" else [key]
    out = {n: S.all_scores(sc, fys)["scores"][n] for n in names}
    tables, notes, pages = [], [], {}
    for n in names:
        tables.append(_score_table(n, out[n], fys))
        for fy in fys:
            r = out[n][fy]
            if r["score"] is None: notes.append(f"{SCORE_NAMES[n]} {fy}: not computed ({r.get('reason') or '; '.join(r['missing'])})")
            notes += [f"{SCORE_NAMES[n]} {fy}: fallback: {f}" for f in r["fallbacks"]]
            for rec in r["inputs"].values():
                m = re.search(r"(FY\d{4}-\d{2}) Annual Report.*page (\S+)", rec["source"])
                if m: pages.setdefault(m.group(1), set()).add(m.group(2))
        proxies = dict.fromkeys(p for fy in fys for p in out[n][fy]["proxies"])
        notes += [f"{SCORE_NAMES[n]} proxy: {p}" for p in proxies]
    sources = "Sources: " + "; ".join(f"{rep} AR p. {', '.join(sorted(p))}" for rep, p in sorted(pages.items()))
    table = ("\n\n".join(tables) + "\n\nt = the scored year, t-1 = prior year; two-year scores take both years from the "
             "report of year t. * = restated in that report.\n\n" + sources)
    return {"score": key, "scope_used": sc, "unit": "INR crore", "years": fys,
            "year_convention": "FY2025-26 = year ended 31 March 2026.",
            "thresholds": {"altman_z": "> 2.60 safe; 1.10-2.60 grey; < 1.10 distress",
                           "piotroski_f": "8-9 strong; 5-7 average; 0-4 weak",
                           "beneish_m": "M > -1.78 possible earnings manipulation flag; otherwise unlikely manipulator"},
            "scores": out, "table": table, "sources": sources, "notes": notes}

FUNCS["compute_scores"] = compute_scores
SCHEMAS.append({"type": "function", "function": {"name": "compute_scores",
    "description": "Composite scores computed exactly from the verified statements: Altman Z'' (book-equity version; "
                   "safe/grey/distress), Piotroski F-score (0-9, nine signals) and Beneish M-score (8-variable earnings-"
                   "manipulation screen). Returns every component and input with sources, the proxies used, and a "
                   "ready-to-paste table. Use for questions on bankruptcy risk, financial strength or earnings quality.",
    "parameters": {"type": "object", "properties": {
        "score": {"type": "string", "enum": list(SCORE_NAMES) + ["all"], "description": "Default all"},
        "fiscal_years": {"type": "array", "items": {"type": "string", "enum": S.SCORE_YEARS}},
        "scope": {"type": "string", "enum": ["consolidated", "standalone"]}},
        "required": ["score"]}}})


# ---------- segment revenue and segment results (EBITDA) per year, from the segment reporting note ----------
import segments as SEG

def norm_segment_item(x):
    x = str(x or "").lower()
    if any(w in x for w in ("result", "ebitda", "profit", "earning")): return "segment_results"
    if "inter" in x: return "inter_segment_revenue"
    if "extern" in x: return "external_revenue"
    if "revenue" in x or "sales" in x or "turnover" in x: return "segment_revenue"
    return None

def _segment_source(rep, label):
    return f"{rep} Annual Report, consolidated segment reporting note, page {label}"

def get_segments(fiscal_years=None, items=None):
    """Segment revenue and segment results (segment EBITDA) for every segment and year, each year from the latest
    report presenting it, with source page per value, restated flags and a ready-to-paste markdown table."""
    fys = sorted({f for f in (norm_fy(y) for y in _list(fiscal_years)) if f in SEG.YEARS}, key=SEG.YEARS.index) or SEG.YEARS
    its = [i for i in SEG.ITEMS if i in {norm_segment_item(x) for x in _list(items)}] or ["segment_revenue", "segment_results"]
    r = SEG.get_segments(fys, its)
    rows = r["segments"] + [x for x in (r["eliminations"], r["totals"]) if x]
    tables, pages = [], {}
    for it in its:
        t = [f"| {SEG.ITEM_LABELS[it]} (INR crore) | " + " | ".join(fys) + " |", "|---|" + "---|" * len(fys)]
        for row in rows:
            cells = []
            for fy in fys:
                c = row["values"].get(fy, {}).get(it)
                if c is None: cells.append("-"); continue
                cells.append(_inr(c["value"]) + ("*" if c["restated"] else ""))
                pages.setdefault(c["report"], set()).add(c["page_label"])
            name = f"**{row['name']}**" if row["key"] == "total" else row["name"]
            t.append(f"| {name} | " + " | ".join(cells) + " |")
        tables.append("\n".join(t))
    sources = "Sources: " + "; ".join(_segment_source(rep, ", ".join(sorted(p))) for rep, p in sorted(pages.items()))
    notes = [f"{x['name']} {x['fiscal_year']}: {', '.join(f'{k} {_inr(v)}' for k, v in x['values'].items())} as printed in the "
             f"{x['report']} report (page {x['page_label']}); not presented in the later {x['latest_report']} report, which re-segmented that year"
             for x in r["superseded"]]
    table = ("\n\n".join(tables) + "\n\nSegment results = segment EBITDA: results before exceptional items, interest, tax and "
             "depreciation. Each year from the latest report presenting it; * = restated versus an earlier report; "
             "- = segment not reported for that year.\n\n" + sources)
    return {"unit": "INR crore", "years": fys, "items": its, "year_convention": "FY2025-26 = year ended 31 March 2026.",
            "definition": r["note"], "segments": r["segments"], "eliminations": r["eliminations"], "totals": r["totals"],
            "superseded": r["superseded"], "table": table, "sources": sources, "notes": notes}

FUNCS["get_segments"] = get_segments
SCHEMAS.append({"type": "function", "function": {"name": "get_segments",
    "description": "Exact, page-verified segment figures from the consolidated segment reporting note for every segment "
                   "(Tata Steel India, Neelachal Ispat Nigam, Tata Steel Netherlands, Tata Steel UK, Tata Steel Europe before "
                   "its split, other Indian operations, South-East Asia, rest of the world, ...), eliminations and totals, "
                   "FY2021-22 to FY2025-26. Segment \"results\" are segment EBITDA: results before exceptional items, interest, "
                   "tax and depreciation. Returns values with source pages, restated flags and a ready-to-paste table. "
                   "Use for any question on segment revenue, segment results/EBITDA or geographic performance.",
    "parameters": {"type": "object", "properties": {
        "fiscal_years": {"type": "array", "items": {"type": "string", "enum": SEG.YEARS}},
        "items": {"type": "array", "items": {"type": "string", "enum": SEG.ITEMS},
                  "description": "Default segment_revenue and segment_results"}}}}})


# ---------- DuPont analysis of ROE: every intermediate value computed and returned here, never by the model ----------
def _dupont_year(sc, fy, basis):
    """3-step and 5-step DuPont for one year. basis 'average' (default; opening + closing / 2) or 'year_end'."""
    val = lambda k, y: (FIN[sc].get(k, {}).get("values", {}).get(y) or {}).get("value") if y else None
    src = lambda k, y: (FIN[sc].get(k, {}).get("values", {}).get(y) or {}).get("source")
    t1 = YEARS[YEARS.index(fy) - 1] if fy in YEARS and YEARS.index(fy) > 0 else None
    pat, pbt, fc, rev = (val(k, fy) for k in ("profit_for_the_year", "profit_before_tax", "finance_costs", "revenue_from_operations"))
    ta, te, ta1, te1 = val("total_assets", fy), val("total_equity", fy), val("total_assets", t1), val("total_equity", t1)
    if None in (pat, pbt, fc, rev, ta, te):
        return {"fiscal_year": fy, "error": "inputs not available"}
    if basis == "average":
        if ta1 is None or te1 is None:
            return {"fiscal_year": fy, "error": f"average basis needs {t1 or 'the prior year'} balances, which are not in the reports; use basis 'year_end'"}
        a_ta, a_te = (ta + ta1) / 2, (te + te1) / 2
    else:
        a_ta, a_te = ta, te
    ebit = pbt + fc
    inputs = {"profit_for_the_year": pat, "profit_before_tax": pbt, "finance_costs": fc, "ebit (profit_before_tax + finance_costs)": round(ebit, 2),
              "revenue_from_operations": rev, f"total_assets {fy}": ta, f"total_equity {fy}": te}
    if basis == "average":
        inputs.update({f"total_assets {t1}": ta1, f"total_equity {t1}": te1,
                       "average_total_assets": round(a_ta, 3), "average_total_equity": round(a_te, 3)})
    npm, at, em = pat / rev, rev / a_ta, a_ta / a_te
    tb = pat / pbt if pbt > 0 else None                 # not meaningful for a pre-tax loss
    ib = pbt / ebit if ebit > 0 and pbt > 0 else None
    ebm = ebit / rev
    roe = pat / a_te
    out = {"fiscal_year": fy, "basis": basis, "inputs": inputs,
           "three_step": {"net_profit_margin_pct": round(npm * 100, 4), "asset_turnover_x": round(at, 4),
                          "equity_multiplier_x": round(em, 4), "roe_pct": round(roe * 100, 4),
                          "product_check_pct": round(npm * at * em * 100, 4)},
           "five_step": {"tax_burden_x": None if tb is None else round(tb, 4), "interest_burden_x": None if ib is None else round(ib, 4),
                         "ebit_margin_pct": round(ebm * 100, 4), "asset_turnover_x": round(at, 4), "equity_multiplier_x": round(em, 4),
                         "product_check_pct": None if tb is None or ib is None else round(tb * ib * ebm * at * em * 100, 4)},
           "sources": sorted({s for k in ("profit_for_the_year", "profit_before_tax", "finance_costs", "revenue_from_operations",
                                           "total_assets", "total_equity") for y in (fy, t1 if basis == "average" else None)
                              if (s := src(k, y))})}
    if tb is None: out["five_step"]["note"] = "tax and interest burden are not meaningful when profit before tax is a loss"
    return out

def dupont(fiscal_years=None, scope="consolidated", basis="average"):
    """DuPont decomposition of ROE (3-step and 5-step) for each year, with every intermediate value (averages, EBIT,
    each ratio, the product check), change of each component versus the prior year, and the composition of the change
    in total equity - so no number in a DuPont answer has to be computed by hand."""
    sc = norm_scope(scope) or "consolidated"
    b = "year_end" if "end" in str(basis or "").lower() or "closing" in str(basis or "").lower() else "average"
    fys = sorted({f for f in (norm_fy(y) for y in _list(fiscal_years)) if f in YEARS}, key=YEARS.index) or [YEARS[-1]]
    res = {fy: _dupont_year(sc, fy, b) for fy in fys}
    for fy in fys:                                        # change of each component vs the prior year
        t1 = YEARS[YEARS.index(fy) - 1] if YEARS.index(fy) > 0 else None
        prior = _dupont_year(sc, t1, b) if t1 else {"error": "no prior year"}
        if "error" in res[fy] or "error" in prior: continue
        res[fy]["prior_year"] = {"fiscal_year": t1, "three_step": prior["three_step"], "five_step": prior["five_step"]}
        res[fy]["change_vs_prior_year"] = {k: round(v - prior["three_step"][k], 4) for k, v in res[fy]["three_step"].items()
                                          if k != "product_check_pct"}
        # composition of the change in total equity (same-report basis, as get_financials)
        eq = get_financials(["equity_share_capital", "other_equity", "non_controlling_interests", "total_equity"], sc, [t1, fy])["items"]
        tot = next((c["change"] for c in eq.get("total_equity", {}).get("yoy_changes", [])), None)
        comp = {}
        for k, v in eq.items():
            c = next(iter(v["yoy_changes"]), None)
            if not c: continue
            comp[k] = {t1: c.get("prior_year_as_presented", v["values"][t1]["value"]), fy: c.get("year_as_presented", v["values"][fy]["value"]),
                       "change": c["change"], "change_pct": c["change_pct"],
                       "share_of_total_equity_change_pct": round(c["change"] / tot * 100, 2) if tot else None}
        res[fy]["equity_change"] = comp
    ok = [fy for fy in fys if "error" not in res[fy]]
    pct = lambda v: "n/a" if v is None else f"{v:.2f}%"
    xx = lambda v: "n/a" if v is None else f"{v:.4f}x"
    head = "| DuPont component | " + " | ".join(ok) + " |\n|---|" + "---|" * len(ok) + "\n"
    rows = [("Net profit margin (profit for the year / revenue)", lambda r: pct(r["three_step"]["net_profit_margin_pct"])),
            (f"Asset turnover (revenue / {'average ' if b == 'average' else ''}total assets)", lambda r: xx(r["three_step"]["asset_turnover_x"])),
            (f"Equity multiplier ({'average ' if b == 'average' else ''}total assets / {'average ' if b == 'average' else ''}total equity)", lambda r: xx(r["three_step"]["equity_multiplier_x"])),
            (f"**ROE** (profit for the year / {'average ' if b == 'average' else ''}total equity)", lambda r: f"**{pct(r['three_step']['roe_pct'])}**"),
            ("Tax burden (profit for the year / PBT)", lambda r: xx(r["five_step"]["tax_burden_x"])),
            ("Interest burden (PBT / EBIT)", lambda r: xx(r["five_step"]["interest_burden_x"])),
            ("EBIT margin (EBIT / revenue; EBIT = PBT + finance costs)", lambda r: pct(r["five_step"]["ebit_margin_pct"]))]
    table = head + "".join(f"| {n} | " + " | ".join(f(res[fy]) for fy in ok) + " |\n" for n, f in rows)
    inputs = head.replace("DuPont component", "Input (INR crore)")
    for k in (res[ok[0]]["inputs"] if ok else {}):
        inputs += f"| {k} | " + " | ".join(_inr(res[fy]["inputs"][k]) if k in res[fy]["inputs"] else "n/a" for fy in ok) + " |\n"
    avg = [f"{fy}: average total assets {res[fy]['inputs']['average_total_assets']:,.3f}, average total equity "
           f"{res[fy]['inputs']['average_total_equity']:,.3f}" for fy in ok if "average_total_assets" in res[fy]["inputs"]]
    chg = ""
    for fy in ok:
        if "change_vs_prior_year" not in res[fy]: continue
        p = res[fy]["prior_year"]
        chg += (f"\n| Component | {p['fiscal_year']} | {fy} | Change |\n|---|---|---|---|\n"
                + "".join(f"| {k} | {p['three_step'][k]:.2f} | {res[fy]['three_step'][k]:.2f} | {v:+.2f} |\n"
                          if k.endswith("pct") else f"| {k} | {p['three_step'][k]:.4f} | {res[fy]['three_step'][k]:.4f} | {v:+.4f} |\n"
                          for k, v in res[fy]["change_vs_prior_year"].items()))
        if res[fy].get("equity_change"):
            t1 = p["fiscal_year"]
            sgn = lambda v: "n/a" if v is None else f"{v:+.2f}%"
            chg += (f"\n| Change in equity (INR crore) | {t1} | {fy} | Change | % change | Share of total equity change |\n|---|---|---|---|---|---|\n"
                    + "".join(f"| {k} | {_inr(c[t1])} | {_inr(c[fy])} | {'+' if c['change'] > 0 else ''}{_inr(c['change'])} | "
                              f"{sgn(c['change_pct'])} | {pct(c['share_of_total_equity_change_pct'])} |\n"
                              for k, c in res[fy]["equity_change"].items()))
    srcs = sorted({s for fy in ok for s in res[fy]["sources"]})
    by = {}
    for s_ in srcs: by.setdefault(s_.split(" Annual Report")[0], set()).add(s_.split("page ")[-1])
    sources = "Sources: " + "; ".join(f"{r} AR p. {', '.join(sorted(p))}" for r, p in sorted(by.items()))
    return {"scope_used": sc, "basis": b, "years": fys, "unit": "INR crore; margins and ROE in %, multiples in x",
            "definitions": {"roe": f"profit_for_the_year / {'average (opening + closing) / 2' if b == 'average' else 'year-end'} total_equity",
                            "three_step": "ROE = net profit margin x asset turnover x equity multiplier",
                            "five_step": "ROE = tax burden x interest burden x EBIT margin x asset turnover x equity multiplier; "
                                         "EBIT = profit_before_tax + finance_costs (PBT is after exceptional items)"},
            "results": res, "table": table, "inputs_table": inputs, "averages": avg, "changes_table": chg.strip(),
            "sources": sources,
            "note": "Quote these values exactly (copy the tables); every intermediate value is here. Profit for the year includes "
                    "non-controlling interests, matching total equity (which includes them). other_equity is NOT retained earnings: it "
                    "also holds the securities premium, general reserve and other reserves."}

FUNCS["dupont"] = dupont
SCHEMAS.append({"type": "function", "function": {"name": "dupont",
    "description": "DuPont analysis of ROE, computed exactly from the verified statements: 3-step (net profit margin x asset "
                   "turnover x equity multiplier) and 5-step (tax burden x interest burden x EBIT margin x asset turnover x "
                   "equity multiplier), with every intermediate value (average total assets and equity, EBIT, each ratio, the "
                   "product check), the change of each component versus the prior year and the composition of the change in "
                   "total equity. Ready-to-paste tables and sources. Use for ANY DuPont or ROE-decomposition question.",
    "parameters": {"type": "object", "properties": {
        "fiscal_years": {"type": "array", "items": {"type": "string", "enum": YEARS}, "description": "Default the latest year"},
        "scope": {"type": "string", "enum": ["consolidated", "standalone"]},
        "basis": {"type": "string", "enum": ["average", "year_end"], "description": "Default average (opening + closing) / 2"}}}}})
```

---

## `src/analysis/canonical.py`

```python
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
def build(rows):
    out = defaultdict(dict)
    for key, st, prx, irx, desc in RULES:
        for r in rows:
            if r["statement"] != st or (prx and not re.search(prx, r["path"].lower())) or not re.search(irx, r["line_item"].lower()):
                continue
            slot = out[r["scope"]].setdefault(key, {"description": desc, "values": {}})["values"]
            if r["fiscal_year"] in slot: continue
            v = {"value": r["value"], "source": cite(r), "line_item": r["line_item"], "pdf_page": r["page"], "report": r["report"]}
            if r["differs_from_original"]: v.update(restated=True, originally_reported=r["original_value"])
            slot[r["fiscal_year"]] = v
    for key, st, prx, desc in SUMS:
        groups = defaultdict(list)
        for r in rows:
            if r["statement"] == st and re.search(prx, r["path"].lower()): groups[(r["scope"], r["fiscal_year"])].append(r)
        for (sc, fy), rs in groups.items():
            out[sc].setdefault(key, {"description": desc, "values": {}})["values"][fy] = {
                "value": round(sum(r["value"] for r in rs), 2), "source": cite(rs[0]) + f" (sum of {len(rs)} rows)",
                "components": {r["line_item"]: r["value"] for r in rs}, "pdf_page": rs[0]["page"], "report": rs[0]["report"]}
    return out

out = build(pref)
(PROC / "financials.json").write_text(json.dumps(out, indent=1))
by_report = {rep: build([r for r in recs if r["report"] == rep and not r.get("synthetic_label")])
             for rep in sorted({r["report"] for r in recs})}
(PROC / "financials_by_report.json").write_text(json.dumps(by_report, indent=1))

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
```

---

## `src/analysis/regions.py`

```python
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
```

---

## `src/analysis/scores.py`

```python
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
SCORE_YEARS = ["FY2021-22", "FY2022-23", "FY2023-24", "FY2024-25", "FY2025-26"]
# FY2021-22 is only a comparative column of the FY2022-23 report: Altman (single year) works, but two-year scores
# would need FY2020-21, which no report contains.
NO_PRIOR_REASON = "needs FY2020-21, which is outside the four reports"

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
    if fy == YEARS[0]:
        return _result("piotroski_f", fy, scope, ins, f"{fy} vs FY2020-21 (not in the reports)", proxies, extra={"reason": NO_PRIOR_REASON})
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
    if fy == YEARS[0]:
        return _result("beneish_m", fy, scope, ins, f"{fy} vs FY2020-21 (not in the reports)", proxies, extra={"reason": NO_PRIOR_REASON})
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
    """Every score for every requested year (default FY2021-22..FY2025-26)."""
    fys = list(fiscal_years or SCORE_YEARS)
    return {"scope": scope, "years": fys, "scores": {n: {fy: _safe(fn, fy, scope) for fy in fys} for n, fn in SCORES.items()}}
```

---

## `src/analysis/segments.py`

```python
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
```

---

## `src/api/main.py`

```python
"""FastAPI backend implementing the API contract in the frontend brief (Section 5).

Endpoints: /api/health, /api/ask, /api/financials, /api/items, /api/metrics, /api/scores, /api/segments, /api/regions,
/api/statements, /api/statement-pdf, /api/pdf/{report}, /api/company, /api/evaluation, /api/reports.
Run from the repo root:  uvicorn main:app --app-dir src/api --host 0.0.0.0 --port 8000
"""
import json, re, sys, time, uuid
from pathlib import Path
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, Response
from typing import List, Literal
from pydantic import BaseModel, Field

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src" / "agent")); sys.path.insert(0, str(ROOT / "src" / "retrieval"))
import agent as A
from tools import FIN, ITEMS as LINE_ITEMS, YEARS, compute_metric, get_financials
from search import client as qdrant, COLL
sys.path.insert(0, str(ROOT / "src" / "analysis"))
from scores import SCORE_YEARS, all_scores

app = FastAPI(title="Tata Steel Financial Analysis RAG", version="1.0.0")
app.add_middleware(CORSMiddleware, allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
                   allow_methods=["*"], allow_headers=["*"])

REPORTS = [
    {"fiscal_year": "FY2022-23", "title": "116th Integrated Report & Annual Accounts 2022-23", "official_url": "https://www.tatasteel.com/media/18370/tata-steel-ir-2022-23.pdf"},
    {"fiscal_year": "FY2023-24", "title": "117th Integrated Report & Annual Accounts 2023-24", "official_url": "https://www.tatasteel.com/media/21244/integrated-report-and-annual-accounts-fy2023-24.pdf"},
    {"fiscal_year": "FY2024-25", "title": "118th Integrated Report & Annual Accounts 2024-25", "official_url": "https://www.tatasteel.com/media/23973/fy25-integratedreport.pdf"},
    {"fiscal_year": "FY2025-26", "title": "119th Integrated Report & Annual Accounts 2025-26", "official_url": "https://www.tatasteel.com/media/25904/tatasteel-iar-2025-26.pdf"}]
for r in REPORTS: r["pdf_url"] = f"/api/pdf/{r['fiscal_year']}"     # served locally: tatasteel.com blocks deep links (HTTP 403)
PDF_PATH = {r["fiscal_year"]: ROOT / "data/raw" / f"TataSteel_{r['fiscal_year']}.pdf" for r in REPORTS}
PAGE_MAPS = {r["fiscal_year"]: json.loads((ROOT / "data/interim" / f"page_map_{r['fiscal_year']}.json").read_text()) for r in REPORTS}
for r in REPORTS: r["pages"] = len(PAGE_MAPS[r["fiscal_year"]])
LABEL_TO_PDF = {fy: {p["label"]: p["page"] for p in pm if p["label"]} for fy, pm in PAGE_MAPS.items()}

def pdf_url(report, pdf_page=None):
    """Relative link to the locally served report, opening at pdf_page (1-based) if given."""
    return f"/api/pdf/{report}" + (f"#page={pdf_page}" if pdf_page else "")
SRC_RE = re.compile(r"(FY\d{4}-\d{2}) Annual Report, ([^,]+?), pages? (F\d{1,3}|PDF p\d+)")
METRICS = [  # key, name, formula, unit, decimals, higher_is_better
    ("current_ratio", "Current ratio", "total_current_assets / total_current_liabilities", "x", 2, True),
    ("debt_to_equity", "Debt-to-equity", "(non_current_borrowings + current_borrowings) / total_equity", "x", 2, False),
    ("interest_coverage", "Interest coverage", "(profit_before_tax + finance_costs) / finance_costs", "x", 2, True),
    ("net_profit_margin", "Net profit margin", "profit_for_the_year / revenue_from_operations * 100", "%", 2, True),
    ("ebitda_margin", "EBITDA margin",
     "(profit_before_exceptional_and_tax + finance_costs + depreciation_amortisation - other_income) / revenue_from_operations * 100", "%", 2, True),
    ("roe", "Return on equity (avg equity)", "profit_for_the_year / avg(total_equity) * 100", "%", 2, True),
    ("net_debt", "Net debt (borrowings + leases - cash, bank balances and current investments)",
     "non_current_borrowings + current_borrowings + non_current_lease_liabilities + current_lease_liabilities"
     " - cash_and_cash_equivalents - other_bank_balances - current_investments", "INR crore", 2, False)]

class HistoryMessage(BaseModel):
    role: Literal["user", "assistant"]
    content: str = Field(..., max_length=20000)

class AskRequest(BaseModel):
    question: str = Field(..., min_length=3, max_length=2000)
    history: List[HistoryMessage] = Field(default_factory=list, max_length=20)

@app.exception_handler(Exception)
async def unhandled(request, exc):
    return JSONResponse(status_code=500, content={"error": f"Internal error: {exc}"})

def describe(t):
    a, n = t["args"], t["tool"]
    if n == "get_financials":
        items = a.get("items"); items = ", ".join(items) if isinstance(items, list) else items
        return f"Fetched {items} ({a.get('scope') or 'consolidated'})"
    if n == "compute_metric": return f"Computed {a.get('formula')}"
    if n == "breakdown": return f"Broke down {a.get('total')} from {a.get('from_year')} to {a.get('to_year')}"
    if n == "search_documents": return f'Searched the reports for "{a.get("query")}"' + (f" in {a['report']}" if a.get("report") else "")
    if n == "get_line_items": return f'Looked up "{a.get("query")}"'
    if n == "calculate": return f"Calculated {a.get('expression')}"
    if n == "dupont": return f"DuPont analysis of ROE ({a.get('scope') or 'consolidated'}, {a.get('basis') or 'average'} basis)"
    return json.dumps(a)[:150]

def build_citations(answer, trace):
    found = {}
    for t in trace:
        for rep, sec, pg in SRC_RE.findall(t.get("result", "")):
            label, pdf = (None, int(pg[5:])) if pg.startswith("PDF p") else (pg, LABEL_TO_PDF.get(rep, {}).get(pg))
            key = (rep, label or f"p{pdf}")
            if key not in found:
                found[key] = {"report": rep, "section": sec.strip(), "page_label": label, "pdf_page": pdf,
                              "pdf_url": pdf_url(rep, pdf) if rep in PDF_PATH else None}
    cited = [c for c in found.values() if c["page_label"] and re.search(rf"\b{c['page_label']}\b", answer)]
    return cited or list(found.values())[:8]

@app.get("/api/health")
def health():
    try: pts = qdrant.count(COLL).count
    except Exception: pts = None
    return {"status": "ok" if pts else "degraded", "llm_model": A.MODELS[0], "index_points": pts,
            "reports": [r["fiscal_year"] for r in REPORTS], "version": "1.0.0"}

@app.post("/api/ask")
def ask(req: AskRequest):
    t0 = time.time()
    try:
        _, info = A.ask(req.question, verbose=False, history=[m.model_dump() for m in req.history])
    except Exception as e:
        return JSONResponse(status_code=503, content={"error": f"The AI model is temporarily unavailable: {str(e)[:200]}"})
    body = info.get("answer_body") or "I could not complete this analysis within the step limit."
    total, unverified, warnings = info.get("total", 0), info.get("unverified", []), info.get("warnings", [])
    status = "not_applicable" if total == 0 else ("verified" if not unverified and not warnings else "partially_verified")
    return {"id": str(uuid.uuid4()), "question": req.question, "answer_markdown": body,
            "verification": {"status": status, "figures_grounded": info.get("grounded", 0), "figures_total": total,
                             "unverified_figures": unverified, "warnings": warnings},
            "citations": build_citations(body, info.get("trace", [])),
            "steps": [{"tool": t["tool"], "description": describe(t)} for t in info.get("trace", [])],
            "model": A.MODELS[0], "elapsed_seconds": round(time.time() - t0, 1)}

@app.get("/api/financials")
def financials(items: str, scope: str = "consolidated"):
    sc = "standalone" if scope == "standalone" else "consolidated"
    r = get_financials([k.strip() for k in items.split(",") if k.strip()], scope=sc)
    out = {k: {"description": v["description"],
               "values": {fy: {"value": x["value"], "source": x["source"], "restated": bool(x.get("restated"))} for fy, x in v["values"].items()},
               "yoy_changes": [{"from": c["from"], "to": c["to"], "change": c["change"], "change_pct": c["change_pct"],
                                "restated_basis": "prior_year_as_presented" in c} for c in v["yoy_changes"]]}
           for k, v in r["items"].items()}
    return {"scope": sc, "unit": "INR crore", "years": YEARS, "items": out, "unknown_items": r.get("unknown_items", [])}

@app.get("/api/items")
def items():
    return {sc: [{"key": k, "description": v["description"]} for k, v in sorted(FIN[sc].items())] for sc in ("consolidated", "standalone")}

@app.get("/api/metrics")
def metrics(scope: str = "consolidated"):
    sc = "standalone" if scope == "standalone" else "consolidated"
    out = []
    for key, name, formula, unit, dec, hib in METRICS:
        r = compute_metric(formula, scope=sc, fiscal_years=YEARS, decimals=4)
        out.append({"key": key, "name": name, "formula": formula, "unit": unit, "decimals": dec,
                    "higher_is_better": hib, "values": r.get("values", {fy: None for fy in YEARS})})
    return {"scope": sc, "years": YEARS, "metrics": out}

@app.get("/api/scores")
def scores(scope: str = "consolidated"):
    sc = "standalone" if scope == "standalone" else "consolidated"
    return all_scores(sc, SCORE_YEARS)

@app.get("/api/segments")
def segments():
    from segments import get_segments as segment_data
    r = segment_data()
    def row(s):
        return {"key": s["key"], "name": s["name"],
                "values": {fy: {i: c["value"] for i, c in v.items()} for fy, v in s["values"].items()},
                "sources": {fy: {**{k: next(iter(v.values()))[k] for k in ("report", "page_label", "pdf_page")},
                                 "url": pdf_url(next(iter(v.values()))["report"], next(iter(v.values()))["pdf_page"])}
                            for fy, v in s["values"].items()},
                "restated": {fy: [i for i, c in v.items() if c["restated"]] for fy, v in s["values"].items() if any(c["restated"] for c in v.values())}}
    return {"unit": r["unit"], "years": r["years"], "items": r["items"], "note": r["note"],
            "segments": [row(s) for s in r["segments"]], "eliminations": row(r["eliminations"]), "totals": row(r["totals"])}

@app.get("/api/regions")
def regions():
    from regions import get_regions
    return get_regions()

# ---------- local PDFs and statement-only PDFs ----------
STATEMENTS = {"profit_and_loss": "statement of profit and loss", "balance_sheet": "balance sheet",
              "cash_flow": "statement of cash flows"}
SCOPES = ("consolidated", "standalone")

def _statement_pages():
    """{(report, scope, statement): [(pdf_page, label)]} from the page map, validated: pages contiguous, every page
    printed-labelled, and exactly the pages the extracted line items (line_items.jsonl) came from."""
    from_items = {}
    for r in LINE_ITEMS:
        from_items.setdefault((r["report"], r["scope"], r["statement"]), set()).add((r["page"], r["page_label"]))
    out, problems = {}, []
    for rep, pm in PAGE_MAPS.items():
        for sc in SCOPES:
            for st in STATEMENTS:
                pages = sorted((p["page"], p["label"]) for p in pm if p["scope"] == sc and p["statement"] == st)
                nums = [p for p, _ in pages]
                if not pages or any(not lab for _, lab in pages) or nums != list(range(nums[0], nums[-1] + 1)):
                    problems.append(f"{rep} {sc} {st}: page map gives {pages}"); continue
                if set(pages) != from_items.get((rep, sc, st), set()):
                    problems.append(f"{rep} {sc} {st}: page map {pages} != line-item pages {sorted(from_items.get((rep, sc, st), []))}"); continue
                out[(rep, sc, st)] = pages
    return out, problems

STATEMENT_PAGES, STATEMENT_PAGE_PROBLEMS = _statement_pages()
_STATEMENT_PDF_CACHE = {}

def _err(code, msg):
    return JSONResponse(status_code=code, content={"error": msg})

@app.get("/api/pdf/{report}")
def report_pdf(report: str):
    path = PDF_PATH.get(report)
    if not path or not path.exists(): return _err(404, f"unknown report '{report}'; available: {', '.join(PDF_PATH)}")
    return FileResponse(path, media_type="application/pdf",
                        headers={"Content-Disposition": f'inline; filename="{path.name}"'})

def statement_url(report, scope, statement):
    return f"/api/statement-pdf?report={report}&scope={scope}&statement={statement}"

@app.get("/api/statements")
def statements(scope: str = "consolidated"):
    sc = "standalone" if scope == "standalone" else "consolidated"
    out = {}
    for fy in YEARS:
        rep = fy if fy in PDF_PATH else "FY2022-23"          # FY2021-22 only exists as the FY2022-23 comparative column
        row = {}
        for st in STATEMENTS:
            pages = STATEMENT_PAGES.get((rep, sc, st))
            if not pages: row[st] = None; continue
            row[st] = {"report": rep, "page_labels": [lab for _, lab in pages], "pdf_pages": [p for p, _ in pages],
                       "url": statement_url(rep, sc, st)}
            if rep != fy: row[st]["note"] = "comparative column of the FY2022-23 report"
        out[fy] = row
    return {"scope": sc, "years": YEARS, "statements": out}

@app.get("/api/statement-pdf")
def statement_pdf(report: str, scope: str, statement: str):
    if report not in PDF_PATH: return _err(404, f"unknown report '{report}'")
    if scope not in SCOPES: return _err(404, f"unknown scope '{scope}'; use consolidated or standalone")
    if statement not in STATEMENTS: return _err(404, f"unknown statement '{statement}'; use {', '.join(STATEMENTS)}")
    key = (report, scope, statement)
    pages = STATEMENT_PAGES.get(key)
    if not pages: return _err(404, f"no validated pages for {report} {scope} {statement}")
    if key not in _STATEMENT_PDF_CACHE:
        try: import pymupdf
        except ImportError: return _err(503, "PDF extraction is unavailable on this server (PyMuPDF is not installed)")
        src = pymupdf.open(PDF_PATH[report])
        for p, lab in pages:                                  # the printed label must be on the page itself
            if not re.search(rf"\b{lab}\b", src[p - 1].get_text()):
                return _err(500, f"page {p} of the {report} report does not show label {lab}")
        label = pages[0][1] if len(pages) == 1 else f"{pages[0][1]}-{pages[-1][1]}"
        out = pymupdf.open()
        out.insert_pdf(src, from_page=pages[0][0] - 1, to_page=pages[-1][0] - 1)
        out.set_metadata({"title": f"Tata Steel {report} {scope} {STATEMENTS[statement]} ({label})",
                          "author": "Tata Steel Limited", "subject": f"From the {report} Integrated Report & Annual Accounts, pages {label}"})
        _STATEMENT_PDF_CACHE[key] = (out.tobytes(garbage=3, deflate=True), label)
    data, label = _STATEMENT_PDF_CACHE[key]
    return Response(content=data, media_type="application/pdf",
                    headers={"Content-Disposition": f'inline; filename="TataSteel_{report}_{scope}_{statement}_{label}.pdf"'})

@app.get("/api/company")
def company():
    path = ROOT / "data/processed/company.json"
    if not path.exists(): return _err(404, "company facts not built; run src/ingest/company_facts.py")
    return json.loads(path.read_text())

@app.get("/api/evaluation")
def evaluation():
    runs = sorted((ROOT / "eval/results").glob("run_*.json"))
    full = [r for r in runs if len(json.loads(r.read_text()).get("records", [])) >= 25]   # ignore partial test runs
    runs = full or runs
    if not runs: return {"available": False}
    data, st = json.loads(runs[-1].read_text()), runs[-1].stem[4:]
    keep = ("id", "category", "question", "numeric", "citation", "mentions", "abstention_ok", "grounded", "seconds")
    return {"available": True, "run_at": f"{st[:4]}-{st[4:6]}-{st[6:8]}T{st[9:11]}:{st[11:13]}:00",
            "summary": data["summary"], "records": [{k: r.get(k) for k in keep} for r in data["records"]]}

@app.get("/api/reports")
def reports():
    return REPORTS
```

---

## `src/index/build_index.py`

```python
"""Stage 5: embed every chunk (dense bge-base + sparse BM25) and load into Qdrant with payload indexes."""
import json, sys, time
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "retrieval"))
from qdrant_client import models
from search import client, dense, sparse, COLL

chunks = [json.loads(l) for l in open("data/processed/chunks.jsonl")]
if client.collection_exists(COLL): client.delete_collection(COLL)
client.create_collection(COLL,
    vectors_config={"dense": models.VectorParams(size=768, distance=models.Distance.COSINE)},
    sparse_vectors_config={"bm25": models.SparseVectorParams(modifier=models.Modifier.IDF)})
for field, schema in [("report", "keyword"), ("fiscal_years", "keyword"), ("scope", "keyword"), ("section", "keyword"),
                      ("type", "keyword"), ("topics", "keyword"), ("page", "integer")]:
    client.create_payload_index(COLL, field, field_schema=schema)

texts = [c["text"] for c in chunks]
t = time.time()
dv = list(dense.embed(texts, batch_size=32))
print(f"Dense embeddings: {len(dv)} in {time.time() - t:.0f}s", flush=True)
t = time.time()
sv = list(sparse.embed(texts, batch_size=64))
print(f"Sparse embeddings: {len(sv)} in {time.time() - t:.0f}s", flush=True)
client.upload_points(COLL, [models.PointStruct(id=c["chunk_id"], payload=c, vector={
    "dense": d.tolist(), "bm25": models.SparseVector(indices=s.indices.tolist(), values=s.values.tolist())})
    for c, d, s in zip(chunks, dv, sv)], batch_size=128)
print(f"Indexed {client.count(COLL).count} points into '{COLL}'")
```

---

## `src/ingest/build_chunks.py`

```python
"""Stage 4: build retrieval chunks from all four reports.

  statement_table - each primary statement page as a clean markdown table, from verified line items
  note_table      - Docling tables from notes / auditor report / other FS pages, tagged with note title
  fs_text         - narrative paragraphs inside the FS section (policies, key audit matters, contingencies)
  narrative       - integrated report and statutory report pages (MD&A, risk, strategy, Directors' Report)
Output: data/processed/chunks.jsonl
"""
import json, re
from collections import defaultdict, Counter
from pathlib import Path
import pymupdf
from docling_core.types.doc import DoclingDocument, TableItem, TextItem, SectionHeaderItem

INTERIM, PROC = Path("data/interim"), Path("data/processed")
PRIMARY = {"balance_sheet", "profit_and_loss", "cash_flow"}
NOTE_TITLE = re.compile(r"^\d{1,2}[A-Z]?\.\s+\S")
NOISE = re.compile(r"^(?:\d{1,3}\s*)?F\d{1,3}$|annual accounts 20\d\d|^financial statements$|^notes forming part", re.I)
MAX_WORDS, TABLE_ROWS = 450, 40
TOPICS = [("risk", r"\brisk"), ("mdna", r"management discussion|md&a"), ("directors_report", r"board.s report|directors.? report"),
          ("governance", r"corporate governance"), ("sustainability", r"sustainab|brsr|climate|emission|decarboni"),
          ("strategy", r"strateg|outlook|capital allocation"), ("segments", r"netherlands|united kingdom|\buk\b|thailand|segment")]

def prior(fy): y = int(fy[2:6]); return f"FY{y - 1}-{str(y)[2:]}"
def topics(s): s = s.lower(); return [k for k, rx in TOPICS if re.search(rx, s)] or ["general"]
def narrative_topics(title, text):
    t = topics(title + " " + text[:400])
    if "risk" in t and not re.search(r"risk", title, re.I) and text.lower().count("risk") < 3: t.remove("risk")
    return t or ["general"]

def inr(v):
    i, d = f"{abs(v):.2f}".split(".")
    if len(i) > 3:
        head, parts = i[:-3], []
        while len(head) > 2: parts.insert(0, head[-2:]); head = head[:-2]
        if head: parts.insert(0, head)
        i = ",".join(parts + [i[-3:]])
    return ("-" if v < 0 else "") + i + "." + d

chunks = []

# 1) statement_table chunks from verified line items
recs = [json.loads(l) for l in open(PROC / "line_items.jsonl")]
groups = defaultdict(list)
for r in recs: groups[(r["report"], r["scope"], r["statement"], r["page"], r["page_label"])].append(r)
for (rep, sc, st, pg, lab), rs in groups.items():
    years = sorted({r["fiscal_year"] for r in rs}, reverse=True)
    rows = {}
    for r in rs: rows.setdefault((r["path"], r["line_item"]), {})[r["fiscal_year"]] = r["value"]
    flag = " | contains restated comparatives" if any(r["differs_from_original"] or r["restated"] for r in rs) else ""
    lines = [f"Tata Steel | {sc.title()} {st.replace('_', ' ').title()} | {rep} Annual Report | page {lab} (PDF p{pg}) | Rs crore{flag}", "",
             "| Line item | " + " | ".join(years) + " |", "|" + "---|" * (len(years) + 1)]
    for (path, item), vals in rows.items():
        lines.append(f"| {(path + ' > ' if path else '') + item} | " + " | ".join(inr(vals[y]) if y in vals else "" for y in years) + " |")
    chunks.append(dict(type="statement_table", report=rep, fiscal_years=years, scope=sc, section=st, note="",
                       topics=["financials"], page=pg, page_label=lab, text="\n".join(lines)))

for path in sorted(INTERIM.glob("docling_FY*.json")):
    rep = path.stem.split("_")[1]
    pm = {p["page"]: p for p in json.loads((INTERIM / f"page_map_{rep}.json").read_text())}

    # 2) note_table and 3) fs_text chunks from Docling
    doc = DoclingDocument.load_from_json(path)
    note, sub, last_stmt, paras = "", "", None, []
    scope_name = lambda m: (m.get("scope") or "standalone & group").title()
    for item, _ in doc.iterate_items():
        if not getattr(item, "prov", None): continue
        pg = item.prov[0].page_no
        meta = pm.get(pg, {})
        stmt = meta.get("statement")
        if stmt in PRIMARY: continue
        if stmt != last_stmt: note, sub, last_stmt = "", "", stmt
        if isinstance(item, TableItem):
            md = item.export_to_markdown(doc=doc).replace("(I crore)", "(Rs crore)")
            if len(md) < 40 or not re.search(r"\d", md) or "sd/-" in md or "DIN:" in md: continue
            label = " > ".join(x for x in (note, sub) if x)
            head = (f"Tata Steel | {scope_name(meta)} {stmt} | {label} | {rep} Annual Report | "
                    f"page {meta.get('label')} (PDF p{pg}) | Rs crore unless stated")
            tl = md.split("\n")
            for i in range(0, max(1, len(tl) - 2), TABLE_ROWS):
                part = "\n".join(tl[:2] + tl[2 + i: 2 + i + TABLE_ROWS])
                chunks.append(dict(type="note_table", report=rep, fiscal_years=[rep, prior(rep)], scope=meta.get("scope"),
                                   section=stmt, note=label, topics=["financials"], page=pg,
                                   page_label=meta.get("label"), text=head + "\n\n" + part))
        elif isinstance(item, TextItem):
            t = " ".join(item.text.split())
            if not t or NOISE.search(t): continue
            if stmt == "notes" and NOTE_TITLE.match(t) and len(t) < 120:
                note, sub = re.sub(r"\s*\(contd\.?\)", "", t, flags=re.I), ""
            elif isinstance(item, SectionHeaderItem):
                sub, t = re.sub(r"\s*\(contd\.?\)", "", t, flags=re.I), "## " + t
            paras.append((note, stmt, pg, meta, t, sub))
    buf, words = [], 0
    def flush():
        global buf, words
        n_words = sum(len(b[4].split()) for b in buf)
        if buf and n_words >= 12:
            n, st, pg0, m = buf[0][0], buf[0][1], buf[0][2], buf[0][3]
            label = n or next((b[5] for b in buf if b[5]), "")
            body = " ".join(b[4] for b in buf)
            chunks.append(dict(type="fs_text", report=rep, fiscal_years=[rep, prior(rep)], scope=m.get("scope"),
                               section=st, note=label, topics=topics(label + " " + body[:400]), page=pg0,
                               page_label=m.get("label"),
                               text=f"Tata Steel | {scope_name(m)} {st} | {label} | {rep} Annual Report | "
                                    f"page {m.get('label')} (PDF p{pg0})\n\n{body}"))
        buf, words = [], 0
    for p in paras:
        if buf and ((p[0], p[1]) != (buf[0][0], buf[0][1]) or words > MAX_WORDS): flush()
        buf.append(p); words += len(p[4].split())
    flush()

    # 4) narrative chunks from non-FS pages (PyMuPDF, visual reading order)
    pdf = pymupdf.open(f"data/raw/TataSteel_{rep}.pdf")
    for p in pm.values():
        if p["section"] == "financial_statements": continue
        page = pdf[p["page"] - 1]
        w = " ".join(b[4] for b in page.get_text("blocks")).split()
        if len(w) < 40: continue
        h = page.rect.height
        title = " ".join(" ".join(b[4].split()) for b in sorted(page.get_text("blocks"), key=lambda b: (b[1], b[0]))
                         if b[1] < h * 0.16 and (b[3] - b[1]) < 50)[:150]
        for i in range(0, len(w), MAX_WORDS):
            piece = " ".join(w[i:i + MAX_WORDS + 50])
            chunks.append(dict(type="narrative", report=rep, fiscal_years=[rep], scope=None, section=p["section"], note=title,
                               topics=narrative_topics(title, piece), page=p["page"], page_label=None,
                               text=f"Tata Steel | {rep} Annual Report | {p['section'].replace('_', ' ')} | {title} | PDF p{p['page']}\n\n{piece}"))

for i, c in enumerate(chunks): c["chunk_id"] = i
with open(PROC / "chunks.jsonl", "w") as f:
    for c in chunks: f.write(json.dumps(c) + "\n")

print(f"{len(chunks)} chunks written to data/processed/chunks.jsonl\n")
cnt = Counter((c["report"], c["type"]) for c in chunks)
for rep in sorted({c["report"] for c in chunks}):
    print(f"  {rep}: " + ", ".join(f"{t}={cnt[(rep, t)]}" for t in ("statement_table", "note_table", "fs_text", "narrative")))
wl = [len(c["text"].split()) for c in chunks]
print(f"\nWords per chunk: min {min(wl)}, median {sorted(wl)[len(wl)//2]}, max {max(wl)}")
print(f"Note tables with a note title: {sum(1 for c in chunks if c['type']=='note_table' and c['note'])}/{sum(1 for c in chunks if c['type']=='note_table')}")
print(f"Narrative chunks tagged 'risk': {sum(1 for c in chunks if c['type']=='narrative' and 'risk' in c['topics'])}")
samples = [
    ("statement_table", lambda c: c["type"] == "statement_table"),
    ("note_table: consolidated borrowings", lambda c: c["type"] == "note_table" and c["scope"] == "consolidated" and "borrowing" in c["note"].lower()),
    ("fs_text: consolidated key audit matters", lambda c: c["type"] == "fs_text" and c["scope"] == "consolidated" and c["section"] == "auditor_report" and "key audit matter" in c["text"].lower()),
    ("narrative: risk", lambda c: c["type"] == "narrative" and "risk" in c["topics"]),
]
for name, cond in samples:
    c = next((c for c in chunks if c["report"] == "FY2025-26" and cond(c)), None)
    print(f"\n===== SAMPLE {name} =====\n" + (c["text"][:600] if c else "NOT FOUND"))
notes = sorted({c["note"] for c in chunks if c["report"] == "FY2025-26" and c["scope"] == "consolidated" and c["type"] == "note_table"})
print(f"\nFY2025-26 consolidated note-table titles ({len(notes)} distinct), first 15:")
for n in notes[:15]: print("  ", n[:100])
```

---

## `src/ingest/company_facts.py`

```python
"""'About Tata Steel' facts for the Home page, from the corporate overview pages of the FY2025-26 report.

Each statement is written in plain words from one PDF page and cites it (report, printed page label, 1-based PDF
page, local URL). The overview pages are two-page spreads, so the printed label is the pair printed on the spread
(e.g. "10-11"); the pair must appear on the page. Verification: every number (digits, with a trailing "+" if written)
and every proper noun (capitalised word not opening a sentence, plus acronyms) in a statement must appear in the
whitespace-normalised pymupdf text of its cited page. A ✓/✗ table is printed; a statement with any ✗ is dropped.
No forward-looking claims (targets, plans, "will").
Output: data/processed/company.json
"""
import json, re, sys
from pathlib import Path
import pymupdf

ROOT = Path(__file__).resolve().parents[2]
REPORT = "FY2025-26"
PDF = ROOT / "data/raw" / f"TataSteel_{REPORT}.pdf"
OUT = ROOT / "data/processed/company.json"

FACTS = [  # (statement, pdf_page, printed page label of the spread)
    ("Tata Steel is a globally diversified integrated steel producer with a combined steelmaking capacity of 36 MTPA "
     "across India, the Netherlands, the UK and Thailand.", 8, "10-11"),
    ("In India it makes steel at Jamshedpur and Gamharia in Jharkhand, Kalinganagar and Meramandali in Odisha, and at "
     "an Electric Arc Furnace (EAF) plant in Ludhiana, Punjab, and it runs captive coal, iron ore, chromite and "
     "manganese mines.", 9, "12-13"),
    ("Tata Steel Nederland makes flat steel at IJmuiden (7 MTPA) for automotive, construction, packaging and heavy "
     "equipment customers; Tata Steel Thailand runs three EAF plants with a combined capacity of 1.7 MTPA.", 9, "12-13"),
    ("It has 77,000+ employees across the globe, and Tata Steel Minerals Canada operates iron ore assets in Labrador "
     "and Northern Quebec, Canada.", 9, "12-13"),
    ("In the year covered by the 2025-26 report, Tata Steel Consolidated produced 31.67 MT of steel and delivered "
     "31.97 MT, with a turnover of ₹2,32,140 crore and EBITDA of ₹34,848 crore.", 5, "4-5"),
]
FORWARD = re.compile(r"\b(will|plans?|target(?:s|ed)?|aims?|expects?|intends?|going to|by 20\d\d)\b", re.I)
SKIP = {"In", "It", "The", "A", "An", "With", "Its", "And"}   # ordinary words when they open a sentence or clause
NUM_WORDS = r"\b(?:one|two|three|four|five|six|seven|eight|nine|ten|eleven|twelve)\b"

def norm(s):
    return re.sub(r"\s+", " ", s).replace("‑", "-").strip()

def tokens(statement):
    """Numbers and proper nouns that must be found on the page."""
    nums = re.findall(r"\d{4}-\d{2}|\d[\d,]*(?:\.\d+)?\+?", statement) + re.findall(NUM_WORDS, statement, re.I)
    names = [w for w in re.findall(r"\b[A-Z][A-Za-z]*\b", statement) if w not in SKIP]
    return list(dict.fromkeys(nums)), list(dict.fromkeys(names))

def on_page(tok, text):
    if tok.isalpha(): return re.search(rf"\b{tok}\b", text, re.I) is not None     # number words ("three")
    return re.search(rf"(?<![\w.,]){re.escape(tok)}(?![\w]|[.,]\d)", text) is not None

def build():
    doc = pymupdf.open(PDF)
    rows, facts = [], []
    for statement, pg, label in FACTS:
        text = norm(doc[pg - 1].get_text())
        a, b = label.split("-")
        checks = [(f"page label {label}", bool(re.search(rf"\b(?:{a} {b}|{b} {a})\b", text)))]
        nums, names = tokens(statement)
        checks += [(t, on_page(t, text)) for t in nums + names]
        checks.append(("no forward-looking wording", not FORWARD.search(statement)))
        ok = all(c for _, c in checks)
        rows.append((statement, pg, label, checks, ok))
        if ok:
            facts.append({"text": statement, "report": REPORT, "page_label": label, "pdf_page": pg,
                          "url": f"/api/pdf/{REPORT}#page={pg}"})
    return facts, rows

if __name__ == "__main__":
    facts, rows = build()
    for i, (statement, pg, label, checks, ok) in enumerate(rows, 1):
        print(f"\n[{i}] {'✓ kept' if ok else '✗ dropped'}  (PDF p{pg}, printed pages {label})\n    {statement}")
        for t, c in checks: print(f"      {'✓' if c else '✗'} {t}")
    print(f"\n{len(facts)} of {len(rows)} statements verified")
    if not 3 <= len(facts) <= 5: sys.exit("expected 3-5 verified statements; company.json not written")
    OUT.write_text(json.dumps({"title": "About Tata Steel", "source": f"{REPORT} Integrated Report & Annual Accounts, "
                               "corporate overview (Highlights of the Year, Corporate Portrait)", "facts": facts}, indent=2,
                              ensure_ascii=False) + "\n")
    print(f"written to {OUT.relative_to(ROOT)}")
```

---

## `src/ingest/line_items.py`

```python
"""Stage 3: extract clean, verified line items from the primary statements (BS, P&L, cash flow).

Uses the coordinate line reader: Docling merged and shifted rows on dense single-page
statements (e.g. FY23 standalone balance sheet), while these pages have a simple
label-plus-value-columns layout. Docling is kept for the notes tables.
Checks: Total assets == Total equity and liabilities; section items sum to their Total row.
Output: data/processed/line_items.jsonl
"""
import json, re, statistics, sys
from pathlib import Path
import pymupdf
sys.path.insert(0, str(Path(__file__).parent))
from statement_lines import page_lines

INTERIM, OUT = Path("data/interim"), Path("data/processed")
OUT.mkdir(parents=True, exist_ok=True)
PRIMARY = ("balance_sheet", "profit_and_loss", "cash_flow")
MARKER = re.compile(r"^\((?:[ivxlc]{1,5}|[a-zA-Z])\)$|^(?:I|II|III|IV|V|VI|VII|VIII|IX|X)$")
REF = re.compile(r"^(?:F\d{1,3}|\d{1,3})$")
IGNORE = re.compile(r"^(?:consolidated )?(?:balance sheet|statement of)|^(?:as at|year ended|for the year|note|march 31|particulars)|^\(?i crore\)?$", re.I)
STOP = re.compile(r"^(?:notes forming part|in terms of our report|for and on behalf)", re.I)
TOP = re.compile(r"^(?:non-current assets|current assets|equity|non-current liabilities|current liabilities|assets|"
                 r"income|expenses|other comprehensive income|.*cash flows? (?:from|used in))", re.I)
CHECK = {"non-current assets", "current assets", "non-current liabilities", "current liabilities"}

ROMAN = {"i": 1, "ii": 2, "iii": 3, "iv": 4, "v": 5, "vi": 6, "vii": 7, "viii": 8, "ix": 9, "x": 10, "xi": 11, "xii": 12}

def marker_of(text, last_letter):
    """Return ('letter', n) or ('roman', n) for a leading (a)/(iv) marker. '(i)' after '(h)' is the letter i."""
    m = re.match(r"^\s*\(([a-z]{1,4})\)", text)
    if not m: return None
    s = m.group(1)
    if len(s) == 1 and not (s in "ivx" and ord(s) - 96 != last_letter + 1):
        return ("letter", ord(s) - 96)
    return ("roman", ROMAN[s]) if s in ROMAN else None

def fy_of(end_year): return f"FY{end_year - 1}-{str(end_year)[2:]}"

def parse_num(s):
    s = s.strip().replace("\u2212", "-")
    if s in {"-", "–", "—"}: return 0.0
    neg = s.startswith("(") and s.endswith(")")
    try: v = float(s.strip("()").replace(",", ""))
    except ValueError: return None
    return -v if neg else v

def extract(doc, report, scope, stmt, pages, labels):
    end = int(report[2:6]) + 1
    lines = []
    for pg in pages:
        for t, v in page_lines(doc, pg):
            if lines and lines[-1][0] == pg:
                _, pt, pv = lines[-1]
                if not t.strip() and v and not pv:                 # values on their own line -> label above
                    lines[-1] = (pg, pt, v); continue
                if t[:1].islower() and (not pv or not v):         # wrapped label continuation
                    lines[-1] = (pg, pt + " " + t, pv or v); continue
            lines.append((pg, t, v))
    restated = "restated" in " ".join(t.lower() for _, t, _ in lines[:25])
    K = min(3, max((len(v) for _, _, v in lines), default=0))       # number of value columns (2, or 3 if restated)
    full = [v for _, _, v in lines if len(v) == K]
    if K < 2 or not full: return [], [], {"error": f"no {K}-value lines"}
    cx = [statistics.median(v[i][0] for v in full) for i in range(K)]
    order = [fy_of(end - i) for i in range(K)]                       # leftmost column = current year
    for _, t, _ in lines[:20]:
        ys = [int(y) for y in re.findall(r"20\d\d", t)]
        if len(ys) >= 2 and re.search(r"march|april", t, re.I):
            if ys[0] < ys[1]: order.reverse()
            break
    cur = fy_of(end)
    recs, checks, stack, sums, stopped, prev = [], [], [], {}, set(), ""
    kinds, last_letter = [], 0
    stats = {"columns": K, "restated": restated, "partial_rows": 0, "extra_values": 0, "unlabelled_subtotals": 0}
    for pg, t, vals in lines:
        if pg in stopped: continue
        if STOP.match(t): stopped.add(pg); continue
        toks = [w for w in t.split() if not MARKER.match(w)]
        while toks and REF.match(toks[-1]): toks.pop()
        label, synthetic = " ".join(toks).strip(" :"), False
        if not label:
            if not vals: continue
            label, synthetic = f"Unlabelled subtotal (after: {prev})", True
            stats["unlabelled_subtotals"] += 1
        if IGNORE.match(label): continue
        mk = marker_of(t, last_letter)
        if mk and mk[0] == "letter": last_letter = mk[1]
        while len(stack) > 1 and mk and kinds[-1] and kinds[-1][0] == mk[0] and mk[1] > kinds[-1][1]:
            stack.pop(); kinds.pop()                                   # next sibling closes the open sub-header
        if not vals:
            if TOP.match(label): stack, kinds, sums = [label], [None], {}
            else:
                if not mk and len(stack) > 1 and kinds[-1] is None: stack.pop(); kinds.pop()
                stack.append(label); kinds.append(mk)
            continue
        if len(vals) > K: stats["extra_values"] += 1; vals = vals[-K:]
        if len(vals) == K:
            assigned = {order[i]: vals[i][1] for i in range(K)}
        else:
            stats["partial_rows"] += 1
            assigned = {order[min(range(K), key=lambda k: abs(x - cx[k]))]: sv for x, sv in vals}
        parsed = {fy: parse_num(sv) for fy, sv in assigned.items()}
        for fy, v in parsed.items():
            if v is not None:
                recs.append(dict(report=report, fiscal_year=fy, scope=scope, statement=stmt, page=pg,
                                 page_label=labels.get(pg), path=" > ".join(stack), line_item=label, value=v,
                                 unit="INR crore", restated=restated and fy != cur, synthetic_label=synthetic,
                                 source="coordinate"))
        if synthetic: continue
        prev = label
        low, sec = label.lower(), (stack[0].lower() if stack else "")
        if low.startswith("total") and not low.startswith("total outstanding dues"):
            if sec in CHECK and low == f"total {sec}":
                for fy, v in parsed.items():
                    if v is not None:
                        sm = round(sums.get(fy, 0.0), 2)
                        checks.append((f"{report} | {scope:12} | {fy} | {label}", sm, v, abs(sm - v) < 0.02))
            stack, kinds = ([], []) if sec and sec in low else (stack[:1], kinds[:1])
            if not stack: sums = {}
        elif sec in CHECK:
            for fy, v in parsed.items():
                if v is not None: sums[fy] = sums.get(fy, 0.0) + v
    return recs, checks, stats

records, checks = [], []
print("EXTRACTION SUMMARY (records | one-value lines | >2-value lines):")
for path in sorted(Path("data/raw").glob("TataSteel_FY*.pdf")):
    report = path.stem.split("_")[1]
    pm = json.loads((INTERIM / f"page_map_{report}.json").read_text())
    labels = {p["page"]: p["label"] for p in pm}
    doc = pymupdf.open(path)
    for scope in ("standalone", "consolidated"):
        for stmt in PRIMARY:
            pages = [p["page"] for p in pm if p["scope"] == scope and p["statement"] == stmt]
            if not pages:
                print(f"  {report} {scope:12} {stmt:16} NO PAGES FOUND"); continue
            r, c, s = extract(doc, report, scope, stmt, pages, labels)
            records += r; checks += c
            print(f"  {report} {scope:12} {stmt:16} pages {pages[0]}-{pages[-1]}: {len(r):4} | {s}")

# Restatement handling: prefer the latest report containing each year (comparable basis),
# and flag any value that differs from the year's own original report.
latest, original = {}, {}
for r in records:
    k = (r["scope"], r["statement"], r["fiscal_year"])
    latest[k] = max(latest.get(k, ""), r["report"])
own = {r["fiscal_year"] for r in records if r["report"] == r["fiscal_year"]}
for r in records:
    ok_report = r["report"] == r["fiscal_year"] or (r["fiscal_year"] not in own and r["report"] == min(
        x["report"] for x in records if x["fiscal_year"] == r["fiscal_year"]))
    if ok_report:
        original[(r["scope"], r["statement"], r["fiscal_year"], r["path"], r["line_item"])] = r["value"]
n_diff = 0
for r in records:
    r["preferred"] = r["report"] == latest[(r["scope"], r["statement"], r["fiscal_year"])]
    o = original.get((r["scope"], r["statement"], r["fiscal_year"], r["path"], r["line_item"]))
    r["original_value"] = o
    r["differs_from_original"] = o is not None and abs(o - r["value"]) > 0.01
    n_diff += r["differs_from_original"]
print(f"Restatement pass: {sum(r['preferred'] for r in records)} preferred records, {n_diff} differ from original report")

with open(OUT / "line_items.jsonl", "w") as f:
    for r in records: f.write(json.dumps(r) + "\n")
print(f"\n{len(records)} records written to data/processed/line_items.jsonl")

print("\nBALANCE SHEET IDENTITY (Total assets vs Total equity and liabilities):")
for rep, sc, fy in sorted({(r["report"], r["scope"], r["fiscal_year"]) for r in records if r["statement"] == "balance_sheet"}):
    get = lambda name: next((r["value"] for r in records if (r["report"], r["scope"], r["fiscal_year"]) == (rep, sc, fy)
                             and r["statement"] == "balance_sheet" and r["line_item"].lower() == name), None)
    ta, tel = get("total assets"), get("total equity and liabilities")
    ok = "OK" if ta is not None and tel is not None and abs(ta - tel) < 0.02 else "MISMATCH"
    print(f"  {rep} report | {sc:12} | {fy}: {ta} vs {tel}  {ok}")

passed = sum(1 for c in checks if c[3])
print(f"\nSECTION SUBTOTAL CHECKS: {passed}/{len(checks)} passed")
for name, s, v, ok in checks:
    if not ok: print(f"  FAIL {name}: items sum {s} vs stated {v}")
```

---

## `src/ingest/page_map.py`

```python
"""Stage 1: classify every page of each annual report by section, scope and statement type.

Reads text by visual position (top and bottom strips of each page), because the PDF's
internal text order does not match the visual order in older reports.
Writes data/interim/page_map_<FY>.json and prints a summary per report.
"""
import json, re, glob
from pathlib import Path
import pymupdf

OUT = Path("data/interim"); OUT.mkdir(parents=True, exist_ok=True)

# Checked in order against the page's top strip only. Notes first, because a notes page
# can mention statement names; cash flow also matches its first line item, since some
# years place the title outside the top strip.
TITLES = [
    ("auditor_report", r"independent auditor.s report"),
    ("notes", r"notes forming part of the"),
    ("balance_sheet", r"balance sheet as at"),
    ("profit_and_loss", r"statement of profit and loss"),
    ("changes_in_equity", r"statement of changes in equity"),
    ("cash_flow", r"statement of cash flows|cash flows from operating activities"),
]
STATEMENTS = {"balance_sheet", "profit_and_loss", "changes_in_equity", "cash_flow", "notes"}
LABEL = re.compile(r"^(?:\d{1,3}\s+)?F(\d{1,3})\b")

def norm(s):
    return " ".join(s.split())

def zones(page):
    """Return (title text, footer text, full page text), read by visual position.

    Title: short blocks in the top 16% of the page (tall blocks are merged tables, ignored).
    Footer: blocks in the bottom 6%, where every year prints the running footer and F-label.
    """
    h = page.rect.height
    blocks = sorted(page.get_text("blocks"), key=lambda b: (b[1], b[0]))
    title = " ".join(norm(b[4]) for b in blocks if b[1] < h * 0.16 and (b[3] - b[1]) < 50)
    footer = " ".join(norm(b[4]) for b in blocks if b[1] > h * 0.94)
    full = norm(" ".join(b[4] for b in blocks))
    return title, footer, full

def classify(pdf_path):
    doc = pymupdf.open(pdf_path)
    pages, scope, current = [], None, None
    for i, page in enumerate(doc):
        title, footer, full = zones(page)
        head, low = title.lower(), full.lower()
        m = re.search(r"\bF(\d{1,3})\b", footer)
        label = f"F{m.group(1)}" if m else None
        if label:
            section = "financial_statements"
        elif "statutory reports" in (head + " " + footer.lower()):
            section = "statutory_reports"
        else:
            section = "integrated_report"
        statement, page_scope = None, None
        if section == "financial_statements":
            if "report on the audit of the consolidated financial statements" in low:
                scope = "consolidated"
            found = next((name for name, pat in TITLES if re.search(pat, head)), None)
            current = found or current or "fs_other"
            statement = current
            page_scope = scope or ("standalone" if statement in STATEMENTS or statement == "auditor_report" else None)
        pages.append(dict(page=i + 1, label=label, section=section, scope=page_scope, statement=statement))
    return pages

for path in sorted(glob.glob("data/raw/*.pdf")):
    fy = Path(path).stem.split("_")[-1]
    pages = classify(path)
    (OUT / f"page_map_{fy}.json").write_text(json.dumps(pages, indent=1))
    counts = {}
    for p in pages:
        counts[p["section"]] = counts.get(p["section"], 0) + 1
    print(f"\n{fy}: {len(pages)} pages | " + ", ".join(f"{k}={v}" for k, v in counts.items()))
    runs = []
    for p in pages:
        if p["section"] != "financial_statements":
            continue
        key = (p["scope"], p["statement"])
        if runs and runs[-1][0] == key:
            runs[-1][2], runs[-1][4] = p["page"], p["label"]
        else:
            runs.append([key, p["page"], p["page"], p["label"], p["label"]])
    for (scope, stmt), a, b, la, lb in runs:
        print(f"  {str(scope):13} {stmt:18} pages {a}-{b}  ({la}-{lb})")
```

---

## `src/ingest/retained_earnings.py`

```python
"""Extract the retained-earnings closing balance from the "Other equity" note of every report and scope.

For each report (FY2022-23..FY2025-26) and scope, finds the notes page(s) that contain the note "Other equity" with
the "A. Retained earnings" movement table, and parses that table only (up to "B. Items of other comprehensive income").
It keeps the "Balance at the end of the year" row for the report year and its comparative year.
Checks per column: opening balance + movements == closing balance (to 0.01 crore). Verification: the value, in Indian
format, must be present in the whitespace-normalised pymupdf text of its cited page; unverifiable values are left out.
Output: data/processed/retained_earnings.json
  {report: {scope: {fiscal_year: {value, pdf_page, page_label, method, verified_on_page}}}}
"""
import json, re
from pathlib import Path
import pymupdf

ROOT = Path(__file__).resolve().parents[2]
RAW, INTERIM, OUT = ROOT / "data/raw", ROOT / "data/interim", ROOT / "data/processed/retained_earnings.json"
REPORTS = ["FY2022-23", "FY2023-24", "FY2024-25", "FY2025-26"]
SCOPES = ["standalone", "consolidated"]
NUM = re.compile(r"^(\()?(\d{1,3}(?:,\d{2})*,?\d{0,3}\.\d{2})(\))?$|^-$")
YEAR_END = re.compile(r"March 31, (20\d\d)")
START = re.compile(r"movement in retained earnings", re.I)
END = re.compile(r"^B\.\s*$|^Items of other comprehensive income", re.I)
METHOD = ("Other equity note, A. Retained earnings movement table, 'Balance at the end of the year' row; "
          "column checked: opening + movements = closing")

def norm(s):
    return re.sub(r"\s+", " ", s).strip()

def inr(v):
    """Indian number format as printed in the reports: 1,00,920.21; negatives in brackets."""
    i, d = f"{abs(v):.2f}".split(".")
    if len(i) > 3:
        head, parts = i[:-3], []
        while len(head) > 2: parts.insert(0, head[-2:]); head = head[:-2]
        if head: parts.insert(0, head)
        i = ",".join(parts + [i[-3:]])
    s = i + "." + d
    return f"({s})" if v < 0 else s

def num(tok):
    m = NUM.match(tok)
    if not m: return None
    if tok == "-": return 0.0
    v = float(m.group(2).replace(",", ""))
    return -v if m.group(1) else v

def fy_of(year_end):
    y = int(year_end)
    return f"FY{y - 1}-{str(y)[2:]}"

def verified(doc, page, value):
    return inr(value) in norm(doc[page - 1].get_text())

def find_pages(doc, pmap, scope):
    """1-based notes pages of `scope` holding the Other equity note's retained-earnings movement table."""
    return [p["page"] for p in pmap if p["scope"] == scope and p["statement"] == "notes"
            and "Other equity" in (t := doc[p["page"] - 1].get_text()) and START.search(t)]

def parse(doc, page):
    """Parse the retained-earnings movement table starting on `page` (continuing onto the next page if needed).
    Returns ({fy: closing}, closing_page, problems)."""
    lines, owner = [], []
    for p in (page, page + 1):
        if p > len(doc): break
        for ln in doc[p - 1].get_text().splitlines():
            lines.append(ln.strip()); owner.append(p)
    i = next(k for k, ln in enumerate(lines) if START.search(ln))
    j = next((k for k in range(i + 1, len(lines)) if END.search(lines[k])), None)
    if j is None: return {}, None, ["end of the retained earnings table not found"]
    body, bowner = lines[i:j], owner[i:j]
    years = [fy_of(y) for y in YEAR_END.findall(" ".join(body[:12]))]
    if len(years) != 2: return {}, None, [f"expected 2 year columns, found {years}"]
    rows, label = [], []
    k = 0
    while k < len(body):
        a = num(body[k])
        if a is not None and k + 1 < len(body) and num(body[k + 1]) is not None:
            rows.append((" ".join(label), a, num(body[k + 1]), bowner[k])); label = []; k += 2
        else:
            if body[k] and not YEAR_END.search(body[k]): label.append(body[k])
            k += 1
    problems = []
    if not rows or not re.search(r"beginning of the year", rows[0][0], re.I):
        problems.append("first row is not the opening balance")
    closing = [r for r in rows if re.search(r"Balance at the end of the year", r[0], re.I)]
    if len(closing) != 1 or closing[0] is not rows[-1]:
        problems.append(f"expected one closing row at the end, found {len(closing)}")
    if problems: return {}, None, problems
    for c, fy in ((1, years[0]), (2, years[1])):
        total = sum(r[c] for r in rows[:-1])
        if abs(total - rows[-1][c]) > 0.011:
            problems.append(f"{fy}: opening + movements = {total:.2f} != closing {rows[-1][c]:.2f}")
    return {years[0]: rows[-1][1], years[1]: rows[-1][2]}, rows[-1][3], problems

def extract():
    out, table, unresolved = {}, [], []
    for rep in REPORTS:
        doc = pymupdf.open(RAW / f"TataSteel_{rep}.pdf")
        pmap = json.loads((INTERIM / f"page_map_{rep}.json").read_text())
        labels = {p["page"]: p["label"] for p in pmap}
        for scope in SCOPES:
            pages = find_pages(doc, pmap, scope)
            if len(pages) != 1:
                unresolved.append(f"{rep} {scope}: expected one retained-earnings page, found {pages}"); continue
            vals, cpage, problems = parse(doc, pages[0])
            if problems:
                unresolved.append(f"{rep} {scope}: " + "; ".join(problems)); continue
            for fy, v in vals.items():
                ok = verified(doc, cpage, v)
                table.append((rep, scope, fy, inr(v), labels.get(cpage), cpage, ok))
                if not ok:
                    unresolved.append(f"{rep} {scope} {fy}: {inr(v)} not found on page {cpage}"); continue
                out.setdefault(rep, {}).setdefault(scope, {})[fy] = {
                    "value": v, "pdf_page": cpage, "page_label": labels.get(cpage), "method": METHOD,
                    "verified_on_page": True}
    return out, table, unresolved

if __name__ == "__main__":
    out, table, unresolved = extract()
    OUT.write_text(json.dumps(out, indent=2) + "\n")
    print(f"{'report':<10} {'scope':<13} {'year':<10} {'value':>12}  {'page':<6} {'pdf_p':>5}  found")
    for rep, scope, fy, v, lab, p, ok in table:
        print(f"{rep:<10} {scope:<13} {fy:<10} {v:>12}  {lab or '-':<6} {p:>5}  {'✓' if ok else '✗'}")
    print(f"\n{sum(t[-1] for t in table)} of {len(table)} values verified; written to {OUT.relative_to(ROOT)}")
    print("unresolved:", "none" if not unresolved else "")
    for u in unresolved: print("  -", u)
```

---

## `src/ingest/run_docling.py`

```python
"""Stage 2: run Docling over every financial-statement page of each report (from the page map).

Saves the full Docling document per year to data/interim/docling_<FY>.json.
Skips years already done, so it is safe to re-run after an interruption.
"""
import json, sys, time
from pathlib import Path
from docling.datamodel.base_models import InputFormat
from docling.datamodel.pipeline_options import PdfPipelineOptions, TableFormerMode
from docling.document_converter import DocumentConverter, PdfFormatOption
try:
    from docling.datamodel.accelerator_options import AcceleratorOptions, AcceleratorDevice
except ImportError:
    from docling.datamodel.pipeline_options import AcceleratorOptions, AcceleratorDevice

INTERIM = Path("data/interim")
YEARS = sys.argv[1:] or ["FY2022-23", "FY2023-24", "FY2024-25", "FY2025-26"]

opts = PdfPipelineOptions(do_ocr=False, do_table_structure=True)
opts.table_structure_options.mode = TableFormerMode.ACCURATE
opts.table_structure_options.do_cell_matching = True
opts.accelerator_options = AcceleratorOptions(num_threads=24, device=AcceleratorDevice.CPU)
converter = DocumentConverter(format_options={InputFormat.PDF: PdfFormatOption(pipeline_options=opts)})
converter.initialize_pipeline(InputFormat.PDF)

for fy in YEARS:
    out = INTERIM / f"docling_{fy}.json"
    if out.exists():
        print(f"{fy}: already done, skipping", flush=True)
        continue
    page_map = json.loads((INTERIM / f"page_map_{fy}.json").read_text())
    fs_pages = [p["page"] for p in page_map if p["section"] == "financial_statements"]
    first, last = min(fs_pages), max(fs_pages)
    print(f"{fy}: starting pages {first}-{last} ({last - first + 1} pages)", flush=True)
    t = time.time()
    result = converter.convert(f"data/raw/TataSteel_{fy}.pdf", page_range=(first, last))
    result.document.save_as_json(out)
    print(f"{fy}: DONE - {len(result.document.tables)} tables in {(time.time() - t) / 60:.1f} min", flush=True)

print("ALL YEARS COMPLETE", flush=True)
```

---

## `src/ingest/segments.py`

```python
"""Extract segment revenue and segment results from the consolidated "Segment reporting" note of every report.

Layout (all four reports): segments are COLUMNS (last two: inter-segment eliminations, total); each item is two
stacked rows without year labels - first row = the report's year, second row = the prior year. Cells can be blank
(no token at all) or "-" (nil), so values are placed in columns by position, not by order: the words of the table
(pymupdf "words") are grouped into lines by y, numeric tokens into columns by their right edge (numbers are right-
aligned), and the header phrases above the table into the same columns by overlapping x-ranges.
Rows: the numeric lines between an item's label ("External revenue", "Inter(-)segment revenue", "Total Revenue",
"Segment results ...") and the next label; exactly two per item are required.

Checks, printed as a table (a value failing any check is left out and listed as unresolved, never guessed):
  (a) every value, in Indian format, is present in the whitespace-normalised pymupdf text of its cited page
      ("-" cells are present as a "-" token in that column; blank cells are omitted, not zero-filled)
  (b) sum of segments + eliminations == printed total, per item and year (to 0.01)
  (c) total external revenue == consolidated revenue_from_operations of that report and year in
      financials_by_report.json (to 0.01)
  (d) extra: external + inter-segment revenue == segment (total) revenue, per column and year (to 0.01)
Output: data/processed/segments.json
  {report: {fiscal_year: {"segments": {name: {"key", item: value}}, "totals": {item: value},
                          "eliminations": {item: value}, "pdf_page", "page_label", "unit", "eliminations_name",
                          "blank_cells": ["item / column" printed empty - omitted, not zero-filled]}}}
"""
import json, re
from pathlib import Path
import pymupdf

ROOT = Path(__file__).resolve().parents[2]
RAW, INTERIM, PROC = ROOT / "data/raw", ROOT / "data/interim", ROOT / "data/processed"
OUT = PROC / "segments.json"
REPORTS = ["FY2022-23", "FY2023-24", "FY2024-25", "FY2025-26"]
ITEMS = ["external_revenue", "inter_segment_revenue", "segment_revenue", "segment_results"]
LABELS = [("external_revenue", re.compile(r"^External revenue", re.I)),
          ("inter_segment_revenue", re.compile(r"^Inter[\s-]?segment revenue", re.I)),
          ("segment_revenue", re.compile(r"^Total Revenue", re.I)),
          ("segment_results", re.compile(r"^Segment results", re.I))]
END = re.compile(r"^Reconciliation", re.I)
NUM = re.compile(r"^(\()?(\d{1,3}(?:,\d{2})*,?\d{0,3}\.\d{2})(\))?$|^-$")
KEYS = [(r"^tata steel india", "tata_steel_india"), (r"^tata steel long products", "tata_steel_long_products"),
        (r"^neelachal ispat nigam", "neelachal_ispat_nigam"), (r"^other indian operations", "other_indian_operations"),
        (r"^tata steel europe", "tata_steel_europe"), (r"^tata steel netherlands", "tata_steel_netherlands"),
        (r"^tata steel uk", "tata_steel_uk"), (r"^other trade related", "other_trade_related_operations"),
        (r"^south-east asian", "south_east_asian_operations"), (r"^rest of the world", "rest_of_the_world"),
        (r"^inter-?\s?segment eliminations", "eliminations"), (r"^total$", "total")]
TOL = 0.011

def norm(s):
    return re.sub(r"\s+", " ", s).strip()

def inr(v):
    """Indian number format as printed in the reports: 1,00,920.21; negatives in brackets."""
    i, d = f"{abs(v):.2f}".split(".")
    if len(i) > 3:
        head, parts = i[:-3], []
        while len(head) > 2: parts.insert(0, head[-2:]); head = head[:-2]
        if head: parts.insert(0, head)
        i = ",".join(parts + [i[-3:]])
    s = i + "." + d
    return f"({s})" if v < 0 else s

def num(tok):
    m = NUM.match(tok)
    if not m: return None
    if tok == "-": return 0.0
    v = float(m.group(2).replace(",", ""))
    return -v if m.group(1) else v

def seg_key(name):
    n = name.lower()
    for pat, key in KEYS:
        if re.search(pat, n): return key
    return re.sub(r"[^a-z0-9]+", "_", n).strip("_")

def fy_prior(fy):
    a = int(fy[2:6]) - 1
    return f"FY{a}-{str(a + 1)[2:]}"

def find_page(doc, pmap):
    """1-based consolidated notes page holding the segment revenue/results table."""
    pages = [p["page"] for p in pmap if p["scope"] == "consolidated" and p["statement"] == "notes"
             and "Segment reporting" in (t := doc[p["page"] - 1].get_text()) and "Segment results" in t
             and "External revenue" in t]
    return pages

def lines_of(page):
    """Words grouped into lines (y within 2.5pt), each line sorted by x: [(y, [(x0, x1, text)])]."""
    words = sorted(page.get_text("words"), key=lambda w: (w[3], w[0]))
    lines = []
    for x0, y0, x1, y1, t, *_ in words:
        if lines and abs(lines[-1][0] - y1) <= 2.5: lines[-1][1].append((x0, x1, t))
        else: lines.append([y1, [(x0, x1, t)]])
    return [(y, sorted(ws)) for y, ws in lines]

def parse(page):
    """Returns ({item: [row_report_year, row_prior_year]} with rows as {column_name: value}, columns, problems)."""
    lines = lines_of(page)
    txt = [" ".join(w[2] for w in ws) for _, ws in lines]
    top = next(k for k, t in enumerate(txt) if "reportable segments" in t)
    unit = next(k for k in range(top, len(txt)) if re.search(r"crore\)", txt[k]))
    first = next(k for k in range(unit, len(txt)) if re.match(r"Segment revenue", txt[k]))
    end = next(k for k in range(first, len(txt)) if END.match(txt[k]))
    # numeric columns: cluster right edges of numeric tokens in the table body
    body = lines[first:end]
    label_right = min(w[0] for _, ws in body for w in ws if num(w[2]) is not None) - 5
    edges = sorted(w[1] for _, ws in body for w in ws if num(w[2]) is not None)
    cols = [[edges[0]]]
    for e in edges[1:]:
        (cols[-1].append(e) if e - cols[-1][-1] <= 12 else cols.append([e]))
    col_x = [max(c) for c in cols]
    # header phrases (words on a line with gaps < 5pt), merged into columns when their x-ranges overlap
    phrases = []
    for y, ws in lines[unit + 1:first]:
        for x0, x1, t in ws:
            if x0 < label_right: continue
            if phrases and phrases[-1][0] == y and x0 - phrases[-1][2] < 5:
                phrases[-1][2] = x1; phrases[-1][3].append(t)
            else: phrases.append([y, x0, x1, [t]])
    groups = []
    for ph in phrases:
        hit = [g for g in groups if ph[1] <= g["x1"] + 1 and ph[2] >= g["x0"] - 1]
        g = {"x0": ph[1], "x1": ph[2], "parts": [ph]}
        for h in hit:
            groups.remove(h); g["x0"] = min(g["x0"], h["x0"]); g["x1"] = max(g["x1"], h["x1"]); g["parts"] += h["parts"]
        groups.append(g)
    groups.sort(key=lambda g: g["x1"])
    problems = []
    if len(groups) != len(col_x):
        return {}, [], [f"{len(groups)} header columns but {len(col_x)} numeric columns"]
    names = []
    for g, cx in zip(groups, col_x):
        if not -6 <= cx - g["x1"] <= 10: problems.append(f"header '{g['parts']}' not aligned with numbers at x={cx:.0f}")
        words = [t for ph in sorted(g["parts"], key=lambda p: (p[0], p[1])) for t in ph[3]]
        names.append(re.sub(r"(\w)- (\w)", r"\1-\2", " ".join(words)))
    # rows: numeric lines between one item label and the next
    anchors = []
    for k in range(first, end):
        label = " ".join(w[2] for w in lines[k][1] if w[1] < label_right)
        for item, pat in LABELS:
            if pat.match(label): anchors.append((lines[k][0], item))
    if [a[1] for a in anchors] != ITEMS:
        return {}, names, problems + [f"item labels found {[a[1] for a in anchors]}"]
    out = {}
    for i, (ay, item) in enumerate(anchors):
        ny = anchors[i + 1][0] - 3 if i + 1 < len(anchors) else lines[end][0] - 3
        rows = []
        for y, ws in body:
            if not ay - 3 <= y < ny: continue
            nums = [w for w in ws if w[0] >= label_right]
            if not nums: continue
            row = {}
            for x0, x1, t in nums:
                v = num(t)
                c = min(range(len(col_x)), key=lambda j: abs(col_x[j] - x1))
                if v is None or abs(col_x[c] - x1) > 8 or names[c] in row:
                    problems.append(f"{item}: cannot place token '{t}' at x={x1:.0f}"); continue
                row[names[c]] = (v, t)
            rows.append(row)
        if len(rows) != 2: problems.append(f"{item}: expected 2 stacked rows, found {len(rows)}")
        out[item] = rows
    return out, names, problems

def extract():
    fin = json.loads((PROC / "financials_by_report.json").read_text())
    out, checks, unresolved = {}, [], []
    for rep in REPORTS:
        doc = pymupdf.open(RAW / f"TataSteel_{rep}.pdf")
        pmap = json.loads((INTERIM / f"page_map_{rep}.json").read_text())
        labels = {p["page"]: p["label"] for p in pmap}
        pages = find_page(doc, pmap)
        if len(pages) != 1:
            unresolved.append(f"{rep}: expected one segment table page, found {pages}"); continue
        pno = pages[0]
        text = norm(doc[pno - 1].get_text())
        rows, names, problems = parse(doc[pno - 1])
        if problems:
            unresolved += [f"{rep}: {p}" for p in problems]; continue
        seg_names = [n for n in names if seg_key(n) not in ("eliminations", "total")]
        elim = next(n for n in names if seg_key(n) == "eliminations")
        total = next(n for n in names if seg_key(n) == "total")
        for r, fy in enumerate((rep, fy_prior(rep))):
            vals = {item: {n: rows[item][r][n][0] for n in names if n in rows[item][r]} for item in ITEMS}
            bad = set()   # (item, column) left out
            # (a) present on page
            for item in ITEMS:
                for n, (v, tok) in rows[item][r].items():
                    ok = tok == "-" or inr(v) in text
                    checks.append((rep, fy, "a", f"{item} / {n}", tok, ok))
                    if not ok: bad.add((item, n)); unresolved.append(f"{rep} {fy} {item} {n}: {tok} not on page {pno}")
            # (b) segments + eliminations == total
            for item in ITEMS:
                if total not in vals[item]:
                    unresolved.append(f"{rep} {fy} {item}: total cell blank on page {labels.get(pno)} - no total to check")
                    continue
                s = sum(vals[item].get(n, 0.0) for n in seg_names + [elim])
                ok = abs(s - vals[item][total]) <= TOL
                checks.append((rep, fy, "b", f"{item}: sum {inr(s)} vs total", inr(vals[item][total]), ok))
                if not ok:
                    bad |= {(item, n) for n in names}
                    unresolved.append(f"{rep} {fy} {item}: segments + eliminations {inr(s)} != total {inr(vals[item][total])}")
            # (c) total external revenue == consolidated revenue from operations
            ref = fin[rep]["consolidated"].get("revenue_from_operations", {}).get("values", {}).get(fy, {}).get("value")
            ext = vals["external_revenue"].get(total)
            ok = ref is not None and ext is not None and abs(ref - ext) <= TOL
            checks.append((rep, fy, "c", f"external revenue total vs revenue_from_operations {inr(ref) if ref is not None else 'n/a'}",
                           inr(ext) if ext is not None else "n/a", ok))
            if not ok:
                bad |= {("external_revenue", n) for n in names}
                unresolved.append(f"{rep} {fy}: external revenue total != consolidated revenue from operations")
            # (d) external + inter-segment == segment revenue, per column
            for n in names:
                if n not in vals["segment_revenue"]: continue
                s = vals["external_revenue"].get(n, 0.0) + vals["inter_segment_revenue"].get(n, 0.0)
                ok = abs(s - vals["segment_revenue"][n]) <= TOL
                checks.append((rep, fy, "d", f"external + inter-segment = revenue / {n}", inr(vals["segment_revenue"][n]), ok))
                if not ok:
                    bad |= {(i, n) for i in ("external_revenue", "inter_segment_revenue", "segment_revenue")}
                    unresolved.append(f"{rep} {fy} {n}: external + inter-segment {inr(s)} != segment revenue")
            rec = {"segments": {}, "totals": {}, "eliminations": {}, "pdf_page": pno, "page_label": labels.get(pno),
                   "unit": "INR crore", "eliminations_name": elim,
                   "blank_cells": [f"{item} / {n}" for item in ITEMS for n in names if n not in vals[item]]}
            for n in names:
                d = {item: vals[item][n] for item in ITEMS if n in vals[item] and (item, n) not in bad}
                if n == total: rec["totals"] = d
                elif n == elim: rec["eliminations"] = d
                else: rec["segments"][n] = {"key": seg_key(n), **d}
            out.setdefault(rep, {})[fy] = rec
    return out, checks, unresolved

if __name__ == "__main__":
    out, checks, unresolved = extract()
    OUT.write_text(json.dumps(out, indent=2) + "\n")
    print("checks: (a) value on cited page  (b) segments + eliminations = total  "
          "(c) external revenue total = revenue from operations  (d) external + inter-segment = segment revenue\n")
    print(f"{'report':<10} {'year':<10} {'chk':<3} {'value':>13}  ok  what")
    for rep, fy, c, what, v, ok in checks:
        print(f"{rep:<10} {fy:<10} {c:<3} {v:>13}  {'✓' if ok else '✗'}   {what}")
    for c in "abcd":
        cs = [x for x in checks if x[2] == c]
        print(f"check ({c}): {sum(x[-1] for x in cs)} of {len(cs)} passed")
    print(f"\npages: " + "; ".join(f"{rep} p{v[rep]['pdf_page']} ({v[rep]['page_label']})" for rep, v in out.items()))
    print(f"written to {OUT.relative_to(ROOT)}")
    print("unresolved:", "none" if not unresolved else "")
    for u in unresolved: print("  -", u)
```

---

## `src/ingest/statement_lines.py`

```python
"""Coordinate-based line reader for primary financial statement pages.

Groups PyMuPDF words into visual lines by vertical position; money-formatted tokens in the
right part of the page are values, recorded with their right edge (numbers are right-aligned).
"""
import re, sys
import pymupdf

NUM = re.compile(r"^\(?-?[\d,]+\.\d{2}\)?$|^[-–—]$")

def page_lines(doc, page_no):
    """Return [(label_text, [(right_edge_x, value_text), ...]), ...] in top-to-bottom order."""
    page = doc[page_no - 1]
    W = page.rect.width
    words = sorted(page.get_text("words"), key=lambda w: ((w[1] + w[3]) / 2, w[0]))
    lines, cur, cy = [], [], None
    for w in words:
        yc = (w[1] + w[3]) / 2
        if cy is not None and abs(yc - cy) > 3:
            lines.append(cur); cur, cy = [], None
        cur.append(w)
        if cy is None: cy = yc
    if cur: lines.append(cur)
    out = []
    for ln in lines:
        ln.sort(key=lambda w: w[0])
        vals = [w for w in ln if w[0] > W * 0.55 and NUM.match(w[4])]
        out.append((" ".join(w[4] for w in ln if w not in vals), [(w[2], w[4]) for w in vals]))
    return out

if __name__ == "__main__":
    doc = pymupdf.open(sys.argv[1])
    for text, vals in page_lines(doc, int(sys.argv[2])):
        print(f"{text[:70]:70} | {[(round(x), v) for x, v in vals]}")
```

---

## `src/retrieval/search.py`

```python
"""Hybrid search over the Tata Steel index: dense (bge-base) + sparse (BM25), fused with RRF, with metadata filters."""
import os
from qdrant_client import QdrantClient, models
from fastembed import TextEmbedding, SparseTextEmbedding

COLL = "tata_steel"
CACHE = os.path.join(os.path.dirname(__file__), "..", "..", ".cache", "fastembed")
client = QdrantClient(url=os.getenv("QDRANT_URL", "http://localhost:6333"))
dense = TextEmbedding("BAAI/bge-base-en-v1.5", cache_dir=CACHE, threads=24)
sparse = SparseTextEmbedding("Qdrant/bm25", cache_dir=CACHE)

def build_filter(report=None, fiscal_year=None, scope=None, types=None, section=None, topic=None):
    must = []
    def add(key, val):
        if val: must.append(models.FieldCondition(key=key, match=models.MatchAny(any=val) if isinstance(val, list) else models.MatchValue(value=val)))
    add("report", report); add("fiscal_years", fiscal_year); add("scope", scope)
    add("type", types); add("section", section); add("topics", topic)
    return models.Filter(must=must) if must else None

def search(query, k=8, **filters):
    flt = build_filter(**filters)
    dq, sq = next(dense.query_embed(query)), next(sparse.query_embed(query))
    res = client.query_points(COLL, prefetch=[
        models.Prefetch(query=dq.tolist(), using="dense", limit=40, filter=flt),
        models.Prefetch(query=models.SparseVector(indices=sq.indices.tolist(), values=sq.values.tolist()), using="bm25", limit=40, filter=flt)],
        query=models.FusionQuery(fusion=models.Fusion.RRF), limit=k, with_payload=True)
    return res.points
```

---

## `frontend/Dockerfile`

```dockerfile
# Build the Vite app, then serve dist/ with nginx (which also proxies /api/ to the backend service).
FROM node:22-alpine AS build
WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci
COPY . .
RUN npm run build

FROM nginx:alpine
COPY nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=build /app/dist /usr/share/nginx/html
EXPOSE 80
```

---

## `frontend/index.html`

```html
<!doctype html>
<html lang="en">
  <head>
    <meta charset="UTF-8" />
    <link rel="icon" type="image/svg+xml" href="/favicon.svg" />
    <meta name="viewport" content="width=device-width, initial-scale=1.0" />
    <title>Edith · Tata Steel Financial Analysis</title>
  </head>
  <body>
    <div id="root"></div>
    <script type="module" src="/src/main.jsx"></script>
  </body>
</html>
```

---

## `frontend/nginx.conf`

```nginx
server {
    listen 80;
    server_name _;
    root /usr/share/nginx/html;
    index index.html;

    # FastAPI backend (docker-compose service "backend"); answers can take up to 300 s.
    location /api/ {
        proxy_pass http://backend:8000;
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_read_timeout 300s;
        proxy_send_timeout 300s;
    }

    # Hashed build assets can be cached for a long time.
    location /assets/ {
        expires 1y;
        add_header Cache-Control "public, immutable";
        try_files $uri =404;
    }

    # SPA fallback: every other path serves the app.
    location / {
        try_files $uri $uri/ /index.html;
    }
}
```

---

## `frontend/package.json`

```json
{
  "name": "tata-steel-assistant",
  "private": true,
  "version": "0.0.0",
  "type": "module",
  "scripts": {
    "dev": "vite",
    "build": "vite build",
    "lint": "oxlint",
    "preview": "vite preview"
  },
  "dependencies": {
    "react": "^19.2.8",
    "react-dom": "^19.2.8",
    "react-markdown": "^10.1.0",
    "remark-gfm": "^4.0.1"
  },
  "devDependencies": {
    "@types/react": "^19.2.18",
    "@types/react-dom": "^19.2.7",
    "@vitejs/plugin-react": "^6.1.1",
    "oxlint": "^1.81.0",
    "vite": "^8.3.0"
  }
}
```

---

## `frontend/src/App.css`

```css
:root {
  --ink: #102321;
  --ink-soft: #233b38;
  --muted: #627572;
  --muted-light: #8a9a96;
  --green: #087e68;
  --green-dark: #075747;
  --green-bright: #13b18d;
  --blue: #3978d7;
  --blue-bright: #6aa7ff;
  --paper: #ffffff;
  --mist: #f4f8f6;
  --line: #dfe8e4;
  --dark: #102421;
  --dark-soft: #1a3530;
  --shadow: 0 20px 55px rgba(14, 42, 36, 0.1);
}

* {
  box-sizing: border-box;
}

button {
  font: inherit;
}

button:focus-visible {
  outline: 3px solid rgba(72, 150, 237, 0.7);
  outline-offset: 3px;
}

.app-shell {
  min-height: 100vh;
  overflow: hidden;
  background: var(--paper);
  color: var(--ink);
}

.site-header {
  position: sticky;
  top: 0;
  z-index: 100;
  width: 100%;
  background: rgba(14, 34, 31, 0.97);
  color: #f7fbf9;
  border-bottom: 1px solid rgba(255, 255, 255, 0.1);
  backdrop-filter: blur(18px);
}

.header-inner {
  width: min(1440px, calc(100% - 64px));
  min-height: 78px;
  margin: 0 auto;
  display: grid;
  grid-template-columns: 1fr auto 1fr;
  align-items: center;
  gap: 28px;
}

.brand-button {
  justify-self: start;
  padding: 0;
  border: 0;
  color: inherit;
  background: transparent;
  text-align: left;
  cursor: pointer;
}

.brand {
  display: inline-flex;
  align-items: center;
  gap: 12px;
  min-width: 0;
}

.brand-mark {
  display: grid;
  place-items: center;
  width: 40px;
  height: 40px;
  flex: 0 0 40px;
  border: 1px solid rgba(218, 239, 231, 0.5);
  border-radius: 50%;
  color: #e7f5ee;
  font-family: Georgia, serif;
  font-size: 23px;
  font-style: italic;
  font-weight: 700;
  box-shadow: inset 0 0 0 4px rgba(255,255,255,.035);
}

.brand-copy {
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.brand-copy strong {
  font-size: 18px;
  line-height: 1.15;
  letter-spacing: -0.03em;
}

.brand-copy span {
  color: #aabbb6;
  font-size: 11px;
  letter-spacing: 0.01em;
}

.main-nav {
  display: flex;
  align-items: stretch;
  gap: 8px;
  height: 78px;
}

.nav-link {
  position: relative;
  padding: 0 15px;
  border: 0;
  color: #b9c7c2;
  background: transparent;
  font-size: 14px;
  font-weight: 600;
  cursor: pointer;
  transition: color .2s ease, background .2s ease;
}

.nav-link::after {
  position: absolute;
  right: 15px;
  bottom: 0;
  left: 15px;
  height: 3px;
  content: "";
  background: linear-gradient(90deg, var(--green-bright), var(--blue-bright));
  transform: scaleX(0);
  transform-origin: left;
  transition: transform .25s ease;
}

.nav-link:hover,
.nav-link.active {
  color: #fff;
}

.nav-link.active::after {
  transform: scaleX(1);
}

.header-cta {
  justify-self: end;
  display: inline-flex;
  align-items: center;
  gap: 9px;
  padding: 12px 17px;
  border: 1px solid rgba(223, 245, 235, .38);
  border-radius: 9px;
  color: #fff;
  background: rgba(255,255,255,.06);
  font-size: 13px;
  font-weight: 700;
  cursor: pointer;
  transition: background .2s ease, border-color .2s ease, transform .2s ease;
}

.header-cta:hover {
  background: rgba(20, 163, 128, .2);
  border-color: var(--green-bright);
  transform: translateY(-1px);
}

.mobile-menu-button {
  display: none;
  color: white;
  background: transparent;
  border: 0;
  cursor: pointer;
}

.page-transition {
  animation: pageEnter .45s cubic-bezier(.2,.75,.25,1) both;
}

@keyframes pageEnter {
  from { opacity: 0; transform: translateY(12px); }
  to { opacity: 1; transform: translateY(0); }
}

.page {
  width: 100%;
}

.home-page {
  background: #fff;
}

.hero-section {
  position: relative;
  display: grid;
  grid-template-columns: minmax(0, .92fr) minmax(460px, 1.08fr);
  align-items: center;
  gap: clamp(40px, 7vw, 110px);
  min-height: 640px;
  padding: 74px max(6.5vw, calc((100vw - 1440px) / 2)) 80px;
  isolation: isolate;
  background:
    radial-gradient(ellipse at 79% 42%, rgba(65, 148, 212, .11), transparent 34%),
    radial-gradient(ellipse at 63% 78%, rgba(18, 170, 132, .09), transparent 29%),
    linear-gradient(180deg, #f8fbfa 0%, #fff 88%);
}

.hero-grid-glow {
  position: absolute;
  z-index: -1;
  inset: 0;
  opacity: .38;
  background-image:
    linear-gradient(rgba(20, 90, 76, .055) 1px, transparent 1px),
    linear-gradient(90deg, rgba(20, 90, 76, .055) 1px, transparent 1px);
  background-size: 48px 48px;
  mask-image: linear-gradient(90deg, black, transparent 90%);
}

.hero-copy {
  position: relative;
  z-index: 2;
  max-width: 650px;
  animation: riseIn .7s .05s both;
}

@keyframes riseIn {
  from { opacity: 0; transform: translateY(18px); }
  to { opacity: 1; transform: translateY(0); }
}

.status-pill {
  display: inline-flex;
  align-items: center;
  gap: 7px;
  width: fit-content;
  padding: 7px 10px;
  border: 1px solid #e9d7a8;
  border-radius: 6px;
  color: #85601e;
  background: #fffaf0;
  font-size: 11px;
  font-weight: 650;
  line-height: 1.2;
  white-space: nowrap;
}

.status-pill::before {
  width: 6px;
  height: 6px;
  flex: 0 0 6px;
  border-radius: 50%;
  background: #d69a30;
  content: "";
}

.status-pill.pending {
  color: #8a6423;
  background: #fff9ed;
  border-color: #efdbb4;
}

.hero-kicker,
.page-overline,
.section-eyebrow {
  color: var(--green);
  font-size: 12px;
  font-weight: 800;
  letter-spacing: .12em;
  text-transform: uppercase;
}

.hero-kicker {
  margin-top: 27px;
}

.hero-copy h1 {
  margin: 17px 0 22px;
  color: #112522;
  font-size: clamp(48px, 5.3vw, 78px);
  font-weight: 800;
  letter-spacing: -.065em;
  line-height: .99;
}

.hero-copy h1 span {
  display: inline-block;
  padding: 5px 0 9px;
  color: transparent;
  background: linear-gradient(105deg, #087d68 8%, #139e86 45%, #397bd4 96%);
  -webkit-background-clip: text;
  background-clip: text;
}

.hero-description {
  max-width: 590px;
  margin: 0;
  color: #5a6d69;
  font-size: clamp(17px, 1.35vw, 20px);
  line-height: 1.75;
}

.hero-actions {
  display: flex;
  flex-wrap: wrap;
  gap: 13px;
  margin-top: 30px;
}

.button {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 10px;
  min-height: 45px;
  padding: 12px 18px;
  border: 1px solid transparent;
  border-radius: 8px;
  font-size: 14px;
  font-weight: 750;
  cursor: pointer;
  transition: transform .22s ease, box-shadow .22s ease, background .22s ease, border-color .22s ease;
}

.button:hover:not(:disabled) {
  transform: translateY(-2px);
}

.button:active:not(:disabled) {
  transform: translateY(0) scale(.99);
}

.button:disabled {
  cursor: not-allowed;
  opacity: .45;
}

.button-large {
  min-height: 53px;
  padding: 15px 22px;
  font-size: 15px;
}

.button-primary {
  color: #fff;
  background: linear-gradient(105deg, #087c68, #0e9277);
  box-shadow: 0 8px 18px rgba(8, 126, 104, .2);
}

.button-primary:hover:not(:disabled) {
  box-shadow: 0 12px 24px rgba(8, 126, 104, .28);
  background: linear-gradient(105deg, #066b5a, #087c68);
}

.button-secondary {
  color: #17312c;
  background: #fff;
  border-color: #cddbd6;
}

.button-secondary:hover {
  border-color: #7db8a9;
  box-shadow: 0 8px 20px rgba(12, 55, 44, .08);
}

.hero-note {
  display: flex;
  align-items: flex-start;
  gap: 9px;
  max-width: 520px;
  margin-top: 21px;
  color: #81908c;
  font-size: 11px;
  line-height: 1.6;
}

.note-dot,
.live-indicator,
.notice-dot,
.recent-dot {
  width: 7px;
  height: 7px;
  flex: 0 0 7px;
  margin-top: 4px;
  border-radius: 50%;
  background: #d69a30;
}

.hero-art {
  position: relative;
  min-height: 480px;
  display: grid;
  place-items: center;
  perspective: 1100px;
  animation: artEnter .85s .12s both;
}

@keyframes artEnter {
  from { opacity: 0; transform: translateX(22px) scale(.98); }
  to { opacity: 1; transform: translateX(0) scale(1); }
}

.art-orbit {
  position: absolute;
  width: 450px;
  height: 450px;
  border: 1px solid rgba(14, 134, 109, .14);
  border-radius: 50%;
  animation: orbitPulse 7s ease-in-out infinite;
}

.orbit-one { transform: rotate(-24deg) scaleY(.55); }
.orbit-two { width: 550px; height: 550px; border-color: rgba(66, 129, 218, .12); transform: rotate(25deg) scaleY(.54); animation-delay: -2s; }

@keyframes orbitPulse {
  0%, 100% { opacity: .55; transform: rotate(-24deg) scaleY(.55) scale(1); }
  50% { opacity: 1; transform: rotate(-24deg) scaleY(.55) scale(1.035); }
}

.report-sheet {
  position: relative;
  z-index: 1;
  width: min(440px, 78%);
  min-height: 440px;
  padding: 29px 32px 22px;
  border: 1px solid #dfe8e4;
  border-radius: 5px;
  background: linear-gradient(150deg, #fff 0%, #fcfefd 100%);
  box-shadow: 0 28px 60px rgba(23, 58, 50, .16);
  transform: rotate(-3.2deg);
  animation: paperFloat 6s ease-in-out infinite;
}

@keyframes paperFloat {
  0%, 100% { transform: translateY(0) rotate(-3.2deg); }
  50% { transform: translateY(-11px) rotate(-2.2deg); }
}

.report-topline,
.report-bottom {
  display: flex;
  align-items: center;
  justify-content: space-between;
  color: #83938e;
  font-family: "Courier New", monospace;
  font-size: 8px;
  letter-spacing: .07em;
}

.report-brand {
  color: #4b625b;
  font-weight: 800;
}

.report-heading {
  margin-top: 47px;
}

.report-heading small {
  color: #0d9278;
  font-family: "Courier New", monospace;
  font-size: 8px;
  letter-spacing: .14em;
}

.report-heading h3 {
  margin: 10px 0 8px;
  color: #1c3731;
  font-family: Georgia, serif;
  font-size: 27px;
  font-weight: 500;
  letter-spacing: -.03em;
}

.report-heading p {
  margin: 0;
  color: #81908b;
  font-size: 9px;
  line-height: 1.6;
}

.report-rule {
  height: 1px;
  margin: 18px 0;
  background: #dfe7e3;
}

.report-lines {
  display: flex;
  flex-direction: column;
  gap: 9px;
}

.line {
  display: block;
  height: 5px;
  border-radius: 4px;
  background: #e9efec;
}

.line-long { width: 100%; }
.line-mid { width: 85%; }
.line-short { width: 57%; }

.report-highlight {
  position: relative;
  display: flex;
  gap: 10px;
  margin: 20px -7px 18px;
  padding: 13px 12px;
  border-left: 3px solid #13a985;
  border-radius: 2px;
  background: linear-gradient(90deg, #e9f7d8, #f0fae7);
  animation: highlightReveal 1.1s .7s both;
}

@keyframes highlightReveal {
  from { opacity: .15; clip-path: inset(0 100% 0 0); }
  to { opacity: 1; clip-path: inset(0 0 0 0); }
}

.highlight-icon {
  color: #087c68;
}

.report-highlight b {
  color: #285448;
  font-size: 9px;
}

.report-highlight p {
  margin: 5px 0 0;
  color: #587066;
  font-family: Georgia, serif;
  font-size: 11px;
  line-height: 1.5;
}

.report-bottom {
  padding-top: 14px;
  border-top: 1px solid #e2e9e5;
  font-size: 7px;
  letter-spacing: .02em;
}

.reference-tag {
  padding: 4px 6px;
  border-radius: 3px;
  background: #f0f4f1;
}

.floating-evidence-card {
  position: absolute;
  z-index: 3;
  right: -2%;
  bottom: 34px;
  width: 215px;
  padding: 17px;
  border: 1px solid rgba(255,255,255,.13);
  border-radius: 9px;
  color: #f2faf6;
  background: #183b33;
  box-shadow: 0 18px 35px rgba(13, 48, 40, .25);
  animation: cardFloat 5s 1s ease-in-out infinite;
}

@keyframes cardFloat {
  0%, 100% { transform: translateY(0); }
  50% { transform: translateY(-8px); }
}

.floating-card-top {
  display: flex;
  align-items: center;
  gap: 7px;
  color: #b6cbc2;
  font-size: 9px;
}

.mini-check {
  display: grid;
  place-items: center;
  width: 20px;
  height: 20px;
  border-radius: 50%;
  color: #0c3b30;
  background: #a7e4c3;
}

.floating-evidence-card strong {
  display: block;
  margin: 13px 0 6px;
  font-family: Georgia, serif;
  font-size: 17px;
  font-weight: 500;
}

.floating-evidence-card p {
  margin: 0;
  color: #b9ccc4;
  font-size: 10px;
  line-height: 1.55;
}

.evidence-progress {
  height: 3px;
  margin: 14px 0 8px;
  overflow: hidden;
  border-radius: 10px;
  background: rgba(255,255,255,.12);
}

.evidence-progress span {
  display: block;
  width: 65%;
  height: 100%;
  border-radius: inherit;
  background: linear-gradient(90deg, #24c99d, #79b7ff);
  animation: progressSweep 2.4s ease-in-out infinite alternate;
}

@keyframes progressSweep {
  from { width: 28%; }
  to { width: 78%; }
}

.floating-evidence-card small {
  color: #91aaa0;
  font-size: 8px;
}

.floating-data-chip {
  position: absolute;
  z-index: 4;
  display: flex;
  align-items: center;
  gap: 9px;
  padding: 10px 13px;
  border: 1px solid #e2ebe7;
  border-radius: 9px;
  background: rgba(255,255,255,.94);
  box-shadow: 0 12px 25px rgba(19, 54, 45, .1);
  animation: chipFloat 5s ease-in-out infinite;
}

.chip-top { top: 45px; left: 0; }
.chip-bottom { right: 6%; bottom: 5px; animation-delay: -2.3s; }

@keyframes chipFloat {
  0%, 100% { transform: translateY(0); }
  50% { transform: translateY(-6px); }
}

.chip-icon {
  display: grid;
  place-items: center;
  width: 30px;
  height: 30px;
  border-radius: 8px;
  color: #087c68;
  background: #e4f6ee;
}

.chip-icon.blue {
  color: #3c7ed7;
  background: #eaf2ff;
}

.floating-data-chip span:last-child {
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.floating-data-chip b {
  font-size: 10px;
}

.floating-data-chip small {
  color: #81918d;
  font-size: 8px;
}

.trust-strip {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 25px;
  padding: 22px max(6.5vw, calc((100vw - 1440px) / 2));
  border-top: 1px solid #eaf0ed;
  border-bottom: 1px solid #eaf0ed;
  background: #fff;
}

.trust-intro {
  display: flex;
  align-items: center;
  gap: 12px;
}

.trust-icon {
  display: grid;
  place-items: center;
  width: 40px;
  height: 40px;
  border-radius: 11px;
  color: #087e68;
  background: #e8f7f0;
}

.trust-intro div {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.trust-intro strong {
  font-size: 13px;
}

.trust-intro span:not(.trust-icon) {
  color: #82908c;
  font-size: 11px;
}

.trust-item {
  display: flex;
  align-items: center;
  gap: 8px;
  color: #536762;
  font-size: 12px;
  font-weight: 600;
}

.trust-item svg {
  color: #168e77;
}

.content-section {
  width: min(1440px, calc(100% - 64px));
  margin: 0 auto;
  padding: 88px 0;
}

.section-heading {
  display: flex;
  align-items: flex-end;
  justify-content: space-between;
  gap: 28px;
  margin-bottom: 30px;
}

.section-heading h2,
.roadmap-heading h2,
.tata-feature h2 {
  max-width: 780px;
  margin: 10px 0 8px;
  color: #142a26;
  font-size: clamp(31px, 3.5vw, 48px);
  font-weight: 750;
  letter-spacing: -.055em;
  line-height: 1.1;
}

.section-heading p,
.roadmap-heading p {
  max-width: 700px;
  margin: 0;
  color: #73827e;
  font-size: 15px;
  line-height: 1.65;
}

.feature-grid {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 20px;
}

.feature-card {
  position: relative;
  min-height: 285px;
  padding: 26px;
  overflow: hidden;
  border: 1px solid #e3ebe7;
  border-radius: 14px;
  background: #fff;
  transition: transform .28s ease, box-shadow .28s ease, border-color .28s ease;
}

.feature-card::after {
  position: absolute;
  right: -44px;
  bottom: -74px;
  width: 170px;
  height: 170px;
  border-radius: 50%;
  background: radial-gradient(circle, rgba(25, 172, 135, .1), transparent 68%);
  content: "";
  transition: transform .4s ease;
}

.feature-card:hover {
  transform: translateY(-7px);
  border-color: #c8ded5;
  box-shadow: 0 20px 38px rgba(17, 57, 47, .1);
}

.feature-card:hover::after {
  transform: scale(1.3);
}

.feature-green { background: linear-gradient(145deg, #f2fbf6, #fff 68%); }
.feature-blue { background: linear-gradient(145deg, #f0f6ff, #fff 68%); }
.feature-dark { color: #f5faf8; background: linear-gradient(145deg, #163b34, #102923); border-color: #234b42; }
.feature-dark h3 { color: #fff; }
.feature-dark p { color: #bfd0ca; }
.feature-dark .feature-number { color: #85d9bc; }
.feature-dark .feature-icon { color: #c0f1dd; background: rgba(255,255,255,.1); }
.feature-dark .text-link { color: #a8e7d0; }

.feature-icon {
  display: grid;
  place-items: center;
  width: 50px;
  height: 50px;
  margin-bottom: 23px;
  border-radius: 13px;
  color: #087c68;
  background: #dff4e9;
}

.feature-blue .feature-icon {
  color: #3978d7;
  background: #e1edff;
}

.feature-number {
  display: block;
  color: #168c72;
  font-size: 10px;
  font-weight: 800;
  letter-spacing: .1em;
}

.feature-card h3 {
  position: relative;
  z-index: 1;
  margin: 9px 0 8px;
  color: #172c28;
  font-size: 21px;
  letter-spacing: -.035em;
}

.feature-card p {
  position: relative;
  z-index: 1;
  max-width: 350px;
  margin: 0;
  color: #6e7e79;
  font-size: 14px;
  line-height: 1.65;
}

.text-link {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  padding: 0;
  border: 0;
  color: #087e68;
  background: transparent;
  font-size: 13px;
  font-weight: 750;
  cursor: pointer;
}

.feature-card .text-link {
  position: relative;
  z-index: 2;
  margin-top: 22px;
}

.text-link svg {
  transition: transform .2s ease;
}

.text-link:hover svg {
  transform: translateX(4px);
}

.roadmap-section {
  padding-top: 20px;
}

.roadmap-heading {
  display: flex;
  align-items: flex-end;
  justify-content: space-between;
  gap: 30px;
  margin-bottom: 28px;
}

.roadmap-stamp {
  display: flex;
  align-items: center;
  gap: 9px;
  padding: 12px 15px;
  border: 1px solid #dce9e3;
  border-radius: 9px;
  color: #43746a;
  background: #f5faf7;
  font-size: 12px;
  font-weight: 700;
  white-space: nowrap;
}

.roadmap {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 0;
  border: 1px solid #dce8e3;
  border-radius: 14px;
  background: #fff;
  overflow: hidden;
}

.roadmap-step {
  position: relative;
  min-height: 230px;
  padding: 25px 28px 22px;
  border: 0;
  border-right: 1px solid #e0eae5;
  background: #fff;
  text-align: left;
  cursor: pointer;
  transition: background .25s ease;
}

.roadmap-step:last-child { border-right: 0; }
.roadmap-step:hover,
.roadmap-step.expanded { background: #f6fbf8; }

.roadmap-step::before {
  position: absolute;
  top: 0;
  right: 100%;
  left: 0;
  height: 3px;
  content: "";
  background: linear-gradient(90deg, #0d9879, #4c8ce8);
  transition: right .25s ease;
}

.roadmap-step.expanded::before { right: 0; }

.roadmap-step-top {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 20px;
}

.roadmap-number {
  color: #168c72;
  font-family: "Courier New", monospace;
  font-size: 13px;
  font-weight: 800;
}

.roadmap-step-icon {
  display: grid;
  place-items: center;
  width: 39px;
  height: 39px;
  border-radius: 11px;
  color: #117e69;
  background: #e5f6ed;
}

.roadmap-step:nth-child(2) .roadmap-step-icon {
  color: #3978d7;
  background: #eaf2ff;
}

.roadmap-step h3 {
  margin: 0 0 7px;
  font-size: 20px;
  letter-spacing: -.03em;
}

.roadmap-step p {
  margin: 0;
  color: #75837f;
  font-size: 13px;
  line-height: 1.6;
}

.roadmap-detail {
  margin-top: 12px;
  padding-top: 11px;
  border-top: 1px solid #dce8e3;
  color: #526760;
  font-size: 12px;
  line-height: 1.55;
  animation: detailDrop .25s ease both;
}

@keyframes detailDrop {
  from { opacity: 0; transform: translateY(-5px); }
  to { opacity: 1; transform: translateY(0); }
}

.roadmap-more {
  display: inline-block;
  margin-top: 15px;
  color: #0c8b71;
  font-size: 10px;
  font-weight: 800;
  letter-spacing: .03em;
}

.tata-feature {
  display: grid;
  grid-template-columns: minmax(300px, .92fr) 1.08fr;
  align-items: center;
  gap: clamp(45px, 8vw, 115px);
  padding: 76px max(6.5vw, calc((100vw - 1440px) / 2));
  background: #f3f8f6;
}

.tata-feature-art {
  position: relative;
  min-height: 320px;
  display: grid;
  place-items: center;
  overflow: hidden;
  border-radius: 18px;
  background: linear-gradient(140deg, #d9f1e7, #e2effb 70%, #f8fcfa);
}

.tata-glow {
  position: absolute;
  width: 300px;
  height: 300px;
  border-radius: 50%;
  background: rgba(53, 154, 124, .15);
  filter: blur(30px);
  animation: glowPulse 5s ease-in-out infinite;
}

@keyframes glowPulse {
  0%, 100% { transform: scale(.85); opacity: .6; }
  50% { transform: scale(1.12); opacity: 1; }
}

.steel-visual {
  position: relative;
  width: 85%;
  height: 230px;
  overflow: hidden;
  border-bottom: 2px solid rgba(14, 72, 61, .28);
}

.steel-sun {
  position: absolute;
  top: 20px;
  right: 23%;
  width: 78px;
  height: 78px;
  border-radius: 50%;
  background: linear-gradient(140deg, #f8fff8, #a9d9c6);
  box-shadow: 0 0 40px rgba(255,255,255,.85);
}

.steel-ground {
  position: absolute;
  right: -20px;
  bottom: -38px;
  left: -20px;
  height: 85px;
  border-radius: 50% 50% 0 0;
  background: linear-gradient(180deg, #8bb7a7, #477f70);
}

.steel-plant {
  position: absolute;
  z-index: 1;
  bottom: 35px;
  display: flex;
  align-items: flex-end;
  gap: 6px;
}

.plant-one { left: 13%; }
.plant-two { right: 10%; }

.steel-plant i {
  display: block;
  width: 31px;
  height: 105px;
  border: 2px solid #456d64;
  border-bottom: 0;
  background: linear-gradient(90deg, #91b9a9, #d1e6dc);
  box-shadow: inset 0 8px 0 rgba(255,255,255,.25);
}

.steel-plant i:nth-child(2) { height: 145px; width: 39px; }
.steel-plant i:nth-child(3) { height: 122px; }
.steel-plant i:nth-child(4) { height: 80px; width: 24px; }

.plant-two i { height: 95px; width: 26px; }
.plant-two i:nth-child(2) { height: 125px; }
.plant-two i:nth-child(3) { height: 72px; }

.tata-feature-copy h2 {
  max-width: 640px;
  margin-bottom: 17px;
}

.tata-feature-copy > p {
  max-width: 600px;
  color: #667873;
  font-size: 16px;
  line-height: 1.75;
}

.tata-feature-points {
  display: grid;
  gap: 11px;
  margin: 22px 0 25px;
}

.tata-feature-points span {
  display: flex;
  align-items: center;
  gap: 9px;
  color: #344f48;
  font-size: 13px;
  font-weight: 650;
}

.tata-feature-points svg { color: #0d9b79; }

.bottom-cta {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 25px;
  padding: 35px max(6.5vw, calc((100vw - 1440px) / 2));
  color: #f5faf8;
  background: linear-gradient(105deg, #12352e, #183d37 55%, #1c3444);
}

.bottom-cta-copy {
  display: flex;
  align-items: center;
  gap: 17px;
}

.cta-orb {
  display: grid;
  place-items: center;
  width: 47px;
  height: 47px;
  flex: 0 0 47px;
  border: 1px solid rgba(255,255,255,.25);
  border-radius: 14px;
  color: #a9e9d1;
  background: rgba(255,255,255,.08);
}

.bottom-cta h2 {
  margin: 0 0 5px;
  font-family: Georgia, serif;
  font-size: 27px;
  font-weight: 500;
  letter-spacing: -.03em;
}

.bottom-cta p {
  margin: 0;
  color: #bfd0ca;
  font-size: 13px;
}

.button-light {
  color: #12332d;
  background: #f4fbf7;
  white-space: nowrap;
}

.button-light:hover {
  background: #dff7eb;
  box-shadow: 0 8px 22px rgba(0,0,0,.13);
}

/* Inner pages */
.inner-page {
  width: min(1440px, calc(100% - 64px));
  margin: 0 auto;
  padding: 50px 0 76px;
}

.page-title-row {
  display: flex;
  align-items: flex-end;
  justify-content: space-between;
  gap: 25px;
  padding-bottom: 25px;
  border-bottom: 1px solid #dfe8e4;
}

.page-overline {
  margin-bottom: 8px;
  font-size: 10px;
}

.page-title-row h1 {
  margin: 0 0 7px;
  color: #142a26;
  font-size: clamp(38px, 4vw, 54px);
  font-weight: 800;
  letter-spacing: -.06em;
  line-height: 1.08;
}

.page-title-row p {
  margin: 0;
  color: #6e7e79;
  font-size: 15px;
  line-height: 1.6;
}

/* Ask Edith */
.ask-layout {
  display: grid;
  grid-template-columns: 290px minmax(0, 1fr);
  gap: 22px;
  margin-top: 24px;
}

.ask-sidebar {
  align-self: start;
  padding: 22px;
  border: 1px solid #23483f;
  border-radius: 13px;
  color: #f1f8f4;
  background: linear-gradient(160deg, #183b34, #102722);
  box-shadow: 0 14px 30px rgba(17, 53, 44, .12);
}

.sidebar-heading {
  display: flex;
  align-items: center;
  gap: 11px;
  padding-bottom: 18px;
  border-bottom: 1px solid rgba(255,255,255,.12);
}

.sidebar-heading-icon {
  display: grid;
  place-items: center;
  width: 39px;
  height: 39px;
  border-radius: 11px;
  color: #b5f0d9;
  background: rgba(255,255,255,.09);
}

.sidebar-heading h2 {
  margin: 0 0 3px;
  font-size: 16px;
}

.sidebar-heading p {
  margin: 0;
  color: #a6bdb4;
  font-size: 11px;
}

.suggestion-list {
  display: grid;
  margin-top: 7px;
}

.suggestion-item {
  position: relative;
  display: flex;
  flex-direction: column;
  gap: 6px;
  padding: 15px 24px 15px 0;
  border: 0;
  border-bottom: 1px solid rgba(255,255,255,.12);
  color: #f3faf6;
  background: transparent;
  text-align: left;
  cursor: pointer;
  transition: padding .2s ease, color .2s ease;
}

.suggestion-item:hover {
  padding-left: 5px;
  color: #a7ebd0;
}

.suggestion-item > span {
  color: #8bd8bb;
  font-size: 10px;
  font-weight: 800;
  letter-spacing: .07em;
  text-transform: uppercase;
}

.suggestion-item strong {
  font-size: 12px;
  font-weight: 550;
  line-height: 1.5;
}

.suggestion-item svg {
  position: absolute;
  top: 50%;
  right: 0;
  color: #8cb6a7;
  transform: translateY(-50%);
  transition: transform .2s ease;
}

.suggestion-item:hover svg { transform: translate(3px, -50%); }

.sidebar-info {
  margin-top: 21px;
  padding: 15px 14px 9px;
  border: 1px solid rgba(255,255,255,.12);
  border-radius: 9px;
  background: rgba(255,255,255,.045);
}

.sidebar-info-title {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 10px;
  color: #dceee5;
  font-size: 12px;
  font-weight: 750;
}

.sidebar-info-title svg { color: #90d8bc; }

.sidebar-info-row {
  display: flex;
  justify-content: space-between;
  gap: 12px;
  padding: 8px 0;
  border-top: 1px solid rgba(255,255,255,.09);
  font-size: 10px;
}

.sidebar-info-row span { color: #9eb3aa; }
.sidebar-info-row b { color: #e7f2ed; font-weight: 600; text-align: right; }

.sidebar-recent {
  display: flex;
  gap: 10px;
  margin-top: 18px;
  padding-top: 15px;
  border-top: 1px solid rgba(255,255,255,.12);
}

.recent-dot { margin-top: 5px; background: #78d5ae; }

.sidebar-recent div {
  display: flex;
  flex-direction: column;
  gap: 4px;
  min-width: 0;
}

.sidebar-recent b { font-size: 11px; }
.sidebar-recent small {
  display: -webkit-box;
  overflow: hidden;
  color: #a7bdb4;
  font-size: 10px;
  line-height: 1.5;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
}

.chat-panel {
  display: flex;
  flex-direction: column;
  min-height: 670px;
  overflow: hidden;
  border: 1px solid #dfe8e4;
  border-radius: 13px;
  background: #fff;
  box-shadow: 0 15px 40px rgba(18, 52, 44, .06);
}

.chat-panel-header {
  display: flex;
  align-items: center;
  gap: 11px;
  padding: 16px 21px;
  border-bottom: 1px solid #e7eeeb;
  background: linear-gradient(90deg, #fbfdfc, #f6faf8);
}

.chat-avatar,
.assistant-message-avatar {
  display: grid;
  place-items: center;
  width: 37px;
  height: 37px;
  flex: 0 0 37px;
  border-radius: 12px;
  color: white;
  background: linear-gradient(145deg, #0a7a66, #1d4940);
  font-family: Georgia, serif;
  font-size: 21px;
  font-style: italic;
  font-weight: 700;
}

.chat-panel-header > div:nth-child(2) {
  display: flex;
  flex-direction: column;
  gap: 3px;
}

.chat-panel-header strong { font-size: 13px; }
.chat-panel-header span { color: #84938f; font-size: 10px; }

.new-chat {
  display: inline-flex;
  align-items: center;
  gap: 7px;
  margin-left: auto;
  padding: 8px 10px;
  border: 1px solid #dce7e2;
  border-radius: 7px;
  color: #5d706a;
  background: #fff;
  font-size: 10px;
  font-weight: 650;
  cursor: pointer;
  transition: background .2s ease;
}

.new-chat:hover { background: #eff8f3; }

.chat-content {
  flex: 1;
  min-height: 420px;
  padding: 34px clamp(22px, 4vw, 52px);
  background:
    radial-gradient(ellipse at 88% 8%, rgba(61, 142, 214, .045), transparent 35%),
    #fff;
}

.welcome-message {
  display: flex;
  gap: 15px;
  max-width: 740px;
  animation: riseIn .4s both;
}

.welcome-icon {
  display: grid;
  place-items: center;
  width: 45px;
  height: 45px;
  flex: 0 0 45px;
  border-radius: 14px;
  color: #087c68;
  background: #e4f6ed;
}

.welcome-message h2 {
  margin: 1px 0 10px;
  font-family: Georgia, serif;
  font-size: 26px;
  font-weight: 500;
  letter-spacing: -.03em;
}

.welcome-message p {
  max-width: 680px;
  margin: 0;
  color: #657873;
  font-size: 14px;
  line-height: 1.75;
}

.welcome-callout {
  display: flex;
  align-items: flex-start;
  gap: 9px;
  max-width: 620px;
  margin-top: 24px;
  padding: 13px 15px;
  border: 1px solid #e4eaf0;
  border-radius: 8px;
  color: #647773;
  background: #f6f9fb;
  font-size: 11px;
  line-height: 1.6;
}

.welcome-callout svg {
  flex: 0 0 auto;
  color: #4381c9;
}

.chat-composer {
  margin: 0 20px 20px;
  padding: 12px 14px 10px;
  border: 1px solid transparent;
  border-radius: 12px;
  background:
    linear-gradient(#fff, #fff) padding-box,
    linear-gradient(110deg, #0c9d79, #4588e6, #0c9d79) border-box;
  box-shadow: 0 9px 24px rgba(22, 78, 62, .08);
  transition: box-shadow .25s ease;
}

.chat-composer:focus-within {
  box-shadow: 0 0 0 4px rgba(34, 152, 126, .09), 0 12px 28px rgba(22, 78, 62, .1);
}

.chat-composer textarea {
  display: block;
  width: 100%;
  min-height: 66px;
  padding: 7px 4px;
  resize: vertical;
  border: 0;
  outline: 0;
  color: #1b302b;
  background: transparent;
  font-size: 14px;
  line-height: 1.6;
}

.chat-composer textarea::placeholder { color: #9aa9a4; }

.composer-bottom {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 15px;
  padding-top: 9px;
  border-top: 1px solid #edf1ef;
}

.composer-bottom > span {
  display: flex;
  align-items: center;
  gap: 5px;
  color: #8c9a95;
  font-size: 10px;
}

.composer-lock { display: inline-flex; color: #7f9a91; }

.conversation {
  display: grid;
  gap: 25px;
  animation: riseIn .35s both;
}

.user-message {
  justify-self: end;
  max-width: 75%;
  padding: 13px 17px;
  border: 1px solid #d9e8e1;
  border-radius: 12px 12px 3px 12px;
  background: #eef8f2;
}

.user-message span,
.assistant-message-body > span {
  display: block;
  margin-bottom: 5px;
  color: #0c8a70;
  font-size: 10px;
  font-weight: 800;
}

.user-message p {
  margin: 0;
  color: #28423a;
  font-size: 13px;
  line-height: 1.55;
}

.assistant-message {
  display: flex;
  align-items: flex-start;
  gap: 12px;
  max-width: 760px;
}

.assistant-message-avatar {
  width: 32px;
  height: 32px;
  flex-basis: 32px;
  border-radius: 10px;
  font-size: 18px;
}

.assistant-message-body { flex: 1; min-width: 0; }
.assistant-message-body > span { color: #7b8a85; }

.assistant-message-body h3 {
  margin: 6px 0 8px;
  font-size: 18px;
  letter-spacing: -.03em;
}

.assistant-message-body > p {
  margin: 0;
  color: #687a74;
  font-size: 13px;
  line-height: 1.7;
}

.evidence-placeholder {
  margin-top: 19px;
  padding: 15px;
  border: 1px solid #dce9e3;
  border-left: 3px solid #0b9979;
  border-radius: 7px;
  background: #f8fbf9;
}

.evidence-placeholder-top {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 15px;
  margin-bottom: 14px;
}

.evidence-placeholder-top > span {
  display: inline-flex;
  align-items: center;
  gap: 7px;
  color: #304c43;
  font-size: 11px;
  font-weight: 750;
}

.evidence-placeholder .status-pill { font-size: 9px; }
.evidence-skeleton {
  width: 68%;
  height: 8px;
  margin: 8px 0;
  border-radius: 5px;
  background: #e7eeea;
  animation: skeletonPulse 1.5s ease-in-out infinite;
}
.evidence-skeleton.wide { width: 94%; }

@keyframes skeletonPulse {
  0%, 100% { opacity: .55; }
  50% { opacity: 1; }
}

.evidence-placeholder small {
  display: block;
  margin-top: 13px;
  color: #82918b;
  font-size: 10px;
  line-height: 1.5;
}

.ask-page-links {
  display: flex;
  flex-wrap: wrap;
  gap: 24px;
  margin-top: 22px;
}

/* Dashboard */
.dashboard-page {
  padding-bottom: 80px;
}

.dashboard-controls {
  display: flex;
  align-items: flex-end;
  gap: 20px;
  margin: 22px 0 17px;
  padding: 14px 17px;
  border: 1px solid #dce8e3;
  border-radius: 10px;
  background: linear-gradient(100deg, #f5faf7, #f5f8fc);
}

.control-group {
  display: flex;
  flex-direction: column;
  gap: 7px;
}

.control-group label {
  color: #7b8c86;
  font-size: 10px;
  font-weight: 800;
  letter-spacing: .03em;
}

.segmented-control {
  display: flex;
  gap: 3px;
  padding: 3px;
  border: 1px solid #dce7e1;
  border-radius: 7px;
  background: #e9efeb;
}

.segmented-control button,
.category-filter button {
  padding: 8px 11px;
  border: 0;
  border-radius: 5px;
  color: #687b74;
  background: transparent;
  font-size: 11px;
  font-weight: 650;
  cursor: pointer;
  transition: color .2s ease, background .2s ease, box-shadow .2s ease;
}

.segmented-control button.selected,
.category-filter button.selected {
  color: white;
  background: #087b67;
  box-shadow: 0 2px 5px rgba(5, 88, 71, .16);
}

.control-note {
  display: flex;
  align-items: center;
  gap: 7px;
  margin-left: auto;
  padding-bottom: 8px;
  color: #7b8b86;
  font-size: 10px;
}

.live-indicator {
  width: 6px;
  height: 6px;
  margin: 0;
  background: #d5a044;
}

.metric-grid {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 14px;
  margin-bottom: 15px;
}

.metric-card {
  min-width: 0;
  padding: 17px;
  border: 1px solid #e0e8e4;
  border-radius: 10px;
  background: #fff;
  text-align: left;
  cursor: pointer;
  transition: transform .22s ease, box-shadow .22s ease, border-color .22s ease;
}

.metric-card:hover {
  transform: translateY(-3px);
  border-color: #9bcbb9;
  box-shadow: 0 10px 24px rgba(18, 62, 50, .08);
}

.metric-active {
  border-color: #6ab59c;
  box-shadow: inset 0 3px 0 #0b9275;
}

.metric-card-top,
.metric-card-bottom,
.ratio-topline {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
}

.metric-card-top > span:first-child {
  color: #546a63;
  font-size: 12px;
  font-weight: 700;
}

.metric-card-icon {
  display: grid;
  place-items: center;
  width: 31px;
  height: 31px;
  border-radius: 9px;
  color: #0a8a70;
  background: #e8f7ef;
}

.metric-card:nth-child(2) .metric-card-icon,
.metric-card:nth-child(4) .metric-card-icon {
  color: #3978d7;
  background: #edf4ff;
}

.metric-value-skeleton {
  display: block;
  width: 76px;
  height: 25px;
  margin: 16px 0 12px;
  border-radius: 5px;
  background: linear-gradient(90deg, #e9efec 20%, #f5f8f6 50%, #e9efec 80%);
  background-size: 200% 100%;
  animation: shimmer 1.7s linear infinite;
}

@keyframes shimmer {
  to { background-position: -200% 0; }
}

.metric-card-bottom {
  padding-top: 10px;
  border-top: 1px solid #eef2f0;
  color: #8b9994;
  font-size: 9px;
}

.metric-mini-line {
  width: 31px;
  height: 2px;
  background: #a9d1c1;
}

.dashboard-main-grid {
  display: grid;
  grid-template-columns: minmax(0, 1.6fr) minmax(300px, .95fr);
  gap: 15px;
}

.dashboard-panel {
  min-width: 0;
  padding: 20px;
  border: 1px solid #dfe8e4;
  border-radius: 11px;
  background: #fff;
  box-shadow: 0 7px 22px rgba(17, 56, 46, .035);
}

.panel-heading {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 14px;
  padding-bottom: 15px;
  border-bottom: 1px solid #e8efeb;
}

.panel-heading h2 {
  margin: 0 0 5px;
  color: #18312b;
  font-size: 20px;
  letter-spacing: -.04em;
}

.panel-heading p {
  margin: 0;
  color: #86948f;
  font-size: 11px;
  line-height: 1.5;
}

.panel-heading .status-pill { font-size: 9px; }

.chart-legend {
  display: flex;
  align-items: center;
  gap: 17px;
  margin: 15px 0 5px;
  color: #7c8b86;
  font-size: 9px;
}

.chart-legend span {
  display: inline-flex;
  align-items: center;
  gap: 6px;
}

.legend-dot {
  width: 7px;
  height: 7px;
  border-radius: 50%;
}

.legend-dot.green { background: #0b9a79; }
.legend-dot.blue { background: #4b88df; }
.chart-period-note { margin-left: auto; color: #9ba8a3; }

.chart-area {
  position: relative;
  height: 265px;
  margin-top: 8px;
  padding-left: 28px;
}

.chart-y-labels {
  position: absolute;
  top: 12px;
  bottom: 20px;
  left: 0;
  display: flex;
  flex-direction: column;
  justify-content: space-between;
  color: #a1ada8;
  font-family: "Courier New", monospace;
  font-size: 9px;
}

.performance-chart {
  width: 100%;
  height: 100%;
  overflow: visible;
}

.chart-gridline {
  stroke: #e7eeeb;
  stroke-width: 1;
  stroke-dasharray: 3 5;
}

.chart-area-fill { opacity: .45; }
.chart-line-animated {
  stroke-dasharray: 1100;
  stroke-dashoffset: 1100;
  animation: drawChart 2.4s .4s ease forwards;
}

@keyframes drawChart {
  to { stroke-dashoffset: 0; }
}

.chart-empty-overlay {
  position: absolute;
  top: 50%;
  left: 50%;
  display: flex;
  align-items: center;
  flex-direction: column;
  width: 230px;
  padding: 14px;
  border: 1px solid rgba(222, 232, 227, .85);
  border-radius: 9px;
  background: rgba(255,255,255,.88);
  text-align: center;
  transform: translate(-50%, -44%);
  backdrop-filter: blur(4px);
}

.chart-empty-icon {
  display: grid;
  place-items: center;
  width: 38px;
  height: 38px;
  margin-bottom: 8px;
  border-radius: 11px;
  color: #0a8a70;
  background: #e6f6ee;
}

.chart-empty-overlay strong { font-size: 11px; }
.chart-empty-overlay p {
  margin: 5px 0 0;
  color: #84938d;
  font-size: 9px;
  line-height: 1.45;
}

.chart-x-labels {
  display: flex;
  justify-content: space-between;
  padding: 0 0 0 28px;
  color: #a0aca7;
  font-size: 9px;
}

.panel-icon {
  display: grid;
  place-items: center;
  width: 35px;
  height: 35px;
  border-radius: 10px;
  color: #3978d7;
  background: #edf4ff;
}

.panel-icon.warning {
  color: #a5792c;
  background: #fff5e3;
}

.ratio-list {
  display: grid;
}

.ratio-item {
  padding: 15px 0 12px;
  border-bottom: 1px solid #edf1ef;
}

.ratio-item:last-child { border-bottom: 0; }

.ratio-topline span {
  color: #586d66;
  font-size: 11px;
  font-weight: 650;
}

.ratio-topline strong {
  color: #7b8b85;
  font-size: 12px;
}

.ratio-track {
  height: 5px;
  margin: 9px 0 6px;
  overflow: hidden;
  border-radius: 20px;
  background: #edf2ef;
}

.ratio-track i {
  display: block;
  height: 100%;
  border-radius: inherit;
  background: linear-gradient(90deg, #0d9b79, #6ba6ed);
  opacity: .65;
}

.ratio-item small {
  color: #a0aca7;
  font-size: 9px;
}

.dashboard-bottom-grid {
  display: grid;
  grid-template-columns: minmax(0, 1.6fr) minmax(280px, .95fr);
  gap: 15px;
  margin-top: 15px;
}

.statement-row {
  display: flex;
  align-items: center;
  gap: 11px;
  padding: 13px 0;
  border-bottom: 1px solid #edf1ef;
}

.statement-row:last-child { border-bottom: 0; }

.statement-icon {
  display: grid;
  place-items: center;
  width: 35px;
  height: 35px;
  flex: 0 0 35px;
  border-radius: 9px;
  color: #0b8b72;
  background: #eaf7f0;
}

.statement-row > div {
  display: flex;
  flex: 1;
  flex-direction: column;
  gap: 4px;
  min-width: 0;
}

.statement-row strong { font-size: 11px; }
.statement-row small { color: #8a9993; font-size: 9px; }
.statement-row .status-pill { font-size: 9px; }

.dashboard-notice {
  display: flex;
  align-items: flex-start;
  gap: 12px;
  padding: 20px;
  border: 1px solid #d7e7e0;
  border-left: 3px solid #0b9a79;
  border-radius: 10px;
  background: linear-gradient(140deg, #f0f8f3, #f1f7fc);
}

.notice-icon {
  display: grid;
  place-items: center;
  width: 35px;
  height: 35px;
  flex: 0 0 35px;
  border-radius: 10px;
  color: #0a8a70;
  background: #dff3e9;
}

.dashboard-notice h3 {
  margin: 2px 0 7px;
  font-size: 13px;
}

.dashboard-notice p {
  margin: 0;
  color: #73837d;
  font-size: 11px;
  line-height: 1.65;
}

.notice-footer {
  display: flex;
  align-items: center;
  gap: 7px;
  margin-top: 18px;
  padding-top: 11px;
  border-top: 1px solid #dce8e2;
  color: #698078;
  font-size: 10px;
  font-weight: 700;
}

.notice-dot {
  width: 6px;
  height: 6px;
  margin: 0;
  background: #0d9b79;
}

/* Evaluation */
.evaluation-summary {
  display: grid;
  grid-template-columns: 112px minmax(0, 1fr) minmax(250px, .72fr);
  align-items: center;
  gap: 25px;
  margin-top: 23px;
  padding: 23px 25px;
  border: 1px solid #dfe8e4;
  border-radius: 13px;
  background:
    radial-gradient(circle at 5% 20%, rgba(14, 156, 121, .08), transparent 28%),
    linear-gradient(110deg, #f5faf7, #f7faff);
}

.gauge-wrap { display: grid; place-items: center; }

.evaluation-gauge {
  display: grid;
  place-items: center;
  width: 96px;
  height: 96px;
  border-radius: 50%;
  background: conic-gradient(from 220deg, #dce8e2 0 78%, #4b9e89 78% 82%, #dce8e2 82% 100%);
  animation: gaugeGlow 3s ease-in-out infinite;
}

@keyframes gaugeGlow {
  0%, 100% { filter: drop-shadow(0 0 0 rgba(10, 145, 112, 0)); }
  50% { filter: drop-shadow(0 0 8px rgba(10, 145, 112, .18)); }
}

.gauge-center {
  display: flex;
  align-items: center;
  justify-content: center;
  flex-direction: column;
  width: 78px;
  height: 78px;
  border-radius: 50%;
  background: #f7faf8;
}

.gauge-center strong {
  color: #647771;
  font-family: Georgia, serif;
  font-size: 25px;
  font-weight: 500;
}

.gauge-center span {
  color: #8b9994;
  font-size: 9px;
}

.summary-label {
  color: #0c8b70;
  font-size: 10px;
  font-weight: 800;
  letter-spacing: .08em;
  text-transform: uppercase;
}

.evaluation-summary-copy h2 {
  margin: 6px 0;
  font-family: Georgia, serif;
  font-size: 25px;
  font-weight: 500;
  letter-spacing: -.03em;
}

.evaluation-summary-copy p {
  max-width: 610px;
  margin: 0;
  color: #74847e;
  font-size: 12px;
  line-height: 1.65;
}

.summary-tags {
  display: flex;
  flex-wrap: wrap;
  gap: 14px;
  margin-top: 12px;
}

.summary-tags span {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  color: #8a9993;
  font-size: 9px;
}

.summary-tags i {
  width: 6px;
  height: 6px;
  border-radius: 50%;
  background: #d2a047;
}

.evaluation-set-card {
  display: flex;
  align-items: flex-start;
  gap: 12px;
  padding: 17px;
  border-left: 1px solid #d6e3dd;
}

.set-card-icon {
  display: grid;
  place-items: center;
  width: 37px;
  height: 37px;
  flex: 0 0 37px;
  border-radius: 10px;
  color: #3978d7;
  background: #e7f0ff;
}

.evaluation-set-card > div:last-child {
  display: flex;
  flex-direction: column;
  align-items: flex-start;
  gap: 7px;
}

.evaluation-set-card strong { font-size: 12px; }
.evaluation-set-card span:not(.status-pill) {
  color: #7b8b85;
  font-size: 10px;
  line-height: 1.5;
}
.evaluation-set-card .status-pill { font-size: 9px; }

.evaluation-measures {
  width: 100%;
  padding: 44px 0 25px;
}

.evaluation-measures .section-heading {
  margin-bottom: 20px;
}

.evaluation-measures .section-heading h2 {
  margin-top: 0;
  font-size: 29px;
}

.evaluation-card-grid {
  display: grid;
  grid-template-columns: repeat(5, 1fr);
  gap: 13px;
}

.evaluation-measure-card {
  padding: 17px;
  border: 1px solid #e0e8e4;
  border-radius: 10px;
  background: #fff;
  animation: cardRise .55s both;
  animation-delay: var(--delay);
  transition: transform .25s ease, box-shadow .25s ease, border-color .25s ease;
}

@keyframes cardRise {
  from { opacity: 0; transform: translateY(12px); }
  to { opacity: 1; transform: translateY(0); }
}

.evaluation-measure-card:hover {
  transform: translateY(-4px);
  border-color: #a8cfc0;
  box-shadow: 0 13px 26px rgba(18, 59, 47, .08);
}

.measure-top {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  margin-bottom: 14px;
}

.measure-icon {
  display: grid;
  place-items: center;
  width: 37px;
  height: 37px;
  border-radius: 10px;
  color: #087e68;
  background: #e7f6ee;
}

.evaluation-measure-card:nth-child(2) .measure-icon,
.evaluation-measure-card:nth-child(4) .measure-icon {
  color: #3978d7;
  background: #eaf2ff;
}

.evaluation-measure-card:nth-child(5) .measure-icon {
  color: #a87928;
  background: #fff5e5;
}

.measure-top .status-pill {
  padding: 5px 7px;
  font-size: 8px;
}

.evaluation-measure-card h3 {
  min-height: 40px;
  margin: 0 0 7px;
  font-size: 14px;
  letter-spacing: -.025em;
  line-height: 1.35;
}

.evaluation-measure-card p {
  min-height: 62px;
  margin: 0;
  color: #7a8984;
  font-size: 10px;
  line-height: 1.55;
}

.measure-progress {
  height: 5px;
  margin: 15px 0 7px;
  overflow: hidden;
  border-radius: 10px;
  background: #e9efec;
}

.measure-progress span {
  display: block;
  width: 30%;
  height: 100%;
  border-radius: inherit;
  background: linear-gradient(90deg, #0d9b79, #6ba6ed);
  opacity: .5;
}

.evaluation-measure-card small {
  color: #a1ada8;
  font-size: 8px;
}

.evaluation-lower-grid {
  display: grid;
  grid-template-columns: minmax(0, 1.2fr) minmax(0, 1fr);
  gap: 15px;
  margin-top: 8px;
}

.category-filter {
  display: flex;
  flex-wrap: wrap;
  gap: 5px;
  margin: 16px 0 13px;
}

.category-filter button {
  padding: 7px 9px;
  border: 1px solid #e1e9e5;
  font-size: 9px;
}

.category-filter button.selected { border-color: #087b67; }

.category-table-head,
.category-table-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  padding: 11px 0;
  border-bottom: 1px solid #edf1ef;
}

.category-table-head {
  color: #9aa7a2;
  font-family: "Courier New", monospace;
  font-size: 9px;
}

.category-table-row > span:first-child {
  color: #3e5a50;
  font-size: 11px;
  font-weight: 650;
}

.category-table-row .status-pill {
  padding: 5px 7px;
  font-size: 8px;
}

.flagged-empty {
  display: flex;
  align-items: flex-start;
  gap: 12px;
  margin-top: 18px;
  padding: 17px;
  border: 1px solid #e7e9e2;
  border-left: 3px solid #d2a047;
  border-radius: 7px;
  background: #faf9f5;
}

.flagged-empty-icon {
  display: grid;
  place-items: center;
  width: 33px;
  height: 33px;
  flex: 0 0 33px;
  border-radius: 9px;
  color: #92702e;
  background: #f8edcf;
}

.flagged-empty strong { font-size: 11px; }
.flagged-empty p {
  margin: 5px 0 0;
  color: #88938d;
  font-size: 10px;
  line-height: 1.5;
}

.flagged-placeholder {
  margin-top: 18px;
  padding: 14px;
  border: 1px dashed #dfe7e2;
  border-radius: 7px;
}

.flagged-placeholder-line {
  width: 82%;
  height: 7px;
  margin-bottom: 9px;
  border-radius: 4px;
  background: #edf1ee;
}
.flagged-placeholder-line.short { width: 51%; }
.flagged-placeholder small { color: #a2ada8; font-size: 9px; }

.methodology-card {
  display: flex;
  align-items: flex-start;
  gap: 14px;
  margin-top: 16px;
  padding: 21px 24px;
  border: 1px solid #dce8e2;
  border-left: 3px solid #0b9b79;
  border-radius: 9px;
  background: linear-gradient(105deg, #eff8f2, #f4f8fc);
}

.methodology-icon {
  display: grid;
  place-items: center;
  width: 39px;
  height: 39px;
  flex: 0 0 39px;
  border-radius: 10px;
  color: #0a8a70;
  background: #dff2e7;
}

.methodology-card h2 {
  margin: 0 0 6px;
  font-family: Georgia, serif;
  font-size: 20px;
  font-weight: 500;
}

.methodology-card p {
  max-width: 1000px;
  margin: 0;
  color: #6f8079;
  font-size: 11px;
  line-height: 1.65;
}

/* Footer */
.site-footer {
  color: #eaf3ee;
  background: #102521;
}

.footer-main {
  display: grid;
  grid-template-columns: 210px minmax(250px, 1fr) auto;
  align-items: center;
  gap: 35px;
  width: min(1440px, calc(100% - 64px));
  margin: 0 auto;
  padding: 28px 0;
}

.footer-main .brand-mark {
  width: 35px;
  height: 35px;
  flex-basis: 35px;
  font-size: 20px;
}

.footer-main .brand-copy strong { font-size: 14px; }
.footer-main .brand-copy span { font-size: 9px; }

.footer-main > p {
  max-width: 700px;
  margin: 0;
  color: #b1c2bb;
  font-size: 11px;
  line-height: 1.6;
}

.footer-link {
  display: inline-flex;
  align-items: center;
  gap: 7px;
  padding: 0 0 5px;
  border: 0;
  border-bottom: 1px solid rgba(221, 243, 232, .45);
  color: #d6e9df;
  background: transparent;
  font-size: 11px;
  cursor: pointer;
}

.footer-link:hover { color: #8ce1bf; }

.footer-bottom {
  display: flex;
  justify-content: space-between;
  gap: 20px;
  padding: 11px max(6.5vw, calc((100vw - 1440px) / 2));
  border-top: 1px solid rgba(255,255,255,.1);
  color: #8ca39a;
  font-size: 9px;
}

/* Responsive layout */
@media (max-width: 1100px) {
  .hero-section {
    grid-template-columns: minmax(0, .95fr) minmax(370px, 1.05fr);
    gap: 25px;
  }

  .hero-art { transform: scale(.92); }
  .floating-evidence-card { right: -1%; }
  .trust-strip { flex-wrap: wrap; }
  .trust-intro { width: 100%; }
  .evaluation-card-grid { grid-template-columns: repeat(3, 1fr); }
}

@media (max-width: 850px) {
  .header-inner {
    width: calc(100% - 36px);
    grid-template-columns: 1fr auto auto;
    gap: 13px;
  }

  .mobile-menu-button {
    display: inline-flex;
    align-items: center;
    justify-content: center;
    width: 40px;
    height: 40px;
  }

  .main-nav {
    position: absolute;
    top: 78px;
    right: 0;
    left: 0;
    display: none;
    height: auto;
    padding: 10px 18px 18px;
    border-top: 1px solid rgba(255,255,255,.1);
    background: #102421;
    box-shadow: 0 14px 25px rgba(0,0,0,.16);
  }

  .main-nav.nav-open {
    display: flex;
    flex-direction: column;
    gap: 0;
    animation: detailDrop .2s ease both;
  }

  .nav-link {
    min-height: 46px;
    padding: 0 10px;
    text-align: left;
  }

  .nav-link::after {
    right: auto;
    left: 10px;
    width: 35px;
  }

  .header-cta { padding: 10px 12px; }
  .hero-section {
    grid-template-columns: 1fr;
    padding: 60px 34px 40px;
  }

  .hero-copy { max-width: 740px; }
  .hero-art { min-height: 420px; transform: none; }
  .report-sheet { width: min(440px, 72%); }
  .content-section,
  .inner-page { width: calc(100% - 48px); }
  .tata-feature { padding: 55px 34px; gap: 35px; }
  .ask-layout { grid-template-columns: 245px minmax(0, 1fr); gap: 14px; }
  .ask-sidebar { padding: 16px; }
  .dashboard-main-grid,
  .dashboard-bottom-grid { grid-template-columns: 1fr; }
  .evaluation-summary { grid-template-columns: 90px 1fr; }
  .evaluation-set-card { grid-column: 1 / -1; border-top: 1px solid #d6e3dd; border-left: 0; padding: 15px 0 0; }
  .footer-main { width: calc(100% - 48px); grid-template-columns: 170px 1fr; }
  .footer-link { grid-column: 2; justify-self: start; }
}

@media (max-width: 620px) {
  .header-inner { min-height: 68px; }
  .main-nav { top: 68px; }
  .brand-mark { width: 35px; height: 35px; flex-basis: 35px; font-size: 20px; }
  .brand-copy strong { font-size: 15px; }
  .brand-copy span { font-size: 9px; }
  .header-cta { font-size: 11px; padding: 9px 10px; }
  .header-cta svg { display: none; }

  .hero-section { padding: 42px 23px 30px; }
  .hero-copy h1 { font-size: clamp(43px, 12vw, 62px); }
  .hero-description { font-size: 16px; line-height: 1.65; }
  .hero-actions { gap: 9px; }
  .button-large { min-height: 48px; padding: 12px 15px; font-size: 13px; }
  .hero-art { min-height: 340px; margin: 5px -10px 0; }
  .report-sheet { width: 75%; min-height: 350px; padding: 22px 22px 18px; }
  .report-heading { margin-top: 31px; }
  .report-heading h3 { font-size: 21px; }
  .report-highlight { margin-top: 13px; padding: 9px; }
  .report-highlight p { font-size: 9px; }
  .floating-evidence-card { right: -1%; bottom: 13px; width: 165px; padding: 12px; }
  .floating-evidence-card strong { font-size: 14px; }
  .floating-evidence-card p { font-size: 8px; }
  .chip-top { top: 8px; left: -2px; }
  .chip-bottom { right: 0; bottom: -4px; }
  .floating-data-chip { padding: 7px 9px; }
  .chip-icon { width: 25px; height: 25px; }
  .floating-data-chip b { font-size: 9px; }
  .floating-data-chip small { font-size: 7px; }
  .art-orbit { width: 330px; height: 330px; }
  .orbit-two { width: 400px; height: 400px; }

  .trust-strip { padding: 17px 23px; gap: 14px; }
  .trust-item { width: calc(50% - 10px); font-size: 10px; }
  .trust-intro strong { font-size: 12px; }
  .trust-intro span:not(.trust-icon) { font-size: 10px; }

  .content-section { width: calc(100% - 46px); padding: 58px 0; }
  .section-heading { align-items: flex-start; margin-bottom: 22px; }
  .section-heading h2,
  .roadmap-heading h2,
  .tata-feature h2 { font-size: 31px; }
  .section-heading p,
  .roadmap-heading p { font-size: 13px; }
  .feature-grid { grid-template-columns: 1fr; gap: 12px; }
  .feature-card { min-height: auto; padding: 21px; }
  .feature-card h3 { font-size: 19px; }
  .feature-card p { font-size: 13px; }
  .feature-icon { margin-bottom: 16px; }
  .roadmap-heading { display: block; }
  .roadmap-stamp { width: fit-content; margin-top: 16px; }
  .roadmap { grid-template-columns: 1fr; }
  .roadmap-step { min-height: auto; padding: 20px; border-right: 0; border-bottom: 1px solid #e0eae5; }
  .roadmap-step:last-child { border-bottom: 0; }
  .roadmap-step-top { margin-bottom: 12px; }
  .roadmap-step h3 { font-size: 18px; }

  .tata-feature { grid-template-columns: 1fr; padding: 43px 23px; gap: 25px; }
  .tata-feature-art { min-height: 245px; }
  .steel-visual { height: 200px; }
  .tata-feature-copy > p { font-size: 14px; }
  .bottom-cta { align-items: flex-start; flex-direction: column; padding: 26px 23px; }
  .bottom-cta h2 { font-size: 23px; }
  .bottom-cta p { font-size: 11px; line-height: 1.55; }
  .button-light { align-self: stretch; }

  .inner-page { width: calc(100% - 36px); padding: 35px 0 50px; }
  .page-title-row { align-items: flex-start; flex-direction: column; gap: 13px; }
  .page-title-row h1 { font-size: 40px; }
  .page-title-row p { font-size: 13px; }
  .ask-layout { grid-template-columns: 1fr; }
  .ask-sidebar { order: 2; }
  .chat-panel { order: 1; min-height: 570px; }
  .chat-content { min-height: 320px; padding: 25px 18px; }
  .welcome-message { gap: 10px; }
  .welcome-icon { width: 37px; height: 37px; flex-basis: 37px; }
  .welcome-message h2 { font-size: 22px; }
  .welcome-message p { font-size: 12px; }
  .chat-composer { margin: 0 11px 11px; }
  .composer-bottom { align-items: flex-start; }
  .composer-bottom > span { max-width: 65%; line-height: 1.4; }
  .new-chat { font-size: 0; padding: 8px; }
  .new-chat svg { width: 16px; height: 16px; }
  .ask-page-links { gap: 15px; }
  .ask-page-links .text-link { font-size: 11px; }

  .dashboard-controls { align-items: flex-start; flex-wrap: wrap; gap: 12px; }
  .control-note { width: 100%; margin-left: 0; padding: 2px 0 0; }
  .metric-grid { grid-template-columns: repeat(2, 1fr); gap: 9px; }
  .metric-card { padding: 12px; }
  .metric-card-top > span:first-child { font-size: 10px; }
  .metric-card-icon { width: 27px; height: 27px; }
  .metric-value-skeleton { width: 60px; height: 21px; margin: 12px 0; }
  .dashboard-panel { padding: 15px; }
  .panel-heading h2 { font-size: 17px; }
  .chart-legend { flex-wrap: wrap; gap: 9px; }
  .chart-period-note { width: 100%; margin-left: 0; }
  .chart-area { height: 225px; }
  .chart-empty-overlay { width: 190px; }
  .evaluation-summary { grid-template-columns: 1fr; gap: 13px; padding: 18px; }
  .gauge-wrap { justify-content: start; }
  .evaluation-gauge { width: 78px; height: 78px; }
  .gauge-center { width: 63px; height: 63px; }
  .gauge-center strong { font-size: 21px; }
  .evaluation-set-card { grid-column: auto; }
  .evaluation-measures { padding-top: 37px; }
  .evaluation-measures .section-heading h2 { font-size: 25px; }
  .evaluation-card-grid { grid-template-columns: 1fr; }
  .evaluation-measure-card { padding: 16px; }
  .evaluation-measure-card h3,
  .evaluation-measure-card p { min-height: auto; }
  .evaluation-lower-grid { grid-template-columns: 1fr; }
  .methodology-card { padding: 17px; }
  .methodology-card h2 { font-size: 18px; }
  .footer-main { width: calc(100% - 36px); grid-template-columns: 1fr; gap: 17px; padding: 25px 0; }
  .footer-main > p { font-size: 10px; }
  .footer-link { grid-column: auto; }
  .footer-bottom { flex-direction: column; padding: 12px 18px; gap: 5px; }
}

@media (prefers-reduced-motion: reduce) {
  *,
  *::before,
  *::after {
    scroll-behavior: auto !important;
    animation-duration: .01ms !important;
    animation-iteration-count: 1 !important;
    transition-duration: .01ms !important;
  }
}
/* =========================================================
   EDITH LANDING PAGE — VISUAL REDESIGN
   Add this entire block at the VERY BOTTOM of App.css.
   ========================================================= */


/* ---------------------------------------------------------
   1. FULL-WIDTH LANDING PAGE
   --------------------------------------------------------- */

.home-page {
  position: relative;
  overflow: hidden;
  background:
    radial-gradient(
      circle at 7% 18%,
      rgba(20, 174, 139, 0.075),
      transparent 24%
    ),
    radial-gradient(
      circle at 91% 34%,
      rgba(55, 125, 220, 0.085),
      transparent 27%
    ),
    linear-gradient(
      180deg,
      #ffffff 0%,
      #fbfefd 44%,
      #ffffff 100%
    );
}


/* ---------------------------------------------------------
   2. HERO
   --------------------------------------------------------- */

.hero-section {
  position: relative;
  display: grid;
  grid-template-columns:
    minmax(520px, 0.88fr)
    minmax(560px, 1.12fr);
  align-items: center;
  gap: clamp(30px, 4vw, 75px);

  min-height: 730px;

  width: 100%;
  padding:
    70px
    clamp(34px, 5vw, 90px)
    75px;

  overflow: hidden;
  isolation: isolate;

  background:
    radial-gradient(
      circle at 74% 45%,
      rgba(45, 137, 221, 0.13),
      transparent 25%
    ),
    radial-gradient(
      circle at 57% 73%,
      rgba(9, 165, 128, 0.12),
      transparent 28%
    ),
    linear-gradient(
      110deg,
      #ffffff 0%,
      #fafffd 48%,
      #f7fbff 100%
    );
}


/* animated background lights */

.hero-background-glow {
  position: absolute;
  z-index: -2;
  border-radius: 50%;
  pointer-events: none;
  filter: blur(12px);
}

.hero-glow-green {
  width: 430px;
  height: 430px;
  left: -150px;
  top: 80px;
  background: rgba(11, 171, 134, 0.11);
  animation: heroGlowGreen 8s ease-in-out infinite;
}

.hero-glow-blue {
  width: 500px;
  height: 500px;
  right: -180px;
  bottom: -140px;
  background: rgba(64, 128, 229, 0.12);
  animation: heroGlowBlue 9s ease-in-out infinite;
}

@keyframes heroGlowGreen {
  0%,
  100% {
    transform: translate(0, 0) scale(1);
  }

  50% {
    transform: translate(55px, 20px) scale(1.13);
  }
}

@keyframes heroGlowBlue {
  0%,
  100% {
    transform: translate(0, 0) scale(1);
  }

  50% {
    transform: translate(-35px, -35px) scale(1.1);
  }
}


/* brighter grid */

.hero-grid-glow {
  position: absolute;
  z-index: -1;
  inset: 0;

  opacity: 0.55;

  background-image:
    linear-gradient(
      rgba(14, 126, 104, 0.045) 1px,
      transparent 1px
    ),
    linear-gradient(
      90deg,
      rgba(54, 119, 211, 0.045) 1px,
      transparent 1px
    );

  background-size: 54px 54px;

  mask-image:
    linear-gradient(
      90deg,
      black 0%,
      black 68%,
      transparent 100%
    );
}


/* ---------------------------------------------------------
   3. TATA STEEL HERO BADGE
   --------------------------------------------------------- */

.tata-hero-badge {
  display: inline-flex;
  align-items: center;
  gap: 11px;

  margin-bottom: 20px;
  padding: 9px 14px;

  border: 1px solid rgba(12, 126, 103, 0.19);
  border-radius: 999px;

  color: #087b67;
  background:
    linear-gradient(
      100deg,
      rgba(224, 249, 240, 0.9),
      rgba(238, 247, 255, 0.9)
    );

  box-shadow:
    0 8px 25px rgba(15, 113, 92, 0.07),
    inset 0 1px 0 rgba(255,255,255,0.9);

  animation:
    heroBadgeEnter
    0.75s
    cubic-bezier(.2,.8,.2,1)
    both;
}

.tata-hero-badge > span:nth-child(2) {
  font-size: 15px;
  font-weight: 900;
  letter-spacing: 0.12em;
}

.tata-hero-badge small {
  padding-left: 10px;
  border-left: 1px solid rgba(8, 123, 103, 0.22);

  color: #637b74;
  font-size: 10px;
  font-weight: 800;
  letter-spacing: 0.1em;
}

.tata-badge-dot {
  width: 9px;
  height: 9px;

  border-radius: 50%;

  background: linear-gradient(
    135deg,
    #0eaa85,
    #428ee8
  );

  box-shadow:
    0 0 0 5px rgba(17, 170, 132, 0.09),
    0 0 18px rgba(27, 151, 221, 0.35);

  animation: tataDotPulse 2.2s ease-in-out infinite;
}

@keyframes tataDotPulse {
  0%,
  100% {
    box-shadow:
      0 0 0 5px rgba(17, 170, 132, 0.09),
      0 0 12px rgba(27, 151, 221, 0.2);
  }

  50% {
    box-shadow:
      0 0 0 8px rgba(17, 170, 132, 0.03),
      0 0 24px rgba(27, 151, 221, 0.38);
  }
}

@keyframes heroBadgeEnter {
  from {
    opacity: 0;
    transform: translateY(10px);
  }

  to {
    opacity: 1;
    transform: translateY(0);
  }
}


/* ---------------------------------------------------------
   4. HERO TYPOGRAPHY
   --------------------------------------------------------- */

.hero-copy {
  max-width: 760px;
}

.hero-kicker {
  font-size: 14px;
}

.hero-copy h1 {
  margin-top: 20px;

  max-width: 780px;

  font-size:
    clamp(58px, 6vw, 92px);

  line-height: 0.98;
  letter-spacing: -0.075em;
}

.hero-copy h1 span {
  position: relative;

  background:
    linear-gradient(
      105deg,
      #087d68 5%,
      #12a987 43%,
      #258fd6 72%,
      #4a7fe4 100%
    );

  -webkit-background-clip: text;
  background-clip: text;
}

.hero-copy h1 span::after {
  position: absolute;

  right: 0;
  bottom: 3px;
  left: 0;

  height: 7px;

  border-radius: 999px;

  background:
    linear-gradient(
      90deg,
      rgba(8, 125, 104, 0.22),
      rgba(63, 133, 226, 0.12)
    );

  content: "";

  transform-origin: left;
  animation:
    heroUnderline
    1.1s
    0.7s
    cubic-bezier(.2,.8,.2,1)
    both;
}

@keyframes heroUnderline {
  from {
    transform: scaleX(0);
  }

  to {
    transform: scaleX(1);
  }
}

.hero-description {
  max-width: 700px;

  margin-top: 27px;

  color: #526b65;

  font-size:
    clamp(18px, 1.45vw, 22px);

  line-height: 1.72;
}

.hero-note {
  max-width: 610px;

  margin-top: 23px;

  font-size: 12px;
}


/* ---------------------------------------------------------
   5. HERO CUSTOM VISUAL
   --------------------------------------------------------- */

.tata-hero-art {
  position: relative;

  min-height: 580px;

  display: grid;
  place-items: center;

  overflow: visible;

  transform: none;

  animation:
    heroVisualEnter
    1s
    0.18s
    cubic-bezier(.16,.85,.25,1)
    both;
}

@keyframes heroVisualEnter {
  from {
    opacity: 0;
    transform:
      translateX(40px)
      scale(0.94);
  }

  to {
    opacity: 1;
    transform:
      translateX(0)
      scale(1);
  }
}


/* big orbital rings */

.hero-art-orbit {
  position: absolute;

  width: 560px;
  height: 560px;

  border:
    1px solid
    rgba(11, 144, 115, 0.15);

  border-radius: 50%;

  pointer-events: none;
}

.orbit-large {
  transform:
    rotate(-23deg)
    scaleY(0.55);

  animation:
    heroOrbitLarge
    10s
    ease-in-out
    infinite;
}

.orbit-small {
  width: 450px;
  height: 450px;

  border-color:
    rgba(60, 128, 220, 0.17);

  transform:
    rotate(26deg)
    scaleY(0.55);

  animation:
    heroOrbitSmall
    8s
    ease-in-out
    infinite;
}

@keyframes heroOrbitLarge {
  0%,
  100% {
    transform:
      rotate(-23deg)
      scaleY(.55)
      scale(1);
  }

  50% {
    transform:
      rotate(-15deg)
      scaleY(.55)
      scale(1.045);
  }
}

@keyframes heroOrbitSmall {
  0%,
  100% {
    transform:
      rotate(26deg)
      scaleY(.55)
      scale(1);
  }

  50% {
    transform:
      rotate(34deg)
      scaleY(.55)
      scale(.95);
  }
}


/* Tata Steel wordmark */

.tata-wordmark {
  position: absolute;

  z-index: 5;

  top: 35px;
  left: 4%;

  display: flex;
  align-items: baseline;
  gap: 10px;

  color: #102d28;

  animation:
    wordmarkFloat
    6s
    ease-in-out
    infinite;
}

.tata-wordmark span {
  font-family: Georgia, serif;

  font-size: 31px;
  font-weight: 700;

  letter-spacing: 0.09em;
}

.tata-wordmark strong {
  color: #0b9275;

  font-size: 17px;
  font-weight: 900;

  letter-spacing: 0.2em;
}

@keyframes wordmarkFloat {
  0%,
  100% {
    transform: translateY(0);
  }

  50% {
    transform: translateY(-6px);
  }
}


/* central financial object */

.steel-data-core {
  position: relative;
  z-index: 3;

  width: min(540px, 78%);
  aspect-ratio: 1 / 0.83;

  display: grid;
  place-items: center;

  overflow: hidden;

  border:
    1px solid
    rgba(255,255,255,0.72);

  border-radius: 36px;

  background:
    radial-gradient(
      circle at 50% 50%,
      rgba(255,255,255,0.96),
      rgba(239,249,246,0.72) 42%,
      rgba(235,244,252,0.66) 72%,
      rgba(255,255,255,0.2)
    );

  box-shadow:
    0 35px 75px rgba(20, 65, 55, 0.14),
    0 8px 25px rgba(48, 117, 207, 0.08),
    inset 0 1px 0 rgba(255,255,255,0.95);

  backdrop-filter: blur(10px);

  animation:
    coreFloat
    7s
    ease-in-out
    infinite;
}

@keyframes coreFloat {
  0%,
  100% {
    transform: translateY(0) rotate(-1deg);
  }

  50% {
    transform: translateY(-12px) rotate(1deg);
  }
}


/* central green/blue glow */

.steel-core-glow {
  position: absolute;

  width: 270px;
  height: 270px;

  border-radius: 50%;

  background:
    radial-gradient(
      circle,
      rgba(14, 174, 136, 0.22),
      rgba(55, 126, 220, 0.08) 48%,
      transparent 72%
    );

  filter: blur(10px);

  animation:
    coreGlow
    5s
    ease-in-out
    infinite;
}

@keyframes coreGlow {
  0%,
  100% {
    transform: scale(.85);
    opacity: .72;
  }

  50% {
    transform: scale(1.12);
    opacity: 1;
  }
}


/* rotating rings */

.steel-core-ring {
  position: absolute;

  border-radius: 50%;

  border: 1px solid transparent;

  pointer-events: none;
}

.ring-one {
  width: 310px;
  height: 310px;

  border-color:
    rgba(7, 145, 116, 0.22);

  border-left-color:
    rgba(7, 145, 116, 0.75);

  animation:
    ringRotateOne
    12s
    linear
    infinite;
}

.ring-two {
  width: 390px;
  height: 390px;

  border-color:
    rgba(56, 125, 218, 0.17);

  border-right-color:
    rgba(56, 125, 218, 0.7);

  animation:
    ringRotateTwo
    17s
    linear
    infinite;
}

.ring-three {
  width: 455px;
  height: 455px;

  border-style: dashed;

  border-color:
    rgba(15, 147, 119, 0.11);

  animation:
    ringRotateThree
    25s
    linear
    infinite;
}

@keyframes ringRotateOne {
  to {
    transform: rotate(360deg);
  }
}

@keyframes ringRotateTwo {
  to {
    transform: rotate(-360deg);
  }
}

@keyframes ringRotateThree {
  to {
    transform: rotate(360deg);
  }
}


/* central label */

.steel-core-center {
  position: relative;
  z-index: 5;

  display: flex;
  flex-direction: column;
  align-items: center;

  gap: 5px;

  text-align: center;
}

.steel-core-center span {
  color: #078a70;

  font-size: 11px;
  font-weight: 900;

  letter-spacing: .2em;
}

.steel-core-center strong {
  color: #102d28;

  font-size:
    clamp(25px, 2.7vw, 39px);

  font-weight: 850;

  letter-spacing: -.055em;
}

.steel-core-center small {
  margin-top: 5px;

  color: #7b8d87;

  font-size: 9px;
  font-weight: 700;

  letter-spacing: .13em;
}


/* graph behind the center */

.steel-chart-lines {
  position: absolute;

  inset:
    20% 9% 20%;

  display: flex;
  flex-direction: column;
  justify-content: space-between;

  opacity: .55;
}

.steel-chart-lines span {
  width: 100%;
  height: 1px;

  background:
    linear-gradient(
      90deg,
      transparent,
      rgba(16, 126, 104, .12),
      rgba(65, 128, 220, .13),
      transparent
    );
}


/* financial chart */

.hero-financial-line {
  position: absolute;

  z-index: 4;

  width: 90%;
  height: 68%;

  opacity: .82;

  pointer-events: none;
}

.hero-financial-line circle {
  fill: #ffffff;

  stroke: #16a987;
  stroke-width: 4;

  animation:
    chartDotPulse
    2.3s
    ease-in-out
    infinite;
}

.hero-financial-line circle:nth-of-type(2) {
  animation-delay: .25s;
}

.hero-financial-line circle:nth-of-type(3) {
  animation-delay: .5s;
}

.hero-financial-line circle:nth-of-type(4) {
  animation-delay: .75s;
}

@keyframes chartDotPulse {
  0%,
  100% {
    opacity: .65;
  }

  50% {
    opacity: 1;
  }
}


/* floating cards */

.floating-finance-card {
  position: absolute;

  z-index: 7;

  display: flex;
  align-items: center;

  gap: 10px;

  min-width: 205px;

  padding: 12px 14px;

  border:
    1px solid
    rgba(222,235,231,.95);

  border-radius: 13px;

  background:
    rgba(255,255,255,.94);

  box-shadow:
    0 18px 38px
    rgba(20,65,55,.12);

  backdrop-filter: blur(12px);

  animation:
    financeCardFloat
    5s
    ease-in-out
    infinite;
}

.finance-card-one {
  top: 125px;
  right: 3%;
}

.finance-card-two {
  left: 0;
  bottom: 118px;

  animation-delay: -2s;
}

.finance-card-three {
  right: 12%;
  bottom: 33px;

  min-width: auto;

  color: #24675a;

  animation-delay: -1s;
}

.finance-card-three span {
  font-size: 10px;
  font-weight: 800;
}

.finance-card-icon {
  display: grid;
  place-items: center;

  width: 38px;
  height: 38px;

  flex: 0 0 38px;

  border-radius: 11px;
}

.finance-card-icon.green {
  color: #087f68;
  background: #e2f7ee;
}

.finance-card-icon.blue {
  color: #3c7edc;
  background: #eaf2ff;
}

.floating-finance-card > div:last-child {
  display: flex;
  flex-direction: column;
  gap: 3px;
}

.floating-finance-card small {
  color: #82928c;

  font-size: 9px;
  font-weight: 600;
}

.floating-finance-card strong {
  color: #18332e;

  font-size: 12px;
  font-weight: 800;
}

.finance-status-dot {
  width: 8px;
  height: 8px;

  border-radius: 50%;

  background: #12a984;

  box-shadow:
    0 0 0 5px rgba(18,169,132,.1),
    0 0 18px rgba(18,169,132,.3);

  animation:
    statusPulse
    2s
    ease-in-out
    infinite;
}

@keyframes statusPulse {
  0%,
  100% {
    transform: scale(1);
  }

  50% {
    transform: scale(1.25);
  }
}

@keyframes financeCardFloat {
  0%,
  100% {
    transform: translateY(0);
  }

  50% {
    transform: translateY(-9px);
  }
}


/* hero sparks */

.hero-spark {
  position: absolute;

  z-index: 8;

  color: #109a7b;

  font-size: 24px;

  animation:
    sparkFloat
    4s
    ease-in-out
    infinite;
}

.spark-one {
  top: 110px;
  right: 28%;
}

.spark-two {
  left: 11%;
  bottom: 125px;

  color: #4d8ce5;

  animation-delay: -1.2s;
}

.spark-three {
  right: 4%;
  top: 260px;

  color: #12a987;

  font-size: 17px;

  animation-delay: -2.1s;
}

@keyframes sparkFloat {
  0%,
  100% {
    opacity: .5;
    transform: translateY(0) rotate(0);
  }

  50% {
    opacity: 1;
    transform: translateY(-10px) rotate(8deg);
  }
}


/* ---------------------------------------------------------
   6. TRUST STRIP
   --------------------------------------------------------- */

.trust-strip {
  position: relative;

  padding:
    26px
    clamp(34px, 5vw, 90px);

  background:
    linear-gradient(
      90deg,
      #ffffff,
      #f8fcfa 50%,
      #f7faff
    );

  border-top:
    1px solid
    rgba(18,91,76,.09);

  border-bottom:
    1px solid
    rgba(18,91,76,.09);

  box-shadow:
    0 8px 25px
    rgba(20, 70, 58, .025);
}

.trust-intro strong,
.trust-item {
  font-size: 14px;
}

.trust-intro span:not(.trust-icon) {
  font-size: 12px;
}


/* ---------------------------------------------------------
   7. LANDING CONTENT WIDTH
   --------------------------------------------------------- */

.content-section {
  width: 100%;

  padding:
    105px
    clamp(34px, 5vw, 90px);
}

.section-heading h2,
.roadmap-heading h2,
.tata-feature h2 {
  font-size:
    clamp(39px, 4.3vw, 62px);

  line-height: 1.04;
}

.section-heading p,
.roadmap-heading p {
  max-width: 850px;

  font-size:
    clamp(16px, 1.2vw, 19px);

  line-height: 1.7;
}


/* ---------------------------------------------------------
   8. FEATURE CARDS — MORE VISUAL
   --------------------------------------------------------- */

.feature-grid {
  gap: 22px;
}

.feature-card {
  min-height: 320px;

  padding: 32px;

  border-radius: 20px;

  box-shadow:
    0 8px 28px
    rgba(18, 60, 50, .045);

  transition:
    transform .35s cubic-bezier(.2,.8,.2,1),
    box-shadow .35s ease,
    border-color .35s ease;
}

.feature-card:hover {
  transform:
    translateY(-10px)
    rotateX(1deg);

  box-shadow:
    0 28px 55px
    rgba(18, 60, 50, .12);
}

.feature-card h3 {
  font-size: 26px;
}

.feature-card p {
  max-width: 430px;

  font-size: 16px;
  line-height: 1.7;
}

.feature-number {
  font-size: 11px;
}

.feature-icon {
  width: 58px;
  height: 58px;

  border-radius: 16px;
}


/* ---------------------------------------------------------
   9. DOTTED ROADMAP
   --------------------------------------------------------- */

.roadmap-section {
  padding-top: 45px;
  padding-bottom: 115px;
}

.roadmap-heading {
  margin-bottom: 58px;
}


/* remove old boxed roadmap */

.roadmap {
  display: none !important;
}


/* actual roadmap */

.visual-roadmap {
  position: relative;

  display: grid;
  grid-template-columns: repeat(3, 1fr);

  gap: 0;

  min-height: 310px;

  padding:
    0
    3%
    20px;
}


/* horizontal dotted path */

.roadmap-line {
  position: absolute;

  top: 61px;
  left: 9%;
  right: 9%;

  height: 4px;

  border-radius: 999px;

  background:
    repeating-linear-gradient(
      90deg,
      #b8d8cf 0,
      #b8d8cf 8px,
      transparent 8px,
      transparent 17px
    );
}


/* animated green/blue progress */

.roadmap-line-progress {
  position: absolute;

  top: 0;
  left: 0;

  width: 72%;
  height: 100%;

  border-radius: inherit;

  background:
    linear-gradient(
      90deg,
      #079d7b,
      #18b997,
      #448ce0
    );

  box-shadow:
    0 0 15px
    rgba(18, 170, 133, .2);

  animation:
    roadmapProgress
    3.5s
    cubic-bezier(.2,.75,.2,1)
    both;
}

@keyframes roadmapProgress {
  from {
    width: 0;
  }

  to {
    width: 72%;
  }
}


/* each roadmap item */

.roadmap-node {
  position: relative;

  display: flex;
  flex-direction: column;

  min-height: 300px;

  padding:
    0
    28px
    25px;

  border: 0;

  color: #132b26;

  background: transparent;

  text-align: left;

  cursor: pointer;

  transition:
    transform .3s ease;
}

.roadmap-node:hover {
  transform: translateY(-7px);
}


/* top row */

.roadmap-node-top {
  position: relative;
  z-index: 5;

  display: flex;
  align-items: center;
  justify-content: space-between;

  min-height: 125px;
}


/* numbered circles */

.roadmap-node-number {
  display: grid;
  place-items: center;

  width: 72px;
  height: 72px;

  border:
    5px solid
    #ffffff;

  border-radius: 50%;

  color: #087d68;

  background:
    linear-gradient(
      145deg,
      #e2f8ef,
      #eef8ff
    );

  box-shadow:
    0 0 0 1px #9ed1c0,
    0 13px 30px
    rgba(22, 117, 94, .11);

  font-family: "Courier New", monospace;
  font-size: 15px;
  font-weight: 900;

  transition:
    transform .35s ease,
    box-shadow .35s ease;
}

.roadmap-node:hover .roadmap-node-number,
.roadmap-node.expanded .roadmap-node-number {
  transform: scale(1.08);

  box-shadow:
    0 0 0 1px #3b9f86,
    0 0 0 9px rgba(19,166,130,.07),
    0 16px 35px
    rgba(22, 117, 94, .15);
}


/* icon */

.roadmap-node-icon {
  display: grid;
  place-items: center;

  width: 48px;
  height: 48px;

  border-radius: 15px;

  color: #087f69;

  background:
    #e5f7ef;

  box-shadow:
    0 10px 25px
    rgba(16, 122, 99, .08);

  transition:
    transform .3s ease;
}

.roadmap-node:nth-child(3) .roadmap-node-icon {
  color: #3979d9;
  background: #eaf2ff;
}

.roadmap-node:hover .roadmap-node-icon {
  transform: rotate(-5deg) scale(1.08);
}


/* little pointer under node */

.roadmap-pointer {
  position: absolute;

  top: 76px;
  left: 68px;

  width: 15px;
  height: 15px;

  border-right:
    2px solid
    #0e9878;

  border-bottom:
    2px solid
    #0e9878;

  transform:
    rotate(45deg);

  background: #ffffff;

  z-index: 4;
}

.roadmap-node:nth-child(3) .roadmap-pointer {
  border-color: #4c8fe5;
}


/* content */

.roadmap-node h3 {
  margin:
    24px
    0
    9px;

  color: #102b25;

  font-size: 29px;
  font-weight: 800;

  letter-spacing: -.045em;
}

.roadmap-node p {
  max-width: 340px;

  margin: 0;

  color: #687d76;

  font-size: 16px;

  line-height: 1.65;
}

.roadmap-detail {
  max-width: 390px;

  margin-top: 16px;

  padding-top: 15px;

  border-top:
    1px solid
    #d9e9e3;

  color: #4f6961;

  font-size: 13px;

  line-height: 1.65;

  animation:
    roadmapDetail
    .35s
    ease
    both;
}

@keyframes roadmapDetail {
  from {
    opacity: 0;
    transform: translateY(-8px);
  }

  to {
    opacity: 1;
    transform: translateY(0);
  }
}

.roadmap-more {
  display: inline-block;

  margin-top: auto;

  color: #078b70;

  font-size: 11px;
  font-weight: 850;

  letter-spacing: .07em;
  text-transform: uppercase;
}


/* ---------------------------------------------------------
   10. TATA FEATURE
   --------------------------------------------------------- */

.tata-feature {
  position: relative;

  width: 100%;

  grid-template-columns:
    minmax(430px, 1fr)
    minmax(450px, 1fr);

  padding:
    95px
    clamp(34px, 5vw, 90px);

  background:
    radial-gradient(
      circle at 20% 50%,
      rgba(16, 171, 134, .13),
      transparent 25%
    ),
    radial-gradient(
      circle at 82% 20%,
      rgba(64, 132, 225, .11),
      transparent 25%
    ),
    linear-gradient(
      110deg,
      #effaf5,
      #f5faff
    );
}

.tata-feature-copy h2 {
  font-size:
    clamp(42px, 4.5vw, 65px);
}

.tata-feature-copy > p {
  max-width: 720px;

  font-size:
    clamp(17px, 1.25vw, 20px);

  line-height: 1.75;
}

.tata-feature-points span {
  font-size: 15px;
}


/* ---------------------------------------------------------
   11. LANDING CTA
   --------------------------------------------------------- */

.bottom-cta {
  padding:
    45px
    clamp(34px, 5vw, 90px);
}

.bottom-cta h2 {
  font-size: 34px;
}

.bottom-cta p {
  font-size: 15px;
}


/* ---------------------------------------------------------
   12. MORE VISUAL STATUS
   --------------------------------------------------------- */

.status-pill {
  box-shadow:
    0 6px 20px
    rgba(132, 93, 30, .06);
}


/* ---------------------------------------------------------
   13. RESPONSIVE HERO
   --------------------------------------------------------- */

@media (max-width: 1100px) {

  .hero-section {
    grid-template-columns: 1fr;

    padding:
      65px
      5vw
      70px;
  }

  .hero-copy {
    max-width: 900px;
  }

  .hero-art {
    min-height: 550px;
  }

  .tata-wordmark {
    left: 10%;
  }

  .content-section {
    padding-left: 5vw;
    padding-right: 5vw;
  }

  .tata-feature {
    padding-left: 5vw;
    padding-right: 5vw;
  }

  .visual-roadmap {
    padding-left: 0;
    padding-right: 0;
  }
}


/* ---------------------------------------------------------
   14. TABLET ROADMAP
   --------------------------------------------------------- */

@media (max-width: 850px) {

  .hero-copy h1 {
    font-size:
      clamp(54px, 9vw, 76px);
  }

  .hero-description {
    font-size: 18px;
  }

  .tata-hero-art {
    min-height: 520px;
  }

  .steel-data-core {
    width: 68%;
  }

  .floating-finance-card {
    transform: scale(.9);
  }

  .visual-roadmap {
    grid-template-columns: 1fr;

    gap: 0;

    padding-left: 35px;
  }

  .roadmap-line {
    top: 20px;
    bottom: 25px;

    left: 70px;
    right: auto;

    width: 4px;
    height: auto;

    background:
      repeating-linear-gradient(
        180deg,
        #b8d8cf 0,
        #b8d8cf 8px,
        transparent 8px,
        transparent 17px
      );
  }

  .roadmap-line-progress {
    width: 100%;
    height: 72%;

    background:
      linear-gradient(
        180deg,
        #079d7b,
        #18b997,
        #448ce0
      );

    animation:
      roadmapProgressVertical
      3.5s
      cubic-bezier(.2,.75,.2,1)
      both;
  }

  @keyframes roadmapProgressVertical {
    from {
      height: 0;
    }

    to {
      height: 72%;
    }
  }

  .roadmap-node {
    min-height: 230px;

    padding:
      0
      0
      35px
      70px;
  }

  .roadmap-node-top {
    min-height: 95px;
  }

  .roadmap-pointer {
    top: 56px;
    left: 62px;
  }

  .roadmap-node-number {
    width: 62px;
    height: 62px;
  }

  .roadmap-node h3 {
    margin-top: 17px;
  }

  .tata-feature {
    grid-template-columns: 1fr;
  }
}


/* ---------------------------------------------------------
   15. MOBILE
   --------------------------------------------------------- */

@media (max-width: 620px) {

  .hero-section {
    min-height: auto;

    padding:
      45px
      22px
      35px;
  }

  .tata-hero-badge {
    flex-wrap: wrap;

    max-width: 100%;

    padding: 8px 11px;
  }

  .tata-hero-badge > span:nth-child(2) {
    font-size: 13px;
  }

  .tata-hero-badge small {
    font-size: 8px;
  }

  .hero-copy h1 {
    margin-top: 18px;

    font-size:
      clamp(46px, 14vw, 63px);

    line-height: .98;
  }

  .hero-copy h1 span::after {
    height: 5px;
  }

  .hero-description {
    font-size: 16px;
    line-height: 1.65;
  }

  .hero-actions {
    align-items: stretch;
    flex-direction: column;
  }

  .hero-actions .button {
    width: 100%;
  }

  .tata-hero-art {
    min-height: 430px;
    margin-top: 20px;
  }

  .hero-art-orbit {
    width: 390px;
    height: 390px;
  }

  .orbit-small {
    width: 315px;
    height: 315px;
  }

  .steel-data-core {
    width: 92%;
    border-radius: 27px;
  }

  .ring-one {
    width: 230px;
    height: 230px;
  }

  .ring-two {
    width: 300px;
    height: 300px;
  }

  .ring-three {
    width: 345px;
    height: 345px;
  }

  .steel-core-center strong {
    font-size: 27px;
  }

  .steel-core-center span {
    font-size: 9px;
  }

  .tata-wordmark {
    top: 7px;
    left: 3%;
  }

  .tata-wordmark span {
    font-size: 23px;
  }

  .tata-wordmark strong {
    font-size: 12px;
  }

  .floating-finance-card {
    min-width: 160px;

    padding: 9px;

    gap: 7px;

    border-radius: 10px;
  }

  .finance-card-one {
    top: 65px;
    right: -3%;
  }

  .finance-card-two {
    left: -2%;
    bottom: 78px;
  }

  .finance-card-three {
    right: 2%;
    bottom: 17px;
  }

  .floating-finance-card strong {
    font-size: 10px;
  }

  .floating-finance-card small {
    font-size: 7px;
  }

  .finance-card-icon {
    width: 29px;
    height: 29px;
    flex-basis: 29px;
  }

  .hero-spark {
    display: none;
  }


  .trust-strip {
    padding:
      20px
      22px;
  }

  .trust-item {
    width: 100%;
    font-size: 12px;
  }


  .content-section {
    width: 100%;

    padding:
      65px
      22px;
  }

  .section-heading {
    margin-bottom: 27px;
  }

  .section-heading h2,
  .roadmap-heading h2,
  .tata-feature h2 {
    font-size: 38px;
  }

  .section-heading p,
  .roadmap-heading p {
    font-size: 15px;
  }

  .feature-card {
    min-height: auto;

    padding: 25px;
  }

  .feature-card h3 {
    font-size: 24px;
  }

  .feature-card p {
    font-size: 15px;
  }


  .roadmap-section {
    padding-bottom: 75px;
  }

  .roadmap-heading {
    display: block;
  }

  .roadmap-stamp {
    margin-top: 20px;
  }

  .visual-roadmap {
    padding-left: 15px;
  }

  .roadmap-line {
    left: 45px;
  }

  .roadmap-node {
    padding-left: 60px;
  }

  .roadmap-node-number {
    width: 55px;
    height: 55px;

    font-size: 12px;
  }

  .roadmap-pointer {
    left: 40px;
    top: 51px;
  }

  .roadmap-node-icon {
    width: 42px;
    height: 42px;
  }

  .roadmap-node h3 {
    font-size: 25px;
  }

  .roadmap-node p {
    font-size: 14px;
  }


  .tata-feature {
    padding:
      65px
      22px;
  }

  .tata-feature-copy h2 {
    font-size: 38px;
  }

  .tata-feature-copy > p {
    font-size: 15px;
  }

  .tata-feature-points span {
    font-size: 13px;
  }

  .tata-feature-art {
    min-height: 260px;
  }


  .bottom-cta {
    padding:
      30px
      22px;
  }

  .bottom-cta h2 {
    font-size: 28px;
  }

  .bottom-cta p {
    font-size: 13px;
  }
}


/* ---------------------------------------------------------
   16. EXTRA MOTION POLISH
   --------------------------------------------------------- */

.hero-section,
.feature-card,
.visual-roadmap,
.tata-feature {
  will-change: transform;
}

.feature-card::before {
  position: absolute;

  top: -100%;
  left: -50%;

  width: 40%;
  height: 300%;

  content: "";

  background:
    linear-gradient(
      90deg,
      transparent,
      rgba(255,255,255,.5),
      transparent
    );

  transform: rotate(20deg);

  transition:
    left .8s ease;
}

.feature-card:hover::before {
  left: 130%;
}


/* subtle section light */

.content-section::before {
  position: absolute;

  width: 220px;
  height: 220px;

  border-radius: 50%;

  background:
    radial-gradient(
      circle,
      rgba(18,168,132,.07),
      transparent 70%
    );

  content: "";

  pointer-events: none;
}


/* Don't let pseudo element affect layout */

.feature-section,
.roadmap-section {
  position: relative;
}


/* accessibility */

@media (prefers-reduced-motion: reduce) {

  .hero-background-glow,
  .hero-art-orbit,
  .steel-data-core,
  .steel-core-glow,
  .steel-core-ring,
  .floating-finance-card,
  .hero-spark,
  .tata-wordmark,
  .roadmap-line-progress,
  .tata-hero-badge {
    animation: none !important;
  }

}

/* Requested refinement pass — scoped to the named pages/components. */
.nav-link { font-size: 16px; }

/* A lighter, original editorial trend treatment for the home explore feature. */
.feature-explore {
  color: var(--ink);
  border-color: #d9e9e3;
  background: linear-gradient(135deg, #effaf5 0%, #f9fcff 58%, #eef5ff 100%);
}
.feature-explore h3 { color: #17332d; }
.feature-explore p { color: #5f746e; }
.feature-explore .feature-number,
.feature-explore .text-link { color: #087e68; }
.feature-explore .feature-icon { color: #087e68; background: #dff4e9; }
.feature-trend-art {
  position: absolute;
  top: 18px;
  right: 18px;
  width: 42%;
  max-width: 230px;
  opacity: .85;
  pointer-events: none;
}
.feature-trend-art svg { width: 100%; height: auto; overflow: visible; }
.feature-trend-art .trend-area { fill: rgba(28, 159, 128, .07); }
.feature-trend-art .trend-line { fill: none; stroke: #168e77; stroke-width: 2.2; stroke-linecap: round; }
.feature-trend-art circle { fill: #f9fcff; stroke: #168e77; stroke-width: 2; }
.feature-explore .feature-icon,
.feature-explore .feature-number,
.feature-explore h3,
.feature-explore p,
.feature-explore .text-link { position: relative; z-index: 1; }

/* Keep inner pages comfortably readable at ordinary browser zoom. */
.inner-page { width: min(1500px, calc(100% - 72px)); padding-top: 30px; padding-bottom: 44px; }
.page-title-row { padding-bottom: 18px; }
.page-title-row p { font-size: 17px; }
.dashboard-page { padding-bottom: 34px; }
.dashboard-page .dashboard-controls { margin-top: 16px; margin-bottom: 13px; padding: 11px 15px; }
.dashboard-page .dashboard-panel { padding: 16px; }
.dashboard-page .panel-heading p,
.dashboard-page .dashboard-panel p { font-size: 14px; line-height: 1.55; }
.dashboard-page .metric-card { min-height: 90px; }

/* Ask Edith: collapse to a slim control rail, with an interactive history list. */
.ask-layout { grid-template-columns: 280px minmax(0, 1fr); gap: 18px; margin-top: 18px; }
.ask-sidebar { position: relative; min-width: 0; transition: width .25s ease, padding .25s ease; }
.sidebar-toggle {
  display: block; width: 100%; margin: 0 0 14px; padding: 7px 9px;
  border: 1px solid rgba(220, 245, 235, .22); border-radius: 7px;
  color: #d6eee5; background: rgba(255,255,255,.055);
  font-size: 12px; font-weight: 700; text-align: left; cursor: pointer;
}
.sidebar-toggle:hover { background: rgba(255,255,255,.12); }
.ask-layout.sidebar-collapsed { grid-template-columns: 54px minmax(0, 1fr); }
.ask-layout.sidebar-collapsed .ask-sidebar { padding: 10px; }
.ask-layout.sidebar-collapsed .sidebar-toggle { writing-mode: vertical-rl; text-align: center; padding: 12px 7px; margin: 0; min-height: 116px; }
.ask-layout.sidebar-collapsed .sidebar-heading,
.ask-layout.sidebar-collapsed .suggestion-list,
.ask-layout.sidebar-collapsed .sidebar-info,
.ask-layout.sidebar-collapsed .sidebar-recent { display: none; }
.chat-panel { border: 2px solid transparent; background: linear-gradient(#fff,#fff) padding-box, linear-gradient(115deg,#0a9c7e,#6aa7ff) border-box; }
.chat-panel-header { padding: 14px 19px; }
.sidebar-recent { display: block; }
.recent-heading { display: flex; align-items: center; gap: 8px; margin-bottom: 9px; }
.recent-question-list { display: flex; flex-direction: column; gap: 6px; }
.recent-question {
  width: 100%; padding: 8px 9px; border: 1px solid rgba(255,255,255,.09);
  border-radius: 7px; color: #d6e6df; background: rgba(255,255,255,.045);
  font-size: 11px; line-height: 1.4; text-align: left; cursor: pointer;
  overflow: hidden; display: -webkit-box; -webkit-line-clamp: 2; -webkit-box-orient: vertical;
}
.recent-question:hover, .recent-question.active { border-color: rgba(110,220,185,.45); background: rgba(32,165,130,.18); color: #fff; }
.recent-empty { display: block; color: #a7bdb4; font-size: 11px; line-height: 1.5; }

/* Dashboard orientation: use a wider canvas and tighter vertical rhythm. */
.dashboard-page .page-title-row { align-items: center; }
.dashboard-page .page-title-row h1 { font-size: clamp(42px, 4vw, 58px); }
.dashboard-page .dashboard-controls label { font-size: 13px; }
.dashboard-page .dashboard-grid, .dashboard-page .dashboard-main-grid { gap: 14px; }
.dashboard-page .dashboard-panel h2 { font-size: 20px; }

/* Evaluation: communicate what is known vs. not yet measured without status clutter. */
.evaluation-page { padding-top: 28px; padding-bottom: 36px; }
.evaluation-page .page-title-row h1 { font-size: clamp(42px, 4vw, 58px); }
.evaluation-page .evaluation-summary { margin-top: 17px; padding: 18px 22px; grid-template-columns: 96px minmax(0,1fr) minmax(230px,.7fr); gap: 20px; }
.evaluation-page .evaluation-summary-copy h2 { font-size: 28px; }
.evaluation-page .evaluation-summary-copy p { font-size: 14px; }
.evaluation-page .evaluation-set-card strong { font-size: 14px; }
.evaluation-page .evaluation-set-card span:not(.status-pill) { font-size: 13px; }
.evaluation-page .evaluation-measures { padding: 28px 0 18px; }
.evaluation-page .evaluation-measures .section-heading { margin-bottom: 14px; }
.evaluation-page .evaluation-measures .section-heading h2 { font-size: 30px; }
.evaluation-page .evaluation-card-grid { grid-template-columns: repeat(5,minmax(0,1fr)); gap: 10px; }
.evaluation-page .evaluation-measure-card { padding: 15px; }
.evaluation-page .evaluation-measure-card h3 { min-height: 0; font-size: 16px; }
.evaluation-page .evaluation-measure-card p { min-height: 68px; font-size: 12px; }
.evaluation-page .measure-progress { margin-top: 11px; }
.evaluation-page .evaluation-measure-card small { font-size: 10px; }
.evaluation-page .evaluation-lower-grid { gap: 14px; margin-top: 4px; }
.evaluation-page .dashboard-panel { padding: 17px; }
.evaluation-page .panel-heading h2 { font-size: 19px; }
.evaluation-page .panel-heading p { font-size: 13px; line-height: 1.5; }
.evaluation-page .category-filter button { font-size: 11px; }
.evaluation-page .category-table-head, .evaluation-page .category-table-row { font-size: 12px; }
.evaluation-page .evaluation-how-it-works, .evaluation-page .evaluation-note { font-size: 13px; }

@media (max-width: 900px) {
  .inner-page { width: min(100% - 36px, 760px); padding-top: 24px; }
  .evaluation-page .evaluation-summary { grid-template-columns: 78px minmax(0,1fr); }
  .evaluation-page .evaluation-set-card { grid-column: 1 / -1; border-left: 0; border-top: 1px solid #d6e3dd; padding: 14px 0 0; }
  .evaluation-page .evaluation-card-grid { grid-template-columns: repeat(2,minmax(0,1fr)); }
  .evaluation-page .evaluation-lower-grid { grid-template-columns: 1fr; }
}
@media (max-width: 620px) {
  .nav-link { font-size: 14px; }
  .ask-layout, .ask-layout.sidebar-collapsed { grid-template-columns: 1fr; }
  .ask-layout.sidebar-collapsed .ask-sidebar { padding: 12px; }
  .ask-layout.sidebar-collapsed .sidebar-toggle { writing-mode: initial; min-height: 0; width: auto; }
  .evaluation-page .evaluation-card-grid { grid-template-columns: 1fr; }
  .feature-trend-art { width: 38%; opacity: .45; }
}

.evaluation-page .measure-definition { display: block; margin-top: 14px; color: #6f817b; font-size: 11px; font-weight: 650; }
.evaluation-page .category-table-head { grid-template-columns: 1fr; }
.evaluation-page .category-table-row { grid-template-columns: 1fr; }
/* =========================================================
   EDITH — INNER PAGE LAYOUT REFINEMENT
   Scoped to Ask Edith, Dashboard and Evaluation.
   Landing page styles remain unchanged.
   ========================================================= */

/* Wider website canvas and reduced unnecessary whitespace */

.inner-page {
  width: min(1640px, calc(100% - 80px));
  max-width: 1640px;
  margin: 0 auto;
  padding: 30px 0 48px;
}

.inner-page .page-title-row {
  margin-bottom: 22px;
  padding-bottom: 20px;
}

.inner-page .page-title-row h1 {
  font-size: clamp(42px, 4vw, 60px);
  line-height: 1.05;
  letter-spacing: -0.055em;
}

.inner-page .page-title-row p {
  max-width: 900px;
  margin-top: 8px;
  font-size: 17px;
  line-height: 1.65;
  color: #657872;
}


/* =========================================================
   ASK EDITH
   A wider, usable workspace with an interactive sidebar
   ========================================================= */

.ask-page {
  padding-top: 28px;
  padding-bottom: 40px;
}

.ask-page .page-title-row {
  margin-bottom: 18px;
}

.ask-layout {
  display: grid;
  grid-template-columns: minmax(270px, 310px) minmax(0, 1fr);
  align-items: stretch;
  gap: 20px;
  margin-top: 12px;
}

/* Sidebar */

.ask-sidebar {
  position: relative;
  display: flex;
  flex-direction: column;
  align-self: stretch;
  min-width: 0;
  max-height: 740px;
  padding: 20px;
  overflow-y: auto;
  overscroll-behavior: contain;
  border: 1px solid rgba(112, 183, 158, 0.45);
  border-radius: 14px;
  background:
    radial-gradient(
      circle at 5% 0%,
      rgba(41, 167, 132, 0.16),
      transparent 38%
    ),
    linear-gradient(155deg, #153b34 0%, #102b26 100%);
  box-shadow: 0 12px 30px rgba(12, 50, 40, 0.1);
  scrollbar-width: thin;
  scrollbar-color: #527a6d transparent;
  transition:
    padding 0.25s ease,
    border-radius 0.25s ease;
}

.sidebar-toggle {
  position: sticky;
  top: 0;
  z-index: 2;
  flex-shrink: 0;
  min-height: 38px;
  margin: 0 0 18px;
  padding: 9px 12px;
  border: 1px solid rgba(218, 245, 232, 0.3);
  border-radius: 8px;
  color: #e1f2eb;
  background: rgba(255, 255, 255, 0.08);
  font-size: 13px;
  font-weight: 750;
  text-align: left;
  cursor: pointer;
  transition:
    background 0.2s ease,
    border-color 0.2s ease,
    transform 0.2s ease;
}

.sidebar-toggle:hover {
  border-color: rgba(113, 226, 186, 0.7);
  background: rgba(255, 255, 255, 0.14);
}

.sidebar-heading {
  display: flex;
  align-items: center;
  gap: 12px;
  margin-bottom: 16px;
}

.sidebar-heading h2 {
  margin: 0 0 4px;
  color: #f4faf7;
  font-size: 17px;
  line-height: 1.35;
}

.sidebar-heading p {
  margin: 0;
  color: #b2c9bf;
  font-size: 13px;
  line-height: 1.5;
}

.sidebar-heading-icon {
  flex: 0 0 40px;
  width: 40px;
  height: 40px;
  border-radius: 11px;
}

/* Make the prompts easy to scan and select */

.suggestion-list {
  display: flex;
  flex-direction: column;
  gap: 0;
}

.suggestion-item {
  position: relative;
  display: grid;
  grid-template-columns: minmax(0, 1fr) 20px;
  align-items: center;
  gap: 5px 10px;
  width: 100%;
  min-height: 78px;
  padding: 13px 2px;
  border: 0;
  border-bottom: 1px solid rgba(222, 243, 233, 0.16);
  border-radius: 0;
  color: #f4faf7;
  background: transparent;
  text-align: left;
  cursor: pointer;
  transition:
    padding 0.2s ease,
    background 0.2s ease;
}

.suggestion-item:hover {
  padding-right: 8px;
  padding-left: 8px;
  border-radius: 7px;
  background: rgba(255, 255, 255, 0.075);
}

.suggestion-item > span {
  grid-column: 1;
  color: #8bd9bb;
  font-size: 11px;
  font-weight: 850;
  letter-spacing: 0.09em;
  text-transform: uppercase;
}

.suggestion-item strong {
  grid-column: 1;
  color: #f2f8f5;
  font-size: 14px;
  font-weight: 700;
  line-height: 1.45;
}

.suggestion-item svg {
  grid-column: 2;
  grid-row: 1 / span 2;
  color: #9dc8b8;
  transition: transform 0.2s ease;
}

.suggestion-item:hover svg {
  transform: translateX(3px);
}

/* Information section */

.sidebar-info {
  margin-top: 20px;
  padding: 15px;
  border: 1px solid rgba(216, 242, 228, 0.2);
  border-radius: 10px;
  background: rgba(255, 255, 255, 0.055);
}

.sidebar-info-title {
  display: flex;
  align-items: center;
  gap: 9px;
  margin-bottom: 10px;
  color: #e5f5ed;
  font-size: 13px;
  font-weight: 750;
}

.sidebar-info-title svg {
  color: #85d6b7;
}

.sidebar-info-row {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 12px;
  padding: 9px 0;
  border-top: 1px solid rgba(216, 242, 228, 0.12);
  font-size: 12px;
  line-height: 1.4;
}

.sidebar-info-row span {
  color: #a8c0b6;
}

.sidebar-info-row b {
  color: #eaf5ef;
  font-weight: 650;
  text-align: right;
}

/* Recent conversation history */

.sidebar-recent {
  margin-top: 20px;
  padding-top: 15px;
  border-top: 1px solid rgba(216, 242, 228, 0.2);
}

.recent-heading {
  display: flex;
  align-items: center;
  gap: 9px;
  margin-bottom: 12px;
  color: #e5f5ed;
  font-size: 13px;
}

.recent-heading .recent-dot {
  flex: 0 0 7px;
  margin-top: 0;
  background: #6fd6ad;
}

.recent-question-list {
  display: flex;
  flex-direction: column;
  gap: 7px;
}

.recent-question {
  width: 100%;
  padding: 10px 11px;
  border: 1px solid rgba(225, 245, 234, 0.14);
  border-radius: 8px;
  color: #dbeae3;
  background: rgba(255, 255, 255, 0.045);
  font-size: 12px;
  line-height: 1.5;
  text-align: left;
  cursor: pointer;
  transition:
    border-color 0.2s ease,
    background 0.2s ease;
}

.recent-question:hover,
.recent-question.active {
  border-color: rgba(116, 221, 183, 0.55);
  background: rgba(26, 158, 120, 0.19);
  color: #fff;
}

.recent-empty {
  display: block;
  color: #afc5bb;
  font-size: 12px;
  line-height: 1.6;
}

/* Sidebar collapse */

.ask-layout.sidebar-collapsed {
  grid-template-columns: 58px minmax(0, 1fr);
  gap: 16px;
}

.ask-layout.sidebar-collapsed .ask-sidebar {
  padding: 10px;
  overflow: hidden;
}

.ask-layout.sidebar-collapsed .sidebar-toggle {
  min-height: 116px;
  padding: 12px 7px;
  margin: 0;
  writing-mode: vertical-rl;
  text-align: center;
}

.ask-layout.sidebar-collapsed .sidebar-heading,
.ask-layout.sidebar-collapsed .suggestion-list,
.ask-layout.sidebar-collapsed .sidebar-info,
.ask-layout.sidebar-collapsed .sidebar-recent {
  display: none;
}

/* Chat workspace */

.chat-panel {
  display: flex;
  flex-direction: column;
  min-width: 0;
  min-height: 600px;
  height: min(740px, calc(100vh - 220px));
  border: 2px solid transparent;
  border-radius: 14px;
  background:
    linear-gradient(#fff, #fff) padding-box,
    linear-gradient(115deg, #079b7e, #3b8be8) border-box;
  box-shadow: 0 14px 34px rgba(18, 56, 47, 0.065);
}

.chat-panel-header {
  flex: 0 0 auto;
  padding: 16px 20px;
  border-bottom: 1px solid #e2ebe6;
  border-radius: 12px 12px 0 0;
  background: linear-gradient(105deg, #f8fcfa, #f4f8fc);
}

.chat-panel-header strong {
  font-size: 15px;
}

.chat-panel-header span {
  font-size: 12px;
}

.new-chat {
  min-height: 38px;
  padding: 9px 12px;
  border: 1px solid #d6e5de;
  border-radius: 8px;
  color: #34584e;
  background: #fff;
  font-size: 12px;
  font-weight: 700;
  cursor: pointer;
  transition:
    border-color 0.2s ease,
    background 0.2s ease;
}

.new-chat:hover {
  border-color: #75bda7;
  background: #f0faf5;
}

.chat-content {
  flex: 1 1 auto;
  min-height: 0;
  padding: clamp(20px, 3vw, 42px);
  overflow-y: auto;
}

.welcome-message {
  max-width: 900px;
  gap: 16px;
}

.welcome-message h2 {
  font-size: clamp(25px, 2.1vw, 34px);
}

.welcome-message p,
.assistant-message-body p {
  font-size: 15px;
  line-height: 1.75;
}

.welcome-callout {
  max-width: 700px;
  margin-top: 20px;
  padding: 15px 17px;
  font-size: 13px;
  line-height: 1.6;
}

/* Composer: make the input clearly visible and easy to use */

.chat-composer {
  flex: 0 0 auto;
  margin: 0 16px 16px;
  padding: 13px 15px;
  border: 2px solid transparent;
  border-radius: 12px;
  background:
    linear-gradient(#fff, #fff) padding-box,
    linear-gradient(110deg, #0a9e80, #438fe8) border-box;
  box-shadow: 0 6px 20px rgba(15, 65, 52, 0.06);
}

.chat-composer textarea {
  width: 100%;
  min-height: 68px;
  padding: 6px 3px 12px;
  border: 0;
  outline: 0;
  color: #18332e;
  background: transparent;
  font: inherit;
  font-size: 15px;
  line-height: 1.6;
  resize: vertical;
}

.chat-composer textarea::placeholder {
  color: #8b9b95;
  opacity: 1;
}

.composer-bottom {
  padding-top: 10px;
  border-top: 1px solid #e5ece8;
}

.composer-bottom > span {
  font-size: 12px;
  line-height: 1.5;
}

.composer-bottom .button {
  min-height: 42px;
  padding: 10px 17px;
  font-size: 13px;
}

/* Links under the chat */

.ask-page-links {
  display: flex;
  flex-wrap: wrap;
  gap: 24px;
  margin-top: 18px;
}

.ask-page-links .text-link {
  font-size: 14px;
}


/* =========================================================
   DASHBOARD
   Website-style orientation, preserving existing visuals
   ========================================================= */

.dashboard-page {
  padding-top: 28px;
  padding-bottom: 42px;
}

.dashboard-page .page-title-row {
  margin-bottom: 18px;
}

.dashboard-page .page-title-row h1 {
  font-size: clamp(42px, 4vw, 60px);
}

.dashboard-page .page-title-row p {
  font-size: 17px;
}

/* Keep filters compact and readable */

.dashboard-page .dashboard-controls {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 18px;
  margin: 0 0 16px;
  padding: 14px 18px;
  border-radius: 12px;
}

.dashboard-page .control-group label {
  margin-bottom: 7px;
  font-size: 13px;
}

.dashboard-page .segmented-control button {
  min-height: 34px;
  padding: 8px 12px;
  font-size: 12px;
}

.dashboard-page .control-note {
  margin-left: auto;
  font-size: 12px;
}

/* KPI cards stay in a single responsive row where possible */

.dashboard-page .metric-grid {
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 14px;
  margin-bottom: 16px;
}

.dashboard-page .metric-card {
  min-height: 112px;
  padding: 16px;
  border-radius: 12px;
}

.dashboard-page .metric-card-top > span:first-child {
  font-size: 13px;
}

.dashboard-page .metric-value-skeleton {
  margin-top: 10px;
}

.dashboard-page .metric-card-bottom span {
  font-size: 11px;
}

/* Broaden the visual workspace */

.dashboard-page .dashboard-main-grid {
  grid-template-columns: minmax(0, 1.5fr) minmax(300px, 0.9fr);
  align-items: stretch;
  gap: 16px;
  margin-bottom: 16px;
}

.dashboard-page .dashboard-bottom-grid {
  grid-template-columns: minmax(0, 1.5fr) minmax(300px, 0.9fr);
  gap: 16px;
}

.dashboard-page .dashboard-panel {
  min-width: 0;
  padding: 20px;
  border-radius: 13px;
}

.dashboard-page .panel-heading {
  margin-bottom: 14px;
}

.dashboard-page .panel-heading h2 {
  font-size: 21px;
}

.dashboard-page .panel-heading p,
.dashboard-page .dashboard-notice p {
  font-size: 15px;
  line-height: 1.65;
}

.dashboard-page .chart-area {
  min-height: 250px;
}

.dashboard-page .chart-empty-overlay {
  max-width: 220px;
  padding: 17px;
}

.dashboard-page .chart-empty-overlay strong {
  font-size: 14px;
}

.dashboard-page .chart-empty-overlay p {
  font-size: 12px;
  line-height: 1.55;
}

.dashboard-page .ratio-item {
  padding: 13px 0;
}

.dashboard-page .ratio-topline {
  font-size: 13px;
}

.dashboard-page .ratio-item small {
  font-size: 11px;
}

.dashboard-page .statement-row {
  min-height: 58px;
}

.dashboard-page .statement-row strong {
  font-size: 13px;
}

.dashboard-page .statement-row small {
  font-size: 12px;
}

.dashboard-page .dashboard-notice {
  padding: 20px;
  border-radius: 13px;
}

.dashboard-page .dashboard-notice h3 {
  font-size: 15px;
}

.dashboard-page .notice-footer {
  font-size: 12px;
}


/* =========================================================
   EVALUATION
   Make reliability concepts easy to compare at a glance.
   Keep all actual data and existing content unchanged.
   ========================================================= */

.evaluation-page {
  padding-top: 28px;
  padding-bottom: 42px;
}

.evaluation-page .page-title-row {
  margin-bottom: 18px;
}

.evaluation-page .page-title-row h1 {
  font-size: clamp(42px, 4vw, 60px);
}

.evaluation-page .page-title-row p {
  font-size: 17px;
}

/* Summary area: a single clear status band */

.evaluation-page .evaluation-summary {
  display: grid;
  grid-template-columns: 100px minmax(0, 1fr) minmax(270px, 0.8fr);
  align-items: center;
  gap: 24px;
  margin: 0 0 26px;
  padding: 22px 26px;
  border-radius: 14px;
}

.evaluation-page .evaluation-summary-copy h2 {
  margin: 5px 0 8px;
  font-size: 29px;
  line-height: 1.2;
}

.evaluation-page .evaluation-summary-copy p {
  max-width: 760px;
  margin: 0;
  font-size: 15px;
  line-height: 1.65;
}

.evaluation-page .summary-label {
  font-size: 11px;
  letter-spacing: 0.1em;
  text-transform: uppercase;
}

.evaluation-page .evaluation-set-card {
  align-self: stretch;
  display: flex;
  align-items: center;
  gap: 13px;
  padding: 10px 0 10px 22px;
  border-left: 1px solid #d4e3dc;
  background: transparent;
  box-shadow: none;
}

.evaluation-page .evaluation-set-card strong {
  display: block;
  margin-bottom: 6px;
  font-size: 15px;
}

.evaluation-page .evaluation-set-card span:not(.status-pill) {
  font-size: 13px;
  line-height: 1.6;
}

/* Assessment measures: a visual sequence rather than five boxed cards */

.evaluation-page .evaluation-measures {
  width: 100%;
  padding: 16px 0 26px;
}

.evaluation-page .evaluation-measures .section-heading {
  margin-bottom: 18px;
}

.evaluation-page .evaluation-measures .section-heading h2 {
  margin-top: 0;
  font-size: clamp(27px, 2.4vw, 34px);
}

.evaluation-page .evaluation-measures .section-heading p {
  font-size: 16px;
  line-height: 1.6;
}

.evaluation-page .evaluation-card-grid {
  display: grid;
  grid-template-columns: repeat(5, minmax(0, 1fr));
  gap: 0;
  overflow: hidden;
  border-top: 1px solid #dce8e2;
  border-bottom: 1px solid #dce8e2;
  border-radius: 0;
  background: #fff;
}

.evaluation-page .evaluation-measure-card {
  position: relative;
  min-width: 0;
  min-height: 220px;
  padding: 22px 18px;
  border: 0;
  border-right: 1px solid #e0e9e5;
  border-radius: 0;
  background: transparent;
  box-shadow: none;
  transition: background 0.2s ease;
}

.evaluation-page .evaluation-measure-card:last-child {
  border-right: 0;
}

.evaluation-page .evaluation-measure-card:hover {
  transform: none;
  border-color: #e0e9e5;
  background: #f6faf8;
  box-shadow: none;
}

.evaluation-page .measure-top {
  display: flex;
  align-items: center;
  justify-content: flex-start;
  margin-bottom: 17px;
}

.evaluation-page .measure-icon {
  width: 40px;
  height: 40px;
  border-radius: 11px;
}

.evaluation-page .evaluation-measure-card h3 {
  min-height: 0;
  margin: 0 0 10px;
  color: #19332d;
  font-size: 16px;
  line-height: 1.4;
}

.evaluation-page .evaluation-measure-card p {
  min-height: 82px;
  margin: 0;
  color: #657872;
  font-size: 13px;
  line-height: 1.6;
}

.evaluation-page .measure-definition {
  display: block;
  margin-top: 14px;
  color: #82918c;
  font-size: 11px;
  line-height: 1.4;
}

/* Category and flagged review sections */

.evaluation-page .evaluation-lower-grid {
  display: grid;
  grid-template-columns: minmax(0, 1.15fr) minmax(0, 0.85fr);
  align-items: stretch;
  gap: 20px;
  margin-top: 0;
}

.evaluation-page .dashboard-panel {
  min-width: 0;
  padding: 21px;
  border-radius: 13px;
}

.evaluation-page .panel-heading {
  margin-bottom: 16px;
}

.evaluation-page .panel-heading h2 {
  font-size: 20px;
  line-height: 1.35;
}

.evaluation-page .panel-heading p {
  max-width: 700px;
  font-size: 14px;
  line-height: 1.6;
}

/* Keep the category filters, but make them more readable */

.evaluation-page .category-filter {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  margin: 16px 0;
}

.evaluation-page .category-filter button {
  min-height: 34px;
  padding: 8px 12px;
  border-radius: 7px;
  font-size: 12px;
  font-weight: 650;
}

/* Category rows become clean data rows */

.evaluation-page .category-table {
  border-top: 1px solid #e0e9e5;
}

.evaluation-page .category-table-head,
.evaluation-page .category-table-row {
  display: grid;
  grid-template-columns: minmax(0, 1fr);
  align-items: center;
  min-height: 42px;
  padding: 10px 4px;
  border-bottom: 1px solid #e4ece8;
  font-size: 13px;
}

.evaluation-page .category-table-head {
  color: #72827c;
  font-size: 11px;
  font-weight: 750;
  letter-spacing: 0.06em;
  text-transform: uppercase;
}

.evaluation-page .category-table-row {
  color: #254139;
  font-weight: 650;
}

.evaluation-page .category-table-row:hover {
  background: #f6faf8;
}

/* The review queue should read as a status message, not a dashboard tile */

.evaluation-page .flagged-empty {
  display: flex;
  align-items: flex-start;
  gap: 13px;
  padding: 18px 0;
  border-top: 1px solid #e3ebe7;
  border-bottom: 1px solid #e3ebe7;
  background: transparent;
}

.evaluation-page .flagged-empty strong {
  font-size: 14px;
}

.evaluation-page .flagged-empty p {
  margin-top: 5px;
  font-size: 13px;
  line-height: 1.55;
}

.evaluation-page .flagged-placeholder {
  margin-top: 15px;
  padding: 14px 0 0;
  border: 0;
  border-top: 1px dashed #d6e3dc;
  border-radius: 0;
  background: transparent;
}

.evaluation-page .flagged-placeholder small {
  font-size: 11px;
  line-height: 1.5;
}

/* Methodology as a readable full-width explainer */

.evaluation-page .methodology-card {
  display: flex;
  align-items: flex-start;
  gap: 15px;
  margin-top: 18px;
  padding: 21px 23px;
  border: 1px solid #d6e5de;
  border-left: 3px solid #0b9b7b;
  border-radius: 11px;
  background: linear-gradient(105deg, #f0faf5, #f5f9fc);
  box-shadow: none;
}

.evaluation-page .methodology-card h2 {
  margin: 0 0 8px;
  font-size: 20px;
  line-height: 1.4;
}

.evaluation-page .methodology-card p {
  max-width: 1200px;
  margin: 0;
  color: #62746e;
  font-size: 14px;
  line-height: 1.7;
}

/* Hide only redundant pending-status pills within Evaluation.
   No measured results are fabricated or removed. */

.evaluation-page .status-pill {
  display: none;
}


/* =========================================================
   RESPONSIVE BEHAVIOUR
   ========================================================= */

@media (max-width: 1100px) {
  .inner-page {
    width: calc(100% - 48px);
  }

  .ask-layout {
    grid-template-columns: minmax(240px, 280px) minmax(0, 1fr);
  }

  .evaluation-page .evaluation-card-grid {
    grid-template-columns: repeat(3, minmax(0, 1fr));
  }

  .evaluation-page .evaluation-measure-card:nth-child(3) {
    border-right: 0;
  }

  .evaluation-page .evaluation-measure-card:nth-child(n + 4) {
    border-top: 1px solid #e0e9e5;
  }
}

@media (max-width: 850px) {
  .inner-page {
    width: calc(100% - 36px);
    padding-top: 24px;
  }

  .ask-layout,
  .ask-layout.sidebar-collapsed {
    grid-template-columns: minmax(0, 1fr);
  }

  .ask-sidebar {
    max-height: 500px;
  }

  .ask-layout.sidebar-collapsed .ask-sidebar {
    max-height: none;
    padding: 10px;
  }

  .ask-layout.sidebar-collapsed .sidebar-toggle {
    min-height: 38px;
    writing-mode: initial;
  }

  .chat-panel {
    height: 680px;
    min-height: 520px;
  }

  .dashboard-page .dashboard-main-grid,
  .dashboard-page .dashboard-bottom-grid,
  .evaluation-page .evaluation-lower-grid {
    grid-template-columns: minmax(0, 1fr);
  }

  .evaluation-page .evaluation-summary {
    grid-template-columns: 78px minmax(0, 1fr);
  }

  .evaluation-page .evaluation-set-card {
    grid-column: 1 / -1;
    padding: 16px 0 0;
    border-top: 1px solid #d4e3dc;
    border-left: 0;
  }
}

@media (max-width: 620px) {
  .inner-page {
    width: calc(100% - 32px);
    padding-top: 20px;
    padding-bottom: 30px;
  }

  .inner-page .page-title-row {
    margin-bottom: 16px;
    padding-bottom: 14px;
  }

  .inner-page .page-title-row h1 {
    font-size: 39px;
  }

  .inner-page .page-title-row p {
    font-size: 15px;
  }

  .ask-layout,
  .ask-layout.sidebar-collapsed {
    gap: 12px;
  }

  .ask-sidebar {
    max-height: 440px;
    padding: 15px;
  }

  .chat-panel {
    height: 72vh;
    min-height: 470px;
  }

  .chat-content {
    padding: 20px 16px;
  }

  .chat-composer {
    margin: 0 10px 10px;
    padding: 11px;
  }

  .chat-composer textarea {
    min-height: 60px;
    font-size: 14px;
  }

  .ask-page-links {
    gap: 14px;
  }

  .ask-page-links .text-link {
    font-size: 13px;
  }

  .dashboard-page .dashboard-controls {
    align-items: flex-start;
    flex-direction: column;
    gap: 13px;
  }

  .dashboard-page .control-note {
    margin-left: 0;
  }

  .dashboard-page .metric-grid {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }

  .dashboard-page .metric-card {
    min-height: 100px;
    padding: 12px;
  }

  .dashboard-page .dashboard-panel {
    padding: 15px;
  }

  .evaluation-page .evaluation-summary {
    grid-template-columns: minmax(0, 1fr);
    gap: 15px;
    padding: 18px;
  }

  .evaluation-page .gauge-wrap {
    display: none;
  }

  .evaluation-page .evaluation-card-grid {
    grid-template-columns: minmax(0, 1fr);
  }

  .evaluation-page .evaluation-measure-card,
  .evaluation-page .evaluation-measure-card:nth-child(3) {
    min-height: 0;
    padding: 18px 4px;
    border-right: 0;
    border-top: 1px solid #e0e9e5;
  }

  .evaluation-page .evaluation-measure-card:first-child {
    border-top: 0;
  }

  .evaluation-page .evaluation-measure-card p {
    min-height: 0;
  }

  .evaluation-page .methodology-card {
    padding: 17px;
  }

  .evaluation-page .methodology-card h2 {
    font-size: 18px;
  }

  .evaluation-page .methodology-card p {
    font-size: 13px;
  }
}

/* =========================================
   EDITH — VIBRANT COLOUR UPDATE
   Colour changes only. Preserve all layout,
   visuals, animations and transitions.
   ========================================= */

:root {
  --ink: #102c29;
  --ink-soft: #254a43;
  --muted: #536f69;
  --muted-light: #829b94;

  --green: #009f78;
  --green-dark: #007456;
  --green-bright: #00d4a0;

  --blue: #2878f0;
  --blue-bright: #65a7ff;

  --paper: #ffffff;
  --mist: #f2fbf8;
  --line: #d5e9e3;

  --dark: #10352f;
  --dark-soft: #19483f;

  --shadow: 0 20px 55px rgba(13, 73, 58, 0.11);
}

/* Brighter, softly tinted page background */
.home-page {
  background-color: #f8fffc;
}

/* Make the workflow heading accent more vivid */
.roadmap-heading .section-eyebrow {
  color: #009f78;
}

/* Evidence-first workflow label */
.roadmap-stamp {
  color: #176e61;
  border-color: #a9e7d5;
  background: linear-gradient(
    115deg,
    #e1fff2,
    #e5f1ff
  );
}

/* The dotted track */
.roadmap-line {
  background: repeating-linear-gradient(
    90deg,
    #a1dfc9 0,
    #a1dfc9 8px,
    transparent 8px,
    transparent 17px
  );
}

/* Brighter animated progress track.
   Existing animation and timing are unchanged. */
.roadmap-line-progress {
  background: linear-gradient(
    90deg,
    #00b985 0%,
    #16d4b0 36%,
    #328bfa 72%,
    #9267f6 100%
  );

  box-shadow: 0 0 18px rgba(22, 192, 156, 0.35);
}

/* Colourful step markers */
.roadmap-node-number {
  color: #007b60;
  background: linear-gradient(
    145deg,
    #caffdf,
    #d8f4ff
  );

  box-shadow:
    0 0 0 1px #74d8b8,
    0 13px 30px rgba(0, 153, 111, 0.16);
}

/* Step 1 — emerald */
.roadmap-node:nth-child(2) .roadmap-node-number {
  color: #007b60;
  background: linear-gradient(
    140deg,
    #b7ffda,
    #c8fff1
  );
}

.roadmap-node:nth-child(2) .roadmap-node-icon {
  color: #008e6c;
  background: linear-gradient(
    145deg,
    #baffdd,
    #e0fff1
  );
}

.roadmap-node:nth-child(2) .roadmap-pointer {
  border-color: #00a67b;
}

/* Step 2 — electric blue */
.roadmap-node:nth-child(3) .roadmap-node-number {
  color: #245fc5;
  background: linear-gradient(
    140deg,
    #c7e4ff,
    #dcd9ff
  );
}

.roadmap-node:nth-child(3) .roadmap-node-icon {
  color: #276de0;
  background: linear-gradient(
    145deg,
    #c9e3ff,
    #e5eaff
  );
}

.roadmap-node:nth-child(3) .roadmap-pointer {
  border-color: #448af0;
}

/* Step 3 — violet */
.roadmap-node:nth-child(4) .roadmap-node-number {
  color: #7245ce;
  background: linear-gradient(
    140deg,
    #e5d5ff,
    #d6eaff
  );
}

.roadmap-node:nth-child(4) .roadmap-node-icon {
  color: #7650df;
  background: linear-gradient(
    145deg,
    #e6d6ff,
    #e2eaff
  );
}

.roadmap-node:nth-child(4) .roadmap-pointer {
  border-color: #9267f6;
}

/* A brighter selection glow without changing
   the existing hover animation */
.roadmap-node:hover .roadmap-node-number,
.roadmap-node.expanded .roadmap-node-number {
  box-shadow:
    0 0 0 1px #26b996,
    0 0 0 9px rgba(31, 190, 152, 0.13),
    0 16px 35px rgba(25, 125, 104, 0.19);
}

/* More colourful detail separator */
.roadmap-detail {
  border-image: linear-gradient(
    90deg,
    #00b987,
    #478ff5,
    #a17bf7
  ) 1;
}

/* Make the active step label more noticeable */
.roadmap-more {
  color: #009b76;
}

/* Richer accent colours for the feature area */
.feature-number {
  color: #008f70;
}

.feature-card .text-link {
  color: #008f70;
}

.feature-card .text-link:hover {
  color: #286fe4;
}

/* Keep the original dark navigation but add
   a more vivid active underline */
.nav-link::after {
  background: linear-gradient(
    90deg,
    #00e0a7,
    #39a4ff,
    #a879ff
  );
}

/* Brighter primary buttons */
.button-primary {
  background: linear-gradient(
    105deg,
    #009f78,
    #00b995 55%,
    #2788ed
  );
}

.button-primary:hover {
  background: linear-gradient(
    105deg,
    #008b6a,
    #00a985 55%,
    #176fe0
  );
}

/* Give the existing decorative financial
   illustrations a little more colour */
.art-footnote {
  color: #008c70;
}

.art-note small {
  color: #2787d9;
}

.art-active {
  color: #007c63;
}

/* Brighter but still soft page accents */
.hero-note .note-dot {
  background: #00c58d;
  box-shadow: 0 0 10px rgba(0, 197, 141, 0.5);
}

.section-eyebrow {
  color: #008e71;
}

/* A little extra colour in the existing
   lower-page call-to-action */
.bottom-cta {
  background: linear-gradient(
    105deg,
    #103c34,
    #155c4b 45%,
    #204b78
  );
}

.cta-orb {
  color: #9dffe0;
  background: linear-gradient(
    135deg,
    rgba(0, 219, 161, 0.2),
    rgba(84, 148, 255, 0.2)
  );
}

/* ==========================================
   EDITH — VIBRANT FEATURE CARDS + WORKFLOW
   Colour-only overrides for the two sections
   ========================================== */

/* 1. FEATURE CARDS: brighter, distinct colours */

.feature-green {
  background: linear-gradient(
    135deg,
    #d5ffea 0%,
    #e7fff3 48%,
    #faffdf 100%
  );
  border-color: #8ce4b9;
  box-shadow: 0 8px 28px rgba(0, 175, 111, .10);
}

.feature-green .feature-icon {
  color: #007b50;
  background: linear-gradient(135deg, #7df5b4, #b6ffdc);
}

.feature-green .feature-number,
.feature-green .text-link {
  color: #00845a;
}

.feature-green h3 {
  color: #123f2e;
}

.feature-green p {
  color: #426c58;
}

.feature-blue {
  background: linear-gradient(
    135deg,
    #d9eaff 0%,
    #e8e7ff 52%,
    #f5e5ff 100%
  );
  border-color: #a7b9ff;
  box-shadow: 0 8px 28px rgba(87, 104, 230, .11);
}

.feature-blue .feature-icon {
  color: #3b46c9;
  background: linear-gradient(135deg, #a9c9ff, #d5c5ff);
}

.feature-blue .feature-number,
.feature-blue .text-link {
  color: #5245d2;
}

.feature-blue h3 {
  color: #242b68;
}

.feature-blue p {
  color: #58618b;
}

/* Third card: vivid aqua, coral and blue */
.feature-explore {
  color: #173c43;
  border-color: #75d9d1;
  background: linear-gradient(
    135deg,
    #c9fff2 0%,
    #e0f9ff 48%,
    #e5e4ff 100%
  );
  box-shadow: 0 8px 28px rgba(0, 150, 170, .12);
}

.feature-explore .feature-icon {
  color: #007d86;
  background: linear-gradient(
    135deg,
    #79f1d9,
    #a5dcff
  );
}

.feature-explore .feature-number {
  color: #007b8c;
}

.feature-explore h3 {
  color: #173e4b;
}

.feature-explore p {
  color: #4a6976;
}

.feature-explore .text-link {
  color: #007b8c;
}

/* Give the existing chart illustration more colour */
.feature-explore .explore-sparkline {
  color: #008f9b;
}

.feature-explore .explore-sparkline svg path:first-child {
  stroke: #008f9b;
}

.feature-explore .explore-sparkline svg path:last-child {
  stroke: #9b7bff;
  opacity: .55;
}

.feature-explore::after {
  background: radial-gradient(
    circle,
    rgba(255, 111, 156, .27),
    transparent 70%
  );
}

/* Keep hover behaviour, enrich its coloured shadow */
.feature-green:hover {
  box-shadow: 0 24px 48px rgba(0, 164, 105, .20);
}

.feature-blue:hover {
  box-shadow: 0 24px 48px rgba(83, 91, 224, .20);
}

.feature-explore:hover {
  box-shadow: 0 24px 48px rgba(0, 145, 164, .20);
}


/* 2. WORKFLOW: make each step a distinct colour */

/* Keep the dotted line, but use a multicolour gradient */
.roadmap-line {
  background: linear-gradient(
    90deg,
    #00bd81 0%,
    #31d4c3 35%,
    #428bff 68%,
    #a36af5 100%
  );

  -webkit-mask-image: repeating-linear-gradient(
    90deg,
    #000 0 8px,
    transparent 8px 17px
  );

  mask-image: repeating-linear-gradient(
    90deg,
    #000 0 8px,
    transparent 8px 17px
  );
}

/* Step 1: emerald */
.roadmap-node:nth-child(2) .roadmap-node-number {
  color: #006b48;
  background: linear-gradient(
    145deg,
    #7af0b5,
    #c6ffdf
  );
  box-shadow:
    0 0 0 1px #22c68a,
    0 13px 30px rgba(0, 167, 106, .22);
}

.roadmap-node:nth-child(2) .roadmap-node-icon {
  color: #007e58;
  background: linear-gradient(
    145deg,
    #a1ffd0,
    #d5ffdf
  );
  box-shadow: 0 10px 25px rgba(0, 167, 106, .15);
}

.roadmap-node:nth-child(2) .roadmap-more {
  color: #009c67;
}

/* Step 2: electric blue */
.roadmap-node:nth-child(3) .roadmap-node-number {
  color: #244fc1;
  background: linear-gradient(
    145deg,
    #8fc6ff,
    #d5e2ff
  );
  box-shadow:
    0 0 0 1px #5795ff,
    0 13px 30px rgba(57, 120, 240, .22);
}

.roadmap-node:nth-child(3) .roadmap-node-icon {
  color: #2864db;
  background: linear-gradient(
    145deg,
    #a6d1ff,
    #d9e4ff
  );
  box-shadow: 0 10px 25px rgba(57, 120, 240, .15);
}

.roadmap-node:nth-child(3) .roadmap-more {
  color: #326fe2;
}

/* Step 3: violet */
.roadmap-node:nth-child(4) .roadmap-node-number {
  color: #6d35bd;
  background: linear-gradient(
    145deg,
    #d5a5ff,
    #f0d9ff
  );
  box-shadow:
    0 0 0 1px #b17af2,
    0 13px 30px rgba(143, 79, 219, .22);
}

.roadmap-node:nth-child(4) .roadmap-node-icon {
  color: #8545d4;
  background: linear-gradient(
    145deg,
    #e3baff,
    #f2ddff
  );
  box-shadow: 0 10px 25px rgba(143, 79, 219, .15);
}

.roadmap-node:nth-child(4) .roadmap-more {
  color: #8545d4;
}

/* More visible active-step glow, retaining the
   existing scale and hover transitions */
.roadmap-node:nth-child(2):hover .roadmap-node-number,
.roadmap-node:nth-child(2).expanded .roadmap-node-number {
  box-shadow:
    0 0 0 1px #00a970,
    0 0 0 10px rgba(0, 198, 126, .18),
    0 16px 35px rgba(0, 167, 106, .25);
}

.roadmap-node:nth-child(3):hover .roadmap-node-number,
.roadmap-node:nth-child(3).expanded .roadmap-node-number {
  box-shadow:
    0 0 0 1px #428bff,
    0 0 0 10px rgba(66, 139, 255, .18),
    0 16px 35px rgba(57, 120, 240, .25);
}

.roadmap-node:nth-child(4):hover .roadmap-node-number,
.roadmap-node:nth-child(4).expanded .roadmap-node-number {
  box-shadow:
    0 0 0 1px #9b60e8,
    0 0 0 10px rgba(155, 96, 232, .18),
    0 16px 35px rgba(143, 79, 219, .25);
}

/* Colourful selected-step detail separator */
.roadmap-node:nth-child(2) .roadmap-detail {
  border-color: #00ad77;
}

.roadmap-node:nth-child(3) .roadmap-detail {
  border-color: #428bff;
}

.roadmap-node:nth-child(4) .roadmap-detail {
  border-color: #9b60e8;
}

/* Landing page: subtle blue-to-green section dividers */

.home-page .feature-section,
.home-page .roadmap-section,
.home-page .tata-feature {
  position: relative;
}

.home-page .feature-section::before,
.home-page .roadmap-section::before,
.home-page .tata-feature::before {
  content: "";
  position: absolute;
  top: 0;
  left: 50%;
  transform: translateX(-50%);
  width: min(88%, 1100px);
  height: 2px;
  border-radius: 999px;

  background: linear-gradient(
    90deg,
    transparent 0%,
    #78baff 18%,
    #45c9ce 50%,
    #48d6a0 82%,
    transparent 100%
  );

  opacity: 0.7;
  box-shadow: 0 0 10px rgba(65, 184, 193, 0.12);
  pointer-events: none;
}

/* ==========================================
   ASK EDITH — SIDEBAR AND TEXT IMPROVEMENTS
   ========================================== */

/* Give the sidebar its own full-height column */
@media (min-width: 901px) {
  .ask-page .ask-layout {
    grid-template-columns: minmax(300px, 26%) minmax(0, 1fr);
    align-items: stretch;
    gap: 18px;
  }

  .ask-page .ask-sidebar {
    align-self: stretch;
    height: 100%;
    min-height: 100%;
    display: flex;
    flex-direction: column;
  }

  .ask-page .ask-layout.sidebar-collapsed {
    grid-template-columns: 54px minmax(0, 1fr);
  }
}

/* Keep the existing hide/show button */
.ask-page .sidebar-toggle {
  flex: 0 0 auto;
}

/* New conversation button inside the sidebar */
.ask-page .sidebar-new-conversation {
  display: flex;
  align-items: center;
  justify-content: flex-start;
  gap: 10px;
  width: 100%;
  min-height: 44px;
  margin: 0 0 20px;
  padding: 11px 13px;
  border: 1px solid rgba(126, 227, 195, .35);
  border-radius: 8px;
  color: #f1fff8;
  background: linear-gradient(
    110deg,
    rgba(17, 165, 126, .30),
    rgba(63, 139, 217, .20)
  );
  font-size: 14px;
  font-weight: 750;
  text-align: left;
  cursor: pointer;
  transition:
    background .22s ease,
    border-color .22s ease,
    transform .22s ease,
    box-shadow .22s ease;
}

.ask-page .sidebar-new-conversation:hover {
  border-color: rgba(126, 227, 195, .75);
  background: linear-gradient(
    110deg,
    rgba(17, 165, 126, .48),
    rgba(63, 139, 217, .34)
  );
  box-shadow: 0 7px 18px rgba(0, 0, 0, .13);
  transform: translateY(-1px);
}

.ask-page .sidebar-new-conversation svg {
  flex: 0 0 auto;
  color: #91f0cd;
}

/* Hide the old button in the chat header */
.ask-page .chat-panel-header > .new-chat {
  display: none;
}

/* The collapsed sidebar retains only its toggle */
.ask-page .ask-layout.sidebar-collapsed
.sidebar-new-conversation {
  display: none;
}

/* Allow the sidebar to use the full available panel height */
.ask-page .sidebar-info {
  margin-top: auto;
}

/* Make explanatory text more readable */
.ask-page .page-title-row p {
  font-size: 18px;
  line-height: 1.7;
}

.ask-page .sidebar-heading p {
  font-size: 15px;
  line-height: 1.6;
}

.ask-page .suggestion-item strong {
  font-size: 15px;
  line-height: 1.55;
}

.ask-page .sidebar-info-row {
  font-size: 14px;
  line-height: 1.6;
}

.ask-page .sidebar-info-title {
  font-size: 14px;
}

.ask-page .recent-question {
  font-size: 14px;
  line-height: 1.5;
}

.ask-page .recent-empty {
  font-size: 13px;
  line-height: 1.6;
}

.ask-page .welcome-message p {
  font-size: 16px;
  line-height: 1.75;
}

.ask-page .welcome-callout {
  font-size: 14px;
  line-height: 1.65;
}

.ask-page .assistant-message-body p {
  font-size: 16px;
  line-height: 1.75;
}

.ask-page .evidence-placeholder small {
  font-size: 13px;
  line-height: 1.6;
}

/* Keep the mobile layout stacked and usable */
@media (max-width: 900px) {
  .ask-page .ask-sidebar {
    align-self: stretch;
    width: 100%;
  }

  .ask-page .sidebar-new-conversation {
    margin-bottom: 18px;
  }
}

@media (max-width: 620px) {
  .ask-page .page-title-row p {
    font-size: 16px;
  }

  .ask-page .welcome-message p,
  .ask-page .assistant-message-body p {
    font-size: 15px;
  }
}
/* Matching medium-dark analytical gradient for the two panels */
.dashboard-panel.statement-panel,
.dashboard-notice {
  background: linear-gradient(
    120deg,
    #104f49 0%,
    #164568 100%
  ) !important;

  border-color: #328e8b;
  color: #f4fffc;
}

/* Keep the text readable on the dark background */
.statement-panel .panel-heading h2,
.dashboard-notice h3 {
  color: #f4fffc;
}

.statement-panel .panel-heading p,
.statement-panel .statement-row small,
.dashboard-notice p {
  color: #d1e7e7;
}

/* Subtle dividers */
.statement-panel .statement-row {
  border-bottom-color: rgba(215, 245, 241, 0.2);
}

/* Preserve the teal accent on the notice panel */
.dashboard-notice {
  border-left: 3px solid #20c997;
}

/* Keep the existing icons visible */
.statement-panel .statement-icon,
.dashboard-notice .notice-icon {
  background: #dff5ec;
  color: #087f70;
}

/* =========================================================
   EDITH — LIVE DATA (task 04)
   Additions only. Everything below reuses the variables,
   colours, radii and card language defined above.
   ========================================================= */

/* ---------- Shared value markers ---------- */

.restated-mark {
  display: inline-grid;
  place-items: center;
  width: 14px;
  height: 14px;
  margin-left: 3px;
  border: 1px solid #e9d7a8;
  border-radius: 4px;
  color: #85601e;
  background: #fffaf0;
  font-size: 8px;
  font-weight: 800;
  line-height: 1;
  vertical-align: super;
  cursor: help;
}

.value-missing {
  color: var(--muted-light);
  cursor: help;
}

.mini-sparkline {
  flex: 0 0 auto;
  overflow: visible;
}

.mini-sparkline circle {
  fill: #fff;
  stroke: var(--blue);
  stroke-width: 1.4;
}

.zone-chip {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  width: fit-content;
  padding: 3px 8px;
  border: 1px solid var(--line);
  border-radius: 999px;
  color: var(--muted);
  background: var(--mist);
  font-size: 11px;
  font-weight: 700;
  line-height: 1.4;
  white-space: nowrap;
}

.zone-chip::before {
  width: 6px;
  height: 6px;
  border-radius: 50%;
  background: currentColor;
  content: "";
}

.zone-chip.safe {
  border-color: #a9e7d5;
  color: var(--green-dark);
  background: #e6f8f0;
}

.zone-chip.grey {
  border-color: #e9d7a8;
  color: #85601e;
  background: #fffaf0;
}

.zone-chip.distress {
  border-color: #f0c3ad;
  color: #a4431b;
  background: #fff1ea;
}

.status-pill.verified {
  border-color: #a9e7d5;
  color: var(--green-dark);
  background: #e6f8f0;
}

.status-pill.verified::before { background: var(--green); }

.status-pill.partial {
  border-color: #e9d7a8;
  color: #85601e;
  background: #fffaf0;
}

.status-pill.neutral {
  border-color: var(--line);
  color: var(--muted);
  background: var(--mist);
}

.status-pill.neutral::before { background: var(--muted-light); }

.load-error {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 10px;
  margin: 0 0 16px;
  padding: 14px 16px;
  border: 1px solid #e7e9e2;
  border-left: 3px solid #d2a047;
  border-radius: 9px;
  color: #6f6040;
  background: #faf9f5;
  font-size: 14px;
  line-height: 1.5;
}

.load-error svg { flex: 0 0 auto; color: #a5792c; }
.load-error .text-link { margin-left: auto; }
.load-error.compact { margin: 14px 0 0; font-size: 13px; }


/* ---------- Header: live backend status ---------- */

.header-actions {
  justify-self: end;
  display: flex;
  align-items: center;
  gap: 14px;
}

.backend-status {
  display: inline-flex;
  align-items: center;
  gap: 7px;
  color: #b9c7c2;
  font-size: 12px;
  font-weight: 700;
  white-space: nowrap;
  cursor: default;
}

.backend-status i {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background: #7f918b;
}

.backend-status.live { color: #d9f5ea; }

.backend-status.live i {
  background: var(--green-bright);
  box-shadow: 0 0 0 3px rgba(0, 212, 160, .18), 0 0 10px rgba(0, 212, 160, .55);
  animation: statusPulse 2.4s ease-in-out infinite;
}

.backend-status.degraded i { background: #d69a30; }

@keyframes statusPulse {
  0%, 100% { box-shadow: 0 0 0 3px rgba(0, 212, 160, .18), 0 0 10px rgba(0, 212, 160, .45); }
  50% { box-shadow: 0 0 0 5px rgba(0, 212, 160, .08), 0 0 14px rgba(0, 212, 160, .7); }
}


/* ---------- Home: wordmark anchored to the hero art card ---------- */

.steel-data-core .tata-wordmark {
  top: clamp(14px, 6%, 30px);
  left: clamp(16px, 6.5%, 36px);
  animation: none;
}


/* ---------- Home: at a glance + try asking ---------- */

.glance-section {
  padding-top: 64px;
  padding-bottom: 56px;
  background: linear-gradient(180deg, #fff, #f6fcf9);
}

.glance-section .section-heading { margin-bottom: 24px; }

.glance-section .section-heading h2 {
  max-width: none;
  font-size: clamp(30px, 3vw, 44px);
}

.glance-grid {
  display: grid;
  grid-template-columns: repeat(5, minmax(0, 1fr));
  gap: 14px;
}

.metric-card.glance-tile {
  display: flex;
  flex-direction: column;
  min-height: 170px;
  padding: 18px;
  border-radius: 12px;
  cursor: default;
}

.glance-tile .metric-card-top > span:first-child { font-size: 13px; }

.metric-value {
  display: flex;
  align-items: baseline;
  flex-wrap: wrap;
  gap: 4px;
  margin: 14px 0 12px;
  color: #142a26;
  font-size: clamp(20px, 1.7vw, 25px);
  font-weight: 800;
  letter-spacing: -.035em;
  line-height: 1.15;
}

.metric-value small {
  color: var(--muted);
  font-size: 12px;
  font-weight: 700;
  letter-spacing: 0;
}

.glance-tile .metric-card-bottom { min-height: 34px; }

.glance-source {
  display: block;
  margin-top: auto;
  padding-top: 10px;
  color: var(--muted-light);
  font-size: 11px;
  line-height: 1.45;
}

.try-asking {
  display: flex;
  align-items: flex-start;
  gap: 16px;
  margin-top: 26px;
}

.try-asking-label {
  display: inline-flex;
  align-items: center;
  flex: 0 0 auto;
  gap: 7px;
  padding-top: 9px;
  color: var(--green);
  font-size: 12px;
  font-weight: 800;
  letter-spacing: .12em;
  text-transform: uppercase;
}

.try-asking-chips {
  display: flex;
  flex-wrap: wrap;
  gap: 9px;
}

.question-chip {
  max-width: 440px;
  padding: 9px 14px;
  border: 1px solid #cfe6dd;
  border-radius: 999px;
  color: var(--green-dark);
  background: #fff;
  font-size: 13px;
  font-weight: 650;
  line-height: 1.4;
  text-align: left;
  cursor: pointer;
  transition: border-color .2s ease, background .2s ease, transform .2s ease, box-shadow .2s ease;
}

.question-chip:hover {
  border-color: var(--green-bright);
  background: linear-gradient(110deg, #e6fff4, #eaf3ff);
  box-shadow: 0 8px 18px rgba(0, 159, 120, .12);
  transform: translateY(-2px);
}


/* ---------- Ask Edith: real conversation ---------- */

.ask-page .suggestion-list {
  flex: 0 0 auto;
  max-height: 430px;
  overflow-y: auto;
  scrollbar-width: thin;
  scrollbar-color: #527a6d transparent;
}

.ask-page .suggestion-item { flex-shrink: 0; min-height: 0; }

.suggestion-item small {
  grid-column: 1;
  color: #f3c98b;
  font-size: 12px;
  font-weight: 650;
}

.suggestion-item:disabled {
  opacity: .55;
  cursor: wait;
}

.follow-up-hint {
  display: flex;
  align-items: flex-start;
  gap: 9px;
  width: 100%;
  margin-top: 14px;
  padding: 11px 12px;
  border: 1px dashed rgba(126, 227, 195, .4);
  border-radius: 8px;
  color: #cfe7de;
  background: rgba(255, 255, 255, .04);
  font-size: 13px;
  line-height: 1.5;
  text-align: left;
  cursor: pointer;
}

.follow-up-hint svg { flex: 0 0 auto; margin-top: 2px; color: #91f0cd; }
.follow-up-hint b { color: #fff; }
.follow-up-hint:hover { border-color: rgba(126, 227, 195, .75); background: rgba(255, 255, 255, .08); }
.ask-layout.sidebar-collapsed .follow-up-hint { display: none; }

.welcome-callout ul {
  display: grid;
  gap: 5px;
  margin: 0;
  padding-left: 18px;
}

.conversation-turn {
  display: grid;
  gap: 18px;
}

.answer-meta {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 10px;
  margin-bottom: 10px;
}

.answer-meta > span:first-child {
  color: #0c8a70;
  font-size: 12px;
  font-weight: 800;
}

.answer-meta .status-pill { font-size: 12px; }

.answer-action {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  margin-left: auto;
  padding: 6px 10px;
  border: 1px solid #d6e5de;
  border-radius: 7px;
  color: #34584e;
  background: #fff;
  font-size: 12px;
  font-weight: 700;
  cursor: pointer;
  transition: border-color .2s ease, background .2s ease;
}

.answer-action:hover { border-color: #75bda7; background: #f0faf5; }

.verification-partial {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.verification-partial small {
  color: #85601e;
  font-size: 12px;
}

.answer-warnings {
  display: grid;
  gap: 6px;
  margin: 0 0 12px;
  padding: 10px 12px;
  border: 1px solid #efdbb4;
  border-radius: 8px;
  color: #6f5520;
  background: #fffaf0;
  font-size: 13px;
  line-height: 1.5;
  list-style: none;
}

.answer-warnings li { display: flex; gap: 7px; }
.answer-warnings svg { flex: 0 0 auto; margin-top: 2px; color: #a5792c; }

.answer-markdown {
  color: #2a423c;
  font-size: 15px;
  line-height: 1.75;
  overflow-wrap: anywhere;
}

.answer-markdown > :first-child { margin-top: 0; }
.answer-markdown > :last-child { margin-bottom: 0; }
.answer-markdown p { margin: 0 0 12px; color: #2a423c; }
.answer-markdown strong { color: #142a26; }
.answer-markdown ul,
.answer-markdown ol { margin: 0 0 12px; padding-left: 22px; }
.answer-markdown li { margin-bottom: 4px; }

.answer-markdown h1,
.answer-markdown h2,
.answer-markdown h3,
.answer-markdown h4 {
  margin: 18px 0 8px;
  color: #18312b;
  font-size: 17px;
  letter-spacing: -.02em;
}

.answer-markdown a { color: var(--blue); text-decoration: underline; }

.answer-markdown code {
  padding: 1px 5px;
  border-radius: 4px;
  background: var(--mist);
  font-size: .9em;
}

.answer-markdown blockquote {
  margin: 0 0 12px;
  padding: 4px 14px;
  border-left: 3px solid var(--green-bright);
  color: var(--muted);
}

.answer-table-wrap {
  max-width: 100%;
  margin: 4px 0 14px;
  overflow-x: auto;
  border: 1px solid #dfe8e4;
  border-radius: 9px;
  scrollbar-width: thin;
}

.answer-table-wrap table,
.data-table {
  width: 100%;
  border-collapse: collapse;
  font-size: 13px;
  font-variant-numeric: tabular-nums;
}

.answer-table-wrap th,
.answer-table-wrap td {
  padding: 8px 12px;
  border-bottom: 1px solid #edf1ef;
  text-align: left;
  white-space: nowrap;
}

.answer-table-wrap th {
  color: #4c655e;
  background: linear-gradient(100deg, #f5faf7, #f5f8fc);
  font-size: 12px;
  font-weight: 750;
}

.answer-table-wrap tr:last-child td { border-bottom: 0; }
.answer-table-wrap tbody tr:hover { background: #f6faf8; }

.evidence-citations .evidence-placeholder-top { margin-bottom: 10px; }
.ask-page .evidence-placeholder-top > span { font-size: 13px; }

.citation-list {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}

.citation-chip {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 6px 10px;
  border: 1px solid #cfe6dd;
  border-radius: 7px;
  color: var(--green-dark);
  background: #fff;
  font-size: 12px;
  font-weight: 700;
  line-height: 1.35;
  transition: border-color .2s ease, background .2s ease, color .2s ease;
}

.citation-chip:hover {
  border-color: var(--blue-bright);
  color: var(--blue);
  background: #f2f7ff;
}

.citation-chip svg:last-child { opacity: .6; }

.answer-steps {
  margin-top: 12px;
  border: 1px solid #e2ebe6;
  border-radius: 8px;
  background: #fbfdfc;
}

.answer-steps summary {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 10px 13px;
  color: #34584e;
  font-size: 13px;
  font-weight: 700;
  cursor: pointer;
  list-style: none;
}

.answer-steps summary::-webkit-details-marker { display: none; }

.answer-steps summary::after {
  margin-left: auto;
  color: var(--muted-light);
  content: "+";
  font-size: 16px;
}

.answer-steps[open] summary::after { content: "−"; }

.answer-steps ol {
  display: grid;
  gap: 7px;
  margin: 0;
  padding: 2px 16px 10px 36px;
  color: #4c655e;
  font-size: 13px;
  line-height: 1.5;
}

.answer-steps li b {
  display: inline-block;
  margin-right: 7px;
  padding: 0 6px;
  border-radius: 4px;
  color: var(--green-dark);
  background: #e6f8f0;
  font-family: "Courier New", monospace;
  font-size: 11px;
}

.answer-steps p { margin: 0; padding: 0 13px 10px; color: var(--muted); font-size: 13px; }

.answer-steps small {
  display: block;
  padding: 9px 13px;
  border-top: 1px solid #e8efeb;
  color: var(--muted-light);
  font-size: 12px;
}

.typing-dots {
  display: inline-flex;
  gap: 5px;
  margin: 6px 0 2px;
}

.typing-dots i {
  width: 7px;
  height: 7px;
  border-radius: 50%;
  background: linear-gradient(135deg, var(--green-bright), var(--blue-bright));
  animation: typingDot 1.2s ease-in-out infinite;
}

.typing-dots i:nth-child(2) { animation-delay: .15s; }
.typing-dots i:nth-child(3) { animation-delay: .3s; }

@keyframes typingDot {
  0%, 80%, 100% { opacity: .35; transform: translateY(0); }
  40% { opacity: 1; transform: translateY(-4px); }
}

.pending-elapsed {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  color: var(--muted);
  font-size: 13px;
  font-weight: 700;
  font-variant-numeric: tabular-nums;
}

.pending-footer {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  margin-top: 12px;
}

.pending-footer small { margin-top: 0 !important; }

.button.pending-cancel {
  min-height: 34px;
  padding: 7px 13px;
  font-size: 12px;
}

.answer-error {
  display: flex;
  align-items: flex-start;
  gap: 9px;
  margin-top: 6px;
  padding: 12px 14px;
  border: 1px solid #e7e9e2;
  border-left: 3px solid #d2a047;
  border-radius: 8px;
  background: #faf9f5;
}

.answer-error svg { flex: 0 0 auto; margin-top: 3px; color: #a5792c; }
.ask-page .answer-error p { margin: 0; color: #6f6040; font-size: 14px; line-height: 1.6; }
.answer-retry { margin-top: 10px; }


/* ---------- Dashboard ---------- */

.dashboard-page .metric-value { margin: 10px 0 10px; }

.metric-change {
  display: inline-flex;
  align-items: center;
  font-weight: 750;
}

.metric-change.up { color: var(--green-dark); }
.metric-change.down { color: #a4431b; }

.chart-area.chart-live { padding-left: 74px; }

.chart-y-labels.chart-y-live {
  top: 0;
  bottom: 0;
  width: 66px;
  display: block;
}

.chart-y-live span {
  position: absolute;
  right: 0;
  transform: translateY(-50%);
  font-size: 11px;
  white-space: nowrap;
}

.chart-plot {
  position: relative;
  height: 100%;
}

.chart-zero-line {
  stroke: #b8cbc4;
  stroke-width: 1;
  vector-effect: non-scaling-stroke;
}

.chart-live .chart-line-animated {
  stroke-dasharray: 2400;
  stroke-dashoffset: 2400;
  animation: drawChart 1.8s .15s ease forwards;
}

.chart-point {
  position: absolute;
  z-index: 2;
  width: 14px;
  height: 14px;
  padding: 0;
  border: 2.5px solid #0d9d79;
  border-radius: 50%;
  background: #fff;
  box-shadow: 0 2px 6px rgba(13, 73, 58, .18);
  transform: translate(-50%, -50%);
  cursor: pointer;
  transition: transform .18s ease, box-shadow .18s ease;
}

.chart-point.latest { border-color: #4b88df; }

.chart-point:hover,
.chart-point.active,
.chart-point:focus-visible {
  box-shadow: 0 0 0 6px rgba(13, 157, 121, .15), 0 4px 10px rgba(13, 73, 58, .2);
  transform: translate(-50%, -50%) scale(1.2);
}

.chart-tooltip {
  position: absolute;
  z-index: 3;
  display: flex;
  flex-direction: column;
  gap: 3px;
  min-width: 170px;
  max-width: 260px;
  padding: 10px 12px;
  border: 1px solid #dce8e3;
  border-radius: 9px;
  background: rgba(255, 255, 255, .97);
  box-shadow: 0 12px 28px rgba(17, 56, 46, .14);
  transform: translate(-50%, calc(-100% - 16px));
  pointer-events: none;
}

.chart-tooltip.align-right { transform: translate(calc(-100% + 24px), calc(-100% - 16px)); }
.chart-tooltip small { color: var(--muted-light); font-size: 11px; font-weight: 700; }
.chart-tooltip strong { color: #142a26; font-size: 15px; }
.chart-tooltip span { color: var(--muted); font-size: 11px; line-height: 1.4; }

.chart-x-labels.chart-x-live {
  display: block;
  padding-left: 74px;
}

.chart-x-track {
  position: relative;
  height: 18px;
  margin-top: 6px;
}

.chart-x-track span {
  position: absolute;
  top: 0;
  transform: translateX(-50%);
  font-size: 11px;
  white-space: nowrap;
}

.ratio-footline {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
}

.ratio-track i.negative { background: linear-gradient(90deg, #d69a30, #e9b870); }
.metric-value-skeleton.ratio-skeleton { width: 60%; height: 14px; margin: 0; }

.dashboard-page .ratio-topline strong { color: #142a26; font-size: 15px; }

.dashboard-page .dashboard-insight-grid { margin-bottom: 16px; }

.table-scroll {
  max-width: 100%;
  margin-top: 4px;
  overflow-x: auto;
  scrollbar-width: thin;
}

.data-table th,
.data-table td {
  padding: 10px 12px;
  border-bottom: 1px solid #edf1ef;
  text-align: right;
  white-space: nowrap;
}

.data-table thead th {
  color: #72827c;
  font-size: 11px;
  font-weight: 750;
  letter-spacing: .06em;
  text-transform: uppercase;
}

.data-table tbody th {
  color: #254139;
  font-weight: 700;
  text-align: left;
}

.data-table thead th:first-child { text-align: left; }
.data-table tbody tr:hover { background: #f6faf8; }
.data-table td.negative { color: #a4431b; }
.data-table td { padding-right: 22px; }
.data-table td .restated-mark { margin-right: -17px; }
.dashboard-page .segments-panel .panel-footnote { display: block; }

.scores-table tbody th {
  min-width: 220px;
  white-space: normal;
}

.scores-table tbody th strong { display: block; font-size: 14px; }

.scores-table tbody th small {
  display: block;
  margin-top: 3px;
  color: var(--muted);
  font-size: 12px;
  font-weight: 500;
  line-height: 1.45;
}

.scores-table td b {
  display: block;
  margin-bottom: 5px;
  color: #142a26;
  font-size: 14px;
}

.scores-table td .zone-chip { margin-left: auto; }
.segments-table tbody th { min-width: 210px; }
.segments-table .subtotal-row th,
.segments-table .subtotal-row td { color: var(--muted); font-weight: 500; }

.segments-table .total-row th,
.segments-table .total-row td {
  border-top: 1.5px solid #cfe0d9;
  border-bottom: 0;
  color: #142a26;
  font-weight: 800;
}

.dashboard-page .panel-footnote {
  display: flex;
  align-items: baseline;
  flex-wrap: wrap;
  gap: 4px 12px;
  margin: 14px 0 0;
  color: var(--muted);
  font-size: 13px;
  line-height: 1.6;
}

.panel-footnote .text-link { font-size: 13px; }

.health-list {
  display: grid;
  margin: 0 0 18px;
  padding: 0;
  list-style: none;
}

.health-list li {
  display: grid;
  grid-template-columns: minmax(0, 1fr) auto;
  align-items: center;
  gap: 4px 12px;
  padding: 11px 0;
  border-bottom: 1px solid #edf1ef;
}

.health-list li > span:first-child { color: #586d66; font-size: 14px; font-weight: 650; }
.health-list li strong { color: #142a26; font-size: 15px; text-align: right; }
.health-list .zone-chip { grid-column: 2; justify-self: end; }
.health-ask { width: 100%; }

.segments-panel { margin-bottom: 16px; }
.segments-panel .panel-heading { align-items: center; }
.segments-panel .segmented-control { flex: 0 0 auto; }

.report-links {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  margin-top: 6px;
}

.report-links a {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  padding: 3px 8px;
  border: 1px solid rgba(215, 245, 241, .3);
  border-radius: 6px;
  color: #eafffa;
  background: rgba(255, 255, 255, .08);
  font-size: 12px;
  font-weight: 700;
  transition: background .2s ease, border-color .2s ease;
}

.report-links a:hover { border-color: #20c997; background: rgba(32, 201, 151, .2); }
.statement-panel .load-error { color: #6f6040; }


/* ---------- Evaluation ---------- */

.evaluation-gauge[data-live] {
  background: conic-gradient(
    from 220deg,
    #0d9d79 0 var(--gauge-fill),
    #dce8e2 var(--gauge-fill) 100%
  );
}

.evaluation-page .gauge-center strong {
  color: #142a26;
  font-size: 20px;
}

.measure-value {
  display: block;
  margin-top: 14px;
  color: #142a26;
  font-size: 26px;
  font-weight: 800;
  letter-spacing: -.035em;
  line-height: 1.1;
}

.evaluation-page .measure-value + .measure-definition { margin-top: 6px; color: var(--muted); }

.evaluation-page .category-table .category-results-row {
  grid-template-columns: minmax(0, 1fr) 90px 90px;
}

.evaluation-page .category-table .category-question-row {
  grid-template-columns: minmax(0, 1fr) 72px 88px 78px 52px;
  gap: 10px;
}

.category-results-row > span:not(:first-child),
.category-question-row > span:not(:first-child) { text-align: right; }

.category-question-row > span:first-child { font-weight: 550; line-height: 1.5; }
.category-question-row > span:first-child b { color: var(--green); }
.result-pass { color: var(--green-dark); font-weight: 800; }
.result-partial { color: #a4431b; font-weight: 800; }

.evaluation-page .flagged-item + .flagged-item { border-top: 0; }

.flagged-grade {
  display: block;
  margin: 5px 0 0;
  color: #85601e;
  font-size: 12px;
  font-weight: 750;
}


/* ---------- Sources ---------- */

.sources-block { margin-top: 34px; }

.sources-page .section-heading { margin-bottom: 18px; }

.sources-page .section-heading h2 {
  font-size: clamp(27px, 2.4vw, 36px);
}

.sources-page .section-heading p { font-size: 16px; }

.report-grid {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 14px;
}

.dashboard-panel.report-card {
  display: flex;
  align-items: flex-start;
  gap: 12px;
  transition: transform .22s ease, box-shadow .22s ease, border-color .22s ease;
}

a.report-card:hover {
  border-color: #9bcbb9;
  box-shadow: 0 10px 24px rgba(18, 62, 50, .08);
  transform: translateY(-3px);
}

.report-card > div {
  display: flex;
  flex: 1;
  flex-direction: column;
  gap: 5px;
  min-width: 0;
}

.report-card > svg { flex: 0 0 auto; color: var(--muted-light); }
.report-year { color: var(--green); font-size: 12px; font-weight: 800; letter-spacing: .08em; }
.report-card strong { color: #142a26; font-size: 15px; line-height: 1.4; }
.report-card small { color: var(--muted); font-size: 12px; }

.evaluation-card-grid.pipeline-grid {
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 14px;
}

.pipeline-grid .evaluation-measure-card h3 { min-height: 0; font-size: 16px; }
.pipeline-grid .evaluation-measure-card p { min-height: 0; font-size: 14px; }

.pipeline-number {
  color: var(--muted-light);
  font-family: Georgia, serif;
  font-size: 20px;
  font-style: italic;
}

.sources-two-up {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 14px;
}

.sources-two-up .methodology-card { margin-top: 0; }
.sources-page .methodology-card p { font-size: 14px; }
.sources-note { margin-top: 14px; }
.limitations-panel { margin-top: 34px; }

.limitations-list {
  display: grid;
  gap: 10px;
  margin: 16px 0 18px;
  padding: 0;
  list-style: none;
}

.limitations-list li {
  display: flex;
  gap: 9px;
  color: #3e5a50;
  font-size: 15px;
  line-height: 1.6;
}

.limitations-list svg { flex: 0 0 auto; margin-top: 4px; color: #a5792c; }


/* ---------- Responsive ---------- */

@media (max-width: 1100px) {
  .glance-grid { grid-template-columns: repeat(3, minmax(0, 1fr)); }
  .report-grid { grid-template-columns: repeat(2, minmax(0, 1fr)); }
  .evaluation-card-grid.pipeline-grid { grid-template-columns: repeat(2, minmax(0, 1fr)); }
}

@media (max-width: 850px) {
  .backend-status { font-size: 0; gap: 0; }
  .backend-status i { width: 9px; height: 9px; }
  .try-asking { flex-direction: column; gap: 10px; }
  .sources-two-up { grid-template-columns: 1fr; }
  .segments-panel .panel-heading { align-items: flex-start; flex-direction: column; }
}

@media (max-width: 620px) {
  .header-actions { gap: 10px; }
  .glance-grid { grid-template-columns: repeat(2, minmax(0, 1fr)); }
  .report-grid,
  .evaluation-card-grid.pipeline-grid { grid-template-columns: 1fr; }
  .chart-area.chart-live,
  .chart-x-labels.chart-x-live { padding-left: 58px; }
  .chart-y-labels.chart-y-live { width: 52px; }
  .chart-y-live span,
  .chart-x-track span { font-size: 9px; }
  .evaluation-page .category-table .category-question-row {
    grid-template-columns: minmax(0, 1fr) 60px 60px;
  }
  .category-question-row > span:nth-child(3),
  .category-question-row > span:nth-child(5) { display: none; }
  .answer-action { margin-left: 0; }
}

@media (prefers-reduced-motion: reduce) {
  .backend-status.live i,
  .typing-dots i,
  .chart-live .chart-line-animated { animation: none; stroke-dashoffset: 0; }
}


/* =========================================================
   EDITH: UI REVIEW CHANGES (task 06)
   Additions only, appended after everything else. Reuses her
   variables, gradients, card styles and accent colours.
   ========================================================= */

/* ---------- Shared: n/a values and the FY2021-22 marker ---------- */

.comparative-mark {
  display: inline-grid;
  place-items: center;
  width: 13px;
  height: 13px;
  margin-left: 3px;
  border: 1px solid #bcd2f2;
  border-radius: 50%;
  color: #3869b8;
  background: #eef4fd;
  font-family: Georgia, serif;
  font-size: 9px;
  font-style: italic;
  font-weight: 800;
  line-height: 1;
  vertical-align: super;
  cursor: help;
}

.select-control {
  display: inline-flex;
  align-items: center;
  gap: 8px;
}

.select-control > span {
  color: var(--muted);
  font-size: 13px;
  font-weight: 750;
}

.select-control select {
  min-height: 36px;
  padding: 7px 34px 7px 12px;
  border: 1px solid #cfe2da;
  border-radius: 8px;
  color: var(--ink);
  background:
    url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='12' height='12' viewBox='0 0 24 24' fill='none' stroke='%23087e68' stroke-width='2.4' stroke-linecap='round' stroke-linejoin='round'%3E%3Cpath d='m6 9 6 6 6-6'/%3E%3C/svg%3E")
      no-repeat right 11px center,
    #fff;
  font: inherit;
  font-size: 14px;
  font-weight: 750;
  cursor: pointer;
  appearance: none;
  transition: border-color .2s ease, box-shadow .2s ease;
}

.select-control select:hover,
.select-control select:focus-visible {
  border-color: #6ab59c;
  outline: none;
  box-shadow: 0 0 0 3px rgba(13, 157, 121, .14);
}

.select-control select:disabled { opacity: .6; cursor: default; }


/* ---------- Home: hero fits one screen (sizes and spacing only) ---------- */

@media (min-width: 1101px) {
  .hero-section {
    min-height: min(730px, calc(100vh - 80px));
    padding-top: clamp(18px, 4.2vh, 70px);
    padding-bottom: clamp(18px, 4.2vh, 75px);
  }

  .hero-section .tata-hero-badge { margin-bottom: clamp(6px, 1.4vh, 20px); }

  .hero-section .hero-copy h1 {
    margin-top: clamp(6px, 1.4vh, 20px);
    font-size: clamp(44px, min(6vw, 8.4vh), 92px);
  }

  .hero-section .hero-description {
    margin-top: clamp(10px, 2.2vh, 27px);
    font-size: clamp(15px, min(1.45vw, 2.3vh), 22px);
    line-height: 1.62;
  }

  .hero-section .hero-actions { margin-top: clamp(12px, 2.6vh, 30px); }

  .hero-section .button-large {
    min-height: clamp(42px, 6.2vh, 53px);
    padding-top: clamp(9px, 1.5vh, 15px);
    padding-bottom: clamp(9px, 1.5vh, 15px);
  }

  .hero-section .hero-note { margin-top: clamp(8px, 1.9vh, 23px); }

  .hero-section .tata-hero-art { min-height: clamp(340px, 70vh, 580px); }
  .hero-section .steel-data-core { width: min(540px, 78%, 64vh); }
  .hero-section .orbit-large { width: min(560px, 74vh); height: min(560px, 74vh); }
  .hero-section .orbit-small { width: min(450px, 59vh); height: min(450px, 59vh); }
  .hero-section .finance-card-one { top: clamp(60px, 16vh, 125px); }
  .hero-section .finance-card-two { bottom: clamp(60px, 15vh, 118px); }
  .hero-section .finance-card-three { bottom: clamp(10px, 4vh, 33px); }
}


/* ---------- Home: at a glance ---------- */

.glance-actions {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 18px;
}

.about-card {
  margin-bottom: 18px;
  padding: 20px 22px;
  border: 1px solid #d5e9e1;
  border-radius: 12px;
  background: linear-gradient(120deg, #f3fbf8 0%, #f2f6fd 100%);
}

.about-card-heading {
  display: flex;
  align-items: center;
  gap: 12px;
  margin-bottom: 12px;
}

.about-card-heading h3 {
  margin: 0;
  color: var(--ink);
  font-size: 19px;
}

.about-card-heading small { color: var(--muted); font-size: 13px; }

.about-facts {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 10px 26px;
  margin: 0;
  padding: 0;
  list-style: none;
}

.about-facts li {
  display: flex;
  gap: 9px;
  color: var(--ink-soft);
  font-size: 15px;
  line-height: 1.6;
}

.about-facts li > svg { flex: 0 0 auto; margin-top: 4px; color: var(--green); }

.fact-page-link {
  display: inline-flex;
  align-items: center;
  gap: 3px;
  margin-left: 2px;
  padding: 0 7px;
  border: 1px solid #cfe6dd;
  border-radius: 6px;
  color: var(--green);
  background: #fff;
  font-size: 12px;
  font-weight: 750;
  white-space: nowrap;
}

.fact-page-link:hover { border-color: #6ab59c; background: #f0faf5; }

.glance-bullets {
  margin-top: 20px;
  padding: 18px 22px;
  border: 1px solid #dfe8e4;
  border-left: 3px solid var(--green-bright);
  border-radius: 10px;
  background: #fff;
}

.glance-bullets h3 { margin: 0 0 8px; color: var(--ink); font-size: 19px; }

.glance-bullets ul {
  display: grid;
  gap: 5px;
  margin: 0;
  padding-left: 20px;
  color: var(--ink-soft);
  font-size: 15px;
  line-height: 1.6;
}

.glance-closing {
  display: flex;
  align-items: flex-start;
  gap: 8px;
  margin: 18px 0 0;
  color: var(--muted);
  font-size: 15px;
  line-height: 1.6;
}

.glance-closing svg { flex: 0 0 auto; margin-top: 4px; color: var(--green); }


/* ---------- Ask Edith: full-height sidebar, taller chat ---------- */

.app-shell .ask-page .ask-sidebar {
  height: auto;
  max-height: none;
  overflow: visible;
}

/* Same clipping as before, but "clip" does not make the shell a scroll
   container, so the chat panel below can stay sticky. */
.app-shell { overflow: clip; }

/* Nothing scrolls under the toggle any more, so it stays in flow. */
.app-shell .ask-page .sidebar-toggle { position: static; }

.app-shell .ask-page .suggestion-list { max-height: none; overflow: visible; }

@media (min-width: 901px) {
  .app-shell .ask-page .ask-layout { align-items: start; }
  .app-shell .ask-page .ask-sidebar { align-self: stretch; }

  .app-shell .ask-page .chat-panel {
    position: sticky;
    top: 92px;
    height: max(600px, calc(100vh - 108px));
    min-height: 0;
  }
}

/* Bigger, readable sidebar text */
.app-shell .ask-page .suggestion-item { min-height: 0; padding-top: 12px; padding-bottom: 12px; }
.app-shell .ask-page .suggestion-item span { font-size: 12px; }
.app-shell .ask-page .suggestion-item strong { font-size: 17px; line-height: 1.4; }
.app-shell .ask-page .suggestion-item small { font-size: 13px; }
.app-shell .ask-page .sidebar-heading h2 { font-size: 19px; }
.app-shell .ask-page .sidebar-heading p { font-size: 15.5px; }
.app-shell .ask-page .follow-up-hint { font-size: 14.5px; line-height: 1.55; }
.app-shell .ask-page .sidebar-info-title { font-size: 16px; }
.app-shell .ask-page .sidebar-info-row { font-size: 15px; }
.app-shell .ask-page .sidebar-info-row b { font-size: 15px; }
.app-shell .ask-page .recent-heading b { font-size: 16px; }
.app-shell .ask-page .recent-question { font-size: 15.5px; line-height: 1.5; }
.app-shell .ask-page .recent-empty { font-size: 14.5px; }

/* Answer tables fit the panel: wrap long cells before scrolling */
.app-shell .answer-table-wrap table { table-layout: auto; font-size: 14px; }

.app-shell .answer-table-wrap th,
.app-shell .answer-table-wrap td {
  min-width: 70px;
  white-space: normal;
  overflow-wrap: break-word;
  vertical-align: top;
}


/* ---------- Dashboard: controls, lighter gradient, selected year ---------- */

.app-shell .dashboard-page .dashboard-controls {
  flex-wrap: wrap;
  border-color: #b9dcd0;
  background: linear-gradient(120deg, #dcf3eb 0%, #dce8f7 100%);
}

.app-shell .dashboard-page .control-note { color: var(--ink-soft); font-size: 14px; font-weight: 650; }

.app-shell .dashboard-page .metric-card {
  border-color: #bfdcd2;
  background: linear-gradient(120deg, #e3f5ef 0%, #e2ecf8 100%);
}

.app-shell .dashboard-page .metric-card.metric-active {
  border-color: #0b9275;
  box-shadow: inset 0 3px 0 #0b9275, 0 10px 24px rgba(18, 62, 50, .1);
}

.app-shell .dashboard-page .metric-card-top > span:first-child { color: var(--ink-soft); }
.app-shell .dashboard-page .metric-card-bottom span { font-size: 12.5px; color: var(--ink-soft); }

.app-shell .dashboard-panel.statement-panel {
  border-color: #b9dcd0;
  color: var(--ink);
  background: linear-gradient(120deg, #dcf3eb 0%, #dce8f7 100%) !important;
}

.app-shell .statement-panel .panel-heading h2,
.app-shell .statement-panel .statement-row strong { color: var(--ink); }

.app-shell .statement-panel .panel-heading p,
.app-shell .statement-panel .statement-row small { color: #3f5a54; }

.app-shell .statement-panel .statement-row { border-bottom-color: rgba(8, 126, 104, .16); }

.app-shell .statement-panel .statement-icon { background: #fff; color: var(--green); }

.app-shell .statement-panel .report-links a {
  gap: 5px;
  padding: 4px 9px;
  border-color: rgba(8, 126, 104, .28);
  color: var(--green-dark);
  background: rgba(255, 255, 255, .7);
  font-size: 13px;
}

.app-shell .statement-panel .report-links a em {
  color: var(--muted);
  font-size: 12px;
  font-style: normal;
  font-weight: 650;
}

.app-shell .statement-panel .report-links a:hover { border-color: var(--green); background: #fff; }

.app-shell .statement-panel .report-links a.selected-year {
  border-color: #4b88df;
  box-shadow: inset 0 -2px 0 #4b88df;
}

.dashboard-panel.statement-panel-full { margin-top: 18px; }

/* Group-level note while a region is selected */
.group-level-row { margin: 0 0 10px; }

.group-level-note {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  margin-top: 6px;
  padding: 3px 10px;
  border: 1px solid #eed9ad;
  border-radius: 999px;
  color: #7a5a1c;
  background: #fff8ea;
  font-size: 12.5px;
  font-weight: 700;
  line-height: 1.5;
}

.dashboard-page .panel-heading .group-level-note { display: inline-flex; }

/* Selected year column in the tables */
.data-table th.selected-year,
.data-table td.selected-year { background: rgba(75, 136, 223, .08); }
.data-table thead th.selected-year { color: #2f67b8; box-shadow: inset 0 -2px 0 #4b88df; }


/* ---------- Dashboard: larger chart and ratio text ---------- */

.dashboard-page .performance-panel { display: flex; flex-direction: column; }

.app-shell .dashboard-page .performance-panel .chart-area.chart-live {
  flex: 1 1 auto;
  height: auto;
  min-height: 300px;
}

.app-shell .dashboard-page .chart-live .chart-plot {
  position: absolute;
  top: 0;
  right: 0;
  bottom: 0;
  left: 74px;
  height: auto;
}

.app-shell .dashboard-page .chart-legend { gap: 18px; font-size: 13.5px; }
.app-shell .dashboard-page .chart-legend .legend-dot { width: 10px; height: 10px; }
.app-shell .dashboard-page .chart-period-note { color: var(--muted); }
.app-shell .dashboard-page .chart-y-live span { color: #6f817b; font-size: 13px; }
.app-shell .dashboard-page .chart-x-labels { color: #6f817b; font-size: 13.5px; }
.app-shell .dashboard-page .chart-x-labels span.selected { color: #2f67b8; font-weight: 800; }

.app-shell .dashboard-page .ratio-topline span { font-size: 15px; }
.app-shell .dashboard-page .ratio-topline strong { font-size: 17px; }
.app-shell .dashboard-page .ratio-item small { font-size: 13px; }
.app-shell .dashboard-page .panel-footnote { font-size: 14px; line-height: 1.6; }

.mini-sparkline circle.sparkline-selected { fill: #4b88df; stroke: #fff; stroke-width: 1.2; }

/* One solid colour for the line and points; selected year in blue */
.chart-point.selected {
  z-index: 3;
  width: 20px;
  height: 20px;
  border: 3px solid #fff;
  background: #4b88df;
  box-shadow: 0 0 0 2px #4b88df, 0 4px 12px rgba(47, 103, 184, .3);
}

.chart-point-label {
  position: absolute;
  z-index: 3;
  padding: 3px 9px;
  border-radius: 7px;
  color: #fff;
  background: #3978d7;
  box-shadow: 0 6px 14px rgba(47, 103, 184, .25);
  font-size: 13px;
  font-weight: 800;
  white-space: nowrap;
  transform: translate(-50%, calc(-100% - 16px));
  pointer-events: none;
}

.chart-point-label.below { transform: translate(-50%, 16px); }
.chart-point-label.align-right { transform: translate(-88%, calc(-100% - 16px)); }
.chart-point-label.align-right.below { transform: translate(-88%, 16px); }


/* ---------- Dashboard: region view ---------- */

.dashboard-panel.region-panel { margin-bottom: 14px; }

.region-stats {
  display: grid;
  grid-template-columns: repeat(5, minmax(0, 1fr));
  gap: 12px;
  margin-top: 6px;
}

.region-stat {
  display: flex;
  flex-direction: column;
  gap: 6px;
  padding: 14px 16px;
  border: 1px solid #bfdcd2;
  border-radius: 10px;
  background: linear-gradient(120deg, #e3f5ef 0%, #e2ecf8 100%);
}

.region-stat span { color: var(--ink-soft); font-size: 13.5px; font-weight: 700; }

.region-stat strong {
  color: #142a26;
  font-size: 21px;
  font-weight: 800;
  letter-spacing: -.02em;
}

.region-stat strong small { color: var(--muted); font-size: 12px; font-weight: 700; }

.region-trend { margin-top: 18px; }
.region-trend .chart-legend { align-items: center; }
.region-trend .chart-legend .segmented-control { margin-left: auto; }
.app-shell .dashboard-page .region-trend .chart-area.chart-live { height: 260px; }

.region-sources a {
  display: inline-flex;
  align-items: center;
  gap: 3px;
  margin-right: 8px;
  color: var(--green);
  font-weight: 750;
}


/* ---------- Evaluation: larger text ---------- */

.app-shell .evaluation-page .page-title-row p { font-size: 18px; }
.app-shell .evaluation-page .summary-label { font-size: 13px; }
.app-shell .evaluation-page .evaluation-summary-copy h2 { font-size: 31px; }
.app-shell .evaluation-page .evaluation-summary-copy p { font-size: 16px; line-height: 1.6; }
.app-shell .evaluation-page .evaluation-set-card strong { font-size: 16px; }
.app-shell .evaluation-page .evaluation-set-card span:not(.status-pill) { font-size: 15px; line-height: 1.6; }
.app-shell .evaluation-page .evaluation-measures .section-heading h2 { font-size: 34px; }
.app-shell .evaluation-page .evaluation-measures .section-heading p { font-size: 17px; }
.app-shell .evaluation-page .evaluation-measure-card h3 { font-size: 18px; }
.app-shell .evaluation-page .evaluation-measure-card p { font-size: 15px; line-height: 1.6; }
.app-shell .evaluation-page .evaluation-measure-card small,
.app-shell .evaluation-page .measure-definition { font-size: 13px; line-height: 1.5; }
.app-shell .evaluation-page .panel-heading h2 { font-size: 22px; }
.app-shell .evaluation-page .panel-heading p { font-size: 15.5px; line-height: 1.6; }
.app-shell .evaluation-page .category-filter button { font-size: 13.5px; }
.app-shell .evaluation-page .category-table-head,
.app-shell .evaluation-page .category-table-row,
.app-shell .evaluation-page .category-table-row > span,
.app-shell .evaluation-page .category-table-row > span:first-child { font-size: 14.5px; }
.app-shell .evaluation-page .flagged-empty strong { font-size: 16px; }
.app-shell .evaluation-page .flagged-grade { font-size: 13.5px; }
.app-shell .evaluation-page .flagged-empty p { font-size: 15px; line-height: 1.6; }
.app-shell .evaluation-page .flagged-placeholder small { color: #6f817b; font-size: 14px; line-height: 1.6; }
.app-shell .evaluation-page .methodology-card h2 { font-size: 25px; }
.app-shell .evaluation-page .methodology-card p { font-size: 16.5px; line-height: 1.75; }


/* ---------- Sources: larger text, FY2021-22 card ---------- */

.app-shell .sources-page .page-title-row p { font-size: 18px; }
.app-shell .sources-page .section-heading p { font-size: 17.5px; line-height: 1.65; }
.app-shell .sources-page .report-card strong { font-size: 16px; }
.app-shell .sources-page .report-card small { font-size: 13.5px; line-height: 1.5; }
.app-shell .sources-page .report-year { font-size: 13px; }
.app-shell .sources-page .evaluation-measure-card h3 { font-size: 18px; }
.app-shell .sources-page .evaluation-measure-card p { font-size: 15px; line-height: 1.6; }
.app-shell .sources-page .methodology-card h2 { font-size: 24px; }
.app-shell .sources-page .methodology-card p { font-size: 16px; line-height: 1.75; }
.app-shell .sources-page .panel-heading p { font-size: 15.5px; }
.app-shell .sources-page .limitations-list li { font-size: 15.5px; line-height: 1.6; }

@media (min-width: 1101px) {
  .app-shell .sources-page .report-grid { grid-template-columns: repeat(3, minmax(0, 1fr)); }
}

@media (min-width: 1600px) {
  .app-shell .sources-page .report-grid { grid-template-columns: repeat(5, minmax(0, 1fr)); }
}

.report-card-link strong { transition: color .2s ease; }
.report-card-link:hover strong { color: var(--green); }

.report-card-open { flex: 0 0 auto; color: var(--muted-light); }
.report-card-open:hover { color: var(--green); }

.report-card small a {
  display: inline-flex;
  align-items: center;
  gap: 3px;
  color: var(--green);
  font-weight: 750;
}

.report-card small a.official-link {
  color: var(--muted);
  font-weight: 650;
  text-decoration: underline;
  text-underline-offset: 2px;
}

.dashboard-panel.report-card-comparative {
  border-style: dashed;
  background: linear-gradient(120deg, #f3fbf8 0%, #f2f6fd 100%);
}


/* ---------- Responsive ---------- */

@media (max-width: 1100px) {
  .region-stats { grid-template-columns: repeat(2, minmax(0, 1fr)); }
  .about-facts { grid-template-columns: 1fr; }
}

/* Composite scores: all five year columns fit the card */
.app-shell .dashboard-page .scores-table tbody th { min-width: 160px; }
.app-shell .dashboard-page .scores-table th,
.app-shell .dashboard-page .scores-table td { padding-left: 8px; padding-right: 10px; }

.app-shell .dashboard-page .control-note { margin-left: auto; white-space: nowrap; }
```

---

## `frontend/src/App.jsx`

```jsx
import { useEffect, useState } from "react";
import "./App.css";
import "./readability.css";
import {
  getCompany,
  getFinancials,
  getHealth,
  getMetrics,
  getScores,
} from "./api.js";
import AskPage, { DUPONT_QUESTION, PROFIT_TREND_QUESTION } from "./components/AskPage.jsx";
import DashboardPage from "./components/DashboardPage.jsx";
import EvaluationPage from "./components/EvaluationPage.jsx";
import SourcesPage from "./components/SourcesPage.jsx";
import {
  COVERAGE_TEXT,
  Icon,
  LoadError,
  RestatedMark,
  SectionHeading,
  Value,
  formatChangePct,
  formatCrore,
  formatNumber,
  sentenceCase,
  useApi,
} from "./components/ui.jsx";
import { useConversations } from "./useConversations.js";

const pages = ["Home", "Ask Edith", "Dashboard", "Evaluation", "Sources"];

const HEALTH_POLL_MS = 60_000;

function Brand({ compact = false }) {
  return (
    <div className={`brand ${compact ? "brand-compact" : ""}`}>
      <div className="brand-mark">E</div>

      <div className="brand-copy">
        <strong>Edith</strong>
        <span>Tata Steel financial assistant</span>
      </div>
    </div>
  );
}

function Header({ activePage, setActivePage }) {
  const [menuOpen, setMenuOpen] = useState(false);

  function goTo(page) {
    setActivePage(page);
    setMenuOpen(false);
    window.scrollTo({ top: 0, behavior: "smooth" });
  }

  return (
    <header className="site-header">
      <div className="header-inner">
        <button
          className="brand-button"
          onClick={() => goTo("Home")}
          aria-label="Go to home"
        >
          <Brand />
        </button>

        <button
          className="mobile-menu-button"
          onClick={() => setMenuOpen((open) => !open)}
          aria-label={menuOpen ? "Close navigation" : "Open navigation"}
        >
          <Icon name={menuOpen ? "close" : "menu"} size={23} />
        </button>

        <nav className={`main-nav ${menuOpen ? "nav-open" : ""}`}>
          {pages.map((page) => (
            <button
              key={page}
              className={`nav-link ${activePage === page ? "active" : ""}`}
              onClick={() => goTo(page)}
            >
              {page}
            </button>
          ))}
        </nav>

        <div className="header-actions">
          <BackendStatus />

          <button className="header-cta" onClick={() => goTo("Ask Edith")}>
            Ask Edith <Icon name="arrow" size={16} />
          </button>
        </div>
      </div>
    </header>
  );
}

/* Live backend status from /api/health, polled every 60 s. */
function BackendStatus() {
  const [health, setHealth] = useState({ state: "checking", detail: null });

  useEffect(() => {
    let active = true;

    function check() {
      getHealth().then(
        (data) =>
          active &&
          setHealth({
            state: data.status === "ok" ? "live" : "degraded",
            detail: data,
          }),
        () => active && setHealth({ state: "offline", detail: null }),
      );
    }

    check();
    const timer = setInterval(check, HEALTH_POLL_MS);

    return () => {
      active = false;
      clearInterval(timer);
    };
  }, []);

  const labels = {
    checking: "Checking",
    live: "Live",
    degraded: "Degraded",
    offline: "Offline",
  };

  const title =
    health.state === "live" || health.state === "degraded"
      ? `Backend ${health.state} · model ${health.detail.llm_model} · ${
          health.detail.index_points ?? "no"
        } indexed passages · reports ${health.detail.reports.join(", ")}`
      : health.state === "offline"
        ? "Edith's backend is not reachable"
        : "Checking the backend";

  return (
    <span
      className={`backend-status ${health.state}`}
      title={title}
      role="status"
      aria-label={title}
    >
      <i />
      {labels[health.state]}
    </span>
  );
}

/* =========================================================
   HOME PAGE
   ========================================================= */

function HomePage({ setActivePage, onAskEdith }) {
  const [expandedStep, setExpandedStep] = useState(0);

  const steps = [
    {
      number: "01",
      title: "Ask",
      description: "Start with a plain-language question about Tata Steel.",
      detail:
        "Ask about profitability, liquidity, risk, segments, cash flow, or another financial topic.",
      icon: "search",
    },
    {
      number: "02",
      title: "Retrieve",
      description: "Find the relevant passage in connected reports.",
      detail:
        "Edith will retrieve the supporting report text together with its document, reporting period and page reference.",
      icon: "file",
    },
    {
      number: "03",
      title: "Verify",
      description: "Check the answer against its evidence.",
      detail:
        "The answer should be traceable to the cited source. If the evidence is unavailable, Edith should say so rather than invent a figure.",
      icon: "check",
    },
  ];

  return (
    <main className="page home-page">

      {/* HERO */}
      <section className="hero-section">

        <div className="hero-background-glow hero-glow-green" />
        <div className="hero-background-glow hero-glow-blue" />
        <div className="hero-grid-glow" />

        <div className="hero-copy">

          <div className="tata-hero-badge">
            <span className="tata-badge-dot" />
            <span>TATA STEEL</span>
            <small>FINANCIAL RESEARCH</small>
          </div>

          <h1>
            Understand
            <br />
            <span>Tata Steel.</span>
            <br />
            Follow the evidence.
          </h1>

          <p className="hero-description">
            Meet Edith, a financial research assistant built around Tata
            Steel's reports. Ask questions about performance, disclosures and
            financial trends, then trace the answer back to its source.
          </p>

          <div className="hero-actions">
            <button
              className="button button-primary button-large"
              onClick={() => setActivePage("Ask Edith")}
            >
              Ask Edith
              <Icon name="arrow" size={18} />
            </button>

            <button
              className="button button-secondary button-large"
              onClick={() => setActivePage("Dashboard")}
            >
              Explore dashboard
            </button>
          </div>

          <div className="hero-note">
            <span className="note-dot" />
            <span>
              Live · {COVERAGE_TEXT}
            </span>
          </div>

        </div>


        {/* CUSTOM HERO VISUAL */}
        <div
          className="hero-art tata-hero-art"
          aria-label="Tata Steel financial intelligence visual"
        >

          <div className="hero-art-orbit orbit-large" />
          <div className="hero-art-orbit orbit-small" />

          <div className="steel-data-core">

            <div className="tata-wordmark">
              <span>TATA</span>
              <strong>STEEL</strong>
            </div>

            <div className="steel-core-glow" />

            <div className="steel-core-ring ring-one" />
            <div className="steel-core-ring ring-two" />
            <div className="steel-core-ring ring-three" />

            <div className="steel-core-center">
              <span>FINANCIAL</span>
              <strong>INTELLIGENCE</strong>
              <small>EDITH · TATA STEEL</small>
            </div>

            <div className="steel-chart-lines">
              <span />
              <span />
              <span />
              <span />
              <span />
              <span />
            </div>

            <svg
              className="hero-financial-line"
              viewBox="0 0 500 220"
              preserveAspectRatio="none"
            >
              <defs>
                <linearGradient
                  id="heroLineGradient"
                  x1="0"
                  y1="0"
                  x2="1"
                  y2="0"
                >
                  <stop offset="0%" stopColor="#11a985" />
                  <stop offset="52%" stopColor="#27bca0" />
                  <stop offset="100%" stopColor="#4e8ff0" />
                </linearGradient>
              </defs>

              <path
                d="M10 175 C65 155 82 158 120 125 S188 138 224 96 S286 116 325 80 S392 92 430 46 S468 52 495 22"
                fill="none"
                stroke="url(#heroLineGradient)"
                strokeWidth="5"
                strokeLinecap="round"
              />

              <circle cx="120" cy="125" r="6" />
              <circle cx="224" cy="96" r="6" />
              <circle cx="325" cy="80" r="6" />
              <circle cx="430" cy="46" r="6" />
            </svg>

          </div>


          <div className="floating-finance-card finance-card-one">
            <div className="finance-card-icon green">
              <Icon name="chart" size={19} />
            </div>

            <div>
              <small>Financial performance</small>
              <strong>Trace the trend</strong>
            </div>
          </div>


          <div className="floating-finance-card finance-card-two">
            <div className="finance-card-icon blue">
              <Icon name="file" size={19} />
            </div>

            <div>
              <small>Report evidence</small>
              <strong>Page-linked source</strong>
            </div>
          </div>


          <div className="floating-finance-card finance-card-three">
            <div className="finance-status-dot" />
            <span>Evidence trail active</span>
          </div>


          <div className="hero-spark spark-one">✦</div>
          <div className="hero-spark spark-two">✧</div>
          <div className="hero-spark spark-three">✦</div>

        </div>

      </section>


      {/* AT A GLANCE (live data) */}
      <GlanceSection
        setActivePage={setActivePage}
        onAskEdith={onAskEdith}
      />


      {/* TRUST STRIP */}
      <section className="trust-strip">

        <div className="trust-intro">
          <span className="trust-icon">
            <Icon name="shield" size={20} />
          </span>

          <div>
            <strong>Built for financial research</strong>
            <span>
              Clear answers. Visible evidence. No made-up numbers.
            </span>
          </div>
        </div>

        <div className="trust-item">
          <Icon name="file" size={18} />
          Tata Steel reports
        </div>

        <div className="trust-item">
          <Icon name="search" size={18} />
          Plain-language questions
        </div>

        <div className="trust-item">
          <Icon name="check" size={18} />
          Source verification
        </div>

      </section>


      {/* WHAT EDITH DOES */}
      <section className="content-section feature-section">

        <SectionHeading
          eyebrow="WHAT EDITH DOES"
          title="Research Tata Steel without losing the story behind the numbers."
          description="A financial research interface that brings questions, reports, evidence and financial trends into one place."
        />

        <div className="feature-grid">

          <article className="feature-card feature-green">
            <div className="feature-icon">
              <Icon name="search" size={25} />
            </div>

            <span className="feature-number">01 / ASK</span>

            <h3>Ask in plain language</h3>

            <p>
              Ask about profitability, liquidity, risk, segments or a specific
              section of a Tata Steel report.
            </p>

            <button
              className="text-link"
              onClick={() => setActivePage("Ask Edith")}
            >
              Try a question
              <Icon name="arrow" size={16} />
            </button>
          </article>


          <article className="feature-card feature-blue">
            <div className="feature-icon">
              <Icon name="file" size={25} />
            </div>

            <span className="feature-number">02 / TRACE</span>

            <h3>See the supporting passage</h3>

            <p>
              Review the source excerpt alongside the answer, including the
              report, period and page reference.
            </p>

            <button
              className="text-link"
              onClick={() => setActivePage("Ask Edith")}
            >
              See the query view
              <Icon name="arrow" size={16} />
            </button>
          </article>


          <article className="feature-card feature-explore">
            <div className="feature-trend-art" aria-hidden="true">
              <svg viewBox="0 0 220 100" role="presentation">
                <path className="trend-area" d="M4 78 C30 71 35 54 59 60 S94 75 117 49 S151 44 169 31 S196 39 216 8 L216 96 L4 96 Z" />
                <path className="trend-line" d="M4 78 C30 71 35 54 59 60 S94 75 117 49 S151 44 169 31 S196 39 216 8" />
                <circle cx="117" cy="49" r="4" />
                <circle cx="169" cy="31" r="4" />
                <circle cx="216" cy="8" r="4" />
              </svg>
            </div>
            <div className="feature-icon">
              <Icon name="chart" size={25} />
            </div>

            <span className="feature-number">03 / EXPLORE</span>

            <h3>Explore financial trends</h3>

            <p>
              Review statements, trends, financial ratios, composite scores
              and segments from verified report data.
            </p>

            <button
              className="text-link"
              onClick={() => setActivePage("Dashboard")}
            >
              Open dashboard
              <Icon name="arrow" size={16} />
            </button>
          </article>

        </div>

      </section>


      {/* NEW ROADMAP */}
      <section className="content-section roadmap-section">

        <div className="roadmap-heading">

          <div>
            <div className="section-eyebrow">
              THE EDITH WORKFLOW
            </div>

            <h2>
              From question
              <br />
              to evidence.
            </h2>

            <p>
              Three connected steps turn a financial question into a
              traceable answer.
            </p>
          </div>

          <div className="roadmap-stamp">
            <Icon name="layers" size={21} />
            Evidence-first workflow
          </div>

        </div>


        <div className="visual-roadmap">

          <div className="roadmap-line">
            <span className="roadmap-line-progress" />
          </div>


          {steps.map((step, index) => (

            <button
              className={`roadmap-node ${
                expandedStep === index ? "expanded" : ""
              }`}
              key={step.number}
              onClick={() => setExpandedStep(index)}
            >

              <div className="roadmap-node-top">

                <div className="roadmap-node-number">
                  {step.number}
                </div>

                <div className="roadmap-node-icon">
                  <Icon name={step.icon} size={23} />
                </div>

              </div>


              <div className="roadmap-pointer">
                <span />
              </div>


              <h3>{step.title}</h3>

              <p>{step.description}</p>


              {expandedStep === index && (
                <div className="roadmap-detail">
                  {step.detail}
                </div>
              )}


              <span className="roadmap-more">
                {expandedStep === index
                  ? "Current step"
                  : "Explore step"}
              </span>

            </button>

          ))}

        </div>

      </section>


      {/* TATA STEEL FEATURE */}
      <section className="tata-feature">

        <div className="tata-feature-art">

          <div className="tata-glow" />

          <div className="steel-visual">

            <div className="steel-sun" />

            <div className="steel-plant plant-one">
              <i />
              <i />
              <i />
              <i />
            </div>

            <div className="steel-plant plant-two">
              <i />
              <i />
              <i />
            </div>

            <div className="steel-ground" />

          </div>

        </div>


        <div className="tata-feature-copy">

          <div className="section-eyebrow">
            TATA STEEL
          </div>

          <h2>
            One place to explore the story behind the numbers.
          </h2>

          <p>
            Edith is being built around Tata Steel's financial reports.
            Explore reported performance, look for supporting disclosures,
            and understand where each answer comes from.
          </p>

          <div className="tata-feature-points">

            <span>
              <Icon name="check" size={17} />
              Four annual reports, FY2022-23 to FY2025-26
            </span>

            <span>
              <Icon name="check" size={17} />
              Financial statements and disclosures
            </span>

            <span>
              <Icon name="check" size={17} />
              Evidence references and verification status
            </span>

          </div>

          <button
            className="button button-primary"
            onClick={() => setActivePage("Ask Edith")}
          >
            Ask about Tata Steel
            <Icon name="arrow" size={17} />
          </button>

        </div>

      </section>


      {/* CTA */}
      <section className="bottom-cta">

        <div className="bottom-cta-copy">

          <span className="cta-orb">
            <Icon name="spark" size={23} />
          </span>

          <div>
            <h2>Start with a question.</h2>

            <p>
              Ask about Tata Steel's financial reports and follow the evidence.
            </p>
          </div>

        </div>

        <button
          className="button button-light"
          onClick={() => setActivePage("Ask Edith")}
        >
          Open Ask Edith
          <Icon name="arrow" size={17} />
        </button>

      </section>

    </main>
  );
}


/* =========================================================
   HOME · AT A GLANCE (live data)
   ========================================================= */

// Same item list as the Dashboard, so the cached response is shared.
const GLANCE_ITEMS = [
  "revenue_from_operations",
  "profit_for_the_year",
  "net_cash_from_operating",
];

// The four report years (each has a prior year to compare with).
const GLANCE_YEARS = ["FY2022-23", "FY2023-24", "FY2024-25", "FY2025-26"];

const TRY_ASKING = [DUPONT_QUESTION, PROFIT_TREND_QUESTION];

function GlanceTile({ label, icon, loading, value, detail, source, tone }) {
  return (
    <article className="metric-card glance-tile">
      <div className="metric-card-top">
        <span>{label}</span>

        <span className="metric-card-icon">
          <Icon name={icon} size={18} />
        </span>
      </div>

      {loading ? (
        <strong className="metric-value-skeleton" />
      ) : (
        <strong className="metric-value">{value}</strong>
      )}

      <div className="metric-card-bottom">
        {detail ? (
          <span className={`zone-chip ${tone || "neutral"}`}>{detail}</span>
        ) : (
          <span />
        )}
      </div>

      {source && <small className="glance-source">{source}</small>}
    </article>
  );
}

/* "About Tata Steel": facts from /api/company, each with its page link. */
function AboutTataSteel() {
  const company = useApi(getCompany, "company");

  if (company.error) {
    return <LoadError error={company.error} onRetry={company.retry} compact />;
  }

  return (
    <div className="about-card">
      <div className="about-card-heading">
        <span className="statement-icon">
          <Icon name="book" size={18} />
        </span>

        <div>
          <h3>{company.data?.title || "About Tata Steel"}</h3>
          {company.data?.source && <small>{company.data.source}</small>}
        </div>
      </div>

      {company.loading ? (
        <>
          <div className="evidence-skeleton wide" />
          <div className="evidence-skeleton" />
        </>
      ) : (
        <ul className="about-facts">
          {company.data.facts.map((fact) => (
            <li key={fact.text}>
              <Icon name="check" size={16} />
              <span>
                {fact.text}{" "}
                <a
                  className="fact-page-link"
                  href={fact.url}
                  target="_blank"
                  rel="noopener noreferrer"
                  title={`Open the ${fact.report} report at page ${fact.page_label}`}
                >
                  {fact.report}, p. {fact.page_label}
                  <Icon name="external" size={12} />
                </a>
              </span>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

/* Short factual bullets, templated from API values only. */
function GlanceBullets({ year, revenue, profit, netDebt, altman, piotroski }) {
  const money = (value) => `₹ ${formatCrore(value)} crore`;
  const change = (entry) =>
    entry ? `, ${formatChangePct(entry.change_pct)} versus ${entry.from}` : "";

  const bullets = [
    revenue.point?.value != null &&
      `Revenue from operations was ${money(revenue.point.value)}${change(revenue.change)}.`,
    profit.point?.value != null &&
      `Profit for the year was ${money(profit.point.value)}${change(profit.change)}.`,
    netDebt != null && `Net debt was ${money(netDebt)}.`,
    altman?.score != null &&
      `Altman Z'' was ${formatNumber(altman.score, 4)}, in the ${altman.interpretation} zone.`,
    piotroski?.score != null &&
      `Piotroski F was ${piotroski.score}/9, rated ${piotroski.interpretation}.`,
  ].filter(Boolean);

  if (bullets.length === 0) return null;

  return (
    <div className="glance-bullets">
      <h3>How its financials look in {year}</h3>

      <ul>
        {bullets.map((text) => (
          <li key={text}>{text}</li>
        ))}
      </ul>
    </div>
  );
}

function GlanceSection({ setActivePage, onAskEdith }) {
  const [year, setYear] = useState(GLANCE_YEARS[GLANCE_YEARS.length - 1]);

  const financials = useApi(
    () => getFinancials(GLANCE_ITEMS, "consolidated"),
    "financials-consolidated",
  );
  const metrics = useApi(() => getMetrics("consolidated"), "metrics-consolidated");
  const scores = useApi(() => getScores("consolidated"), "scores-consolidated");

  function itemData(key) {
    const item = financials.data?.items[key];
    return {
      point: item?.values[year],
      change: item?.yoy_changes.find((entry) => entry.to === year),
    };
  }

  function itemTile(key, label, icon) {
    const { point, change } = itemData(key);

    return (
      <GlanceTile
        key={key}
        label={label}
        icon={icon}
        loading={financials.loading}
        value={
          <>
            <small>₹</small>
            <Value value={point?.value ?? null} restated={point?.restated} />
            <small>cr</small>
          </>
        }
        detail={
          change && (
            <>
              {formatChangePct(change.change_pct)} YoY
              {change.restated_basis && <RestatedMark />}
            </>
          )
        }
        tone={change ? (change.change_pct < 0 ? "distress" : "safe") : null}
        source={point?.source || (financials.error ? "Could not load" : null)}
      />
    );
  }

  const netDebt = metrics.data?.metrics.find((metric) => metric.key === "net_debt");
  const altman = scores.data?.scores.altman_z?.[year];
  const piotroski = scores.data?.scores.piotroski_f?.[year];
  const zoneTone = (label) =>
    ({ safe: "safe", strong: "safe", grey: "grey", average: "grey" })[label] ||
    "distress";
  const loaded = financials.data && metrics.data && scores.data;

  return (
    <section className="content-section glance-section">
      <SectionHeading
        eyebrow="LIVE FROM THE REPORTS"
        title={`Tata Steel at a glance (${year}, consolidated)`}
        description="Reported values with their year-on-year change, straight from the verified statements."
        action={
          <div className="glance-actions">
            <label className="select-control">
              <span>Year</span>
              <select value={year} onChange={(event) => setYear(event.target.value)}>
                {GLANCE_YEARS.map((item) => (
                  <option key={item} value={item}>
                    {item}
                  </option>
                ))}
              </select>
            </label>

            <button className="text-link" onClick={() => setActivePage("Dashboard")}>
              Open dashboard
              <Icon name="arrow" size={16} />
            </button>
          </div>
        }
      />

      <AboutTataSteel />

      <div className="glance-grid">
        {itemTile("revenue_from_operations", "Revenue from operations", "chart")}
        {itemTile("profit_for_the_year", "Profit for the year", "layers")}

        <GlanceTile
          label="Net debt"
          icon="shield"
          loading={metrics.loading}
          value={
            <>
              <small>₹</small>
              <Value value={netDebt?.values[year] ?? null} />
              <small>cr</small>
            </>
          }
          source={
            metrics.error
              ? "Could not load"
              : "Borrowings + lease liabilities − cash, bank balances and current investments"
          }
        />

        <GlanceTile
          label="Altman Z''"
          icon="check"
          loading={scores.loading}
          value={<Value value={altman?.score ?? null} format={(value) => formatNumber(value, 4)} />}
          detail={altman?.interpretation && sentenceCase(`${altman.interpretation} zone`)}
          tone={zoneTone(altman?.interpretation)}
          source={scores.error ? "Could not load" : altman?.thresholds}
        />

        <GlanceTile
          label="Piotroski F"
          icon="spark"
          loading={scores.loading}
          value={piotroski?.score == null ? <Value value={null} /> : `${piotroski.score}/9`}
          detail={sentenceCase(piotroski?.interpretation)}
          tone={zoneTone(piotroski?.interpretation)}
          source={scores.error ? "Could not load" : piotroski?.thresholds}
        />
      </div>

      {loaded && (
        <GlanceBullets
          year={year}
          revenue={itemData("revenue_from_operations")}
          profit={itemData("profit_for_the_year")}
          netDebt={netDebt?.values[year] ?? null}
          altman={altman}
          piotroski={piotroski}
        />
      )}

      <p className="glance-closing">
        <Icon name="spark" size={16} />
        Edith can explain any of these: trends, ratios, DuPont, composite
        scores, segment and region performance, audit matters or an overall
        verdict, with every figure cited.
      </p>

      <div className="try-asking">
        <span className="try-asking-label">
          <Icon name="spark" size={16} />
          Try asking
        </span>

        <div className="try-asking-chips">
          {TRY_ASKING.map((question) => (
            <button
              key={question}
              type="button"
              className="question-chip"
              onClick={() => onAskEdith(question)}
              title="Opens Ask Edith and sends this question"
            >
              {question}
            </button>
          ))}
        </div>
      </div>
    </section>
  );
}


/* =========================================================
   FOOTER
   ========================================================= */

function Footer({ setActivePage }) {
  return (
    <footer className="site-footer">

      <div className="footer-main">

        <Brand />

        <p>
          {COVERAGE_TEXT} Every figure is verified against its source page.
          For research and educational use, not investment advice.
        </p>

        <button
          className="footer-link"
          onClick={() => setActivePage("Sources")}
        >
          Sources &amp; limitations
          <Icon name="arrow" size={15} />
        </button>

      </div>


      <div className="footer-bottom">

        <span>
          © Edith · Tata Steel financial assistant
        </span>

        <span>
          Evidence-first financial research
        </span>

      </div>

    </footer>
  );
}


/* =========================================================
   APP
   ========================================================= */

export default function App() {
  const [activePage, setActivePage] = useState("Home");
  const chat = useConversations();

  function goTo(page) {
    setActivePage(page);
    window.scrollTo({ top: 0, behavior: "smooth" });
  }

  // Open Ask Edith and send a question in a new conversation.
  function askEdith(question) {
    goTo("Ask Edith");
    chat.send(question, { fresh: true });
  }

  return (
    <div className="app-shell">

      <Header
        activePage={activePage}
        setActivePage={setActivePage}
      />

      <div
        className="page-transition"
        key={activePage}
      >

        {activePage === "Home" && (
          <HomePage setActivePage={goTo} onAskEdith={askEdith} />
        )}

        {activePage === "Ask Edith" && (
          <AskPage setActivePage={goTo} chat={chat} />
        )}

        {activePage === "Dashboard" && (
          <DashboardPage setActivePage={goTo} onAskEdith={askEdith} />
        )}

        {activePage === "Evaluation" && (
          <EvaluationPage />
        )}

        {activePage === "Sources" && (
          <SourcesPage setActivePage={goTo} />
        )}

      </div>

      <Footer setActivePage={goTo} />

    </div>
  );
}
```

---

## `frontend/src/api.js`

```javascript
/* =========================================================
   API CLIENT
   Every call uses a relative /api/... path: the Vite dev server
   and nginx both proxy it to the FastAPI backend.
   ========================================================= */

const OFFLINE_MESSAGE =
  "Edith's backend is not reachable. Please check that it is running and try again.";
const ASK_TIMEOUT_MS = 300_000;

export class ApiError extends Error {
  constructor(message, { status = null, cancelled = false } = {}) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.cancelled = cancelled;
  }
}

function errorMessage(status, body) {
  if (body && typeof body.error === "string") return body.error;
  if (status === 422 && Array.isArray(body?.detail) && body.detail[0]?.msg) {
    return `Please check your question: ${body.detail[0].msg}.`;
  }
  if (typeof body?.detail === "string") return body.detail;
  // A proxy answering for a stopped backend returns 5xx without a JSON body.
  if (status >= 500) return OFFLINE_MESSAGE;
  return `The request failed (HTTP ${status}).`;
}

async function request(path, options = {}) {
  let response;

  try {
    response = await fetch(path, {
      ...options,
      headers: { Accept: "application/json", ...options.headers },
    });
  } catch (error) {
    if (error?.name === "AbortError") throw error;
    throw new ApiError(OFFLINE_MESSAGE);
  }

  let body = null;
  try {
    body = await response.json();
  } catch {
    body = null;
  }

  if (!response.ok) {
    throw new ApiError(errorMessage(response.status, body), {
      status: response.status,
    });
  }

  if (body === null) throw new ApiError(OFFLINE_MESSAGE);
  return body;
}

/* Read-only endpoints are cached for the session: the data only
   changes when the backend is rebuilt. A failed call is dropped
   from the cache so that it can be retried. */
const cache = new Map();

function cachedGet(path) {
  if (!cache.has(path)) {
    const promise = request(path).catch((error) => {
      cache.delete(path);
      throw error;
    });
    cache.set(path, promise);
  }
  return cache.get(path);
}

export function getHealth() {
  return request("/api/health", { cache: "no-store" });
}

export function getReports() {
  return cachedGet("/api/reports");
}

export function getFinancials(items, scope = "consolidated") {
  const keys = encodeURIComponent(items.join(","));
  return cachedGet(`/api/financials?items=${keys}&scope=${scope}`);
}

export function getMetrics(scope = "consolidated") {
  return cachedGet(`/api/metrics?scope=${scope}`);
}

export function getScores(scope = "consolidated") {
  return cachedGet(`/api/scores?scope=${scope}`);
}

export function getSegments() {
  return cachedGet("/api/segments");
}

export function getStatements(scope = "consolidated") {
  return cachedGet(`/api/statements?scope=${scope}`);
}

export function getRegions() {
  return cachedGet("/api/regions");
}

export function getCompany() {
  return cachedGet("/api/company");
}

export function getEvaluation() {
  return cachedGet("/api/evaluation");
}

/**
 * Ask Edith a question.
 * history: earlier turns of this conversation, oldest first
 *          ([{ role: "user" | "assistant", content }], max 20).
 * signal:  optional AbortSignal; aborting it cancels the request.
 * Rejects with ApiError (cancelled: true when the user cancelled).
 */
export async function ask(question, history = [], signal) {
  const controller = new AbortController();
  let timedOut = false;

  const timer = setTimeout(() => {
    timedOut = true;
    controller.abort();
  }, ASK_TIMEOUT_MS);

  const onCancel = () => controller.abort();
  if (signal) {
    if (signal.aborted) controller.abort();
    else signal.addEventListener("abort", onCancel, { once: true });
  }

  try {
    return await request("/api/ask", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ question, history: history.slice(-20) }),
      signal: controller.signal,
    });
  } catch (error) {
    if (error?.name === "AbortError") {
      if (timedOut) {
        throw new ApiError(
          "Edith did not answer within 5 minutes. Please try again, or ask a narrower question.",
        );
      }
      throw new ApiError("Question cancelled.", { cancelled: true });
    }
    throw error;
  } finally {
    clearTimeout(timer);
    signal?.removeEventListener("abort", onCancel);
  }
}
```

---

## `frontend/src/components/AskPage.jsx`

```jsx
import { useEffect, useLayoutEffect, useRef, useState } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { COVERAGE_TEXT, Icon, StatusPill } from "./ui.jsx";

/* =========================================================
   ASK EDITH
   ========================================================= */

export const VERDICT_QUESTION =
  "Give an overall verdict on Tata Steel's financial health in FY2025-26.";

export const PROFIT_TREND_QUESTION =
  "How has Tata Steel's consolidated profit for the year changed from FY2022-23 to FY2025-26?";

export const DUPONT_QUESTION =
  "Run a DuPont analysis of Tata Steel's consolidated ROE for FY2025-26.";

// Short labels in the sidebar; each sends its full question.
export const suggestedQuestions = [
  {
    category: "Trends",
    label: "Profit trend, FY23 to FY26",
    question: PROFIT_TREND_QUESTION,
  },
  {
    category: "Ratios",
    label: "DuPont analysis of ROE",
    question: DUPONT_QUESTION,
  },
  {
    category: "Scores",
    label: "Altman, Piotroski, Beneish",
    question:
      "What are Tata Steel's Altman Z'', Piotroski F and Beneish M scores for FY2025-26?",
  },
  {
    category: "Segments",
    label: "India vs Netherlands vs UK",
    question:
      "Compare the EBITDA of Tata Steel's India, Netherlands and UK segments in FY2024-25 and FY2025-26.",
  },
  {
    category: "Verdict",
    label: "Overall verdict",
    question: VERDICT_QUESTION,
  },
  {
    category: "Try to trick it",
    label: "Can it predict FY2027-28?",
    question: "What will Tata Steel's revenue be in FY2027-28?",
    note: "Edith refuses what the reports can't answer",
  },
];

const FOLLOW_UP_EXAMPLE = "And in FY2023-24?";

const markdownComponents = {
  table: ({ node: _node, ...props }) => (
    <div className="answer-table-wrap">
      <table {...props} />
    </div>
  ),
  a: ({ node: _node, ...props }) => (
    <a {...props} target="_blank" rel="noopener noreferrer" />
  ),
};

function citationLabel(citation) {
  const page = citation.page_label || (citation.pdf_page ? `PDF p. ${citation.pdf_page}` : null);
  return [citation.report, citation.section, page].filter(Boolean).join(" · ");
}

function VerificationBadge({ verification }) {
  if (!verification) return null;

  const {
    status,
    figures_grounded: grounded,
    figures_total: total,
    unverified_figures: unverified = [],
  } = verification;

  if (status === "verified") {
    return (
      <StatusPill tone="verified">
        Verified · {grounded}/{total} figures
      </StatusPill>
    );
  }

  if (status === "partially_verified") {
    return (
      <div className="verification-partial">
        <StatusPill tone="partial">
          Partially verified · {grounded}/{total}
        </StatusPill>

        {unverified.length > 0 && (
          <small>
            Not matched to a source: {unverified.join(", ")}
          </small>
        )}
      </div>
    );
  }

  return <StatusPill tone="neutral">No figures to verify</StatusPill>;
}

function ElapsedSeconds({ startedAt }) {
  const [now, setNow] = useState(() => Date.now());

  useEffect(() => {
    const timer = setInterval(() => setNow(Date.now()), 1000);
    return () => clearInterval(timer);
  }, []);

  return <>{Math.max(0, Math.floor((now - startedAt) / 1000))} s</>;
}

function CopyButton({ text }) {
  const [copied, setCopied] = useState(false);

  async function copy() {
    try {
      await navigator.clipboard.writeText(text);
      setCopied(true);
      setTimeout(() => setCopied(false), 1800);
    } catch {
      setCopied(false);
    }
  }

  return (
    <button type="button" className="answer-action" onClick={copy}>
      <Icon name={copied ? "check" : "copy"} size={15} />
      {copied ? "Copied" : "Copy answer"}
    </button>
  );
}

function PendingAnswer({ turn, onCancel }) {
  return (
    <div className="assistant-message answer-pending" aria-live="polite">
      <div className="assistant-message-avatar">E</div>

      <div className="assistant-message-body">
        <span>Edith · Working on it</span>

        <div className="typing-dots" aria-hidden="true">
          <i />
          <i />
          <i />
        </div>

        <div className="evidence-placeholder">
          <div className="evidence-placeholder-top">
            <span>
              <Icon name="search" size={17} />
              Fetching figures and checking sources
            </span>

            <span className="pending-elapsed">
              <Icon name="clock" size={15} />
              <ElapsedSeconds startedAt={turn.startedAt} />
            </span>
          </div>

          <div className="evidence-skeleton wide" />
          <div className="evidence-skeleton" />

          <div className="pending-footer">
            <small>Usually 10-60 seconds; the first question may take 2-3 minutes.</small>

            <button
              type="button"
              className="button button-secondary pending-cancel"
              onClick={onCancel}
            >
              Cancel
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}

function ErrorAnswer({ turn, onRetry }) {
  return (
    <div className="assistant-message" role="alert">
      <div className="assistant-message-avatar">E</div>

      <div className="assistant-message-body">
        <span>Edith · {turn.cancelled ? "Cancelled" : "No answer"}</span>

        <div className="answer-error">
          <Icon name="shield" size={18} />
          <p>{turn.error}</p>
        </div>

        <button type="button" className="text-link answer-retry" onClick={onRetry}>
          Retry
          <Icon name="refresh" size={15} />
        </button>
      </div>
    </div>
  );
}

function AnswerMessage({ response }) {
  const {
    answer_markdown: markdown,
    verification,
    citations = [],
    steps = [],
    model,
    elapsed_seconds: elapsed,
  } = response;
  const warnings = verification?.warnings || [];

  return (
    <div className="assistant-message">
      <div className="assistant-message-avatar">E</div>

      <div className="assistant-message-body">
        <div className="answer-meta">
          <span>Edith</span>
          <VerificationBadge verification={verification} />
          <CopyButton text={markdown} />
        </div>

        {warnings.length > 0 && (
          <ul className="answer-warnings">
            {warnings.map((warning) => (
              <li key={warning}>
                <Icon name="shield" size={14} />
                {warning}
              </li>
            ))}
          </ul>
        )}

        <div className="answer-markdown">
          <ReactMarkdown remarkPlugins={[remarkGfm]} components={markdownComponents}>
            {markdown}
          </ReactMarkdown>
        </div>

        <div className="evidence-placeholder evidence-citations">
          <div className="evidence-placeholder-top">
            <span>
              <Icon name="file" size={17} />
              Supporting evidence
            </span>
          </div>

          {citations.length > 0 ? (
            <div className="citation-list">
              {citations.map((citation) => (
                <a
                  key={`${citation.report}-${citation.page_label || citation.pdf_page}`}
                  className="citation-chip"
                  href={citation.pdf_url}
                  target="_blank"
                  rel="noopener noreferrer"
                  title="Open the report at this page"
                >
                  <Icon name="file" size={14} />
                  {citationLabel(citation)}
                  <Icon name="external" size={13} />
                </a>
              ))}
            </div>
          ) : (
            <small>No report pages were cited for this answer.</small>
          )}
        </div>

        <details className="answer-steps">
          <summary>
            <Icon name="layers" size={15} />
            How this answer was produced
          </summary>

          {steps.length > 0 ? (
            <ol>
              {steps.map((step, index) => (
                <li key={`${step.tool}-${index}`}>
                  <b>{step.tool}</b>
                  {step.description}
                </li>
              ))}
            </ol>
          ) : (
            <p>No tools were needed for this answer.</p>
          )}

          <small>
            Model · {model} · {elapsed} s
          </small>
        </details>
      </div>
    </div>
  );
}

export default function AskPage({ setActivePage, chat }) {
  const [question, setQuestion] = useState("");
  const [sidebarCollapsed, setSidebarCollapsed] = useState(false);
  const chatContentRef = useRef(null);
  const textareaRef = useRef(null);

  const { conversations, active, activeId } = chat;
  const turns = active?.turns || [];
  const isPending = turns.some((turn) => turn.status === "pending");
  const lastTurn = turns[turns.length - 1];

  // The app area fills the viewport below the sticky header.
  useLayoutEffect(() => {
    const header = document.querySelector(".site-header");
    if (!header) return undefined;

    const root = document.documentElement;
    const update = () =>
      root.style.setProperty("--site-header-h", `${header.offsetHeight}px`);
    update();

    const observer = new ResizeObserver(update);
    observer.observe(header);
    return () => observer.disconnect();
  }, []);

  // Keep the newest message in view.
  useEffect(() => {
    const element = chatContentRef.current;
    if (!element || turns.length === 0) return;
    element.scrollTo({ top: element.scrollHeight, behavior: "smooth" });
  }, [activeId, turns.length, lastTurn?.status]);

  function askQuestion(value = question) {
    const trimmed = value.trim();
    if (!trimmed || isPending) return;

    chat.send(trimmed);
    setQuestion("");
  }

  function startNewConversation() {
    chat.startNew();
    setQuestion("");
    textareaRef.current?.focus();
  }

  function fillFollowUpExample() {
    setQuestion(FOLLOW_UP_EXAMPLE);
    textareaRef.current?.focus();
  }

  return (
    <main className="page inner-page ask-page">
      <div
        className={`ask-layout ${
          sidebarCollapsed ? "sidebar-collapsed" : ""
        }`}
      >
        <aside
          className="ask-sidebar"
          aria-label="Conversation sidebar"
        >
          <button
            type="button"
            className="sidebar-toggle"
            onClick={() =>
              setSidebarCollapsed((collapsed) => !collapsed)
            }
            aria-label={
              sidebarCollapsed ? "Expand sidebar" : "Collapse sidebar"
            }
            title={
              sidebarCollapsed ? "Expand sidebar" : "Collapse sidebar"
            }
          >
            {sidebarCollapsed ? "Show sidebar" : "Hide sidebar"}
          </button>

          <button
            type="button"
            className="new-chat sidebar-new-chat"
            onClick={startNewConversation}
            aria-label="Start a new conversation"
          >
            <span>+ New conversation</span>
            <Icon name="spark" size={16} />
          </button>

          <div className="sidebar-heading">
            <div className="sidebar-heading-icon">
              <Icon name="spark" size={19} />
            </div>

            <div>
              <h2>Explore a topic</h2>
              <p>Choose a prompt to get started.</p>
            </div>
          </div>

          <div className="suggestion-list">
            {suggestedQuestions.map((item) => (
              <button
                key={item.question}
                type="button"
                className={`suggestion-item ${item.note ? "suggestion-trick" : ""}`}
                onClick={() => askQuestion(item.question)}
                disabled={isPending}
                title={item.question}
              >
                <span>{item.category}</span>
                <strong>{item.label}</strong>
                {item.note && <small>{item.note}</small>}
                <Icon name="arrow" size={16} />
              </button>
            ))}
          </div>

          <button
            type="button"
            className="follow-up-hint"
            onClick={fillFollowUpExample}
          >
            <Icon name="spark" size={15} />
            <span>
              Follow-ups work. After a lookup, try <b>“{FOLLOW_UP_EXAMPLE}”</b>
            </span>
          </button>

          <div className="sidebar-info">
            <div className="sidebar-info-title">
              <Icon name="shield" size={18} />
              What Edith will show
            </div>

            <div className="sidebar-info-row">
              <span>Source</span>
              <b>Tata Steel reports</b>
            </div>

            <div className="sidebar-info-row">
              <span>Reference</span>
              <b>Report, year, page</b>
            </div>

            <div className="sidebar-info-row">
              <span>Evidence</span>
              <b>Links to the cited pages</b>
            </div>

            <div className="sidebar-info-row">
              <span>Status</span>
              <b>Verified / partially verified, with each figure checked</b>
            </div>
          </div>

          <div className="sidebar-recent">
            <div className="recent-heading">
              <span className="recent-dot" />
              <b>Recent conversations</b>
            </div>

            {conversations.length > 0 ? (
              <div className="recent-question-list">
                {conversations.map((conversation) => (
                  <button
                    type="button"
                    key={conversation.id}
                    className={`recent-question ${
                      activeId === conversation.id ? "active" : ""
                    }`}
                    onClick={() => chat.open(conversation.id)}
                    title={conversation.title}
                  >
                    {conversation.title}
                    {conversation.turns.length > 1 &&
                      ` · ${conversation.turns.length} questions`}
                  </button>
                ))}
              </div>
            ) : (
              <small className="recent-empty">
                Your questions will appear here after you start a
                conversation.
              </small>
            )}
          </div>
        </aside>

        <div className="ask-main">
          <div className="page-title-row">
            <div>
              <div className="page-overline">
                Tata Steel report assistant
              </div>

              <h1>Ask Edith</h1>

              <p>
                Ask about Tata Steel's financial reports and inspect the evidence
                that would support an answer.
              </p>
            </div>
          </div>

          <section className="chat-panel">
            <div className="chat-panel-header">
              <div className="chat-avatar">E</div>

              <div className="chat-header-copy">
                <strong>Edith</strong>
                <span>Report research assistant</span>
              </div>
            </div>

            <div className="chat-content" ref={chatContentRef}>
              {turns.length === 0 ? (
                <div className="welcome-message">
                  <div className="welcome-icon">
                    <Icon name="spark" size={24} />
                  </div>

                  <div>
                    <h2>Hello, I'm Edith.</h2>

                    <p>
                      Ask a question about Tata Steel's financial reports.
                      I'll look up the reported figures, work out what the
                      question needs, and show the pages each figure comes
                      from.
                    </p>

                    <div className="welcome-callout">
                      <Icon name="book" size={18} />

                      <ul>
                        <li>
                          {COVERAGE_TEXT} Consolidated and standalone.
                        </li>
                        <li>
                          Every figure in an answer is checked against its
                          source and cited to the report page.
                        </li>
                        <li>
                          Follow-up questions work, e.g. “{FOLLOW_UP_EXAMPLE}”
                          after a lookup.
                        </li>
                        <li>
                          Answers usually take 10-60 seconds; the first
                          question may take 2-3 minutes.
                        </li>
                      </ul>
                    </div>
                  </div>
                </div>
              ) : (
                <div className="conversation">
                  {turns.map((turn) => (
                    <div className="conversation-turn" key={turn.id}>
                      <div className="user-message">
                        <span>You</span>
                        <p>{turn.question}</p>
                      </div>

                      {turn.status === "pending" && (
                        <PendingAnswer
                          turn={turn}
                          onCancel={() => chat.cancel(turn.id)}
                        />
                      )}

                      {turn.status === "error" && (
                        <ErrorAnswer
                          turn={turn}
                          onRetry={() => chat.retry(active.id, turn.id)}
                        />
                      )}

                      {turn.status === "done" && turn.response && (
                        <AnswerMessage response={turn.response} />
                      )}
                    </div>
                  ))}
                </div>
              )}
            </div>

            <form
              className="chat-composer"
              onSubmit={(event) => {
                event.preventDefault();
                askQuestion();
              }}
            >
              <textarea
                ref={textareaRef}
                value={question}
                onChange={(event) => setQuestion(event.target.value)}
                onKeyDown={(event) => {
                  if (
                    event.key === "Enter" &&
                    !event.shiftKey &&
                    !event.nativeEvent.isComposing
                  ) {
                    event.preventDefault();
                    askQuestion();
                  }
                }}
                placeholder={
                  turns.length > 0
                    ? "Ask a follow-up question…"
                    : "Ask about Tata Steel's financial reports…"
                }
                rows={2}
                maxLength={2000}
                aria-label="Ask a question"
              />

              <div className="composer-bottom">
                <span>
                  <span className="composer-lock">
                    <Icon name="shield" size={13} />
                  </span>
                  Answers are verified against the source pages
                </span>

                <button
                  type="submit"
                  className="button button-primary"
                  disabled={!question.trim() || isPending}
                >
                  Send
                  <Icon name="arrow" size={16} />
                </button>
              </div>
            </form>
          </section>
        </div>
      </div>

      <div className="ask-page-links">
        <button
          className="text-link"
          onClick={() => setActivePage("Dashboard")}
        >
          Open financial dashboard
          <Icon name="arrow" size={15} />
        </button>

        <button
          className="text-link"
          onClick={() => setActivePage("Evaluation")}
        >
          See evaluation results
          <Icon name="arrow" size={15} />
        </button>
      </div>
    </main>
  );
}
```

---

## `frontend/src/components/DashboardPage.jsx`

```jsx
import { useState } from "react";
import {
  getFinancials,
  getMetrics,
  getRegions,
  getScores,
  getSegments,
  getStatements,
} from "../api.js";
import { VERDICT_QUESTION } from "./AskPage.jsx";
import {
  COMPARATIVE_NOTE,
  COMPARATIVE_YEAR,
  Icon,
  LoadError,
  Missing,
  NEEDS_PRIOR_YEAR_NOTE,
  REASON,
  RestatedMark,
  Sparkline,
  Value,
  YearLabel,
  formatChangePct,
  formatCrore,
  formatMetric,
  formatNumber,
  sentenceCase,
  useApi,
} from "./ui.jsx";

/* =========================================================
   DASHBOARD
   Every value comes from the API; the frontend only formats
   it and scales it to fit bars and charts.
   ========================================================= */

const FINANCIAL_ITEMS = [
  "revenue_from_operations",
  "profit_for_the_year",
  "net_cash_from_operating",
];

const metricCards = [
  { key: "revenue_from_operations", label: "Revenue from operations", icon: "chart" },
  { key: "profit_for_the_year", label: "Profit for the year", icon: "layers" },
  { key: "net_cash_from_operating", label: "Operating cash flow", icon: "book" },
  { key: "net_debt", label: "Net debt", icon: "shield" },
];

const RATIO_KEYS = [
  "current_ratio",
  "debt_to_equity",
  "interest_coverage",
  "net_profit_margin",
  "ebitda_margin",
  "roe",
];

const scoreRows = [
  {
    key: "altman_z",
    name: "Altman Z''",
    meaning: "Bankruptcy-risk score, book-equity variant.",
    decimals: 4,
  },
  {
    key: "piotroski_f",
    name: "Piotroski F",
    meaning: "Nine pass/fail checks of profitability, leverage, liquidity and efficiency (0-9).",
    decimals: 0,
  },
  {
    key: "beneish_m",
    name: "Beneish M",
    meaning: "Earnings-manipulation screen.",
    decimals: 4,
  },
];

const FALLBACK_YEARS = ["FY2021-22", "FY2022-23", "FY2023-24", "FY2024-25", "FY2025-26"];

// Region filter: the six geographic regions from /api/regions, in this order.
const REGION_KEYS = ["india", "netherlands", "uk", "europe", "south_east_asia", "rest_of_world"];

const GROUP_LEVEL_NOTE = "Group-level only: the reports don't break this down by region";

const statementRows = [
  ["profit_and_loss", "Income statement", "Revenue, costs, and profit"],
  ["balance_sheet", "Balance sheet", "Assets, liabilities, and equity"],
  ["cash_flow", "Cash flow statement", "Operating, investing, and financing cash flows"],
];

const RESTATED_SEGMENT_NOTE =
  "Restated: a later report presents a different figure for this year; the latest report's figure is shown.";

/* ---------------------------------------------------------
   Helpers
   --------------------------------------------------------- */

function lastYear(years) {
  return years?.[years.length - 1];
}

/** Why a year-on-year change is missing: FY2021-22 has no prior year. */
function missingChange(year) {
  return year === COMPARATIVE_YEAR
    ? { reason: REASON.noPriorYear, note: NEEDS_PRIOR_YEAR_NOTE }
    : { reason: REASON.notInReports };
}

// Europe was split into Netherlands and UK operations from this year.
const EUROPE_SPLIT_YEAR = "FY2024-25";

/** Why a segment has no value in a year (fiscal-year labels sort as text). */
function missingSegmentReason(segmentKey, year) {
  const beforeSplit = year < EUROPE_SPLIT_YEAR;

  if (["tata_steel_netherlands", "tata_steel_uk"].includes(segmentKey) && beforeSplit) {
    return REASON.withinEurope;
  }
  if (segmentKey === "tata_steel_europe" && !beforeSplit) return REASON.splitEurope;
  if (segmentKey === "tata_steel_long_products" && year > COMPARATIVE_YEAR) {
    return REASON.mergedIntoIndia;
  }
  return REASON.notASegment;
}

/** The small "Group-level only" note shown while a region is selected. */
function GroupLevelNote({ region }) {
  if (!region) return null;
  return (
    <span className="group-level-note" title={GROUP_LEVEL_NOTE}>
      <Icon name="layers" size={13} />
      {GROUP_LEVEL_NOTE}
    </span>
  );
}

/** One item's five years from /api/financials or /api/metrics. */
function buildSeries(key, financials, metrics, selectedYear) {
  if (key === "net_debt") {
    const metric = metrics?.metrics.find((item) => item.key === "net_debt");
    if (!metric) return null;

    return {
      years: metrics.years,
      points: metrics.years.map((year) => ({
        year,
        value: metric.values[year] ?? null,
        restated: false,
        source: "Borrowings + lease liabilities − cash, bank balances and current investments",
      })),
      yoy: null,
    };
  }

  const item = financials?.items[key];
  if (!item) return null;

  const year = selectedYear || lastYear(financials.years);

  return {
    years: financials.years,
    points: financials.years.map((year) => ({
      year,
      value: item.values[year]?.value ?? null,
      restated: Boolean(item.values[year]?.restated),
      source: item.values[year]?.source,
    })),
    yoy: item.yoy_changes.find((change) => change.to === year) || null,
  };
}

function zoneTone(scoreKey, result) {
  const label = (result?.interpretation || result?.zone || "").toLowerCase();

  if (scoreKey === "beneish_m") {
    return label.includes("flag") ? "distress" : "safe";
  }

  if (["safe", "strong"].includes(label)) return "safe";
  if (["grey", "average"].includes(label)) return "grey";
  if (["distress", "weak"].includes(label)) return "distress";
  return "neutral";
}

function zoneLabel(scoreKey, result) {
  const label = result?.interpretation || result?.zone || "";

  if (scoreKey === "altman_z") return label ? sentenceCase(`${label} zone`) : "";
  if (scoreKey === "beneish_m") {
    return label.toLowerCase().includes("flag") ? "Flag" : "No flag";
  }
  return sentenceCase(label);
}

function formatScore(row, score) {
  if (score == null) return null;
  return row.decimals === 0 ? `${score}/9` : formatNumber(score, row.decimals);
}

/** Round, "nice" gridline values for the chart (display scaling only). */
function niceStep(raw) {
  const exponent = Math.floor(Math.log10(raw));
  const base = 10 ** exponent;
  const fraction = raw / base;
  const nice =
    fraction <= 1 ? 1 : fraction <= 2 ? 2 : fraction <= 2.5 ? 2.5 : fraction <= 5 ? 5 : 10;
  return nice * base;
}

function chartScale(values) {
  let low = Math.min(...values);
  let high = Math.max(...values);

  if (low === high) {
    low -= Math.abs(low) * 0.1 || 1;
    high += Math.abs(high) * 0.1 || 1;
  }

  let step = niceStep((high - low) / 3);
  let start = Math.floor(low / step) * step;

  while (start + step * 3 < high) {
    step = niceStep(step * 1.01);
    start = Math.floor(low / step) * step;
  }

  return { start, step };
}

/* ---------------------------------------------------------
   Performance chart (Edith's chart style, real data)
   --------------------------------------------------------- */

const CHART_WIDTH = 700;
const CHART_HEIGHT = 250;
const GRID_Y = [195, 140, 85, 30]; // Edith's gridlines, bottom to top
const X_PAD = 36;

function PerformanceChart({ series, label, selectedYear }) {
  const [hovered, setHovered] = useState(null);
  const present = series.points.filter((point) => point.value != null);

  if (present.length === 0) {
    return (
      <div className="chart-area">
        <div className="chart-empty-overlay">
          <span className="chart-empty-icon">
            <Icon name="chart" size={24} />
          </span>
          <strong>Not reported</strong>
          <p>The reports contain no values for this item.</p>
        </div>
      </div>
    );
  }

  const { start, step } = chartScale(present.map((point) => point.value));
  const span = step * 3;
  const count = series.points.length;
  const xAt = (index) =>
    X_PAD + (index * (CHART_WIDTH - X_PAD * 2)) / Math.max(count - 1, 1);
  const yAt = (value) =>
    GRID_Y[0] - ((value - start) / span) * (GRID_Y[0] - GRID_Y[3]);

  const coords = series.points
    .map((point, index) =>
      point.value == null ? null : { ...point, index, x: xAt(index), y: yAt(point.value) },
    )
    .filter(Boolean);

  const line = coords
    .map((point, index) => {
      if (index === 0) return `M${point.x} ${point.y}`;
      const previous = coords[index - 1];
      const mid = (point.x - previous.x) / 2;
      return `C${previous.x + mid} ${previous.y} ${point.x - mid} ${point.y} ${point.x} ${point.y}`;
    })
    .join(" ");
  const first = coords[0];
  const last = coords[coords.length - 1];
  const area = `${line} L${last.x} 220 L${first.x} 220 Z`;
  const zeroY = start < 0 && start + span > 0 ? yAt(0) : null;
  const animationKey = `${label}-${coords.map((point) => point.value).join("|")}`;

  return (
    <>
      <div className="chart-area chart-live">
        <div className="chart-y-labels chart-y-live" aria-hidden="true">
          {GRID_Y.map((y, index) => (
            <span key={y} style={{ top: `${(y / CHART_HEIGHT) * 100}%` }}>
              {formatNumber(start + step * index, 0)}
            </span>
          ))}
        </div>

        <div className="chart-plot">
          <svg
            className="performance-chart"
            viewBox={`0 0 ${CHART_WIDTH} ${CHART_HEIGHT}`}
            preserveAspectRatio="none"
            role="img"
            aria-label={`${label}, INR crore, ${series.points
              .map((point) => `${point.year}: ${formatCrore(point.value)}`)
              .join("; ")}`}
          >
            <defs>
              <linearGradient id="chartFillGreen" x1="0" y1="0" x2="0" y2="1">
                <stop offset="0%" stopColor="#0f9b79" stopOpacity=".23" />
                <stop offset="100%" stopColor="#0f9b79" stopOpacity="0" />
              </linearGradient>

            </defs>

            {GRID_Y.map((y) => (
              <line
                key={y}
                x1="0"
                y1={y}
                x2={CHART_WIDTH}
                y2={y}
                className="chart-gridline"
              />
            ))}

            {zeroY != null && (
              <line
                x1="0"
                y1={zeroY}
                x2={CHART_WIDTH}
                y2={zeroY}
                className="chart-zero-line"
              />
            )}

            <path
              key={`area-${animationKey}`}
              d={area}
              fill="url(#chartFillGreen)"
              className="chart-area-fill"
            />

            <path
              key={`line-${animationKey}`}
              d={line}
              fill="none"
              stroke="#0d9d79"
              strokeWidth="3.5"
              strokeLinecap="round"
              vectorEffect="non-scaling-stroke"
              className="chart-line-animated"
            />
          </svg>

          {coords.map((point) => (
            <button
              type="button"
              key={point.year}
              className={`chart-point ${point.year === selectedYear ? "selected" : ""} ${
                hovered === point.index ? "active" : ""
              }`}
              style={{
                left: `${(point.x / CHART_WIDTH) * 100}%`,
                top: `${(point.y / CHART_HEIGHT) * 100}%`,
              }}
              onMouseEnter={() => setHovered(point.index)}
              onMouseLeave={() => setHovered(null)}
              onFocus={() => setHovered(point.index)}
              onBlur={() => setHovered(null)}
              aria-label={`${point.year}: ${formatCrore(point.value)} crore`}
            />
          ))}

          {coords
            .filter((point) => point.year === selectedYear && hovered !== point.index)
            .map((point) => (
              <span
                key={`label-${point.year}`}
                className={`chart-point-label ${point.x > CHART_WIDTH * 0.8 ? "align-right" : ""} ${
                  point.y < CHART_HEIGHT * 0.3 ? "below" : ""
                }`}
                style={{
                  left: `${(point.x / CHART_WIDTH) * 100}%`,
                  top: `${(point.y / CHART_HEIGHT) * 100}%`,
                }}
                aria-hidden="true"
              >
                ₹ {formatCrore(point.value)} cr
              </span>
            ))}

          {hovered != null && coords.find((point) => point.index === hovered) && (
            <ChartTooltip point={coords.find((point) => point.index === hovered)} />
          )}
        </div>
      </div>

      <div className="chart-x-labels chart-x-live">
        <div className="chart-x-track">
          {series.points.map((point, index) => (
            <span
              key={point.year}
              className={point.year === selectedYear ? "selected" : ""}
              style={{ left: `${(xAt(index) / CHART_WIDTH) * 100}%` }}
            >
              <YearLabel year={point.year} />
            </span>
          ))}
        </div>
      </div>
    </>
  );
}

function ChartTooltip({ point }) {
  const alignRight = point.x > CHART_WIDTH * 0.7;

  return (
    <div
      className={`chart-tooltip ${alignRight ? "align-right" : ""}`}
      style={{
        left: `${(point.x / CHART_WIDTH) * 100}%`,
        top: `${(point.y / CHART_HEIGHT) * 100}%`,
      }}
      role="status"
    >
      <small>{point.year}</small>
      <strong>
        ₹ {formatCrore(point.value)} cr
        {point.restated && <RestatedMark />}
      </strong>
      {point.source && <span>{point.source}</span>}
    </div>
  );
}

/* ---------------------------------------------------------
   Region view (from /api/regions; all arithmetic in the backend)
   --------------------------------------------------------- */

function regionYearsText(region, years) {
  const present = years.filter((year) => region.values[year]);
  if (present.length === 0) return "no year";
  return present.length === 1
    ? present[0]
    : `${present[0]} to ${present[present.length - 1]}`;
}

/** Where a region's figures are when it was not reported in a year. */
function regionAbsence(region, year) {
  const beforeSplit = year < EUROPE_SPLIT_YEAR;
  const until = "FY2023-24";

  if (region.key === "uk" && beforeSplit) {
    return {
      text: `The UK was reported within Tata Steel Europe until ${until}`,
      links: [["europe", "Europe"]],
    };
  }
  if (region.key === "netherlands" && beforeSplit) {
    return {
      text: `The Netherlands was reported within Tata Steel Europe until ${until}`,
      links: [["europe", "Europe"]],
    };
  }
  if (region.key === "europe" && !beforeSplit) {
    return {
      text: `Tata Steel Europe is reported as Netherlands and UK operations from ${EUROPE_SPLIT_YEAR}`,
      links: [
        ["netherlands", "Netherlands"],
        ["uk", "UK"],
      ],
    };
  }
  return { text: `${region.name} is not a segment in ${year}`, links: [] };
}

function RegionView({ region, years, year, onSelectRegion }) {
  const [item, setItem] = useState("segment_revenue");
  const values = region.values[year];
  const absentNote = `${region.name} is reported only for ${regionYearsText(region, years)}`;
  const absence = values ? null : regionAbsence(region, year);
  const pct = (value) => (value == null ? null : `${formatNumber(value, 2)}%`);

  const stats = [
    { label: "Revenue (segment)", value: values?.segment_revenue, crore: true },
    { label: "EBITDA", value: values?.ebitda, crore: true },
    { label: "EBITDA margin", value: pct(values?.ebitda_margin_pct) },
    {
      label: "Share of group revenue",
      value: pct(values?.share_of_group_external_revenue_pct),
      note: "External revenue as a share of the group's external revenue",
    },
    {
      label: "Share of group EBITDA",
      value: pct(values?.share_of_group_ebitda_pct),
      note: "Share of the group's EBITDA after inter-segment eliminations",
    },
  ];

  const sourceText = (fy) =>
    (region.values[fy]?.sources || [])
      .map((source) => `${source.report} report, page ${source.page_label}`)
      .join("; ");

  const series = {
    years,
    points: years.map((fy) => ({
      year: fy,
      value: region.values[fy]?.[item] ?? null,
      restated: Object.values(region.values[fy]?.restated || {}).some((items) =>
        items.includes(item),
      ),
      source: sourceText(fy),
    })),
  };

  return (
    <section className="dashboard-panel region-panel">
      <div className="panel-heading">
        <div>
          <h2>Region view: {region.name}</h2>
          <p>
            Consolidated segment note · <YearLabel year={year} /> · INR crore
            {values?.components?.length > 0 &&
              ` · Includes ${values.components.map((component) => component.name).join(", ")}`}
          </p>
        </div>

        <span className="panel-icon">
          <Icon name="layers" size={20} />
        </span>
      </div>

      {absence ? (
        <div className="region-absent" role="note">
          <Icon name="layers" size={18} />
          <span>{absence.text}.</span>

          {absence.links.length > 0 && (
            <span className="region-absent-actions">
              {absence.links.map(([key, name]) => (
                <button
                  key={key}
                  type="button"
                  className="button button-secondary"
                  onClick={() => onSelectRegion(key)}
                >
                  View {name} for {year}
                  <Icon name="arrow" size={15} />
                </button>
              ))}
            </span>
          )}
        </div>
      ) : (
      <div className="region-stats">
        {stats.map((stat) => (
          <div className="region-stat" key={stat.label} title={stat.note}>
            <span>{stat.label}</span>
            <strong>
              {stat.value == null ? (
                <Missing note={absentNote} />
              ) : stat.crore ? (
                <>
                  <small>₹</small> {formatCrore(stat.value)} <small>cr</small>
                </>
              ) : (
                stat.value
              )}
            </strong>
          </div>
        ))}
      </div>
      )}

      <div className="region-trend">
        <div className="chart-legend">
          <span>
            <i className="legend-dot green" />
            {item === "ebitda" ? "EBITDA" : "Revenue (segment)"}
          </span>

          <span>
            <i className="legend-dot blue" />
            Selected year: {year}
          </span>

          <div className="segmented-control">
            {[
              ["segment_revenue", "Revenue"],
              ["ebitda", "EBITDA"],
            ].map(([key, label]) => (
              <button
                key={key}
                className={item === key ? "selected" : ""}
                onClick={() => setItem(key)}
              >
                {label}
              </button>
            ))}
          </div>
        </div>

        <PerformanceChart
          series={series}
          label={`${region.name} ${item === "ebitda" ? "EBITDA" : "revenue"}`}
          selectedYear={year}
        />
      </div>

      <p className="panel-footnote region-sources">
        {values?.sources?.length > 0 && "Sources: "}
        {values?.sources?.length > 0 &&
          values.sources.map((source) => (
            <a
              key={`${source.report}-${source.page_label}`}
              href={source.url}
              target="_blank"
              rel="noopener noreferrer"
              title="Open the report at this page"
            >
              {source.report} report, page {source.page_label}
              <Icon name="external" size={12} />
            </a>
          ))}
        {values?.sources?.length > 0 && " "}Hover a point for the source of each year. Shares use the group
        total after inter-segment eliminations, so a loss-making region has a
        negative EBITDA share.
      </p>
    </section>
  );
}

/* ---------------------------------------------------------
   Page
   --------------------------------------------------------- */

export default function DashboardPage({ setActivePage, onAskEdith }) {
  const [basis, setBasis] = useState("Consolidated");
  const [selectedYear, setSelectedYear] = useState(null);
  const [regionKey, setRegionKey] = useState("all");
  const [activeMetric, setActiveMetric] = useState("revenue_from_operations");
  const [segmentItem, setSegmentItem] = useState("segment_revenue");

  const scope = basis.toLowerCase();

  const financials = useApi(() => getFinancials(FINANCIAL_ITEMS, scope), `financials-${scope}`);
  const metrics = useApi(() => getMetrics(scope), `metrics-${scope}`);
  const scores = useApi(() => getScores(scope), `scores-${scope}`);
  const segments = useApi(getSegments, "segments");
  const statements = useApi(() => getStatements(scope), `statements-${scope}`);
  const regions = useApi(getRegions, "regions");

  const years = financials.data?.years || metrics.data?.years || FALLBACK_YEARS;
  const year = selectedYear || lastYear(years);
  const regionOptions = REGION_KEYS.map((key) =>
    regions.data?.regions.find((region) => region.key === key),
  ).filter(Boolean);
  const region =
    regionKey === "all" ? null : regionOptions.find((item) => item.key === regionKey);

  const activeCard = metricCards.find((card) => card.key === activeMetric);
  const activeSeries = buildSeries(activeMetric, financials.data, metrics.data, year);
  const activeLoading = activeMetric === "net_debt" ? metrics.loading : financials.loading;
  const activeError = activeMetric === "net_debt" ? metrics.error : financials.error;
  const activeRetry = activeMetric === "net_debt" ? metrics.retry : financials.retry;
  const selectedCol = (fy) => (fy === year ? "selected-year" : undefined);

  return (
    <main className="page inner-page dashboard-page">

      <div className="page-title-row">

        <div>
          <div className="page-overline">
            Tata Steel · Financial overview
          </div>

          <h1>Dashboard</h1>

          <p>
            A working view of statements, financial trends and key ratios.
          </p>
        </div>


      </div>


      <div className="dashboard-controls">

        <div className="control-group">

          <label>Reporting basis</label>

          <div className="segmented-control">

            {["Consolidated", "Standalone"].map((item) => (

              <button
                key={item}
                className={basis === item ? "selected" : ""}
                onClick={() => setBasis(item)}
              >
                {item}
              </button>

            ))}

          </div>

        </div>


        <div className="control-group">

          <label htmlFor="dashboard-year">Year</label>

          <div className="select-control">
            <select
              id="dashboard-year"
              value={year}
              onChange={(event) => setSelectedYear(event.target.value)}
            >
              {years.map((item) => (
                <option key={item} value={item}>
                  {item}
                  {item === COMPARATIVE_YEAR ? " (comparative column)" : ""}
                </option>
              ))}
            </select>
          </div>

        </div>


        <div className="control-group">

          <label htmlFor="dashboard-region">Region</label>

          <div className="select-control">
            <select
              id="dashboard-region"
              value={regionKey}
              onChange={(event) => setRegionKey(event.target.value)}
              disabled={!regions.data}
            >
              <option value="all">All regions</option>
              {regionOptions.map((item) => (
                <option key={item.key} value={item.key}>
                  {item.name}
                </option>
              ))}
            </select>
          </div>

        </div>


        <div className="control-note">
          <span className="live-indicator" />
          Showing {basis.toLowerCase()} view · <YearLabel year={year} />
        </div>

      </div>

      {regions.error && (
        <LoadError error={regions.error} onRetry={regions.retry} compact />
      )}

      {region && regions.data && (
        <RegionView
          region={region}
          years={regions.data.years}
          year={year}
          onSelectRegion={setRegionKey}
        />
      )}

      {region && (
        <div className="group-level-row">
          <GroupLevelNote region={region} />
        </div>
      )}

      <div className="metric-grid">

        {metricCards.map((card) => {
          const series = buildSeries(card.key, financials.data, metrics.data, year);
          const loading = card.key === "net_debt" ? metrics.loading : financials.loading;
          const failed = card.key === "net_debt" ? metrics.error : financials.error;
          const point = series?.points.find((item) => item.year === year);

          return (

            <button
              key={card.key}
              className={`metric-card ${
                activeMetric === card.key ? "metric-active" : ""
              }`}
              onClick={() => setActiveMetric(card.key)}
              title={point?.source}
            >

              <div className="metric-card-top">

                <span>{card.label}</span>

                <span className="metric-card-icon">
                  <Icon name={card.icon} size={18} />
                </span>

              </div>

              {loading ? (
                <strong className="metric-value-skeleton" />
              ) : failed || !point ? (
                <strong className="metric-value">
                  <Value value={null} />
                </strong>
              ) : (
                <strong className="metric-value">
                  <small>₹</small>
                  <Value value={point.value} restated={point.restated} />
                  <small>cr</small>
                </strong>
              )}

              <div className="metric-card-bottom">
                {loading ? (
                  <span>Loading {year}…</span>
                ) : failed ? (
                  <span>Could not load</span>
                ) : series?.yoy ? (
                  <span
                    className={`metric-change ${
                      series.yoy.change_pct < 0 ? "down" : "up"
                    }`}
                    title={`Change ${formatCrore(series.yoy.change)} crore from ${series.yoy.from} to ${series.yoy.to}`}
                  >
                    {formatChangePct(series.yoy.change_pct)} vs {series.yoy.from}
                    {series.yoy.restated_basis && (
                      <RestatedMark note="Compared on a restated basis: the prior year as presented in the latest report." />
                    )}
                  </span>
                ) : card.key !== "net_debt" && series ? (
                  <span>
                    YoY <Missing {...missingChange(year)} />
                  </span>
                ) : (
                  <span>
                    <YearLabel year={year} /> · 5-year trend
                  </span>
                )}

                {card.key === "net_debt" && series ? (
                  <Sparkline
                    values={series.points.map((item) => item.value)}
                    highlightIndex={series.years.indexOf(year)}
                    width={72}
                    height={24}
                    label="Net debt, five-year trend"
                  />
                ) : (
                  <span className="metric-mini-line" />
                )}
              </div>

            </button>

          );
        })}

      </div>

      {(financials.error || metrics.error) && (
        <LoadError
          error={financials.error || metrics.error}
          onRetry={() => {
            if (financials.error) financials.retry();
            if (metrics.error) metrics.retry();
          }}
        />
      )}


      <div className="dashboard-main-grid">

        <section className="dashboard-panel performance-panel">

          <div className="panel-heading">

            <div>
              <h2>Financial performance</h2>
              <p>
                {activeCard?.label} · {basis} · {years[0]} to {lastYear(years)}
              </p>
              <GroupLevelNote region={region} />
            </div>


          </div>


          <div className="chart-legend">
            <span>
              <i className="legend-dot green" />
              {activeCard?.label}
            </span>

            <span>
              <i className="legend-dot blue" />
              Selected year: {year}
            </span>

            <span className="chart-period-note">
              INR crore · hover a point for its value and source
            </span>
          </div>

          {activeLoading ? (
            <div className="chart-area">
              <div className="chart-empty-overlay">
                <span className="chart-empty-icon">
                  <Icon name="chart" size={24} />
                </span>
                <strong>Loading figures…</strong>
              </div>
            </div>
          ) : activeError || !activeSeries ? (
            <LoadError error={activeError} onRetry={activeRetry} compact />
          ) : (
            <PerformanceChart
              series={activeSeries}
              label={activeCard?.label}
              selectedYear={year}
            />
          )}

        </section>


        <section className="dashboard-panel ratios-panel">

          <div className="panel-heading">

            <div>
              <h2>Financial ratios</h2>
              <p>Calculated from verified statement inputs.</p>
              <GroupLevelNote region={region} />
            </div>

            <span className="panel-icon">
              <Icon name="layers" size={20} />
            </span>

          </div>


          <div className="ratio-list">

            {metrics.loading &&
              RATIO_KEYS.map((key) => (
                <div className="ratio-item" key={key}>
                  <div className="ratio-topline">
                    <span className="metric-value-skeleton ratio-skeleton" />
                  </div>
                  <div className="ratio-track" />
                </div>
              ))}

            {metrics.error && (
              <LoadError error={metrics.error} onRetry={metrics.retry} compact />
            )}

            {metrics.data &&
              RATIO_KEYS.map((key) => {
                const metric = metrics.data.metrics.find((item) => item.key === key);
                if (!metric) return null;

                const metricYears = metrics.data.years;
                const values = metricYears.map((fy) => metric.values[fy] ?? null);
                const selectedValue = metric.values[year] ?? null;
                const largest = Math.max(
                  ...values.filter((value) => value != null).map(Math.abs),
                );
                const width =
                  selectedValue == null || !largest
                    ? 0
                    : (Math.abs(selectedValue) / largest) * 100;

                return (

                  <div className="ratio-item" key={key}>

                    <div className="ratio-topline">
                      <span title={metric.formula}>{metric.name}</span>
                      <strong>
                        <Value
                          value={selectedValue}
                          missingReason={
                            year === COMPARATIVE_YEAR ? REASON.noPriorYear : REASON.notInReports
                          }
                          missingNote={
                            year === COMPARATIVE_YEAR
                              ? "Needs the average of FY2020-21 and FY2021-22 equity; FY2020-21 is outside the four reports"
                              : undefined
                          }
                          format={(value) =>
                            formatMetric(value, metric.unit, metric.decimals)
                          }
                        />
                      </strong>
                    </div>

                    <div className="ratio-track">
                      <i
                        className={selectedValue < 0 ? "negative" : ""}
                        style={{
                          width: `${width}%`,
                        }}
                      />
                    </div>

                    <div className="ratio-footline">
                      <small>
                        {year} · {metric.higher_is_better ? "higher" : "lower"} is
                        better
                      </small>
                      <Sparkline
                        values={values}
                        highlightIndex={metricYears.indexOf(year)}
                        width={96}
                        height={26}
                        label={`${metric.name}, ${metricYears[0]} to ${lastYear(metricYears)}: ${values
                          .map((value) => formatMetric(value, metric.unit, metric.decimals))
                          .join(", ")}`}
                      />
                    </div>

                  </div>

                );
              })}

          </div>

          {metrics.data && (
            <p className="panel-footnote">
              Bars compare the {year} value with the ratio's own 5-year high;
              the line shows {metrics.data.years[0]} to {lastYear(metrics.data.years)},
              with {year} marked.
            </p>
          )}

        </section>

      </div>


      <div className="dashboard-main-grid dashboard-insight-grid">

        <section className="dashboard-panel scores-panel">

          <div className="panel-heading">

            <div>
              <h2>Composite scores</h2>
              <p>
                {basis} · Altman Z'', Piotroski F and Beneish M for each year,
                computed from the reported statements.
              </p>
              <GroupLevelNote region={region} />
            </div>

            <span className="panel-icon">
              <Icon name="check" size={20} />
            </span>

          </div>

          {scores.loading && <div className="evidence-skeleton wide" />}

          {scores.error && (
            <LoadError error={scores.error} onRetry={scores.retry} compact />
          )}

          {scores.data && (
            <>
              <div className="table-scroll">
                <table className="data-table scores-table">
                  <thead>
                    <tr>
                      <th scope="col">Score</th>
                      {scores.data.years.map((fy) => (
                        <th scope="col" key={fy} className={selectedCol(fy)}>
                          <YearLabel year={fy} />
                        </th>
                      ))}
                    </tr>
                  </thead>

                  <tbody>
                    {scoreRows.map((row) => {
                      const results = scores.data.scores[row.key] || {};
                      const thresholds = Object.values(results).find(
                        (result) => result?.thresholds,
                      )?.thresholds;

                      return (
                        <tr key={row.key}>
                          <th scope="row">
                            <strong>{row.name}</strong>
                            <small>
                              {row.meaning}
                              {thresholds && ` ${thresholds}.`}
                            </small>
                          </th>

                          {scores.data.years.map((fy) => {
                            const result = results[fy];
                            const tone = zoneTone(row.key, result);

                            return (
                              <td key={fy} className={selectedCol(fy)}>
                                {result?.score == null ? (
                                  <Missing
                                    reason={
                                      fy === COMPARATIVE_YEAR && row.key !== "altman_z"
                                        ? REASON.needsPriorYear
                                        : REASON.notInReports
                                    }
                                    note={
                                      fy === COMPARATIVE_YEAR
                                        ? NEEDS_PRIOR_YEAR_NOTE
                                        : sentenceCase(result?.reason)
                                    }
                                  />
                                ) : (
                                  <>
                                    <b>{formatScore(row, result.score)}</b>
                                    <span className={`zone-chip ${tone}`}>
                                      {zoneLabel(row.key, result)}
                                    </span>
                                  </>
                                )}
                              </td>
                            );
                          })}
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>

              <p className="panel-footnote">
                Altman Z'' uses the actual retained earnings from each report's
                "Other equity" note (verified on the page) and book equity in
                place of market value. FY2021-22 comes from the FY2022-23
                report's comparative column; Piotroski F and Beneish M compare
                with the prior year, so they need FY2020-21, which is outside
                the four reports.
                <button
                  type="button"
                  className="text-link"
                  onClick={() => setActivePage("Sources")}
                >
                  How these are calculated
                  <Icon name="arrow" size={14} />
                </button>
              </p>
            </>
          )}

        </section>


        <section className="dashboard-panel health-panel">

          <div className="panel-heading">

            <div>
              <h2>Financial health summary</h2>
              <p>
                {basis} · {year} · values exactly as the API reports them.
              </p>
              <GroupLevelNote region={region} />
            </div>

            <span className="panel-icon">
              <Icon name="shield" size={20} />
            </span>

          </div>

          <HealthSummary
            financials={financials}
            metrics={metrics}
            scores={scores}
            year={year}
          />

          <button
            type="button"
            className="button button-primary health-ask"
            onClick={() => onAskEdith(VERDICT_QUESTION)}
          >
            Ask Edith for the full verdict
            <Icon name="arrow" size={16} />
          </button>

        </section>

      </div>


      <section className="dashboard-panel segments-panel">

        <div className="panel-heading">

          <div>
            <h2>Segments</h2>
            <p>
              Consolidated only: segments are reported in the consolidated
              statements, so this card does not change with the basis toggle.
              INR crore.
            </p>
          </div>

          <div className="segmented-control">
            {[
              ["segment_revenue", "Revenue"],
              ["segment_results", "EBITDA"],
            ].map(([key, label]) => (
              <button
                key={key}
                className={segmentItem === key ? "selected" : ""}
                onClick={() => setSegmentItem(key)}
              >
                {label}
              </button>
            ))}
          </div>

        </div>

        {segments.loading && <div className="evidence-skeleton wide" />}

        {segments.error && (
          <LoadError error={segments.error} onRetry={segments.retry} compact />
        )}

        {segments.data && (
          <>
            <div className="table-scroll">
              <table className="data-table segments-table">
                <thead>
                  <tr>
                    <th scope="col">
                      {segmentItem === "segment_results"
                        ? "Segment EBITDA (segment results)"
                        : "Segment revenue"}
                    </th>
                    {segments.data.years.map((fy) => (
                      <th scope="col" key={fy} className={selectedCol(fy)}>
                        <YearLabel year={fy} />
                      </th>
                    ))}
                  </tr>
                </thead>

                <tbody>
                  {[
                    ...segments.data.segments,
                    { ...segments.data.eliminations, rowClass: "subtotal-row" },
                    { ...segments.data.totals, rowClass: "total-row" },
                  ].map((segment) => (
                    <tr key={segment.key} className={segment.rowClass || ""}>
                      <th scope="row">{segment.name}</th>

                      {segments.data.years.map((fy) => {
                        const value = segment.values?.[fy]?.[segmentItem];
                        const source = segment.sources?.[fy];
                        const restated = segment.restated?.[fy]?.includes(segmentItem);

                        return (
                          <td
                            key={fy}
                            className={[value < 0 ? "negative" : "", selectedCol(fy) || ""]
                              .join(" ")
                              .trim() || undefined}
                            title={
                              source && value != null
                                ? `${source.report} report, page ${source.page_label}`
                                : undefined
                            }
                          >
                            <Value
                              value={value}
                              restated={restated}
                              restatedNote={RESTATED_SEGMENT_NOTE}
                              missingReason={missingSegmentReason(segment.key, fy)}
                            />
                          </td>
                        );
                      })}
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>

            <p className="panel-footnote">
              {segments.data.note} Tata Steel Europe was reported until
              FY2023-24 and is split into Netherlands and UK operations from
              FY2024-25; Tata Steel Long Products (FY2021-22) was merged into
              Tata Steel India. A grey note replaces the value where a segment was
              not reported that year. <RestatedMark note={RESTATED_SEGMENT_NOTE} /> marks a
              restated value.
            </p>
          </>
        )}

      </section>


      <section className="dashboard-panel statement-panel statement-panel-full">

        <div className="panel-heading">

          <div>
            <h2>Statement coverage</h2>
            <p>
              {basis} primary statements behind this dashboard. Each chip opens
              only that statement's pages from the annual report.
            </p>
          </div>


        </div>


        {statementRows.map(([key, name, detail]) => (

          <div className="statement-row" key={key}>

            <span className="statement-icon">
              <Icon name="file" size={18} />
            </span>

            <div>
              <strong>{name}</strong>
              <small>{detail}</small>

              {statements.data && (
                <span className="report-links">
                  {statements.data.years.map((fy) => {
                    const entry = statements.data.statements[fy]?.[key];
                    if (!entry) return null;

                    const pages = entry.page_labels.join("-");
                    const title = `${name}, ${fy} (${scope}): ${entry.report} report, ${
                      entry.page_labels.length > 1 ? "pages" : "page"
                    } ${entry.page_labels.join(", ")}${
                      fy === COMPARATIVE_YEAR ? `. ${COMPARATIVE_NOTE}` : ""
                    }`;

                    return (
                      <a
                        key={fy}
                        className={selectedCol(fy)}
                        href={entry.url}
                        target="_blank"
                        rel="noopener noreferrer"
                        title={title}
                      >
                        <YearLabel year={fy} />
                        <em>{pages}</em>
                        <Icon name="external" size={12} />
                      </a>
                    );
                  })}
                </span>
              )}
            </div>


          </div>

        ))}

        {statements.loading && <div className="evidence-skeleton wide" />}

        {statements.error && (
          <LoadError error={statements.error} onRetry={statements.retry} compact />
        )}

      </section>

    </main>
  );
}

/* ---------------------------------------------------------
   Financial health summary: a factual list, no narrative
   --------------------------------------------------------- */

function HealthSummary({ financials, metrics, scores, year }) {
  if (financials.loading || metrics.loading || scores.loading) {
    return (
      <div className="health-list">
        <div className="evidence-skeleton wide" />
        <div className="evidence-skeleton" />
        <div className="evidence-skeleton wide" />
      </div>
    );
  }

  const failed = financials.error || metrics.error || scores.error;
  if (failed) {
    return (
      <LoadError
        error={failed}
        onRetry={() => {
          if (financials.error) financials.retry();
          if (metrics.error) metrics.retry();
          if (scores.error) scores.retry();
        }}
        compact
      />
    );
  }

  const altman = scores.data.scores.altman_z?.[year];
  const piotroski = scores.data.scores.piotroski_f?.[year];
  const metric = (key) => metrics.data.metrics.find((item) => item.key === key);
  const currentRatio = metric("current_ratio");
  const debtToEquity = metric("debt_to_equity");
  const netDebt = metric("net_debt");
  const profit = financials.data.items.profit_for_the_year;
  const profitChange = profit?.yoy_changes.find((change) => change.to === year);

  const rows = [
    {
      label: `Altman Z'' (${year})`,
      value: altman?.score == null ? null : formatNumber(altman.score, 4),
      chip: altman?.score != null && zoneLabel("altman_z", altman),
      tone: zoneTone("altman_z", altman),
    },
    {
      label: `Piotroski F (${year})`,
      value: piotroski?.score == null ? null : `${piotroski.score}/9`,
      chip: sentenceCase(piotroski?.interpretation),
      tone: zoneTone("piotroski_f", piotroski),
      missingReason: year === COMPARATIVE_YEAR ? REASON.needsPriorYear : undefined,
      missingNote: year === COMPARATIVE_YEAR ? NEEDS_PRIOR_YEAR_NOTE : undefined,
    },
    {
      label: `Current ratio (${year})`,
      value: formatMetric(currentRatio?.values[year], "x", currentRatio?.decimals),
      raw: currentRatio?.values[year],
    },
    {
      label: `Debt-to-equity (${year})`,
      value: formatMetric(debtToEquity?.values[year], "x", debtToEquity?.decimals),
      raw: debtToEquity?.values[year],
    },
    {
      label: `Net debt (${year})`,
      value:
        netDebt?.values[year] == null
          ? null
          : `₹ ${formatCrore(netDebt.values[year])} cr`,
    },
    {
      label: `Profit for the year (${year})`,
      value:
        profit?.values[year]?.value == null
          ? null
          : `₹ ${formatCrore(profit.values[year].value)} cr`,
      chip: profitChange && `${formatChangePct(profitChange.change_pct)} YoY`,
      tone: profitChange ? (profitChange.change_pct < 0 ? "distress" : "safe") : null,
    },
  ];

  return (
    <ul className="health-list">
      {rows.map((row) => (
        <li key={row.label}>
          <span>{row.label}</span>
          <strong>
            {row.value == null || ("raw" in row && row.raw == null) ? (
              <Missing reason={row.missingReason} note={row.missingNote} />
            ) : (
              row.value
            )}
          </strong>
          {row.chip && <span className={`zone-chip ${row.tone || "neutral"}`}>{row.chip}</span>}
        </li>
      ))}
    </ul>
  );
}
```

---

## `frontend/src/components/EvaluationPage.jsx`

```jsx
import { useState } from "react";
import { getEvaluation } from "../api.js";
import {
  Icon,
  LoadError,
  Missing,
  REASON,
  SectionHeading,
  formatRunDate,
  useApi,
} from "./ui.jsx";

/* =========================================================
   EVALUATION
   Figures come from /api/evaluation (latest full run).
   ========================================================= */

const categoryLabels = {
  lookup: "Lookup",
  table_grounded: "Table grounded",
  trend: "Trend",
  ratio: "Ratio",
  yoy: "Year on year",
  composite: "Composite",
  segment: "Segment",
  follow_up: "Follow-up",
  narrative: "Narrative",
  risk_evolution: "Risk evolution",
  scope_trap: "Scope trap",
  abstain: "Abstain",
  verdict: "Verdict",
};

// Hand-graded known limitations (eval/EVALUATION_NOTES.md).
const flaggedAnswers = [
  {
    id: "G1",
    title: "Risk evolution",
    grade: "Correct method, unreliable conclusions",
    detail:
      "Compares the named risks in the Integrated Report risk sections, but called some risks \"new in FY26\" that the FY2022-23 report also discusses (regulatory risk, employee well-being, R&D) and misreported its own search results.",
  },
  {
    id: "G2",
    title: "UK losses and restructuring",
    grade: "Partial",
    detail:
      "Correct UK segment figures and UK government support, but attributed India's new labour-code charge to the UK, linked exceptional provisions to segment results (which exclude them) and omitted the electric-arc-furnace transition.",
  },
];

function categoryLabel(category) {
  return categoryLabels[category] || category.replace(/_/g, " ");
}

function isFull(fraction) {
  if (fraction == null) return true;
  const [found, total] = String(fraction).split("/").map(Number);
  return found === total;
}

/** A record passes when every automated check that applies to it is complete. */
function passes(record) {
  return (
    record.abstention_ok !== false &&
    isFull(record.numeric) &&
    isFull(record.grounded) &&
    isFull(record.mentions)
  );
}

function ratioOf(fraction) {
  const [found, total] = String(fraction || "").split("/").map(Number);
  return total ? found / total : 0;
}

function formatRate(value) {
  return typeof value === "number" ? value.toFixed(2) : "not recorded";
}

export default function EvaluationPage() {
  const [selectedCategory, setSelectedCategory] =
    useState("All categories");

  const evaluation = useApi(getEvaluation, "evaluation");
  const data = evaluation.data;
  const available = data?.available;
  const summary = data?.summary || {};
  const records = data?.records || [];
  const retrieval = summary.tier1_filtered_retrieval || {};

  const categories = [
    "All categories",
    ...records.reduce(
      (list, record) =>
        list.includes(record.category) ? list : [...list, record.category],
      [],
    ),
  ];

  const measures = [
    {
      title: "Numeric accuracy",
      description:
        "Compare extracted values with reviewed reference answers.",
      icon: "chart",
      value: summary.numeric_questions_fully_correct,
      detail: `numeric questions fully correct · ${summary.expected_numbers_found || "not recorded"} expected numbers found`,
    },
    {
      title: "Citation correctness",
      description:
        "Check whether each citation points to the right report and page.",
      icon: "file",
      value: summary.expected_pages_cited,
      detail: "expected pages cited",
    },
    {
      title: "Groundedness",
      description:
        "Assess whether the response is supported by retrieved report text.",
      icon: "shield",
      value: summary.answers_fully_grounded,
      detail: "answers fully grounded (every figure matched to its source)",
    },
    {
      title: "Retrieval quality",
      description:
        "Measure whether relevant passages are found for each question.",
      icon: "search",
      value: `${formatRate(retrieval["hit_rate@4"])} / ${formatRate(retrieval.mrr)}`,
      detail: `Hit Rate@4 / MRR · source pages retrieved: ${summary.source_pages_retrieved || "not recorded"}`,
    },
    {
      title: "Abstention",
      description:
        "Check that Edith avoids unsupported answers when evidence is missing.",
      icon: "check",
      value: summary.abstention_correct,
      detail: "correct: out-of-scope questions refused, no valid question refused",
    },
  ];

  const byCategory = categories.slice(1).map((category) => {
    const items = records.filter((record) => record.category === category);
    return {
      category,
      total: items.length,
      passed: items.filter(passes).length,
    };
  });

  const selectedRecords = records.filter(
    (record) => record.category === selectedCategory,
  );

  const headline = summary.numeric_questions_fully_correct;

  return (
    <main className="page inner-page evaluation-page">

      <div className="page-title-row">

        <div>
          <div className="page-overline">
            Quality and reliability
          </div>

          <h1>Evaluation</h1>

          <p>
            How answer quality is tested before results are treated as
            reliable.
          </p>
        </div>


      </div>


      {evaluation.error && (
        <LoadError error={evaluation.error} onRetry={evaluation.retry} />
      )}


      <section className="evaluation-summary">

        <div className="gauge-wrap">
          <div
            className="evaluation-gauge"
            style={
              headline
                ? { "--gauge-fill": `${Math.round(ratioOf(headline) * 100)}%` }
                : undefined
            }
            data-live={headline ? "true" : undefined}
          >

            <div className="gauge-center">
              <strong title={headline ? undefined : "No evaluation run is available yet"}>
                {headline || <Missing reason="No run yet" />}
              </strong>
              <span>Numeric</span>
            </div>

          </div>
        </div>


        <div className="evaluation-summary-copy">

          <span className="summary-label">
            Evaluation status
          </span>

          {evaluation.loading && <h2>Loading the latest run…</h2>}

          {data && !available && (
            <>
              <h2>No results yet</h2>
              <p>No evaluation run is available on the backend.</p>
            </>
          )}

          {available && (
            <>
              <h2>{headline} numeric questions fully correct</h2>

              <p>
                Latest full run · {formatRunDate(data.run_at)} ·{" "}
                {records.length} questions · {summary.expected_numbers_found}{" "}
                expected numbers found · average {summary.avg_seconds} s and{" "}
                {summary.avg_tool_calls} tool calls per answer.
              </p>
            </>
          )}


        </div>


        <div className="evaluation-set-card">

          <div className="set-card-icon">
            <Icon name="book" size={20} />
          </div>

          <div>
            <strong>Evaluation set</strong>

            <span>
              A reviewed question set, reference answers and source passages define the basis for reliability checks.
            </span>

          </div>

        </div>

      </section>


      <section className="content-section evaluation-measures">

        <SectionHeading
          title="What is assessed?"
          description="Each measure addresses a different part of the evidence chain."
        />

        <div className="evaluation-card-grid">

          {measures.map((measure, index) => (

            <article
              className="evaluation-measure-card"
              key={measure.title}
              style={{
                "--delay": `${index * 75}ms`,
              }}
            >

              <div className="measure-top">

                <span className="measure-icon">
                  <Icon name={measure.icon} size={21} />
                </span>


              </div>

              <h3>{measure.title}</h3>

              <p>{measure.description}</p>

              <strong
                className="measure-value"
                title={available && measure.value ? undefined : "No score recorded in the latest run"}
              >
                {available && measure.value ? measure.value : <Missing reason="Not recorded" />}
              </strong>

              <small className="measure-definition">
                {available ? measure.detail : "Measure definition · no score recorded"}
              </small>

            </article>

          ))}

        </div>

      </section>


      <div className="evaluation-lower-grid">

        <section className="dashboard-panel category-panel">

          <div className="panel-heading">

            <div>
              <h2>Results by question category</h2>

              <p>
                A question counts as correct when every automated check that
                applies to it passes: expected numbers, grounding, required
                mentions and abstention.
              </p>
            </div>

            <span className="panel-icon">
              <Icon name="chart" size={20} />
            </span>

          </div>


          <div
            className="category-filter"
            role="group"
            aria-label="Filter question categories"
          >

            {categories.map((category) => (

              <button
                key={category}
                className={
                  selectedCategory === category
                    ? "selected"
                    : ""
                }
                onClick={() => setSelectedCategory(category)}
              >
                {category === "All categories" ? category : categoryLabel(category)}
              </button>

            ))}

          </div>


          <div className="category-table">

            {selectedCategory === "All categories" ? (
              <>
                <div className="category-table-head category-results-row">
                  <span>Question category</span>
                  <span>Questions</span>
                  <span>Correct</span>
                </div>

                {byCategory.map((row) => (

                  <div
                    className="category-table-row category-results-row"
                    key={row.category}
                  >
                    <span>{categoryLabel(row.category)}</span>
                    <span>{row.total}</span>
                    <span className={row.passed === row.total ? "result-pass" : "result-partial"}>
                      {row.passed}/{row.total}
                    </span>
                  </div>

                ))}
              </>
            ) : (
              <>
                <div className="category-table-head category-question-row">
                  <span>Question</span>
                  <span>Numbers</span>
                  <span>Pages cited</span>
                  <span>Grounded</span>
                  <span>Time</span>
                </div>

                {selectedRecords.map((record) => (

                  <div
                    className="category-table-row category-question-row"
                    key={record.id}
                  >
                    <span>
                      <b>{record.id}</b> {record.question}
                    </span>
                    <span title={record.numeric ? undefined : "No figures to check for this question"}>
                      {record.numeric || <Missing reason={REASON.nothingToCheck} />}
                    </span>
                    <span title={record.citation ? undefined : "No citation check for this question"}>
                      {record.citation || <Missing reason={REASON.nothingToCheck} />}
                    </span>
                    <span className={isFull(record.grounded) ? "result-pass" : "result-partial"}>
                      {record.grounded || <Missing reason={REASON.nothingToCheck} />}
                    </span>
                    <span>{record.seconds} s</span>
                  </div>

                ))}
              </>
            )}

          </div>

        </section>


        <section className="dashboard-panel flagged-panel">

          <div className="panel-heading">

            <div>
              <h2>Flagged-answer review</h2>

              <p>
                Hand-graded answers that need human checking: the known
                limitations of the current version.
              </p>
            </div>

            <span className="panel-icon warning">
              <Icon name="shield" size={20} />
            </span>

          </div>


          {flaggedAnswers.map((item) => (

            <div className="flagged-empty flagged-item" key={item.id}>

              <div className="flagged-empty-icon">
                <Icon name="shield" size={19} />
              </div>

              <div>
                <strong>
                  {item.id} · {item.title}
                </strong>

                <span className="flagged-grade">{item.grade}</span>

                <p>{item.detail}</p>
              </div>

            </div>

          ))}


          <div className="flagged-placeholder">

            <small>
              Narrative comparison across long report sections is the weakest
              area. Every other hand-graded answer (segments, key audit
              matters, verdict and the three composite scores) was graded
              correct.
            </small>

          </div>

        </section>

      </div>


      <section className="methodology-card">

        <div className="methodology-icon">
          <Icon name="layers" size={22} />
        </div>

        <div>

          <h2>How the evaluation works</h2>

          <p>
            32 questions across categories (lookups, trends, ratios, year-on-year
            changes, composite scores, segments, follow-ups, narrative and risk
            questions, scope traps, abstention and an overall verdict) are run
            automatically against Edith. The answer key was checked against the
            PDF pages (118/118 figures found). Results are scored in four tiers:
            filtered retrieval (Hit Rate@4, MRR), numeric accuracy against the
            answer key, the source pages retrieved and cited, and abstention
            with automatic numeric grounding. Narrative answers are also graded
            by hand.
          </p>

        </div>

      </section>

    </main>
  );
}
```

---

## `frontend/src/components/SourcesPage.jsx`

```jsx
import { getReports } from "../api.js";
import {
  COMPARATIVE_NOTE,
  COVERAGE_TEXT,
  Icon,
  LoadError,
  SectionHeading,
  useApi,
} from "./ui.jsx";

/* =========================================================
   SOURCES & METHODOLOGY
   ========================================================= */

const pipeline = [
  {
    title: "Parse the statements",
    description:
      "The balance sheet, profit and loss and cash flow statements of each report are extracted into canonical line items, consolidated and standalone.",
    icon: "file",
  },
  {
    title: "Verify",
    description:
      "Assets must equal equity plus liabilities, subtotals must add up, and figures restated in a later report are flagged.",
    icon: "check",
  },
  {
    title: "Index",
    description:
      "The report text is chunked and indexed for hybrid search (keyword and semantic), filtered by report and section.",
    icon: "layers",
  },
  {
    title: "Answer",
    description:
      "The model plans the answer, but tools fetch and compute every number: lookups, ratios, changes, scores and segments.",
    icon: "search",
  },
  {
    title: "Check",
    description:
      "Every figure in the answer is matched to its source data; unmatched figures are listed and the answer is marked partially verified.",
    icon: "shield",
  },
  {
    title: "Cite",
    description:
      "Each answer links to the report pages it relies on, opening the PDF at that page.",
    icon: "book",
  },
];

const limitations = [
  "Annual data only: there are no quarterly results.",
  "Narrative comparison across long report sections (for example, how risks changed between years) is the weakest area; check those answers against the cited pages.",
  "Answers take 10-60 seconds, occasionally longer for multi-step analyses.",
  "For research and education only. Nothing here is investment advice.",
];

export default function SourcesPage({ setActivePage }) {
  const reports = useApi(getReports, "reports");

  return (
    <main className="page inner-page sources-page">

      <div className="page-title-row">

        <div>
          <div className="page-overline">
            Sources and methodology
          </div>

          <h1>Sources</h1>

          <p>
            Where Edith's figures come from, how they are checked, and what
            the current version cannot do.
          </p>
        </div>

      </div>


      <section className="sources-block">

        <SectionHeading
          eyebrow="THE REPORTS"
          title="Four Tata Steel annual reports"
          description={`Integrated Reports & Annual Accounts. ${COVERAGE_TEXT}`}
        />

        {reports.error && (
          <LoadError error={reports.error} onRetry={reports.retry} />
        )}

        <div className="report-grid">

          {reports.loading &&
            [0, 1, 2, 3].map((index) => (
              <div className="dashboard-panel report-card" key={index}>
                <div className="evidence-skeleton wide" />
                <div className="evidence-skeleton" />
              </div>
            ))}

          {reports.data && (() => {
            const comparative = reports.data.find(
              (report) => report.fiscal_year === "FY2022-23",
            );

            return comparative ? (
              <div className="dashboard-panel report-card report-card-comparative">
                <span className="statement-icon">
                  <Icon name="layers" size={18} />
                </span>

                <div>
                  <span className="report-year" title={COMPARATIVE_NOTE}>
                    FY2021-22
                  </span>
                  <strong>
                    FY2021-22: figures from the comparative column of the
                    FY2022-23 report
                  </strong>
                  <small>
                    <a href={comparative.pdf_url} target="_blank" rel="noopener noreferrer">
                      Open the FY2022-23 report
                      <Icon name="external" size={12} />
                    </a>
                  </small>
                </div>
              </div>
            ) : null;
          })()}

          {reports.data?.map((report) => (

            <div className="dashboard-panel report-card" key={report.fiscal_year}>

              <span className="statement-icon">
                <Icon name="file" size={18} />
              </span>

              <div>
                <span className="report-year">{report.fiscal_year}</span>
                <a
                  className="report-card-link"
                  href={report.pdf_url}
                  target="_blank"
                  rel="noopener noreferrer"
                  title="Open the report PDF (local copy)"
                >
                  <strong>{report.title}</strong>
                </a>
                <small>
                  {report.pages ? `${report.pages} pages · ` : ""}PDF (local copy)
                  {report.official_url && (
                    <>
                      {" · "}
                      <a
                        className="official-link"
                        href={report.official_url}
                        target="_blank"
                        rel="noopener noreferrer"
                        title="The official copy on tatasteel.com"
                      >
                        tatasteel.com
                      </a>
                    </>
                  )}
                </small>
              </div>

              <a
                className="report-card-open"
                href={report.pdf_url}
                target="_blank"
                rel="noopener noreferrer"
                aria-label={`Open the ${report.fiscal_year} report PDF`}
              >
                <Icon name="external" size={16} />
              </a>

            </div>

          ))}

        </div>

      </section>


      <section className="sources-block">

        <SectionHeading
          eyebrow="HOW IT WORKS"
          title="From report to cited answer."
        />

        <div className="evaluation-card-grid pipeline-grid">

          {pipeline.map((step, index) => (

            <article
              className="evaluation-measure-card"
              key={step.title}
              style={{
                "--delay": `${index * 75}ms`,
              }}
            >

              <div className="measure-top">

                <span className="measure-icon">
                  <Icon name={step.icon} size={21} />
                </span>

                <span className="pipeline-number">
                  {String(index + 1).padStart(2, "0")}
                </span>

              </div>

              <h3>{step.title}</h3>

              <p>{step.description}</p>

            </article>

          ))}

        </div>

      </section>


      <section className="sources-block sources-two-up">

        <div className="methodology-card" id="scores">

          <div className="methodology-icon">
            <Icon name="chart" size={22} />
          </div>

          <div>

            <h2>Composite scores</h2>

            <ul className="methodology-points">
              <li>
                Altman Z'' (book-equity variant), Piotroski F and Beneish M are
                computed in code from the verified statements, consolidated and
                standalone, FY2021-22 to FY2025-26.
              </li>
              <li>
                FY2021-22 from the FY2022-23 report's comparative column;
                Piotroski F and Beneish M need FY2020-21, so they start in
                FY2022-23.
              </li>
              <li>
                Altman X2 uses the actual retained earnings from each report's
                "Other equity" note, each value verified on its page.
              </li>
              <li>
                Disclosed proxies: X4 uses book equity instead of market value
                (not in the reports) and EBIT is taken as profit before tax plus
                finance costs.
              </li>
              <li>
                Piotroski and Beneish compare each year with the prior year as
                presented in the same report.
              </li>
            </ul>

          </div>

        </div>


        <div className="methodology-card">

          <div className="methodology-icon">
            <Icon name="layers" size={22} />
          </div>

          <div>

            <h2>Segments</h2>

            <ul className="methodology-points">
              <li>
                Segment revenue and segment results (segment EBITDA: before
                exceptional items, interest, tax and depreciation) come from the
                consolidated "Segment reporting" note of each report.
              </li>
              <li>
                Every value is checked on its page, segments plus eliminations
                reconcile to the printed total, and restated values are marked.
              </li>
              <li>
                Tata Steel Europe is split into Netherlands and UK operations
                from FY2024-25, and Tata Steel Long Products was merged into Tata
                Steel India.
              </li>
            </ul>

          </div>

        </div>

      </section>


      <section className="methodology-card sources-note">

        <div className="methodology-icon">
          <Icon name="spark" size={22} />
        </div>

        <div>

          <h2>Built with Claude Code, then independently verified</h2>

          <p>
            The composite scores module, the page-verified retained earnings
            and the segment extraction were built with Claude Code from
            written briefs, with automated tests. Each result was then checked
            independently: scores recomputed by hand from the statements,
            retained earnings and segment values located on the PDF pages, and
            the tests re-run.
          </p>

        </div>

      </section>


      <section className="dashboard-panel limitations-panel">

        <div className="panel-heading">

          <div>
            <h2>Limitations</h2>
            <p>What the current version of Edith cannot do well.</p>
          </div>

          <span className="panel-icon warning">
            <Icon name="shield" size={20} />
          </span>

        </div>

        <ul className="limitations-list">
          {limitations.map((item) => (
            <li key={item}>
              <Icon name="check" size={16} />
              {item}
            </li>
          ))}
        </ul>

        <button
          type="button"
          className="text-link"
          onClick={() => setActivePage("Evaluation")}
        >
          See the evaluation results
          <Icon name="arrow" size={15} />
        </button>

      </section>

    </main>
  );
}
```

---

## `frontend/src/components/ui.jsx`

```jsx
import { useEffect, useState } from "react";

/* =========================================================
   SHARED UI
   Edith's Icon, StatusPill and SectionHeading (unchanged apart
   from three extra icon paths), plus display helpers for API data.
   Nothing here computes a financial figure: values are formatted
   exactly as the API returns them.
   ========================================================= */

export function Icon({ name, size = 22 }) {
  const paths = {
    spark: (
      <>
        <path d="M12 2.8 14.2 9.8 21.2 12 14.2 14.2 12 21.2 9.8 14.2 2.8 12 9.8 9.8 12 2.8Z" />
        <path d="m19 2 .6 2.4L22 5l-2.4.6L19 8l-.6-2.4L16 5l2.4-.6L19 2Z" />
      </>
    ),

    search: (
      <>
        <circle cx="10.8" cy="10.8" r="6.8" />
        <path d="m16 16 5 5" />
      </>
    ),

    file: (
      <>
        <path d="M6 2.8h8l4.5 4.5v13.9H6z" />
        <path d="M14 2.8v5h4.5M9 12h6M9 16h6" />
      </>
    ),

    check: (
      <>
        <path d="m4 12.5 5 5L20 6.5" />
        <circle cx="12" cy="12" r="9" />
      </>
    ),

    chart: (
      <>
        <path d="M3 20V4M3 20h18" />
        <path d="m6 15 4-4 3 2 6-7" />
        <path d="M16 6h3v3" />
      </>
    ),

    arrow: <path d="M4 12h15m-6-6 6 6-6 6" />,

    menu: (
      <>
        <path d="M4 7h16M4 12h16M4 17h16" />
      </>
    ),

    close: <path d="m6 6 12 12M18 6 6 18" />,

    book: (
      <>
        <path d="M3.5 5.5A3 3 0 0 1 6.5 3H20v16H6.5a3 3 0 0 0-3 3z" />
        <path d="M3.5 5.5v16M7.5 7h8M7.5 11h8" />
      </>
    ),

    shield: (
      <>
        <path d="M12 2.8 20 6v5.4c0 5.2-3.4 8.5-8 10.2-4.6-1.7-8-5-8-10.2V6z" />
        <path d="m8.5 12 2.3 2.3 4.8-5" />
      </>
    ),

    clock: (
      <>
        <circle cx="12" cy="12" r="9" />
        <path d="M12 7v5l3.5 2" />
      </>
    ),

    layers: (
      <>
        <path d="m12 3 9 5-9 5-9-5z" />
        <path d="m3 12 9 5 9-5M3 16l9 5 9-5" />
      </>
    ),

    copy: (
      <>
        <rect x="8.5" y="8.5" width="12" height="12" rx="2.5" />
        <path d="M15.5 8.5V6a2.5 2.5 0 0 0-2.5-2.5H6A2.5 2.5 0 0 0 3.5 6v7A2.5 2.5 0 0 0 6 15.5h2.5" />
      </>
    ),

    external: (
      <>
        <path d="M14 4h6v6M20 4l-9 9" />
        <path d="M18 14v4.5a1.5 1.5 0 0 1-1.5 1.5h-11A1.5 1.5 0 0 1 4 18.5v-11A1.5 1.5 0 0 1 5.5 6H10" />
      </>
    ),

    refresh: (
      <>
        <path d="M20 11a8 8 0 1 0-2.3 5.7" />
        <path d="M20 4v7h-7" />
      </>
    ),
  };

  return (
    <svg
      className="icon"
      width={size}
      height={size}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.7"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
    >
      {paths[name] || paths.spark}
    </svg>
  );
}

export function StatusPill({ children, tone = "pending" }) {
  return (
    <span className={`status-pill ${tone}`}>
      {children}
    </span>
  );
}

export function SectionHeading({ eyebrow, title, description, action }) {
  return (
    <div className="section-heading">
      <div>
        {eyebrow && <div className="section-eyebrow">{eyebrow}</div>}
        <h2>{title}</h2>
        {description && <p>{description}</p>}
      </div>

      {action && <div className="section-heading-action">{action}</div>}
    </div>
  );
}


/* ---------------------------------------------------------
   Formatting (display only)
   --------------------------------------------------------- */

const MINUS = "−";

export function formatNumber(value, decimals = 2) {
  if (value == null || Number.isNaN(value)) return "not in the reports";
  const text = Math.abs(value).toLocaleString("en-IN", {
    minimumFractionDigits: decimals,
    maximumFractionDigits: decimals,
  });
  return value < 0 ? `${MINUS}${text}` : text;
}

/** INR crore with Indian grouping and 2 decimals, e.g. 2,32,139.94 */
export function formatCrore(value) {
  return formatNumber(value, 2);
}

/** A percentage change exactly as the API gives it, e.g. +6.22% */
export function formatChangePct(value) {
  if (value == null) return "not in the reports";
  return `${value > 0 ? "+" : ""}${formatNumber(value, 2)}%`;
}

/** A metric from /api/metrics with its unit and the API's decimals. */
export function formatMetric(value, unit, decimals = 2) {
  if (value == null) return "not in the reports";
  if (unit === "x") return `${formatNumber(value, decimals)}x`;
  if (unit === "%") return `${formatNumber(value, decimals)}%`;
  return formatNumber(value, decimals);
}

/** "distress zone" -> "Distress zone" */
export function sentenceCase(text) {
  if (!text) return text;
  return text.charAt(0).toUpperCase() + text.slice(1);
}

export function formatRunDate(iso) {
  if (!iso) return "";
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return iso;
  return date.toLocaleString("en-IN", {
    day: "numeric",
    month: "short",
    year: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
}

/* ---------------------------------------------------------
   Value markers
   --------------------------------------------------------- */

export function RestatedMark({
  note = "Restated: the later report presents a different figure for this year; the latest report's figure is shown.",
}) {
  return (
    <sup className="restated-mark" title={note} aria-label={note}>
      R
    </sup>
  );
}

/** A value, or a short grey reason (tooltip adds detail) when it is null. */
export function Value({
  value,
  format = formatCrore,
  restated = false,
  restatedNote,
  missingReason = REASON.notInReports,
  missingNote,
}) {
  if (value == null) return <Missing reason={missingReason} note={missingNote} />;

  return (
    <>
      {format(value)}
      {restated && <RestatedMark note={restatedNote} />}
    </>
  );
}

/* Short reasons shown in grey in place of a missing value. */
export const REASON = {
  notInReports: "Not in the reports",
  noPriorYear: "No FY2020-21 data",
  needsPriorYear: "Needs FY2020-21 data",
  withinEurope: "Reported within Europe then",
  splitEurope: "Split into Netherlands and UK",
  mergedIntoIndia: "Merged into Tata Steel India",
  notASegment: "Not a segment that year",
  nothingToCheck: "Nothing to check",
};

/** A short grey reason in place of a missing value; the tooltip may add detail. */
export function Missing({ reason = REASON.notInReports, note }) {
  return (
    <span className="value-missing missing-reason" title={note || reason}>
      {reason}
    </span>
  );
}

/* ---------------------------------------------------------
   Years and coverage (standard wording)
   --------------------------------------------------------- */

export const COMPARATIVE_YEAR = "FY2021-22";
export const COMPARATIVE_NOTE = "From the FY2022-23 report's comparative column";
export const NEEDS_PRIOR_YEAR_NOTE = "Needs FY2020-21, which is outside the four reports";
export const COVERAGE_TEXT =
  "Figures cover FY2021-22 to FY2025-26, taken from Tata Steel's four annual reports (FY2022-23 to FY2025-26; FY2021-22 from the comparative column of the FY2022-23 report).";

/** Small info marker for FY2021-22 (comparative-column year). */
export function ComparativeMark() {
  return (
    <sup className="comparative-mark" title={COMPARATIVE_NOTE} aria-label={COMPARATIVE_NOTE}>
      i
    </sup>
  );
}

/** A fiscal-year label, with the info marker when it is FY2021-22. */
export function YearLabel({ year }) {
  return (
    <>
      {year}
      {year === COMPARATIVE_YEAR && <ComparativeMark />}
    </>
  );
}

/* ---------------------------------------------------------
   Sparkline: a tiny 5-year trend drawn in Edith's chart colours.
   The values are only scaled to fit the box.
   --------------------------------------------------------- */

let sparklineCount = 0;

export function Sparkline({ values, width = 64, height = 20, label, highlightIndex }) {
  const [gradientId] = useState(() => `sparkStroke${++sparklineCount}`);
  const present = values
    .map((value, index) => ({ value, index }))
    .filter((point) => point.value != null);

  if (present.length < 2) {
    return <span className="metric-mini-line" aria-hidden="true" />;
  }

  const min = Math.min(...present.map((point) => point.value));
  const max = Math.max(...present.map((point) => point.value));
  const span = max - min || 1;
  const step = (width - 4) / Math.max(values.length - 1, 1);
  const points = present.map((point) => {
    const x = 2 + point.index * step;
    const y = 2 + (1 - (point.value - min) / span) * (height - 4);
    return [x, y];
  });
  // Mark the selected year when given, otherwise the latest point.
  const markIndex = present.findIndex((point) => point.index === highlightIndex);
  const last = points[markIndex >= 0 ? markIndex : points.length - 1];

  return (
    <svg
      className="mini-sparkline"
      width={width}
      height={height}
      viewBox={`0 0 ${width} ${height}`}
      role="img"
      aria-label={label || "Five-year trend"}
    >
      <defs>
        <linearGradient id={gradientId} x1="0" y1="0" x2="1" y2="0">
          <stop offset="0%" stopColor="#0d9d79" />
          <stop offset="100%" stopColor="#4c8ce8" />
        </linearGradient>
      </defs>

      <polyline
        points={points.map(([x, y]) => `${x},${y}`).join(" ")}
        fill="none"
        stroke={`url(#${gradientId})`}
        strokeWidth="1.8"
        strokeLinecap="round"
        strokeLinejoin="round"
      />

      <circle
        cx={last[0]}
        cy={last[1]}
        r={highlightIndex != null ? 3 : 2.2}
        className={highlightIndex != null ? "sparkline-selected" : undefined}
      />
    </svg>
  );
}

/* ---------------------------------------------------------
   Data loading
   --------------------------------------------------------- */

/**
 * Loads data with `load()` whenever `key` changes.
 * Returns { data, error, loading, retry }.
 */
export function useApi(load, key) {
  const [state, setState] = useState({ key: null, data: null, error: null });
  const [attempt, setAttempt] = useState(0);

  useEffect(() => {
    let active = true;

    load().then(
      (data) => active && setState({ key, data, error: null }),
      (error) => active && setState({ key, data: null, error }),
    );

    return () => {
      active = false;
    };
    // `load` is recreated on every render; `key` identifies the request.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [key, attempt]);

  const current = state.key === key;

  return {
    data: current ? state.data : null,
    error: current ? state.error : null,
    loading: !current,
    retry: () => {
      setState((previous) => ({ ...previous, key: null }));
      setAttempt((value) => value + 1);
    },
  };
}

/** A friendly inline error with a Retry button, in Edith's notice style. */
export function LoadError({ error, onRetry, compact = false }) {
  return (
    <div className={`load-error ${compact ? "compact" : ""}`} role="alert">
      <Icon name="shield" size={17} />
      <span>{error?.message || "Something went wrong while loading this data."}</span>
      {onRetry && (
        <button type="button" className="text-link" onClick={onRetry}>
          Retry
          <Icon name="refresh" size={14} />
        </button>
      )}
    </div>
  );
}
```

---

## `frontend/src/index.css`

```css
@import url("https://fonts.googleapis.com/css2?family=DM+Sans:wght@400;500;600;700&family=Manrope:wght@400;500;600;700;800&family=Playfair+Display:ital,wght@0,600;0,700;1,600;1,700&display=swap");

:root {
  font-family: "DM Sans", sans-serif;
  color: #17302b;
  background: #fbfcfa;
  font-synthesis: none;
  text-rendering: optimizeLegibility;
  -webkit-font-smoothing: antialiased;
  -moz-osx-font-smoothing: grayscale;
  font-variant-numeric: tabular-nums;
}

* { box-sizing: border-box; }

html {
  min-width: 320px;
  scroll-behavior: smooth;
}

body {
  margin: 0;
  min-width: 320px;
  min-height: 100vh;
}

button, textarea { font: inherit; }
button, a { -webkit-tap-highlight-color: transparent; }
a { color: inherit; text-decoration: none; }
::selection { color: #fff; background: #126b5b; }
```

---

## `frontend/src/main.jsx`

```jsx
import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import './index.css'
import App from './App.jsx'

createRoot(document.getElementById('root')).render(
  <StrictMode>
    <App />
  </StrictMode>,
)
```

---

## `frontend/src/readability.css`

```css
/* =========================================================
   READABILITY (review round 2)
   Loaded after App.css. Only font sizes, line heights, the
   spacing they need, and the full-height Ask Edith layout
   change here; colours, cards and layout stay Edith's.
   Minimums at 100% zoom: body 18px, secondary 15px, eyebrow
   labels 13px, card titles 22px, KPI values 30px.
   The Home hero keeps its own one-screen scaling (App.css).
   ========================================================= */

:root {
  --fs-body: 18px;
  --fs-secondary: 15px;
  --fs-eyebrow: 13px;
  --fs-card-title: 23px;
  --fs-kpi: 30px;
  --lh-body: 1.6;
}


/* ---------- Global: header, footer, shared bits ---------- */

.app-shell .site-header .nav-link { font-size: 16px; }
.app-shell .site-header .brand-copy strong { font-size: 18px; }
.app-shell .site-header .brand-copy span { font-size: var(--fs-secondary); }
.app-shell .site-header .header-cta { font-size: 16px; }
.app-shell .site-header .backend-status { font-size: var(--fs-secondary); }

.app-shell .site-footer .brand-copy strong { font-size: 18px; }
.app-shell .site-footer .brand-copy span { font-size: var(--fs-secondary); }
.app-shell .site-footer .footer-main p { font-size: var(--fs-body); line-height: var(--lh-body); }
.app-shell .site-footer .footer-link { font-size: 16px; }
.app-shell .site-footer .footer-bottom span { font-size: var(--fs-secondary); }

.app-shell .page .page-overline,
.app-shell .page .section-eyebrow { font-size: var(--fs-eyebrow); }

.app-shell .inner-page .page-title-row h1 { font-size: clamp(36px, 3vw, 46px); }
.app-shell .inner-page .page-title-row p { font-size: 19px; line-height: var(--lh-body); }

.app-shell .page .section-heading h2 { font-size: clamp(32px, 2.8vw, 42px); }
.app-shell .page .section-heading p { font-size: 19px; line-height: var(--lh-body); }

.app-shell .page .button,
.app-shell .page .text-link { font-size: 16px; }

.app-shell .page .zone-chip,
.app-shell .page .status-pill { font-size: var(--fs-secondary); }

/* Restated "R" and FY2021-22 "i" markers */
.app-shell .restated-mark,
.app-shell .comparative-mark {
  min-width: 17px;
  height: 17px;
  font-size: var(--fs-secondary);
  line-height: 17px;
}

/* A short grey reason in place of a missing value */
.app-shell .missing-reason {
  color: var(--muted);
  font-size: var(--fs-secondary);
  font-weight: 600;
  font-style: italic;
  letter-spacing: 0;
  line-height: 1.4;
  white-space: normal;
}

.app-shell .select-control select { min-height: 42px; font-size: 16px; }
.app-shell .select-control > span { font-size: var(--fs-secondary); }

.app-shell .page .panel-heading h2 { font-size: var(--fs-card-title); }
.app-shell .page .panel-heading p { font-size: 17px; line-height: var(--lh-body); }
.app-shell .page .panel-heading p { font-size: var(--fs-body); }
.app-shell .page .panel-footnote { font-size: 16px; line-height: var(--lh-body); }
.app-shell .page .panel-footnote .text-link { font-size: 16px; }


/* ---------- Home (below the hero) ---------- */

.app-shell .glance-section .about-card-heading h3,
.app-shell .glance-section .glance-bullets h3 { font-size: var(--fs-card-title); }
.app-shell .glance-section .about-card-heading small { font-size: var(--fs-secondary); }
.app-shell .glance-section .about-facts li { font-size: var(--fs-body); line-height: var(--lh-body); }
.app-shell .glance-section .about-facts li > svg { margin-top: 6px; }
.app-shell .glance-section .fact-page-link { font-size: var(--fs-secondary); }
.app-shell .glance-section .glance-bullets ul { font-size: var(--fs-body); line-height: var(--lh-body); }
.app-shell .glance-section .glance-closing { font-size: var(--fs-body); }
.app-shell .glance-section .glance-closing svg { margin-top: 5px; }
.app-shell .glance-section .try-asking-label { font-size: 16px; }
.app-shell .glance-section .question-chip { font-size: 16px; }
.app-shell .glance-section .glance-source { font-size: var(--fs-secondary); line-height: 1.5; }
.app-shell .glance-section .metric-card-top > span:first-child { font-size: 16px; }
.app-shell .glance-section .metric-value { font-size: var(--fs-kpi); }
.app-shell .glance-section .metric-value small { font-size: 16px; }

.app-shell .trust-strip .trust-intro strong { font-size: 19px; }
.app-shell .trust-strip .trust-intro span { font-size: var(--fs-body); }
.app-shell .trust-strip .trust-item { font-size: 16px; }

.app-shell .feature-section .feature-number { font-size: var(--fs-eyebrow); }
.app-shell .feature-section .feature-card h3 { font-size: 25px; }
.app-shell .feature-section .feature-card p { font-size: var(--fs-body); line-height: var(--lh-body); }
.app-shell .feature-section .text-link { font-size: 16px; }

.app-shell .roadmap-section .roadmap-heading p { font-size: 19px; line-height: var(--lh-body); }
.app-shell .roadmap-section .roadmap-stamp { font-size: var(--fs-secondary); }
.app-shell .roadmap-section .roadmap-node h3 { font-size: 25px; }
.app-shell .roadmap-section .roadmap-node p,
.app-shell .roadmap-section .roadmap-detail { font-size: var(--fs-body); line-height: var(--lh-body); }
.app-shell .roadmap-section .roadmap-node-number { font-size: var(--fs-eyebrow); }
.app-shell .roadmap-section .roadmap-more { font-size: var(--fs-secondary); }

.app-shell .tata-feature .tata-feature-copy p { font-size: 19px; line-height: var(--lh-body); }
.app-shell .tata-feature .tata-feature-points span { font-size: var(--fs-body); }
.app-shell .tata-feature .button { font-size: 16px; }

.app-shell .bottom-cta p { font-size: 19px; line-height: var(--lh-body); }
.app-shell .bottom-cta .button { font-size: 16px; }


/* ---------- Ask Edith: full-height app layout ---------- */

@media (min-width: 901px) {
  .app-shell .ask-page.inner-page {
    width: 100%;
    max-width: none;
    margin: 0;
    padding: 0;
  }

  .app-shell .ask-page .ask-layout {
    height: calc(100vh - var(--site-header-h, 79px));
    min-height: 560px;
    margin: 0;
    gap: 0;
    align-items: stretch;
    grid-template-columns: 330px minmax(0, 1fr);
  }

  .app-shell .ask-page .ask-layout.sidebar-collapsed {
    grid-template-columns: 64px minmax(0, 1fr);
  }

  /* The sidebar starts right under the header and scrolls on its own */
  .app-shell .ask-page .ask-sidebar {
    align-self: stretch;
    height: 100%;
    max-height: none;
    padding: 0 20px 24px;
    overflow-y: auto;
    border: 0;
    border-right: 1px solid rgba(112, 183, 158, 0.45);
    border-radius: 0;
    box-shadow: none;
  }

  /* "Hide sidebar" stays on top of everything that scrolls below it */
  .app-shell .ask-page .sidebar-toggle {
    position: sticky;
    top: 0;
    z-index: 5;
    margin: 0 -20px 16px;
    padding: 14px 20px;
    border: 0;
    border-bottom: 1px solid rgba(218, 245, 232, 0.18);
    border-radius: 0;
    width: calc(100% + 40px);
    background: #153b34;
    text-align: left;
  }

  .app-shell .ask-page .sidebar-new-chat {
    display: flex;
    align-items: center;
    justify-content: space-between;
    align-self: stretch;
    width: 100%;
    margin: 0 0 18px;
  }

  .app-shell .ask-page .ask-layout.sidebar-collapsed .ask-sidebar { padding: 0 8px; }

  .app-shell .ask-page .ask-layout.sidebar-collapsed .sidebar-toggle {
    width: calc(100% + 16px);
    margin: 0 -8px 12px;
    padding: 14px 8px;
    text-align: center;
  }

  .app-shell .ask-page .ask-main {
    display: flex;
    flex-direction: column;
    min-width: 0;
    min-height: 0;
    padding: 18px clamp(20px, 2.4vw, 40px) 20px;
  }

  .app-shell .ask-page .ask-main .page-title-row {
    flex: 0 0 auto;
    margin: 0 0 14px;
    padding: 0;
  }

  .app-shell .ask-page .ask-main .page-title-row h1 { margin: 2px 0 4px; font-size: 34px; }
  .app-shell .ask-page .ask-main .page-title-row p { margin: 0; }

  .app-shell .ask-page .chat-panel {
    position: static;
    flex: 1 1 auto;
    height: auto;
    min-height: 0;
  }

  .app-shell .ask-page .ask-page-links {
    width: min(1500px, calc(100% - 72px));
    margin: 22px auto 30px;
  }
}

.app-shell .ask-page .ask-main { min-width: 0; }


/* ---------- Ask Edith: sidebar text ---------- */

.app-shell .ask-page .sidebar-toggle { font-size: 16px; }
.app-shell .ask-page .sidebar-new-chat span { font-size: 17px; }
.app-shell .ask-page .sidebar-heading h2 { font-size: var(--fs-card-title); }
.app-shell .ask-page .sidebar-heading p { font-size: var(--fs-body); line-height: 1.5; }
.app-shell .ask-page .suggestion-item span { font-size: var(--fs-eyebrow); }
.app-shell .ask-page .suggestion-item strong { font-size: var(--fs-body); line-height: 1.45; }
.app-shell .ask-page .suggestion-item small { font-size: var(--fs-secondary); line-height: 1.45; }
.app-shell .ask-page .follow-up-hint { font-size: 16px; line-height: 1.55; }
.app-shell .ask-page .follow-up-hint b { font-size: 16px; }
.app-shell .ask-page .sidebar-info-title { font-size: 18px; }
.app-shell .ask-page .sidebar-info-row,
.app-shell .ask-page .sidebar-info-row span { font-size: var(--fs-secondary); }
.app-shell .ask-page .sidebar-info-row b { font-size: var(--fs-body); line-height: 1.5; }
.app-shell .ask-page .recent-heading b { font-size: 18px; }
.app-shell .ask-page .recent-question { font-size: var(--fs-body); line-height: 1.5; }
.app-shell .ask-page .recent-empty { font-size: 16px; line-height: 1.55; }


/* ---------- Ask Edith: chat panel ---------- */

.app-shell .ask-page .chat-panel-header { padding-top: 16px; padding-bottom: 16px; }

.app-shell .ask-page .chat-avatar,
.app-shell .ask-page .assistant-message-avatar {
  width: 46px;
  height: 46px;
  font-size: 20px;
}

.app-shell .ask-page .chat-header-copy strong { font-size: 21px; }
.app-shell .ask-page .chat-header-copy span { font-size: 16px; }

/* Welcome: centred block that fills the panel */
.app-shell .ask-page .welcome-message {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: safe center;
  gap: 18px;
  max-width: 820px;
  min-height: 100%;
  margin: 0 auto;
  text-align: left;
}

.app-shell .ask-page .welcome-icon { width: 58px; height: 58px; }
.app-shell .ask-page .welcome-message h2 { margin: 0 0 12px; font-size: clamp(36px, 3vw, 46px); text-align: center; }
.app-shell .ask-page .welcome-message p { font-size: 19px; line-height: var(--lh-body); text-align: center; }
.app-shell .ask-page .welcome-callout { margin-top: 20px; padding: 20px 24px; }
.app-shell .ask-page .welcome-callout ul { gap: 8px; font-size: var(--fs-body); line-height: var(--lh-body); }
.app-shell .ask-page .welcome-callout li { font-size: var(--fs-body); }
.app-shell .ask-page .welcome-callout svg { margin-top: 4px; }

/* Messages: answers use the panel width so tables have room */
.app-shell .ask-page .assistant-message { max-width: min(1180px, 100%); }
.app-shell .ask-page .assistant-message-body { flex: 1 1 auto; min-width: 0; }

.app-shell .ask-page .user-message span,
.app-shell .ask-page .assistant-message-body > span { font-size: var(--fs-secondary); }
.app-shell .ask-page .user-message p { font-size: var(--fs-body); line-height: var(--lh-body); }
.app-shell .ask-page .answer-meta,
.app-shell .ask-page .answer-meta span { font-size: var(--fs-secondary); }
.app-shell .ask-page .answer-action { font-size: var(--fs-secondary); }
.app-shell .ask-page .answer-warnings li { font-size: 16px; line-height: 1.55; }
.app-shell .ask-page .verification-partial small { font-size: var(--fs-secondary); }

.app-shell .ask-page .answer-markdown,
.app-shell .ask-page .answer-markdown p,
.app-shell .ask-page .answer-markdown li,
.app-shell .ask-page .assistant-message-body p { font-size: var(--fs-body); line-height: var(--lh-body); }
.app-shell .ask-page .answer-markdown h1,
.app-shell .ask-page .answer-markdown h2,
.app-shell .ask-page .answer-markdown h3 { font-size: 21px; }

/* Answer tables: full width, cells wrap */
.app-shell .ask-page .answer-table-wrap table { width: 100%; font-size: var(--fs-body); }
.app-shell .ask-page .answer-table-wrap th,
.app-shell .ask-page .answer-table-wrap td {
  padding: 10px 14px;
  font-size: var(--fs-body);
  line-height: 1.5;
}

.app-shell .ask-page .evidence-placeholder-top > span { font-size: 16px; }
.app-shell .ask-page .evidence-placeholder small { font-size: var(--fs-secondary); }
.app-shell .ask-page .citation-chip { font-size: var(--fs-secondary); padding: 6px 12px; }
.app-shell .ask-page .answer-steps summary { font-size: 16px; }
.app-shell .ask-page .answer-steps li { font-size: var(--fs-body); line-height: var(--lh-body); }
.app-shell .ask-page .answer-steps li b { font-size: var(--fs-secondary); }
.app-shell .ask-page .answer-steps p { font-size: var(--fs-body); }
.app-shell .ask-page .answer-steps small { font-size: var(--fs-secondary); }
.app-shell .ask-page .pending-footer small { font-size: var(--fs-secondary); }
.app-shell .ask-page .pending-elapsed { font-size: var(--fs-secondary); }
.app-shell .ask-page .pending-cancel { font-size: var(--fs-secondary); }
.app-shell .ask-page .answer-error p { font-size: var(--fs-body); }

/* Composer */
.app-shell .ask-page .chat-composer textarea { font-size: var(--fs-body); line-height: 1.55; }
.app-shell .ask-page .chat-composer textarea::placeholder { font-size: var(--fs-body); }
.app-shell .ask-page .composer-bottom > span { font-size: var(--fs-secondary); }
.app-shell .ask-page .composer-bottom .button { min-height: 46px; padding: 11px 22px; font-size: 17px; }
.app-shell .ask-page .ask-page-links .text-link { font-size: 17px; }


/* ---------- Dashboard ---------- */

.app-shell .dashboard-page .control-group > label { font-size: var(--fs-secondary); }
.app-shell .dashboard-page .segmented-control button { font-size: var(--fs-secondary); }
.app-shell .dashboard-page .control-note { font-size: 16px; }
.app-shell .dashboard-page .group-level-note { font-size: var(--fs-secondary); }

.app-shell .dashboard-page .metric-card-top > span:first-child { font-size: 16px; }
.app-shell .dashboard-page .metric-value { font-size: var(--fs-kpi); }
.app-shell .dashboard-page .metric-value small { font-size: 16px; }
.app-shell .dashboard-page .metric-card-bottom span { font-size: var(--fs-secondary); }

/* Region view */
.app-shell .dashboard-page .region-stat span { font-size: var(--fs-secondary); }
.app-shell .dashboard-page .region-stat strong { font-size: var(--fs-kpi); }
.app-shell .dashboard-page .region-stat strong small { font-size: var(--fs-secondary); }
.app-shell .dashboard-page .region-stats { grid-template-columns: repeat(auto-fit, minmax(210px, 1fr)); }

.app-shell .dashboard-page .region-absent {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 10px 14px;
  margin-top: 6px;
  padding: 16px 18px;
  border: 1px solid #eed9ad;
  border-radius: 10px;
  color: #6b4f16;
  background: #fff8ea;
  font-size: var(--fs-body);
  font-weight: 650;
  line-height: 1.5;
}

.app-shell .dashboard-page .region-absent > svg { flex: 0 0 auto; color: #9a6f1c; }
.app-shell .dashboard-page .region-absent-actions { display: flex; flex-wrap: wrap; gap: 10px; }
.app-shell .dashboard-page .region-absent-actions .button { min-height: 40px; padding: 8px 16px; font-size: var(--fs-secondary); }

/* Chart */
.app-shell .dashboard-page .chart-legend,
.app-shell .dashboard-page .chart-legend span { font-size: var(--fs-secondary); }
.app-shell .dashboard-page .chart-y-live span { font-size: var(--fs-secondary); }
.app-shell .dashboard-page .chart-x-labels,
.app-shell .dashboard-page .chart-x-labels span { font-size: var(--fs-secondary); }
.app-shell .dashboard-page .chart-point-label { font-size: var(--fs-secondary); }
.app-shell .dashboard-page .chart-tooltip small,
.app-shell .dashboard-page .chart-tooltip span { font-size: var(--fs-secondary); }
.app-shell .dashboard-page .chart-tooltip strong { font-size: 18px; }
.app-shell .dashboard-page .chart-live .chart-plot { left: 88px; }

/* Ratios */
.app-shell .dashboard-page .ratio-topline span { font-size: var(--fs-body); }
.app-shell .dashboard-page .ratio-topline strong { font-size: 20px; }
.app-shell .dashboard-page .ratio-item small,
.app-shell .dashboard-page .ratio-footline small { font-size: var(--fs-secondary); }

/* Composite scores and the health summary: full width, so the
   bigger text has room */
.app-shell .dashboard-page .dashboard-insight-grid { grid-template-columns: minmax(0, 1fr); }

.app-shell .dashboard-page .data-table { width: 100%; }
.app-shell .dashboard-page .data-table th,
.app-shell .dashboard-page .data-table td { font-size: var(--fs-body); line-height: 1.5; }
.app-shell .dashboard-page .data-table thead th { font-size: var(--fs-secondary); }

.app-shell .dashboard-page .scores-table tbody th { min-width: 280px; width: 34%; white-space: normal; }
.app-shell .dashboard-page .scores-table tbody th strong { font-size: 19px; }
.app-shell .dashboard-page .scores-table tbody th small { font-size: 16px; line-height: 1.55; white-space: normal; }
.app-shell .dashboard-page .scores-table td b { font-size: 19px; }
.app-shell .dashboard-page .scores-table td .zone-chip { font-size: var(--fs-secondary); }
.app-shell .dashboard-page .scores-table th,
.app-shell .dashboard-page .scores-table td { padding: 12px 14px; }

.app-shell .dashboard-page .segments-table th,
.app-shell .dashboard-page .segments-table td { padding: 10px 14px; }
.app-shell .dashboard-page .segments-table tbody th { white-space: normal; }

.app-shell .dashboard-page .health-list li > span:first-child { font-size: 16px; }
.app-shell .dashboard-page .health-list li strong { font-size: 20px; }
.app-shell .dashboard-page .health-list .zone-chip { font-size: var(--fs-secondary); }
.app-shell .dashboard-page .health-ask { font-size: 17px; }

/* Statement coverage */
.app-shell .dashboard-page .statement-row strong { font-size: var(--fs-card-title); }
.app-shell .dashboard-page .statement-row small { font-size: 16px; }
.app-shell .dashboard-page .statement-panel .report-links a { font-size: var(--fs-secondary); }
.app-shell .dashboard-page .statement-panel .report-links a em { font-size: var(--fs-secondary); }


/* ---------- Evaluation ---------- */

.app-shell .evaluation-page .summary-label { font-size: var(--fs-eyebrow); }
.app-shell .evaluation-page .evaluation-summary-copy p { font-size: var(--fs-body); line-height: var(--lh-body); }
.app-shell .evaluation-page .evaluation-set-card strong { font-size: 19px; }
.app-shell .evaluation-page .evaluation-set-card span:not(.status-pill) { font-size: var(--fs-body); line-height: var(--lh-body); }
.app-shell .evaluation-page .gauge-center strong { font-size: 34px; }
.app-shell .evaluation-page .gauge-center span { font-size: var(--fs-secondary); }
.app-shell .evaluation-page .evaluation-measure-card h3 { font-size: var(--fs-card-title); }
.app-shell .evaluation-page .evaluation-measure-card p { font-size: var(--fs-body); line-height: var(--lh-body); }
.app-shell .evaluation-page .measure-value { font-size: var(--fs-kpi); }
.app-shell .evaluation-page .evaluation-measure-card small,
.app-shell .evaluation-page .measure-definition { font-size: var(--fs-secondary); line-height: 1.5; }
.app-shell .evaluation-page .panel-heading p { font-size: var(--fs-body); }
.app-shell .evaluation-page .evaluation-measures .section-heading p { font-size: 19px; line-height: var(--lh-body); }
.app-shell .evaluation-page .category-filter button { font-size: var(--fs-secondary); }
.app-shell .evaluation-page .category-table-head,
.app-shell .evaluation-page .category-table-head > span { font-size: var(--fs-secondary); }
.app-shell .evaluation-page .category-table-row,
.app-shell .evaluation-page .category-table-row > span,
.app-shell .evaluation-page .category-table-row > span:first-child,
.app-shell .evaluation-page .category-table-row b { font-size: var(--fs-body); line-height: 1.55; }
.app-shell .evaluation-page .flagged-empty strong { font-size: 19px; }
.app-shell .evaluation-page .flagged-grade { font-size: var(--fs-secondary); }
.app-shell .evaluation-page .flagged-empty p { font-size: var(--fs-body); line-height: var(--lh-body); }
.app-shell .evaluation-page .flagged-placeholder small { font-size: var(--fs-secondary); }
.app-shell .evaluation-page .methodology-card h2 { font-size: 28px; }
.app-shell .evaluation-page .methodology-card p { font-size: var(--fs-body); line-height: 1.7; }


/* ---------- Sources ---------- */

.app-shell .sources-page .section-heading p { font-size: 19px; }
.app-shell .sources-page .report-card strong { font-size: var(--fs-card-title); line-height: 1.3; }
.app-shell .sources-page .report-card small,
.app-shell .sources-page .report-card small a { font-size: var(--fs-secondary); }
.app-shell .sources-page .report-year { font-size: var(--fs-secondary); }
.app-shell .sources-page .pipeline-number { font-size: var(--fs-eyebrow); }
.app-shell .sources-page .evaluation-measure-card h3 { font-size: var(--fs-card-title); }
.app-shell .sources-page .evaluation-measure-card p { font-size: var(--fs-body); line-height: var(--lh-body); }
.app-shell .sources-page .methodology-card h2 { font-size: 28px; }
.app-shell .sources-page .methodology-card p { font-size: var(--fs-body); line-height: 1.7; }
.app-shell .sources-page .panel-heading p { font-size: var(--fs-body); }
.app-shell .sources-page .limitations-list li { font-size: var(--fs-body); line-height: var(--lh-body); }

.methodology-points {
  display: grid;
  gap: 8px;
  margin: 10px 0 0;
  padding-left: 20px;
  color: var(--ink-soft);
  font-size: var(--fs-body);
  line-height: var(--lh-body);
}

.methodology-points li::marker { color: var(--green); }

@media (min-width: 1101px) {
  .app-shell .sources-page .report-grid { grid-template-columns: repeat(auto-fit, minmax(300px, 1fr)); }
}


/* ---------- Home hero: paragraph and note reach the minimums
   (headline and art keep their one-screen scaling) ---------- */

@media (min-width: 1101px) {
  .app-shell .hero-section .hero-description { font-size: clamp(18px, min(1.45vw, 2.3vh), 22px); }
  .app-shell .hero-section .hero-note { font-size: 16px; }
}

/* Full-width health summary: two columns of facts on wide screens */
@media (min-width: 1101px) {
  .app-shell .dashboard-page .health-list {
    display: grid;
    grid-template-columns: repeat(2, minmax(0, 1fr));
    column-gap: 48px;
  }
}
```

---

## `frontend/src/useConversations.js`

```javascript
import { useCallback, useRef, useState } from "react";
import { ask } from "./api.js";

/* =========================================================
   CONVERSATIONS
   Kept in App state so a thread (and an answer still being
   produced) survives switching pages. Nothing is persisted
   beyond the browser session.

   conversation = { id, title, turns: [turn] }
   turn = { id, question, status: "pending" | "done" | "error",
            startedAt, response, error, cancelled }
   ========================================================= */

const MAX_HISTORY_MESSAGES = 20;
const MAX_MESSAGE_CHARS = 20_000; // the backend's limit per history message

let idCounter = 0;
function newId(prefix) {
  idCounter += 1;
  return `${prefix}-${Date.now().toString(36)}-${idCounter}`;
}

/** Earlier answered turns as API history, oldest first, max 20 messages. */
function historyBefore(turns, turnId) {
  const messages = [];

  for (const turn of turns) {
    if (turn.id === turnId) break;
    if (turn.status !== "done" || !turn.response) continue;

    messages.push(
      { role: "user", content: turn.question.slice(0, MAX_MESSAGE_CHARS) },
      {
        role: "assistant",
        content: turn.response.answer_markdown.slice(0, MAX_MESSAGE_CHARS),
      },
    );
  }

  // Keep whole question/answer pairs.
  return messages.slice(-MAX_HISTORY_MESSAGES);
}

export function useConversations() {
  const [conversations, setConversations] = useState([]);
  const [activeId, setActiveId] = useState(null);
  const controllers = useRef(new Map());

  const updateTurn = useCallback((conversationId, turnId, changes) => {
    setConversations((items) =>
      items.map((conversation) =>
        conversation.id !== conversationId
          ? conversation
          : {
              ...conversation,
              turns: conversation.turns.map((turn) =>
                turn.id === turnId ? { ...turn, ...changes } : turn,
              ),
            },
      ),
    );
  }, []);

  const run = useCallback(
    (conversationId, turn, history) => {
      const controller = new AbortController();
      controllers.current.set(turn.id, controller);

      ask(turn.question, history, controller.signal)
        .then((response) => {
          updateTurn(conversationId, turn.id, {
            status: "done",
            response,
            error: null,
          });
        })
        .catch((error) => {
          updateTurn(conversationId, turn.id, {
            status: "error",
            error: error?.message || "Something went wrong.",
            cancelled: Boolean(error?.cancelled),
          });
        })
        .finally(() => {
          controllers.current.delete(turn.id);
        });
    },
    [updateTurn],
  );

  /**
   * Send a question. It continues the active conversation unless
   * `fresh` is true or no conversation is open.
   */
  const send = useCallback(
    (rawQuestion, { fresh = false } = {}) => {
      const question = rawQuestion.trim();
      if (!question) return;

      const current = fresh
        ? null
        : conversations.find((conversation) => conversation.id === activeId);

      if (current?.turns.some((turn) => turn.status === "pending")) return;

      const turn = {
        id: newId("turn"),
        question,
        status: "pending",
        startedAt: Date.now(),
        response: null,
        error: null,
        cancelled: false,
      };

      if (current) {
        const history = historyBefore(current.turns, null);
        setConversations((items) =>
          items.map((conversation) =>
            conversation.id === current.id
              ? { ...conversation, turns: [...conversation.turns, turn] }
              : conversation,
          ),
        );
        run(current.id, turn, history);
      } else {
        const conversation = {
          id: newId("conversation"),
          title: question,
          turns: [turn],
        };
        setConversations((items) => [conversation, ...items]);
        setActiveId(conversation.id);
        run(conversation.id, turn, []);
      }
    },
    [activeId, conversations, run],
  );

  const retry = useCallback(
    (conversationId, turnId) => {
      const conversation = conversations.find((item) => item.id === conversationId);
      const turn = conversation?.turns.find((item) => item.id === turnId);
      if (!turn || turn.status === "pending") return;

      const restarted = {
        ...turn,
        status: "pending",
        startedAt: Date.now(),
        error: null,
        cancelled: false,
      };

      updateTurn(conversationId, turnId, restarted);
      run(conversationId, restarted, historyBefore(conversation.turns, turnId));
    },
    [conversations, run, updateTurn],
  );

  const cancel = useCallback((turnId) => {
    controllers.current.get(turnId)?.abort();
  }, []);

  const startNew = useCallback(() => setActiveId(null), []);

  const active =
    conversations.find((conversation) => conversation.id === activeId) || null;

  return {
    conversations,
    active,
    activeId,
    send,
    retry,
    cancel,
    startNew,
    open: setActiveId,
  };
}
```

---

## `frontend/vite.config.js`

```javascript
import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'

// https://vite.dev/config/
export default defineConfig({
  plugins: [react()],
  server: {
    allowedHosts: ['.trycloudflare.com'],   // allow the temporary Cloudflare review tunnel
    proxy: {
      // The FastAPI backend (Docker) — every call in src/api.js uses a relative /api/... path.
      '/api': {
        target: 'http://127.0.0.1:8000',
        changeOrigin: true,
        timeout: 300_000,
        proxyTimeout: 300_000,
      },
    },
  },
})
```

---

## `eval/build_questions.py`

```python
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
# J: follow-up questions (conversation memory). The earlier turn is given as history; the answer must re-fetch figures.
add("J1", "follow_up", "And in FY2023-24?", metric("total_current_assets / total_current_liabilities", ["FY2023-24"]),
    [inp(k, "FY2023-24") for k in ("total_current_assets", "total_current_liabilities")])
Q[-1]["history"] = [{"role": "user", "content": "What was Tata Steel's consolidated current ratio in FY2025-26?"},
                    {"role": "assistant", "content": "Tata Steel's consolidated current ratio in FY2025-26 was 0.75x "
                     "(total current assets 72,265.11 / total current liabilities 96,917.64 INR crore; FY2025-26 AR, p. F142-F143)."}]
rv = lambda y: val("revenue_from_operations", y)
add("J2", "follow_up", "How much did it grow compared with the previous year, in crore and percent?",
    [rv("FY2025-26") - rv("FY2024-25"), (rv("FY2025-26") / rv("FY2024-25") - 1) * 100],
    [inp("revenue_from_operations", y) for y in ("FY2024-25", "FY2025-26")])
Q[-1]["history"] = [{"role": "user", "content": "What was Tata Steel's consolidated revenue from operations in FY2025-26?"},
                    {"role": "assistant", "content": "Consolidated revenue from operations in FY2025-26 was INR 2,32,139.94 crore "
                     "(FY2025-26 AR, consolidated statement of profit and loss, p. F144)."}]
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
```

---

## `eval/run_eval.py`

```python
"""Run the evaluation set and score it in separate tiers: filtered retrieval, numeric accuracy,
citations/retrieval, abstention and grounding. Usage: python eval/run_eval.py [question ids...]"""
import json, re, sys, time
from datetime import datetime
from pathlib import Path
sys.path.insert(0, "src/agent"); sys.path.insert(0, "src/retrieval")
from agent import ask, numbers_in, close
from search import search

Q = json.loads(Path("eval/questions.json").read_text())
only = set(sys.argv[1:])
RES = Path("eval/results"); RES.mkdir(parents=True, exist_ok=True)
stamp = datetime.now().strftime("%Y%m%d_%H%M")
REFUSAL = re.compile(r"could not (find|locate)|couldn.t find|not (available|included|contained|covered|present|disclosed|provided|reported) (in|for)|"
                     r"outside (the )?(scope|period|coverage)|no (information|data|figure|forecast|projection)|"
                     r"cannot (be )?(provide|provided|answer|predict|forecast|supply|supplied|give|given|determined)|"
                     r"do(es)? not (contain|include|cover|provide|disclose|report)|only covers?|beyond the (scope|reports|period)|"
                     r"unable to (provide|find|answer|supply)", re.I)

def num_match(e, found):
    """Match within rounding or 0.5%, in either direction, also when shown as a percentage (x100) or fraction."""
    for n in found:
        for sc in (1, 100, 0.01):
            t = abs(e) * sc
            if close(abs(n), t) or close(t, abs(n)) or (t and abs(abs(n) - t) / t <= 0.005): return True
    return False

print("TIER 1 - FILTERED RETRIEVAL (search only, correct filters given)")
RETRIEVAL = [("key audit matters", dict(report="FY2025-26", scope="consolidated", section="auditor_report"), {"F131"}),
             ("current borrowings", dict(report="FY2025-26", scope="consolidated", types=["note_table"]), {"F204"}),
             ("trade receivables", dict(report="FY2023-24", scope="standalone", types=["note_table"]), {"F70", "F71"}),
             ("total current liabilities", dict(report="FY2025-26", scope="consolidated", types=["statement_table"]), {"F143"})]
hits, rr = 0, 0.0
for qt, f, gold in RETRIEVAL:
    labels = [p.payload.get("page_label") for p in search(qt, k=4, **f)]
    rank = next((i + 1 for i, l in enumerate(labels) if l in gold), None)
    hits += rank is not None; rr += (1 / rank) if rank else 0
    print(f"  {qt:28} gold={sorted(gold)} got={labels} rank={rank}")
t1 = {"hit_rate@4": hits / len(RETRIEVAL), "mrr": rr / len(RETRIEVAL)}
print(f"  Hit Rate@4 = {t1['hit_rate@4']:.3f}   MRR = {t1['mrr']:.3f}\n")

print("TIER 2 - END-TO-END AGENT")
records = []
for q in Q:
    if only and q["id"] not in only: continue
    t = time.time()
    try: answer, info = ask(q["question"], verbose=False, history=q.get("history"))
    except Exception as e: answer, info = f"ERROR: {e}", {"trace": [], "grounded": 0, "total": 0, "unverified": []}
    found = [v for v, _ in numbers_in(answer, signed=True)]
    exp = q["expected_numbers"]
    nh = [num_match(e, found) for e in exp]
    trace_text = " ".join(x.get("result", "") for x in info["trace"])
    labels = sorted({i["page_label"] for i in q["inputs"]} | {s["page_label"] for s in q["expected_sources"]})
    cited = [l for l in labels if re.search(rf"\b{l}\b", answer)]
    retrieved = [l for l in labels if re.search(rf"\b{l}\b", trace_text)]
    refused = bool(REFUSAL.search(answer))
    mentions = [m for m in q["must_mention"] if (re.search(m[3:], answer, re.I) if m.startswith("re:") else m.lower() in answer.lower())]
    r = dict(id=q["id"], category=q["category"], question=q["question"], seconds=round(time.time() - t),
             tool_calls=len(info["trace"]), numeric=f"{sum(nh)}/{len(exp)}" if exp else None,
             numeric_all=all(nh) if exp else None, missed_numbers=[e for e, h in zip(exp, nh) if not h],
             citation=f"{len(cited)}/{len(labels)}" if labels else None,
             retrieval_hit=bool(retrieved) if labels else None,
             mentions=f"{len(mentions)}/{len(q['must_mention'])}" if q["must_mention"] else None,
             must_abstain=q["must_abstain"], refused=refused,
             abstention_ok=refused if q["must_abstain"] else not (refused and exp and not any(nh)),
             grounded=f'{info["grounded"]}/{info["total"]}', unverified=info["unverified"], answer=answer)
    records.append(r)
    print(f'  {r["id"]:3} {r["category"]:14} numeric={r["numeric"] or "-":6} cite={r["citation"] or "-":6} '
          f'mention={r["mentions"] or "-":4} abstention={"OK" if r["abstention_ok"] else "FAIL":4} '
          f'grounded={r["grounded"]:8} {r["seconds"]}s', flush=True)
    time.sleep(2)

nq = [r for r in records if r["numeric"]]
cq = [r for r in records if r["citation"]]
summary = {
    "tier1_filtered_retrieval": t1,
    "numeric_questions_fully_correct": f'{sum(r["numeric_all"] for r in nq)}/{len(nq)}',
    "expected_numbers_found": f'{sum(int(r["numeric"].split("/")[0]) for r in nq)}/{sum(int(r["numeric"].split("/")[1]) for r in nq)}',
    "source_pages_retrieved": f'{sum(r["retrieval_hit"] for r in cq)}/{len(cq)} questions',
    "expected_pages_cited": f'{sum(int(r["citation"].split("/")[0]) for r in cq)}/{sum(int(r["citation"].split("/")[1]) for r in cq)}',
    "abstention_correct": f'{sum(r["abstention_ok"] for r in records)}/{len(records)}',
    "answers_fully_grounded": f'{sum(not r["unverified"] for r in records)}/{len(records)}',
    "avg_seconds": round(sum(r["seconds"] for r in records) / max(1, len(records))),
    "avg_tool_calls": round(sum(r["tool_calls"] for r in records) / max(1, len(records)), 1)}
print("\nSUMMARY"); [print(f"  {k:34} {v}") for k, v in summary.items()]
(RES / f"run_{stamp}.json").write_text(json.dumps({"summary": summary, "records": records}, indent=1, ensure_ascii=False))
with open(RES / f"answers_{stamp}.md", "w") as fh:
    for r in records: fh.write(f"## {r['id']} ({r['category']})\n**Q:** {r['question']}\n\n{r['answer']}\n\n---\n\n")
print(f"\nSaved eval/results/run_{stamp}.json and answers_{stamp}.md")
```

---

## `tests/test_backend_review.py`

```python
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
```

---

## `tests/test_scores.py`

```python
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
```

---

## `tests/test_segments.py`

```python
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
```

---

## `Dockerfile`

```dockerfile
# Backend image: FastAPI + agent + hybrid search. Data, eval results and model cache are mounted at runtime.
FROM python:3.11-slim
WORKDIR /app
ENV PYTHONUNBUFFERED=1
COPY requirements-api.txt .
RUN pip install --no-cache-dir -r requirements-api.txt
COPY src/ src/
EXPOSE 8000
CMD ["uvicorn", "main:app", "--app-dir", "src/api", "--host", "0.0.0.0", "--port", "8000"]
```

---

## `docker-compose.yml`

```yaml
# Deployment (brief Section 10): Docker Compose on this machine, published through a Cloudflare Tunnel.
# Backend only:   docker compose up -d --build qdrant backend
# Full stack:     docker compose --profile full up -d --build     (after the frontend is merged)
services:
  qdrant:
    image: qdrant/qdrant:latest
    restart: unless-stopped
    volumes:
      - ./qdrant_storage:/qdrant/storage          # bind mount: the existing index, persisted on disk
    ports:
      - "127.0.0.1:6333:6333"                     # local only: lets host scripts (evaluation, re-indexing) reach Qdrant

  backend:
    build: .
    restart: unless-stopped
    env_file: .env                                # OLLAMA_API_KEY (never committed)
    environment:
      QDRANT_URL: http://qdrant:6333
      HF_HUB_OFFLINE: "1"                         # use the downloaded models in .cache only; never depend on the network at start-up
    volumes:
      - ./data:/app/data:ro
      - ./eval:/app/eval:ro
      - ./.cache:/app/.cache                      # embedding models, downloaded once
    depends_on: [qdrant]
    ports:
      - "127.0.0.1:8000:8000"                     # local only; the public goes through the tunnel

  frontend:
    build: ./frontend
    restart: unless-stopped
    depends_on: [backend]                         # nginx proxies /api/ to http://backend:8000
    ports:
      - "127.0.0.1:8080:80"
    profiles: ["full"]

  tunnel:
    image: cloudflare/cloudflared:latest
    restart: unless-stopped
    command: tunnel --no-autoupdate --url http://frontend:80
    depends_on: [frontend]
    profiles: ["full"]
```

---

## `requirements-api.txt`

```text
# Runtime dependencies for the FastAPI backend (src/api) and agent (src/agent, src/retrieval).
# Ingestion-only packages (docling, torch, pymupdf) are deliberately excluded to keep the image small.
fastapi==0.141.1
uvicorn[standard]==0.54.0
pydantic==2.13.5
qdrant-client[fastembed]==1.19.1
fastembed==0.8.1
ollama==0.6.2
python-dotenv==1.2.3
RapidFuzz==3.14.6
pymupdf==1.28.2
```

---

## `scripts/bench_docling.py`

```python
"""Benchmark Docling (OCR off, accurate tables, 24 threads) over a page range in one run."""
import sys, time
from docling.datamodel.base_models import InputFormat
from docling.datamodel.pipeline_options import PdfPipelineOptions, TableFormerMode
from docling.document_converter import DocumentConverter, PdfFormatOption
try:
    from docling.datamodel.accelerator_options import AcceleratorOptions, AcceleratorDevice
except ImportError:
    from docling.datamodel.pipeline_options import AcceleratorOptions, AcceleratorDevice

pdf_path, first, last = sys.argv[1], int(sys.argv[2]), int(sys.argv[3])
opts = PdfPipelineOptions(do_ocr=False, do_table_structure=True)
opts.table_structure_options.mode = TableFormerMode.ACCURATE
opts.table_structure_options.do_cell_matching = True
opts.accelerator_options = AcceleratorOptions(num_threads=24, device=AcceleratorDevice.CPU)
converter = DocumentConverter(format_options={InputFormat.PDF: PdfFormatOption(pipeline_options=opts)})

t0 = time.time()
converter.initialize_pipeline(InputFormat.PDF)
t1 = time.time()
result = converter.convert(pdf_path, page_range=(first, last))
t2 = time.time()
n = last - first + 1
print(f"\nModel load: {t1 - t0:.1f}s | {n} pages converted in {t2 - t1:.1f}s = {(t2 - t1) / n:.1f}s per page")
print(f"Tables found: {len(result.document.tables)}")
```

---

## `scripts/download_reports.sh`

```bash
#!/bin/bash
# Downloads Tata Steel Integrated Reports & Annual Accounts (FY2022-23 to FY2025-26)
# from the official tatasteel.com investor relations pages into data/raw/
set -e
mkdir -p data/raw
UA="Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36"
curl -L -A "$UA" -o data/raw/TataSteel_FY2022-23.pdf https://www.tatasteel.com/media/18370/tata-steel-ir-2022-23.pdf
curl -L -A "$UA" -o data/raw/TataSteel_FY2023-24.pdf https://www.tatasteel.com/media/21244/integrated-report-and-annual-accounts-fy2023-24.pdf
curl -L -A "$UA" -o data/raw/TataSteel_FY2024-25.pdf https://www.tatasteel.com/media/23973/fy25-integratedreport.pdf
curl -L -A "$UA" -o data/raw/TataSteel_FY2025-26.pdf https://www.tatasteel.com/media/25904/tatasteel-iar-2025-26.pdf
echo "All four reports downloaded to data/raw/"
```

---

## `scripts/model_bakeoff.py`

```python
"""Full agent-loop test of every Ollama Cloud model: tool calls are executed and fed back until a final answer."""
import os, time, ast, operator
from dotenv import load_dotenv
from ollama import Client

load_dotenv()
client = Client(host="https://ollama.com", headers={"Authorization": "Bearer " + os.environ["OLLAMA_API_KEY"]})

OPS = {ast.Add: operator.add, ast.Sub: operator.sub, ast.Mult: operator.mul, ast.Div: operator.truediv, ast.USub: operator.neg}
def calculate(expression: str) -> str:
    """Safe arithmetic evaluator: numbers and + - * / only, no code execution."""
    def ev(n):
        if isinstance(n, ast.Constant): return n.value
        if isinstance(n, ast.BinOp): return OPS[type(n.op)](ev(n.left), ev(n.right))
        if isinstance(n, ast.UnaryOp): return OPS[type(n.op)](ev(n.operand))
        raise ValueError("unsupported expression")
    return str(round(ev(ast.parse(expression.replace(",", ""), mode="eval").body), 6))

TOOLS = [{"type": "function", "function": {
    "name": "calculate",
    "description": "Evaluate an arithmetic expression exactly. Use this for ALL arithmetic.",
    "parameters": {"type": "object", "properties": {
        "expression": {"type": "string", "description": "Plain arithmetic, e.g. 72265.11 / 96917.64"}},
        "required": ["expression"]}}}]
PROMPT = ("From Tata Steel's consolidated balance sheet (Rs crore): FY2025-26 total current assets 72,265.11 "
          "and total current liabilities 96,917.64; FY2024-25 total current assets 68,391.54 and total current "
          "liabilities 86,093.55. Compute the current ratio for both years using the calculate tool. "
          "Do not do any arithmetic yourself. Give the final ratios to 4 decimal places.")

models = [m.model for m in client.list().models]
for m in models:
    t, msgs, n_calls = time.time(), [{"role": "user", "content": PROMPT}], 0
    try:
        for _ in range(6):
            r = client.chat(model=m, messages=msgs, tools=TOOLS)
            msgs.append(r.message)
            if not r.message.tool_calls:
                break
            for c in r.message.tool_calls:
                n_calls += 1
                msgs.append({"role": "tool", "tool_name": "calculate", "content": calculate(c.function.arguments["expression"])})
        final = " ".join((r.message.content or "").split())
        ok = "PASS" if ("0.7456" in final and "0.7944" in final) else "FAIL"
        print(f"{m:24} {ok}  {time.time() - t:5.1f}s  tool_calls={n_calls}  | {final[:70]}")
    except Exception as e:
        err = "PAID ONLY" if "free usage" in str(e) else f"ERROR: {str(e)[:70]}"
        print(f"{m:24} {err}")
```

---

## `scripts/test_docling_page.py`

```python
"""Run Docling table extraction (OCR off, embedded PDF text only) on a single page."""
import sys, time
from docling.datamodel.base_models import InputFormat
from docling.datamodel.pipeline_options import PdfPipelineOptions
from docling.document_converter import DocumentConverter, PdfFormatOption

pdf_path, page = sys.argv[1], int(sys.argv[2])
opts = PdfPipelineOptions(do_ocr=False, do_table_structure=True)
opts.table_structure_options.do_cell_matching = True
converter = DocumentConverter(format_options={InputFormat.PDF: PdfFormatOption(pipeline_options=opts)})

start = time.time()
result = converter.convert(pdf_path, page_range=(page, page))
doc = result.document
print(f"\nPage {page}: {len(doc.tables)} table(s) found in {time.time() - start:.1f}s\n")
for n, table in enumerate(doc.tables, 1):
    print(f"===== TABLE {n} =====")
    print(table.export_to_markdown(doc=doc))
    print()
```

---

## `submission/MACHINE_AND_PLATFORM.txt`

```text
Machine: Ubuntu 22.04.5 LTS, 28 cores, 62 GiB RAM
LAN IP: [removed]
Public IP: [removed]
Platform: Claude Code (terminal) + Claude chat; not VS Code or Antigravity
```