# SallyTracker — Salamander video tracker

Full-stack demo: upload a short salamander clip, run **Ultralytics YOLO** tracking on a **FastAPI** backend, then play the video in a **React (Vite)** UI with bounding boxes, a **path trail**, **live center coordinates**, and a **detection count vs time** chart.

## How to run

### Prerequisites

- Python 3.11+ recommended  
- Node 20+  
- **Either** a YOLO weights file at **`weights/best.pt`** (or `YOLO_WEIGHTS` pointing at any `.pt` for wiring tests), **or** a **Label Studio JSON** export with `videorectangle` annotations (see below) so you can preview labels **without** running YOLO.

### Label Studio JSON (no `best.pt` required)

Export your project as **JSON** (tasks with `videorectangle` results). In the web UI, pick the same video file you annotated, attach the JSON, and click **Build playback from labels**. The backend matches the upload to a task by filename (e.g. your `Salamander_Video_1.mp4` matches `86128414-Salamander_Video_1.mp4` in the export). If several tasks could match, set **Task id** to the Label Studio task id (for example `67`).

This path **interpolates** sparse keyframes to every frame, writes the same `tracks.json` shape the player already uses, and sets `meta.model_path` to `label_studio_import`. **Rotated** boxes are approximated as **axis-aligned** rectangles in percent space (rotation is ignored). **CSV** exports are not supported here; use JSON.

This is **not** a substitute for training: it only visualizes what you already labeled. For automatic detection on new footage you still need a trained `best.pt` (or another weights file).

### Backend

```bash
cd /path/to/SallyTracker
python3 -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r backend/requirements.txt
uvicorn app.main:app --reload --host 127.0.0.1 --port 8000 --app-dir backend
```

Health check: [http://127.0.0.1:8000/api/health](http://127.0.0.1:8000/api/health) reports whether the weights file exists.

### Frontend

```bash
cd frontend
npm install
npm run dev
```

Open [http://127.0.0.1:5173](http://127.0.0.1:5173). The Vite dev server **proxies** `/api` to the backend on port 8000.

### Committing `best.pt` with Git LFS

YOLO weights are large. After training, install [Git LFS](https://git-lfs.com/), then:

```bash
git lfs install
git lfs track "*.pt"
git add .gitattributes weights/best.pt
```

The repo already includes a `.gitattributes` rule for `*.pt`; ensure LFS is installed before committing weights.

---

## Dataset and training pipeline

This project includes an example **Label Studio export** in [`modelSettings.json`](modelSettings.json) (tasks with `videorectangle` annotations: keyframed boxes in percent of frame width/height, with `frame` indices and `labels: ["Salamander"]`). That file reflects **two labeled videos** (`86128414-Salamander_Video_1.mp4` and `daf50286-Salamander_Video.mp4` in the export metadata). The sequences are **sparse keyframes**; the prep script turns **each keyframe into one training image** with a YOLO label line per object track (axis-aligned box; Label Studio **rotation is ignored**, same as the in-app import).

### 1. Put your source MP4s on disk

Copy the actual video files into **`data/videos/raw/`** using either the exact `file_upload` name from the export or the suffix after the first hyphen (e.g. `Salamander_Video_1.mp4` for `86128414-Salamander_Video_1.mp4`).

### 2. Build `data/dataset/` from the JSON

From the **repository root** (with the same virtualenv as the backend, so `opencv-python-headless` and `ultralytics` are installed):

```bash
python scripts/prepare_dataset.py --export modelSettings.json --videos-dir data/videos/raw --out data/dataset
```

Use **`--clean`** to wipe existing `data/dataset/images` and `data/dataset/labels` before regenerating. The script writes **`data/dataset/dataset.yaml`** with an absolute `path:` so training works regardless of current working directory.

**Frames labeled (for your write-up):** the number of **images** produced equals the number of **unique keyframe indices** across tasks (multiple `videorectangle` tracks on the same frame become multiple lines in one `.txt` file). With the checked-in export and both videos present, that is **39** images (26 keyframes on task 67 + 13 on task 68).

### 3. Train YOLO11n

```bash
python scripts/train.py
```

Defaults match the bundled trainer: **`yolo11n.pt`**, **`imgsz=320`**, **`batch=8`**, **`epochs=50`**, augment flags as in [`scripts/train.py`](scripts/train.py). Weights and logs are written under **`runs/detect/<name>/`** (see `--name`, default `run1`). Copy the trained file to the web app:

```bash
cp runs/detect/run1/weights/best.pt weights/best.pt
```

If `yolo11n.pt` is not found, upgrade Ultralytics (`pip install -U ultralytics`) or pass **`--model yolov8n.pt`** (or another checkpoint) to `scripts/train.py`.

The web app uses `model.track(..., persist=True)` so displayed **track IDs** are stable enough for short clips; occlusions can still cause ID switches.

---

## Color masking vs YOLO

**Color masking** (thresholding in HSV/Lab, background subtraction, or hand-tuned rules) is fast, lightweight, and easy to debug when the salamander’s color is distinct, lighting is stable, and the background is simple. It falls apart quickly with mud, glare, shadows, similar-colored debris, partial occlusion, or compression noise. **YOLO** (especially after fine-tuning on your own frames) learns appearance and context, handles clutter and variable lighting better, and gives you a standard box format for downstream metrics—at the cost of labeling effort, training time, and heavier runtime (GPU helps). A practical approach for field footage is to use **YOLO for detection** and, only in very controlled lab setups, optionally refine with a mask if the scene is genuinely color-stable.

---

## API overview

| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/health` | Service and weights path check |
| POST | `/api/jobs` | Multipart: **`file`** (video, required), optional **`labels`** (Label Studio JSON), optional form field **`task_id`** (integer) → `{ job_id }`. If `labels` is present, YOLO is skipped and tracks are built from `videorectangle` keyframes. |
| GET | `/api/jobs/{id}` | `pending` \| `running` \| `done` \| `error` |
| GET | `/api/jobs/{id}/video` | Processed input video for playback |
| GET | `/api/jobs/{id}/tracks` | JSON: per-frame boxes, confidences, track ids |

Job files live under `backend/data/jobs/` (gitignored).

---

## Project layout

- [`backend/app/main.py`](backend/app/main.py) — FastAPI routes, CORS, background jobs  
- [`backend/app/process_video.py`](backend/app/process_video.py) — Ultralytics `track()` → `tracks.json`  
- [`backend/app/labelstudio_import.py`](backend/app/labelstudio_import.py) — Label Studio JSON → interpolated `tracks.json`  
- [`scripts/prepare_dataset.py`](scripts/prepare_dataset.py) — Label Studio JSON + MP4s → YOLO `images/` + `labels/` + `dataset.yaml`  
- [`scripts/train.py`](scripts/train.py) — Fine-tune **YOLO11n** (or `--model`) on the prepared dataset  
- [`frontend/`](frontend/) — React UI, canvas overlay, metrics  

---

## License

Use for course / research demos; adjust as needed for your institution.
