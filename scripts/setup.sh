#!/usr/bin/env bash
# First-time environment setup for SallyTracker (Python backend + Node frontend).
# Run from the repository root:
#   chmod +x scripts/setup.sh && ./scripts/setup.sh
#
# macOS / Linux: uses backend/.venv and bin/activate
# Windows (Git Bash): same paths; activate is backend/.venv/Scripts/activate

set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

SKIP_NPM=0
for arg in "$@"; do
  case "$arg" in
    --skip-npm) SKIP_NPM=1 ;;
    -h|--help)
      echo "Usage: ./scripts/setup.sh [--skip-npm]"
      echo "  Creates backend/.venv, installs Python deps, runs npm install in frontend/."
      exit 0
      ;;
  esac
done

echo "==> SallyTracker first-time setup (root: $ROOT)"

if ! command -v python3 >/dev/null 2>&1; then
  echo "Error: python3 not found. Install Python 3.10+ and try again." >&2
  exit 1
fi

PYVER="$(python3 -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')"
echo "    Using Python $PYVER at $(command -v python3)"

VENV="$ROOT/backend/.venv"
if [[ ! -d "$VENV" ]]; then
  echo "==> Creating virtualenv: $VENV"
  python3 -m venv "$VENV"
else
  echo "==> Virtualenv already exists: $VENV"
fi

if [[ -f "$VENV/bin/activate" ]]; then
  # shellcheck source=/dev/null
  source "$VENV/bin/activate"
elif [[ -f "$VENV/Scripts/activate" ]]; then
  # shellcheck source=/dev/null
  source "$VENV/Scripts/activate"
else
  echo "Error: could not find activate script under $VENV" >&2
  exit 1
fi

echo "==> Upgrading pip"
python -m pip install --upgrade pip

echo "==> Installing backend dependencies"
python -m pip install -r "$ROOT/backend/requirements.txt"

if [[ "$SKIP_NPM" -eq 0 ]]; then
  if ! command -v npm >/dev/null 2>&1; then
    echo "Warning: npm not found; skipping frontend install. Install Node.js 20+ and re-run without --skip-npm." >&2
  else
    echo "==> Installing frontend dependencies (npm install)"
    (cd "$ROOT/frontend" && npm install)
  fi
else
  echo "==> Skipping npm (--skip-npm)"
fi

echo ""
echo "Setup finished."
echo ""
echo "Next — start the backend (from repo root):"
echo "  source backend/.venv/bin/activate          # Windows Git Bash: source backend/.venv/Scripts/activate"
echo "  uvicorn app.main:app --host 127.0.0.1 --port 8000 --app-dir backend"
echo ""
echo "Next — start the frontend (separate terminal):"
echo "  cd frontend && npm run dev"
echo ""
echo "Optional — train a model (videos + Label Studio JSON export required):"
echo "  python scripts/prepare_dataset.py --export modelSettings.json --videos-dir data/videos/raw --clean"
echo "  python scripts/train.py --name salamander_run1"
echo "  cp runs/detect/salamander_run1/weights/best.pt weights/best.pt"
echo ""
echo "Weights tips:"
echo "  - If weights/best.pt is a tiny Git LFS pointer, run: git lfs pull  (or copy a real .pt from training)"
echo "  - For a quick YOLO smoke test without training: export YOLO_WEIGHTS=yolo11n.pt  (Ultralytics downloads it)"
