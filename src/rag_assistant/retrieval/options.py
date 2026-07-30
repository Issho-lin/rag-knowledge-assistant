"""检索后处理选项：过滤 / 子查询分解 / 父文档扩展。

默认全关，与 hybrid+rerank baseline 行为一致；对照实验通过 RetrievalOptions 或 .env 开关。
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class RetrievalOptions:
    """可插拔检索增强；日后迁入 COMMON_PROFILE 或各 KB Profile。"""

    # 低分过滤（重排后 cross-encoder 分数）
    filter_low_score: bool = False
    min_score: float | None = None

    # 元数据过滤（分库预演）：domain / kind / corpus / source_contains
    metadata_filter: dict[str, str] = field(default_factory=dict)

    # 复合问句拆分子查询，多路检索再 RRF 合并
    decompose: bool = False

    # 命中子块时扩展为父节全文
    expand_parent: bool = False

    @classmethod
    def from_settings(cls) -> "RetrievalOptions":
        from ..config import get_settings

        s = get_settings()
        return cls(
            filter_low_score=s.retrieval_filter_enabled,
            min_score=s.retrieval_min_score,
            decompose=s.query_decompose_enabled,
            expand_parent=s.parent_expand_enabled,
        )

    def with_overrides(self, **kwargs: object) -> "RetrievalOptions":
        data = {
            "filter_low_score": self.filter_low_score,
            "min_score": self.min_score,
            "metadata_filter": dict(self.metadata_filter),
            "decompose": self.decompose,
            "expand_parent": self.expand_parent,
        }
        data.update(kwargs)
        return RetrievalOptions(**data)
