from __future__ import annotations

import json
import os
from pathlib import Path

from ultralytics import YOLO

from app.video_io import probe_video


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def default_weights_path() -> Path:
    override = os.environ.get("YOLO_WEIGHTS")
    if override:
        return Path(override).expanduser().resolve()
    return _repo_root() / "weights" / "best.pt"


def run_tracking(
    *,
    input_video: Path,
    work_dir: Path,
    weights_path: Path,
) -> dict:
    """
    Run Ultralytics YOLO tracking on a video file. Writes tracks.json and meta.json under work_dir.
    Returns meta dict for the job registry.
    """
    if not input_video.is_file():
        raise FileNotFoundError(str(input_video))
    if not weights_path.is_file():
        raise FileNotFoundError(
            f"YOLO weights not found at {weights_path}. "
            "Train and place best.pt in weights/, or set YOLO_WEIGHTS."
        )

    fps, width, height, frame_count_cv = probe_video(input_video)

    model = YOLO(str(weights_path))

    frames: list[dict] = []
    for frame_idx, result in enumerate(
        model.track(
            source=str(input_video),
            stream=True,
            persist=True,
            verbose=False,
        )
    ):
        tracks: list[dict] = []
        boxes = result.boxes
        if boxes is not None and boxes.xyxy is not None:
            xyxy = boxes.xyxy.cpu().numpy()
            confs = boxes.conf.cpu().numpy() if boxes.conf is not None else None
            ids = boxes.id.cpu().numpy() if boxes.id is not None else None
            for i in range(xyxy.shape[0]):
                x1, y1, x2, y2 = (float(v) for v in xyxy[i])
                conf = float(confs[i]) if confs is not None else 0.0
                tid = int(ids[i]) if ids is not None else i
                tracks.append({"id": tid, "xyxy": [x1, y1, x2, y2], "conf": conf})
        frames.append({"i": frame_idx, "tracks": tracks})

    frame_count = len(frames)
    meta = {
        "fps": fps,
        "width": width,
        "height": height,
        "frame_count": frame_count,
        "frame_count_cv": frame_count_cv,
        "model_path": str(weights_path),
    }

    tracks_payload = {"meta": meta, "frames": frames}
    tracks_path = work_dir / "tracks.json"
    with tracks_path.open("w", encoding="utf-8") as f:
        json.dump(tracks_payload, f)

    meta_path = work_dir / "meta.json"
    with meta_path.open("w", encoding="utf-8") as f:
        json.dump(meta, f)

    return meta
