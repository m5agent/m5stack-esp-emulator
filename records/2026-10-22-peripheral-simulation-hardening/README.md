# Peripheral simulation hardening

Status: **SIMULATION ONLY**. This record does not claim real-hardware
validation.

## Scope

- Make UIFlow2 peripheral regression fail on missing runtime evidence instead
  of accepting static `checks` metadata.
- Fix PaperColor SPI SD and PaperMono SX1262 DMA routing through SPI3.
- Fix CoreS3/StackChan GC0308 camera VSYNC, GDMA link-start, cyclic descriptor
  and snapshot delivery.
- Fix PaperMono IP2315 I2C `0x75` charger state and `Power.isCharging()`.
- Preserve per-slave DMA routing for CoreS3 M-Bus SD/MAX3421E on SPI2.
- Add BCM2837 Unicam CSI1 register/DMA/frame-end model and IMX219 CCI binding.
- Validate a real Linux V4L2 RG10 capture buffer and deterministic frame hash.
- Make IMX219 output depend on mode/window/timing/exposure/gain/orientation and
  test-pattern registers, with V4L2 controls and live QOM inspection.
- Add GL852G TT-compatible Full/Low-Speed downstream routing and validate both
  Full-Speed SR9900A Ethernet and a Low-Speed USB HID.
- Read the source hardware catalog during CI validation and add a Device
  Center-facing peripheral inventory covering all 155 hardware requirements.
- Validate peripheral inventory in both directions so every modeled component
  must appear in the device hardware manifest and vice versa.
- Require every simulated peripheral model to map to a runtime matrix case
  with serial/QOM/PCM/RMT/SD/frame evidence or to an external test/evidence
  pair, and require the mapped machine/device to match `tested_devices`.
- Expose the inventory through `/api/peripherals` and
  `/api/peripherals/<device>` for Device Center integration.
- Expose a machine-readable runtime interface map through
  `/api/peripheral-interfaces` and `/api/peripheral-interfaces/<model>`.
- Add charging/discharging Tab5 scenarios for the active-low PI4IOE CHG_STAT
  path and verify both states through the official `Power.isCharging()` API.
- Gate new devices on peripheral completeness with an explicit, review-dated
  Tab5 backend exemption instead of allowing silent partial registrations.
- Bind every device to a matching runtime case group and expose those cases in
  the inventory so Device Center can schedule by device instead of by ad-hoc
  case IDs.
- Show peripheral completeness, component interfaces and runtime case counts
  in the simulator gallery and device page.
- Specify the P4 backend interfaces required for dynamic I2C, I2S/PCM,
  MIPI-CSI, USB Host, SDIO and IRQ side effects, with explicit Tab5 acceptance
  cases.
- Build a matching UIFlow2 Core2 ELF and symbolize intermittent failures down
  to the flash-cache cross-core handshake instead of relying on the firmware's
  ambiguous `Cache error` label.
- Isolate the NanoC6 and Nesso N1 ESP32-C6 board assemblies so Nesso display,
  SX1262, board I2C and forced GPIO lines are not attached to NanoC6.
- Validate NanoC6 RGBPWR/WS2812, GPIO9 button, GPIO7 blue LED and RMT IR paths.
- Add a StackChan combined probe for BMI270, BM8563 RTC, AW9523, INA226 and
  NEC IR TX/RX.

## Verification

```text
platform catalog: PERIPHERAL_CATALOG_OK
platform unit tests: 42 PASS
Core2 matching ELF: UIFlow2 release/2.5.3 + ESP-IDF v5.5.4, PASS
Core2 IROM similarity: same load address/length, 99.49% identical bytes
Core2 panic symbolization: `spi_flash_op_block_func` + `cache_ll_l1_disable_cache`
runtime interface map: 60/60 simulated models covered
per-device runtime groups: 14/14 devices covered by matching machine/probe cases
runtime case assignment: 63/63 matrix and 7/7 external cases assigned exactly once
device page peripheral contract panel: StickS3 8/8 components, PASS
gallery completeness summary: 13/14 devices peripheral-complete, PASS
Tab5 partial-device UI: 17 components, 15 blocker entries and dated exemption, PASS
QEMU patch 0006 reverse check: PASS
QEMU patch 0007 reverse check: PASS
QEMU patch 0008 reverse check: PASS
QEMU patch 0009 reverse check: PASS
QEMU patch 0011 reverse check: PASS
QEMU C6 patch 0002 reverse check: PASS
QEMU aarch64 build: PASS
QEMU xtensa build: PASS
QEMU ESP32-C6 build: PASS
PaperColor SD raw sector 100: match=True
PaperMono LoRa UI marker: PASS
CoreS3/StackChan camera: snapshot ok 320x240 153600 bytes
CardputerZero camera: /dev/video0, 640x480 RG10, 614400 bytes
CardputerZero default frame SHA256: 5568cf027da59228168e211e27283adaad4eaf6c299a4ad44026b0b703f7af4c
CardputerZero controlled-pattern SHA256: d837dbbc02798310b0f7f940cc5e1c6e469ef5a7ffbe7feb8d92f0c8a8f5bcbe
CardputerZero combined probe: PASS (137.287 s), including FS Ethernet through
GL852G TT and the full keyboard/audio/charging/camera path
SR9900A direct-root full-speed Ethernet round-trip: PASS
SR9900A full-speed Ethernet through GL852G TT: PASS
Low-speed USB HID through GL852G TT: PASS
NanoC6 RGB/button/blue LED: PASS
NanoC6 RMT WS2812 GRB: 00ff00
Nesso N1 peripheral regression after board isolation: PASS
StackChan AW9523/INA226/IR: PASS
StackChan BMI270 accel/gyro through the official API: PASS
StackChan BM8563/PCF8563 RTC injection, write/read and progression: PASS
StackChan/CoreS3 LTR553 ALS 640 + proximity 321: PASS
StackChan INA226 power: 4.00 V / 0.25 A / 1.00 W
StackChan AW9523 output/input: 1/0
StackChan NEC IR: 34 symbols, address 0x56, command 0xA3
StackChan peripheral suite: 8/8 cases PASS
Tab5 SIT3088 RS-485 UART1 G20/G21/G34: TX 15 bytes, RX 15 bytes, PASS
Tab5 RS-485 UI framebuffer: 1280x720, touch=1, changed_channels=33048, PASS
Tab5 I2C peripheral UI framebuffer: 1280x720, touch=1, changed_channels=880, PASS
Tab5 charger scenarios: CHG_STAT input 0x00/0x40, CHG_EN output bit 1;
Power.isCharging() returns charging/discharging accordingly, PASS
Tab5 peripheral scenario runner: 2/2 PASS (charging-normal and discharging-low)
Tab5 INA226 charging API: 8000 mV, 1248 mA, 87%, PASS
Tab5 INA226 discharging API: 7200 mV, -501 mA, 37%, PASS
Tab5 machine.RTC RX8130 write/readback: 2026-10-22 12:34:56, PASS
BCM2835 SPI DMAEN 32-bit FIFO + write-only panel backpressure: PASS
CardputerZero factory UI startup to LVGL 320x170: PASS
CardputerZero factory UI first frame: PASS (54400/54400 non-black pixels, 127 RGB565 colors)
UIFlow2 peripheral matrix: 63/63 cases, 246/246 checks PASS
(clean final run; a separate 6-run Core2 stress check reproduced the known
intermittent boot cache panic once)
```

The full UIFlow2 peripheral matrix is run with:

```bash
python3 tests/uiflow2/run_peripheral_matrix.py \
  --out-dir /tmp/m5-uiflow2-peripheral-matrix
```

Final matrix result is recorded in the task response and the corresponding
`summary.json`. The runner rejects a case that has no serial, QOM, PCM, RMT,
disk or frame-marker evidence source, and guest panic/Traceback/`status=error`
or `FAIL` is treated as a test failure.

The CardputerZero camera/combined path is reproducible with:

```bash
python3 tests/cardputer_zero/run_camera_probe.py
python3 tests/cardputer_zero/run_camera_probe.py --controls
python3 tests/cardputer_zero/run_usb_ethernet_probe.py --full-speed --tt-compat
python3 tests/cardputer_zero/run_usb_low_speed_probe.py
python3 tests/cardputer_zero/run_full_probe.py
python3 tests/uiflow2/run_nanoc6_peripherals.py
```

## Evidence artifacts

- `tab5-charging-scenarios-2026-10-22.json`: charging/discharging scenario
  summary and exact esp-emu commands.
- `runtime-interfaces-2026-10-22.json`: generated Device Center runtime
  interface snapshot for all 65 registered models.
- `peripheral-matrix-summary-2026-10-22.json`: full 63-case peripheral matrix
  summary with 246/246 passing checks.
- `tab5-charging-ui-2026-10-22.png`: native 1280x720 Tab5 framebuffer after
  touch, showing `CHG in:00 api:True en:1`.
- `sticks3-peripheral-contract-2026-10-22.png`: device page showing the
  StickS3 8/8 peripheral completeness panel and component interface details.
- `device-center-peripheral-overview-2026-10-22.png`: gallery summary showing
  13/14 peripheral-complete devices and the StopWatch 12-component contract.
- `core2-panic-serial-2026-10-22.log`: captured intermittent panic with
  both-core registers and backtraces.
- `core2-panic-symbolized-2026-10-22.json`: symbolized PCs and IROM matching
  evidence.
- `core2-symbol-build-2026-10-22.json`: reproducible ELF/app hashes and source
  revisions.

## Remaining hardware-backend gaps

- StackChan: `Imu.getGyro()` initially appeared broken because the test
  injected a nonzero rate before `M5.begin()` and M5Unified calibrated it as
  zero bias. Injecting after boot now returns the expected 10/-20/30 dps.
- StackChan: official schematics identify BM8563 at 0x51. The board model now
  attaches a PCF8563-compatible device there instead of the incorrect RX8130
  at 0x32.
- StackChan and CoreS3 now enumerate and exercise the carrier LTR553 ALS/PS
  registers at 0x23; proximity is an 11-bit QOM-injected register value.
- Tab5 RS-485 is now closed through esp-emu's `--uart1-tcp` byte peer; only
  the native P4 CSI/I2S/USB/SDIO and dynamic-I2C gaps remain.
- Tab5 framebuffer capture now prefers native `riscv64-elf-gdb`; the Docker
  fallback is no longer on the critical path. The RS-485 probe captures the
  real 1280x720 frame and verifies touch-driven redraw.
- The existing I2C register probe was rerun through native GDB: INA226,
  PI4IOE1/2 and the extra 0x55 device are visible, while BMI270 still reports
  CHIP_ID 0x00 and remains a documented partial gap.
- Tab5 PI4IOE CHG_STAT input and CHG_EN output registers reach
  `Power.isCharging()`. The active-low input returns charging for `0x00` and
  discharging for `0x40`. IP2326 analog current/termination behavior and hot
  state injection remain partial.
- Tab5 INA226 bus/current register preload reaches the official Power API as
  `8000 mV / 1248 mA / 87%`. Dynamic host injection remains unavailable.
- Tab5 `machine.RTC()` writes and reads back `2026-10-22 12:34:56` through
  RX8130 registers; progression and dynamic host time injection remain absent.
- Tab5: SC2356 MIPI-CSI, ES8388/ES7210 P4 I2S PCM, P4 USB Host, SDIO,
  ST7123 register-level touch and IP2326 charger remain blocked by the native
  P4 backend.
- CardputerZero: the GL852G TT path is functional rather than cycle-accurate;
  USB split transaction timing is not modelled packet-by-packet.
- Core2: AXP192 is functionally passing and the final full matrix was clean,
  but a separate six-run stress check hit the pre-existing MicroPython cache
  panic once. See `docs/core2-cache-panic-investigation.md`; single-thread
  TCG and SMP1 experiments did not resolve it.
- No real-hardware validation was performed for these changes.
