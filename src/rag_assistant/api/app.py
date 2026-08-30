"""星云知识控制台 HTTP API。"""

from __future__ import annotations

import shutil
import uuid
from pathlib import Path
from typing import Any

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from ..conversation import ChatTurn
from ..core.logging import configure_logging
from ..core.paths import CHROMA_ROOT
from ..ingest.loaders import load_file
from ..ingest.preview import preview_path
from ..ingest.run import upsert_documents
from ..ingest.uploads import UploadRejected, destination_path, folder_for
from ..kb.browse import kb_summaries, list_chunks, list_documents
from ..kb.registry import get_kb
from . import jobs

STAGING_ROOT = Path("data/uploads/staging")
STATIC_DIR = Path(__file__).resolve().parent / "static"
MAX_UPLOAD_BYTES = 20 * 1024 * 1024


class ChatTurnIn(BaseModel):
    role: str
    content: str


class ChatRequest(BaseModel):
    message: str
    history: list[ChatTurnIn] = Field(default_factory=list)


class IngestRequest(BaseModel):
    staging_id: str
    kb_id: str


def _staging_dir(staging_id: str) -> Path:
    path = (STAGING_ROOT / staging_id).resolve()
    root = STAGING_ROOT.resolve()
    if root not in path.parents and path != root:
        raise HTTPException(400, "无效的暂存 id")
    return path


def create_app() -> FastAPI:
    configure_logging()
    app = FastAPI(title="星云知识控制台", version="0.1.0")
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["http://127.0.0.1:5173", "http://localhost:5173"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.get("/api/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/api/kbs")
    def api_kbs() -> dict[str, Any]:
        return {"items": kb_summaries()}

    @app.get("/api/kbs/{kb_id}/documents")
    def api_documents(kb_id: str) -> dict[str, Any]:
        try:
            get_kb(kb_id)
        except KeyError as exc:
            raise HTTPException(404, str(exc)) from exc
        return {"items": list_documents(kb_id)}

    @app.get("/api/kbs/{kb_id}/chunks")
    def api_chunks(
        kb_id: str,
        source: str | None = None,
        q: str | None = None,
        offset: int = 0,
        limit: int = 40,
    ) -> dict[str, Any]:
        try:
            get_kb(kb_id)
        except KeyError as exc:
            raise HTTPException(404, str(exc)) from exc
        return list_chunks(kb_id, source=source, q=q, offset=offset, limit=limit)

    @app.post("/api/preview")
    async def api_preview(
        kb_id: str = Form(...),
        files: list[UploadFile] = File(...),
    ) -> dict[str, Any]:
        try:
            get_kb(kb_id)
        except KeyError as exc:
            raise HTTPException(404, str(exc)) from exc
        if not files:
            raise HTTPException(400, "请至少选择一个文件")

        staging_id = uuid.uuid4().hex[:12]
        dest_root = STAGING_ROOT / staging_id
        dest_root.mkdir(parents=True, exist_ok=True)
        previews = []
        try:
            for upload in files:
                name = upload.filename or "upload"
                suffix = Path(name).suffix.lower()
                try:
                    folder_for(kb_id, suffix)
                except UploadRejected as exc:
                    shutil.rmtree(dest_root, ignore_errors=True)
                    raise HTTPException(400, str(exc)) from exc
                data = await upload.read()
                if len(data) > MAX_UPLOAD_BYTES:
                    shutil.rmtree(dest_root, ignore_errors=True)
                    raise HTTPException(400, f"{name} 超过 20MB 限制")
                path = dest_root / Path(name).name
                path.write_bytes(data)
                previews.append(preview_path(path, kb_id=kb_id))
        except HTTPException:
            raise
        except Exception as exc:
            shutil.rmtree(dest_root, ignore_errors=True)
            raise HTTPException(400, str(exc)) from exc
        return {"staging_id": staging_id, "kb_id": kb_id, "files": previews}

    @app.post("/api/ingest")
    def api_ingest(body: IngestRequest) -> dict[str, Any]:
        try:
            kb = get_kb(body.kb_id)
        except KeyError as exc:
            raise HTTPException(404, str(exc)) from exc
        staging = _staging_dir(body.staging_id)
        if not staging.is_dir():
            raise HTTPException(404, "预览已过期，请重新上传")
        paths = [p for p in staging.iterdir() if p.is_file()]
        if not paths:
            raise HTTPException(400, "暂存目录为空")

        def _work() -> dict[str, Any]:
            committed: list[str] = []
            for src in paths:
                dest = destination_path(body.kb_id, src.name)
                dest.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(src, dest)
                committed.append(str(dest))
            if kb.backend == "graph":
                from ..graph.ingest import ingest_graph

                stats = ingest_graph()
                shutil.rmtree(staging, ignore_errors=True)
                return {"mode": "graph", "files": committed, **stats}
            docs = [load_file(Path(p)) for p in committed]
            stats = upsert_documents(docs, kb_id=body.kb_id)
            shutil.rmtree(staging, ignore_errors=True)
            return {"mode": "vector", "files": committed, **stats}

        job = jobs.submit(_work, message=f"入库 {kb.id}")
        return {"job_id": job.id, "status": job.status}

    @app.get("/api/jobs/{job_id}")
    def api_job(job_id: str) -> dict[str, Any]:
        job = jobs.get_job(job_id)
        if job is None:
            raise HTTPException(404, "任务不存在")
        return {
            "id": job.id,
            "status": job.status,
            "message": job.message,
            "result": job.result,
        }

    @app.post("/api/chat")
    def api_chat(body: ChatRequest) -> dict[str, Any]:
        from ..query.modes.agent_react import query_agent_react

        history = [
            ChatTurn(role=t.role, content=t.content)
            for t in body.history
            if t.role in {"user", "assistant"}
        ]
        result = query_agent_react(body.message, history=history)
        chunks = []
        for c in result.chunks:
            text = str(c.get("text") or "")
            chunks.append(
                {
                    "id": c.get("id"),
                    "source": c.get("source"),
                    "filename": Path(str(c.get("source") or "")).name,
                    "score": c.get("score"),
                    "kb": c.get("kb"),
                    "preview": text.replace("\n", " ").strip()[:280],
                    "text": text,
                }
            )
        citations = [c.to_dict() for c in result.citations]
        return {
            "answer": result.answer,
            "refused": result.refused,
            "refusal_note": result.refusal_note(),
            "rewritten_query": result.rewritten_query,
            "routed_tool": result.routed_tool,
            "routed_kb_id": result.routed_kb_id,
            "chunks": chunks,
            "citations": citations,
        }

    app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

    @app.get("/")
    def index() -> FileResponse:
        return FileResponse(STATIC_DIR / "index.html")

    return app


def main() -> None:
    import argparse

    import uvicorn

    parser = argparse.ArgumentParser(description="星云知识控制台")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8000)
    args = parser.parse_args()
    CHROMA_ROOT.mkdir(parents=True, exist_ok=True)
    uvicorn.run(
        "rag_assistant.api.app:create_app",
        factory=True,
        host=args.host,
        port=args.port,
        reload=False,
    )
