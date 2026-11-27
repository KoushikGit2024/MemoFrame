#!/usr/bin/env bash
set -euo pipefail
ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
export MEMOFRAME_ENGINE_DIR="$ROOT_DIR/services/engine"
cd "$ROOT_DIR/apps/desktop"
if [ ! -d node_modules ]; then
  npm install
fi
if [ "${1:-}" = "--build" ]; then
  npm start
else
  npm run dev
fi
