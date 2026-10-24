"""Shared onedir/AppImage and standalone executable build."""
import json
import os
from pathlib import Path
from PyInstaller.utils.hooks import collect_all

project = Path(SPECPATH)
build_root = Path(os.environ.get('DF_BUILD_ROOT', str(project / 'build')))
pil_data, pil_binaries, pil_hidden = collect_all('PIL')
trash_data, trash_binaries, trash_hidden = collect_all('send2trash')
a = Analysis(
    [str(project / 'DuplicateFinder.py')], pathex=[str(project)],
    binaries=pil_binaries + trash_binaries,
    datas=pil_data + trash_data + [(str(project / 'LICENSE'), '.')],
    hiddenimports=pil_hidden + trash_hidden + ['PIL.ImageTk'],
    noarchive=False,
)
build_root.mkdir(parents=True, exist_ok=True)
(build_root / 'native-sources.json').write_text(json.dumps([item[1] for item in a.binaries], indent=2))
pyz = PYZ(a.pure)
if os.environ.get('DF_BUILD_MODE') == 'onedir':
    exe = EXE(pyz, a.scripts, [], exclude_binaries=True, name='DuplicateFinder',
              debug=False, strip=False, upx=False, console=True)
    coll = COLLECT(exe, a.binaries, a.datas, strip=False, upx=False, name='DuplicateFinder')
else:
    exe = EXE(pyz, a.scripts, a.binaries, a.datas, [], name='DuplicateFinder',
              debug=False, strip=False, upx=False, console=False)
