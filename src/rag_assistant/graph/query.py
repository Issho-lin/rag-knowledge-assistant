"""图检索：GraphPlan → 参数化 Cypher。变长跳数只来自校验后的 1..3 整数。"""

from __future__ import annotations

from typing import Any

from ..core.config import get_settings
from ..core.logging import get_logger
from .client import neo4j_session
from .identity import IdentityIndex
from .plan import GraphPlan, infer_plan_from_lexicon, plan_graph_query
from .schema import REL_DEPENDS_ON, REL_REPORTS_TO

log = get_logger(__name__)


def classify_intent(question: str) -> str:
    """兼容旧测试名：本体词典模式。"""
    plan = infer_plan_from_lexicon(question)
    if plan.pattern == "reports_to" and plan.hops >= 2:
        return "reports_2hop"
    if plan.pattern == "depends_on" and plan.hops >= 2:
        return "depends_2hop"
    return {
        "reports_to": "reports_1hop",
        "depends_on": "depends_1hop",
        "approval_chain": "approval_chain",
        "neighborhood": "neighborhood",
    }[plan.pattern]


def match_entity(question: str, names: list[str]) -> str | None:
    hits = [n for n in names if n and n in question]
    if not hits:
        return None
    return max(hits, key=len)


def _var_len(rel: str, hops: int, exact: bool) -> str:
    if rel not in {REL_REPORTS_TO, REL_DEPENDS_ON}:
        raise ValueError(f"不允许的关系类型: {rel}")
    hops = min(max(hops, 1), 3)
    if hops == 1:
        return f"-[:{rel}]->"
    if exact:
        return f"-[:{rel}*{hops}]->"
    return f"-[:{rel}*1..{hops}]->"


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


def _catalog(session) -> dict[str, list[str]]:
    person_rows = list(session.run("MATCH (p:Person) RETURN p.name AS name, p.emp_id AS emp_id"))
    people = [r["name"] for r in person_rows if r.get("name")]
    services = [r["name"] for r in session.run("MATCH (s:Service) RETURN s.name AS name") if r.get("name")]
    processes = [
        r["name"]
        for r in session.run("MATCH (t:Step) RETURN DISTINCT t.process AS name")
        if r.get("name")
    ]
    return {
        "people": people,
        "services": services,
        "processes": processes,
        "person_records": [
            {"name": r["name"], "emp_id": r.get("emp_id") or ""} for r in person_rows if r.get("name")
        ],
    }


def execute_plan(session, plan: GraphPlan) -> list[dict[str, Any]]:
    if plan.pattern == "approval_chain":
        records = list(
            session.run(
                """
                MATCH (s:Step)
                WHERE $process = '' OR s.process CONTAINS $process
                OPTIONAL MATCH (s)-[:NEXT]->(n:Step)
                RETURN s.seq AS seq, s.name AS name, s.actor AS actor,
                       s.process AS process, n.name AS next_name, s.source AS source
                ORDER BY s.process, s.seq
                """,
                process=plan.process or "",
            )
        )
        if not records:
            return []
        by_proc: dict[str, list] = {}
        source = "kb_graph"
        for r in records:
            proc = r["process"] or "流程"
            by_proc.setdefault(proc, []).append(r)
            source = r.get("source") or source
        blocks = []
        for proc, items in by_proc.items():
            lines = []
            for r in items:
                nxt = f" → 下一环「{r['next_name']}」" if r.get("next_name") else ""
                lines.append(f"{r['seq']}. {r['name']}（{r['actor']}）{nxt}")
            blocks.append(f"{proc}：\n" + "\n".join(lines))
        return _chunks([{"text": "\n\n".join(blocks), "source": source}], source=source)

    if not plan.entity:
        return []

    if plan.pattern == "reports_to":
        rel = _var_len(REL_REPORTS_TO, plan.hops, plan.exact_hops)
        cypher = f"""
        MATCH path = (a:Person {{name: $name}}){rel}(b:Person)
        WITH a, b, length(path) AS hops, [n IN nodes(path) | n.name] AS names
        RETURN a.name AS src, b.name AS dst, b.title AS title,
               a.emp_id AS emp_id, b.emp_id AS mgr_id, hops AS hops, names AS chain
        ORDER BY hops
        """
        records = list(session.run(cypher, name=plan.entity))
        return _chunks(
            [
                {
                    "text": (
                        f"{r['src']}（{r['emp_id']}）到 {r['dst']}（{r['mgr_id']}，{r['title']}）"
                        f"共 {int(r['hops'])} 跳。路径：{' → '.join(r['chain'])}。"
                    ),
                    "source": "graph:REPORTS_TO",
                }
                for r in records
            ],
            source="graph:REPORTS_TO",
        )

    if plan.pattern == "depends_on":
        rel = _var_len(REL_DEPENDS_ON, plan.hops, plan.exact_hops)
        cypher = f"""
        MATCH path = (a:Service {{name: $name}}){rel}(b:Service)
        WITH a, b, length(path) AS hops, [n IN nodes(path) | n.name] AS names
        RETURN a.name AS src, b.name AS dst, hops AS hops, names AS chain
        ORDER BY hops, dst
        """
        records = list(session.run(cypher, name=plan.entity))
        return _chunks(
            [
                {
                    "text": (
                        f"{r['src']} 依赖 {r['dst']}（{int(r['hops'])} 跳）。"
                        f"路径：{' → '.join(r['chain'])}。"
                    ),
                    "source": "graph:DEPENDS_ON",
                }
                for r in records
            ],
            source="graph:DEPENDS_ON",
        )

    records = list(
        session.run(
            """
            MATCH (a {name: $name})-[r]-(b)
            RETURN labels(a)[0] AS la, a.name AS src, type(r) AS rel,
                   labels(b)[0] AS lb, coalesce(b.name, b.id) AS dst
            LIMIT 20
            """,
            name=plan.entity,
        )
    )
    return _chunks(
        [
            {
                "text": f"{r['la']}:{r['src']} -[{r['rel']}]- {r['lb']}:{r['dst']}",
                "source": "graph:neighborhood",
            }
            for r in records
        ],
        source="graph:neighborhood",
    )


def query_relations(question: str, *, k: int = 8) -> list[dict[str, Any]]:
    s = get_settings()
    with neo4j_session() as session:
        catalog = _catalog(session)
        if s.graph_query_planner:
            plan = plan_graph_query(question, catalog=catalog)
        else:
            plan = infer_plan_from_lexicon(question)
        people = catalog.get("person_records") or [{"name": n, "emp_id": ""} for n in catalog["people"]]
        index = IdentityIndex(people)
        linked = None
        if plan.entity:
            linked = index.resolve(plan.entity)
        if not linked:
            linked = index.link_in_question(question, extra=catalog["services"])
        if linked:
            plan = plan.model_copy(update={"entity": linked})
        if plan.pattern == "approval_chain" and not plan.process and catalog["processes"]:
            hinted = match_entity(question, catalog["processes"])
            if hinted:
                plan = plan.model_copy(update={"process": hinted})
        chunks = execute_plan(session, plan)
    log.info(
        "graph.query",
        pattern=plan.pattern,
        hops=plan.hops,
        entity=plan.entity,
        hits=len(chunks),
        question=question[:80],
    )
    return chunks[:k]
