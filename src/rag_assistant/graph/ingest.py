"""prose + CSV → Neo4j。按源文档增量：未改跳过，变更先删该 source 的边再写入。"""

from __future__ import annotations

from pathlib import Path
import re
import json

from ..core.config import get_settings
from ..core.logging import configure_logging, get_logger
from ..ingest.fingerprint import content_hash
from ..ingest.loaders import load_markdown
from ..ingest.run import discover_corpus_roots
from .client import neo4j_session
from .extract import Triple, extract_all, extract_people_from_csv
from .schema import REL_DEPENDS_ON, REL_NEXT, REL_REPORTS_TO
from .models import GraphDocument

log = get_logger(__name__)

_CONSTRAINTS = (
    "CREATE CONSTRAINT person_name IF NOT EXISTS FOR (p:Person) REQUIRE p.name IS UNIQUE",
    "CREATE CONSTRAINT service_name IF NOT EXISTS FOR (s:Service) REQUIRE s.name IS UNIQUE",
    "CREATE CONSTRAINT step_id IF NOT EXISTS FOR (t:Step) REQUIRE t.id IS UNIQUE",
    "CREATE CONSTRAINT source_doc_path IF NOT EXISTS FOR (d:SourceDoc) REQUIRE d.path IS UNIQUE",
)


def _graph_markdown_and_csv() -> tuple[list[tuple[str, str, str]], list[Path]]:
    md_docs: list[tuple[str, str, str]] = []
    csv_paths: list[Path] = []
    for root in discover_corpus_roots():
        csv_dir = root / "csv"
        if csv_dir.is_dir():
            csv_paths.extend(sorted(csv_dir.glob("*.csv")))
        if root.name != "kb_graph":
            continue
        md_dir = root / "markdown"
        if md_dir.is_dir():
            for path in sorted(md_dir.glob("*.md")):
                doc = load_markdown(path)
                md_docs.append((doc.text, str(path), content_hash(str(path), doc.text)))
    return md_docs, csv_paths


def _wipe(session) -> None:
    session.run("MATCH (n) DETACH DELETE n")
    log.info("graph.reset_wiped")


def _ensure_constraints(session) -> None:
    for cypher in _CONSTRAINTS:
        session.run(cypher)


def _source_hash(session, path: str) -> str | None:
    rec = session.run(
        "MATCH (d:SourceDoc {path: $path}) RETURN d.file_hash AS h",
        path=path,
    ).single()
    return rec["h"] if rec else None


def _touch_source(session, path: str, file_hash: str) -> None:
    session.run(
        "MERGE (d:SourceDoc {path: $path}) SET d.file_hash = $hash",
        path=path,
        hash=file_hash,
    )


def _delete_source_edges(session, source: str) -> None:
    session.run("MATCH ()-[r]->() WHERE r.source = $source DELETE r", source=source)
    session.run("MATCH (s:Step {source: $source}) DETACH DELETE s", source=source)
    log.info("graph.source_cleared", source=source)


def _write_people(session, people) -> None:
    for p in people:
        session.run(
            """
            MERGE (n:Person {name: $name})
            SET n.emp_id = $emp_id, n.dept = $dept, n.title = $title,
                n.source = $source, n.identity_master = true
            """,
            name=p.name,
            emp_id=p.emp_id,
            dept=p.dept,
            title=p.title,
            source=p.source,
        )


def _safe_label(value: str) -> str:
    value = re.sub(r"[^A-Za-z0-9_]", "_", value or "Entity")
    return value[:63].strip("_") or "Entity"


def _safe_rel(value: str) -> str:
    value = re.sub(r"[^A-Za-z0-9_]", "_", value or "RELATED_TO")
    return value[:63].strip("_") or "RELATED_TO"


def _write_graph_documents(session, documents: list[GraphDocument]) -> None:
    """写入 LLM 自动发现的任意实体/关系，业务类型不在代码中枚举。"""
    for document in documents:
        for entity in document.entities:
            label = _safe_label(entity.type)
            session.run(
                f"""
                MERGE (n:Entity:{label} {{name: $name}})
                SET n.properties_json = $properties_json,
                    n.source = $source,
                    n.evidence = $evidence,
                    n.confidence = $confidence
                """,
                name=entity.id,
                properties_json=json.dumps(entity.properties, ensure_ascii=False),
                source=entity.source,
                evidence=entity.evidence,
                confidence=entity.confidence,
            )
        for relation in document.relations:
            rel = _safe_rel(relation.relation)
            session.run(
                f"""
                MERGE (a:Entity {{name: $source}})
                MERGE (b:Entity {{name: $target}})
                MERGE (a)-[r:{rel}]->(b)
                SET r.source = $doc_source,
                    r.evidence = $evidence,
                    r.properties_json = $properties_json,
                    r.confidence = $confidence,
                    r.extractor = $extractor
                """,
                source=relation.source_id,
                target=relation.target_id,
                doc_source=relation.source,
                evidence=relation.evidence,
                properties_json=json.dumps(relation.properties, ensure_ascii=False),
                confidence=relation.confidence,
                extractor=relation.extractor,
            )


def _parse_step_id(src_id: str, props: dict[str, str]) -> tuple[int, str]:
    seq = int(props["seq"]) if props.get("seq", "").isdigit() else 0
    if src_id.count(":") >= 2:
        _proc, seq_s, name = src_id.rsplit(":", 2)
        if seq_s.isdigit():
            seq = int(seq_s)
        return seq, name
    return seq, src_id


def _write_triples(session, triples: list[Triple]) -> None:
    for t in triples:
        if t.rel == REL_REPORTS_TO:
            session.run(
                """
                MERGE (a:Person {name: $src})
                MERGE (b:Person {name: $dst})
                MERGE (a)-[r:REPORTS_TO]->(b)
                SET r.source = $source, r.extractor = $extractor
                """,
                src=t.src,
                dst=t.dst,
                source=t.source,
                extractor=t.extractor,
            )
        elif t.rel == REL_DEPENDS_ON:
            session.run(
                """
                MERGE (a:Service {name: $src})
                MERGE (b:Service {name: $dst})
                MERGE (a)-[r:DEPENDS_ON]->(b)
                SET r.source = $source, r.extractor = $extractor
                """,
                src=t.src,
                dst=t.dst,
                source=t.source,
                extractor=t.extractor,
            )
        elif t.rel == REL_NEXT:
            seq, name = _parse_step_id(t.src, t.props)
            session.run(
                """
                MERGE (a:Step {id: $src_id})
                SET a.seq = $seq, a.name = $name, a.actor = $actor,
                    a.process = $process, a.source = $source
                """,
                src_id=t.src,
                seq=seq,
                name=name,
                actor=t.props.get("actor", ""),
                process=t.props.get("process", ""),
                source=t.source,
            )
            if t.dst:
                session.run(
                    """
                    MERGE (b:Step {id: $dst_id})
                    SET b.source = coalesce(b.source, $source)
                    WITH b
                    MATCH (a:Step {id: $src_id})
                    MERGE (a)-[r:NEXT]->(b)
                    SET r.source = $source, r.extractor = $extractor
                    """,
                    dst_id=t.dst,
                    src_id=t.src,
                    source=t.source,
                    extractor=t.extractor,
                )


def ingest_graph(*, reset: bool = False) -> dict[str, int]:
    """默认按 SourceDoc.file_hash 增量；``reset=True`` 清空后全量。"""
    configure_logging()
    md_docs, csv_paths = _graph_markdown_and_csv()
    if not md_docs:
        print("未找到 kb_graph 语料。请在 data/corpus/kb_graph/markdown/ 放置 MD。")
        return {"people": 0, "triples": 0}

    s = get_settings()
    llm_triples: list[Triple] = []
    graph_documents: list[GraphDocument] = []
    work_md: list[tuple[str, str]] = []
    skipped = 0

    with neo4j_session() as session:
        if reset:
            _wipe(session)
        _ensure_constraints(session)

        for text, source, file_hash in md_docs:
            if not reset and _source_hash(session, source) == file_hash:
                skipped += 1
                continue
            _delete_source_edges(session, source)
            work_md.append((text, source))
            if s.graph_llm_extract:
                from .extract_llm import extract_graph_document_with_llm

                graph_documents.append(
                    extract_graph_document_with_llm(
                        text,
                        source,
                        file_hash=file_hash,
                    )
                )
            _touch_source(session, source, file_hash)

        people = []
        for path in csv_paths:
            people.extend(extract_people_from_csv(path))
        _, triples = extract_all(
            csv_paths=csv_paths,
            markdown_docs=work_md,
            llm_triples=llm_triples,
        )
        _write_people(session, people)
        _write_triples(session, triples)
        _write_graph_documents(session, graph_documents)
        n_person = session.run("MATCH (p:Person) RETURN count(p) AS n").single()["n"]
        n_svc = session.run("MATCH (s:Service) RETURN count(s) AS n").single()["n"]
        n_step = session.run("MATCH (t:Step) RETURN count(t) AS n").single()["n"]
        n_rel = session.run("MATCH ()-[r]->() RETURN count(r) AS n").single()["n"]

    stats = {
        "people": len(people),
        "triples": len(triples),
        "skipped_docs": skipped,
        "nodes_person": int(n_person),
        "nodes_service": int(n_svc),
        "nodes_step": int(n_step),
        "rels": int(n_rel),
    }
    log.info("graph.ingest_done", **stats, uri=s.neo4j_uri)
    print(
        f"\n图入库：Person={stats['nodes_person']} Service={stats['nodes_service']} "
        f"Step={stats['nodes_step']} 边={stats['rels']} "
        f"跳过 {skipped} 篇 ({s.neo4j_uri})"
    )
    return stats
