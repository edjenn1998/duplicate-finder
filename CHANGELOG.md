# Changelog

## 1.3.0

- Publish a portable x86_64 AppImage with Python, Tcl/Tk, Pillow and Send2Trash,
  a modern static runtime, checksums and an actual native dependency/ABI audit.
- Stage moves privately and publish complete, verified copies atomically without
  overwriting existing files; retain the source if publication/copy checks fail.
- Replace per-selection preview threads with one coalescing worker. Clear stale
  previews after rescans/cleanup and release unused preview images.
- Refuse changed/replaced preview files, including symlinks and FIFOs; fix EXIF
  orientation/bounds, normalize image modes, and support UTF-16 text previews.
- Fix the Cancel button's stale event binding for both scans and cleanup, honor
  cancellation at the final scan step, and protect queued-directory traversal
  against replacement by a symlink on Linux.
- Add First path/Newest/Oldest keeper policies, hard-link-aware size estimates,
  CSV scan export, and copy/save buttons on error and cleanup reports.
- Remember folder/options/window size, add Show containing folder, and avoid
  passing bundled Python/Tk libraries to external system viewers.
- Add missing CI and ignore files, pin release dependencies, regenerate notices,
  refresh the screenshot, and document AppImage launching for new Linux users.
- Expand the 22 existing checks with failure-case and real GUI regression tests.

## 1.2

- Replace font-dependent check marks with drawn, clickable checkboxes.
- Replace garbled button ellipses with plain text.
- Retain the larger preview and fixed confirmation footer from 1.1.

## 1.1

- Enlarge the preview pane and default window.
- Keep confirmation buttons visible at the minimum dialog size.
- Package the Linux application as one executable with Python and dependencies.

## 1.0

- Add a desktop GUI for exact duplicate detection and previews.
- Scan with a subfolder toggle, minimum size, progress and cancellation.
- Revalidate files and retained copies before cleanup.
- Provide confirmed trash and collision-safe move actions.
