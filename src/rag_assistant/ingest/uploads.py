"""控制台：按知识库校验格式，并把上传文件落到对应语料目录。"""

from __future__ import annotations

import re
from pathlib import Path

from ..core.config import get_settings
from ..kb import get_kb

# kb_id -> {suffix: 语料子目录名}
_KB_FOLDERS: dict[str, dict[str, str]] = {
    "policies": {".md": "markdown", ".html": "html", ".htm": "html"},
    "tabular": {".csv": "csv"},
    "pdf": {".pdf": "pdf"},
    "multimodal": {".png": "images", ".jpg": "images", ".jpeg": "images", ".webp": "images"},
    "relations": {".md": "markdown"},
}

_UNSAFE = re.compile(r"[^A-Za-z0-9._\-\u4e00-\u9fff]+")


class UploadRejected(ValueError):
    """格式与所选知识库不匹配。"""


def allowed_suffixes(kb_id: str) -> tuple[str, ...]:
    return tuple(sorted(_KB_FOLDERS[get_kb(kb_id).id]))


def folder_for(kb_id: str, suffix: str) -> str:
    kb = get_kb(kb_id)
    mapping = _KB_FOLDERS[kb.id]
    folder = mapping.get(suffix.lower())
    if folder is None:
        allowed = "、".join(sorted(mapping))
        raise UploadRejected(
            f"知识库「{kb.name}」只接受 {allowed}，收到 {suffix or '无扩展名'}。"
            " 请换库或换文件，不要把 PDF/表格/图片丢进制度库。"
        )
    return folder


def corpus_name_for(kb_id: str) -> str:
    kb = get_kb(kb_id)
    if not kb.corpus_names:
        return "uploads"
    return kb.corpus_names[0]


def safe_filename(name: str) -> str:
    raw = Path(name).name
    cleaned = _UNSAFE.sub("_", raw).strip("._") or "upload"
    return cleaned[:180]


def destination_path(kb_id: str, filename: str) -> Path:
    suffix = Path(filename).suffix.lower()
    folder = folder_for(kb_id, suffix)
    corpus = corpus_name_for(kb_id)
    dest_dir = get_settings().corpus_dir / corpus / folder
    dest_dir.mkdir(parents=True, exist_ok=True)
    return dest_dir / safe_filename(filename)
