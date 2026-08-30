"""控制台：格式校验、切片预览、upsert 不误删。"""

from __future__ import annotations

from unittest.mock import patch

import pytest

from rag_assistant.core import config as config_module
from rag_assistant.ingest.loaders import load_file
from rag_assistant.ingest.preview import preview_path
from rag_assistant.ingest.run import upsert_documents
from rag_assistant.ingest.uploads import UploadRejected, folder_for
from rag_assistant.retrieval.bm25_store import create_bm25_store
from rag_assistant.retrieval.vector_store import create_vector_store


def _env(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    monkeypatch.setenv("OPENAI_BASE_URL", "http://localhost:9999/v1")
    monkeypatch.setenv("VECTOR_BACKEND", "chroma")
    monkeypatch.setenv("BM25_BACKEND", "pkl")
    monkeypatch.setenv("CORPUS_DIR", str(tmp_path / "data" / "corpus"))
    monkeypatch.setattr(config_module, "_settings", None)


def test_folder_for_rejects_pdf_in_policies():
    with pytest.raises(UploadRejected, match="只接受"):
        folder_for("policies", ".pdf")


def test_folder_for_accepts_csv_in_tabular():
    assert folder_for("tabular", ".csv") == "csv"


def test_preview_heading_chunks(tmp_path):
    path = tmp_path / "leave.md"
    path.write_text("# 年假\n\n正式员工 10 天。\n\n# 病假\n\n每年 5 天。\n")
    out = preview_path(path, kb_id="policies")
    assert out["strategy"] == "heading"
    assert len(out["chunks"]) >= 2
    assert any("年假" in c["text"] for c in out["chunks"])


def test_preview_pdf_profile_uses_fixed_window(tmp_path):
    path = tmp_path / "note.md"
    path.write_text("没有标题的长段落。" * 40)
    out = preview_path(path, kb_id="pdf")
    assert out["strategy"] == "fixed_window"
    assert out["max_chars"] == 800


@patch("rag_assistant.retrieval.chroma_store.embed_documents")
def test_upsert_does_not_delete_other_docs(mock_embed, monkeypatch, tmp_path):
    mock_embed.side_effect = lambda texts: [[0.1, 0.2, 0.3, 0.4] for _ in texts]
    _env(monkeypatch, tmp_path)
    md_dir = tmp_path / "data" / "corpus" / "internal" / "markdown"
    md_dir.mkdir(parents=True)
    keep = md_dir / "keep.md"
    keep.write_text("# 保留\n\n这篇应还在。\n")
    extra = md_dir / "extra.md"
    extra.write_text("# 新增\n\n这篇后写入。\n")

    upsert_documents([load_file(keep)], kb_id="policies")
    n1 = create_vector_store(kb_id="policies").count()
    assert n1 >= 1

    upsert_documents([load_file(extra)], kb_id="policies")
    bm25 = create_bm25_store(kb_id="policies")
    texts = " ".join(bm25._docs)
    assert "这篇应还在" in texts
    assert "这篇后写入" in texts
    assert create_vector_store(kb_id="policies").count() > n1


def test_api_preview_rejects_wrong_format(monkeypatch, tmp_path):
    _env(monkeypatch, tmp_path)
    from fastapi.testclient import TestClient

    from rag_assistant.api.app import create_app

    client = TestClient(create_app())
    resp = client.post(
        "/api/preview",
        data={"kb_id": "policies"},
        files=[("files", ("a.pdf", b"%PDF-1.4", "application/pdf"))],
    )
    assert resp.status_code == 400
    assert "只接受" in str(resp.json()["detail"])


def test_api_serves_console(monkeypatch, tmp_path):
    _env(monkeypatch, tmp_path)
    from fastapi.testclient import TestClient

    from rag_assistant.api.app import create_app

    client = TestClient(create_app())
    home = client.get("/")
    assert home.status_code == 200
    assert "星云知识控制台" in home.text
    css = client.get("/static/styles.css")
    assert css.status_code == 200
    kbs = client.get("/api/kbs")
    assert kbs.status_code == 200
    ids = {item["id"] for item in kbs.json()["items"]}
    assert {"policies", "pdf", "multimodal"} <= ids

