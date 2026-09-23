# PyInstaller build recipe:  pyinstaller sayso.spec
from PyInstaller.utils.hooks import collect_data_files, collect_dynamic_libs, collect_submodules

datas = collect_data_files("faster_whisper")          # includes the VAD model it needs
datas += collect_data_files("customtkinter")
datas += [("sayso/sayso.ico", "sayso")]
binaries = collect_dynamic_libs("ctranslate2") + collect_dynamic_libs("onnxruntime")  # onnxruntime: VAD
hidden = collect_submodules("pystray") + collect_submodules("pynput") + ["sounddevice"]

a = Analysis(
    ["sayso/__main__.py"],
    pathex=["."],
    datas=datas,
    binaries=binaries,
    hiddenimports=hidden,
    excludes=["matplotlib", "pandas", "scipy.spatial.cKDTree", "IPython", "pytest"],
)
pyz = PYZ(a.pure)
exe = EXE(
    pyz, a.scripts, [],
    exclude_binaries=True,
    name="Sayso",
    icon="sayso/sayso.ico",
    console=False,          # no black window
    version="installer/version_info.txt",
)
coll = COLLECT(exe, a.binaries, a.datas, name="Sayso")
