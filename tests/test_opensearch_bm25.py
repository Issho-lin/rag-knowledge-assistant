"""OpenSearch BM25 单元测试（mock 客户端，不依赖 Docker）。"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from rag_assistant.retrieval.bm25 import BM25Store
from rag_assistant.retrieval.bm25_store import create_bm25_store
from rag_assistant.retrieval.opensearch_bm25 import _filter_clauses, OpenSearchBM25Store


def test_filter_clauses_exact_match():
    clauses = _filter_clauses({"kb": "policies", "corpus": "internal"})
    assert clauses == [
        {"term": {"kb": "policies"}},
        {"term": {"corpus": "internal"}},
    ]


def test_create_bm25_store_pkl(monkeypatch, tmp_path):
    monkeypatch.setenv("BM25_BACKEND", "pkl")
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    monkeypatch.setenv("OPENAI_BASE_URL", "http://localhost:9999/v1")
    from rag_assistant.core import config as config_module

    monkeypatch.setattr(config_module, "_settings", None)

    path = tmp_path / "bm25.pkl"
    store = create_bm25_store(path)
    assert isinstance(store, BM25Store)
    n = store.rebuild(
        ["a"],
        ["ITSM ticket XY003"],
        ["doc.md"],
        metadatas=[{"source": "doc.md", "kb": "policies", "corpus": "internal", "kind": "markdown"}],
    )
    assert n == 1
    assert store.count() == 1


@patch("rag_assistant.retrieval.opensearch_bm25.bulk")
@patch("rag_assistant.retrieval.opensearch_bm25._build_client")
def test_opensearch_rebuild_and_query(mock_build, mock_bulk, monkeypatch):
    monkeypatch.setenv("BM25_BACKEND", "opensearch")
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    monkeypatch.setenv("OPENAI_BASE_URL", "http://localhost:9999/v1")
    from rag_assistant.core import config as config_module

    monkeypatch.setattr(config_module, "_settings", None)

    client = MagicMock()
    mock_build.return_value = client
    mock_bulk.return_value = (1, [])
    client.indices.exists.side_effect = [False, False, True]
    client.count.return_value = {"count": 1}
    client.search.return_value = {
        "hits": {
            "hits": [
                {
                    "_id": "c_abc",
                    "_score": 2.5,
                    "_source": {
                        "chunk_id": "c_abc",
                        "text": "年假五天",
                        "source": "hr.md",
                        "kb": "policies",
                        "corpus": "internal",
                        "kind": "markdown",
                        "domain": "hr",
                        "parent_text": "",
                        "chunk_index": 0,
                    },
                }
            ]
        }
    }

    store = OpenSearchBM25Store()
    n = store.rebuild(
        ["c_abc"],
        ["年假五天"],
        ["hr.md"],
        metadatas=[
            {
                "source": "hr.md",
                "kb": "policies",
                "corpus": "internal",
                "kind": "markdown",
                "domain": "hr",
                "parent_text": "",
                "chunk_index": 0,
            }
        ],
    )
    assert n == 1
    mock_bulk.assert_called_once()
    client.indices.create.assert_called()

    hits = store.query("年假", k=3, metadata_filter={"kb": "policies"})
    assert len(hits) == 1
    assert hits[0]["id"] == "c_abc"
    assert hits[0]["score"] == 2.5

    search_body = client.search.call_args[1]["body"]
    assert search_body["query"]["bool"]["filter"] == [{"term": {"kb": "policies"}}]
