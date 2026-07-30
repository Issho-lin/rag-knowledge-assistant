"""检索链路单元测试（元数据 / 过滤 / 父文档 / 子查询解析；不依赖 LLM / 向量库）。"""

from __future__ import annotations

from rag_assistant.ingest.chunking import chunk_by_heading_info
from rag_assistant.ingest.loaders import Document
from rag_assistant.query_decompose import _parse_subqueries
from rag_assistant.retrieval.context import expand_parent_context
from rag_assistant.retrieval.filters import filter_chunks
from rag_assistant.retrieval.metadata import infer_domain


def test_infer_domain_hr_and_directory():
    assert infer_domain("/data/02-请假与考勤制度.md", kind="markdown") == "hr"
    assert infer_domain("/data/员工通讯录-摘录.csv", kind="csv") == "directory"


def test_chunk_parent_text_on_long_section():
    long_body = "段落内容。\n\n" * 80
    doc = Document(
        text=f"# 标题\n\n{long_body}",
        source="test.md",
        metadata={"kind": "markdown"},
    )
    infos = chunk_by_heading_info(doc, max_chars=200)
    assert len(infos) > 1
    assert all(info.parent_text.startswith("# 标题") for info in infos)
    assert any(info.text != info.parent_text for info in infos)


def test_filter_by_metadata_and_score():
    chunks = [
        {"id": "a", "text": "t", "source": "hr/a.md", "domain": "hr", "score": 0.9},
        {"id": "b", "text": "t", "source": "it/b.md", "domain": "it_sec", "score": 0.9},
        {"id": "c", "text": "t", "source": "hr/c.md", "domain": "hr", "score": 0.05},
    ]
    filtered = filter_chunks(
        chunks,
        min_score=0.08,
        metadata_filter={"domain": "hr"},
        rerank_was_used=True,
    )
    assert len(filtered) == 1
    assert filtered[0]["id"] == "a"


def test_expand_parent_dedupes():
    parent = "# FAQ\n\n会议室与打印机说明……"
    chunks = [
        {"id": "1", "text": "会议室……", "parent_text": parent, "source": "faq.md"},
        {"id": "2", "text": "打印机……", "parent_text": parent, "source": "faq.md"},
    ]
    out = expand_parent_context(chunks)
    assert len(out) == 1
    assert out[0]["text"] == parent
    assert out[0]["expanded_from_child"] is True


def test_parse_subqueries_json():
    subs = _parse_subqueries('["会议室怎么订？", "打印机怎么用？"]', "fallback")
    assert len(subs) == 2
    assert "会议室" in subs[0]
