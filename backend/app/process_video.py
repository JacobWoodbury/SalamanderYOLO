from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Callable, Optional

from ultralytics import YOLO

from app.video_io import probe_video

_model_cache: dict[str, YOLO] = {}


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def default_weights_path() -> Path:
    override = os.environ.get("YOLO_WEIGHTS")
    if override:
        return Path(override).expanduser().resolve()
    return _repo_root() / "weights" / "best.pt"


def validate_weights_file(weights_path: Path) -> None:
    """
    Reject Git LFS pointer stubs and other non-checkpoint files before torch.load runs.
    """
    if not weights_path.is_file():
        raise FileNotFoundError(
            f"YOLO weights not found at {weights_path}. "
            "Train and place best.pt in weights/, or set YOLO_WEIGHTS (e.g. yolo11n.pt)."
        )
    head = weights_path.read_bytes()[:256]
    if head.startswith(b"version https://git-lfs.github.com"):
        raise ValueError(
            f"{weights_path} is a Git LFS pointer, not real model weights. "
            "Run: git lfs pull — or copy a trained best.pt from runs/detect/.../weights/best.pt — "
            "or set YOLO_WEIGHTS=yolo11n.pt to use a downloaded base model."
        )
    if head.lstrip().startswith((b"{", b"[")):
        raise ValueError(
            f"{weights_path} looks like JSON/text, not a PyTorch .pt checkpoint. "
            "Use weights/best.pt from training, not a Label Studio export."
        )
    size = weights_path.stat().st_size
    if size < 100_000:
        raise ValueError(
            f"{weights_path} is too small ({size} bytes) to be a YOLO weights file."
        )


def _env_float(name: str, default: float, minimum: float = 0.0, maximum: float = 1.0) -> float:
    raw = os.environ.get(name)
    if raw is None or not str(raw).strip():
        return default
    try:
        return min(maximum, max(minimum, float(raw)))
    except ValueError:
        return default


def _env_int(name: str, default: int, minimum: int = 1) -> int:
    raw = os.environ.get(name)
    if raw is None or not str(raw).strip():
        return default
    try:
        return max(minimum, int(raw))
    except ValueError:
        return default


def inference_device() -> str | int:
    """
    Device for Ultralytics track(). Uses YOLO_DEVICE if set (e.g. 0, cuda, cpu).
    Otherwise cuda:0 when PyTorch sees a GPU, else cpu.
    """
    override = os.environ.get("YOLO_DEVICE", "").strip()
    if override:
        if override.isdigit():
            return int(override)
        return override
    import torch

    if torch.cuda.is_available():
        return 0
    return "cpu"


def _get_model(weights_path: Path) -> YOLO:
    key = str(weights_path.resolve())
    if key not in _model_cache:
        _model_cache[key] = YOLO(key)
    return _model_cache[key]


def _tracks_from_result(result: Any) -> list[dict]:
    tracks: list[dict] = []
    boxes = result.boxes
    if boxes is None or boxes.xyxy is None:
        return tracks
    xyxy = boxes.xyxy.cpu().numpy()
    confs = boxes.conf.cpu().numpy() if boxes.conf is not None else None
    ids = boxes.id.cpu().numpy() if boxes.id is not None else None
    for i in range(xyxy.shape[0]):
        x1, y1, x2, y2 = (float(v) for v in xyxy[i])
        conf = float(confs[i]) if confs is not None else 0.0
        tid = int(ids[i]) if ids is not None else i
        tracks.append({"id": tid, "xyxy": [x1, y1, x2, y2], "conf": conf})
    return tracks


def _expand_sparse_frames(
    sparse: dict[int, list[dict]],
    frame_count: int,
) -> list[dict]:
    """Fill skipped frames so the player can index frames[video_frame_index]."""
    if frame_count <= 0:
        return []
    if not sparse:
        return [{"i": i, "tracks": []} for i in range(frame_count)]

    keys = sorted(sparse)
    out: list[dict] = []
    last_tracks: list[dict] = []
    ki = 0
    for fi in range(frame_count):
        while ki + 1 < len(keys) and keys[ki + 1] <= fi:
            ki += 1
            last_tracks = sparse[keys[ki]]
        if fi in sparse:
            last_tracks = sparse[fi]
            out.append({"i": fi, "tracks": sparse[fi]})
        elif keys[ki] <= fi:
            out.append({"i": fi, "tracks": list(last_tracks)})
        else:
            out.append({"i": fi, "tracks": []})
    return out


def run_tracking(
    *,
    input_video: Path,
    work_dir: Path,
    weights_path: Path,
    on_progress: Optional[Callable[[int], None]] = None,
) -> dict:
    """
    Run Ultralytics YOLO tracking on a video file. Writes tracks.json and meta.json under work_dir.
    Returns meta dict for the job registry.
    """
    if not input_video.is_file():
        raise FileNotFoundError(str(input_video))
    validate_weights_file(weights_path)

    fps, width, height, frame_count_cv = probe_video(input_video)
    imgsz = _env_int("YOLO_IMGSZ", 320, minimum=160)
    vid_stride = _env_int("YOLO_VID_STRIDE", 1, minimum=1)
    conf = _env_float("YOLO_CONF", 0.1, minimum=0.01, maximum=0.95)
    device = inference_device()

    model = _get_model(weights_path)

    infer_total = max(1, (frame_count_cv + vid_stride - 1) // vid_stride) if frame_count_cv > 0 else 1
    if on_progress:
        on_progress(0)

    sparse: dict[int, list[dict]] = {}
    stream_idx = 0
    for result in model.track(
        source=str(input_video),
        stream=True,
        persist=True,
        verbose=False,
        imgsz=imgsz,
        vid_stride=vid_stride,
        conf=conf,
        device=device,
    ):
        fi = getattr(result, "frame", None)
        if fi is None:
            fi = stream_idx * vid_stride
        frame_i = int(fi)
        sparse[frame_i] = _tracks_from_result(result)
        stream_idx += 1
        if on_progress:
            # Reserve ~10% for expanding frames and writing JSON.
            pct = min(90, int(stream_idx / infer_total * 90))
            on_progress(pct)

    n_out = frame_count_cv if frame_count_cv > 0 else (max(sparse) + 1 if sparse else 0)
    if on_progress:
        on_progress(92)
    frames = _expand_sparse_frames(sparse, n_out)
    if on_progress:
        on_progress(96)
    frame_count = len(frames)
    meta = {
        "fps": fps,
        "width": width,
        "height": height,
        "frame_count": frame_count,
        "frame_count_cv": frame_count_cv,
        "model_path": str(weights_path),
        "inference_imgsz": imgsz,
        "inference_vid_stride": vid_stride,
        "inference_device": str(device),
        "inference_conf": conf,
    }

    tracks_payload = {"meta": meta, "frames": frames}
    tracks_path = work_dir / "tracks.json"
    with tracks_path.open("w", encoding="utf-8") as f:
        json.dump(tracks_payload, f)

    meta_path = work_dir / "meta.json"
    with meta_path.open("w", encoding="utf-8") as f:
        json.dump(meta, f)

    return meta
