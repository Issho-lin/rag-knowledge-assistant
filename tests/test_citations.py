"""来源引用：解析正文 [N] 与格式化来源块。"""

from rag_assistant.answer import (
    build_citations,
    cited_indices,
    format_answer_with_sources,
    format_sources_block,
)


def test_cited_indices_parses_multiple_refs():
    assert cited_indices("年假 5 天 [1]，审批见 [2] 与 [1]") == {1, 2}


def test_build_citations_marks_cited_and_uncited():
    chunks = [
        {"source": "data/corpus/internal/markdown/02-请假与考勤制度.md", "text": "年假 5 天", "score": 0.98},
        {"source": "data/corpus/internal/markdown/01-员工手册-总则.md", "text": "总则", "score": 0.42},
    ]
    citations = build_citations(chunks, "满 1 年 5 天 [1]")

    assert len(citations) == 2
    assert citations[0].source == "02-请假与考勤制度.md"
    assert citations[0].cited is True
    assert citations[1].cited is False
    assert "年假 5 天" in citations[0].preview


def test_format_sources_block_lists_all_hits():
    chunks = [
        {"source": "a.md", "text": "hello", "score": 0.9},
    ]
    block = format_sources_block(build_citations(chunks, "答 [1]"))

    assert "参考来源：" in block
    assert "[1] a.md" in block
    assert "已引用" in block
    assert "hello" in block


def test_format_answer_with_sources_appends_block():
    chunks = [{"source": "a.md", "text": "x", "score": 1.0}]
    out = format_answer_with_sources("结论 [1]", chunks)

    assert out.startswith("结论 [1]")
    assert "参考来源：" in out
