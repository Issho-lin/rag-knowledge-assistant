"""ReAct 端到端评测：走 ``query_agent_react``，评答案 + 可选工具路由 + recall。

用法（需已 ingest，会调 LLM，较慢）：
    uv run python tests/eval/run_react.py --limit 1
    uv run python tests/eval/run_react.py
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

_EVAL_DIR = Path(__file__).resolve().parent
_ROOT = _EVAL_DIR.parents[1]
if str(_EVAL_DIR) not in sys.path:
    sys.path.insert(0, str(_EVAL_DIR))

from rag_assistant.core.logging import configure_logging
from rag_assistant.query.modes.agent_react import query_agent_react

from scoring import score_answer, score_react_tools, score_recall

_GOLDEN = _ROOT / "data/eval/react_golden.json"
_RESULTS_DIR = _ROOT / "data/eval/results"


def run(*, limit: int | None = None, k: int = 4) -> Path:
    configure_logging()
    items = json.loads(_GOLDEN.read_text(encoding="utf-8"))
    if limit is not None:
        items = items[:limit]

    rows: list[dict] = []
    for i, item in enumerate(items, 1):
        q = item["question"]
        print(f"\n[{i}/{len(items)}] {item['id']}: {q}")
        result = query_agent_react(q, k=k)
        scored = score_answer(result.answer, item)
        recall = score_recall(result.chunks, item)
        tools = score_react_tools(result.routed_tool, item)
        passed = scored["passed"]
        if tools is not None and not tools["tools_hit"]:
            passed = False
        row = {
            "id": item["id"],
            "question": q,
            "answer": result.answer,
            "routed_tool": result.routed_tool,
            "routed_kb_id": result.routed_kb_id,
            **scored,
        }
        if recall is not None:
            row.update(recall)
        if tools is not None:
            row.update(tools)
        row["passed"] = passed
        rows.append(row)

        mark = "PASS" if passed else "FAIL"
        extra = ""
        if recall is not None:
            rh = "R✓" if recall["recall_hit"] else "R✗"
            extra += f"  recall={rh}"
        if tools is not None:
            th = "T✓" if tools["tools_hit"] else "T✗"
            extra += f"  tools={th} ({result.routed_tool})"
        print(
            f"  -> {mark}  keyword={scored['keyword_score']}  "
            f"miss={scored['keyword_miss']}{extra}"
        )

    n = len(rows)
    n_pass = sum(1 for r in rows if r["passed"])
    rate = round(n_pass / n, 3) if n else 0.0
    summary = {
        "created_at": datetime.now(timezone.utc).isoformat(),
        "mode": "react",
        "k": k,
        "n": n,
        "pass": n_pass,
        "pass_rate": rate,
        "items": rows,
    }
    _RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    out = _RESULTS_DIR / f"react_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    out.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print("\n======== react eval summary ========")
    print(f"pass: {n_pass}/{n} ({rate})")
    print(f"saved: {out}")
    return out


def main() -> None:
    parser = argparse.ArgumentParser(description="ReAct 端到端 golden 评测")
    parser.add_argument("--limit", type=int, default=None, help="只跑前 N 题（建议先 1）")
    parser.add_argument("--k", type=int, default=4)
    args = parser.parse_args()
    run(limit=args.limit, k=args.k)


if __name__ == "__main__":
    main()
