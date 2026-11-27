#!/usr/bin/env bash
set -euo pipefail
ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
echo "[1/2] Running Python engine and RPC pytest suite..."
(cd "$ROOT_DIR/services/engine" && python3 -m pytest tests)
echo "[2/2] Running Desktop TypeScript typecheck..."
(cd "$ROOT_DIR/apps/desktop" && [ -d node_modules ] && npm run typecheck)
