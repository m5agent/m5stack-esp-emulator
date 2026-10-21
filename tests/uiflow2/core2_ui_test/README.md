# Core2 UIFlow2 Local UI and Touch Test

Status: **PASS**. Official UIFlow2 reaches `main.py`, `M5.begin()` reports
`320x240`, the complete ILI9342 frame renders, and a QMP FT5x06 touch event
redraws the on-screen counter. QEMU currently needs `-m 0` for best
PSRAM/cache stability.

The runner replaces only `/boot.py` and `/main.py` in the official Core2
UIFlow2 v2.5.3 LittleFS partition (`0x820000`, size `0x7DF000`).

The unified matrix writes the resulting 16 MiB image through the QEMU ESP32
ROM UART download mode with `esptool --no-stub`, verifies the virtual flash
byte-for-byte, and boots that same image. The QEMU patch adds a receive
`baud-scale` property so the ROM download path is practical while normal boots
retain the default timing model.

```bash
PYTHONPATH=.work/py python3 tests/uiflow2/run_profile_ui_test.py \
  --base platform/.cache/firmware/core2/uiflow2.bin --machine m5core2 \
  --files-dir tests/uiflow2/core2_ui_test \
  --vfs-offset 0x820000 --vfs-size 0x7DF000 --flash-size 0x1000000 \
  --expected-size 320x240 --input touch:160,183 \
  --efuse-driver none --memory 0
```

The test asserts a `320x240` first frame and an FT5x06 touch event that
redraws the displayed touch status.
