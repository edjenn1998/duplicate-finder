# Building and verifying an AppImage

See [README.md](README.md) for download/run instructions and the no-FUSE fallback.

## Official release environment

- Ubuntu 22.04, x86_64, Python **3.12.15**.
- Exact Python dependencies in `requirements-build.txt`.
- Updated distribution Tcl/Tk and display libraries; exact bundled versions are
  recorded in `native-packages.txt`.
- Hash-verified AppImage tool/static runtime/license texts from
  `packaging/appimage/toolchain.json`.

This is a documented, repeatable build process, not a promise of bit-identical
output across OS updates. Changing a dependency requires a new audit and test run.

```sh
sudo apt-get update
sudo apt-get install tk tcl python3-tk xvfb xauth binutils desktop-file-utils fonts-dejavu-core
# Supply Python 3.12.15; Ubuntu 22.04 does not include it by default.
# GitHub Actions uses actions/setup-python.
python3.12 -m venv .venv-build
. .venv-build/bin/activate
python -m pip install -r requirements-build.txt
python DuplicateFinder.py --self-test
xvfb-run -a python -m unittest discover -s tests -v
DF_PYTHON="$PWD/.venv-build/bin/python" \
DF_BUILD_ROOT=/tmp/duplicate-finder-build \
bash packaging/appimage/build-appimage.sh
```

Use a clean environment and an unused build directory. No FUSE package is needed
for building or testing: the build tool is extracted and the final AppImage is
tested in extraction mode. The runtime is statically linked, avoiding the old
libfuse2 dependency. Kernel-restricted environments can also run via extraction.

The continuous upstream tool URLs can change. A checksum mismatch stops the build;
review the upstream change and deliberately repin the recorded SHA-256 hashes.

## Verification and outputs

The script builds an inspectable onedir app through `DuplicateFinder.spec`, checks
Tcl/Tk script/shared-library presence, runs `readelf` and `ldd` on every bundled ELF
file, collects actual dependency licenses, and tests engine plus real GUI behavior
both before and after AppImage packaging. Engine tests never use real user data;
GUI tests only move generated files within a disposable temporary directory.

Official builds reject a glibc requirement above **2.35**. `DF_MAX_GLIBC` can be
overridden for local native builds on newer systems, but that does not make them
compatible with older distributions. Failed/incomplete audits are errors.

The following are created under `dist/`:

- `DuplicateFinder-1.3.0-x86_64.AppImage`
- `SHA256SUMS`
- `abi-audit.json`
- `python-dependencies.txt`
- `native-packages.txt`

Current application/Python/native/runtime notices and inventories are included
under `usr/share/duplicate-finder/` inside the AppImage. The ABI report audits the
payload; the appended static runtime has no glibc dependency. Symbol compatibility
alone does not guarantee operation on every desktop/distribution.

## Publishing

The GitHub workflow uploads a `DuplicateFinder-Linux-x86_64` artifact only after
tests and the packaged GUI pass. Download the successful artifact, check hashes,
and test on a separate machine with clean library paths. Tag the exact tested
source commit and upload the five generated files as release assets. Preserve
older releases. Generated binaries do not belong in Git history.
