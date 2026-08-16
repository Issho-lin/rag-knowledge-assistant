"""分块策略：按 Markdown 标题切分（制度/FAQ 类文档的常规做法）。

原则：
  - 一节（标题 + 正文）尽量保持完整，避免把条款从所属标题下拆开
  - 单节过长时再按段落打包，并限制最大长度
  - 切出的块自带标题，检索时上下文完整
"""

from __future__ import annotations

import re

from dataclasses import dataclass

from .loaders import Document

_HEADING = re.compile(r"^(#{1,6})\s+(.+)$", re.MULTILINE)


@dataclass
class ChunkInfo:
    """切块结果：子块文本 + 所属父节（供父文档检索扩展）。"""

    text: str
    parent_text: str
    chunk_index: int

def _pack_paragraphs(text: str, max_chars: int) -> list[str]:
    """把长文本按空行分段，再拼成不超过 max_chars 的块。"""
    paragraphs = [p.strip() for p in re.split(r"\n\s*\n", text) if p.strip()]
    if not paragraphs:
        return [text.strip()] if text.strip() else []

    chunks: list[str] = []
    buf = ""
    for p in paragraphs:
        candidate = f"{buf}\n\n{p}".strip() if buf else p
        if len(candidate) <= max_chars:
            buf = candidate
            continue
        if buf:
            chunks.append(buf)
        # 单段本身超长：硬切（少见；表格大段时可能碰到）
        if len(p) <= max_chars:
            buf = p
        else:
            for i in range(0, len(p), max_chars):
                piece = p[i : i + max_chars].strip()
                if piece:
                    chunks.append(piece)
            buf = ""
    if buf:
        chunks.append(buf)
    return chunks


def chunk_by_heading_info(doc: Document, max_chars: int = 1200) -> list[ChunkInfo]:
    """按标题切分；过长节再按段落打包，保留父节全文。

    父文档检索：检索命中子块时可扩展为 parent_text。

    没有触发段落打包的，父文本与子文本相同
    """
    text = doc.text.strip()
    if not text:
        doc.chunks = []
        return []

    matches = list(_HEADING.finditer(text))
    sections: list[str] = []

    if not matches:
        sections = [text]
    else:
        if matches[0].start() > 0:
            preamble = text[: matches[0].start()].strip()
            if preamble:
                sections.append(preamble)
        for i, m in enumerate(matches):
            end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
            section = text[m.start() : end].strip()
            if section:
                sections.append(section)

    infos: list[ChunkInfo] = []
    for section in sections:
        if len(section) <= max_chars:
            infos.append(
                ChunkInfo(text=section, parent_text=section, chunk_index=len(infos))
            )
        else:
            for piece in _pack_paragraphs(section, max_chars):
                infos.append(
                    ChunkInfo(text=piece, parent_text=section, chunk_index=len(infos))
                )

    doc.chunks = [c.text for c in infos]
    return infos


def chunk_fixed_window(doc: Document, max_chars: int = 800) -> list[ChunkInfo]:
    """固定窗口切块（PDF 等无标题结构语料）。"""
    text = doc.text.strip()
    if not text:
        doc.chunks = []
        return []

    pieces = _pack_paragraphs(text, max_chars) if len(text) > max_chars else [text]
    infos = [
        ChunkInfo(text=piece, parent_text=piece, chunk_index=i)
        for i, piece in enumerate(pieces)
    ]
    doc.chunks = [c.text for c in infos]
    return infos


def chunk_document(doc: Document, profile_max_chars: int, strategy: str) -> list[ChunkInfo]:
    """按 Profile 选择切块策略。"""
    if strategy == "fixed_window":
        return chunk_fixed_window(doc, max_chars=profile_max_chars)
    return chunk_by_heading_info(doc, max_chars=profile_max_chars)


def chunk_by_heading(doc: Document, max_chars: int = 1200) -> list[str]:
    """兼容旧接口：仅返回 chunk 文本列表。"""
    return [c.text for c in chunk_by_heading_info(doc, max_chars=max_chars)]
