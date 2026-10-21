# AtomS3R UIFlow2 Local UI Test

Build a test image by replacing only the LittleFS user files in the official
8 MiB UIFlow2 v2.5.3 AtomS3R image:

```bash
PYTHONPATH=.work/py python3 tests/uiflow2/atoms3r_ui_test/make_image.py \
  --base platform/.cache/firmware/atoms3r/uiflow2.bin.padded \
  --out /tmp/atoms3r-ui-test.bin \
  --efuse-out /tmp/atoms3r-efuse.bin
```

Run:

```bash
qemu-system-xtensa -M m5atoms3r \
  -drive file=/tmp/atoms3r-ui-test.bin,if=mtd,format=raw \
  -drive if=none,id=efuse,file=/tmp/atoms3r-efuse.bin,format=raw \
  -global driver=nvram.esp32s3.efuse,property=drive,value=efuse \
  -L bin/Darwin-arm64 -display none
```

Expected serial markers:

```text
ATOMS3R_BOOT_FLAG
ATOMS3R_MAIN_START
ATOMS3R_M5_BEGIN_OK
ATOMS3R_DISPLAY 128 128
```
