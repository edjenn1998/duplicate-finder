# Duplicate Finder 1.3.0

A desktop utility by Edwin Combs that finds files with **identical contents**, even
when their names differ. Review duplicates, preview them, then move extra copies
to a holding folder or send them to your operating system's trash.

![Duplicate Finder window](docs/screenshot.png)

## Download and run an AppImage — start here

### 1. Download the ready-to-run application

Visit [the latest release](https://github.com/edjenn1998/duplicate-finder/releases/latest),
expand **Assets**, and download **`DuplicateFinder-1.3.0-x86_64.AppImage`**.
GitHub's “Source code” ZIP/tar downloads are for developers, not the ready-to-run app.

The AppImage includes Python, Tcl/Tk, Pillow and Send2Trash. It targets **64-bit
Intel/AMD Linux with glibc 2.35 or newer**, such as Ubuntu 22.04 and newer, on a
graphical desktop. It is not a Windows/macOS executable or an ARM/Raspberry Pi or
Alpine/musl build. Each release includes its exact `abi-audit.json`.

### 2. Allow it to run

An AppImage is a portable application file, **not an installer or ZIP archive**.
Keep it in Downloads, or move it somewhere convenient, such as an `Applications`
folder in your home directory.

On Ubuntu and many other Linux desktops:

1. Right-click the downloaded AppImage and choose **Properties**.
2. Open **Permissions** and enable **Allow executing file as program**. Other
   file managers may call this **Executable as Program**.
3. Close Properties and double-click the AppImage. Choose **Run** if prompted.

No Python installation, administrator account or `sudo` is needed to run it.
The first launch may take a moment. An application-menu entry is not installed
automatically; launch the same file again whenever you need it.

### Terminal alternative

Open a terminal in the download's folder (in Ubuntu Files, right-click the folder
background and choose **Open in Terminal**):

```sh
chmod +x ./DuplicateFinder-1.3.0-x86_64.AppImage
./DuplicateFinder-1.3.0-x86_64.AppImage
```

Use the filename you actually downloaded. The `./` means “run this file in the
current folder.” If you see “No such file,” check the filename and terminal folder.

### If launching fails: no-FUSE mode

This release uses the modern, statically linked AppImage runtime. **You do not need
to install the old `libfuse2` or `libfuse2t64` package**, unlike many older AppImages.
Normal launching uses the kernel's FUSE mounting facility. If your computer
restricts mounting, or you receive a FUSE or permission error, run without FUSE:

```sh
./DuplicateFinder-1.3.0-x86_64.AppImage --appimage-extract-and-run
```

The app is extracted to temporary storage, run, and cleaned up after exit. This
requires temporary disk space, but no FUSE package installation or administrator
access. If the download is on a filesystem that prohibits executable files, move
it to your home folder first.

You can also keep an extracted copy:

```sh
./DuplicateFinder-1.3.0-x86_64.AppImage --appimage-extract
./squashfs-root/AppRun
```

An error mentioning a newer `GLIBC` version means the distribution is too old for
this build; installing FUSE will not solve it. Run from a terminal to see errors
and include that text and your Linux version in a [GitHub issue](https://github.com/edjenn1998/duplicate-finder/issues).

### Updates, removal and optional verification

Updates are manual: download the newer AppImage, make it executable, then use it
instead of the old file. To remove the application, delete the AppImage and any
`squashfs-root` directory you explicitly extracted. **Your scanned files and holding
folders are separate and are not removed with the app.** Preferences are stored at
`~/.config/duplicate-finder/settings.json` (or under `$XDG_CONFIG_HOME`).

Optional: download `SHA256SUMS` into the same folder and check download integrity:

```sh
sha256sum --ignore-missing --check SHA256SUMS
```

The AppImage should report **OK**. Checksums verify download integrity, not publisher identity.

## Using Duplicate Finder

1. Choose a folder and whether to **Include subfolders**.
2. Set the minimum file size in B, KiB, MiB or GiB. The default ignores files
   smaller than **1 KiB**; use **0 B** to include empty and very small files.
3. Click **Scan folder**. Groups contain exact matches, not just similar names.
4. Click a file to preview it. Use **Open in default viewer** for media/PDFs, or
   **Show containing folder** to inspect its location.
5. Click a checkbox or **Remove?** cell to mark a copy. **Select extra copies**
   applies the **Keep** policy: **First path** (alphabetical), **Newest**, or **Oldest**
   (modification time). Hard-linked names are left for manual review. Review the
   resulting choices; at least one path in each group must remain.
6. Choose **Move selected...** or **Trash selected...** and review the listed target
   and retained paths before confirming.
7. Read the cleanup report, then rescan before another cleanup.

**Move** preserves copies in a holding folder of your choice. Choosing a holding
folder outside the scanned tree avoids rediscovering those copies on the next scan.
**Trash** uses the OS trash. It never falls back to permanent deletion if trash
support fails. Permanent deletion is not offered by this application.

The size estimate counts each selected inode once and accounts for hard links
outside the scan. It is an upper bound on duplicate file data, not a measurement
of allocated blocks, compression or copy-on-write sharing. **Trashed data still
occupies storage until the trash is emptied. Moving to another folder on the same
filesystem does not free space on that filesystem.**

### Reports and preferences

- **Export CSV...** saves all current groups, exact paths, SHA-256 hashes, sizes,
  hard-link counts and Keep/Remove choices. CSV export does not change files.
- Scan-error and cleanup reports have **Copy report** and **Save report...** buttons.
- Folder, recursion, minimum-size settings, keeper policy and window size are
  remembered. No scan or cleanup is started automatically on launch.
- Background scanning and a single bounded preview worker keep browsing responsive.
  Cancel stops at the next safe step. Completed cleanup actions remain applied;
  remaining items are left alone and the report identifies completed/failed actions.

## Matching and file protection

File sizes, partial hashes and full SHA-256 hashes identify duplicate groups.
Each target and retained copy is rehashed before cleanup. Moves copy to a private
temporary file in the destination folder, flush/check it, then publish the complete
copy atomically without overwriting an existing name. Collisions get `_dup1`,
`_dup2`, etc. The original is removed only after copy/publication checks succeed.
Filesystems without the necessary no-replace rename or hard-link operation can
reject a move; the source is retained rather than weakening overwrite protection.

Symlinks within a scan are excluded. A deliberately selected symlink root is
resolved once. Hard-linked names are labeled separately; removing one name may
free no storage, and changing link metadata can make later actions require a rescan.
File changes are checked before/during hashing, copying and previewing. A small
final filesystem check/action race remains: avoid concurrent edits while cleaning
up. Metadata copying is best-effort; ACLs, extended attributes and sparse allocation
are not guaranteed. Scan errors mean results may be incomplete.

Images are bounded to 30 million source pixels for embedded previews and are
resized/oriented in the background. Very large images can use the external viewer.
Similar photos, re-encoded media or files with different embedded metadata are
not byte-identical duplicates.

## Run from source

Python **3.10 or newer** and Tkinter are required. Release builds use Python 3.12.
Pillow supplies image previews; Send2Trash supplies trash integration.

On Ubuntu/Debian:

```sh
sudo apt update
sudo apt install python3-tk python3-venv
python3 -m venv .venv
. .venv/bin/activate
python -m pip install -r requirements.txt
python DuplicateFinder.py
```

On Arch/CachyOS install `python tk`, then use the same venv commands. On Windows,
use python.org Python with Tk support, `py -m venv .venv`, activate
`.venv\Scripts\Activate.ps1`, install requirements, then run the script. Linux
source and AppImage behavior are tested; Windows/macOS builds have not been verified.

## Tests and builds

```sh
python DuplicateFinder.py --self-test
xvfb-run -a python -m unittest discover -s tests -v
xvfb-run -a python DuplicateFinder.py --gui-self-test
```

`xvfb-run` is needed only for headless GUI testing; install `xvfb xauth` on
Ubuntu/Debian, or use a real X11 display instead. Tests use temporary fixtures,
not user files. GUI self-tests do not change saved preferences.

The suite contains **22 embedded regression tests plus 23 extended engine/GUI
tests**, including cancellation, changed files, collisions, copy failure, hard links,
symlinks/FIFOs, preview bounds/coalescing, CSV export and preferences. The packaged
GUI self-test additionally exercises real scanning, previews, verified moves and reports.

For a native single-file executable:

```sh
python -m pip install -r requirements-build.txt
python build.py
```

Use `python build.py --onedir` for an inspectable bundle. Build on the target OS;
PyInstaller does not cross-compile. See [APPIMAGE.md](APPIMAGE.md) for official
Ubuntu 22.04 AppImage builds, pinned toolchain hashes, audits and release checks.
GitHub Actions runs the tests and AppImage build on pushes and pull requests.

## Project and licensing

- [CHANGELOG.md](CHANGELOG.md): release changes.
- [AUDIT.md](AUDIT.md): findings addressed in the 1.3.0 review.
- [NOTICE.md](NOTICE.md): third-party notices and source information.
- `DuplicateFinder.py`: application and embedded smoke/regression tests.
- `tests/`: extended tests; `tools/` and `packaging/`: reproducible build sources.

Copyright (C) 2026 Edwin Combs. Licensed under **GNU GPL version 3 or later**;
see [LICENSE](LICENSE). Generated release binaries and build artifacts are distributed
through GitHub Releases, with current bundled license notices and dependency inventories.
