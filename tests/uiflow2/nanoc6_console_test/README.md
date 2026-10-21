# NanoC6 UIFlow2 Console Test

Status: **PASS**. The official UIFlow2 v2.5.3 image runs on the ESP32-C6
QEMU machine through the USB-Serial-JTAG console. A replaced `vfs` image
executes `boot.py` and `main.py`, and `M5.begin()` reports board 140.

```bash
PYTHONPATH=.work/py python3 tests/uiflow2/nanoc6_console_test/make_image.py \
  --base platform/.cache/firmware/nanoc6/uiflow2.bin \
  --out /tmp/nanoc6-ui-test.bin

qemu-system-riscv32 -M esp32c6 \
  -drive file=/tmp/nanoc6-ui-test.bin,if=mtd,format=raw \
  -L .work/M5StopWatch-QEMU/build/qemu-c6/pc-bios \
  -display none -serial null -serial null \
  -serial file:/tmp/nanoc6-serial.log
```

The QEMU binary is
`.work/M5StopWatch-QEMU/build/qemu-c6/build/qemu-system-riscv32`; the
third serial port is the C6 USB-Serial-JTAG console. The display runner is
not applicable because NanoC6 has no panel.
