"""从 CSV / Markdown 抽关系：按列角色（本体同义词），不绑某一份表的列名。"""

from __future__ import annotations

import csv
import re
from dataclasses import dataclass
from pathlib import Path

from ..core.logging import get_logger
from .identity import IdentityIndex, cell, is_null, map_headers, normalize_cell
from .schema import REL_DEPENDS_ON, REL_NEXT, REL_REPORTS_TO

log = get_logger(__name__)

_SPLIT_DEPS = re.compile(r"[,，、/;]+")
_HEADING = re.compile(r"^#\s+(.+)$", re.MULTILINE)


@dataclass(frozen=True)
class PersonFact:
    emp_id: str
    name: str
    dept: str
    title: str
    source: str


@dataclass(frozen=True)
class Triple:
    rel: str
    src: str
    dst: str
    source: str
    props: dict[str, str]
    extractor: str = "rule"


def parse_markdown_tables(text: str) -> list[tuple[list[str], list[list[str]]]]:
    tables: list[tuple[list[str], list[list[str]]]] = []
    headers: list[str] | None = None
    rows: list[list[str]] = []
    seen_sep = False

    def flush() -> None:
        nonlocal headers, rows, seen_sep
        if headers and rows:
            tables.append((headers, rows))
        headers, rows, seen_sep = None, [], False

    for raw in text.splitlines():
        line = raw.strip()
        if not (line.startswith("|") and line.endswith("|")):
            flush()
            continue
        cells = [c.strip() for c in line.strip("|").split("|")]
        if headers is None:
            headers = cells
            continue
        if not seen_sep and all(re.fullmatch(r":?-{3,}:?", c.replace(" ", "")) for c in cells):
            seen_sep = True
            continue
        if len(cells) == len(headers):
            rows.append(cells)
    flush()
    return tables


def document_title(text: str, fallback: str = "") -> str:
    match = _HEADING.search(text)
    if match:
        return match.group(1).strip()
    return fallback


def extract_people_from_csv(path: Path) -> list[PersonFact]:
    people: list[PersonFact] = []
    with path.open(encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        if not reader.fieldnames:
            return people
        header_by_role: dict[str, str] = {}
        for h in reader.fieldnames:
            mapped = map_headers([h])
            for role in mapped:
                header_by_role.setdefault(role, h)
        if "person_name" not in header_by_role:
            return people
        for row in reader:
            name = normalize_cell(row.get(header_by_role["person_name"], ""))
            if is_null(name):
                continue
            people.append(
                PersonFact(
                    emp_id=normalize_cell(row.get(header_by_role.get("emp_id", ""), "")),
                    name=name,
                    dept=normalize_cell(row.get(header_by_role.get("dept", ""), "")),
                    title=normalize_cell(row.get(header_by_role.get("title", ""), "")),
                    source=str(path),
                )
            )
    return people


def _split_multi(value: str) -> list[str]:
    return [p for p in (normalize_cell(x) for x in _SPLIT_DEPS.split(value)) if not is_null(p)]


def extract_triples_from_markdown(text: str, source: str) -> list[Triple]:
    process = document_title(text, fallback=Path(source).stem)
    triples: list[Triple] = []
    for headers, rows in parse_markdown_tables(text):
        roles = map_headers(headers)
        if "person_name" in roles and "manager" in roles:
            for row in rows:
                name = cell(row, roles, "person_name")
                manager = cell(row, roles, "manager")
                if is_null(name) or is_null(manager):
                    continue
                triples.append(Triple(REL_REPORTS_TO, name, manager, source, {}))
            continue
        if "service" in roles and "depends" in roles:
            for row in rows:
                svc = cell(row, roles, "service")
                if is_null(svc):
                    continue
                for dep in _split_multi(cell(row, roles, "depends")):
                    triples.append(Triple(REL_DEPENDS_ON, svc, dep, source, {}))
            continue
        if "seq" in roles and "step" in roles:
            steps = []
            for row in rows:
                seq_raw = re.sub(r"\D", "", cell(row, roles, "seq"))
                if not seq_raw:
                    continue
                steps.append(
                    (
                        int(seq_raw),
                        cell(row, roles, "step"),
                        cell(row, roles, "actor"),
                    )
                )
            steps.sort(key=lambda x: x[0])
            for i, (seq, name, actor) in enumerate(steps):
                node = f"{process}:{seq}:{name}"
                props = {"seq": str(seq), "actor": actor, "process": process}
                dst = ""
                if i + 1 < len(steps):
                    nseq, nname, _ = steps[i + 1]
                    dst = f"{process}:{nseq}:{nname}"
                triples.append(Triple(REL_NEXT, node, dst, source, props))
    return triples


def resolve_triples(triples: list[Triple], people: list[PersonFact]) -> list[Triple]:
    index = IdentityIndex(people)
    out: list[Triple] = []
    for t in triples:
        if t.rel == REL_REPORTS_TO:
            src = index.resolve(t.src)
            dst = index.resolve(t.dst)
            if not src or not dst:
                continue
            out.append(Triple(t.rel, src, dst, t.source, t.props, t.extractor))
        else:
            out.append(t)
    return out


def extract_all(
    *,
    csv_paths: list[Path],
    markdown_docs: list[tuple[str, str]],
    llm_triples: list[Triple] | None = None,
) -> tuple[list[PersonFact], list[Triple]]:
    people: list[PersonFact] = []
    for path in csv_paths:
        people.extend(extract_people_from_csv(path))
    triples: list[Triple] = []
    for text, source in markdown_docs:
        triples.extend(extract_triples_from_markdown(text, source))
    if llm_triples:
        triples.extend(llm_triples)
    triples = resolve_triples(triples, people)
    log.info(
        "graph.extracted",
        people=len(people),
        triples=len(triples),
        reports=sum(1 for t in triples if t.rel == REL_REPORTS_TO),
        deps=sum(1 for t in triples if t.rel == REL_DEPENDS_ON),
        steps=sum(1 for t in triples if t.rel == REL_NEXT),
        llm=len(llm_triples or []),
    )
    return people, triples
