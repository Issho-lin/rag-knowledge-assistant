"""BM25 后端协议：pkl（教学/CI）与 OpenSearch（生产）共用接口。"""

from __future__ import annotations

from typing import Any, Protocol


class BM25Backend(Protocol):
    def rebuild(
        self,
        ids: list[str],
        docs: list[str],
        sources: list[str],
        *,
        metadatas: list[dict[str, str | int]] | None = None,
    ) -> int: ...

    def query(
        self,
        text: str,
        k: int = 4,
        *,
        metadata_filter: dict[str, str] | None = None,
    ) -> list[dict[str, Any]]: ...

    def count(self) -> int: ...
