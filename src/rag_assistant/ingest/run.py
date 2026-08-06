"""入库流水线：语料发现 → 切块 → 按 KB 物理分库写入向量库 + BM25。"""

from __future__ import annotations

import hashlib
import shutil
from collections import defaultdict
from pathlib import Path

from ..core.config import get_settings
from ..core.logging import configure_logging, get_logger
from ..core.paths import BM25_PATH, UNIFIED_CHROMA, bm25_path_for_kb, chroma_path_for_kb
from ..kb import kb_profile_for_doc, list_kbs, resolve_kb_id
from ..retrieval.bm25_store import create_bm25_store
from ..retrieval.opensearch_bm25 import OpenSearchBM25Store
from ..retrieval.metadata import build_chunk_metadata
from ..retrieval.vector_store import create_vector_store
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


def _legacy_storage_names() -> list[str]:
    """逻辑分库遗留的单一 collection / index 名（reset 时删除）。"""
    s = get_settings()
    kb_ids = {kb.id for kb in list_kbs()}
    names: list[str] = []
    if s.qdrant_collection not in kb_ids:
        names.append(s.qdrant_collection)
    if s.opensearch_index not in kb_ids:
        names.append(s.opensearch_index)
    return names


def _reset_bm25_index() -> None:
    """按 KB 清空关键词索引（含遗留统一 index）。"""
    s = get_settings()
    if s.bm25_backend.lower() == "opensearch":
        names = [kb.id for kb in list_kbs()] + _legacy_storage_names()
        for name in names:
            OpenSearchBM25Store(index_name=name).delete_index()
        return
    if BM25_PATH.is_file():
        BM25_PATH.unlink()
        log.info("ingest.reset_bm25_pkl", path=str(BM25_PATH))
    for kb in list_kbs():
        path = bm25_path_for_kb(kb.id)
        if path.is_file():
            path.unlink()
            log.info("ingest.reset_bm25_pkl", path=str(path), kb=kb.id)


def _reset_vector_store() -> None:
    """按 KB 清空向量索引（含遗留统一 collection / chroma 路径）。"""
    s = get_settings()
    if s.vector_backend.lower() == "qdrant":
        from qdrant_client import QdrantClient

        client = QdrantClient(url=s.qdrant_url)
        names = [kb.id for kb in list_kbs()] + _legacy_storage_names()
        for name in names:
            if client.collection_exists(name):
                client.delete_collection(name)
                log.info("ingest.reset_qdrant", collection=name)
        return
    if UNIFIED_CHROMA.exists():
        shutil.rmtree(UNIFIED_CHROMA)
        log.info("ingest.reset_chroma", path=str(UNIFIED_CHROMA))
    for kb in list_kbs():
        path = chroma_path_for_kb(kb.id)
        if path.exists():
            shutil.rmtree(path)
            log.info("ingest.reset_chroma", path=str(path), kb=kb.id)


def ingest(*, reset: bool = False, only: str | None = None) -> int:
    """将知识库全部（或指定包）切块入库：每 KB 独立向量库 + BM25。"""
    configure_logging()
    docs = load_all_documents(only=only)
    if not docs:
        log.error("ingest.empty", parent=str(get_settings().corpus_dir))
        print("未找到任何语料。请在 data/corpus/<名称>/{markdown,html,csv}/ 下放置文件。")
        return 0

    if reset:
        _reset_vector_store()
        _reset_bm25_index()

    by_kb: dict[str, dict[str, list]] = defaultdict(
        lambda: {"ids": [], "chunks": [], "sources": [], "metadatas": []}
    )
    for d in docs:
        corpus_name = str(d.metadata.get("corpus", "?"))
        kind = str(d.metadata.get("kind", ""))
        kb_id = resolve_kb_id(d)
        profile = kb_profile_for_doc(d)
        chunk_infos = chunk_document(d, profile.max_chars, profile.chunk_strategy)
        batch = by_kb[kb_id]
        for i, info in enumerate(chunk_infos):
            batch["ids"].append(_chunk_id(d.source, info.text, i))
            batch["chunks"].append(info.text)
            batch["sources"].append(d.source)
            batch["metadatas"].append(
                build_chunk_metadata(
                    source=d.source,
                    kind=kind,
                    corpus=corpus_name,
                    kb=kb_id,
                    parent_text=info.parent_text,
                    chunk_index=info.chunk_index,
                )
            )

    total = 0
    kb_counts: dict[str, int] = {}
    for kb_id, batch in sorted(by_kb.items()):
        if not batch["chunks"]:
            continue
        store = create_vector_store(kb_id=kb_id)
        n = store.add(
            batch["chunks"],
            batch["sources"],
            ids=batch["ids"],
            metadatas=batch["metadatas"],
        )
        bm25 = create_bm25_store(kb_id=kb_id)
        bm25.rebuild(
            batch["ids"],
            batch["chunks"],
            batch["sources"],
            metadatas=batch["metadatas"],
        )
        kb_counts[kb_id] = n
        total += n
        log.info(
            "ingest.kb_done",
            kb=kb_id,
            chunks=n,
            vector_count=store.count(),
            bm25_count=bm25.count(),
        )

    if total == 0:
        print("切块结果为空，未写入索引。")
        return 0

    backend = get_settings().vector_backend
    bm25_backend = get_settings().bm25_backend
    bundles = sorted({d.metadata.get("corpus", "?") for d in docs})
    log.info(
        "ingest.done",
        bundles=bundles,
        docs=len(docs),
        chunks=total,
        kb_counts=kb_counts,
        vector_backend=backend,
        bm25_backend=bm25_backend,
    )
    print(f"\n已索引 {total} 个 chunk，来源语料包: {', '.join(bundles)}")
    kb_summary = ", ".join(f"{k}={v}" for k, v in sorted(kb_counts.items()))
    print(f"物理分库: {kb_summary}")
    print(
        f"向量库后端: {backend}"
        + (f" ({get_settings().qdrant_url})" if backend == "qdrant" else "")
    )
    if bm25_backend == "opensearch":
        s = get_settings()
        print(f"BM25 索引: opensearch ({s.opensearch_url}, index=<kb_id>)")
    else:
        print(f"BM25 索引: data/chroma/<kb_id>/bm25.pkl")
    return total
