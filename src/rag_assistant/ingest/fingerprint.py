"""文档指纹：用 doc_id + file_hash 判断增量入库时是否跳过。"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class DocFingerprint:
    doc_id: str
    file_hash: str
    corpus: str = ""


def document_id(source: str) -> str:
    """稳定文档 ID：优先用已存在文件的绝对路径，避免相对/绝对路径各写一份。"""
    path = Path(source)
    key = str(path.expanduser().resolve()) if path.is_file() else source
    digest = hashlib.sha1(key.encode("utf-8")).hexdigest()[:16]
    return f"d_{digest}"


def content_hash(source: str, text: str = "") -> str:
    """文件字节 SHA-256；路径不存在时退回正文哈希（测试夹具）。"""
    path = Path(source)
    if path.is_file():
        hasher = hashlib.sha256()
        with path.open("rb") as fh:
            for block in iter(lambda: fh.read(65536), b""):
                hasher.update(block)
        return hasher.hexdigest()
    return hashlib.sha256(text.encode("utf-8")).hexdigest()
