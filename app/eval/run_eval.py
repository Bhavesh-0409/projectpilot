"""
Runs the golden dataset against the live graph, scores every case with
the judge, and writes eval_results.json + a console summary by
dimension. This is the artifact you demo as your "eval dashboard".

    python -m app.eval.run_eval
"""
import json
from collections import defaultdict
from dotenv import load_dotenv

load_dotenv()

from app.graph.build import get_graph
from app.eval.golden_dataset import GOLDEN
from app.eval.judge import judge_case


def run():
    graph = get_graph()
    results = []

    for case in GOLDEN:
        state = {"user_query": case["input"], "conversation_history": [], "trace": []}
        try:
            out = graph.invoke(state)
            response = out.get("final_response", "")
            required_caps = out.get("required_capabilities", [])
        except Exception as e:
            response = f"[AGENT ERROR] {type(e).__name__}: {e}"
            required_caps = []

        judgment = judge_case(
            query=case["input"],
            response=response,
            required_capabilities=required_caps,
            expected=case["expected"],
            dimension=case["dimension"],
        )

        results.append({
            "id": case["id"],
            "input": case["input"],
            "category": case["category"],
            "dimension": case["dimension"],
            "score": judgment.get("score", 0),
            "reasoning": judgment.get("reasoning", ""),
            "required_capabilities": required_caps,
            "response": response,
        })
        print(f"{case['id']:8s} [{case['dimension']:14s}] score={judgment.get('score')}  {case['input'][:60]}")

    avg = sum(r["score"] for r in results) / len(results) if results else 0

    by_dim = defaultdict(list)
    for r in results:
        by_dim[r["dimension"]].append(r["score"])
    dim_summary = {d: round(sum(v) / len(v), 2) for d, v in by_dim.items()}

    by_cat = defaultdict(list)
    for r in results:
        by_cat[r["category"]].append(r["score"])
    cat_summary = {c: round(sum(v) / len(v), 2) for c, v in by_cat.items()}

    print(f"\nOverall average: {avg:.2f} / 5.0")
    print("By dimension:", dim_summary)
    print("By category :", cat_summary)

    with open("eval_results.json", "w") as f:
        json.dump({
            "results": results,
            "overall_average": avg,
            "by_dimension": dim_summary,
            "by_category": cat_summary,
        }, f, indent=2)
    print("\nWrote eval_results.json")


if __name__ == "__main__":
    run()
