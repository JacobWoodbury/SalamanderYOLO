from __future__ import annotations

import enum
import json
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from threading import Lock
from typing import Any, Optional


class JobStatus(str, enum.Enum):
    PENDING = "pending"
    RUNNING = "running"
    DONE = "done"
    ERROR = "error"


@dataclass
class Job:
    id: str
    status: JobStatus = JobStatus.PENDING
    percent: int = 0
    error: Optional[str] = None
    meta: dict[str, Any] = field(default_factory=dict)
    work_dir: Optional[Path] = None


_lock = Lock()
_jobs: dict[str, Job] = {}


def create_job(work_root: Path) -> Job:
    job_id = uuid.uuid4().hex
    work_dir = work_root / job_id
    work_dir.mkdir(parents=True, exist_ok=True)
    job = Job(id=job_id, work_dir=work_dir)
    with _lock:
        _jobs[job_id] = job
    return job


def get_job(job_id: str) -> Optional[Job]:
    with _lock:
        return _jobs.get(job_id)


def update_job(job_id: str, **kwargs: Any) -> None:
    with _lock:
        job = _jobs.get(job_id)
        if not job:
            return
        for k, v in kwargs.items():
            setattr(job, k, v)


def restore_jobs_from_disk(work_root: Path) -> int:
    """Re-register jobs after a server reload (--reload clears in-memory state)."""
    if not work_root.is_dir():
        return 0
    restored = 0
    with _lock:
        for work_dir in work_root.iterdir():
            if not work_dir.is_dir():
                continue
            job_id = work_dir.name
            if len(job_id) != 32 or job_id in _jobs:
                continue
            meta: dict[str, Any] = {}
            error: Optional[str] = None
            tracks_path = work_dir / "tracks.json"
            meta_path = work_dir / "meta.json"
            if tracks_path.is_file():
                status = JobStatus.DONE
                if meta_path.is_file():
                    try:
                        meta = json.loads(meta_path.read_text(encoding="utf-8"))
                    except (OSError, json.JSONDecodeError):
                        meta = {}
            elif list(work_dir.glob("input.*")):
                status = JobStatus.ERROR
                error = "Processing was interrupted (server restarted). Upload again."
            else:
                continue
            _jobs[job_id] = Job(
                id=job_id,
                status=status,
                percent=100 if status == JobStatus.DONE else 0,
                error=error,
                meta=meta,
                work_dir=work_dir,
            )
            restored += 1
    return restored
