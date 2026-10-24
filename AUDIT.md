# Duplicate Finder 1.3.0 review

The original 1.2 source, build script, 22 embedded tests and screenshot were
reviewed. All original tests passed before changes. The following findings were
addressed, with additional regression coverage where applicable.

| Finding | Resolution |
| --- | --- |
| Every selection started another preview thread; rapid browsing could accumulate work/images. | One coalescing worker processes the current request, discards stale output and closes unused images. |
| New scans and cleanup did not fully reset old previews/viewer controls. | Reset and invalidate preview state at operation boundaries. |
| Preview reads followed replaced paths and could block on a FIFO. | Open descriptors with no-follow/nonblocking flags and validate the scanned file identity/type. |
| EXIF orientation was not handled; rotated previews could exceed their bounds. | Orient, normalize color mode, then resize; test CMYK and rotated images. |
| UTF-16 text was treated as binary. | Detect its BOM while retaining bounded text/binary previews. |
| A cancellation arriving at the final scan callback could still return results. | Check cancellation before returning the completed scan. |
| The Cancel button captured the initial event, but scans/cleanup replaced that event, leaving the button ineffective. | Resolve the current event on click; test actual button cancellation during both scan and cleanup. |
| Queued directories could be swapped for symlinks before traversal. | Resolve an explicitly selected root and pin Linux directory descriptors with no-follow checks. |
| Move destinations were visible while copying. | Private staging, verification, then atomic no-replace publication with collision handling and source preservation on failure. |
| Frozen-app library paths could leak into external viewers; a long-lived launcher could look like failure. | Restore system library environment and treat an ongoing viewer process as successful launch. |
| No keeper-age policy, hard-link-aware estimate or CSV export. | Add deterministic policies, inode/link-aware estimates and current-selection CSV reports. |
| Reports could not be copied/saved, and settings were forgotten. | Add report controls and atomic, optional preferences with malformed-file fallback. |
| README referenced `.gitignore` and CI files absent from the checkout. | Add both, plus tracked AppImage launcher/icon/desktop/build sources. |
| Build dependencies were broad ranges, and release notices/audit were missing. | Pin Python/tool dependencies and generate actual license, native dependency and ABI records. |
| Download instructions covered only the older executable. | Add beginner-friendly AppImage permissions, launch, update/removal and no-FUSE instructions. |

## Verification scope

45 automated checks (22 embedded plus 23 extended), real Tk GUI tests under Xvfb,
and packaged engine/GUI self-tests cover the implemented changes. Release builds
target Ubuntu 22.04/x86_64; Windows/macOS and every possible Linux distribution
are not claimed as tested. Existing file-change checks and keep-one protections
remain, with a documented final filesystem check/action race. No permanent-delete
fallback has been introduced.
