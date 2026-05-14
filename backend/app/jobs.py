from __future__ import annotations

import enum
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
