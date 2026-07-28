"""LangChain Loader 对照实现（学习用）。

与 loaders.py 对外接口一致：
  load_markdown / load_html / load_csv / load_corpus
  → 返回本项目的 Document（不是 LangChain 的 Document）

依赖（可选 extra）：
  uv pip install -e ".[lc]"

切换方式（二选一）：
  1. 在 pipeline.py 里把
       from .ingest.loaders import load_corpus
     改成
       from .ingest.loaders_lc import load_corpus
  2. 或在调用处显式 import loaders_lc

说明：
  - MD：TextLoader 读入后，复用 loaders._clean_markdown 做噪音清洗
  - HTML：BSHTMLLoader（BeautifulSoup 抽文本）；效果与 trafilatura 不同
  - CSV：CSVLoader 默认一行一个 LC Document，这里合并成「一个文件一个 Document」
    以保持与现有 chunk / ingest 流程兼容
"""

from __future__ import annotations

from pathlib import Path

from langchain_community.document_loaders import BSHTMLLoader, CSVLoader, TextLoader

from ..logging import get_logger
from .loaders import Document, _clean_markdown

log = get_logger(__name__)


def _to_our_document(
    lc_docs: list,
    path: Path,
    *,
    kind: str,
) -> Document:
    """把 LangChain Document 列表收成我们的单文件 Document。"""
    text = "\n\n".join(d.page_content for d in lc_docs if d.page_content).strip()
    meta = {"kind": kind, "name": path.stem, "loader": "langchain"}
    # 保留 LC 侧常见元数据（若有）
    if lc_docs and getattr(lc_docs[0], "metadata", None):
        for k, v in lc_docs[0].metadata.items():
            if k not in meta and v is not None:
                meta[k] = v
    return Document(text=text, source=str(path), metadata=meta)


def load_markdown(path: Path) -> Document:
    """用 LangChain TextLoader 读 Markdown，再做与自研版相同的清洗。"""
    path = Path(path)
    loader = TextLoader(str(path), encoding="utf-8", autodetect_encoding=True)
    doc = _to_our_document(loader.load(), path, kind="markdown")
    doc.text = _clean_markdown(doc.text)
    return doc


def load_html(path: Path) -> Document:
    """用 LangChain BSHTMLLoader（BeautifulSoup）抽 HTML 文本。"""
    path = Path(path)
    loader = BSHTMLLoader(str(path), open_encoding="utf-8")
    return _to_our_document(loader.load(), path, kind="html")


def load_csv(path: Path) -> Document:
    """用 LangChain CSVLoader；多行合并为一个 Document。"""
    path = Path(path)
    loader = CSVLoader(
        file_path=str(path),
        encoding="utf-8-sig",
        csv_args={"delimiter": ","},
    )
    lc_docs = loader.load()
    # CSVLoader 通常一行一条；前面加文件标题，便于检索时知道来源表
    if lc_docs:
        header = f"# {path.stem}"
        body = "\n\n".join(d.page_content for d in lc_docs if d.page_content)
        text = f"{header}\n\n{body}".strip()
    else:
        text = ""
    return Document(
        text=text,
        source=str(path),
        metadata={"kind": "csv", "name": path.stem, "loader": "langchain"},
    )


def load_corpus(root: Path) -> list[Document]:
    """加载语料根目录下 markdown/、html/、csv/（接口与 loaders.load_corpus 相同）。"""
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

    log.info("ingest.load_corpus_lc", root=str(root), count=len(docs))
    return docs
