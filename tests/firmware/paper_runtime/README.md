# PaperS3 and PaperDIY factory firmware

`run_test.py` uses Device Service to run PaperS3 Factory V0.5 or the
PaperDIY V1.0 factory demo. It checks the device's native EPD output after
GT911 touch on PaperS3 or independent A/B press and release on PaperDIY.
It exports the evidence before stopping the session and releasing Flash.

See the [validation record](../../../docs/evidence/2026-11-09-paper-et047tc1/README.md)
for the QEMU build, firmware versions, PaperDIY NVS fixture, and replay commands.

## PaperS3 GT911 configured scan period

Build the ESP-IDF probe using v5.5.4 and create a merged 8 MiB image.

```sh
idf.py -C tests/firmware/paper_runtime/gt911_scan -B "$PAPER_GT911_BUILD" build
cd "$PAPER_GT911_BUILD"
python -m esptool --chip esp32s3 merge_bin --fill-flash-size 8MB -o "$PAPER_GT911_FIRMWARE" @flash_args
```

Import the same merged image into isolated native Device Service sessions for
`papers3` on the frozen and candidate builds. Wait for `PAPER_SCAN_READY rate=15`.
Send `{"kind":"longpress","x":113,"y":347,"hold_seconds":1.4,"settle_seconds":0.3}`
through the session input route. The probe writes register `0x8056` through
the ESP32-S3 I²C controller and measures ACK-to-ready in guest time at `0x814E`.
It requires eight one-point reports, one zero-point release and an idle read
after ACK. At least six of the eight intervals must reach 9 ms to distinguish
the configured period from the old hard-coded 5 ms. Fetch each session ZIP
before stopping it. [A/B receipt](gt911_scan/summary.json)

Both the unchanged Factory V0.5 image and the ESP-IDF probe reached the actual
native GT911 model. The candidate passed the configured-period assertion. In
the original app, the buzzer icon still missed some inputs. The bounded receipt
keeps the original icon outcomes and the separate instrumented I²C drag/readback.
