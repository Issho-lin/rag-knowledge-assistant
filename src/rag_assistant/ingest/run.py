"""入库流水线：语料发现 → 切块 → 向量库 + BM25。"""

from __future__ import annotations

import hashlib
import shutil
from pathlib import Path

from ..core.config import get_settings
from ..core.logging import configure_logging, get_logger
from ..core.paths import BM25_PATH, UNIFIED_CHROMA
from ..kb import kb_profile_for_doc, resolve_kb_id
from ..retrieval.bm25_store import create_bm25_store
from ..retrieval.opensearch_bm25 import OpenSearchBM25Store
from ..retrieval.metadata import build_chunk_metadata
from ..retrieval.vector import VectorStore
from .chunking import chunk_document
from .loaders import Document, load_corpus

log = get_logger(__name__)


def _chunk_id(source: str, text: str, index: int) -> str:
    """生成 chunk 的唯一标识符。保持chroma和bm25的chunk id一致。"""
    digest = hashlib.sha1(f"{source}\0{index}\0{text}".encode("utf-8")).hexdigest()[:16]
    return f"c_{digest}"


def discover_corpus_roots(parent: Path | None = None) -> list[Path]:
    """发现父目录下所有合法语料包（子目录内存在 markdown/ 或 html/ 或 csv/）。"""
    parent = parent or get_settings().corpus_dir
    if not parent.is_dir():
        return []

    roots: list[Path] = []
    for child in sorted(parent.iterdir()):
        if not child.is_dir() or child.name.startswith("."):
            continue
        if any((child / sub).is_dir() for sub in ("markdown", "html", "csv", "pdf")):
            roots.append(child)
    return roots


def load_all_documents(only: str | None = None) -> list[Document]:
    """加载全部语料包；only 为目录名时仅加载那一包（运维调试用）。"""
    roots = discover_corpus_roots()
    if only:
        roots = [r for r in roots if r.name == only]
        if not roots:
            raise FileNotFoundError(
                f"未找到语料包 {only!r}。当前可用: {[r.name for r in discover_corpus_roots()]}"
            )

    docs: list[Document] = []
    for root in roots:
        part = load_corpus(root)
        for d in part:
            d.metadata.setdefault("corpus", root.name)
        docs.extend(part)
        log.info("ingest.load_bundle", corpus=root.name, docs=len(part))
    return docs


def _reset_bm25_index() -> None:
    """按后端清空关键词索引。"""
    s = get_settings()
    if s.bm25_backend.lower() == "opensearch":
        OpenSearchBM25Store().delete_index()
        return
    if BM25_PATH.is_file():
        BM25_PATH.unlink()
        log.info("ingest.reset_bm25_pkl", path=str(BM25_PATH))


def _reset_vector_store() -> None:
    """按后端清空向量索引。"""
    s = get_settings()
    if s.vector_backend.lower() == "qdrant":
        from qdrant_client import QdrantClient

        client = QdrantClient(url=s.qdrant_url)
        if client.collection_exists(s.qdrant_collection):
            client.delete_collection(s.qdrant_collection)
            log.info("ingest.reset_qdrant", collection=s.qdrant_collection)
        return
    chroma_path = UNIFIED_CHROMA
    if chroma_path.exists():
        shutil.rmtree(chroma_path)
        log.info("ingest.reset_chroma", path=str(chroma_path))


def ingest(*, reset: bool = False, only: str | None = None) -> int:
    """将知识库全部（或指定包）切块入库：向量库 + BM25。"""
    configure_logging()
    docs = load_all_documents(only=only)
    if not docs:
        log.error("ingest.empty", parent=str(get_settings().corpus_dir))
        print("未找到任何语料。请在 data/corpus/<名称>/{markdown,html,csv}/ 下放置文件。")
        return 0

    chroma_path = UNIFIED_CHROMA
    if reset:
        _reset_vector_store()
        _reset_bm25_index()

    all_ids: list[str] = []
    all_chunks: list[str] = []
    all_sources: list[str] = []
    all_metadatas: list[dict[str, str | int]] = []
    for d in docs:
        corpus_name = str(d.metadata.get("corpus", "?"))
        kind = str(d.metadata.get("kind", ""))
        kb_id = resolve_kb_id(d)
        profile = kb_profile_for_doc(d)
        chunk_infos = chunk_document(d, profile.max_chars, profile.chunk_strategy)
        for i, info in enumerate(chunk_infos):
            all_ids.append(_chunk_id(d.source, info.text, i))
            all_chunks.append(info.text)
            all_sources.append(d.source)
            all_metadatas.append(
                build_chunk_metadata(
                    source=d.source,
                    kind=kind,
                    corpus=corpus_name,
                    kb=kb_id,
                    parent_text=info.parent_text,
                    chunk_index=info.chunk_index,
                )
            )

    if not all_chunks:
        print("切块结果为空，未写入索引。")
        return 0

    store = VectorStore(chroma_path=chroma_path)
    total = store.add(all_chunks, all_sources, ids=all_ids, metadatas=all_metadatas)
    bm25 = create_bm25_store(BM25_PATH)
    bm25.rebuild(all_ids, all_chunks, all_sources, metadatas=all_metadatas)

    backend = get_settings().vector_backend
    bm25_backend = get_settings().bm25_backend
    bundles = sorted({d.metadata.get("corpus", "?") for d in docs})
    log.info(
        "ingest.done",
        bundles=bundles,
        docs=len(docs),
        chunks=total,
        store_count=store.count(),
        bm25_count=bm25.count(),
        vector_backend=backend,
        bm25_backend=bm25_backend,
    )
    print(f"\n已索引 {total} 个 chunk，来源语料包: {', '.join(bundles)}")
    print(
        f"向量库后端: {backend}"
        + (f" ({get_settings().qdrant_url})" if backend == "qdrant" else f" ({chroma_path})")
    )
    if bm25_backend == "opensearch":
        s = get_settings()
        print(f"BM25 索引: opensearch ({s.opensearch_url}, index={s.opensearch_index})")
    else:
        print(f"BM25 索引: {BM25_PATH}")
    return total
