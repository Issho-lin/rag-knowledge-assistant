"""知识库搜索工具：ReAct / --agent 的统一检索出口。

职责划分：
- 本模块：单库检索 + 格式化为 Observation 文本（不调用 LLM）
- ``--react``：Agent 读 Observation 后自行写终答
- ``--agent``：Python 在工具外调用 ``produce_answer`` 写终答
"""

from __future__ import annotations

from dataclasses import dataclass, field

from langchain_core.tools import StructuredTool

from ..core.config import get_settings
from ..answer.refusal import RefusalReason, pre_llm_refusal
from .registry import KnowledgeBase, get_kb, list_kbs

# Observation 中单条 chunk 正文的最大预览长度（避免 token 爆炸）
_PREVIEW_LEN = 400


@dataclass(frozen=True)
class ToolSearchResult:
    """单次工具调用的结构化结果（供 KbToolRunContext 收集，与 Observation 字符串并行存在）。"""

    kb_id: str
    tool_name: str
    query: str  # Agent 传入的检索子问句（可与用户原问不同）
    chunks: list[dict]
    refused: bool  # pre_llm_refusal 是否命中
    refusal_reason: RefusalReason | None


@dataclass
class KbToolRunContext:
    """ReAct 执行期间收集各次工具调用结果，供 loop 层合并 chunks 与引用。"""

    results: list[ToolSearchResult] = field(default_factory=list)

    @property
    def last_result(self) -> ToolSearchResult | None:
        return self.results[-1] if self.results else None


def format_chunks_observation(
    chunks: list[dict],
    *,
    kb_id: str,
    refusal_reason: RefusalReason | None = None,
) -> str:
    """把检索片段格式化为工具 Observation（供 Agent 阅读，不调用 LLM）。"""
    # 无命中或 NO_CHUNKS：给 Agent 明确信号，可换库重试
    if refusal_reason == RefusalReason.NO_CHUNKS or not chunks:
        return f"（{kb_id}）未检索到相关片段。"
    if refusal_reason == RefusalReason.LOW_CONFIDENCE:
        header = f"（{kb_id}）检索置信度过低，以下片段仅供参考（{len(chunks)} 条）："
    else:
        header = f"（{kb_id}）检索到 {len(chunks)} 条片段："

    lines = [header, ""]
    for i, chunk in enumerate(chunks, 1):
        source = chunk.get("source", "?")
        score = float(chunk.get("score", 0.0))
        text = str(chunk.get("text", "")).strip()
        if len(text) > _PREVIEW_LEN:
            text = text[:_PREVIEW_LEN] + "…"
        media = str(chunk.get("media_path") or "").strip()
        # [1][2] 编号与 Agent 终答中的引用标注对齐
        if media and (chunk.get("kind") == "image" or media != source):
            lines.append(f"[{i}] {source} (score={score:.3f}, media={media})")
        else:
            lines.append(f"[{i}] {source} (score={score:.3f})")
        lines.append(text)
        lines.append("")
    return "\n".join(lines).strip()


def run_kb_retrieve(
    kb_id: str,
    query: str,
    *,
    k: int = 4,
    retrieve: str = "hybrid",
    use_rerank: bool | None = None,
) -> ToolSearchResult:
    """在指定 KB 内检索，返回片段（ReAct 工具与 --agent 的统一检索入口）。"""
    kb = get_kb(kb_id)
    if kb.backend == "graph":
        from ..graph.query import query_relations

        chunks = query_relations(query, k=k)
        reason = pre_llm_refusal(chunks, use_rerank=False)
        if reason == RefusalReason.NO_CHUNKS:
            chunks = []
        return ToolSearchResult(
            kb_id=kb.id,
            tool_name=kb.tool_name,
            query=query,
            chunks=chunks,
            refused=reason is not None,
            refusal_reason=reason,
        )

    from ..query.retrieve import retrieve_chunks

    do_rerank = get_settings().rerank_enabled if use_rerank is None else use_rerank
    chunks = retrieve_chunks(
        query,
        k=k,
        retrieve=retrieve,
        use_rerank=do_rerank,
        kb_id=kb_id,
    )
    # 工具层拒答：只影响 Observation 文案与 chunks 是否清空，不阻止 Agent 换库
    reason = pre_llm_refusal(chunks, use_rerank=do_rerank)
    if reason == RefusalReason.NO_CHUNKS:
        chunks = []
    return ToolSearchResult(
        kb_id=kb_id,
        tool_name=kb.tool_name,
        query=query,
        chunks=chunks,
        refused=reason is not None,
        refusal_reason=reason,
    )


def _tool_fn_for_kb(
    kb: KnowledgeBase,
    *,
    k: int,
    retrieve: str,
    use_rerank: bool | None,
    context: KbToolRunContext | None,
):
    """为单个 KB 生成 LangChain 工具函数：检索 → 写 context → 返回 Observation 字符串。"""
    def search(query: str) -> str:
        result = run_kb_retrieve(
            kb.id,
            query,
            k=k,
            retrieve=retrieve,
            use_rerank=use_rerank,
        )
        # ReAct 路径：保留结构化 chunks，Observation 仅给 LLM 读
        if context is not None:
            context.results.append(result)
        return format_chunks_observation(
            result.chunks,
            kb_id=result.kb_id,
            refusal_reason=result.refusal_reason,
        )

    search.__name__ = kb.tool_name
    return search


def build_kb_tools(
    *,
    k: int = 4,
    retrieve: str = "hybrid",
    use_rerank: bool | None = None,
    context: KbToolRunContext | None = None,
) -> list[StructuredTool]:
    """为注册表中每个 KB 构建 LangChain StructuredTool（仅检索，name/description 供 Agent 选型）。"""
    return [
        StructuredTool.from_function(
            func=_tool_fn_for_kb(
                kb,
                k=k,
                retrieve=retrieve,
                use_rerank=use_rerank,
                context=context,
            ),
            name=kb.tool_name,
            description=kb.description,
        )
        for kb in list_kbs()
    ]
