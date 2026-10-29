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
`0037-s3-ledc-duty-readback.patch`, then `0038-unit-pwm-route-refresh.patch`,
then `0043-unit-scroll-controller.patch`, `0044-unit-2relay-gpio.patch`, and
`0045-unit-flashlight-aw3641.patch`, then
`0046-unit-flashlight-route-lifecycle.patch`, then
`0047-unit-flashlight-cold-pad-observation.patch`, then
`0048-unit-servos8-joystick2-nfc.patch`. The intervening `0039`–`0042` files
belong to the separate Core2 diagnostic branch and are not part of this Unit stack.
`0045` adds a partial U152 AW3641E observer on yellow EN GPIO pad edges and
QEMU virtual time. Its S1 Flash/Torch fixture freezes after all creation inputs
are applied. Flash pulses qualify only on the supported GPIO route and within
the documented recommended HI/LO window; out-of-scope waveforms withdraw known
output. The 500 us stable-high decode and first-rise timeout origin are explicit
model policies. Torch models static EN only. It does not validate dynamic S1,
reset observation, PWM modulation, bit-exact timing, current, light or heat.
`0046` adds same-layout/same-pin GPIO OUT_SEL lifecycle invalidation to the
partial FlashLight model: route changes cancel all qualification timers and
old low intervals, and restoration requires a newly observed EN falling edge
plus long-low reset. Route changes do not fabricate pad edges or PWM waveforms.
New runtime `3f1617` passed the scoped four-host/eight-lane same-VM API and
CoreS3 mounted Web route-history checks; see the
[evidence](https://github.com/m5agent/m5stack-esp-emulator/blob/a37342f61c05964c060719a6e35c2d568c828e84/docs/evidence/2026-10-27-flashlight-route-history/README.md).
The independent full matrix remains 66 PASS / 1 Core2 IMU FAIL. Cold-route/no-edge
behavior, dynamic S1, PWM, full OEN/IOMUX, hard-reset observation and physical
equivalence stay OPEN.
`0047` supersedes the extra-falling-edge recovery rule with a controller-owned
pad observation. A newly known low starts its own >500us reset interval without
fabricating an edge. MMIO OUT/ENABLE/route/PAD_DRIVER, IO_MUX, external/force,
direct open-drain, reset and RTC ownership commits synchronously update the
observer. S3 GPIO256 applies OUT_INV and OEN_INV; OEN_SEL is equivalent for this
route. R1 is an owned passive bias. Unmodeled RTC/hold/power/USB ownership and
ambiguous source conflicts withdraw qualification. It does not implement RTC,
peripheral or PWM waveforms, the sleep FSM, electrical behavior, or a general
GPIO interrupt receiver model. The new C suite replays the complete stack;
the 0046 suite remains a fixed historical negative-control regression.
`0048` adds the official UIFlow2-compatible register banks and routed I2C
attachments for StickS3 `servo8-hat` at `0x36`, CoreS3 `8servos` at `0x25`,
Joystick2 at `0x63`/`0x64`, and the deterministic ST25R3916 NFC Unit fixture
at `0x50`. It covers controller-visible setup and register/data-plane
behavior, not physical servo, ADC/current, RF/antenna or electrical equivalence.
The soft-I2C bridge now owns explicit weak SDA/SCL pull-ups instead of relying
on the GPIO compatibility default. This preserves M5GFX's external-pull-up
board probe when it temporarily enables internal pull-downs. Opposing weak
sources remain unknown; compatibility reads do not establish electrical
thresholds. CoreS3 R20/R32 evidence and the failed first candidate are retained
in the [cold-pad record](https://github.com/m5agent/m5stack-esp-emulator/blob/a37342f61c05964c060719a6e35c2d568c828e84/docs/evidence/2026-10-27-flashlight-cold-pad/README.md).
`0087` adds the shared GPIO hard-reset observer used by Relay and Relay2. GPIO
reset now establishes the post-reset level, notifies reset observers, then
publishes any normal line change. Relay models rebase their previous level and
clear digital transition counters without treating the reset edge as a guest
transition. The AtomS3R fixed/pre-fix guest A/B is virtual-device validation;
contact, coil, load, electrical and physical-hardware behavior remain outside
the model. See the
[hard-reset evidence](../../docs/evidence/2026-10-29-unit-hard-reset-output-boundary/README.md).
`0044` adds U131's two independent GPIO pad observers and schematic R3/R6
digital pull-downs. White is channel 1, yellow channel 2; each transition
counter is independent. Outputs are read-only. This is nominal-powered
functional indication, not relay contact/load or electrical validation.
`0043` adds an independent, explicitly partial Scroll controller; the prelude
README and [Scroll audit](../../docs/unit-research/scroll-roller485.md) define
its bounded ticks, snapshot semantics and RGB queue/bootloader/persistence gaps.
Patch `0036` removes the permanent
classic ESP32 software-I2C disable introduced with Unit routing; it preserves
Core2's hardware/software switching while retaining the S3 handoff behavior.
Patch `0037` adds S3-only DUTY/DUTY_R low-19-bit readback from the existing
immediate duty model for settled set+update observations. It leaves classic
layout and PWM writes/output unchanged, and does not gate register reads on
output enable or timer pause. Pending/current-cycle separation, active-latch,
fade and physical timing remain explicit gaps; see the fixed official sources
and validation scope in the prelude README. A source/contract check is not a
new runtime or firmware PASS.
Patch `0038` is a candidate for GPIO-route initialization observation: a real
matrix OUT_SEL change refreshes same-layout LEDC state without replaying MMIO
writes or LED intensity side effects. It retains zero-duty frequency, the
existing unroute getter gate and readback semantics, and filters cross-layout
Unit observers. It does not extend current-cycle/fade or physical timing.
The initial candidate has passed same-firmware Device Service initialization
and shared-controller regression gates: `UNIT-HOST-20` is FIXED only for route
observation. Full-cycle/fade and physical behavior remain OPEN; see the
[scoped evidence](https://github.com/m5agent/m5stack-esp-emulator/blob/a37342f61c05964c060719a6e35c2d568c828e84/docs/evidence/2026-10-26-unit-pwm-route-d1ba/README.md).
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
- Core2 for AWS ATECC608A Cryptoauth wake/Read/Info/CRC I2C data plane with a
  deterministic locked test config and no production key material;
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

`0049-core2-offline-wifi-controller.patch` is an incremental board-wiring fix
for the reconstructed Xtensa source stack documented in
[`qemu-unit-runtime/README.md`](../qemu-unit-runtime/README.md). It realizes the
existing Core2 WiFi MAC/DMA/IRQ when there is no configured WiFi backend, then
disables the synthetic radio and AP timers. It does not attach a host network
or alter explicit WiFi NICs. Offline controller availability does not establish
WiFi connectivity, physical RF behavior or hardware validation.

`0050-esp32-spi-panel-dma-transaction.patch` fixes classic SPI panel delivery in
the same reconstructed source stack. OUT_LINK arms a DMA chain; USR consumes it
once through SSI and the panel within the MOSI length. Long ordinary FIFO writes
repeat the selected register bank safely. This removes duplicated/stale pixel
streams in UIFlow2 LVGL flushes. Descriptor owner/writeback, DMA interrupt/error
status, receive DMA and continuation across USR commands retain their existing
model boundaries; the patch does not establish physical display timing.

`0051-cardputer-adv-internal-i2c-pullups.patch` adds the ADV board's passive
pull-ups on GPIO8/9. M5GFX's pull-down identification can then distinguish its
internal I2C wiring from the original Cardputer. Open-drain peripheral ACK and
master low remain visible through the GPIO controller; this is not an electrical
threshold or physical-board measurement.

`0052-cores3-panel-spi2-gdma.patch` connects CoreS3's panel to GDMA SPI2, matching
M5GFX's SPI2 host and the shared M-Bus controller. FIFO drawing could previously
work while LVGL image flushes searched for a SPI3 DMA channel and delivered no
descriptor bytes. It changes board wiring only, without a fallback channel or
host-generated pixels.

`0053-s3-watchdog-immediate-config.patch` gives ESP32-S3 its documented MWDT
immediate register updates. Its HAL does not write the newer chips'
`CONF_UPDATE_EN`; requiring that bit left stage modes and the prescaler
inactive. The generic latched mode remains unchanged. Register protection and
a zero-prescaler host-crash guard have C regressions. Actual watchdog expiry
can now trigger the guest panic/reset path; successful warm boot after that
reset remains a separate validation gate.

`0054-i2s-rx-consume-transferred-pcm.patch` advances the RX source cursor by
actual GDMA-transferred bytes. Short descriptors previously discarded the
untransferred portion of a 4096-byte pre-read, introducing phase jumps and a
wrong captured frequency. The source is consumed only after real DMA progress.

`0055-lcd-cam-frame-dma-chunks.patch` fills a camera half-buffer across its
actual GDMA descriptors, preserving partial progress and pending EOF
acknowledgement. A stopped or unready capture must not consume the source or
publish a frame. C logic regression and visible camera-stream validation are
distinct gates; this is not optical or physical-camera evidence.

`0056-spi-sd-multiblock-transfers.patch` adds CMD18/CMD25 multi-sector data
tokens, stop handling and ACMD22/23 to the real SPI-backed SD model. It advances
only after transferred blocks, rejects absent/out-of-range backing storage,
and keeps writes in the session-owned disk. Both selected boards have native
block/FAT/remount and independent host file-byte oracles; those fixtures do
not establish arbitrary cards, all SD commands or physical bus timing.

`0057-gc0308-sccb-register-pages.patch` replaces GC0308's generic single
register bank with its SCCB page-zero/page-one state. Page-one register `0x00`
is writable independently of page-zero's `0x9b` product ID; `0xfe` bit 7 resets
the stored state and bit 0 selects the page. This preserves detection when the
official camera wrapper rebuilds the pipeline for `camera.framesize()` or a
later `camera.init()`. It does not implement image-processing register effects.
The fixed source is Espressif's
[`esp32-camera` commit `b817e9b`](https://github.com/espressif/esp32-camera/tree/b817e9b81041980608d1a3d3e0b08d86e3666382):
[`gc0308_regs.h`](https://github.com/espressif/esp32-camera/blob/b817e9b81041980608d1a3d3e0b08d86e3666382/sensors/private_include/gc0308_regs.h)
defines the reset/page bits,
[`gc0308_settings.h`](https://github.com/espressif/esp32-camera/blob/b817e9b81041980608d1a3d3e0b08d86e3666382/sensors/private_include/gc0308_settings.h#L179)
writes page-one register zero to `0xf5`, and
[`gc0308.c`](https://github.com/espressif/esp32-camera/blob/b817e9b81041980608d1a3d3e0b08d86e3666382/sensors/gc0308.c#L414)
selects page zero before reading the product ID. The offline C regression
replays actual helper bytes and keeps the old generic bank as a negative
control; `probe_gc0308_sccb.py` is the separate visible guest lifecycle probe.

`0058-gpspi-dma-transfer-chunks.patch` preserves the GDMA descriptor byte
cursor when M5GFX splits one Canvas buffer across multiple SPI transactions.
Previously every USR transaction reread the chain head, duplicating the upper
image in the lower half. The later `0061` supersedes this patch's provisional
START callback with per-channel generations and actual active-channel checks;
the patches must be applied in the documented bootstrap order.

`0059-lcd-cam-dvp-wire-order.patch` supplies GC0308 RGB565 as chronological
high-byte-first samples on the supported eight-bit DVP bus. It applies
`CAM_BIT_ORDER` to each bus byte and ignores the sixteen-bit-only
`CAM_BYTE_ORDER` field in this lane. Sixteen-bit input and enabled YUV/RGB
conversion are unimplemented: they produce `LOG_GUEST_ERROR` and no synthetic
RGB565 DMA frame. Raw file fixtures remain caller-provided wire bytes. The
register contract is Espressif's `lcd_cam_reg.h`; the pinned camera driver
sets `swap_data=0`, eight-bit input and converter bypass, and its native
JPG/BMP converters consume high-byte-first RGB565. The C regression checks
bit order, odd transfer boundaries, the complete scene and rejected modes.
Historical little-endian raw hashes establish only the old model's contents;
they do not establish correct sensor byte order or image colors.
The register source is pinned to ESP-IDF
[`7355072/lcd_cam_reg.h`](https://github.com/espressif/esp-idf/blob/735507283d5b2f9fb363a1901172dbd9e847945d/components/soc/esp32s3/register/soc/lcd_cam_reg.h).
The corresponding camera path is
[`b817e9b/ll_cam.c`](https://github.com/espressif/esp32-camera/blob/b817e9b81041980608d1a3d3e0b08d86e3666382/target/esp32s3/ll_cam.c),
[`to_bmp.c`](https://github.com/espressif/esp32-camera/blob/b817e9b81041980608d1a3d3e0b08d86e3666382/conversions/to_bmp.c)
and [`to_jpg.cpp`](https://github.com/espressif/esp32-camera/blob/b817e9b81041980608d1a3d3e0b08d86e3666382/conversions/to_jpg.cpp).

`0060-gdma-link-cursor-lifecycle.patch` mounts the programmed descriptor head
on a new `START`, resets cached cursor/FSM state on channel reset, and stops
peripheral delivery on `STOP`. `RESTART` preserves the next descriptor rather
than rewinding to the programmed head. Self-clearing command bits are hidden
from guest register reads so read/modify/write cannot replay an old `START`.
An address-only update preserves the active cursor. The offline regression
replays the actual register, descriptor and memory-to-memory C functions
against independent RAM sentinels, including new-ring writes and restart
continuation. These source checks are separate from visible camera lifecycle
and full shared-controller matrix validation.
The `RESTART` continuation and self-clearing register semantics come from the
same pinned ESP-IDF
[`gdma_ll.h`](https://github.com/espressif/esp-idf/blob/735507283d5b2f9fb363a1901172dbd9e847945d/components/hal/esp32s3/include/hal/gdma_ll.h)
and [`gdma_reg.h`](https://github.com/espressif/esp-idf/blob/735507283d5b2f9fb363a1901172dbd9e847945d/components/soc/esp32s3/register/soc/gdma_reg.h).

`0061-gpspi-gdma-channel-lifecycle.patch` checks the actual running GDMA
channel before every GP-SPI DMA pull. Private byte cursors are kept per channel,
so slave/peripheral/channel selection does not reuse another channel's offset.
A GDMA transfer generation changes only on a new `START` or reset. It survives
whole-controller reset before incrementing, preventing an old GP-SPI cursor
from matching a newly reset chain. `STOP` denies descriptor and payload reads;
`RESTART` preserves the paused descriptor and byte offset. The former global
GP-SPI START/RESTART callback is removed, so unrelated transfers do not rewind
an active split transfer. The combined C regression replays the actual GDMA
register/reset logic and GP-SPI transfer functions against independent RAM,
including `START 128 → pull 64 → STOP/reset → pull 64`, legal resume, two
channels/slaves and the complete 64800-byte Canvas split. These checks do not
replace the separate visible guest or shared-controller matrix gates.

`0062-esp32s3-i2s-continuous-dma-completion.patch` separates ESP32-S3 I2S DMA
hardware progress from the evidence-capture window. TX completion now continues
while the guest keeps TX enabled, instead of stopping after two seconds or 128
descriptors. The existing PCM limit remains the evidence bound. Without this
split, a guest that fills the speaker driver ring after the capture window can
block forever even though the virtual controller still has descriptors to
complete.

`0063-core2-touch-buttons.patch` maps `key:a/b/c` on Core2 to the FT5x06
lower touch-button band consumed by M5Unified. The three Core2 buttons are not
the generic GPIO key path; without this explicit panel mode, input lands on
unrelated default GPIOs and `BtnA/B/C` callbacks never observe the press.
The touch mapping is limited to A/B/C; `key:p` must continue to the AXP2101
power-key switch arm. The first revision broke early for every key code and
therefore also swallowed PWR. The replay test now checks that A/B/C enter the
touch branch while the PWR path remains reachable. Final guest sessions observe
callback state 2 for all four controls and no new callback after removal.

`0064-esp32-intmatrix-pending-irq-remap.patch` retains every ESP32 interrupt
matrix input level and recomputes CPU external-interrupt outputs whenever a
source level or mapping changes. The old model forwarded only input edges; a
guest could raise a pending SPI source, rewrite its mapping from unconnected to
a CPU interrupt, and leave the IRQ undelivered forever. The patch also stores
`SPI_SLAVE.TRANS_DONE/TRANS_INTEN` and drives the SPI line as their logical AND.
The same ESP-IDF 5.5.4 Core2 probe times out before the patch and passes `3/3`
after it, with one guest `post_cb` and queued-result completion per run. This
fixes the generic SPI/INTMATRIX completion defect but does not close legacy
UIFlow `RUNTIME-03`; its retained runtime still resets or fails to reach the
display flush callback.

`0065-xtensa-high-priority-irq-cooperative-yield.patch` tracks active Xtensa
level-4/5 handlers and yields at the DPORT handoff ordering points. The classic
ESP32 protocol uses a high-priority interrupt on the peer CPU plus shared SRAM
start/end flags. Large single-thread TCG slices let one CPU clear the previous
completion flags and start another transfer before the handler observed them,
leaving CPU0 waiting for `start` and CPU1 waiting for `end`. The handler yields
after publishing its start flag in `memw`, and the sender yields when the end
path returns through `retw`. A level-5 handler returning to level 4 keeps the
state active; leaving level 4 through RFI/RFE or reset clears it. Guest
instructions, virtual time and interrupt levels are unchanged. The state
machine is active only when TCG icount is enabled; non-icount accelerators do
not gain forced yields. Five independent retries pass with the cooperative
path. This closes the scheduler-induced deadlock, not the remaining legacy
watchdog and application issues.

`0066-esp32-classic-rmt-legacy.patch` replaces the previous unimplemented
classic ESP32 RMT region with an eight-channel register and RMTMEM model.
It implements the legacy IDF driver's memory-size readback, memory-mode TX,
threshold refill, TX_END interrupt and bounded symbol capture. Without the
model, `conf0.mem_size` read as zero and UIFlow1's Neopixel translator
allocated a zero-byte buffer. This is a functional-controller model, not a
GPIO waveform, electrical or physical-timing claim.

`0067-esp32-espnow-controlled-peer-loopback.patch` adds a default-off
`M5SW_ESPNOW_LOOPBACK=1` test fixture for controller-level ESP-NOW delivery.
When enabled, an 802.11 management action frame that the guest wrote through
the normal TX DMA path is echoed back through RX DMA with the peer/source
addresses exchanged; broadcast frames use a fixed locally administered peer.
The stock `espnow`/`m5espnow` Python stack therefore demonstrates unicast,
broadcast, receive-buffer and IRQ delivery without host-side Python values.
This is one virtual peer echo, not an external ESP-NOW peer, encrypted message
delivery, retry/loss behavior, RF, timing or physical-hardware validation.

`0068-core2-dual-spi-panel-routing.patch` attaches the shared ILI9342 panel
sink to both classic ESP32 HSPI/SPI2 and VSPI/SPI3. UIFlow2 Core2 drives the
panel through SPI3, while the public legacy UIFlow firmware's `display.TFT`
path selects HSPI. The old board glue attached only SPI3, so all legacy panel
DMA writes reached a controller without the panel model. A legacy boot probe
now produces visible text and a green rectangle from the original
`m5stack`/`lcd` path. This fixes controller-to-panel routing, not the
remaining normal-WDT startup failure.

`0069-esp32-timg-wdt-feed-unprotected.patch` makes `WDTFEED` reset the current
stage and count regardless of `WDTPROTECT`. ESP-IDF `wdt_hal_feed()` writes
`mwdt_ll_feed()` directly, while configuration writes still require the
unlock key. This separates the hardware feed register semantics from
protected configuration registers and does not disable the watchdog or
change reset timing.

`0070-esp32-uart-tx-virtual-clock.patch` adds the QEMU virtual timestamp to
the existing opt-in `M5SW_UART_TRACE` transmit log. The trace remains disabled
by default and changes no UART data path or guest instruction; it aligns boot
markers, watchdog transitions and handoff traces on one virtual-time axis.

`0071-esp32-ssi-transaction-profile.patch` extends the existing default-off
handoff metrics with exact SSI command, RX-length and
completion-to-next-command gap histograms. The counters are emitted only at an
explicit freezes and reset with the existing metrics state. They do not alter
SPI timing, scheduler behaviour, watchdog configuration or transaction data.

`0072-esp32-ssi-command-correlation.patch` adds bounded sparse
command-length, per-command gap and command-transition tables, each with an
overflow counter. It applies after `0071`, remains freeze-only, and does not
change SPI data or scheduling.

`0073-esp32-ssi-command-pc.patch` adds a bounded sparse
command/CPU/transaction-issuer-PC table and overflow counter. It applies after
`0072`, emits only at an explicit freeze, and does not change SPI data,
scheduling, watchdog or accelerator behavior. The recorded PC is a diagnostic
issuer address: without a matching legacy ELF/MAP, it must be interpreted only
against the BIN segments or sourced ROM linker symbols.

`0074-esp32-spi-panel-dma-dedup.patch` fixes classic ESP32 panel flushes that
were consumed first from `DMA_LINK` descriptors and then replayed through the
64-byte CPU data registers. It skips the duplicate panel sink until the current
command finishes and adds opt-in RAMWR expected/written byte accounting. On
Core2 the hash-pinned M5UI candidate moved from `12736` bytes written into a
`6400`-byte strip to exact delivery and passed both triangle/image frame
oracles. This is a virtual panel data-plane fix; physical DMA/SPI timing remains
separate.

`0075-esp32-legacy-status-cas-correlation.patch` adds freeze-only legacy
Core2 diagnostics for `RDSR(0x05)` status bytes, their preceding `0xBB/64`
address and receive prefix, cache-counter deltas, CPU/PC/PS/IRQ context and
bounded `s32c1i` PC/caller/lock/old-owner/result aggregates. It applies after
`0074` and changes no Flash value, interrupt state, watchdog semantics or
default scheduling. The included failed-`s32c1i` TCG-slice yield is an explicit
default-off negative control; enabling it did not move the normal-WDT reset
boundary and it is not a product fix.

`0076-esp32-external-espnow-peer-bridge.patch` adds a default-off IPv4
loopback UDP bridge between independent controller instances. A management
action frame still leaves the sender through the normal controller TX DMA path
and enters the receiver through the normal RX DMA path; no Python-level payload
or callback is synthesized. Paired session-derived ports are mandatory, the
bridge rejects invalid/equal ports and cannot be combined with `0067`'s
same-guest loopback. This unencrypted external-guest lane does not implement
PMK/LMK, CCMP, loss/retry, RF, antenna or timing.

`0077-esp32-espnow-external-ccmp.patch` adds key-bound AES-CCMP to that
external bridge. The explicit fixture supplies a PMK and plaintext LMK to the
controller boundary; QEMU stores only the AES-128-ECB-wrapped LMK, strips the
guest hardware envelope on TX, encrypts the action body with a fresh PN and
eight-byte MIC, and authenticates RX before normal DMA delivery. A wrong LMK
causes RX authentication failure and no guest callback. The same PMK rule
still permits traffic when both ends use the same on-wire LMK, so this is not
a wrong-PMK negative control. This milestone does not prove guest
`set_pmk`/`add_peer` state propagation, peer add/update/delete, replay
protection, loss/retry, cross-fabric routing, RF, timing or physical hardware.

`0078-esp32-espnow-external-ccmp-replay.patch` adds a monotonic PN guard for
the single external encrypted peer. It records the last successfully
authenticated CCMP PN and drops equal or older PNs after MIC validation but
before normal RX DMA delivery. Authentication failures never advance the
counter. Session realize/cleanup resets the receiver PN state with the wrapped
key state. This is not a multi-peer replay window, key-rotation lifecycle,
loss/retry model or physical-controller validation.

`0079-esp32-espnow-external-ccmp-window.patch` replaces that strict monotonic
guard with a 64-frame authenticated replay window. Newer PNs shift a bitmap;
older unseen PNs inside the window are accepted once; duplicates and packets
older than the window are dropped after MIC validation. This supports bounded
single-peer reordering but remains separate from multi-peer replay windows,
PN wrap, key rotation, loss/retry, RF and physical-controller validation.

`0080-esp32-espnow-guest-key-state.patch` mirrors the classic ESP32 and
ESP32-S3 WiFi crypto key-store MMIO windows. With the external ESP-NOW bridge
configured without runtime-env PMK/LMK, the model arms the highest active
extended key slot only after the guest has written its full 16-byte LMK and
the controller valid bit. Slot clear and replacement reset the active key and
replay state. The bridge still authenticates CCMP at its own RX boundary and
delivers through normal DMA. This closes the stock `set_pmk`/`add_peer` LMK
programming handoff for one external peer; multi-peer key routing, PN wrap,
loss/retry, channel/rate, RF and physical-controller equivalence remain
separate.

`0081-esp32-espnow-peer-fabric.patch` adds an opt-in three-guest fabric mode.
Each controller uses a configured synthetic peer MAC before CCMP encryption,
so the broker never rewrites authenticated address fields after the MIC is
computed. RX preserves the broker-supplied transmitter and the 64-frame
authenticated replay window is selected by source peer MAC, with bounded
state for up to eight peers. The runner connects StopWatch, StickS3 and Core2
to one UDP broker, registers two encrypted peers per guest and duplicates one
real forwarded frame for a per-peer replay negative control. This lane uses a
shared LMK; per-peer LMK routing, PN wrap, loss/retry, RF and physical
controller behavior remain separate.

`0082-esp32-espnow-per-peer-key-routing.patch` captures the stock controller
key-entry metadata written by `hal_crypto_set_key_entry`: the first six bytes
contain the peer MAC and the LMK starts at offset eight. Fabric TX selects the
guest LMK by receiver peer and RX selects it by transmitter peer. Each key slot
keeps its own transmit PN, while the authenticated replay window remains scoped
to the source peer. The runner covers three pairwise LMKs and an intentional
B/A cross-wire negative control; PN wrap, loss/retry, RF and physical-controller
behavior remain separate.

`0083-esp32-espnow-ccmp-pn-exhaustion.patch` makes the 48-bit CCMP transmit
PN fail closed instead of wrapping to zero. An opt-in decimal seed lets the
runner approach the limit through the normal controller bridge, burn the final
PNs and observe explicit exhaustion drops. Reinstalling a new guest LMK resets
that peer's PN chain and the direct pair resumes. Shared-LMK and pairwise-key
fabric regressions remain separate.

`0084-esp32-espnow-loss-channel-rate.patch` adds an eight-byte bridge envelope
for the configured channel and PHY-rate metadata. RX validates the envelope
before CCMP/DMA delivery, rejects frames from another channel, and reports the
delivered frame's envelope channel/rate in controller RX metadata. The
envelope is trusted test-fixture metadata outside CCMP, not an authenticated
security field. The runner uses
a loss proxy, same/different-channel controls, mixed 11/24 Mbps traffic and a
60-second bidirectional soak. This is a deterministic virtual-link model, not
RF propagation, PHY rate adaptation or physical-controller equivalence.

`0085-core2-atecc608.patch` adds the Core2 for AWS ATECC608A slave at 7-bit
address `0x35`. It implements wake/idle/sleep, CryptoAuthentication command
framing, CRC16, 32-byte config reads, lock-word reads and Info revision against
a deterministic locked test configuration. It also fixes classic ESP32 DMA
handling when firmware writes a descriptor address and start bit separately,
and derives command versus pixel data from the GPIO15 DC level. The public
factory firmware changes from `atcab_init=f0` plus abort to
`atecc608: ok: 60 02` and a three-run nonempty `320x240` frame. No production
private key, certificate, ECDSA signing, live trust root or electrical
equivalence is claimed; BMI270 errors in the same firmware remain independent.

`0086-esp32-legacy-cas-episode-profile.patch` extends the freeze-only
`s32c1i` diagnostics with bounded contention episodes. It tracks each CPU's
current contended lock, failed-attempt count, maximum inter-attempt gap and
hold duration, then emits overall and per-lock aggregates at the existing
freeze point. Virtual-clock sampling is skipped while the vCPU is executing a
no-I/O translation block, where QEMU would terminate with `Bad icount read`;
the next I/O-capable observation continues or closes the episode. This changes
diagnostics only and does not alter guest instructions, lock outcomes,
interrupts, watchdog behavior or default scheduling.

`0088-xtensa-contended-cas-fair-yield.patch` addresses the scheduling boundary
exposed by those episodes. A real failed cross-core S32C1I can request a
one-millisecond RR quantum for the next vCPU turn instead of leaving the holder
to run the normal 100-millisecond TCG quantum. The guest CAS result, lock owner,
`-icount` conversion, WDT deadlines and peripheral paths are unchanged. The
behavior is default-off behind `M5SW_XTENSA_CONTENDED_CAS_FAIR_YIELD=1`.
Same-binary five-second A/B reduced S32C1I operations from `1,070,625` to
`91,465`, contended operations from `984,964` to `2,702`, and total episode
time from `2.239772672 s` to `1.017736288 s`, while SSI `0x05`/`0xBB` counts
stayed within eight operations. Normal WDT still reset at TG0 stage 1 in both
lanes, so this is scheduler attribution rather than `RUNTIME-03` closure; see
the [scheduler evidence](../../docs/evidence/2026-10-29-core2-contended-cas-scheduler/README.md).

`0089-xtensa-handoff-pc-trace-io-boundary.patch` makes the existing
default-off, BIN-bound `M5SW_XTENSA_PC_TRACE` helper safe under deterministic
`-icount`. Before the fix, a match inside a no-I/O translation block aborted
QEMU with `Bad icount read`. The patch calls `translator_io_start()` for a
matching PC and keeps a defensive `can_do_io` guard in the helper. Guest
instructions, watchdog deadlines, peripheral paths and default runtime
behavior are unchanged. A short control before the fix terminated at
`Bad icount read` after about `2.351 s` virtual time; the fixed binary
completed both the short trace and repeated 50-second handoff-episode runs.

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
