# Build (from the project root):  pyinstaller packaging/engine.spec --noconfirm
# Result: dist/photo_engine/photo_engine.exe   (one-folder build; faster start than one-file)
from pathlib import Path
from PyInstaller.utils.hooks import collect_all

ROOT = Path(SPECPATH).parent
datas = [(str(ROOT / "src" / "memoframe" / "database" / "schema.sql"), "database"),
         (str(ROOT / "src" / "memoframe" / "database" / "schema.sql"), "memoframe/database")]
binaries, hiddenimports = [], ["sklearn.utils._typedefs", "sklearn.neighbors._partition_nodes"]
try:
    d, b, h = collect_all("pillow_heif")
    datas += d; binaries += b; hiddenimports += h
except Exception:
    pass
model = ROOT / "models" / "face_detection_yunet_2023mar.onnx"   # optional: ship it
if model.is_file():
    datas.append((str(model), "models"))

a = Analysis([str(ROOT / "packaging" / "engine_entry.py")],
             pathex=[str(ROOT), str(ROOT / "src"), str(ROOT / "src" / "memoframe")],
             datas=datas, binaries=binaries, hiddenimports=hiddenimports,
             excludes=["tkinter", "matplotlib", "IPython", "pytest"])
pyz = PYZ(a.pure)
exe = EXE(pyz, a.scripts, [], exclude_binaries=True, name="photo_engine", console=True)
coll = COLLECT(exe, a.binaries, a.datas, name="photo_engine")
