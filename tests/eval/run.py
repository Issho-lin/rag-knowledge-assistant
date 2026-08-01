"""Golden set 回归评测：对固定题集跑 RAG，评答案关键词 + recall@k。

用法（在项目根目录）：
    uv run python tests/eval/run.py
    uv run python tests/eval/run.py --limit 3
    uv run python tests/eval/run.py --retrieve vector --no-rerank --tag vector_norerank
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

from rag_assistant.config import get_settings
from rag_assistant.generation import produce_answer
from rag_assistant.logging import configure_logging, get_logger
from rag_assistant.pipeline import retrieve_chunks
from rag_assistant.retrieval.options import RetrievalOptions
from rag_assistant.retrieval.vector import VectorStore

from scoring import score_answer, score_recall

log = get_logger(__name__)

_GOLDEN = _ROOT / "data/eval/golden.json"
_RESULTS_DIR = _ROOT / "data/eval/results"
_CHROMA_PATH = _ROOT / "data/chroma/unified"
_EMPTY_STORE_MSG = (
    "知识库为空。请先执行：python -m rag_assistant.pipeline --ingest --reset"
)


def run(
    *,
    limit: int | None = None,
    k: int = 4,
    retrieve: str = "hybrid",
    use_rerank: bool | None = None,
    tag: str | None = None,
    retrieval_options: RetrievalOptions | None = None,
    default_kb: str | None = None,
) -> Path:
    configure_logging()
    items = json.loads(_GOLDEN.read_text(encoding="utf-8"))
    if limit is not None:
        items = items[:limit]

    store_empty = VectorStore(chroma_path=_CHROMA_PATH).count() == 0

    rows: list[dict] = []
    for i, item in enumerate(items, 1):
        q = item["question"]
        kb_id = default_kb if default_kb is not None else item.get("kb")
        kb_label = f" [kb={kb_id}]" if kb_id else ""
        print(f"\n[{i}/{len(items)}] {item['id']}: {q}{kb_label}")
        chunks = retrieve_chunks(
            q,
            k=k,
            retrieve=retrieve,
            use_rerank=use_rerank,
            options=retrieval_options,
            kb_id=kb_id,
        )
        if store_empty:
            answer = _EMPTY_STORE_MSG
        else:
            do_rerank = (
                get_settings().rerank_enabled if use_rerank is None else use_rerank
            )
            answer, _, _ = produce_answer(q, chunks, use_rerank=do_rerank)
        scored = score_answer(answer, item)
        recall = score_recall(chunks, item)
        row = {
            "id": item["id"],
            "question": q,
            "kb": kb_id,
            "answer": answer,
            **scored,
        }
        if recall is not None:
            row.update(recall)
        rows.append(row)

        mark = "PASS" if scored["passed"] else "FAIL"
        extra = ""
        if recall is not None:
            rh = "R✓" if recall["recall_hit"] else "R✗"
            extra = f"  recall={rh}"
        print(
            f"  -> {mark}  keyword={scored['keyword_score']}  "
            f"miss={scored['keyword_miss']}{extra}"
        )

    n = len(rows)
    n_pass = sum(1 for r in rows if r["passed"])
    avg = sum(r["keyword_score"] for r in rows) / n if n else 0.0
    recall_rows = [r for r in rows if "recall_hit" in r]
    n_recall_hit = sum(1 for r in recall_rows if r["recall_hit"])
    recall_rate = round(n_recall_hit / len(recall_rows), 3) if recall_rows else None

    rerank_label = (
        "rerank"
        if use_rerank is True
        else ("norerank" if use_rerank is False else "rerank-default")
    )
    label = tag or f"{retrieve}_{rerank_label}"
    summary = {
        "created_at": datetime.now(timezone.utc).isoformat(),
        "retrieve": retrieve,
        "use_rerank": use_rerank,
        "default_kb": default_kb,
        "retrieval_options": (
            {
                "decompose": retrieval_options.decompose,
                "expand_parent": retrieval_options.expand_parent,
                "metadata_filter": retrieval_options.metadata_filter,
            }
            if retrieval_options
            else None
        ),
        "k": k,
        "tag": label,
        "n": n,
        "pass": n_pass,
        "pass_rate": round(n_pass / n, 3) if n else 0.0,
        "avg_keyword_score": round(avg, 3),
        "recall_at_k": recall_rate,
        "recall_n": len(recall_rows),
        "recall_hit": n_recall_hit,
        "items": rows,
    }

    _RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    out = _RESULTS_DIR / f"{label}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    out.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")

    print("\n======== eval summary ========")
    print(f"pass: {n_pass}/{n} ({summary['pass_rate']})")
    print(f"avg keyword score: {summary['avg_keyword_score']}")
    if recall_rate is not None:
        print(f"recall@{k}: {n_recall_hit}/{len(recall_rows)} ({recall_rate})")
    print(f"saved: {out}")
    log.info(
        "eval.done",
        pass_rate=summary["pass_rate"],
        avg_keyword_score=summary["avg_keyword_score"],
        recall_at_k=recall_rate,
        path=str(out),
    )
    return out


def main() -> None:
    parser = argparse.ArgumentParser(description="跑 golden set 回归评测")
    parser.add_argument("--limit", type=int, default=None, help="只跑前 N 条（调试用）")
    parser.add_argument("--k", type=int, default=4)
    parser.add_argument(
        "--retrieve",
        choices=("hybrid", "vector"),
        default="hybrid",
        help="检索模式（与 pipeline --retrieve 一致）",
    )
    parser.add_argument(
        "--rerank",
        dest="use_rerank",
        action="store_true",
        default=None,
        help="强制启用重排",
    )
    parser.add_argument(
        "--no-rerank",
        dest="use_rerank",
        action="store_false",
        help="强制关闭重排",
    )
    parser.add_argument("--tag", type=str, default=None, help="结果文件名前缀")
    parser.add_argument(
        "--kb",
        type=str,
        default=None,
        choices=("policies", "tabular", "pdf"),
        help="强制所有题目在该 KB 内检索（覆盖 golden 单条 kb 字段）",
    )
    args = parser.parse_args()
    run(
        limit=args.limit,
        k=args.k,
        retrieve=args.retrieve,
        use_rerank=args.use_rerank,
        tag=args.tag,
        default_kb=args.kb,
    )


if __name__ == "__main__":
    main()
