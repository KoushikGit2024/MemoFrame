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

cd "$ROOT_DIR/backend"
exec "$PY_EXE" cli.py "$@"
