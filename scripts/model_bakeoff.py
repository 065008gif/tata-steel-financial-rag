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
