"""入库流水线：语料发现 → 切块 → 按 KB 物理分库写入向量库 + BM25。"""

from __future__ import annotations

import hashlib
import shutil
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path

from ..core.config import get_settings
from ..core.logging import configure_logging, get_logger
from ..core.paths import BM25_PATH, UNIFIED_CHROMA, bm25_path_for_kb, chroma_path_for_kb
from ..kb import get_kb, list_vector_kbs, resolve_kb_id
from ..retrieval.bm25_store import create_bm25_store
from ..retrieval.opensearch_bm25 import OpenSearchBM25Store
from ..retrieval.metadata import build_chunk_metadata
from ..retrieval.vector_store import create_vector_store
from .chunking import chunk_document
from .fingerprint import content_hash, document_id
from .loaders import Document, load_corpus

log = get_logger(__name__)


def _chunk_id(source: str, text: str, index: int) -> str:
    """生成 chunk 的唯一标识符。保持chroma和bm25的chunk id一致。"""
    digest = hashlib.sha1(f"{source}\0{index}\0{text}".encode("utf-8")).hexdigest()[:16]
    return f"c_{digest}"


def discover_corpus_roots(parent: Path | None = None) -> list[Path]:
    """发现父目录下所有合法语料包（子目录内存在 markdown/html/csv/pdf/images）。"""
    parent = parent or get_settings().corpus_dir
    if not parent.is_dir():
        return []

    roots: list[Path] = []
    for child in sorted(parent.iterdir()):
        if not child.is_dir() or child.name.startswith("."):
            continue
        if any(
            (child / sub).is_dir()
            for sub in ("markdown", "html", "csv", "pdf", "images")
        ):
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
    kb_ids = {kb.id for kb in list_vector_kbs()}
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
        names = [kb.id for kb in list_vector_kbs()] + _legacy_storage_names()
        for name in names:
            OpenSearchBM25Store(index_name=name).delete_index()
        return
    if BM25_PATH.is_file():
        BM25_PATH.unlink()
        log.info("ingest.reset_bm25_pkl", path=str(BM25_PATH))
    for kb in list_vector_kbs():
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
        names = [kb.id for kb in list_vector_kbs()] + _legacy_storage_names()
        for name in names:
            if client.collection_exists(name):
                client.delete_collection(name)
                log.info("ingest.reset_qdrant", collection=name)
        return
    if UNIFIED_CHROMA.exists():
        shutil.rmtree(UNIFIED_CHROMA)
        log.info("ingest.reset_chroma", path=str(UNIFIED_CHROMA))
    for kb in list_vector_kbs():
        path = chroma_path_for_kb(kb.id)
        if path.exists():
            shutil.rmtree(path)
            log.info("ingest.reset_chroma", path=str(path), kb=kb.id)


@dataclass
class _LiveDoc:
    doc: Document
    doc_id: str
    file_hash: str
    corpus: str
    kb_id: str


def _chunk_live_doc(live: _LiveDoc) -> dict[str, list]:
    d = live.doc
    kind = str(d.metadata.get("kind", ""))
    profile = get_kb(live.kb_id).profile
    chunk_infos = chunk_document(d, profile.max_chars, profile.chunk_strategy)
    batch: dict[str, list] = {"ids": [], "chunks": [], "sources": [], "metadatas": []}
    for i, info in enumerate(chunk_infos):
        batch["ids"].append(_chunk_id(d.source, info.text, i))
        batch["chunks"].append(info.text)
        batch["sources"].append(d.source)
        batch["metadatas"].append(
            build_chunk_metadata(
                source=d.source,
                kind=kind,
                corpus=live.corpus,
                kb=live.kb_id,
                parent_text=info.parent_text,
                chunk_index=info.chunk_index,
                doc_id=live.doc_id,
                file_hash=live.file_hash,
                media_path=str(d.metadata.get("media_path") or ""),
            )
        )
    return batch


def _sync_kb(
    kb_id: str,
    live_docs: dict[str, _LiveDoc],
    *,
    only: str | None,
) -> tuple[int, int, int, int]:
    """增量同步一个 KB。返回 (chunks_written, skipped_docs, upserted_docs, deleted_docs)。"""
    store = create_vector_store(kb_id=kb_id)
    bm25 = create_bm25_store(kb_id=kb_id)
    store.purge_unfingerprinted()
    bm25.purge_unfingerprinted()

    indexed = store.list_doc_fingerprints()
    if only is not None:
        # only是指定的语料包名称
        indexed_ids = {doc_id for doc_id, (_h, corpus) in indexed.items() if corpus == only}
    else:
        indexed_ids = set(indexed)

    current_ids = set(live_docs)
    unchanged = {
        doc_id
        for doc_id, live in live_docs.items()
        if indexed.get(doc_id, ("", ""))[0] == live.file_hash and live.file_hash
    }
    to_upsert = current_ids - unchanged
    to_delete = indexed_ids - current_ids
    remove_ids = list(to_delete | to_upsert)
    if remove_ids:
        store.delete_by_doc_ids(remove_ids)
        bm25.delete_by_doc_ids(remove_ids)

    written = 0
    if to_upsert:
        batch: dict[str, list] = {"ids": [], "chunks": [], "sources": [], "metadatas": []}
        for doc_id in sorted(to_upsert):
            part = _chunk_live_doc(live_docs[doc_id])
            for key in batch:
                batch[key].extend(part[key])
        if batch["chunks"]:
            written = store.add(
                batch["chunks"],
                batch["sources"],
                ids=batch["ids"],
                metadatas=batch["metadatas"],
            )
            bm25.upsert(
                batch["ids"],
                batch["chunks"],
                batch["sources"],
                metadatas=batch["metadatas"],
            )

    log.info(
        "ingest.kb_sync",
        kb=kb_id,
        skipped=len(unchanged),
        upserted=len(to_upsert),
        deleted=len(to_delete),
        chunks=written,
        vector_count=store.count(),
        bm25_count=bm25.count(),
    )
    return written, len(unchanged), len(to_upsert), len(to_delete)


def ingest(*, reset: bool = False, only: str | None = None) -> int:
    """增量入库：未改文件跳过 embedding；``--reset`` 先清空再全量写入。"""
    configure_logging()
    docs = load_all_documents(only=only)
    if reset:
        _reset_vector_store()
        _reset_bm25_index()

    if not docs and only is None:
        log.error("ingest.empty", parent=str(get_settings().corpus_dir))
        print("未找到任何语料。请在 data/corpus/<名称>/{markdown,html,csv,pdf,images}/ 下放置文件。")
        return 0

    live_by_kb: dict[str, dict[str, _LiveDoc]] = defaultdict(dict)
    for d in docs:
        corpus_name = str(d.metadata.get("corpus", "?"))
        kb_id = resolve_kb_id(d)
        live = _LiveDoc(
            doc=d,
            doc_id=document_id(d.source),
            file_hash=content_hash(d.source, d.text),
            corpus=corpus_name,
            kb_id=kb_id,
        )
        live_by_kb[kb_id][live.doc_id] = live

    total = 0
    skipped = upserted = deleted = 0
    kb_counts: dict[str, int] = {}
    for kb in list_vector_kbs():
        written, skip_n, upsert_n, delete_n = _sync_kb(
            kb.id,
            live_by_kb.get(kb.id, {}),
            only=only,
        )
        kb_counts[kb.id] = written
        total += written
        skipped += skip_n
        upserted += upsert_n
        deleted += delete_n

    backend = get_settings().vector_backend
    bm25_backend = get_settings().bm25_backend
    bundles = sorted({d.metadata.get("corpus", "?") for d in docs}) or ([only] if only else [])
    log.info(
        "ingest.done",
        reset=reset,
        bundles=bundles,
        docs=len(docs),
        chunks=total,
        skipped_docs=skipped,
        upserted_docs=upserted,
        deleted_docs=deleted,
        kb_counts=kb_counts,
        vector_backend=backend,
        bm25_backend=bm25_backend,
    )
    mode = "全量重建" if reset else "增量入库"
    print(f"\n{mode}：写入 {total} 个 chunk，跳过 {skipped} 篇，更新 {upserted} 篇，删除 {deleted} 篇")
    if bundles:
        print(f"来源语料包: {', '.join(str(b) for b in bundles)}")
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
        print("BM25 索引: data/chroma/<kb_id>/bm25.pkl")
    return total


def upsert_documents(docs: list[Document], *, kb_id: str) -> dict[str, int]:
    """只写入给定文档，不把库内其它文档当成缺失删除。"""
    kb = get_kb(kb_id)
    if kb.backend != "vector":
        raise ValueError(f"kb={kb_id} 不是向量库，不能走文档 upsert")
    if not docs:
        return {"chunks": 0, "docs": 0}

    corpus_name = kb.corpus_names[0] if kb.corpus_names else "uploads"
    live_docs: dict[str, _LiveDoc] = {}
    for d in docs:
        d.metadata["corpus"] = corpus_name
        d.metadata["kb"] = kb_id
        live = _LiveDoc(
            doc=d,
            doc_id=document_id(d.source),
            file_hash=content_hash(d.source, d.text),
            corpus=corpus_name,
            kb_id=kb_id,
        )
        live_docs[live.doc_id] = live

    store = create_vector_store(kb_id=kb_id)
    bm25 = create_bm25_store(kb_id=kb_id)
    remove_ids = list(live_docs)
    store.delete_by_doc_ids(remove_ids)
    bm25.delete_by_doc_ids(remove_ids)

    batch: dict[str, list] = {"ids": [], "chunks": [], "sources": [], "metadatas": []}
    for doc_id in sorted(live_docs):
        part = _chunk_live_doc(live_docs[doc_id])
        for key in batch:
            batch[key].extend(part[key])
    written = 0
    if batch["chunks"]:
        written = store.add(
            batch["chunks"],
            batch["sources"],
            ids=batch["ids"],
            metadatas=batch["metadatas"],
        )
        bm25.upsert(
            batch["ids"],
            batch["chunks"],
            batch["sources"],
            metadatas=batch["metadatas"],
        )
    log.info("ingest.upsert", kb=kb_id, docs=len(live_docs), chunks=written)
    return {"chunks": written, "docs": len(live_docs)}
