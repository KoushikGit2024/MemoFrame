#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
export MEMOFRAME_BACKEND_DIR="$ROOT_DIR/backend"

for cand in "$ROOT_DIR/.venv/bin/python" "$ROOT_DIR/venv/bin/python" "$ROOT_DIR/backend/.venv/bin/python"; do
  if [[ -x "$cand" ]]; then
    export MEMOFRAME_PYTHON="$cand"
    break
  fi
done

cd "$ROOT_DIR/frontElectron"
if [[ ! -d node_modules ]]; then
  echo "[MemoFrame] Installing Electron frontend dependencies..."
  npm install
fi

if [[ "${1:-}" == "--build" ]]; then
  npm start
elif [[ "${1:-}" == "--test" ]]; then
  npm run typecheck
else
  npm run dev
fi
