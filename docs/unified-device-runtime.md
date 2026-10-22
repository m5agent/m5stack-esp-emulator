# Unified Device Runtime Contract

Date: `2026-10-22`

## Decision

The final simulator contract is one Device Service lease, one QEMU
guest, one firmware image, and one evidence bundle:

```text
Device Service /api/v1
        |
        +-- one QEMU process
              +-- SoC + flash + RAM + PSRAM
              +-- display / touch / buttons / IMU / audio / camera
              +-- WiFi MAC/PHY or equivalent virtual radio path
              +-- BLE controller / HCI path
              +-- serial + framebuffer + input + network evidence
```

The separate `esp-emu` + QEMU lanes remain useful for diagnosis and
regression, but they are transitional only. They must not be presented as a
complete simulated device or as a unified-device PASS.

## Current evidence

- QEMU already owns the modeled M5Stack board peripherals and the common
  display/input/framebuffer path.
- `esp-emu` has validated WiFi/BLE behavior on S3/C6, including same-instance
  WiFi + BLE inside one `esp-emu` guest.
- The QEMU classic-ESP32 experiment at
  `/tmp/m5qemu-core2-openmac.l6vOEl` contains a `misc.esp32_wifi` model and
  reaches WiFi scan plus probe-request transmission, but has not completed
  association or DHCP. This is a prototype, not the final radio model.
- The QEMU runtime does not yet have a complete native WiFi MAC/PHY or BLE
  controller model for the M5Stack product families.

## Integration rule

Do not copy the `esp-emu` executable into a QEMU session and do not run a
second emulator process behind the same Device Service lease. Reuse its
protocol behavior by implementing or linking the equivalent radio/MAC/BLE
device model into the QEMU process. The network test harness may be reused,
but its peer must target the same guest instance.

The public `esp-emulator` repository currently distributes prebuilt release
binaries and installer/tooling rather than the complete Rust implementation.
Reverse engineering or independently implementing the required device
behavior is allowed for the prototype, but the resulting model must be
checked against observed frame formats, register transitions, and guest
boot/network markers. A binary-only observation is not sufficient to claim a
finished chip model.

## Base selection

- **ESP32-S3/C6/Core2:** QEMU is the base because it owns the board models.
- **Tab5:** retain the existing `esp-emu` P4/C6 ESP-Hosted path as a
  documented exception unless QEMU reaches equivalent P4/C6 coverage.
- **Core2 classic ESP32:** extend QEMU with the missing MAC/PHY and Bluetooth
  controller blocks; OpenETH is not a substitute for stock `network.WLAN`.

## Acceptance milestone

First vertical slice: a StickS3 UIFlow2 image in one QEMU guest simultaneously
shows a non-black frame, accepts a physical key/touch event, reads IMU/audio
state, associates with the virtual WiFi SSID, obtains DHCP, completes a
controlled HTTP request, and completes BLE GATT discovery/write. The session
must expose all of these through one `/api/v1` lease and retain the evidence
after completion.

After StickS3 passes, repeat the same contract on CoreS3, Cardputer ADV,
StopWatch, NanoC6/Nesso N1, and then Core2. Each device gets explicit network
and board-peripheral status; no family-wide PASS is inferred from another
device's result.

