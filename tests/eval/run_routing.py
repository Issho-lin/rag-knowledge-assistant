"""路由专项评测：只测 Agent 是否选对 KB 工具（不调 RAG 生成）。

用法：
    uv run python tests/eval/run_routing.py
    uv run python tests/eval/run_routing.py --limit 5
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

from rag_assistant.query.modes.agent_route import select_tool_names
from rag_assistant.core.logging import configure_logging

from scoring import score_routing

_GOLDEN = _ROOT / "data/eval/golden.json"
_RESULTS_DIR = _ROOT / "data/eval/results"


def run(*, limit: int | None = None) -> Path:
    configure_logging()
    items = [
        i for i in json.loads(_GOLDEN.read_text(encoding="utf-8")) if i.get("expected_tool")
    ]
    if limit is not None:
        items = items[:limit]

    rows: list[dict] = []
    for i, item in enumerate(items, 1):
        q = item["question"]
        print(f"\n[{i}/{len(items)}] {item['id']}: {q}")
        tools = select_tool_names(q)
        scored = score_routing(tools, item)
        assert scored is not None
        row = {"id": item["id"], "question": q, "tool_calls": tools, **scored}
        rows.append(row)
        mark = "PASS" if scored["routing_hit"] else "FAIL"
        print(f"  -> {mark}  expected={scored['expected_tool']}  got={scored['selected_tool']}")

    n = len(rows)
    n_hit = sum(1 for r in rows if r["routing_hit"])
    rate = round(n_hit / n, 3) if n else 0.0
    summary = {
        "created_at": datetime.now(timezone.utc).isoformat(),
        "n": n,
        "routing_hit": n_hit,
        "routing_rate": rate,
        "items": rows,
    }
    _RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    out = _RESULTS_DIR / f"routing_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    out.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print("\n======== routing summary ========")
    print(f"routing: {n_hit}/{n} ({rate})")
    print(f"saved: {out}")
    return out


def main() -> None:
    parser = argparse.ArgumentParser(description="Agent 路由专项评测")
    parser.add_argument("--limit", type=int, default=None)
    args = parser.parse_args()
    run(limit=args.limit)


if __name__ == "__main__":
    main()
