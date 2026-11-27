# PyInstaller spec for the standalone MemoFrame CLI engine.
# Build from repository root:
#   python -m PyInstaller --noconfirm packaging/pyinstaller/cli.spec
# Result: dist/photo_engine/photo_engine.exe

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
]

try:
    d, b, h = collect_all("pillow_heif")
    datas += d
    binaries += b
    hiddenimports += h
except Exception:
    pass

a = Analysis(
    [str(Path(SPECPATH) / "cli_entry.py")],
    pathex=[str(ENGINE_ROOT)],
    datas=datas,
    binaries=binaries,
    hiddenimports=hiddenimports,
    excludes=["tkinter", "matplotlib", "IPython", "pytest"],
)
pyz = PYZ(a.pure)
exe = EXE(pyz, a.scripts, [], exclude_binaries=True, name="photo_engine", console=True)
coll = COLLECT(exe, a.binaries, a.datas, name="photo_engine")
