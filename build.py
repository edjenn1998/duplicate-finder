#!/usr/bin/env python3
"""Build a single executable on the target OS. Install requirements-build.txt first."""
import subprocess
import sys
from pathlib import Path

root = Path(__file__).resolve().parent
args = [sys.executable, "-m", "PyInstaller", "--noconfirm", "--clean",
        "--onefile", "--windowed", "--name", "DuplicateFinder",
        "--distpath", str(root / "dist"), "--workpath", str(root / "build"),
        "--specpath", str(root / "build"),
        "--collect-all", "send2trash", "--hidden-import", "PIL.ImageTk"]
# Some standalone Python distributions keep Tcl/Tk shared libraries outside
# the system loader's search path. Include those when present.
if sys.platform.startswith("linux"):
    libdir = Path(sys.base_prefix) / "lib"
    for pattern in ("libtcl[89]*.so", "libtcl[89]tk*.so", "libtk[89]*.so"):
        for library in sorted(libdir.glob(pattern)):
            args += ["--add-binary", str(library) + ":."]
args.append(str(root / "DuplicateFinder.py"))
subprocess.run(args, cwd=root, check=True)
print("Built executable in", root / "dist")
