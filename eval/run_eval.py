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
    try: answer, info = ask(q["question"], verbose=False)
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
