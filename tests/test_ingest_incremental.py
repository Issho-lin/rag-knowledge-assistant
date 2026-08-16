"""增量入库：doc_id + file_hash 跳过未改文件、upsert 变更、删除失效文档。"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from rag_assistant.core import config as config_module
from rag_assistant.ingest.fingerprint import content_hash, document_id
from rag_assistant.ingest.run import ingest
from rag_assistant.retrieval.bm25 import BM25Store
from rag_assistant.retrieval.bm25_store import create_bm25_store
from rag_assistant.retrieval.opensearch_bm25 import OpenSearchBM25Store
from rag_assistant.retrieval.vector_store import create_vector_store


def _env(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    monkeypatch.setenv("OPENAI_BASE_URL", "http://localhost:9999/v1")
    monkeypatch.setenv("VECTOR_BACKEND", "chroma")
    monkeypatch.setenv("BM25_BACKEND", "pkl")
    monkeypatch.setenv("CORPUS_DIR", str(tmp_path / "data" / "corpus"))
    monkeypatch.setattr(config_module, "_settings", None)


def test_document_id_stable_for_same_file(tmp_path):
    path = tmp_path / "a.md"
    path.write_text("hello")
    assert document_id(str(path)) == document_id(str(path.resolve()))
    assert document_id(str(path)).startswith("d_")


def test_content_hash_changes_with_bytes(tmp_path):
    path = tmp_path / "a.md"
    path.write_text("v1")
    h1 = content_hash(str(path))
    path.write_text("v2")
    assert content_hash(str(path)) != h1


def test_bm25_upsert_and_delete_by_doc_id(tmp_path):
    store = BM25Store(tmp_path / "bm25.pkl")
    store.upsert(
        ["c1", "c2"],
        ["年假五天", "病假三天"],
        ["a.md", "a.md"],
        metadatas=[
            {"doc_id": "d_a", "file_hash": "h1", "source": "a.md", "kb": "policies"},
            {"doc_id": "d_a", "file_hash": "h1", "source": "a.md", "kb": "policies"},
        ],
    )
    store.upsert(
        ["c3"],
        ["通讯录周凯"],
        ["b.csv"],
        metadatas=[{"doc_id": "d_b", "file_hash": "h2", "source": "b.csv", "kb": "tabular"}],
    )
    assert store.count() == 3
    assert store.delete_by_doc_ids(["d_a"]) == 2
    assert store.count() == 1
    assert store._docs == ["通讯录周凯"]


def test_bm25_purge_unfingerprinted(tmp_path):
    store = BM25Store(tmp_path / "bm25.pkl")
    store.rebuild(
        ["old", "new"],
        ["旧全文索引", "新年假"],
        ["old.md", "new.md"],
        metadatas=[
            {"source": "old.md", "kb": "policies"},
            {"source": "new.md", "kb": "policies", "doc_id": "d_new"},
        ],
    )
    assert store.purge_unfingerprinted() == 1
    assert store.count() == 1
    assert store._ids == ["new"]


@patch("rag_assistant.retrieval.chroma_store.embed_documents")
def test_ingest_skips_unchanged_upserts_and_deletes(mock_embed, monkeypatch, tmp_path):
    mock_embed.side_effect = lambda texts: [[0.1, 0.2, 0.3, 0.4] for _ in texts]
    _env(monkeypatch, tmp_path)

    md_dir = tmp_path / "data" / "corpus" / "internal" / "markdown"
    md_dir.mkdir(parents=True)
    keep = md_dir / "keep.md"
    gone = md_dir / "gone.md"
    keep.write_text("# 年假\n\n正式员工年假五天。\n")
    gone.write_text("# 作废\n\n这篇会被删掉。\n")

    ingest(reset=True)
    first_calls = mock_embed.call_count
    assert first_calls >= 1
    policies = create_vector_store(kb_id="policies")
    bm25 = create_bm25_store(kb_id="policies")
    n_after_first = policies.count()
    assert n_after_first >= 2
    assert bm25.count() == n_after_first

    mock_embed.reset_mock()
    ingest()
    assert mock_embed.call_count == 0
    assert policies.count() == n_after_first

    keep.write_text("# 年假\n\n正式员工年假改为十五天。\n")
    gone.unlink()
    mock_embed.reset_mock()
    ingest()
    assert mock_embed.call_count >= 1
    bm25 = create_bm25_store(kb_id="policies")
    assert any("十五天" in t for t in bm25._docs)
    assert not any("会被删掉" in t for t in bm25._docs)


@patch("rag_assistant.retrieval.opensearch_bm25.bulk")
@patch("rag_assistant.retrieval.opensearch_bm25._build_client")
def test_opensearch_delete_by_doc_ids(mock_build, mock_bulk, monkeypatch):
    monkeypatch.setenv("BM25_BACKEND", "opensearch")
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    monkeypatch.setenv("OPENAI_BASE_URL", "http://localhost:9999/v1")
    monkeypatch.setattr(config_module, "_settings", None)

    client = MagicMock()
    mock_build.return_value = client
    client.indices.exists.return_value = True
    client.delete_by_query.return_value = {"deleted": 2}

    store = OpenSearchBM25Store(index_name="policies")
    assert store.delete_by_doc_ids(["d_a"]) == 2
    body = client.delete_by_query.call_args[1]["body"]
    assert body["query"]["terms"]["doc_id"] == ["d_a"]
