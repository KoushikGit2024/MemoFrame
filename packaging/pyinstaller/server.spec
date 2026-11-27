# PyInstaller spec for MemoFrame's NDJSON-RPC server + Python engine.
# Build from apps/desktop/:
#   python -m PyInstaller --noconfirm --distpath build-backend --workpath build-backend-work ../../packaging/pyinstaller/server.spec
# Result: apps/desktop/build-backend/server/server.exe

from pathlib import Path
from PyInstaller.utils.hooks import collect_all

REPO_ROOT = Path(SPECPATH).resolve().parents[1]
ENGINE_ROOT = REPO_ROOT / "services" / "engine"
PKG_ROOT = ENGINE_ROOT / "memoframe_engine"

datas = [
    (str(PKG_ROOT / "db" / "schema.sql"), "memoframe_engine/db"),
]
binaries = []
hiddenimports = [
    "sklearn.utils._typedefs",
    "sklearn.neighbors._partition_nodes",
    "memoframe_engine.rpc.handlers.collections",
    "memoframe_engine.rpc.handlers.library",
    "memoframe_engine.rpc.handlers.people",
    "memoframe_engine.rpc.handlers.system",
    "memoframe_engine.rpc.handlers.analytics",
    "memoframe_engine.rpc.handlers.errors",
    "memoframe_engine.core.observability",
    "memoframe_engine.rpc.prefs",
    "memoframe_engine.rpc.progress",
    "memoframe_engine.rpc.protocol",
]

try:
    d, b, h = collect_all("pillow_heif")
    datas += d
    binaries += b
    hiddenimports += h
except Exception:
    pass

a = Analysis(
    [str(PKG_ROOT / "rpc" / "server.py")],
    pathex=[str(ENGINE_ROOT)],
    datas=datas,
    binaries=binaries,
    hiddenimports=hiddenimports,
    excludes=["tkinter", "matplotlib", "IPython", "pytest"],
)
pyz = PYZ(a.pure)
exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="server",
    console=True,
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    name="server",
)
