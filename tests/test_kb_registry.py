"""知识库注册表单测。"""

from __future__ import annotations

from rag_assistant.ingest.loaders import Document
from rag_assistant.kb import get_kb, list_kbs, resolve_kb_id
from rag_assistant.pipeline import _merge_retrieval_options


def test_resolve_kb_by_kind():
    md = Document(text="x", source="/a/02-请假.md", metadata={"kind": "markdown", "corpus": "internal"})
    csv = Document(text="x", source="/a/员工.csv", metadata={"kind": "csv", "corpus": "internal"})
    pdf = Document(text="x", source="/a/handbook.pdf", metadata={"kind": "pdf", "corpus": "kb_pdf"})
    assert resolve_kb_id(md) == "policies"
    assert resolve_kb_id(csv) == "tabular"
    assert resolve_kb_id(pdf) == "pdf"


def test_registry_has_three_kbs():
    ids = {kb.id for kb in list_kbs()}
    assert ids == {"policies", "tabular", "pdf"}


def test_merge_options_adds_kb_filter():
    opts = _merge_retrieval_options(None, "tabular")
    assert opts.metadata_filter["kb"] == "tabular"
    assert get_kb("tabular").profile.retrieval.expand_parent is False


def test_policies_profile_expands_parent():
    assert get_kb("policies").profile.retrieval.expand_parent is True
