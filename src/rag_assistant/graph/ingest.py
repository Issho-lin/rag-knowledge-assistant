"""prose + CSV → Neo4j。按源文档增量：未改跳过，变更先删该 source 的边再写入。"""

from __future__ import annotations

import re
import json

from ..core.config import get_settings
from ..core.logging import configure_logging, get_logger
from ..ingest.fingerprint import content_hash
from ..ingest.loaders import load_markdown
from ..ingest.run import discover_corpus_roots
from .client import neo4j_session
from .models import GraphDocument

log = get_logger(__name__)
_PIPELINE_VERSION = "graph-v2"

_CONSTRAINTS = (
    "CREATE CONSTRAINT entity_key IF NOT EXISTS FOR (e:Entity) REQUIRE e.key IS UNIQUE",
    "CREATE CONSTRAINT source_doc_path IF NOT EXISTS FOR (d:SourceDoc) REQUIRE d.path IS UNIQUE",
)


def _graph_documents() -> list[tuple[str, str, str]]:
    md_docs: list[tuple[str, str, str]] = []
    for root in discover_corpus_roots():
        if root.name != "kb_graph":
            continue
        md_dir = root / "markdown"
        if md_dir.is_dir():
            for path in sorted(md_dir.glob("*.md")):
                doc = load_markdown(path)
                md_docs.append((doc.text, str(path), content_hash(str(path), doc.text)))
    return md_docs


def _wipe(session) -> None:
    session.run("MATCH (n) DETACH DELETE n")
    log.info("graph.reset_wiped")


def _ensure_constraints(session) -> None:
    for name in ("person_name", "service_name", "step_id"):
        session.run(f"DROP CONSTRAINT {name} IF EXISTS")
    for cypher in _CONSTRAINTS:
        session.run(cypher)


def _source_is_current(session, path: str, file_hash: str) -> bool:
    rec = session.run(
        """
        MATCH (d:SourceDoc {path: $path})
        RETURN d.file_hash AS hash, d.pipeline_version AS version
        """,
        path=path,
    ).single()
    return bool(
        rec
        and rec.get("hash") == file_hash
        and rec.get("version") == _PIPELINE_VERSION
    )


def _touch_source(session, path: str, file_hash: str) -> None:
    session.run(
        """
        MERGE (d:SourceDoc {path: $path})
        SET d.file_hash = $hash, d.pipeline_version = $version
        """,
        path=path,
        hash=file_hash,
        version=_PIPELINE_VERSION,
    )


def _delete_source_edges(session, source: str) -> None:
    session.run("MATCH ()-[r]->() WHERE r.source = $source DELETE r", source=source)
    session.run(
        """
        MATCH (n:Entity)
        WHERE $source IN coalesce(n.sources, [])
        SET n.sources = [item IN n.sources WHERE item <> $source]
        WITH n
        WHERE size(n.sources) = 0 AND NOT (n)--()
        DELETE n
        """,
        source=source,
    )
    log.info("graph.source_cleared", source=source)


def _safe_label(value: str) -> str:
    value = re.sub(r"[^A-Za-z0-9_]+", "_", value or "Entity").strip("_")
    if "_" in value or value.isupper() or value.islower():
        value = "".join(part[:1].upper() + part[1:].lower() for part in value.split("_"))
    if not re.fullmatch(r"[A-Za-z][A-Za-z0-9]{0,62}", value):
        return "Entity"
    return value


def _safe_rel(value: str) -> str:
    value = re.sub(r"(?<=[a-z0-9])(?=[A-Z])", "_", value or "RELATED_TO")
    value = re.sub(r"[^A-Za-z0-9_]+", "_", value).strip("_").upper()
    if not re.fullmatch(r"[A-Z][A-Z0-9_]{0,62}", value):
        return "RELATED_TO"
    return value


def _neo4j_properties(properties: dict) -> dict:
    """仅保留 Neo4j 可直接存储的标量或同类标量数组。"""
    allowed = (str, int, float, bool)
    return {
        str(key): value
        for key, value in properties.items()
        if isinstance(value, allowed)
        or (
            isinstance(value, list)
            and all(isinstance(item, allowed) for item in value)
        )
    }


def _entity_key(entity_id: str) -> str:
    """开放域默认按规范化实体 ID 合并；类型作为可叠加 Label，不参与主键。"""
    return " ".join(entity_id.casefold().split())


def _entity_identity(entity_id: str, properties: dict) -> tuple[str, str]:
    display_value = next(
        (
            properties[key]
            for key in ("name", "display_name", "label", "title")
            if isinstance(properties.get(key), str) and properties[key].strip()
        ),
        None,
    )
    if display_value is None:
        display_value = next(
            (
                value
                for key, value in properties.items()
                if (key.endswith("_name") or key.endswith("_name_cn"))
                and isinstance(value, str)
                and value.strip()
            ),
            entity_id,
        )
    aliases = properties.get("aliases")
    if display_value == entity_id and isinstance(aliases, list):
        display_value = next(
            (
                alias
                for alias in aliases
                if isinstance(alias, str) and alias.strip() and alias != entity_id
            ),
            entity_id,
        )
    display_name = str(display_value).strip()
    return _entity_key(display_name), display_name


def _canonical_order(properties: dict) -> int | float | None:
    for key, value in properties.items():
        folded = key.casefold()
        if isinstance(value, (int, float)) and any(
            token in folded for token in ("sequence", "seq", "index", "order")
        ):
            return value
    return None


def _resolve_endpoint(
    raw_id: str,
    evidence: str,
    identities: dict[str, tuple[str, str]],
) -> tuple[str, str]:
    if raw_id in identities:
        return identities[raw_id]
    normalized = _entity_key(raw_id)
    for alias, identity in identities.items():
        if _entity_key(alias) == normalized:
            return identity
    evidence_matches = {
        identity
        for identity in identities.values()
        if identity[1] and identity[1] in evidence
    }
    if len(evidence_matches) == 1:
        return evidence_matches.pop()
    raise ValueError(f"关系端点未声明或存在歧义: {raw_id}")


def _write_graph_documents(session, documents: list[GraphDocument]) -> None:
    """写入 LLM 自动发现的任意实体/关系，业务类型不在代码中枚举。"""
    for document in documents:
        identity: dict[str, tuple[str, str]] = {}
        document_name = document.title or document.source
        document_key = _entity_key(document_name)
        session.run(
            """
            MERGE (d:Entity {key: $key})
            SET d:Document,
                d.name = $name,
                d.source_path = $source,
                d.sources = CASE
                    WHEN $source IN coalesce(d.sources, []) THEN d.sources
                    ELSE coalesce(d.sources, []) + $source
                END
            """,
            key=document_key,
            name=document_name,
            source=document.source,
        )
        for entity in document.entities:
            label = _safe_label(entity.type)
            properties = _neo4j_properties(entity.properties)
            order = _canonical_order(properties)
            if order is not None:
                properties["_order"] = order
            key, display_name = _entity_identity(entity.id, properties)
            properties.pop("name", None)
            identity[entity.id] = (key, display_name)
            aliases = properties.pop("aliases", [])
            if not isinstance(aliases, list):
                aliases = [str(aliases)]
            if entity.id != display_name and entity.id not in aliases:
                aliases.append(entity.id)
            identity[display_name] = (key, display_name)
            for alias in aliases:
                identity[str(alias)] = (key, display_name)
            session.run(
                f"""
                MERGE (n:Entity {{key: $key}})
                SET n:{label},
                    n.name = $name,
                    n += $properties,
                    n.properties_json = $properties_json,
                    n.aliases = $aliases,
                    n.sources = CASE
                        WHEN $source IN coalesce(n.sources, []) THEN n.sources
                        ELSE coalesce(n.sources, []) + $source
                    END,
                    n.evidence = $evidence,
                    n.confidence = $confidence
                """,
                key=key,
                name=display_name,
                properties=properties,
                properties_json=json.dumps(entity.properties, ensure_ascii=False),
                aliases=aliases,
                source=entity.source,
                evidence=entity.evidence,
                confidence=entity.confidence,
            )
        for key, name in set(identity.values()):
            if key == document_key:
                continue
            session.run(
                """
                MATCH (d:Entity {key: $document_key})
                MATCH (n:Entity {key: $entity_key})
                MERGE (d)-[r:MENTIONS]->(n)
                SET r.source = $source, r.extractor = 'system'
                """,
                document_key=document_key,
                entity_key=key,
                source=document.source,
            )
        for relation in document.relations:
            rel = _safe_rel(relation.relation)
            source_label = _safe_label(relation.source_type)
            target_label = _safe_label(relation.target_type)
            source_key, source_name = _resolve_endpoint(
                relation.source_id,
                relation.evidence,
                identity,
            )
            target_key, target_name = _resolve_endpoint(
                relation.target_id,
                relation.evidence,
                identity,
            )
            session.run(
                f"""
                MERGE (a:Entity {{key: $source_key}})
                ON CREATE SET a.name = $source
                SET a:{source_label},
                    a.sources = CASE
                        WHEN $doc_source IN coalesce(a.sources, []) THEN a.sources
                        ELSE coalesce(a.sources, []) + $doc_source
                    END
                MERGE (b:Entity {{key: $target_key}})
                ON CREATE SET b.name = $target
                SET b:{target_label},
                    b.sources = CASE
                        WHEN $doc_source IN coalesce(b.sources, []) THEN b.sources
                        ELSE coalesce(b.sources, []) + $doc_source
                    END
                MERGE (a)-[r:{rel}]->(b)
                SET r.source = $doc_source,
                    r.evidence = $evidence,
                    r.properties_json = $properties_json,
                    r.confidence = $confidence,
                    r.extractor = $extractor
                """,
                source_key=source_key,
                target_key=target_key,
                source=source_name,
                target=target_name,
                doc_source=relation.source,
                evidence=relation.evidence,
                properties_json=json.dumps(relation.properties, ensure_ascii=False),
                confidence=relation.confidence,
                extractor=relation.extractor,
            )


def ingest_graph(*, reset: bool = False) -> dict[str, int]:
    """默认按 SourceDoc.file_hash 增量；``reset=True`` 清空后全量。"""
    configure_logging()
    md_docs = _graph_documents()
    if not md_docs:
        print("未找到 kb_graph 语料。请在 data/corpus/kb_graph/markdown/ 放置 MD。")
        return {"documents": 0, "entities": 0, "relations": 0}

    s = get_settings()
    if not s.graph_llm_extract:
        raise RuntimeError("GRAPH_LLM_EXTRACT=false：通用图入库不再回退旧领域规则")
    graph_documents: list[GraphDocument] = []
    skipped = 0

    with neo4j_session() as session:
        _ensure_constraints(session)
        current_sources = {source for _, source, _ in md_docs}
        stale_sources = [
            row["path"]
            for row in session.run("MATCH (d:SourceDoc) RETURN d.path AS path")
            if row.get("path") not in current_sources
        ]
        for text, source, file_hash in md_docs:
            if not reset and _source_is_current(session, source, file_hash):
                skipped += 1
                continue
            from .extract_llm import extract_graph_document_with_llm

            document = extract_graph_document_with_llm(
                text,
                source,
                file_hash=file_hash,
            )
            if not document.entities and not document.relations:
                raise RuntimeError(f"图抽取为空，拒绝覆盖已有数据: {source}")
            graph_documents.append(document)

        def apply_changes(tx) -> None:
            if reset:
                _wipe(tx)
            for source in stale_sources:
                _delete_source_edges(tx, source)
                tx.run("MATCH (d:SourceDoc {path: $path}) DELETE d", path=source)
            for document in graph_documents:
                _delete_source_edges(tx, document.source)
                _write_graph_documents(tx, [document])
                _touch_source(tx, document.source, document.file_hash)

        session.execute_write(apply_changes)

        n_entities = session.run(
            "MATCH (n:Entity) RETURN count(n) AS n"
        ).single()["n"]
        n_relations = session.run(
            "MATCH (:Entity)-[r]->(:Entity) RETURN count(r) AS n"
        ).single()["n"]

    stats = {
        "documents": len(graph_documents),
        "skipped_docs": skipped,
        "deleted_docs": len(stale_sources),
        "entities": int(n_entities),
        "relations": int(n_relations),
    }
    log.info("graph.ingest_done", **stats, uri=s.neo4j_uri)
    print(
        f"\n图入库：Entity={stats['entities']} Relation={stats['relations']} "
        f"更新 {stats['documents']} 篇，跳过 {skipped} 篇，删除 {len(stale_sources)} 篇 "
        f"({s.neo4j_uri})"
    )
    return stats
