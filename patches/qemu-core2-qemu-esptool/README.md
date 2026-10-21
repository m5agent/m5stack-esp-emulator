# Core2 QEMU esptool transport

This patch adds a configurable RX baud scale to the ESP32 QEMU UART model. The
Core2 virtual-host flash path uses the QEMU ESP32 ROM in UART download mode and
esptool's `--no-stub` protocol:

- QEMU machine: `m5core2`
- GPIO strap: `0x0f`
- UART property: `esp_soc.uart.baud-scale=16`
- esptool: `--chip esp32 --no-stub`

The baud scale only adjusts the UART receive-throttle model used by the ROM
download path. Normal Core2 boots do not set the property and retain the
default scale of `1`.

Apply and rebuild from the emulator project root:

```bash
cd .work/M5StopWatch-QEMU/build/qemu
git apply --check ../../../../patches/qemu-core2-qemu-esptool/0001-esp32-uart-configurable-rx-baud-scale.patch
git apply ../../../../patches/qemu-core2-qemu-esptool/0001-esp32-uart-configurable-rx-baud-scale.patch
ninja -C build qemu-system-xtensa
```

The patch was generated against `espressif/qemu` commit
`da100c9` in the M5StopWatch-QEMU worktree.
