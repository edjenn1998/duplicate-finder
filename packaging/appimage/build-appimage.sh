#!/usr/bin/env bash
set -euo pipefail
project_dir=$(cd -- "$(dirname -- "$0")/../.." && pwd)
python_bin=${DF_PYTHON:-python3.12}
build_root=${DF_BUILD_ROOT:-/tmp/duplicate-finder-build}
version=$("$python_bin" -c 'import sys; sys.path.insert(0,sys.argv[1]); from DuplicateFinder import VERSION; print(VERSION)' "$project_dir")
if [[ $(uname -m) != x86_64 ]]; then
  printf '%s\n' 'This AppImage build targets x86_64 only.' >&2
  exit 1
fi
"$python_bin" -c 'import sys; assert sys.version_info[:2] == (3,12), "Official AppImages use Python 3.12"'
"$python_bin" "$project_dir/build.py" --onedir --distpath "$build_root/dist" --workpath "$build_root"
mkdir -p "$project_dir/dist"
bundle="$build_root/dist/DuplicateFinder"
"$python_bin" "$project_dir/tools/audit_bundle.py" "$bundle" \
  --max-glibc "${DF_MAX_GLIBC:-2.35}" > "$project_dir/dist/abi-audit.json"
"$python_bin" "$project_dir/tools/collect_licenses.py" "$bundle/share" "$build_root/native-sources.json"
"$python_bin" "$project_dir/tools/fetch_appimage_tools.py" "$build_root/tools"
(cd "$build_root/tools" && ./appimagetool --appimage-extract)
app_dir=$(mktemp -d "$build_root/DuplicateFinder.AppDir.XXXXXX")
trap 'rm -rf -- "$app_dir"' EXIT
mkdir -p "$app_dir/usr/lib/duplicate-finder" "$app_dir/usr/share/duplicate-finder"
cp -a "$bundle/." "$app_dir/usr/lib/duplicate-finder/"
mv "$app_dir/usr/lib/duplicate-finder/share/"* "$app_dir/usr/share/duplicate-finder/"
rmdir "$app_dir/usr/lib/duplicate-finder/share"
cp "$project_dir/packaging/appimage/AppRun" "$app_dir/AppRun"
chmod +x "$app_dir/AppRun"
cp "$project_dir/packaging/appimage/"*.desktop "$project_dir/packaging/appimage/"*.svg "$app_dir/"
ln -s io.github.edjenn1998.DuplicateFinder.svg "$app_dir/.DirIcon"
cp "$project_dir/dist/abi-audit.json" "$project_dir/packaging/appimage/toolchain.json" "$app_dir/usr/share/duplicate-finder/"
mkdir -p "$app_dir/usr/share/duplicate-finder/licenses/appimage-runtime"
cp "$build_root/tools/"*-license "$app_dir/usr/share/duplicate-finder/licenses/appimage-runtime/"
"$app_dir/AppRun" --self-test
xvfb-run -a "$app_dir/AppRun" --gui-self-test
output="$project_dir/dist/DuplicateFinder-$version-x86_64.AppImage"
ARCH=x86_64 "$build_root/tools/squashfs-root/AppRun" --no-appstream \
  --runtime-file "$build_root/tools/runtime" "$app_dir" "$output"
chmod +x "$output"
"$output" --appimage-extract-and-run --self-test
xvfb-run -a "$output" --appimage-extract-and-run --gui-self-test
cp "$app_dir/usr/share/duplicate-finder/python-dependencies.txt" "$app_dir/usr/share/duplicate-finder/native-packages.txt" "$project_dir/dist/"
(cd "$project_dir/dist" && sha256sum "$(basename "$output")" abi-audit.json python-dependencies.txt native-packages.txt > SHA256SUMS)
