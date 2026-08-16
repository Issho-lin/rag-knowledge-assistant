"""三种问答模式（与 CLI 开关一一对应）。

主路径：``query_agent_react``（``--react``）；辅助：``query``、``query_agent``。
"""

from .agent_react import query_agent_react
from .agent_route import query_agent
from .direct import query

__all__ = ["query", "query_agent", "query_agent_react"]
