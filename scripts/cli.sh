#!/usr/bin/env bash
set -euo pipefail
ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
export PYTHONPATH="$ROOT_DIR/services/engine:${PYTHONPATH:-}"
python3 -m memoframe_engine.cli.cli "$@"
