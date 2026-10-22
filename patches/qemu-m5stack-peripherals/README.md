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
- complete M5IOE1 GPIO direction/pull/drive/input, ADC and temperature,
  write-zero-to-clear IRQ status, PWM and reset-key semantics;
- AW9523 input/output/direction/interrupt registers with QOM input-bank
  injection and GPIO-mode output readback;
- PI4IOE5V6408 direction, output, high-impedance, pull, input-default,
  input-status and read-to-clear interrupt-status semantics;
- LP5562 RGB controller enable/mode and independent PWM registers on AtomS3R;
- SX1262 command/register/FIFO, IRQ, packet metadata and local TX/RX loopback
  over ESP32-S3 GP-SPI3 and GDMA;
- cyclic I2S/GDMA TX PCM capture and RX PCM injection, including ES8311,
  ES7210, AW88298, AW8737A, NS4150B and PDM paths;
- continuous I2S TX capture from the first non-silent descriptor, without
  whole-ring snapshots, duplicate-hash suppression or skipped silence;
- ESP32 classic I2S0/I2S1 linked-list DMA model for Core2 v1.1, with NS4168
  speaker PCM capture, SPM1423 PDM microphone injection and AXP2101 ALDO3
  amplifier-enable tracking;
- INA3221 three-channel power-monitor model with chip-native bus/shunt register
  scaling and QOM physical-value injection;
- ESP32-S3 TWAI connection to a reusable QEMU CAN-bus peer for bidirectional
  StamPLC CAN frame tests on G42/G43;
- StamPLC PWR485 UART2 peer and the IDF UART2 clock-check compatibility mirror
  for G0/G39/G46 half-duplex transmit/receive;
- StamPLC G44 I2S 1-bit delta-sigma buzzer capture through the existing I2S TX
  DMA data plane;
- MPU6886 big-endian accel/gyro register correction and LM75 11-bit
  temperature-register validation;
- GP-SPI SD SPI command/data model with ACMD/CMD support, CRC16 and raw image
  backing for Cardputer-ADV and PaperColor;
- peripheral-start callbacks in GDMA so LCD_CAM capture starts on the real
  `IN_LINK.START` transaction, cyclic camera descriptor completion, continuous
  sensor VSYNC while DMA is idle, and the resulting CoreS3/StackChan camera
  snapshot path;
- PaperMono IP2315 I2C charger state at address `0x75`, including the charge
  enable bit and `REG_CHG_STAT(0xC7)` consumed by `Power.isCharging()`;
- PaperMono GPIO42 buzzer output through ESP32-S3 I2S TX/GDMA and host PCM
  capture, plus power-key input routing for PaperMono and PaperColor;
- StackChan BM8563-compatible PCF8563 RTC at `0x51`, with QOM absolute epoch
  and relative-offset injection on PCF8563/RX8130;
- StackChan LTR-553ALS-WA ambient-light/proximity sensor at `0x23`;
- byte-accurate GP-SPI register access plus GDMA TX/RX completion for
  MicroPython `machine.SPI` transactions;
- optional raw camera frame injection through `M5SW_CAMERA_FRAME`;
- Cardputer-Adv, AtomS3R, Core2, PaperColor, PaperMono, StackChan and StamPLC
  peripheral attachment updates.

Historical incremental replay uses `0001` then `0002`. For a fresh upstream
tree, use the current standalone snapshot `0003` followed by the PCM capture
fix `0004`:

```bash
cd "$QEMU_ROOT/build/qemu"
git apply /path/to/0003-m5stack-shared-spi-full.patch
git apply /path/to/0004-m5stack-i2s-pcm-capture.patch
git apply /path/to/0005-m5stack-max3421e-usb.patch
git apply /path/to/0006-m5stack-gdma-camera-ip2315.patch
git apply /path/to/0007-m5stack-spi-slave-dma-routing.patch
git apply /path/to/0008-m5stack-core2-i2s-virtual-clock.patch
git apply /path/to/0009-bcm2835-unicam-imx219-frame.patch
git apply /path/to/0010-bcm2835-spi-dma-panel-sink.patch
git apply /path/to/0011-imx219-register-controlled-frames-and-gl852g-tt.patch
git apply /path/to/0012-stackchan-correct-bm8563-rtc.patch
git apply /path/to/0013-papermono-buzzer-and-power-key.patch
git apply /path/to/0014-m5-lcd-cam-runtime-frame-seed.patch
ninja -C build qemu-system-xtensa
```

`0005`-`0007` are incremental fixes against the M5StopWatch-QEMU development
worktree used by this repository. Replay them on the matching checkout rather
than a bare upstream tree; `0003` is retained as the historical shared-SPI
snapshot and is not by itself a complete clean-room source bundle for every
later backend file.

Verified source baseline:

- `espressif/qemu` base `da100c909249926b9f4458f18e4f2d216d08f51a`;
- QEMU `9.2.2`;
- historical `0001`/`0002` checks pass on their incremental baseline;
- `0004` applies cleanly immediately after the current standalone `0003`.

The camera frame path is a simulation data plane, not real-camera validation.
StickS3 IR TX/RX, PaperMono/StackChan I2C NFC, PaperMono SX1262 LoRa,
StackChan SCS servo, audio PCM capture/injection, Core2 v1.1 audio/INA3221 and
Cardputer/PaperColor SPI SD and Cardputer-ADV NFCCap ST25R3916 SPI plus Cap
CC1101 Sub-GHz are validated through the UIFlow2 runtime. USB Host and Tab5
MIPI-CSI/ES8388 remain follow-up work and are tracked in the peripheral
catalog. The SX1262 test still keeps CS asserted and splits large SPI transfers
into ≤4-byte transactions for compatibility with the current UIFlow2 SPI
driver path; the SPI SD path exercises larger block transfers directly.

`0003-m5stack-shared-spi-full.patch` is a standalone full snapshot against
upstream QEMU `da100c909249926b9f4458f18e4f2d216d08f51a`. It includes the
multi-CS ESP32-S3 GP-SPI model, ST25R3916 SPI/NFCCap and CC1101 Cap local
loopback paths; use it when rebuilding a fresh tree without replaying the
earlier incremental patches.

`0004-m5stack-i2s-pcm-capture.patch` applies after `0003` and fixes PCM
capture fidelity for both the ESP32-S3 GDMA path and ESP32 classic linked-list
I2S path. The DMA completion path is now the sole ESP32-S3 capture source;
duplicate blocks are no longer removed, and silence after capture starts is
preserved so WAV timing and waveform remain continuous.

`0005-m5stack-max3421e-usb.patch` adds the shared-SPI transaction gating and
CoreS3 MAX3421E USB host model. `0006` adds the GDMA peripheral-start callback,
fixes the camera VSYNC/DMA startup ordering and cyclic descriptor writes, and
adds the PaperMono IP2315 charger model. `0007` lets each GP-SPI slave select
the DMA peripheral used by its board alias, so CoreS3 M-Bus SD/MAX3421E use
`GDMA_SPI2` while PaperColor SD and PaperMono SX1262 continue to use
`GDMA_SPI3`. `0008` moves the ESP32 classic I2S DMA timers onto QEMU's virtual
clock so descriptor interrupts are serialized with guest execution.

`0009-bcm2835-unicam-imx219-frame.patch` adds the BCM2835 Unicam CSI1 MMIO,
CMI aperture, CAM1 IRQ and image-buffer destination model. Linux
`bcm2835-unicam` programs the format/stride/address, the model writes a
complete deterministic frame into the guest V4L2 buffer, and frame-start /
frame-end interrupts complete real capture buffers. `run_camera_probe.py`
verifies a 640x480 RG10 frame with a repeatable SHA256.

`0010-bcm2835-spi-dma-panel-sink.patch` adds 32-bit FIFO transfers in BCM2835
SPI DMA mode, keeps write-only DMA TX moving when the RX FIFO has no consumer,
and reconstructs the CardputerZero ST7789v3 RGB565 framebuffer from the
panel-mipi-dbi SPI stream. The optional sink emits PPM snapshots for visual
checks without reading `/dev/fb1`.

`0011-imx219-register-controlled-frames-and-gl852g-tt.patch` extends the
CardputerZero camera from a controller-generated scene to a register-driven
sensor model. IMX219 mode select, output window, lane configuration,
frame/line length, exposure, analogue/digital gain, orientation and test
patterns now control the RG10 frame emitted by Unicam. QOM exposes the live
configuration for Device Center automation.

It also adds a functional GL852G transaction-translator compatibility path.
Full- and low-speed children retain their real model speed while the upstream
HCD sees the High-Speed hub port and routes normal control/bulk/interrupt
packets. SR9900A Full-Speed Ethernet and a low-speed USB HID both enumerate
through the hub. This is functional TT routing, not cycle-accurate USB split
transaction timing.

`0012-stackchan-correct-bm8563-rtc.patch` corrects StackChan's RTC attachment
from a non-existent RX8130 at `0x32` to the BM8563-compatible PCF8563 at
`0x51`, exposes `rtc-offset` plus absolute `unix-time` QOM injection on both
RTC models, and attaches the carrier LTR553 ambient-light sensor at `0x23`.

`0013-papermono-buzzer-and-power-key.patch` attaches PaperMono's GPIO42
buzzer path to the ESP32-S3 I2S/GDMA model and routes the QMP `P` key to the
board power-key signal shared by PaperMono and PaperColor.

`0014-m5-lcd-cam-runtime-frame-seed.patch` exposes the deterministic GC0308
camera frame seed through QOM, adds per-frame auto-increment, and registers
`/machine/m5-lcd-cam`. CoreS3 can therefore observe changing frame content
across runtime snapshots while StackChan keeps its single-frame path.
