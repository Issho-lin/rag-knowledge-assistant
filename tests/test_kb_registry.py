"""知识库注册表单测。"""

from __future__ import annotations

from rag_assistant.ingest.loaders import Document
from rag_assistant.kb import get_kb, get_kb_by_tool_name, list_kbs, list_vector_kbs, resolve_kb_id
from rag_assistant.query.retrieve import merge_retrieval_options


def test_resolve_kb_by_kind():
    md = Document(text="x", source="/a/02-请假.md", metadata={"kind": "markdown", "corpus": "internal"})
    csv = Document(text="x", source="/a/员工.csv", metadata={"kind": "csv", "corpus": "internal"})
    pdf = Document(text="x", source="/a/handbook.pdf", metadata={"kind": "pdf", "corpus": "kb_pdf"})
    graph = Document(text="x", source="/a/org.md", metadata={"kind": "markdown", "corpus": "kb_graph"})
    assert resolve_kb_id(md) == "policies"
    assert resolve_kb_id(csv) == "tabular"
    assert resolve_kb_id(pdf) == "pdf"
    assert resolve_kb_id(graph) == "relations"


def test_registry_has_three_kbs():
    ids = {kb.id for kb in list_kbs()}
    assert ids == {"policies", "tabular", "pdf", "relations"}
    assert {kb.id for kb in list_vector_kbs()} == {"policies", "tabular", "pdf"}


def test_merge_options_physical_kb_no_metadata_filter():
    """物理分库：检索直连 KB 索引，不再用 metadata_filter 限定 kb。"""
    opts = merge_retrieval_options(None, "tabular")
    assert "kb" not in opts.metadata_filter
    assert get_kb("tabular").profile.retrieval.expand_parent is False


def test_policies_profile_expands_parent():
    assert get_kb("policies").profile.retrieval.expand_parent is True


def test_get_kb_by_tool_name():
    assert get_kb_by_tool_name("search_pdf_handbook").id == "pdf"
