"""Neo4j 驱动（懒加载，CI 无 neo4j 包也能 import 其它模块）。"""

from __future__ import annotations

from contextlib import contextmanager
from typing import Any, Iterator

from ..core.config import get_settings


def _graph_database():
    try:
        from neo4j import GraphDatabase
    except ImportError as exc:
        raise RuntimeError(
            "未安装 neo4j 驱动。请执行：uv sync --extra prod"
        ) from exc
    return GraphDatabase


def get_driver():
    s = get_settings()
    return _graph_database().driver(
        s.neo4j_uri, auth=(s.neo4j_user, s.neo4j_password)
    )


@contextmanager
def neo4j_session() -> Iterator[Any]:
    driver = get_driver()
    try:
        with driver.session() as session:
            yield session
    finally:
        driver.close()
