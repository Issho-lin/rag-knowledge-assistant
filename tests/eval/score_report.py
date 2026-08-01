"""导出 golden 集每题 rerank top-k 分数，用于标定 REFUSE_MIN_RERANK_SCORE。

用法：
    uv run python tests/eval/score_report.py
    uv run python tests/eval/score_report.py --limit 5
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

from rag_assistant.config import get_settings
from rag_assistant.pipeline import retrieve_chunks

_GOLDEN = _ROOT / "data/eval/golden.json"
_OUT = _ROOT / "data/eval/results/score_report_latest.json"


def run(*, limit: int | None = None, k: int = 4) -> Path:
    """导出 golden 集每题 rerank top-k 分数，用于标定 REFUSE_MIN_RERANK_SCORE。"""
    items = json.loads(_GOLDEN.read_text(encoding="utf-8"))
    if limit is not None:
        items = items[:limit]

    threshold = get_settings().refuse_min_rerank_score
    rows: list[dict] = []
    # 遍历 golden 集每题，检索 top-k 分数
    for item in items:
        q = item["question"]
        chunks = retrieve_chunks(q, k=k, retrieve="hybrid", use_rerank=True)
        scores = [round(float(c.get("score", 0)), 4) for c in chunks]
        top1 = scores[0] if scores else None
        expect_refuse = bool(item.get("expect_refuse", False))
        would_refuse = not chunks  # rerank 后统一低分过滤

        rows.append(
            {
                "id": item["id"],
                "question": q,
                "expect_refuse": expect_refuse,
                "top1_score": top1,
                "topk_scores": scores,
                "n_chunks_after_filter": len(chunks),
                "would_refuse": would_refuse,
            }
        )

    # 库内题
    in_corpus = [r for r in rows if not r["expect_refuse"]]
    # 库外题
    out_corpus = [r for r in rows if r["expect_refuse"]]
    # 库内题 top-1 分数范围
    in_top1 = [r["top1_score"] for r in in_corpus if r["top1_score"] is not None]
    # 库外题 top-1 分数范围
    out_top1 = [r["top1_score"] for r in out_corpus if r["top1_score"] is not None]
    # 库内误拒数
    false_refuse = sum(1 for r in in_corpus if r["would_refuse"])
    # 库外漏拒数
    miss_refuse = sum(1 for r in out_corpus if not r["would_refuse"])

    report = {
        # 原始拒答阈值
        "threshold": threshold,
        "k": k,
        "summary": {
            # 库内题数
            "in_corpus_n": len(in_corpus),
            # 库外题数
            "out_corpus_n": len(out_corpus),
            # 库内题 top-1 最低分
            "in_corpus_top1_min": min(in_top1) if in_top1 else None,
            # 库内题 top-1 最高分
            "in_corpus_top1_max": max(in_top1) if in_top1 else None,
            # 库外题 top-1 最高分
            "out_corpus_top1_max": max(out_top1) if out_top1 else None,
            # 库内误拒数，大于0说明库内题被误拒，阈值太高->调低
            "false_refuse_in_corpus": false_refuse,
            # 库外漏拒数，大于0说明库外题被漏拒，阈值太低->调高
            "miss_refuse_out_corpus": miss_refuse,
            # 两者都为0，说明阈值合适
            "all_ok": false_refuse == 0 and miss_refuse == 0,
            # 两者都大于0，库内外分数有重叠：误拒与漏拒同时存在，单靠调阈值无法两全
            "score_overlap": false_refuse > 0 and miss_refuse > 0,
        },
        "items": rows,
    }

    _OUT.parent.mkdir(parents=True, exist_ok=True)
    _OUT.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"阈值 REFUSE_MIN_RERANK_SCORE = {threshold}")
    print(f"库内题 top-1 范围: {report['summary']['in_corpus_top1_min']} ~ {report['summary']['in_corpus_top1_max']}")
    print(f"库外题 top-1 最高: {report['summary']['out_corpus_top1_max']}")
    print(f"库内误拒: {report['summary']['false_refuse_in_corpus']}  库外漏拒: {report['summary']['miss_refuse_out_corpus']}")
    print()
    print(f"{'id':<22} {'expect':>8} {'top1':>8} {'n':>4} {'拒答?':>6}")
    print("-" * 52)
    for r in rows:
        top_s = f"{r['top1_score']:.3f}" if r["top1_score"] is not None else "n/a"
        print(
            f"{r['id']:<22} {'库外' if r['expect_refuse'] else '库内':>8} "
            f"{top_s:>8} {r['n_chunks_after_filter']:>4} {'是' if r['would_refuse'] else '否':>6}"
        )
    print(f"\n报告: {_OUT}")
    return _OUT


def main() -> None:
    parser = argparse.ArgumentParser(description="golden 检索分数报告（标定拒答阈值）")
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--k", type=int, default=4)
    args = parser.parse_args()
    run(limit=args.limit, k=args.k)


if __name__ == "__main__":
    main()
