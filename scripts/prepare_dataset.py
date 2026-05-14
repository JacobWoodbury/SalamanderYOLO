#!/usr/bin/env python3
"""
Build a YOLO detection dataset from a Label Studio JSON export (videorectangle keyframes).

For each keyframed frame index in each task, extracts the matching video frame with OpenCV and
writes a YOLO-format label file (class x_center y_center width height, 0-1). Boxes use the same
axis-aligned percent→pixel logic as the app import (rotation in Label Studio is ignored).

Prerequisites:
  - Place the original MP4 files under --videos-dir. Names can match `file_upload` exactly, or a
    shorter name that appears as a suffix (e.g. Salamander_Video_1.mp4 vs 86128414-Salamander_Video_1.mp4).

Run from project root::

    python scripts/prepare_dataset.py
    python scripts/prepare_dataset.py --export modelSettings.json --videos-dir data/videos/raw
"""
from __future__ import annotations

import argparse
import json
import random
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

import cv2  # noqa: E402

from app.labelstudio_import import (  # noqa: E402
    _box_at_ls_frame,
    _normalize_export,
    _task_video_basename,
    _videorectangle_sequences,
)


def _resolve_video(task: dict, videos_dir: Path) -> Path:
    base = _task_video_basename(task)
    if not base:
        raise FileNotFoundError("Task has no file_upload / data.video basename")
    candidates = [
        videos_dir / base,
        videos_dir / Path(base).name,
    ]
    if "-" in base:
        tail = base.split("-", 1)[-1]
        candidates.append(videos_dir / tail)
    for c in candidates:
        if c.is_file():
            return c.resolve()
    names = sorted(p.name for p in videos_dir.iterdir() if p.is_file())
    raise FileNotFoundError(
        f"Video for task not found under {videos_dir}. Expected something like {base!r}. "
        f"Found files: {names}"
    )


def _ls_percent_to_yolo_line(x: float, y: float, w: float, h: float, class_id: int) -> str:
    """Label Studio top-left x,y and size in % of frame (0-100) → YOLO normalized xywh."""
    xc = (x + w / 2.0) / 100.0
    yc = (y + h / 2.0) / 100.0
    wn = w / 100.0
    hn = h / 100.0
    xc = min(max(xc, 0.0), 1.0)
    yc = min(max(yc, 0.0), 1.0)
    wn = min(max(wn, 1e-6), 1.0)
    hn = min(max(hn, 1e-6), 1.0)
    return f"{class_id} {xc:.6f} {yc:.6f} {wn:.6f} {hn:.6f}"


def _class_id_from_labels(val: dict) -> int:
    labels = val.get("labels")
    if isinstance(labels, list) and labels:
        return 0
    return 0


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--export", type=Path, default=ROOT / "modelSettings.json", help="Label Studio JSON export")
    parser.add_argument("--videos-dir", type=Path, default=ROOT / "data" / "videos" / "raw", help="Folder with source MP4s")
    parser.add_argument("--out", type=Path, default=ROOT / "data" / "dataset", help="YOLO dataset root (images/, labels/)")
    parser.add_argument("--val-ratio", type=float, default=0.2, help="Fraction of images for validation")
    parser.add_argument("--seed", type=int, default=42, help="Shuffle seed for train/val split")
    parser.add_argument(
        "--clean",
        action="store_true",
        help="Remove existing images/ and labels/ under --out before writing",
    )
    args = parser.parse_args()

    export_path = args.export.resolve()
    videos_dir = args.videos_dir.resolve()
    out_root = args.out.resolve()

    if not export_path.is_file():
        raise SystemExit(f"Missing export file: {export_path}")
    if not videos_dir.is_dir():
        raise SystemExit(f"Videos directory not found: {videos_dir}")

    if args.clean and out_root.is_dir():
        for sub in ("images", "labels"):
            p = out_root / sub
            if p.is_dir():
                shutil.rmtree(p)

    raw = json.loads(export_path.read_text(encoding="utf-8"))
    tasks = _normalize_export(raw)

    samples: list[tuple[int, int, Path, list[str]]] = []
    # (task_id, ls_frame, video_path, yolo_lines)

    for task in tasks:
        tid = int(task.get("id", -1))
        anns = task.get("annotations") or []
        if not isinstance(anns, list) or not anns:
            continue
        try:
            video_path = _resolve_video(task, videos_dir)
        except FileNotFoundError as e:
            print(f"Skipping task {tid}: {e}")
            continue

        cap = cv2.VideoCapture(str(video_path))
        if not cap.isOpened():
            print(f"Skipping task {tid}: cannot open video {video_path}")
            continue
        n_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
        cap.release()

        seqs = _videorectangle_sequences(task)
        if not seqs:
            print(f"Skipping task {tid}: no videorectangle sequences")
            continue

        keyframes: set[int] = set()
        for seq in seqs:
            for pt in seq:
                if isinstance(pt, dict) and pt.get("enabled") is False:
                    continue
                if isinstance(pt, dict) and pt.get("frame") is not None:
                    keyframes.add(int(pt["frame"]))

        class_id = 0
        for ann in anns:
            if not isinstance(ann, dict):
                continue
            for r in ann.get("result") or []:
                if isinstance(r, dict) and r.get("type") == "videorectangle":
                    val = r.get("value") or {}
                    class_id = _class_id_from_labels(val)
                    break
            else:
                continue
            break

        for ls_frame in sorted(keyframes):
            fi = ls_frame - 1
            if n_frames > 0 and (fi < 0 or fi >= n_frames):
                continue
            lines: list[str] = []
            for seq in seqs:
                try:
                    x, y, w, h = _box_at_ls_frame(seq, ls_frame)
                except ValueError:
                    continue
                lines.append(_ls_percent_to_yolo_line(x, y, w, h, class_id))
            if not lines:
                continue
            samples.append((tid, ls_frame, video_path, lines))

    if not samples:
        raise SystemExit("No training samples produced. Check export, videos-dir, and video file names.")

    rng = random.Random(args.seed)
    rng.shuffle(samples)

    n = len(samples)
    if n == 1:
        splits = ["train"]
    elif n == 2:
        splits = ["train", "val"]
    else:
        n_val = max(1, int(round(n * args.val_ratio)))
        n_val = min(n_val, n - 1)
        splits = ["train"] * (n - n_val) + ["val"] * n_val

    for sub in ("images/train", "images/val", "labels/train", "labels/val"):
        (out_root / sub).mkdir(parents=True, exist_ok=True)

    written = 0
    for (tid, ls_frame, video_path, lines), split in zip(samples, splits):
        stem = f"task{tid}_frame{ls_frame:06d}"
        img_path = out_root / "images" / split / f"{stem}.jpg"
        lbl_path = out_root / "labels" / split / f"{stem}.txt"

        cap = cv2.VideoCapture(str(video_path))
        cap.set(cv2.CAP_PROP_POS_FRAMES, ls_frame - 1)
        ok, frame = cap.read()
        cap.release()
        if not ok or frame is None:
            continue
        cv2.imwrite(str(img_path), frame)
        lbl_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
        written += 1

    yaml_path = out_root / "dataset.yaml"
    val_path = "images/train" if n == 1 else "images/val"
    yaml_text = (
        "# Auto-generated by scripts/prepare_dataset.py — edit paths if you move the dataset.\n"
        f"path: {out_root.as_posix()}\n"
        "train: images/train\n"
        f"val: {val_path}\n"
        "nc: 1\n"
        "names:\n"
        "  0: Salamander\n"
    )
    yaml_path.write_text(yaml_text, encoding="utf-8")

    print(f"Wrote {written} image/label pairs under {out_root} (from {len(samples)} keyframes)")
    print(f"dataset.yaml → {yaml_path}")
    print("Next: python scripts/train.py")


if __name__ == "__main__":
    main()
