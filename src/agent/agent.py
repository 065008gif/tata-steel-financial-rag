"""Financial analysis agent: Ollama Cloud LLM + tool loop over verified figures, hybrid search and a calculator."""
import json, os, sys
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
1. Every number you state must come from a tool result. Use get_line_items for balance sheet, profit and loss and cash flow
   figures. Use search_documents for notes, segments, borrowings detail, risks, management commentary and auditor matters.
2. NEVER do arithmetic in your head. Use calculate for every ratio, difference, percentage, average and growth rate.
3. Default to CONSOLIDATED figures unless the user asks for standalone. Always say which you used.
4. Cite every figure: report, statement or section, and page, e.g. (FY2025-26 AR, consolidated balance sheet, p. F143).
5. If a value is marked restated, use the restated value and mention the originally reported figure.
6. If the answer is not in these reports (another company, a year before FY2021-22, forecasts or future values),
   say so clearly and do not guess.
7. Interpret: explain what the numbers mean and what drove them, not just the numbers.

STANDARD DEFINITIONS (state the definition you used)
- Current ratio = Total current assets / Total current liabilities
- Total debt = Non-current borrowings + Current borrowings (lease liabilities shown separately if relevant)
- Debt-to-equity = Total debt / Total equity
- Net profit margin = Profit for the year / Revenue from operations
- Interest coverage = (Profit before tax + Finance costs) / Finance costs
- ROE = Profit for the year / Average total equity (average of opening and closing)
- YoY change % = (Current - Prior) / Prior * 100
Answer in clear prose with a small table where it helps."""

def chat(msgs):
    last = None
    for m in MODELS:
        try:
            return client.chat(model=m, messages=msgs, tools=SCHEMAS, options={"temperature": 0.1})
        except Exception as e:
            last = e
            print(f"  [model {m} failed: {str(e)[:100]}]", flush=True)
    raise last

def ask(question, max_steps=14, verbose=True):
    msgs, trace = [{"role": "system", "content": SYSTEM}, {"role": "user", "content": question}], []
    for _ in range(max_steps):
        r = chat(msgs)
        msgs.append(r.message)
        if not r.message.tool_calls:
            return r.message.content, trace
        for c in r.message.tool_calls:
            name, args = c.function.name, dict(c.function.arguments)
            try:
                result = FUNCS[name](**args)
            except Exception as e:
                result = {"error": str(e)}
            trace.append({"tool": name, "args": args})
            if verbose: print(f"  -> {name}({json.dumps(args)[:140]})", flush=True)
            msgs.append({"role": "tool", "tool_name": name, "content": json.dumps(result, ensure_ascii=False)[:12000]})
    return "I could not complete this analysis within the step limit.", trace

if __name__ == "__main__":
    answer, _ = ask(" ".join(sys.argv[1:]))
    print("\n" + answer)
