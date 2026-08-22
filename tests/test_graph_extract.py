"""图抽取、列角色、查询计划（不连 Neo4j）。"""

from __future__ import annotations

from pathlib import Path

from rag_assistant.graph.extract import extract_people_from_csv, extract_triples_from_markdown
from rag_assistant.graph.identity import IdentityIndex
from rag_assistant.graph.plan import infer_plan_from_lexicon, parse_plan_payload
from rag_assistant.graph.query import classify_intent, match_entity
from rag_assistant.graph.schema import REL_REPORTS_TO
from rag_assistant.graph.models import GraphDocument
from rag_assistant.graph.extract_llm import extract_graph_document_with_llm


def test_extract_reports_and_skip_dash():
    text = Path("data/corpus/kb_graph/markdown/12-组织架构与汇报线.md").read_text(
        encoding="utf-8"
    )
    triples = extract_triples_from_markdown(text, "org.md")
    reports = {(t.src, t.dst) for t in triples if t.rel == REL_REPORTS_TO}
    assert ("周凯", "何北") in reports
    assert ("何北", "苏晚") in reports
    assert not any(t.src == "苏晚" for t in triples)


def test_extract_depends_two_hop_pair():
    text = Path("data/corpus/kb_graph/markdown/13-系统依赖与服务清单.md").read_text(
        encoding="utf-8"
    )
    triples = extract_triples_from_markdown(text, "dep.md")
    deps = {(t.src, t.dst) for t in triples if t.rel == "DEPENDS_ON"}
    assert ("订单服务", "支付服务") in deps
    assert ("支付服务", "账户服务") in deps
    assert ("订单服务", "账户服务") not in deps


def test_extract_approval_uses_document_title_as_process():
    text = Path("data/corpus/kb_graph/markdown/14-费用报销审批链.md").read_text(
        encoding="utf-8"
    )
    triples = extract_triples_from_markdown(text, "apv.md")
    steps = [t for t in triples if t.rel == "NEXT_STEP"]
    assert any("财务复核" in t.src and "超标加签" in t.dst for t in steps)
    assert any(t.props.get("actor") == "林舒" for t in steps)
    assert all(t.props.get("process") == "费用报销审批链" for t in steps)


def test_column_role_synonyms_not_bound_to_one_corpus():
    text = """
| 员工 | 经理 |
|------|------|
| 周凯 | 何北 |
"""
    triples = extract_triples_from_markdown(text, "syn.md")
    assert ("周凯", "何北") in {(t.src, t.dst) for t in triples}


def test_extract_people_aligns_with_org():
    people = extract_people_from_csv(Path("data/corpus/internal/csv/员工通讯录-摘录.csv"))
    names = {p.name for p in people}
    assert {"周凯", "何北", "苏晚", "林舒"} <= names


def test_identity_resolves_emp_id():
    people = extract_people_from_csv(Path("data/corpus/internal/csv/员工通讯录-摘录.csv"))
    index = IdentityIndex(people)
    assert index.resolve("XY003") == "周凯"
    assert index.link_in_question("工号 XY003 的上级") == "周凯"


def test_classify_intent():
    assert classify_intent("周凯的隔级上级是谁？") == "reports_2hop"
    assert classify_intent("周凯的上级是谁？") == "reports_1hop"
    assert classify_intent("订单服务间接依赖哪些服务？") == "depends_2hop"
    assert classify_intent("报销审批链有哪些环节？") == "approval_chain"


def test_match_entity_longest():
    assert match_entity("订单服务依赖什么", ["服务", "订单服务"]) == "订单服务"
    assert match_entity("年假几天", ["周凯", "何北"]) is None


def test_infer_plan_lexicon_hops():
    plan = infer_plan_from_lexicon("周凯的隔级上级是谁？")
    assert plan.pattern == "reports_to"
    assert plan.hops == 2
    assert plan.exact_hops is True


def test_parse_plan_payload():
    plan = parse_plan_payload(
        '{"pattern":"depends_on","entity":"订单服务","hops":2,"exact_hops":false}'
    )
    assert plan.entity == "订单服务"
    assert plan.hops == 2


def test_generic_graph_document_accepts_new_domain():
    document = GraphDocument.model_validate(
        {
            "source": "book.md",
            "entities": [
                {"id": "刘慈欣", "type": "Person"},
                {"id": "三体", "type": "Book"},
            ],
            "relations": [
                {
                    "source_id": "刘慈欣",
                    "source_type": "Person",
                    "relation": "AUTHOR_OF",
                    "target_id": "三体",
                    "target_type": "Book",
                    "evidence": "刘慈欣创作了《三体》",
                }
            ],
        }
    )
    assert document.entities[1].type == "Book"
    assert document.relations[0].relation == "AUTHOR_OF"


def test_llm_graph_extractor_parses_open_domain(monkeypatch):
    monkeypatch.setattr(
        "rag_assistant.graph.extract_llm.LLMClient.invoke",
        lambda *_args, **_kwargs: (
            '{"entities":[{"id":"刘慈欣","type":"Person"},'
            '{"id":"三体","type":"Book"}],'
            '"relations":[{"source_id":"刘慈欣","source_type":"Person",'
            '"relation":"AUTHOR_OF","target_id":"三体","target_type":"Book",'
            '"evidence":"刘慈欣创作了《三体》"}]}'
        ),
    )
    document = extract_graph_document_with_llm(
        "刘慈欣创作了《三体》。",
        "book.md",
        file_hash="h1",
    )
    assert [e.type for e in document.entities] == ["Person", "Book"]
    assert document.relations[0].relation == "AUTHOR_OF"
    assert document.relations[0].source == "book.md"
