UNIT-HOST-38 layered testing evidence (2026-10-27)

The complete matrix round is FAIL: 66 PASS / 1 FAIL across 67 cases. The only
failed case is core2-imu: guest exit code 0, but the required final framebuffer
marker is missing (rgb 0,0,0). Its original UART reaches the requested final
accel/gyro values. Both facts remain separate; the UART values do not turn the
frame oracle or the round into PASS. Original before/after PNGs, serial bytes,
summary and oracle output are retained. No rerun or substituted frame is mixed
into this archive.

The new Xtensa runtime 3f161756cdb31dec3812393b730e1ae670733e7354d7b57fddbbd0149b8645e1
covers 62 cases (61 PASS / 1 FAIL). The other five cases use the independent C6
runtime ff6c2ef71e83253ef35ccc2ef5aa42243270f6a397b169a9af549b47d5ca09c0
and all pass. Their results are not transferred to the new Xtensa build.
Every case ran once, with no retries or filter selection. Root's terminal
session attestation records exit 1, captured after execution.

Host-only platform validation is separately green: 1220 full tests and 24
focused tests. UNIT-HOST-22 is also separate: the old actual-main mock preserves
the wrong checker command in summary and FAIL; the corrected mock records the
actual profile launch argv and PASS while preserving checker calls. The actual
PaperColor RGB case passes in this complete round and now retains a profile
command, WS2812 decode and frame-marker output. This is not an independent
pre-execution ps/exec trace.

All 835 matrix input files are indexed: 402 original byte copies, including
134 CRC-checked PNGs, and 433 fingerprint-only binary/non-UTF8 inputs. Firmware,
ROM, executable, Flash, eFuse, PPM, PCM, RMT, SD and raw UART1 binary bytes are
not copied. The safe text and PNG originals are byte-for-byte unchanged.
Additional source snapshots and evidence are explicitly captured after the run.
PNG text metadata is absent; all 134 PNGs have heuristic OCR privacy checks,
and the Core2/PaperColor final frames were visually inspected. OCR is not a
guarantee that every possible visual identifier can be detected.

The launch-composition SHA printed before QEMU starts is separate from the
post-run mutable Flash file SHA. Six IR-related cases have different hashes;
both are preserved without assigning a guest fault cause. The runner attaches
the Flash file as writable raw MTD. A post-run image cannot replace launch-time
composition evidence. The initial archive-only script's incorrect equality
assertion is retained with its corrected interpretation. Its second CRLF
window-parser failure is also retained; neither failure changed the matrix or
its source files.

Portable verification needs only Python 3.10+ and this directory:
  python3 -B verify.py

It validates original hashes, all PNG CRCs, two exact frame pixels, original
UART byte windows, status layers, command preservation, platform logs and the
binary fingerprints. A PASS from this verifier means archive integrity; it
continues to report the complete matrix as FAIL.

Optional original-file comparison (reads about 1 GB of mutable-Flash evidence):
  python3 -B verify.py --check-originals --repo-root /path/to/repository

The index covers every other file and excludes itself. Original raw CRLF,
trailing whitespace, diagnostics and failed receipts are intentionally retained.
No API/Web running asset, guest, product source or git index was modified during
archival. These direct repository QEMU regressions are not Device Service
product-path acceptance and are not physical-hardware evidence.
