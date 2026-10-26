# M5Stack peripheral models and data planes

This directory contains historical snapshot branches, not one universal
linear patch sequence. The standalone `0003` snapshot is based on the
M5StopWatch-QEMU-derived tree; it is **not** applicable after
`qemu-multi-board-uiflow2/0001`, and the two patches have different images of
shared files such as `hw/gpio/esp32_gpio.c`.

For a working runtime, use the published macOS arm64 release bundle or the
target-specific tree described below. Do not reconstruct a clean tree by
applying both historical branches in sequence.

For the reproducible external-Unit Xtensa source, follow
[`qemu-unit-runtime/README.md`](../qemu-unit-runtime/README.md): its pinned public
base and two prelude patches are followed by `0033`, `0034`, `0035`,
`0036-core2-soft-i2c-handoff-compat.patch`, then
`0037-s3-ledc-duty-readback.patch`. Patch `0036` removes the permanent
classic ESP32 software-I2C disable introduced with Unit routing; it preserves
Core2's hardware/software switching while retaining the S3 handoff behavior.
Patch `0037` adds S3-only DUTY/DUTY_R low-19-bit readback from the existing
immediate duty model for settled set+update observations. It leaves classic
layout and PWM writes/output unchanged, and does not gate register reads on
output enable or timer pause. Pending/current-cycle separation, active-latch,
fade and physical timing remain explicit gaps; see the fixed official sources
and validation scope in the prelude README. A source/contract check is not a
new runtime or firmware PASS.
Do not apply these on top of an arbitrary historical snapshot.

The peripheral work adds:

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
- ESP32-S3 Bluetooth low-power clock register readback, the RWIP busy/ID/time
  handshake used by precompiled BLE controller firmware, and both validated
  CO5300 QSPI command byte layouts used by UIFlow2 and MotoNav.
- GigaDevice GD25Qxx status-register-2 QIO enable/readback, fixing firmware
  that aborts in `esp_flash_init_default_chip()` after a failed QIE write.
- ISSI IS25LP/WP status-register-2 QE mirroring for C6 firmware that verifies
  quad enable through `RDSR2(0x35)` after setting SR1 bit 6.
- Cardputer ADV QMP-to-TCA8418 matrix encoding for printable keys, Enter,
  Space, Tab, Backspace and FN-arrow combinations.
- CS-gated direct SPI panel ID reads so M5GFX autodetection probes using
  unselected pin groups do not all observe the same ST7789 identity.
- StickS3 panel identification as ST7789 (`0x81`) instead of inheriting the
  generic ST7735 (`0x7683`) ID, which made M5GFX select a 128x128 AtomS3R path.
- An ESP32-S3 WiFi MAC/DMA device at `0x60033000` sharing the OpenMAC WLAN
  access-point/data-frame state machine with the classic ESP32 model. It uses
  the S3 RX/TX descriptor layout, S3 RX metadata header, WLAN interrupt source
  and QEMU user networking, while preserving the existing StickS3 board
  peripherals in the same machine.

Historical incremental replay uses `0001` then `0002` on their original
derived tree. The list below records predecessor order on the retained
M5StopWatch-QEMU-derived target tree. It is **not** a validated raw-upstream
bootstrap recipe: later snapshots contain state from earlier incremental
changes, and some files exist only in the retained worktree.

```bash
cd "$QEMU_ROOT/build/qemu"
# Historical provenance order; apply only to the matching predecessor tree.
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
git apply /path/to/0015-motonav-rwip-and-co5300-framing.patch
git apply /path/to/0016-gigadevice-status2-qio.patch
git apply /path/to/0017-cardputer-adv-qmp-key-matrix.patch
git apply /path/to/0018-gpspi-cs-gated-panel-id.patch
git apply /path/to/qemu-core2-openmac-wifi/0001-esp32-openmac-wifi-model.patch
git apply /path/to/0019-esp32s3-wifi-mac.patch
git apply /path/to/0020-m5ioe1-pa-output-state.patch
git apply /path/to/0021-esp32s3-uart2-chardev.patch
git apply /path/to/0022-sticks3-st7789-panel-id.patch
git apply /path/to/0023-user-firmware-hot-samples.patch
git apply /path/to/0024-esp32s3-qio-read-phase.patch
git apply /path/to/0025-esp32c6-wifi-mac.patch
git apply /path/to/0026-m5stack-rtc-virtual-clock.patch
git apply /path/to/0027-esp32s3-gdma-external-memory.patch
git apply /path/to/0028-esp32-wifi-dual-guest-fabric.patch
git apply /path/to/0029-esp32s3-wpa2-psk-data-plane.patch
git apply /path/to/0030-core2-eight-mib-psram.patch
git apply /path/to/0031-core2-shared-board-i2c.patch
git apply /path/to/0032-esp32-timg-wdt-trace.patch
git apply /path/to/0033-esp32-s32c1i-trace.patch
git apply /path/to/0034-xtensa-ccompare-equal-deadline.patch
git apply /path/to/0035-esp32-timg-wdt-int-ena.patch
git apply /path/to/0036-ssi-transfer-buf.patch
git apply /path/to/0037-esp32-handoff-trace.patch
git apply /path/to/0038-esp32-handoff-pause.patch
git apply /path/to/0039-esp32-handoff-state-dump.patch
git apply /path/to/0040-xtensa-handoff-pc-trace.patch
git apply /path/to/0041-esp32-handoff-register-stack-dump.patch
git apply /path/to/0042-esp32-spi-trans-done-irq-diagnostic.patch
ninja -C build qemu-system-xtensa qemu-system-riscv32
```

`0005`-`0007` are incremental fixes against the M5StopWatch-QEMU development
worktree used by this repository. Replay them on the matching checkout rather
than a bare upstream tree; `0003` is retained as the historical shared-SPI
snapshot and is not by itself a complete clean-room source bundle for every
later backend file.

Verified source baseline:

- public `espressif/qemu` tag `esp-develop-9.2.2-20260417`
  (`6cdce334bfa5541a5e46c860a9b40a4fe5a13aae`) plus the published
  `zqqf16/M5StopWatch-QEMU` v0.1.0 patches;
- QEMU `9.2.2`;
- historical `0001`/`0002` checks pass on their incremental baseline;
- `0004` and the later numbered patches are predecessor-bound, not standalone
  raw-upstream patches. The current `0003` snapshot already contains later PCM
  state, so replaying `0004` after that snapshot is not a supported
  clean-room operation.

The camera frame path is a simulation data plane, not real-camera validation.

`0019-esp32s3-wifi-mac.patch` depends on the shared WLAN files imported by
`qemu-core2-openmac-wifi/0001-esp32-openmac-wifi-model.patch`. It is a
functional scan/association/DHCP/HTTP data plane on one fixed virtual channel,
not a complete S3 PHY/rate/security model. The unified StickS3 test also uses
an HCI-UART UIFlow2 build so the external Bumble controller can exercise the
same guest's BLE NUS data plane without a second emulator process.

`0020-m5ioe1-pa-output-state.patch` tracks M5IOE1 `GPIO_OUT_H` bit 1 and
exposes the decoded StopWatch G10 PA level as `pa-enabled`. StopWatch routes
the AW8737A enable through M5IOE1; M5PM1's G3 PA bit is the StickS3 path and
must not be used as a StopWatch proxy.

`0021-esp32s3-uart2-chardev.patch` connects the optional ESP32-S3 UART2 to
QEMU's third serial chardev. StackChan uses it for external HCI because UART1
is dedicated to the SCS servo bus. Without the mapping, guest HCI commands
were write-only and NimBLE timed out waiting for a controller acknowledgement.

`0022-sticks3-st7789-panel-id.patch` changes StickS3's modelled panel identity
from the generic ST7735 `0x7683` default to the ST7789 `0x81` family. With the
old value, M5GFX's LGA56 autodetection accepted the AtomS3R probe and mapped
the application through a 128x128 ST7735 panel; a normal 240x135 StickS3 layout
therefore appeared as only a clipped corner.

`0030-core2-eight-mib-psram.patch` expands the `m5core2` PSRAM memory region
to 8 MiB and models the 128 32 KiB DRAM1 MMU entries used by
ESP-IDF bank switching. It keeps the normal ESP32 heap window at 4 MiB and
maps the upper half on demand. The `core2_psram_himem` firmware probe passes
three independent leases by alternating two distinct upper physical blocks
through the same virtual window and verifying both after remap. This is not a
physical PSRAM or cache-timing measurement.

`0031-core2-shared-board-i2c.patch` routes both ESP32 I2C controller register
blocks to the single physical GPIO21/22 Core2 board bus and attaches AXP,
RTC, touch and IMU once. Legacy UIFlow performs AXP and BM8563 transactions
through controller 0, while the previous model exposed RTC only on controller
1. Port-level trace proves `0x34` and `0x51` now share
`/machine/soc/i2c0/i2c`; the public UIFlow image advances beyond the prior
`I2C bus error (19)`. Existing UIFlow2 Core2 peripheral cases pass.
The same firmware still reaches an independent interrupt-WDT boundary and
does not yet produce a non-empty application frame. This patch does not claim
physical board timing or complete legacy-firmware compatibility.

`0032-esp32-timg-wdt-trace.patch` adds a default-off `M5SW_TIMG_TRACE`
diagnostic channel for timer-group watchdog reset/config/feed/arm/timeout
events. It does not alter watchdog behavior. In a default single-session run,
the legacy image continued feeding TG0/TG1 for more than three minutes; two
independent four-session default batches produced interrupt-WDT failures in
five of eight leases at varying CPUs and PCs. Explicit `thread=single`,
`thread=multi`, and `icount shift=0/5` controls did not remove the failure:
the thread and icount controls instead exposed TG hardware resets during boot.
The remaining investigation is the interaction between the guest's long
synchronous boot phase and virtual-time/host scheduling, not a missing PMIC
transaction.

`0033-esp32-s32c1i-trace.patch` adds a default-off
`M5SW_S32C1I_TRACE` channel for CPU index, PRID, stack pointer, PC, virtual
address, `SCOMPARE1`, desired value, returned old value and CAS success. It is
a diagnostic only and does not change compare-and-swap semantics. The corrected
`core2_flash_ipc` probe produced no spinlock-owner assertion across dated
current/portable runs, so this trace is retained to audit atomic operations
rather than as evidence of a confirmed CAS defect.

`0034-xtensa-ccompare-equal-deadline.patch` fixes the generic Xtensa timer
deadline calculation when a guest writes `CCOMPARE == CCOUNT`. The old
subtraction wrapped that valid equal-cycle window to `2^32` ticks, deferring
the next interrupt by roughly 26.8 seconds on Core2 and allowing the guest
tick watchdog to expire. The patch schedules the equal deadline on the next
cycle while preserving the previous 32-bit wraparound interpretation for all
other deltas. A business-only control with tracing disabled passed the
corrected `core2_flash_ipc` first-boot probe repeatedly; this does not close
the separate legacy-UIFlow TG0/TG1 watchdog and black-frame failure.

`0035-esp32-timg-wdt-int-ena.patch` corrects TIMG WDT level-interrupt masking.
The model previously raised the WDT line whenever `INT_RAW.WDT` became set,
even when `INT_ENA.WDT` was clear. The patch preserves raw status and the stage
timer but drives the level only from `INT_RAW & INT_ENA`. The trace observed
`INT_ENA=0`, `INT_RAW=4`, masked status `0`; two Device Service controls still
reached `TG0WDT_SYS_RESET` after the fix. This patch is a model-semantics fix,
not closure of the legacy UIFlow QIO/cross-core/flash-cache path.

`0036-ssi-transfer-buf.patch` adds an optional byte-buffer transfer callback to
the generic SSI bus. Devices without the callback retain the original
per-byte `ssi_transfer` behavior. m25p80 implements the callback only for
`STATE_READ`; command, address, dummy-cycle, CS and address-wrap handling stay
on the existing state machine. ESP32 SPI uses the callback only for
receive-only data phases. In the legacy Core2 image, sampled batches matched
the original per-byte path; the Core2 UIFlow2 device group and shared-controller
full matrix passed, but watchdog-disabled legacy firmware still did not reach
the REPL.
This is a controller/data-path optimization, not closure of `RUNTIME-03`.

`0037-esp32-handoff-trace.patch` adds a default-off
`M5SW_ESP32_HANDOFF_TRACE` diagnostic channel shared by cross-core interrupts,
DPORT cache control/sync, TIMG WDT, UART interrupt state and ESP32 SPI
transactions. Each line records virtual time, current CPU, guest PC and four
component-specific values. Routine events support
`M5SW_ESP32_HANDOFF_TRACE_SAMPLE`; WDT timeout/interrupt/reset events are always
emitted. `M5SW_ESP32_HANDOFF_PC_SAMPLE_NS=1000000` optionally samples both
guest PCs, but is off by default because it perturbs scheduling. Early
normal-WDT runs showed a fixed 800 ms gap between the last TG1 feed and stage-0
timeout, but a later no-PC-trace TIMG liveness control classified that gap as
`NOT_REPRODUCED`. A same-VMA byte audit rejected the
local UIFlow2 v2.5.3 ELF mapping of the public legacy v1.15.4 BIN to UART
ISR/MicroPython; the exact BIN bytes are consistent with cross-core
Flash/cache-disable handoff but remain symbol-unbound. WDT-disabled
`sample=1024` and trace-off produced the same serial output. This patch closes
the missing-timeline prerequisite, not `RUNTIME-03`.

`0038-esp32-handoff-pause.patch` adds the default-off
`M5SW_ESP32_HANDOFF_PAUSE_NS` diagnostic timer. At the requested QEMU virtual
time it records a `component=cpu event=pause` marker and sends `SIGSTOP` to the
QEMU process. This freezes both vCPUs without enabling high-frequency PC
sampling, allowing a debugger to read guest PS, `INTENABLE`, `INTSET`,
`EXCCAUSE`, register windows and QEMU CPU state at an exact virtual timestamp.
It is diagnostic-only and does not alter reset, WDT or controller behavior.

`0039-esp32-handoff-state-dump.patch` makes the pause self-describing. It logs
both vCPU PCs, interrupt-request and halted/running state, the Core2 handoff
flags, DPORT cache state, and aggregate cache/SSI/cross-core counters before
optionally entering `SIGSTOP`. The default action remains `SIGSTOP`;
`M5SW_ESP32_HANDOFF_PAUSE_ACTION=exit` is only for isolated one-point Device
Service diagnostics.

`0040-xtensa-handoff-pc-trace.patch` adds a default-off list of
`M5SW_XTENSA_PC_TRACE` addresses. It records only selected BIN-bound PCs with
PRID, PS, INTENABLE and INTSET, avoiding the scheduling perturbation of a
periodic PC sampler. A normal-WDT run observed 4,376 completed cache-handoff
cycles before reset at `15.914787 s`, so `RUNTIME-03` is not a permanent
cross-core deadlock. The three-run liveness control further shows a masked TG0
stage-0 timeout, TG0 stage-1 as the first reset path, and TG1 feeding until
`1.779-4.271 ms` before reset with zero TG1 timeouts. Exact counts and evidence
remain in the validation ledger.

`0041-esp32-handoff-register-stack-dump.patch` extends the exact-time dump with
A0-A15, PS, selected object pointers and an optional bounded stack window.
`M5SW_ESP32_HANDOFF_STACK_WORDS` is clamped to 64 words, defaults to zero and
is read through each vCPU's address space. WDT-off 45/120-second snapshots
placed CPU0 in `waiti` idle and CPU1 in the same `0x40100049` flag/object loop
after Flash activity ended around 44 seconds. This is diagnostic only; the
late object has no matching ELF symbol.

`0042-esp32-spi-trans-done-irq-diagnostic.patch` adds the missing
`SPI_SLAVE.TRANS_DONE`/`TRANS_INTEN` state and drives the SPI interrupt line
as their logical AND. It also adds optional bounded object-word output to the
exact-time handoff dump. BIN-bound analysis identifies the former late loop as
LVGL `lv_refr_vdb_flush`: the VDB is double-buffered with `flushing=1`,
`wait_cb` is null, and the display flush callback is invoked at about 44-48 s.
The completion callback and `lv_disp_flush_ready` were still not observed
within 50 seconds after enabling the transaction-done IRQ model, and normal
WDT still reset at TG0 stage-1. This is a partial controller-model diagnostic,
not a `RUNTIME-03` fix.

`0023-user-firmware-hot-samples.patch` adds the regressions found by booting
three popular M5Burner images per available ESP device. It enables the S3 LEDC
register layout used by Cardputer Meshtastic, preserves PSRAM cache control
bits, fixes APPCPU reset/mailbox startup and the `0xff` CPU-id sentinel alias,
restores coprocessor enable state, separates CO5300 QSPI command framing,
infers unreliable SPI panel D/C phases from DCS commands and pixel lengths,
adds the second StamPLC PI4IOE expander with unique QOM names, and attaches
AtomS3R's ES8311/PI4IOE devices.

`0024-esp32s3-qio-read-phase.patch` completes the S3 `0xEB` QIO read phase for
the m25p80 model. Arduino ESP32 4.4 supplies one programmed dummy byte while
m25p80 consumes a mode byte and four dummy bytes; the four-byte shortfall
shifted every read so NVS returned empty values, LittleFS data was corrupt and
display assets repeated. The fix is limited to QIO reads selected on flash
CS0.

`0025-esp32c6-wifi-mac.patch` adds the ESP32-C6 WiFi MAC/PHY register
windows, RX/TX descriptor rings, interrupt completion and QEMU NIC conversion
behind `-nic`. It supports the open virtual AP used by the repository tests:
stock UIFlow2 performs scan, Authentication, Association, DHCP, DNS and a
controlled or public HTTP request. MODEM_SYSCON at `0x600a9800` is required for
leaving scan mode; TX queue state and command frame construction are also
modelled. The patch is validated with NanoC6 and Nesso N1 in the same C6 guest
as their board peripherals and UART1 HCI BLE path. Apply it after `0023` on
the M5StopWatch-QEMU ESP32-C6 worktree; it is not a standalone patch against
the upstream C6 machine.

`0026-m5stack-rtc-virtual-clock.patch` makes the RX8130 and PCF8563 models
advance from a boot-time epoch on QEMU's virtual clock instead of host wall
time. Core2 deterministic `icount` execution can run a guest 1.2-second RTC
probe faster than host time; host-clock RTCs therefore appeared frozen. The
firmware-facing register layout and QOM offsets are unchanged.

`0027-esp32s3-gdma-external-memory.patch` keeps the normal internal-DRAM
descriptor path and falls back to the SoC system address space when an AES
descriptor points into the ESP32-S3 external-memory window. UIFlow2
`ssl.SSLContext` previously stalled while an AES payload read returned
`MEMTX_ERROR`; the stock TLS path now reaches the certificate parser and HTTPS
gateway. The fallback uses the modelled cache/PSRAM path and does not expose
arbitrary host memory.

`0028-esp32-wifi-dual-guest-fabric.patch` makes the shared classic/S3 WLAN
model usable by more than one guest at a time. It honors the explicit QEMU NIC
MAC for the full virtual STA lifecycle, accepts host ingress during the
association/DHCP transition, and flushes controller input held while the
802.11 injection queue was busy. The validation fixture runs two UIFlow2
StickS3 guests through a private QEMU socket L2 switch: both complete
DISCOVER/OFFER/REQUEST/ACK, exchange a real TCP request/reply in both pcap
directions, and cannot reach the host, public IPv4 or metadata from the
namespace.

`0029-esp32s3-wpa2-psk-data-plane.patch` adds WPA2-PSK RSN advertisement,
PBKDF2/PTK derivation, EAPOL M1-M4, MIC validation, CCMP encryption/decryption
and the ESP32-S3 hardware-decrypted RX layout. Correct credentials now reach
the guest WiFi callback, DHCP, DNS and TCP/443; wrong credentials fail at M2
MIC and trigger deauthentication/retry. DHCP replies are delivered as
pairwise-key 802.11 unicast so the guest receives a complete Ethernet/DHCP
frame. The validated scope is WPA2-PSK pairwise/unicast; WPA3, group-key
multicast and physical RF behavior are not claimed.

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

`0015-motonav-rwip-and-co5300-framing.patch` closes two firmware-path gaps
found while booting the unmodified MotoNav v7.12.3 StopWatch image. ESP32-S3
now preserves the `SYSTEM_BT_LPCK_DIV_INT/FRAC` registers long enough for the
BTDM low-power setup readback, exposes the RWIP control/ID/time handshake used
by BLE controller startup, and the CO5300 accepts both
`[op, 00, cmd, 00]` and `[op, cmd, 00, 00]` QSPI address phase layouts. The
same StopWatch image now produces the MotoNav link page while the reference
UIFlow2 image still renders normally.
