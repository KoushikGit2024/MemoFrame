#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PY_EXE="python3"
for cand in "$ROOT_DIR/.venv/bin/python" "$ROOT_DIR/venv/bin/python" "$ROOT_DIR/backend/.venv/bin/python"; do
  if [[ -x "$cand" ]]; then
    PY_EXE="$cand"
    break
  fi
done

echo "[1/3] Running backend pytest suite..."
(cd "$ROOT_DIR/backend" && "$PY_EXE" -m pytest)

echo "[2/3] Running bridge pytest suite..."
PYTHONPATH="$ROOT_DIR:$ROOT_DIR/backend:${PYTHONPATH:-}" "$PY_EXE" -m pytest "$ROOT_DIR/bridge/tests"

echo "[3/3] Running Electron TSX typecheck..."
if [[ -d "$ROOT_DIR/frontElectron/node_modules" ]]; then
  (cd "$ROOT_DIR/frontElectron" && npm run typecheck)
else
  echo "Skipping npm run typecheck (frontElectron/node_modules not installed yet)."
fi
