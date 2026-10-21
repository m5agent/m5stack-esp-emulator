# M5Stack peripheral models and data planes

This patch is incremental to `qemu-multi-board-uiflow2` and
`qemu-core2-qemu-esptool`. It adds:

- a corrected ESP32-S3 I2C FIFO and repeated-start model;
- level-triggered ESP32-S3 interrupt-matrix retriggering and the special
  disconnected interrupt line used by the IDF SPI bus lock;
- a software/hardware I2C hand-off guard used by board autodetection;
- BMI270 configuration upload, accel/gyro data and BMM150 Sensor Hub data;
- MPU6886, PCF8563, BM8563/RX8130, AXP192/AXP2101, M5PM1, AW9523,
  PI4IOE5V6408, TCA8418, FT5x06, CST820, LM75, SHT40, LTR553 and INA226
  register-level models;
- INA226 calibration-aware voltage/current/power conversion;
- CoreS3 GC0308 identity plus an ESP32-S3 LCD_CAM + GDMA RGB565 frame path;
- PaperMono SSD1677 e-paper refresh, GPIO keys and DWC SDMMC block I/O;
- ESP32-S3 I2S APB register front-end and PCM observation hooks;
- ESP32-S3 RMT APB/RMTMEM model with NEC TX symbol capture and RX symbol
  injection through real `TX_END`/`RX_END` interrupts;
- ESP32-S3 system UART clock/reset gates for IDF UART1 bring-up;
- StackChan SCSCL UART servo model with PING/READ/WRITE/SYNC_WRITE framing;
- ST25R3916 I2C command/register/FIFO model with ISO14443A anticollision,
  SELECT and deterministic NTAG page read/write;
- Si12T three-point body-touch register model with QOM touch-bit injection;
- M5IOE1 NeoPixel configuration and RGB565 LED RAM readback for StackChan;
- LP5562 RGB controller enable/mode and independent PWM registers on AtomS3R;
- SX1262 command/register/FIFO, IRQ, packet metadata and local TX/RX loopback
  over ESP32-S3 GP-SPI3 and GDMA;
- cyclic I2S/GDMA TX PCM capture and RX PCM injection, including ES8311,
  ES7210, AW88298, AW8737A, NS4150B and PDM paths;
- GP-SPI SD SPI command/data model with ACMD/CMD support, CRC16 and raw image
  backing for Cardputer-ADV and PaperColor;
- byte-accurate GP-SPI register access plus GDMA TX/RX completion for
  MicroPython `machine.SPI` transactions;
- optional raw camera frame injection through `M5SW_CAMERA_FRAME`;
- Cardputer-Adv, AtomS3R, Core2, PaperColor, PaperMono, StackChan and StamPLC
  peripheral attachment updates.

Apply after the two prerequisite patches:

```bash
cd "$QEMU_ROOT/build/qemu"
git apply /path/to/qemu-multi-board-uiflow2/0001-qemu-m5stack-multiboard-uiflow2.patch
git apply /path/to/qemu-core2-qemu-esptool/0001-esp32-uart-configurable-rx-baud-scale.patch
git apply /path/to/0001-m5stack-peripheral-models-and-data-planes.patch
git apply /path/to/0002-m5stack-peripheral-data-paths.patch
ninja -C build qemu-system-xtensa
```

Verified source baseline:

- `espressif/qemu` base `da100c909249926b9f4458f18e4f2d216d08f51a`;
- QEMU `9.2.2`;
- `git apply --check` passes for `0001` on a clean tree after both prerequisite
  patches, and for `0002` immediately after `0001`.

The camera frame path is a simulation data plane, not real-camera validation.
StickS3 IR TX/RX, PaperMono/StackChan I2C NFC, PaperMono SX1262 LoRa,
StackChan SCS servo, audio PCM capture/injection and Cardputer/PaperColor SPI
SD are validated through the UIFlow2 runtime. USB Host, ST25R3916 SPI/NFCCap,
Tab5 MIPI-CSI/ES8388 and CAN/RS485 remain follow-up work and are tracked in
the peripheral catalog. The SX1262 test still keeps CS asserted and splits
large SPI transfers into ≤4-byte transactions for compatibility with the
current UIFlow2 SPI driver path; the SPI SD path exercises larger block
transfers directly.
