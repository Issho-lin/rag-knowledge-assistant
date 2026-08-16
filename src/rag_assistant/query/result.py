"""问答结果（一次 query 的完整返回）。"""

from __future__ import annotations

from dataclasses import dataclass

from ..answer import Citation, format_answer_with_sources, format_sources_block
from ..answer.refusal import RefusalReason


@dataclass
class QueryResult:
    """一次问答的完整结果：正文、检索片段、结构化引用。"""

    answer: str
    chunks: list[dict]  # ReAct：各次工具 chunks 合并后的全集
    citations: list[Citation]
    refused: bool = False
    refusal_reason: RefusalReason | None = None
    rewritten_query: str | None = None  # 多轮改写后的 search_q
    routed_tool: str | None = None  # ReAct：实际调用的工具名（可多个，逗号分隔）
    routed_kb_id: str | None = None  # 最后一次工具对应的 kb_id

    def display_text(self) -> str:
        """供 CLI 打印：正文 + 参考来源块。"""
        return format_answer_with_sources(self.answer, self.chunks)

    def sources_text(self) -> str:
        return format_sources_block(self.citations)

    def refusal_note(self) -> str | None:
        """拒答原因的人类可读说明（CLI 用）。"""
        if not self.refused or self.refusal_reason is None:
            return None
        labels = {
            RefusalReason.NO_CHUNKS: "未检索到相关片段",
            RefusalReason.LOW_CONFIDENCE: "检索置信度过低",
            RefusalReason.MODEL: "模型判断文档无依据",
        }
        return labels.get(self.refusal_reason, self.refusal_reason.value)
