# M5Stack peripheral input, power and RTC models

This patch is incremental to the existing M5Stack QEMU board patches. It:

- routes StickS3 `BtnPWR` through M5PM1 `IRQ_STATUS3` (`0x42`);
- routes CoreS3 `BtnPWR` through AXP2101 PWR IRQ (`0x49`);
- acks AXP2101 PWR IRQ bits with write-one-to-clear semantics;
- exposes AXP2101 battery level, battery voltage, VBUS voltage and charging
  state through live QOM properties;
- models CoreS3's PCF8563 RTC at I2C address `0x51`;
- adds the CoreS3 GC0308 SCCB identity at I2C address `0x21`.

The GC0308 identity is enough for board/camera initialization, but QEMU still
does not model ESP32-S3 LCD_CAM capture/DMA, so `camera.snapshot()` currently
returns `None`.

The patch baseline is the QEMU worktree after the project's existing
`qemu-multi-board-uiflow2` and C6 adapter patches. Verify with:

```bash
git apply --check /path/to/0001-m5stack-peripheral-input-power-rtc.patch
ninja -C build qemu-system-xtensa
```
