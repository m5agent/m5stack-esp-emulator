# Arduino documentation through Device Service

Run paired virtual-device validation on an agent-owned Device Service with
separate state and control token. Provision its QEMU and esp32sim assets and
use Python 3.12 with Pillow.

```sh
python3 tests/firmware/arduino_docs/run_service.py \
  --service "http://127.0.0.1:$TEST_PORT" \
  --token-file "$CONTROL_TOKEN_FILE" \
  --firmware-root "$ARDUINO_DOCS_FIRMWARE_ROOT" \
  --out .work/arduino-docs-paired \
  --case cores3/display --case cores3/quickstart-bargraph
```

The firmware root uses `DEVICE/CASE/sketch.merged.bin` and must contain the
actual merged image bytes. Use the original docs builds from the
[firmware archive](https://github.com/m5agent/m5stack-firmware-archive) or its
pinned build recipes. Verify the image hashes against the case manifests.
Omit `--case` to replay every currently implemented service oracle.

Each case runs twice on each runtime, with a new lease per observation.
Each trial records the firmware hash, session receipt, sampled panel frames,
serial and a verified evidence ZIP, then stops with `purge=0`. Output paths
must be new so that repeated runs preserve earlier receipts.

The runner covers selected display and quick-start cases for CoreS3,
Cardputer, Dial, StickS3, StopWatch, Basic, Core2, PaperColor, PaperDIY,
PaperMono, AtomS3, AtomS3R, StackChan, StamPLC and the StickC family.
It also checks the CoreS3 power-button and battery readback examples and the
Dial encoder example. It ports predicates
from the [CoreS3 checker](https://github.com/m5agent/esp32sim/blob/4e257b6be8ee0ed706c2e509d8f31ef7472a424b/tools/check_cores3.py)
and [S3-B checker](https://github.com/m5agent/esp32sim/blob/4e257b6be8ee0ed706c2e509d8f31ef7472a424b/tools/check-s3b-docs.py),
plus the fork's [classic](https://github.com/m5agent/esp32sim/blob/4e257b6be8ee0ed706c2e509d8f31ef7472a424b/tools/check-lx6-cores.py)
and [e-paper](https://github.com/m5agent/esp32sim/blob/4e257b6be8ee0ed706c2e509d8f31ef7472a424b/tools/check-paper-docs.py)
checkers.
The runner compares the panel-native API geometry and samples against a bounded
wall-time window. A matching frame result is `PARTIAL` until the service can
also verify the controller and guest-time checks. A missing image is `NOT RUN`.
Use the [pinned defect list](../../../docs/arduino-docs-defects-2026-11-27.md)
for cases whose source or library builds have known defects.
