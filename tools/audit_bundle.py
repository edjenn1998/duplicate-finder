"""Inspect all ELF requirements and reject incomplete native/Tcl/Tk bundles."""
import argparse
import json
import os
import re
import struct
import subprocess
from pathlib import Path


def audit(root):
    root = Path(root)
    internal = root / '_internal'
    errors, files, architectures = [], [], set()
    for pattern in ('libtcl*.so*', 'libtk*.so*'):
        if not any(internal.glob(pattern)):
            errors.append(f'Missing bundled Tcl/Tk shared library: {pattern}')
    for relative in ('_tcl_data/init.tcl', '_tk_data/tk.tcl'):
        if not (internal / relative).is_file():
            errors.append(f'Missing Tcl/Tk runtime data: {relative}')
    for path in sorted(root.rglob('*')):
        if not path.is_file() or path.is_symlink():
            continue
        try:
            with path.open('rb') as f:
                header = f.read(20)
            if header[:4] != b'\x7fELF':
                continue
            machine = struct.unpack(('<' if header[5] == 1 else '>') + 'H', header[18:20])[0]
            architectures.add({62: 'x86_64', 183: 'aarch64'}.get(machine, f'ELF-machine-{machine}'))
            text = subprocess.check_output(['readelf', '--version-info', str(path)], text=True)
            versions = [tuple(map(int, version.split('.'))) for version in re.findall(r'Name: GLIBC_(\d+(?:\.\d+)+)', text)]
            files.append({'file': str(path.relative_to(root)), 'minimum_glibc': '.'.join(map(str, max(versions))) if versions else ''})
            result = subprocess.run(['ldd', str(path)], capture_output=True, text=True,
                                    env=dict(os.environ, LD_LIBRARY_PATH=str(internal.resolve())))
            text = result.stdout + result.stderr
            if 'not found' in text or (result.returncode and 'not a dynamic executable' not in text and 'statically linked' not in text):
                errors.append(f'{path.relative_to(root)}: {text.strip()}')
        except (OSError, subprocess.SubprocessError, IndexError, struct.error) as exc:
            errors.append(f'{path}: {exc}')
    versions = [tuple(map(int, item['minimum_glibc'].split('.'))) for item in files if item['minimum_glibc']]
    return {'architecture': ', '.join(sorted(architectures)),
            'minimum_glibc': '.'.join(map(str, max(versions))) if versions else '',
            'elf_files_checked': len(files), 'errors': errors, 'files': files,
            'limitations': 'Symbol/dependency audit, not a guarantee of compatibility with every desktop or distribution.'}


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('directory', type=Path)
    parser.add_argument('--max-glibc', default='2.35')
    args = parser.parse_args()
    report = audit(args.directory)
    print(json.dumps(report, indent=2))
    if report['errors'] or not report['minimum_glibc']:
        raise SystemExit(1)
    if tuple(map(int, report['minimum_glibc'].split('.'))) > tuple(map(int, args.max_glibc.split('.'))):
        raise SystemExit(1)
