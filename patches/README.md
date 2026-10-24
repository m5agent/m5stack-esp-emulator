# QEMU and firmware patch index

Last reviewed: `2026-10-25`

This directory stores replayable patches, not QEMU binaries or the `.work/`
build tree. Exact base commits, apply order, reverse-check commands and known
incremental dependencies remain authoritative in each subdirectory README.

## Patch groups

| Group | Base / layer | Purpose | Current boundary |
| --- | --- | --- | --- |
| [`qemu-stopwatch-uiflow2-boot`](qemu-stopwatch-uiflow2-boot/README.md) | Espressif QEMU `da100c909249926b9f4458f18e4f2d216d08f51a` | initial StopWatch/UIFlow2 board boot | historical first board layer |
| [`qemu-multi-board-uiflow2`](qemu-multi-board-uiflow2/README.md) | after StopWatch boot patch | S3, C6 and Core2 board/display/input entrypoints | applies before peripheral and radio layers |
| [`qemu-core2-qemu-esptool`](qemu-core2-qemu-esptool/README.md) | Espressif QEMU `da100c9` worktree | configurable Core2 UART RX scale for ROM `esptool --no-stub` | flashing transport only |
| [`qemu-m5stack-peripherals`](qemu-m5stack-peripherals/README.md) | multi-board and Core2 esptool layers | shared displays, buses, sensors, audio, camera, SD, USB and S3/C6 WiFi data planes | exact incremental order matters; see its README |
| [`qemu-core2-openmac-wifi`](qemu-core2-openmac-wifi/README.md) | multi-board worktree | classic ESP32 WiFi MAC/DMA/user-net model | functional WiFi, not PHY/RF equivalence |
| [`qemu-core2-ble-controller`](qemu-core2-ble-controller/README.md) | after OpenMAC WiFi | classic ESP32 BT RAM/control-register bootstrap | controller bootstrap and stock VHCI boundary |
| [`qemu-core2-native-hci`](qemu-core2-native-hci/README.md) | after Core2 BT bootstrap | H4 transport, HLI event/ACL delivery and no-GDB native HCI | canonical Core2 BLE path; not bit-exact baseband |
| [`qemu-esp32c6-uiflow2-adapters`](qemu-esp32c6-uiflow2-adapters/README.md) | Espressif C6 backend `febae18` | C6 boot, flash/PMP, board peripherals and WiFi support | Zigbee/802.15.4 remains a model gap |
| [`qemu-linux-arm64-cardputerzero`](qemu-linux-arm64-cardputerzero/README.md) | after shared M5Stack peripheral snapshot | BCM2837, audio, USB, Ethernet and Linux board data planes | independent Linux backend |
| [`uiflow2-tab5-emulator`](uiflow2-tab5-emulator/README.md) | UIFlow2/M5GFX/LVGL checkouts | emulator-only Tab5 firmware build guards | simulation infrastructure, not a physical Tab5 PASS |

## Build rules

1. Start from the exact QEMU or firmware source named by the subdirectory
   README.
2. Apply the layer order there. Do not reorder numbered patches by filename
   across different base trees.
3. Apply patches from a matching worktree and retain only intended files.
4. Run `git apply --reverse --check` for every generated patch before commit.
5. Rebuild the affected emulator target and run the narrow runtime test.

The common ESP32 QEMU build used by the repository is:

```bash
ninja -C .work/M5StopWatch-QEMU/build/qemu/build qemu-system-xtensa
```

Some C6 or Linux backends use a separate build directory and target. Consult
their README rather than assuming the ESP32 command built that backend.

## Status rules

- Patch presence proves source availability, not that a device currently
  passes.
- A transport-only patch must not be described as guest/controller support.
- A functional QEMU result must not be described as physical RF, timing,
  security or hardware validation.
- Current patch-backed capabilities are summarized in
  [`docs/project-status.md`](../docs/project-status.md); unresolved model gaps
  are tracked in
  [`docs/runtime-model-gap-register.md`](../docs/runtime-model-gap-register.md).
