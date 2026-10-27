# Core2 UIFlow2 startup regression

These probes target stock UIFlow2 V2.5.3 on the virtual `m5core2` board.
`run_service_test.py` prepares only the VFS locally, then uploads and executes
through a visible Device Service session on port 8787. It never starts QEMU or
the service directly.

Cases: `display`, `widgets`, `lvgl`, and `network`. The LVGL case checks label
geometry and glyph structure as well as serial completion; a nonblack striped
frame must fail. The offline network case expects `active(True)` to return,
`isconnected()` to report false, and an unavailable TEST-NET NTP send to raise
a bounded transport error before drawing `loading...`.

```bash
PYTHONPATH=platform/tools:.work/py312 python3.12 \
  tests/firmware/core2_startup/run_service_test.py \
  --case all --out-dir .work/core2-startup/replay \
  --expected-runtime-sha256 <sha256-of-running-runtime> \
  --runtime-source-receipt <source-receipt-json> \
  --token-file <local-token-file>
```

The base firmware and application bytes are pinned; wrong/legacy executables
fail before upload. Evidence ZIP contents and ownership are verified before
stopping with history retained. The runner checks that the original runtime
process is gone, Flash is released, and the exact last frame remains available.
Raw images, ZIPs, process identities and local paths stay in the ignored output
folder. Physical hardware is not exercised.

`run_radio_service_test.py` executes the existing official stock WiFi probe in
two sequential visible sessions. It checks scan/association, DHCP DORA and a
controlled HTTP fixture against packet evidence, then verifies cleanup.
The original headless program only receives its fixture port substitution;
its black framebuffer is not counted as a display test.

```bash
PYTHONPATH=platform/tools:.work/py312 python3.12 \
  tests/firmware/core2_startup/run_radio_service_test.py --execute \
  --token-file <local-token-file> \
  --expected-runtime-sha <sha256-of-running-runtime> \
  --receipt <source-receipt-json> \
  --out-dir .work/core2-startup/radio-replay
```

See the [dated result and limits](../../../docs/evidence/2026-10-27-core2-startup/README.md).
The private complete applications from issues #2/#3 were not available; these
probes do not assert their entire business logic or legacy UIFlow1 LVGL7 support.
