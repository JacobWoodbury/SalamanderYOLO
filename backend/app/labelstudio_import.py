from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Optional

from app.video_io import probe_video


def _normalize_export(raw: Any) -> list[dict[str, Any]]:
    if isinstance(raw, list):
        return [t for t in raw if isinstance(t, dict)]
    if isinstance(raw, dict):
        if "tasks" in raw and isinstance(raw["tasks"], list):
            return [t for t in raw["tasks"] if isinstance(t, dict)]
        return [raw]
    raise ValueError("Label Studio export must be a JSON array of tasks or an object with a 'tasks' array")


def _task_video_basename(task: dict[str, Any]) -> str:
    fu = task.get("file_upload")
    if isinstance(fu, str) and fu:
        return Path(fu).name
    data = task.get("data") or {}
    if isinstance(data, dict):
        v = data.get("video")
        if isinstance(v, str) and v:
            return Path(v.replace("\\", "/")).name
    return ""


def _pick_task(tasks: list[dict[str, Any]], upload_name: str, task_id_hint: Optional[str]) -> dict[str, Any]:
    if task_id_hint:
        try:
            tid = int(task_id_hint)
        except ValueError as e:
            raise ValueError("task_id must be an integer (Label Studio task id)") from e
        for t in tasks:
            if int(t.get("id", -1)) == tid:
                return t
        raise ValueError(f"No task with id={tid} in export")

    up = upload_name.lower()
    up_stem = Path(upload_name).stem.lower()
    candidates: list[dict[str, Any]] = []
    for t in tasks:
        base = _task_video_basename(t).lower()
        if not base:
            continue
        if up == base or base.endswith(up) or up in base or up_stem in base.replace("-", "_"):
            candidates.append(t)
    if len(candidates) == 1:
        return candidates[0]
    if len(candidates) > 1:
        ids = [t.get("id") for t in candidates]
        raise ValueError(
            f"Multiple tasks match upload {upload_name!r}; pass task_id. Matching task ids: {ids}"
        )
    if len(tasks) == 1:
        return tasks[0]
    ids = [t.get("id") for t in tasks]
    raise ValueError(
        f"Could not match upload {upload_name!r} to a task. Pass task_id. Available task ids: {ids}"
    )


def _videorectangle_sequences(task: dict[str, Any]) -> list[list[dict[str, Any]]]:
    out: list[list[dict[str, Any]]] = []
    anns = task.get("annotations") or []
    if not isinstance(anns, list):
        return out
    for ann in anns:
        if not isinstance(ann, dict):
            continue
        for r in ann.get("result") or []:
            if not isinstance(r, dict):
                continue
            if r.get("type") != "videorectangle":
                continue
            val = r.get("value") or {}
            seq = val.get("sequence")
            if not isinstance(seq, list) or not seq:
                continue
            kfs: list[dict[str, Any]] = []
            for pt in seq:
                if not isinstance(pt, dict):
                    continue
                if pt.get("enabled") is False:
                    continue
                fr = pt.get("frame")
                if fr is None:
                    continue
                kfs.append(pt)
            if kfs:
                kfs.sort(key=lambda p: int(p["frame"]))
                out.append(kfs)
    return out


def _lerp(a: float, b: float, t: float) -> float:
    return a + (b - a) * t


def _box_at_ls_frame(kfs: list[dict[str, Any]], ls_frame: int) -> tuple[float, float, float, float]:
    """Return x,y,w,h in Label Studio percent units (0–100 scale). Rotation is ignored (axis-aligned box)."""
    if not kfs:
        raise ValueError("empty keyframe sequence")
    f0 = int(kfs[0]["frame"])
    f_last = int(kfs[-1]["frame"])
    if ls_frame <= f0:
        p = kfs[0]
        return float(p["x"]), float(p["y"]), float(p["width"]), float(p["height"])
    if ls_frame >= f_last:
        p = kfs[-1]
        return float(p["x"]), float(p["y"]), float(p["width"]), float(p["height"])
    for i in range(len(kfs) - 1):
        a, b = kfs[i], kfs[i + 1]
        fa, fb = int(a["frame"]), int(b["frame"])
        if fa <= ls_frame <= fb:
            if fb == fa:
                return float(a["x"]), float(a["y"]), float(a["width"]), float(a["height"])
            t = (ls_frame - fa) / (fb - fa)
            return (
                _lerp(float(a["x"]), float(b["x"]), t),
                _lerp(float(a["y"]), float(b["y"]), t),
                _lerp(float(a["width"]), float(b["width"]), t),
                _lerp(float(a["height"]), float(b["height"]), t),
            )
    p = kfs[-1]
    return float(p["x"]), float(p["y"]), float(p["width"]), float(p["height"])


def _pct_to_xyxy(x_pct: float, y_pct: float, w_pct: float, h_pct: float, W: int, H: int) -> list[float]:
    x1 = x_pct / 100.0 * W
    y1 = y_pct / 100.0 * H
    x2 = (x_pct + w_pct) / 100.0 * W
    y2 = (y_pct + h_pct) / 100.0 * H
    return [x1, y1, x2, y2]


def run_labelstudio_import(
    *,
    input_video: Path,
    export_path: Path,
    work_dir: Path,
    upload_filename: str,
    task_id_hint: Optional[str] = None,
) -> dict[str, Any]:
    """
    Build tracks.json from Label Studio JSON (videorectangle keyframes), interpolated per video frame.
    Does not require YOLO weights. Rotation on keyframes is ignored (axis-aligned rectangle in percent space).
    """
    raw = json.loads(export_path.read_text(encoding="utf-8"))
    tasks = _normalize_export(raw)
    task = _pick_task(tasks, upload_filename, task_id_hint)
    seqs = _videorectangle_sequences(task)
    if not seqs:
        raise ValueError("No videorectangle annotations with a non-empty sequence found in matched task")

    fps, width, height, frame_count_cv = probe_video(input_video)
    if width <= 0 or height <= 0:
        raise ValueError("Could not read video width/height")

    # Prefer OpenCV frame count; fall back to export hint
    n = frame_count_cv if frame_count_cv > 0 else 0
    if n <= 0:
        for seq in seqs:
            for p in seq:
                n = max(n, int(p.get("frame", 0)))
        if n <= 0:
            raise ValueError("Could not determine frame count from video or export")
    # Label Studio frames are 1-based in exports we have seen
    max_ls = max(int(p["frame"]) for seq in seqs for p in seq)
    n = max(n, max_ls)

    frames: list[dict[str, Any]] = []
    for fi in range(n):
        ls_frame = fi + 1
        tracks: list[dict[str, Any]] = []
        for tid, seq in enumerate(seqs):
            x, y, w, h = _box_at_ls_frame(seq, ls_frame)
            xyxy = _pct_to_xyxy(x, y, w, h, width, height)
            tracks.append({"id": tid, "xyxy": xyxy, "conf": 1.0})
        frames.append({"i": fi, "tracks": tracks})

    meta: dict[str, Any] = {
        "fps": fps,
        "width": width,
        "height": height,
        "frame_count": len(frames),
        "frame_count_cv": frame_count_cv,
        "model_path": "label_studio_import",
        "label_studio_task_id": task.get("id"),
        "label_studio_source": _task_video_basename(task),
    }

    payload = {"meta": meta, "frames": frames}
    tracks_path = work_dir / "tracks.json"
    with tracks_path.open("w", encoding="utf-8") as f:
        json.dump(payload, f)
    meta_path = work_dir / "meta.json"
    with meta_path.open("w", encoding="utf-8") as f:
        json.dump(meta, f)
    return meta
