"""Download hash-verified AppImage tooling and runtime license texts."""
import hashlib
import json
import sys
import urllib.request
from pathlib import Path

root = Path(__file__).resolve().parents[1]
target = Path(sys.argv[1])
target.mkdir(parents=True, exist_ok=True)
for name, info in json.loads((root / 'packaging/appimage/toolchain.json').read_text()).items():
    path = target / name
    if not path.is_file() or hashlib.sha256(path.read_bytes()).hexdigest() != info['sha256']:
        request = urllib.request.Request(info['url'], headers={'User-Agent': 'DuplicateFinder-build'})
        with urllib.request.urlopen(request, timeout=120) as response:
            data = response.read()
        if hashlib.sha256(data).hexdigest() != info['sha256']:
            raise SystemExit(f'SHA-256 mismatch for {name}; review and repin toolchain.json')
        path.write_bytes(data)
    path.chmod(0o644 if name.endswith('-license') else 0o755)
    print(f'Verified {name}')
