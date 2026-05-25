# SallyTracker — Salamander video tracker

Full-stack app: upload a salamander clip, run **Ultralytics YOLO** tracking on a **FastAPI** backend, then play the video in a **React (Vite)** UI with bounding boxes, a **path trail**, **live center coordinates**, and a **detection count vs time** chart. A **progress wheel** shows job status while processing.

Supports two input paths:

1. **YOLO** — automatic detection + tracking when `weights/best.pt` is present.
2. **Label Studio JSON** — preview manual `videorectangle` video labels without running YOLO.

## Dataset and training pipeline

We labeled **63 frames** total (50 train / 13 val) using Label Studio's video labeling tool with axis-aligned `videorectangle` bounding boxes. Source footage came from seven trimmed MP4 clips covering multiple plastic salamander colors (blue, grey, ensatina), varied backgrounds, different distances, and multi-salamander scenes (`lotsa_salamanders`, `two_salamanders`). Keyframes were exported as Label Studio JSON, then `scripts/prepare_dataset.py` extracted each keyframe from the video with OpenCV and wrote a matching YOLO-format `.txt` label, converting percent-space coordinates to normalized `x_center y_center width height`.

Training used `scripts/train.py` with `yolo11n.pt` as the base, `imgsz=320`, `batch=8`, `epochs=50`, and default Ultralytics augmentations (HSV jitter, mosaic, horizontal flip). Two runs were produced (`salamander_run1`, `salamander_run2`). The best weights from run 2 (final epoch: precision=1.00, recall=0.99, mAP@50=0.995) were copied to `weights/best.pt`.

## YOLO vs Masking
---
Masking would work well when using the plastic salamanders on a table or floor. Their colors are consistent, and the background is generally consistent. When it comes to real salamanders there colors very much more, with some actively blending to their enviornment. YOLO can perform better when it needs to detect the shapes when colors might be too similar to distinguish. 

## How to run

### Prerequisites

- Python 3.11+
- Node 20+
- **Either** `weights/best.pt` (or `YOLO_WEIGHTS` pointing at a `.pt` file), **or** a Label Studio **JSON** export with `videorectangle` annotations.

### Backend

Create the venv **inside `backend/`** (recommended):

```bash
cd backend
python -m venv .venv
source .venv/Scripts/activate   # Windows Git Bash
pip install -r requirements.txt
```

Start the API **from `backend/`** (do not add `--app-dir backend` here — that is only when launching from the repo root):

```bash
cd backend
source .venv/Scripts/activate
uvicorn app.main:app --host 127.0.0.1 --port 8000
```

From the **repository root** instead:

```bash
source backend/.venv/Scripts/activate
uvicorn app.main:app --host 127.0.0.1 --port 8000 --app-dir backend
```

Avoid `--reload` while a long YOLO job is running; a reload clears in-memory job state (uploads on disk are restored on restart when possible).

**Health check:** [http://127.0.0.1:8000/api/health](http://127.0.0.1:8000/api/health)

```json
{
  "ok": true,
  "weights_exist": true,
  "weights_path": ".../weights/best.pt",
  "torch_version": "2.6.0+cu124",
  "cuda_available": true,
  "inference_device": "0",
  "gpu_name": "NVIDIA GeForce GTX 1060 6GB"
}
```

On a laptop without CUDA, `cuda_available` is `false` and `inference_device` is `"cpu"` — the app still works, just slower.

### Frontend

```bash
cd frontend
npm install
npm run dev
```

Open [http://127.0.0.1:5173](http://127.0.0.1:5173). Vite **proxies** `/api` to port 8000.

### Fast GPU run (copy-paste)

Terminal 1 — backend:

```bash
cd /SalamanderTracker/backend
source .venv/Scripts/activate
export YOLO_CONF=0.1
export YOLO_IMGSZ=320
uvicorn app.main:app --host 127.0.0.1 --port 8000
```

Terminal 2 — frontend:

```bash
cd /SalamanderTracker/frontend
npm run dev
```

Upload a **short** clip (15–60 s), ideally similar to training footage (e.g. `data/videos/raw/Salamander_Video_1.mp4`). Confirm `/api/health` shows `cuda_available: true` before expecting GPU speed.

---

## Label Studio video labeling → training → app

You can label **in Label Studio’s video tool** (not only still frames). Export **JSON** (not CSV). Each task should have `type: "videorectangle"` with a `sequence` of keyframes (`frame`, `x`, `y`, `width`, `height` in **percent**, axis-aligned boxes only — rotation is ignored).

Example exports in this repo:

- `[modelSettings.json](modelSettings.json)` — sample with 39 keyframes across two tasks
- `[project-7-at-2026-05-25-18-33-901d5158.json](project-7-at-2026-05-25-18-33-901d5158.json)` — same shape; use **your** export path in commands below

### 1. Put source MP4s on disk

Copy videos into `data/videos/raw/`. Names can match `file_upload` exactly, or the suffix after the first hyphen:


| Export `file_upload`              | Also works as            |
| --------------------------------- | ------------------------ |
| `86128414-Salamander_Video_1.mp4` | `Salamander_Video_1.mp4` |
| `daf50286-Salamander_Video.mp4`   | `Salamander_Video.mp4`   |


### 2. Build YOLO dataset from JSON + videos

From the **repository root** (backend venv active):

```bash
python scripts/prepare_dataset.py \
  --export project-7-at-2026-05-25-18-33-901d5158.json \
  --videos-dir data/videos/raw \
  --out data/dataset \
  --clean
```

Each **keyframe** becomes one training image + `.txt` label. The script prints how many pairs were written — use that count in your write-up (**frames labeled** = number of images produced, not every frame of the video).

### 3. Train YOLO11n

```bash
python scripts/train.py --data data/dataset/dataset.yaml --name salamander_run1
```

Defaults: `yolo11n.pt`, `imgsz=320`, `batch=8`, `epochs=50`. Copy weights for the web app:

```bash
mkdir -p weights
cp runs/detect/salamander_run1/weights/best.pt weights/best.pt
```

### 4. Preview labels in the UI (optional, no YOLO)

Export JSON from Label Studio → in the web UI, upload the **same MP4** + attach the JSON → **Build playback from labels**. Set **Task id** (e.g. `67`) if multiple tasks match the filename.

---

## Inference tuning (environment variables)

Set before starting `uvicorn`:


| Variable          | Default                        | Effect                                                                                           |
| ----------------- | ------------------------------ | ------------------------------------------------------------------------------------------------ |
| `YOLO_DEVICE`     | auto (`0` if CUDA, else `cpu`) | Force GPU `0`, `cuda`, or `cpu`                                                                  |
| `YOLO_CONF`       | `0.1`                          | Detection confidence (Ultralytics default is `0.25`; lower helps weak detections on new footage) |
| `YOLO_IMGSZ`      | `320`                          | Inference size; should match training (`320`)                                                    |
| `YOLO_VID_STRIDE` | `1`                            | Run YOLO every Nth frame (`2` ≈ 2× faster; skipped frames hold the last box in playback)         |
| `YOLO_WEIGHTS`    | `weights/best.pt`              | Override weights path                                                                            |


Example:

```bash
export YOLO_CONF=0.3
export YOLO_IMGSZ=320
export YOLO_VID_STRIDE=2
export YOLO_DEVICE=0
```

### NVIDIA GPU on Windows

1. `nvidia-smi` — confirm the GPU is visible.
2. In `backend/.venv`:
  ```bash
   python -c "import torch; print(torch.__version__, torch.cuda.is_available())"
  ```
3. If you see `+cpu` and `False`, install CUDA PyTorch:
  ```bash
   pip uninstall -y torch torchvision
   pip install torch torchvision --index-url https://download.pytorch.org/whl/cu124
  ```
4. Restart uvicorn; `/api/health` should show `cuda_available: true`.

**CPU-only machines** (e.g. many laptops): use the normal `pip install -r requirements.txt` — no CUDA wheel required. Inference falls back to CPU automatically.

---

## Troubleshooting

### No bounding boxes after upload

1. Job status is `done` but boxes never appear — open `/api/jobs/{id}/tracks` and check whether `frames[*].tracks` are empty.
2. **Model mismatch** — `best.pt` may work on training frames but not on very different footage (lighting, angle, background). Test with `data/videos/raw/Salamander_Video_1.mp4` or use **Label Studio JSON** to verify the player.
3. **Low confidence** — lower `YOLO_CONF` (e.g. `0.05`), restart the server, and **re-upload** (old jobs keep old tracks).
4. **Sparse detections** — scrub the timeline; boxes only exist on frames where YOLO fired. The UI shows a warning banner when **zero** detections exist for the whole clip.

### `ModuleNotFoundError: No module named 'app'`

You are in `backend/` but passed `--app-dir backend`. Either:

- `uvicorn app.main:app --host 127.0.0.1 --port 8000` from `backend/`, **or**
- `uvicorn app.main:app --host 127.0.0.1 --port 8000 --app-dir backend` from the repo root.

### `Missing export file: my_export.json`

Use your real export filename, e.g. `project-7-at-2026-05-25-18-33-901d5158.json`, not a placeholder.

### Job polling returns 404

The server restarted and lost in-memory job IDs. Refresh the page and upload again. Completed jobs on disk may be **restored** on startup; interrupted runs show `error` with a restart message.

### Very slow processing

An 8-minute / 11k-frame clip on CPU can take **an hour or more**. Trim to 15–60 s for demos, use GPU, or set `YOLO_VID_STRIDE=2`.

---

## API overview


| Method | Path                    | Description                                                                            |
| ------ | ----------------------- | -------------------------------------------------------------------------------------- |
| GET    | `/api/health`           | Weights, PyTorch/CUDA info, `inference_device`                                         |
| POST   | `/api/jobs`             | Multipart: `file` (video), optional `labels` (JSON), optional `task_id` → `{ job_id }` |
| GET    | `/api/jobs/{id}`        | `status`, `percent` (0–100), optional `error`, `meta` when done                        |
| GET    | `/api/jobs/{id}/video`  | Input video for playback                                                               |
| GET    | `/api/jobs/{id}/tracks` | Per-frame boxes: `id`, `xyxy`, `conf`                                                  |


Job files: `backend/data/jobs/{job_id}/` (`input.`*, `tracks.json`, `meta.json`, optional `labelstudio_export.json`).

---

## Committing `best.pt` with Git LFS

```bash
git lfs install
git lfs track "*.pt"
git add .gitattributes weights/best.pt
git commit -m "Add trained salamander weights"
```

`.gitattributes` already lists `*.pt`; install LFS before committing large weights.

---

## Project layout


| Path                                                                                               | Role                                                       |
| -------------------------------------------------------------------------------------------------- | ---------------------------------------------------------- |
| `[backend/app/main.py](backend/app/main.py)`                                                       | FastAPI routes, background jobs, progress updates          |
| `[backend/app/process_video.py](backend/app/process_video.py)`                                     | YOLO `track()` → `tracks.json`; GPU/CPU device; env tuning |
| `[backend/app/labelstudio_import.py](backend/app/labelstudio_import.py)`                           | Label Studio JSON → interpolated `tracks.json`             |
| `[backend/app/jobs.py](backend/app/jobs.py)`                                                       | Job registry; restore jobs from disk after reload          |
| `[scripts/prepare_dataset.py](scripts/prepare_dataset.py)`                                         | Label Studio JSON + MP4s → YOLO dataset                    |
| `[scripts/train.py](scripts/train.py)`                                                             | Fine-tune YOLO11n                                          |
| `[frontend/src/App.tsx](frontend/src/App.tsx)`                                                     | Upload, polling, progress wheel                            |
| `[frontend/src/components/VideoPlayerOverlay.tsx](frontend/src/components/VideoPlayerOverlay.tsx)` | Video + canvas boxes / trail                               |
| `[frontend/src/components/ProgressWheel.tsx](frontend/src/components/ProgressWheel.tsx)`           | Circular progress indicator                                |
| `[weights/best.pt](weights/best.pt)`                                                               | Trained weights (you add via LFS)                          |


---

## License

Use for course / research demos; adjust as needed for your institution.