"""多轮对话：轮次结构与历史裁剪。"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

Role = Literal["user", "assistant"]

# 保留最近 N 条消息（约 3 轮问答），避免改写 prompt 过长
MAX_HISTORY_MESSAGES = 6


@dataclass(frozen=True)
class ChatTurn:
    role: Role
    content: str


def trim_history(
    history: list[ChatTurn] | None,
    *,
    max_messages: int = MAX_HISTORY_MESSAGES,
) -> list[ChatTurn]:
    """只保留最近若干条，供改写与展示。"""
    if not history:
        return []
    if max_messages <= 0:
        return []
    return history[-max_messages:]


def format_history(history: list[ChatTurn]) -> str:
    """把对话历史格式化为可读文本（供改写 prompt 使用）。"""
    lines: list[str] = []
    for turn in history:
        label = "用户" if turn.role == "user" else "助手"
        lines.append(f"{label}：{turn.content.strip()}")
    return "\n".join(lines)
