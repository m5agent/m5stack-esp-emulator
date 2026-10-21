# CoreS3 UIFlow2 Local UI and Touch Test

The test replaces only `/boot.py` and `/main.py` in the official CoreS3
UIFlow2 v2.5.3 LittleFS partition (`0xAA0000`, size `0x4C0000`).

```bash
cp platform/.cache/firmware/cores3/uiflow2.bin /tmp/cores3-base.bin
truncate -s 16777216 /tmp/cores3-base.bin
PYTHONPATH=.work/py python3 tests/uiflow2/cores3_ui_test/make_image.py \
  --base /tmp/cores3-base.bin \
  --out /tmp/cores3-ui-test.bin

qemu-system-xtensa -M m5cores3 \
  -drive file=/tmp/cores3-ui-test.bin,if=mtd,format=raw \
  -L bin/Darwin-arm64 -display none
```

The acceptance target is a `320x240` first frame and a touch event that
increments the on-screen counter.
