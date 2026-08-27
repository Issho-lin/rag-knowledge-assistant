"""通用 Graph RAG 模型、抽取与查询安全测试。"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from rag_assistant.graph.extract_llm import extract_graph_document_with_llm
from rag_assistant.graph.ingest import (
    _entity_identity,
    _entity_key,
    _canonical_order,
    _resolve_endpoint,
    _safe_label,
    _safe_rel,
    _source_is_current,
)
from rag_assistant.graph.models import GraphDocument
from rag_assistant.graph.plan import GraphPlan, parse_plan_payload
from rag_assistant.graph.query import (
    _candidate_terms,
    _generic_plan_query,
    _resolve_candidate,
    _validated_relationships,
)


def test_graph_document_accepts_unseen_domain():
    document = GraphDocument.model_validate(
        {
            "source": "medical.md",
            "entities": [
                {"id": "阿司匹林", "type": "Drug"},
                {"id": "发热", "type": "Symptom"},
            ],
            "relations": [
                {
                    "source_id": "阿司匹林",
                    "source_type": "Drug",
                    "relation": "TREATS",
                    "target_id": "发热",
                    "target_type": "Symptom",
                }
            ],
        }
    )
    assert document.relations[0].relation == "TREATS"


def test_llm_extractor_parses_unseen_domain(monkeypatch):
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
    document = extract_graph_document_with_llm("刘慈欣创作了《三体》。", "book.md")
    assert [entity.type for entity in document.entities] == ["Person", "Book"]
    assert document.relations[0].relation == "AUTHOR_OF"
    assert document.title == "book"


def test_llm_extractor_does_not_silently_swallow_failure(monkeypatch):
    def fail(*_args, **_kwargs):
        raise RuntimeError("provider unavailable")

    monkeypatch.setattr("rag_assistant.graph.extract_llm.LLMClient.invoke", fail)
    with pytest.raises(RuntimeError, match="provider unavailable"):
        extract_graph_document_with_llm("有内容", "broken.md")


def test_graph_plan_rejects_removed_legacy_fields():
    with pytest.raises(ValidationError):
        parse_plan_payload(
            '{"intent":"path_search","entities":["A"],"pattern":"reports_to"}'
        )


def test_graph_plan_supports_generic_attribute_query():
    plan = GraphPlan(
        intent="attribute_lookup",
        entity_types=["Drug"],
        filters={"status": "approved"},
        return_fields=["name", "manufacturer"],
    )
    assert plan.entity_types == ["Drug"]
    assert plan.filters == {"status": "approved"}


def test_graph_plan_normalizes_empty_filter_list():
    plan = parse_plan_payload(
        '{"intent":"path_search","entities":["A"],"filters":[]}'
    )
    assert plan.filters == {}
    plan = parse_plan_payload(
        '{"intent":"entity_lookup","min_hops":null,"max_hops":0}'
    )
    assert (plan.min_hops, plan.max_hops) == (0, 1)


def test_relationships_must_exist_in_catalog():
    assert _validated_relationships(["AUTHOR_OF"], ["AUTHOR_OF", "TREATS"]) == [
        "AUTHOR_OF"
    ]
    assert _validated_relationships(["MADE_UP"], ["AUTHOR_OF"]) is None
    assert _validated_relationships(["bad relation"], ["bad relation"]) is None


def test_dynamic_schema_names_are_canonicalized():
    assert _safe_label("APPROVAL_STEP") == "ApprovalStep"
    assert _safe_label("Department") == "Department"
    assert _safe_label("service") == "Service"
    assert _safe_rel("reportsTo") == "REPORTS_TO"
    assert _safe_rel("depends-on") == "DEPENDS_ON"


def test_entity_identity_does_not_depend_on_llm_type_wording():
    assert _entity_key(" 林舒 ") == _entity_key("林舒")
    assert _entity_identity("person_lin_shu", {"name": "林舒"}) == ("林舒", "林舒")
    assert _entity_identity(
        "Step_Financial_Review",
        {"step_name_cn": "财务复核"},
    ) == ("财务复核", "财务复核")
    assert _entity_identity(
        "APPLICANT_SUBMIT",
        {"aliases": ["申请人提交"]},
    ) == ("申请人提交", "申请人提交")
    assert _canonical_order({"step_index": 2}) == 2
    assert _canonical_order({"title": "无顺序"}) is None


def test_relation_endpoint_can_reconcile_from_unique_evidence():
    identities = {
        "step_2": ("直属上级审批", "直属上级审批"),
        "step_3": ("财务复核", "财务复核"),
    }
    assert _resolve_endpoint(
        "Step2Approve",
        "| 2 | 直属上级审批 | 直属上级 |",
        identities,
    ) == ("直属上级审批", "直属上级审批")
    with pytest.raises(ValueError, match="关系端点未声明"):
        _resolve_endpoint("unknown", "无证据", identities)


class _FakeSession:
    def __init__(self, rows):
        self.rows = rows
        self.calls = []

    def run(self, cypher, **params):
        self.calls.append((cypher, params))
        return self.rows


class _SingleResult:
    def __init__(self, row):
        self.row = row

    def single(self):
        return self.row


class _SourceSession:
    def __init__(self, row):
        self.row = row

    def run(self, *_args, **_kwargs):
        return _SingleResult(self.row)


def test_path_search_constrains_both_source_and_target():
    session = _FakeSession([])
    plan = GraphPlan(
        intent="path_search",
        entities=["A", "C"],
        relation_types=["LINKS_TO"],
        min_hops=2,
        max_hops=2,
        direction="outgoing",
    )
    _generic_plan_query(
        session,
        plan,
        available_relations=["LINKS_TO"],
    )
    cypher, params = session.calls[0]
    assert "target.name = $target" in cypher
    assert params["source"] == "A"
    assert params["target"] == "C"


def test_unknown_relation_fails_closed_without_query():
    session = _FakeSession([])
    plan = GraphPlan(
        intent="path_search",
        entities=["A"],
        relation_types=["MADE_UP"],
    )
    assert (
        _generic_plan_query(session, plan, available_relations=["LINKS_TO"]) == []
    )
    assert session.calls == []


def test_relationship_lookup_uses_typed_document_mentions_as_provenance_fallback():
    session = _FakeSession(
        [
            {
                "source": "流程",
                "relation": "CONTAINS_STEP",
                "target": "步骤一",
                "properties": {},
            },
            {
                "source": "流程",
                "relation": "MENTIONS",
                "target": "步骤一",
                "properties": {},
            },
            {
                "source": "流程",
                "relation": "MENTIONS",
                "target": "步骤二",
                "properties": {},
            },
        ]
    )
    plan = GraphPlan(
        intent="relationship_lookup",
        entities=["流程"],
        relation_types=["CONTAINS_STEP"],
        target_entity_types=["Step"],
        direction="outgoing",
    )
    rows = _generic_plan_query(
        session,
        plan,
        available_relations=["CONTAINS_STEP", "MENTIONS"],
    )
    assert len(rows) == 2
    assert session.calls[0][1]["rels"] == ["CONTAINS_STEP", "MENTIONS"]


def test_source_skip_requires_hash_and_pipeline_version():
    assert _source_is_current(
        _SourceSession({"hash": "h1", "version": "graph-v2"}),
        "doc.md",
        "h1",
    )
    assert not _source_is_current(
        _SourceSession({"hash": "h1", "version": "graph-v1"}),
        "doc.md",
        "h1",
    )


def test_catalog_candidate_supports_partial_chinese_name():
    assert "报销审批链" in _candidate_terms("报销审批链有哪些环节？")
    catalog = {
        "entity_candidates": [
            {
                "name": "费用报销审批链",
                "aliases": [],
                "types": ["Document"],
            }
        ]
    }
    assert _resolve_candidate("报销审批链", catalog) == "费用报销审批链"


def test_exact_entity_name_wins_over_another_nodes_alias():
    catalog = {
        "entity_candidates": [
            {"name": "machine_id", "aliases": ["费用报销审批链"], "types": ["Workflow"]},
            {"name": "费用报销审批链", "aliases": [], "types": ["Document"]},
        ]
    }
    assert _resolve_candidate("费用报销审批链", catalog) == "费用报销审批链"


def test_relation_aware_resolution_selects_connected_alias_candidate():
    catalog = {
        "entity_candidates": [
            {
                "name": "费用报销审批链",
                "aliases": [],
                "types": ["Document"],
                "outgoing_relations": ["MENTIONS"],
            },
            {
                "name": "FeeReimbursementApprovalChain",
                "aliases": ["费用报销审批链"],
                "types": ["ApprovalChain"],
                "outgoing_relations": ["CONTAINS_STEP"],
            },
        ]
    }
    assert (
        _resolve_candidate(
            "费用报销审批链",
            catalog,
            relation_types=["CONTAINS_STEP"],
            entity_types=["ApprovalChain"],
        )
        == "FeeReimbursementApprovalChain"
    )
    assert (
        _resolve_candidate(
            "报销审批链",
            catalog,
            relation_types=["CONTAINS_STEP"],
        )
        == "FeeReimbursementApprovalChain"
    )
