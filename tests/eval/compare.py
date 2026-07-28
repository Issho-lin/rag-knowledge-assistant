"""一键跑三路检索对照：vector / hybrid / hybrid+rerank。

用法：
    uv run python tests/eval/compare.py
    uv run python tests/eval/compare.py --limit 5
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

_EVAL_DIR = Path(__file__).resolve().parent
_ROOT = _EVAL_DIR.parents[1]
if str(_EVAL_DIR) not in sys.path:
    sys.path.insert(0, str(_EVAL_DIR))

from run import run

_PROFILES: list[tuple[str, str, bool | None]] = [
    ("vector", "vector_norerank", False),
    ("hybrid", "hybrid_norerank", False),
    ("hybrid", "hybrid_rerank", True),
]


def compare(*, limit: int | None = None, k: int = 4) -> Path:
    summaries: list[dict] = []
    paths: list[Path] = []

    for retrieve, tag, use_rerank in _PROFILES:
        print(f"\n{'=' * 60}\n>>> {tag}\n{'=' * 60}")
        out = run(
            limit=limit,
            k=k,
            retrieve=retrieve,
            use_rerank=use_rerank,
            tag=tag,
        )
        paths.append(out)
        summaries.append(json.loads(out.read_text(encoding="utf-8")))

    report = {
        "profiles": [
            {
                "tag": s["tag"],
                "retrieve": s["retrieve"],
                "use_rerank": s["use_rerank"],
                "pass_rate": s["pass_rate"],
                "avg_keyword_score": s["avg_keyword_score"],
                "recall_at_k": s.get("recall_at_k"),
                "result_file": str(p),
            }
            for s, p in zip(summaries, paths)
        ]
    }

    out_path = _ROOT / "data/eval/results/compare_latest.json"
    out_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    print("\n" + "=" * 60)
    print("三路对照")
    print("=" * 60)
    header = f"{'profile':<20} {'pass':>8} {'keyword':>8} {'recall@k':>10}"
    print(header)
    print("-" * len(header))
    for s in summaries:
        recall = s.get("recall_at_k")
        recall_s = f"{recall:.3f}" if recall is not None else "n/a"
        print(
            f"{s['tag']:<20} {s['pass_rate']:>8.3f} "
            f"{s['avg_keyword_score']:>8.3f} {recall_s:>10}"
        )
    print(f"\n对照报告: {out_path}")
    return out_path


def main() -> None:
    parser = argparse.ArgumentParser(description="三路检索 eval 对照")
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--k", type=int, default=4)
    args = parser.parse_args()
    compare(limit=args.limit, k=args.k)


if __name__ == "__main__":
    main()
