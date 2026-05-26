"""Helpers for avoiding Git LFS pointer stubs masquerading as .pt checkpoints."""
from __future__ import annotations

from pathlib import Path


def is_git_lfs_pointer(path: Path) -> bool:
    if not path.is_file():
        return False
    head = path.read_bytes()[:64]
    return head.startswith(b"version https://git-lfs.github.com")


def ensure_downloadable_model(model_arg: str, root: Path) -> str:
    """
    If model_arg is a local path to an LFS stub, remove it so Ultralytics downloads the real weights.
    Returns the string to pass to YOLO().
    """
    candidates: list[Path] = []
    p = Path(model_arg)
    if p.is_absolute() or "/" in model_arg or "\\ in model_arg":
        candidates.append(p)
    else:
        candidates.append(root / model_arg)
        candidates.append(Path(model_arg))

    for path in candidates:
        if path.is_file() and is_git_lfs_pointer(path):
            print(
                f"Removing Git LFS stub at {path} (not real weights). "
                f"Ultralytics will download {Path(model_arg).name}."
            )
            path.unlink()
            return Path(model_arg).name

    return model_arg
