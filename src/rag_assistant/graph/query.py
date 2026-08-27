"""图检索：GraphPlan → 参数化 Cypher。变长跳数只来自校验后的 1..3 整数。"""

from __future__ import annotations

from typing import Any
import re

from ..core.config import get_settings
from ..core.logging import get_logger
from .client import neo4j_session
from .plan import GraphPlan, plan_graph_query

log = get_logger(__name__)


def _validated_relationships(
    requested: list[str], available: list[str]
) -> list[str] | None:
    """关系必须真实存在于当前图库；None 表示模型请求了未知关系。"""
    cleaned = [
        rel
        for rel in requested
        if re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]{0,63}", rel)
    ][:16]
    if requested and (len(cleaned) != len(requested) or not set(cleaned) <= set(available)):
        return None
    return cleaned


def _entity_rows(session, plan: GraphPlan) -> list[dict[str, Any]]:
    cypher = """
    MATCH (n:Entity)
    WHERE (size($entities) = 0 OR n.name IN $entities)
      AND (size($types) = 0 OR any(label IN labels(n) WHERE label IN $types))
      AND all(key IN keys($filters) WHERE n[key] = $filters[key])
    RETURN n.name AS name,
           [label IN labels(n) WHERE label <> 'Entity'] AS types,
           properties(n) AS properties
    ORDER BY coalesce(n._order, 0), n.name
    LIMIT $limit
    """
    return list(
        session.run(
            cypher,
            entities=plan.entities,
            types=plan.entity_types,
            filters=plan.filters,
            limit=plan.limit,
        )
    )


def _generic_plan_query(
    session,
    plan: GraphPlan,
    *,
    available_relations: list[str],
) -> list[dict[str, Any]]:
    """按 intent 执行固定模板；模型输出只能作为参数或受限枚举。"""
    relation_types = _validated_relationships(plan.relation_types, available_relations)
    if relation_types is None:
        log.warning("graph.unknown_relation", requested=plan.relation_types)
        return []
    if plan.intent in {"entity_lookup", "attribute_lookup"}:
        output = []
        for row in _entity_rows(session, plan):
            properties = dict(row["properties"])
            for internal in (
                "key",
                "sources",
                "evidence",
                "confidence",
                "properties_json",
                "aliases",
                "_order",
            ):
                properties.pop(internal, None)
            if plan.return_fields:
                properties = {
                    key: properties.get(key)
                    for key in plan.return_fields
                    if key in properties
                }
            output.append(
                {
                    "text": (
                        f"实体：{row['name']}；类型：{'、'.join(row['types']) or 'Entity'}；"
                        f"属性：{properties}"
                    ),
                    "source": "graph:entity",
                }
            )
        return output
    if not plan.entities:
        return []
    if plan.intent == "relationship_lookup":
        if len(plan.entities) >= 2:
            source, target = plan.entities[:2]
        else:
            source, target = plan.entities[0], ""
        pattern = {
            "outgoing": "(a:Entity {name: $source})-[r]->(b:Entity)",
            "incoming": "(a:Entity {name: $source})<-[r]-(b:Entity)",
            "both": "(a:Entity {name: $source})-[r]-(b:Entity)",
        }[plan.direction]
        effective_relations = list(relation_types)
        if (
            plan.target_entity_types
            and "MENTIONS" in available_relations
            and "MENTIONS" not in effective_relations
        ):
            effective_relations.append("MENTIONS")
        rows = list(
            session.run(
                f"""
                MATCH {pattern}
                WHERE ($target = '' OR b.name = $target)
                  AND (size($rels) = 0 OR type(r) IN $rels)
                  AND (size($types) = 0 OR any(label IN labels(b) WHERE label IN $types))
                RETURN a.name AS source, type(r) AS relation,
                       b.name AS target, properties(r) AS properties
                ORDER BY coalesce(b._order, 0), b.name
                LIMIT $limit
                """,
                source=source,
                target=target,
                rels=effective_relations,
                types=plan.target_entity_types,
                limit=plan.limit,
            )
        )
        deduplicated: dict[str, dict[str, Any]] = {}
        for row in rows:
            deduplicated.setdefault(str(row["target"]), row)
        return [
            {
                "text": f"{r['source']} -[{r['relation']}]-> {r['target']}；属性：{dict(r['properties'])}",
                "source": "graph:relationship",
            }
            for r in deduplicated.values()
        ]

    direction = {
        "outgoing": "->",
        "incoming": "<-",
        "both": "-",
    }[plan.direction]
    upper = min(max(plan.max_hops, 1), 3)
    lower = min(max(plan.min_hops, 1), upper)
    if lower == upper:
        length = str(lower)
    else:
        length = f"{lower}..{upper}"
    arrow = f"-[rels*{length}]{direction}" if direction != "-" else f"-[rels*{length}]-"
    target_filter = "AND target.name = $target" if len(plan.entities) >= 2 else ""
    cypher = f"""
    MATCH path = (start:Entity {{name: $source}}){arrow}(target:Entity)
    WHERE (size($rels) = 0 OR ALL(r IN relationships(path) WHERE type(r) IN $rels))
      AND (size($types) = 0 OR any(label IN labels(target) WHERE label IN $types))
      {target_filter}
    RETURN [n IN nodes(path) | coalesce(n.name, n.id)] AS chain,
           [r IN relationships(path) | type(r)] AS relations,
           length(path) AS hops
    ORDER BY hops
    LIMIT $limit
    """
    rows = list(
        session.run(
            cypher,
            source=plan.entities[0],
            target=plan.entities[1] if len(plan.entities) >= 2 else "",
            rels=relation_types,
            types=plan.target_entity_types,
            limit=plan.limit,
        )
    )
    return [
        {
            "text": f"路径：{' → '.join(r['chain'])}；关系：{'、'.join(r['relations'])}。",
            "source": "graph:path",
        }
        for r in rows
    ]


def _chunks(rows: list[dict[str, Any]], *, source: str) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for i, row in enumerate(rows):
        text = row.get("text") or ""
        if not text:
            continue
        out.append(
            {
                "id": f"g_{i}",
                "text": text,
                "source": row.get("source") or source,
                "score": 1.0 - i * 0.01,
                "kb": "relations",
            }
        )
    return out


def _candidate_terms(question: str) -> list[str]:
    compact = re.sub(r"[\s，。！？、；：,.!?;:（）()]+", "", question)
    terms = {
        compact[start:end]
        for start in range(len(compact))
        for end in range(start + 2, min(len(compact), start + 12) + 1)
    }
    return sorted(terms, key=len, reverse=True)[:200]


def _catalog(session, question: str) -> dict[str, Any]:
    """只召回问题相关的实体候选，并附上图库真实 schema。"""
    candidates = list(
        session.run(
            """
            MATCH (n:Entity)
            WHERE any(term IN $terms WHERE n.name CONTAINS term OR term = n.name)
               OR any(alias IN coalesce(n.aliases, [])
                      WHERE any(term IN $terms WHERE alias CONTAINS term OR term = alias))
            OPTIONAL MATCH (n)-[r]->(target:Entity)
            RETURN n.name AS name,
                   [label IN labels(n) WHERE label <> 'Entity'] AS types,
                   coalesce(n.aliases, []) AS aliases,
                   collect(DISTINCT type(r)) AS outgoing_relations,
                   collect(DISTINCT [label IN labels(target) WHERE label <> 'Entity'])
                       AS outgoing_target_types
            ORDER BY size(n.name) DESC
            LIMIT 50
            """,
            terms=_candidate_terms(question),
        )
    )
    relation_types = [
        str(row["relation_type"])
        for row in session.run(
            "MATCH ()-[r]->() RETURN DISTINCT type(r) AS relation_type ORDER BY relation_type"
        )
        if row.get("relation_type")
    ]
    entity_types = [
        str(row["label"])
        for row in session.run(
            """
            MATCH (n:Entity)
            UNWIND labels(n) AS label
            WITH DISTINCT label WHERE label <> 'Entity'
            RETURN label ORDER BY label
            """
        )
        if row.get("label")
    ]
    return {
        "entity_candidates": [
            {
                "name": row["name"],
                "types": list(row.get("types") or []),
                "aliases": list(row.get("aliases") or []),
                "outgoing_relations": [
                    item for item in (row.get("outgoing_relations") or []) if item
                ],
                "outgoing_target_types": [
                    item
                    for item in (row.get("outgoing_target_types") or [])
                    if item
                ],
            }
            for row in candidates
        ],
        "entity_types": entity_types,
        "relation_types": relation_types,
    }


def _resolve_candidate(
    entity: str,
    catalog: dict[str, Any],
    *,
    relation_types: list[str] | None = None,
    entity_types: list[str] | None = None,
) -> str | None:
    candidates = list(catalog["entity_candidates"])
    if relation_types:
        compatible = [
            item
            for item in candidates
            if set(item["outgoing_relations"]) & set(relation_types)
        ]
        if compatible:
            candidates = compatible
    if entity_types:
        compatible = [
            item for item in candidates if set(item["types"]) & set(entity_types)
        ]
        if compatible:
            candidates = compatible
    for item in candidates:
        if entity == item["name"]:
            return item["name"]
    for item in candidates:
        if entity in item["aliases"]:
            return item["name"]
    fuzzy = [
        item["name"]
        for item in candidates
        if entity in item["name"]
        or item["name"] in entity
        or any(entity in alias or alias in entity for alias in item["aliases"])
    ]
    return max(fuzzy, key=len) if fuzzy else None


def execute_plan(
    session,
    plan: GraphPlan,
    *,
    available_relations: list[str],
) -> list[dict[str, Any]]:
    rows = _generic_plan_query(
        session,
        plan,
        available_relations=available_relations,
    )
    return _chunks(rows, source=f"graph:{plan.intent}")


def query_relations(question: str, *, k: int = 8) -> list[dict[str, Any]]:
    s = get_settings()
    with neo4j_session() as session:
        catalog = _catalog(session, question)
        if not s.graph_query_planner:
            raise RuntimeError("GRAPH_QUERY_PLANNER=false：通用图查询禁止按旧领域词典猜测")
        plan = plan_graph_query(question, catalog=catalog)
        resolutions = {
            entity: _resolve_candidate(
                entity,
                catalog,
                relation_types=plan.relation_types,
                entity_types=plan.entity_types,
            )
            for entity in plan.entities
        }
        resolved = [value for value in resolutions.values() if value]
        unknown_entities = [
            entity for entity, value in resolutions.items() if value is None
        ]
        valid_types = [
            entity_type
            for entity_type in plan.entity_types
            if entity_type in catalog["entity_types"]
        ]
        valid_target_types = [
            entity_type
            for entity_type in plan.target_entity_types
            if entity_type in catalog["entity_types"]
        ]
        if unknown_entities and plan.intent not in {"entity_lookup", "attribute_lookup"}:
            log.warning("graph.unknown_entity", entities=unknown_entities)
            return []
        if unknown_entities and not valid_types:
            log.warning("graph.unknown_entity_or_type", entities=unknown_entities)
            return []
        plan = plan.model_copy(
            update={
                "entities": resolved,
                "entity_types": valid_types,
                "target_entity_types": valid_target_types,
            }
        )
        chunks = execute_plan(
            session,
            plan,
            available_relations=catalog["relation_types"],
        )
    log.info(
        "graph.query",
        intent=plan.intent,
        hops=f"{plan.min_hops}..{plan.max_hops}",
        entities=plan.entities,
        hits=len(chunks),
        question=question[:80],
    )
    return chunks[:k]
