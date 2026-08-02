"""问答阶段的检索、预处理与编排。

子模块：
- ``query.result`` — QueryResult
- ``query.retrieve`` — 检索入口
- ``query.preprocess`` — 改写 / 分解
- ``query.modes`` — direct / agent_route / agent_react
"""

from .result import QueryResult
from .retrieve import merge_retrieval_options, retrieve_chunks

__all__ = [
    "QueryResult",
    "merge_retrieval_options",
    "retrieve_chunks",
]
