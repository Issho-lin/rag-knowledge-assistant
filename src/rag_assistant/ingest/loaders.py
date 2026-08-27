"""文档加载器：多类型文件 → 内部 Document。

每种格式负责把正文抽干净，并保留 source 路径供回答引用。
当前支持：Markdown、HTML、CSV、PDF、图像（VLM caption）。
"""

from __future__ import annotations

import csv
import re
from dataclasses import dataclass, field
from pathlib import Path

import trafilatura

from ..core.logging import get_logger

log = get_logger(__name__)


@dataclass
class Document:
    """一次入库的文本单元，带溯源信息。

    `chunks` 由 chunking 稍后填充；加载器只负责 text + source。
    """

    text: str
    source: str
    metadata: dict = field(default_factory=dict)
    chunks: list[str] = field(default_factory=list)


# --- markdown 清洗 ---------------------------------------------------------

_FONT_SPAN = re.compile(r"<font[^>]*>|</font>", re.IGNORECASE)
_SPAN_TAG = re.compile(r"<span[^>]*>|</span>", re.IGNORECASE)
_HTML_DIV_BLOCK = re.compile(r"<div[^>]*>.*?</div>", re.IGNORECASE | re.DOTALL)
_INCLUDE_MACRO = re.compile(r"\{\*[^}]*\*\}")
_BLANK_RUN = re.compile(r"\n{3,}")


def _clean_markdown(raw: str) -> str:
    text = _INCLUDE_MACRO.sub("", raw)
    text = _HTML_DIV_BLOCK.sub("", text)
    text = _FONT_SPAN.sub("", text)
    text = _SPAN_TAG.sub("", text)
    text = _BLANK_RUN.sub("\n\n", text)
    return text.strip()


def load_markdown(path: Path) -> Document:
    raw = path.read_text(encoding="utf-8", errors="ignore")
    return Document(
        text=_clean_markdown(raw),
        source=str(path),
        metadata={"kind": "markdown", "name": path.stem},
    )


def load_html(path: Path) -> Document:
    """用 trafilatura 抽正文，去掉导航/页脚等噪音。"""
    raw = path.read_text(encoding="utf-8", errors="ignore")
    text = trafilatura.extract(raw, include_comments=False, include_tables=True) or ""
    if not text.strip():
        # 抽取失败时退回去标签的纯文本，避免整页丢掉
        text = re.sub(r"<script[\s\S]*?</script>", " ", raw, flags=re.I)
        text = re.sub(r"<style[\s\S]*?</style>", " ", text, flags=re.I)
        text = re.sub(r"<[^>]+>", " ", text)
        text = _BLANK_RUN.sub("\n\n", text)
    return Document(
        text=text.strip(),
        source=str(path),
        metadata={"kind": "html", "name": path.stem},
    )


def load_csv(path: Path) -> Document:
    """CSV 转成「表头 + 逐行」文本，便于检索工号/姓名/部门等字段。"""
    lines: list[str] = [f"# {path.stem}", ""]
    with path.open(encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        if not reader.fieldnames:
            return Document(text="", source=str(path), metadata={"kind": "csv", "name": path.stem})
        lines.append("字段：" + "、".join(reader.fieldnames))
        lines.append("")
        for row in reader:
            parts = [f"{k}={v}" for k, v in row.items() if v is not None and str(v).strip()]
            if parts:
                lines.append("；".join(parts))
    return Document(
        text="\n".join(lines).strip(),
        source=str(path),
        metadata={"kind": "csv", "name": path.stem},
    )


def load_pdf(path: Path) -> Document:
    """PDF 抽文本（pypdf）；扫描件需 OCR，本期不覆盖。"""
    from pypdf import PdfReader

    reader = PdfReader(str(path))
    pages = [(p.extract_text() or "").strip() for p in reader.pages]
    text = "\n\n".join(p for p in pages if p)
    return Document(
        text=text,
        source=str(path),
        metadata={"kind": "pdf", "name": path.stem},
    )


def load_image(path: Path) -> Document:
    """图像为事实源：VLM 自动 caption 后入库；source 指向图像路径。"""
    from .vision_caption import caption_image

    caption = caption_image(path)
    return Document(
        text=caption,
        source=str(path),
        metadata={
            "kind": "image",
            "name": path.stem,
            "media_path": str(path),
            "media_type": path.suffix.lower().lstrip(".") or "image",
        },
    )


def load_corpus(root: Path) -> list[Document]:
    """加载语料根目录下 markdown/、html/、csv/、pdf/、images/ 中的全部文件。"""
    root = Path(root)
    if not root.is_dir():
        raise FileNotFoundError(f"语料目录不存在: {root}")

    docs: list[Document] = []
    md_dir = root / "markdown"
    if md_dir.is_dir():
        for path in sorted(md_dir.rglob("*.md")):
            docs.append(load_markdown(path))

    html_dir = root / "html"
    if html_dir.is_dir():
        for path in sorted(html_dir.rglob("*.html")):
            docs.append(load_html(path))

    csv_dir = root / "csv"
    if csv_dir.is_dir():
        for path in sorted(csv_dir.rglob("*.csv")):
            docs.append(load_csv(path))

    pdf_dir = root / "pdf"
    if pdf_dir.is_dir():
        for path in sorted(pdf_dir.rglob("*.pdf")):
            docs.append(load_pdf(path))

    images_dir = root / "images"
    if images_dir.is_dir():
        from .vision_caption import is_image_path

        for path in sorted(images_dir.rglob("*")):
            if path.is_file() and is_image_path(path):
                docs.append(load_image(path))

    log.info("ingest.load_corpus", root=str(root), count=len(docs))
    return docs
