"""一键跑多组 eval 对照。

用法：
    # 检索模式：vector / hybrid / hybrid+rerank（默认）
    uv run python tests/eval/compare.py
    uv run python tests/eval/compare.py --suite retrieval --limit 5

    # 检索增强：filter / decompose / parent / all（固定 hybrid+rerank）
    uv run python tests/eval/compare.py --suite enhanced
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

_EVAL_DIR = Path(__file__).resolve().parent
_ROOT = _EVAL_DIR.parents[1]
if str(_EVAL_DIR) not in sys.path:
    sys.path.insert(0, str(_EVAL_DIR))

from rag_assistant.retrieval.options import RetrievalOptions

from run import run


@dataclass(frozen=True)
class CompareProfile:
    tag: str
    retrieve: str = "hybrid"
    use_rerank: bool | None = True
    retrieval_options: RetrievalOptions | None = None


_RETRIEVAL_PROFILES: list[CompareProfile] = [
    CompareProfile("vector_norerank", retrieve="vector", use_rerank=False),
    CompareProfile("hybrid_norerank", retrieve="hybrid", use_rerank=False),
    CompareProfile("hybrid_rerank", retrieve="hybrid", use_rerank=True),
]

_ENHANCED_PROFILES: list[CompareProfile] = [
    CompareProfile(
        "retrieval_baseline",
        retrieval_options=RetrievalOptions(
            filter_low_score=False, decompose=False, expand_parent=False
        ),
    ),
    CompareProfile(
        "retrieval_filter",
        retrieval_options=RetrievalOptions(
            filter_low_score=True, decompose=False, expand_parent=False
        ),
    ),
    CompareProfile(
        "retrieval_decompose",
        retrieval_options=RetrievalOptions(
            filter_low_score=False, decompose=True, expand_parent=False
        ),
    ),
    CompareProfile(
        "retrieval_parent",
        retrieval_options=RetrievalOptions(
            filter_low_score=False, decompose=False, expand_parent=True
        ),
    ),
    CompareProfile(
        "retrieval_all_enhanced",
        retrieval_options=RetrievalOptions(
            filter_low_score=True, decompose=True, expand_parent=True
        ),
    ),
]

_SUITES: dict[str, tuple[str, Path, list[CompareProfile], str | None]] = {
    "retrieval": (
        "检索模式三路对照",
        _ROOT / "data/eval/results/compare_latest.json",
        _RETRIEVAL_PROFILES,
        None,
    ),
    "enhanced": (
        "检索增强五路对照",
        _ROOT / "data/eval/results/compare_enhanced_retrieval_latest.json",
        _ENHANCED_PROFILES,
        (
            "filter 需 hybrid+rerank；parent 需 --ingest --reset 写入 parent_text；"
            "decompose 对复合问句（如 admin-faq）预期 recall 提升"
        ),
    ),
}


def _profile_row(summary: dict[str, Any], result_path: Path) -> dict[str, Any]:
    row: dict[str, Any] = {
        "tag": summary["tag"],
        "pass_rate": summary["pass_rate"],
        "avg_keyword_score": summary["avg_keyword_score"],
        "recall_at_k": summary.get("recall_at_k"),
        "result_file": str(result_path),
    }
    if "retrieve" in summary:
        row["retrieve"] = summary["retrieve"]
    if "use_rerank" in summary:
        row["use_rerank"] = summary["use_rerank"]
    if summary.get("retrieval_options") is not None:
        row["retrieval_options"] = summary["retrieval_options"]
    return row


def compare(
    *,
    suite: str = "retrieval",
    limit: int | None = None,
    k: int = 4,
) -> Path:
    title, out_path, profiles, note = _SUITES[suite]
    summaries: list[dict] = []
    paths: list[Path] = []

    for profile in profiles:
        print(f"\n{'=' * 60}\n>>> {profile.tag}\n{'=' * 60}")
        out = run(
            limit=limit,
            k=k,
            retrieve=profile.retrieve,
            use_rerank=profile.use_rerank,
            tag=profile.tag,
            retrieval_options=profile.retrieval_options,
        )
        paths.append(out)
        summaries.append(json.loads(out.read_text(encoding="utf-8")))

    report: dict[str, Any] = {
        "suite": suite,
        "profiles": [_profile_row(s, p) for s, p in zip(summaries, paths)],
    }
    if note:
        report["note"] = note

    out_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    print("\n" + "=" * 60)
    print(title)
    print("=" * 60)
    tag_width = max(len(s["tag"]) for s in summaries) if summaries else 16
    header = f"{'profile':<{tag_width}} {'pass':>8} {'keyword':>8} {'recall@k':>10}"
    print(header)
    print("-" * len(header))
    for s in summaries:
        recall = s.get("recall_at_k")
        recall_s = f"{recall:.3f}" if recall is not None else "n/a"
        print(
            f"{s['tag']:<{tag_width}} {s['pass_rate']:>8.3f} "
            f"{s['avg_keyword_score']:>8.3f} {recall_s:>10}"
        )
    print(f"\n对照报告: {out_path}")
    return out_path


def main() -> None:
    parser = argparse.ArgumentParser(description="多组 eval 对照")
    parser.add_argument(
        "--suite",
        choices=tuple(_SUITES),
        default="retrieval",
        help="retrieval=vector/hybrid/rerank；enhanced=filter/decompose/parent",
    )
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--k", type=int, default=4)
    args = parser.parse_args()
    compare(suite=args.suite, limit=args.limit, k=args.k)


if __name__ == "__main__":
    main()
