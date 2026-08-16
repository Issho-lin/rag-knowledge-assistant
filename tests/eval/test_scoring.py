"""eval 打分纯函数单测（不调 LLM）。运行：pytest tests/eval/test_scoring.py -q"""

from tests.eval.scoring import score_answer, score_react_tools, score_recall


def test_space_insensitive_keyword():
    item = {"must_contain": ["5 天", "10 天"], "expect_refuse": False}
    assert score_answer("满1年5天、10天", item)["passed"] is True


def test_synonym_or_group():
    item = {
        "must_contain": ["个人网盘", ["禁止", "不得", "不能"]],
        "expect_refuse": False,
    }
    assert score_answer("不得将数据发到个人网盘", item)["passed"] is True
    assert score_answer("禁止将数据发到个人网盘", item)["passed"] is True


def test_recall_hit_and_miss():
    chunks = [
        {"source": "data/corpus/internal/markdown/09-发布与变更窗口.md", "text": "x"},
    ]
    hit = score_recall(chunks, {"expected_sources": ["09-发布与变更窗口.md"]})
    assert hit is not None and hit["recall_hit"] is True

    miss = score_recall(chunks, {"expected_sources": ["员工通讯录-摘录.csv"]})
    assert miss is not None and miss["recall_hit"] is False


def test_react_tools_single_and_multi():
    single = score_react_tools("search_tabular", {"expected_tool": "search_tabular"})
    assert single is not None and single["tools_hit"] is True

    multi = score_react_tools(
        "search_policies,search_pdf_handbook",
        {"expected_tools": ["search_policies", "search_pdf_handbook"]},
    )
    assert multi is not None and multi["tools_hit"] is True

    partial = score_react_tools(
        "search_policies",
        {"expected_tools": ["search_policies", "search_pdf_handbook"]},
    )
    assert partial is not None and partial["tools_hit"] is False
