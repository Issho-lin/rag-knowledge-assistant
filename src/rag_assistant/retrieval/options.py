"""检索后处理选项：子查询分解 / 父文档扩展 / 元数据过滤。

rerank 后的低分过滤已与拒答阈值合并（见 retrieval/engine.py），不在此重复配置。
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class RetrievalOptions:
    """可插拔检索增强；日后迁入 COMMON_PROFILE 或各 KB Profile。"""

    # 元数据过滤：`--kb` 等在 Chroma where / BM25 子集召回阶段下推
    metadata_filter: dict[str, str] = field(default_factory=dict)

    # 复合问句拆分子查询，多路检索再 RRF 合并
    decompose: bool = False

    # 命中子块时扩展为父节全文
    expand_parent: bool = False

    @classmethod
    def from_settings(cls) -> "RetrievalOptions":
        from ..core.config import get_settings

        s = get_settings()
        return cls(
            decompose=s.query_decompose_enabled,
            expand_parent=s.parent_expand_enabled,
        )

    def with_overrides(self, **kwargs: object) -> "RetrievalOptions":
        data = {
            "metadata_filter": dict(self.metadata_filter),
            "decompose": self.decompose,
            "expand_parent": self.expand_parent,
        }
        data.update(kwargs)
        return RetrievalOptions(**data)
