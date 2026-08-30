"""进程内入库任务。单机控制台够用，不上独立队列。"""

from __future__ import annotations

import threading
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Callable


@dataclass
class Job:
    id: str
    status: str  # queued | running | done | error
    message: str = ""
    result: dict[str, Any] = field(default_factory=dict)
    created_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )


_LOCK = threading.Lock()
_JOBS: dict[str, Job] = {}


def get_job(job_id: str) -> Job | None:
    with _LOCK:
        return _JOBS.get(job_id)


def submit(fn: Callable[[], dict[str, Any]], *, message: str = "") -> Job:
    job = Job(id=uuid.uuid4().hex[:12], status="queued", message=message)
    with _LOCK:
        _JOBS[job.id] = job

    def _run() -> None:
        with _LOCK:
            job.status = "running"
        try:
            result = fn()
            with _LOCK:
                job.status = "done"
                job.result = result
                job.message = "完成"
        except Exception as exc:  # noqa: BLE001 — 任务失败要回写给前端
            with _LOCK:
                job.status = "error"
                job.message = str(exc)

    threading.Thread(target=_run, daemon=True).start()
    return job
