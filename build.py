#!/usr/bin/env python3
"""Build a native executable; --onedir is used by AppImage packaging."""
import argparse
import os
import subprocess
import sys
from pathlib import Path


def main():
    root = Path(__file__).resolve().parent
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--onedir', action='store_true')
    parser.add_argument('--distpath', type=Path, default=root / 'dist')
    parser.add_argument('--workpath', type=Path, default=root / 'build')
    args = parser.parse_args()
    env = dict(os.environ, DF_BUILD_MODE='onedir' if args.onedir else 'onefile',
               DF_BUILD_ROOT=str(args.workpath.resolve()))
    subprocess.run([sys.executable, '-m', 'pip', 'check'], check=True)
    subprocess.run([sys.executable, '-m', 'PyInstaller', '--noconfirm', '--clean',
                    '--distpath', str(args.distpath), '--workpath', str(args.workpath / 'work'),
                    str(root / 'DuplicateFinder.spec')], env=env, cwd=root, check=True)
    print('Built executable in', args.distpath)


if __name__ == '__main__':
    main()
