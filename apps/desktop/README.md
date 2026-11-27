# MemoFrame Desktop (Electron + React + TypeScript + Vite + Tailwind CSS)

Offline-first desktop frontend for **MemoFrame — Local Photo & Face Intelligence**, built with **Electron + React + TypeScript (TSX) + Vite + Tailwind CSS** and a stdlib-only Python NDJSON-RPC stdio bridge.

## Architecture

- `electron/` — Main process, secure context-isolated preload, `memoframe-media://` local file protocol, IPC handlers, and Python bridge subprocess manager.
- `bridge/` — Stdlib-only Python NDJSON-RPC server wrapping `../backend`'s `Engine` with 100% API parity and zero open network ports.
- `src/` — Strictly typed React TSX + Tailwind CSS UI (`types/`, `lib/`, `context/`, `components/`, `views/`, `modals/`) using crisp `lucide-react` SVG icons (zero emojis, zero gradients).
- `tests/` — Deterministic `pytest` bridge tests.

## Quick Start

1. Place this folder alongside your `backend/` directory (same sibling layout as the original `frontend/` folder: `../backend`), or set `MEMOFRAME_BACKEND_DIR=/path/to/backend`.
2. Install Node dependencies:
   ```bash
   npm install
   ```
3. Run in development mode (Vite HMR + Electron):
   ```bash
   npm run dev
   ```
   Or typecheck, build, and run production bundle:
   ```bash
   npm run typecheck
   npm start
   ```

### Optional Environment Variables

- `MEMOFRAME_PYTHON` — Python interpreter path with backend dependencies installed (defaults to `python3` / `python`).
- `MEMOFRAME_BACKEND_DIR` — Path to your Python `backend/` directory (defaults to `../backend`).
- `MEMOFRAME_WORKSPACE` — Override the workspace directory (defaults to `config.DEFAULT_WORKSPACE`).

## Tests

```bash
npm run typecheck
pytest
```
