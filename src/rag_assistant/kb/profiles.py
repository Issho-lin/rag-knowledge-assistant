"""知识库检索 / 切块策略（Profile）。

COMMON_PROFILE 为默认；各 KB 只覆盖与通用路径的差异项。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

from ..retrieval.options import RetrievalOptions

# 切块策略-1.按markdown段落标题；2.按固定块的大小
ChunkStrategy = Literal["heading", "fixed_window"]


@dataclass(frozen=True)
class KBProfile:
    """单个 KB 的策略：切块 + 检索增强开关。"""
    # 切块策略
    chunk_strategy: ChunkStrategy = "heading"
    max_chars: int = 1200
    # 检索策略
    retrieval: RetrievalOptions = field(default_factory=RetrievalOptions)

    def with_retrieval(self, **kwargs: object) -> "KBProfile":
        return KBProfile(
            chunk_strategy=self.chunk_strategy,
            max_chars=self.max_chars,
            retrieval=self.retrieval.with_overrides(**kwargs),
        )


# 通用默认：与当前 hybrid+rerank 主线一致；增强开关默认关
COMMON_PROFILE = KBProfile()

# 制度 / FAQ / HTML：标题切块1200字 + 可选父文档（长节）
POLICIES_PROFILE = COMMON_PROFILE.with_retrieval(expand_parent=True)

# 表格行数据（CSV 等）：短块、无父文档、不拆复合问；按行检索
TABULAR_PROFILE = KBProfile(
    retrieval=RetrievalOptions(decompose=False, expand_parent=False),
)

# PDF 手册：固定窗口切块800字、不拆复合问、不扩父文档（第 8 周 PDF KB）
PDF_PROFILE = KBProfile(
    chunk_strategy="fixed_window",
    max_chars=800,
    retrieval=RetrievalOptions(decompose=False, expand_parent=False),
)
