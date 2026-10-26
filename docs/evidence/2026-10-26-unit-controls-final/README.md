# Final control Unit validation

2026-10-26: five guest/controller cases **PASS**, all through visible Device
Service leases on CoreS3 using the final frozen QEMU binary:

`1880891da692de06612aa0a10b2026c0209875f4641e837df29dc818bb3ac81d`

`summary.json` selects the exact firmware, session, ZIP and checks for Joystick
v1.1, Encoder, 8Encoder, CardKB and RFID2. Each folder contains final serial,
settled native framebuffer, pre-stop ZIP, result/prepared metadata, and exact
probe/config text. The official driver source manifest is preserved at the
root. All five final framebuffers were visually inspected. Firmware/ROM
binaries remain outside this directory in ignored build storage.

The ZIPs retain one worker ID/generation, matching all three final browser runs.
`runtime-worker-provenance.json` links those immutable manifests to the frozen
service/source-replay records and the independent live Key/Fan executable SHA
observations. The extra controls live-PID observer used a ten-second window
and missed the flashing interval; `live-pid-observer.json` preserves that
incomplete observation. Its observer exit code is 1; the controller runner's
exit code is 0 and all five functional results are PASS. No direct per-control
PID observation is claimed.

All leases requested evidence before stop and ended with `purge=0`, retaining
metadata, serial and the last frame. These cases prove only their exact
firmware/runtime/controller paths. They do not establish RF, switch mechanics,
physical LED placement, mechanical travel/angle, or hardware equivalence.
Earlier 732d runtime runs and the resolved RFID probe failure remain in
`../2026-10-26-unit-controls-service/`; they are not used as final-revision
acceptance evidence.

Final command (with the existing compatible reference firmware and dependencies):

```sh
M5_PYTHON_DEPS="$PWD/.work/py312" PYTHONPATH=.work/py312 \
  /opt/miniconda3/bin/python3.12 tests/units/run_control_cases.py \
  --case all --out-dir .work/control-unit-validation-final-20261026
```
