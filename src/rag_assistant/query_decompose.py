"""子查询分解：复合问题拆成多句检索再合并。

例：「会议室怎么订？打印机怎么用？」→ 两次检索 → RRF 合并。
单主题 KB 可在 Profile 关闭以省延迟。
"""

from __future__ import annotations

import json
import re

from langchain_core.messages import HumanMessage, SystemMessage

from .llm import LLMClient
from .logging import get_logger
from .observability import get_langfuse

log = get_logger(__name__)

_DECOMPOSE_SYSTEM = """你是「星云科技」内部知识助手的查询分解模块。

任务：把用户问题拆成 1～3 个可独立用于文档检索的中文子问题。

规则：
1. 若已是单一主题、无需拆分，只输出包含原问题的一个 JSON 数组。
2. 若含多个并列子问题（用问号、顿号、以及、还有 等连接），按子问题拆开。
3. 每个子问题必须能独立检索，补全省略的主语。
4. 只输出 JSON 数组，如 ["子问题1", "子问题2"]，不要其它文字。"""


def _parse_subqueries(raw: str, fallback: str) -> list[str]:
    """解析分解结果
    
    Args:
        raw: 分解结果
        fallback: 兜底问题
    
    Returns:
        子查询列表
    """
    # 修剪分解结果
    text = raw.strip()
    # 尝试直接解析 JSON 数组
    try:
        data = json.loads(text)
        # 如果解析结果为列表，则返回列表中的每个非空问题组成的列表
        if isinstance(data, list):
            items = [str(x).strip() for x in data if str(x).strip()]
            if items:
                return items
    except json.JSONDecodeError:
        pass
    # 如果LLM不严格遵循JSON格式，则尝试提取 [...] 片段，并解析为 JSON 数组
    m = re.search(r"\[[\s\S]*\]", text)
    if m:
        # 如果匹配到 [...] 片段，则尝试解析为 JSON 数组
        try:
            data = json.loads(m.group(0))
            # 如果解析结果为列表，则返回列表中的每个非空问题组成的列表
            if isinstance(data, list):
                items = [str(x).strip() for x in data if str(x).strip()]
                if items:
                    return items
        except json.JSONDecodeError:
            pass

    # 兜底策略，如果LLM分解的结果有问题，只能自己处理
    # 按行或问号切分兜底，并返回列表中的每个元素
    parts = re.split(r"[？?]\s*", fallback)
    items = [p.strip() + "？" for p in parts if p.strip()]
    # 如果切分得到的问题列表长度大于 1，则返回列表
    if len(items) > 1:
        return items

    # 最后兜底就是返回原始问题
    return [fallback]


def decompose_for_retrieval(question: str, *, tier: str = "cheap") -> list[str]:
    """无并列子问题时返回单元素列表；失败时回退原问句。"""

    # 修剪问题
    q = question.strip()

    if not q:
        return [q]

    # 启发式：无明显复合特征则跳过 LLM 分解
    marker_count = sum(q.count(m) for m in ("？", "?"))
    # 不含多个问号且不含 "以及" 或 "还有" 等连接词则跳过 LLM 分解
    if marker_count < 2 and not any(m in q for m in ("以及", "还有")):
        return [q]

    # 构造指引模型进行分解的 messages
    messages = [
        SystemMessage(content=_DECOMPOSE_SYSTEM),
        HumanMessage(content=f"用户问题：{q}\n\nJSON 数组："),
    ]
    # 获取 Langfuse 实例
    lf = get_langfuse()

    if lf is None:
        # 如果 Langfuse 实例为空，则直接调用 LLM 进行分解
        raw = LLMClient().invoke(messages, tier=tier)
    else:
        # 如果 Langfuse 实例不为空，则启动一个 Langfuse 观察，记录分解过程
        with lf.start_as_current_observation(
            name="query-decompose",
            as_type="generation",
            input={"question": q},
        ) as obs:
            # 调用 LLM 进行分解
            raw = LLMClient().invoke(messages, tier=tier)
            obs.update(output=raw)

    # 解析分解结果
    subs = _parse_subqueries(raw, q)
    # 如果分解结果为单元素列表且与原始问题相同，则记录分解过程
    if len(subs) == 1 and subs[0] == q:
        log.info("decompose.unchanged", query=q)
    else:
        log.info("decompose.done", original=q, subqueries=subs)
    return subs
