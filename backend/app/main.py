from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Optional

from fastapi import BackgroundTasks, FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse

from app import jobs
from app.labelstudio_import import run_labelstudio_import
from app.process_video import default_weights_path, run_tracking

logger = logging.getLogger(__name__)

REPO_ROOT = Path(__file__).resolve().parents[2]
DATA_ROOT = REPO_ROOT / "backend" / "data" / "jobs"
ALLOWED_EXTENSIONS = {".mp4", ".mov", ".avi", ".mkv", ".webm", ".m4v"}


def _process_job(job_id: str) -> None:
    job = jobs.get_job(job_id)
    if not job or not job.work_dir:
        return
    jobs.update_job(job_id, status=jobs.JobStatus.RUNNING, error=None)
    try:
        inputs = sorted(job.work_dir.glob("input.*"))
        if not inputs:
            raise RuntimeError("Missing uploaded video file")
        input_path = inputs[0]
        orig_name_file = job.work_dir / "original_upload_name.txt"
        if orig_name_file.is_file():
            upload_name = orig_name_file.read_text(encoding="utf-8").strip() or input_path.name
        else:
            upload_name = input_path.name

        ls_export = job.work_dir / "labelstudio_export.json"
        task_hint_path = job.work_dir / "labelstudio_task_id.txt"
        task_hint = task_hint_path.read_text(encoding="utf-8").strip() if task_hint_path.is_file() else None

        if ls_export.is_file():
            meta = run_labelstudio_import(
                input_video=input_path,
                export_path=ls_export,
                work_dir=job.work_dir,
                upload_filename=upload_name,
                task_id_hint=task_hint or None,
            )
        else:
            weights = default_weights_path()
            meta = run_tracking(input_video=input_path, work_dir=job.work_dir, weights_path=weights)
        jobs.update_job(job_id, status=jobs.JobStatus.DONE, meta=meta, error=None)
    except Exception as e:
        logger.exception("Job %s failed", job_id)
        jobs.update_job(job_id, status=jobs.JobStatus.ERROR, error=str(e))


app = FastAPI(title="Salamander tracker API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://127.0.0.1:5173",
        "http://localhost:5173",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
def startup() -> None:
    DATA_ROOT.mkdir(parents=True, exist_ok=True)
    logging.basicConfig(level=logging.INFO)


@app.get("/api/health")
def health() -> dict:
    w = default_weights_path()
    return {"ok": True, "weights_path": str(w), "weights_exist": w.is_file()}


@app.post("/api/jobs")
async def create_job(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    labels: Optional[UploadFile] = File(None),
    task_id: Optional[str] = Form(None),
) -> JSONResponse:
    if not file.filename:
        raise HTTPException(status_code=400, detail="Missing filename")
    suffix = Path(file.filename).suffix.lower()
    if suffix not in ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported extension {suffix!r}. Allowed: {sorted(ALLOWED_EXTENSIONS)}",
        )

    job = jobs.create_job(DATA_ROOT)
    assert job.work_dir is not None
    dest = job.work_dir / f"input{suffix}"
    original_basename = Path(file.filename).name
    try:
        (job.work_dir / "original_upload_name.txt").write_text(original_basename, encoding="utf-8")
        with dest.open("wb") as out:
            while chunk := await file.read(1024 * 1024):
                out.write(chunk)
        if labels is not None:
            raw = await labels.read()
            if raw:
                try:
                    json.loads(raw.decode("utf-8"))
                except (UnicodeDecodeError, json.JSONDecodeError) as e:
                    raise HTTPException(status_code=400, detail="labels file must be valid UTF-8 JSON") from e
                (job.work_dir / "labelstudio_export.json").write_bytes(raw)
        if task_id is not None and str(task_id).strip():
            (job.work_dir / "labelstudio_task_id.txt").write_text(str(task_id).strip(), encoding="utf-8")
    except HTTPException:
        import shutil

        shutil.rmtree(job.work_dir, ignore_errors=True)
        jobs.update_job(job.id, status=jobs.JobStatus.ERROR, error="Upload failed")
        raise
    except Exception:
        import shutil

        shutil.rmtree(job.work_dir, ignore_errors=True)
        jobs.update_job(job.id, status=jobs.JobStatus.ERROR, error="Upload failed")
        raise HTTPException(status_code=500, detail="Failed to save upload")

    background_tasks.add_task(_process_job, job.id)
    return JSONResponse({"job_id": job.id})


@app.get("/api/jobs/{job_id}")
def get_job(job_id: str) -> dict:
    job = jobs.get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    out: dict = {"status": job.status.value}
    if job.error:
        out["error"] = job.error
    if job.meta:
        out["meta"] = job.meta
    return out


def _job_dir(job_id: str) -> Path:
    job = jobs.get_job(job_id)
    if not job or not job.work_dir:
        raise HTTPException(status_code=404, detail="Job not found")
    return job.work_dir


@app.get("/api/jobs/{job_id}/video")
def get_video(job_id: str) -> FileResponse:
    d = _job_dir(job_id)
    candidates = list(d.glob("input.*"))
    if not candidates:
        raise HTTPException(status_code=404, detail="Video not ready")
    path = candidates[0]
    media = {
        ".mp4": "video/mp4",
        ".webm": "video/webm",
        ".mov": "video/quicktime",
        ".avi": "video/x-msvideo",
        ".mkv": "video/x-matroska",
        ".m4v": "video/x-m4v",
    }.get(path.suffix.lower(), "application/octet-stream")
    return FileResponse(path, media_type=media, filename=path.name)


@app.get("/api/jobs/{job_id}/tracks")
def get_tracks(job_id: str) -> dict:
    d = _job_dir(job_id)
    tracks_path = d / "tracks.json"
    if not tracks_path.is_file():
        raise HTTPException(status_code=404, detail="Tracks not ready")
    return json.loads(tracks_path.read_text(encoding="utf-8"))
