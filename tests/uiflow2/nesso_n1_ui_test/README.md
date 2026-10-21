# Nesso N1 UIFlow2 Virtual Host Test

Official UIFlow2 v2.5.3 is loaded into the ESP32-C6 QEMU machine.  The
runner replaces only `/boot.py` and `/main.py` in the `vfs` partition and
requires a changed `135x240` screendump after a QMP touch event.

Status: **PASS**. `M5.getBoard()` reports the Nesso N1 board, the
135x240 panel is detected, and touch redraws both the counter and the
reported coordinates.

QEMU writes PPM rows with 4-byte alignment, so a 135-pixel RGB row occupies
408 bytes instead of 405. The matrix runner now honors that stride, emits a
canonical PNG, and compares canonical pixels. The earlier diagonal artifact
was therefore in the capture reader, not in the ST7789 panel model.

```bash
PYTHONPATH=.work/py python3 tests/uiflow2/run_profile_ui_test.py \
  --base platform/.cache/firmware/nesso-n1/uiflow2.bin \
  --machine esp32c6 \
  --files-dir tests/uiflow2/nesso_n1_ui_test \
  --vfs-offset 0x820000 --vfs-size 0x7DF000 --flash-size 0x1000000 \
  --expected-size 135x240 --input touch:67,160 \
  --efuse-driver none --wait 15 --post-input-wait 2 \
  --qemu .work/M5StopWatch-QEMU/build/qemu-c6/build/qemu-system-riscv32 \
  --rom-dir .work/M5StopWatch-QEMU/build/qemu-c6/pc-bios
```
