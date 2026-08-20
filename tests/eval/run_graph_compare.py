"""关系题：无图（文档检索）vs 有图（Cypher）对照，不调生成 LLM。"""

from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[2]
if str(Path(__file__).resolve().parent) not in sys.path:
    sys.path.insert(0, str(Path(__file__).resolve().parent))

from rag_assistant.core.logging import configure_logging
from rag_assistant.graph.query import query_relations
from rag_assistant.query.retrieve import retrieve_chunks

QUESTIONS = [
    "周凯的隔级上级是谁？",
    "订单服务间接依赖哪些服务？",
    "报销审批链有哪些环节？",
]


def _preview(chunks: list[dict], n: int = 180) -> str:
    if not chunks:
        return "（无命中）"
    text = str(chunks[0].get("text") or "").replace("\n", " ")
    return text[:n]


def main() -> None:
    configure_logging()
    rows = []
    print("question                         | docs_hit | graph_hit | graph_preview")
    print("-" * 100)
    for q in QUESTIONS:
        docs = retrieve_chunks(q, k=4, retrieve="hybrid", kb_id=None)
        try:
            graph = query_relations(q, k=4)
        except Exception as exc:
            graph = []
            graph_err = str(exc)
        else:
            graph_err = ""
        preview = graph_err or _preview(graph)
        print(
            f"{q:32} | {len(docs):8} | {len(graph):9} | {preview}"
        )
        rows.append(
            {
                "question": q,
                "docs_n": len(docs),
                "docs_sources": [c.get("source") for c in docs],
                "graph_n": len(graph),
                "graph_preview": preview,
            }
        )
    out = _ROOT / "data/eval/results" / f"graph_compare_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(
        json.dumps(
            {"created_at": datetime.now(timezone.utc).isoformat(), "items": rows},
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    print(f"\nsaved: {out}")


if __name__ == "__main__":
    main()
