# M5Stack peripheral models and data planes

This patch is incremental to `qemu-multi-board-uiflow2` and
`qemu-core2-qemu-esptool`. It adds:

- a corrected ESP32-S3 I2C FIFO and repeated-start model;
- a software/hardware I2C hand-off guard used by board autodetection;
- BMI270 configuration upload, accel/gyro data and BMM150 Sensor Hub data;
- MPU6886, PCF8563, BM8563/RX8130, AXP192/AXP2101, M5PM1, AW9523,
  PI4IOE5V6408, TCA8418, FT5x06, CST820, LM75, SHT40, LTR553 and INA226
  register-level models;
- INA226 calibration-aware voltage/current/power conversion;
- CoreS3 GC0308 identity plus an ESP32-S3 LCD_CAM + GDMA RGB565 frame path;
- optional raw camera frame injection through `M5SW_CAMERA_FRAME`;
- Cardputer-Adv, AtomS3R, Core2, PaperColor, PaperMono, StackChan and StamPLC
  peripheral attachment updates.

Apply after the two prerequisite patches:

```bash
cd "$QEMU_ROOT/build/qemu"
git apply /path/to/qemu-multi-board-uiflow2/0001-qemu-m5stack-multiboard-uiflow2.patch
git apply /path/to/qemu-core2-qemu-esptool/0001-esp32-uart-configurable-rx-baud-scale.patch
git apply /path/to/0001-m5stack-peripheral-models-and-data-planes.patch
ninja -C build qemu-system-xtensa
```

Verified source baseline:

- `espressif/qemu` base `da100c909249926b9f4458f18e4f2d216d08f51a`;
- QEMU `9.2.2`;
- `git apply --check` passes on a clean tree after both prerequisite patches.

The camera frame path is a simulation data plane, not real-camera validation.
Audio PCM, IR packets, SD, USB Host, SX1262 and the Tab5 MIPI-CSI path remain
separate follow-up work and are tracked as `partial`/`planned` in the peripheral
catalog.
