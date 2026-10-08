# PyInstaller recipe: bundles Python and all libraries into dist/Verbalis/.
#
#   pyinstaller packaging/verbalis.spec --noconfirm
#
# Produces two programs sharing one set of libraries:
#   Verbalis.exe      the app, without console window (target of the shortcut)
#   verbalis-cli.exe  the command line (different name: Windows ignores case)
#
# Models are not bundled – they are downloaded or converted on first use.
# pylint: disable=undefined-variable  (Analysis, PYZ, EXE, COLLECT come from PyInstaller)
import sys
from pathlib import Path

from PyInstaller.utils.hooks import collect_data_files, collect_dynamic_libs, collect_submodules

ROOT = Path(SPECPATH).parent
ICON = str(ROOT / "src" / "verbalis" / "ui" / "verbalis.ico")
EXT = ".exe" if sys.platform == "win32" else ""

datas = [(str(ROOT / "src" / "verbalis" / "ui"), "verbalis/ui")]
datas += collect_data_files("faster_whisper")   # Silero VAD model for the silence filter
datas += collect_data_files("soundcard")        # C headers that soundcard reads at runtime (cffi)
binaries = collect_dynamic_libs("ctranslate2") + collect_dynamic_libs("soxr")

a = Analysis(
    [str(ROOT / "packaging" / "verbalis_app.py"), str(ROOT / "packaging" / "verbalis_cli.py")],
    pathex=[str(ROOT / "src")],
    binaries=binaries,
    datas=datas,
    hiddenimports=collect_submodules("verbalis") + ["soundcard", "soxr", "faster_whisper"],
    # only needed to convert models (`pip install -e ".[convert]"`), far too big for the installer
    excludes=["torch", "transformers", "accelerate", "tkinter", "matplotlib", "IPython", "pytest"],
    noarchive=False,
)
pyz = PYZ(a.pure)


def scripts_for(name: str):
    """Runtime hooks plus exactly one of our two entry scripts."""
    own = {"verbalis_app", "verbalis_cli"}
    return [s for s in a.scripts if s[0] not in own or s[0] == name]


app = EXE(pyz, scripts_for("verbalis_app"), [], exclude_binaries=True, name="Verbalis",
          console=False, icon=ICON, upx=False)
cli = EXE(pyz, scripts_for("verbalis_cli"), [], exclude_binaries=True, name="verbalis-cli",
          console=True, icon=ICON, upx=False)
coll = COLLECT(app, cli, a.binaries, a.datas, name="Verbalis", upx=False)
