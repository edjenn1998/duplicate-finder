"""Collect license texts and exact inventories from the release build environment."""
import importlib.metadata
import json
import shutil
import subprocess
import sys
import sysconfig
from pathlib import Path


def collect(destination, manifest):
    root = Path(__file__).resolve().parents[1]
    destination.mkdir(parents=True, exist_ok=True)
    licenses = destination / 'licenses'
    licenses.mkdir(exist_ok=True)
    for name in ('LICENSE', 'NOTICE.md'):
        shutil.copyfile(root / name, destination / name)
    python_license = Path(sysconfig.get_path('stdlib')) / 'LICENSE.txt'
    if not python_license.is_file():
        raise RuntimeError('Missing Python runtime license')
    shutil.copyfile(python_license, licenses / 'Python-LICENSE.txt')
    records = []
    copied = set()
    for dist in sorted(importlib.metadata.distributions(), key=lambda d: d.metadata['Name'].lower()):
        records.append(f"{dist.metadata['Name']}=={dist.version}")
        for member in dist.files or []:
            if '..' in member.parts or not any(part.lower().startswith(('license', 'copying', 'notice')) for part in member.parts):
                continue
            source = Path(dist.locate_file(member))
            if source.is_file():
                out = licenses / 'python-packages' / f"{dist.metadata['Name']}-{dist.version}" / member
                out.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(source, out)
                copied.add(dist.metadata['Name'].lower())
    for name in ('pillow', 'send2trash'):
        if name not in copied:
            raise RuntimeError(f'Missing license text for {name}')
    (destination / 'python-dependencies.txt').write_text('\n'.join(records) + '\n')
    (destination / 'python-runtime.txt').write_text(sys.version + '\n')
    packages = set()
    for source in json.loads(Path(manifest).read_text()):
        path = Path(source)
        if not str(path).startswith(('/usr/lib/', '/lib/')):
            continue
        candidates = {str(path), str(path.resolve())}
        candidates.update(p.replace('/usr/lib/', '/lib/', 1) for p in list(candidates))
        for candidate in candidates:
            result = subprocess.run(['dpkg-query', '-S', candidate], capture_output=True, text=True)
            if not result.returncode:
                packages.update(line.rsplit(': ', 1)[0] for line in result.stdout.splitlines())
                break
    # The Tcl/Tk script libraries have their own package copyright records too.
    for path in ('/usr/share/tcltk/tcl8.6/init.tcl', '/usr/share/tcltk/tk8.6/tk.tcl'):
        result = subprocess.run(['dpkg-query', '-S', path], capture_output=True, text=True)
        if not result.returncode:
            packages.update(line.rsplit(': ', 1)[0] for line in result.stdout.splitlines())
    for package in sorted(packages):
        name = package.split(':', 1)[0]
        source = Path('/usr/share/doc') / name / 'copyright'
        if not source.is_file():
            raise RuntimeError(f'Missing native license for {package}')
        out = licenses / 'system-packages' / name / 'copyright'
        out.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, out)
    inventory = subprocess.check_output(['dpkg-query', '-W', '-f=${Package}=${Version}\\n', *sorted(packages)], text=True) if packages else ''
    (destination / 'native-packages.txt').write_text(inventory)
    print(f'Collected notices for {len(records)} Python distributions and {len(packages)} native packages')


if __name__ == '__main__':
    collect(Path(sys.argv[1]), sys.argv[2])
