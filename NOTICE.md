# Third-party notices

Duplicate Finder's original application code is copyright (C) 2026 Edwin Combs
and licensed under **GPL-3.0-or-later**. See LICENSE and source file headers.

Current release builds generate license texts from the actual installed Python
distributions and bundled system packages. The AppImage contains these notices
under `usr/share/duplicate-finder/licenses/`, plus exact Python/native inventories.

- Python: Python Software Foundation license and included third-party notices;
  https://www.python.org/downloads/source/
- Tcl/Tk: Tcl/Tk licenses, with system-package copyright notices included;
  https://www.tcl-lang.org/software/tcltk/
- Pillow: HPND and included codec licenses; https://python-pillow.org/
- Send2Trash: BSD license; https://github.com/arsenetar/send2trash
- PyInstaller: GPL with distribution exception; https://pyinstaller.org/
- AppImage static runtime: MIT, with musl, libfuse, squashfuse, zstd and zlib
  components; https://github.com/AppImage/type2-runtime. Runtime and component
  license texts are hash-verified and included in the package. Corresponding
  source/build instructions are in that project's BUILD.md.

Native GPU/display drivers remain provided by the user's operating system.
The build scripts, pinned tooling hashes and tagged application source permit
rebuilding with replacement dependency versions. Third-party components retain
their respective licenses.
