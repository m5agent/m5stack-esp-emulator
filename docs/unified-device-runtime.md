# Unified Device Runtime Contract

Date: `2026-10-23`

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
- QEMU now owns a functional ESP32-S3 WiFi MAC/DMA model at `0x60033000`.
  Stock UIFlow2 `network.WLAN` completes scan, association, DHCP and a
  controlled HTTP request while the same `m5sticks3` guest drives the panel,
  PMIC, IMU, buttons and I2S speaker.
- The same QEMU S3 NIC is integrated into the `m5cores3` machine. One CoreS3
  guest runs its 320x240 display, touch, AXP2101, BMI270, AW88298 speaker,
  WiFi association/DHCP/HTTP and external HCI BLE exchange.
- The Cardputer ADV machine uses the same NIC with its display, TCA8418
  keyboard, BMI270, ES8311/NS4150B audio, WiFi DHCP/HTTP and external HCI BLE
  exchange in one guest.
- The StopWatch machine uses the same NIC with its 466x466 CO5300 display,
  CST820 touch, M5PM1 power, M5IOE1 G10/AW8737A amplifier, BMI270, ES8311
  audio, WiFi DHCP/HTTP and external HCI BLE exchange in one guest.
- The AtomS3R machine uses the same NIC with its 128x128 display, GPIO41
  button, BMI270, BMM150, LP5562, WiFi DHCP/HTTP and external HCI BLE
  exchange in one guest.
- The PaperColor machine uses the same NIC with its 400x600 Spectra 6
  display, GPIO buttons, M5PM1, SHT40, ES8311/AW8737A audio, WiFi DHCP/HTTP
  and external HCI BLE exchange in one guest.
- The PaperMono machine uses the same NIC with its 480x800 SSD1677
  display, FT6336 touch, GPIO keys, M5PM1/IP2315, BMI270, RX8130, RGB,
  GPIO42 speaker, WiFi DHCP/HTTP and external HCI BLE exchange in one guest.
- The StickS3 unified HCI-UART build routes real NimBLE H4 traffic through
  QEMU UART1 to a Bumble controller. An external peer completes NUS discovery,
  subscription, write, guest receive and notify ACK in the same QEMU process.
- `esp-emu` has validated WiFi/BLE behavior on S3/C6, including same-instance
  WiFi + BLE inside one `esp-emu` guest.
- The QEMU classic-ESP32 experiment contains a `misc.esp32_wifi` model and
  completes scan, association, DHCP and controlled HTTP in the same guest.
  A following BT bootstrap exposes the 64 KiB BT RAM/control page and lets
  stock UIFlow2 activate NimBLE and enable advertising.
- The native QEMU Core2 BT bootstrap does not yet expose an external peer.
  A separate HCI-offload build now routes NimBLE's H4 traffic through QEMU
  UART1 to Bumble and passes external scan/connect/NUS write/notify 5/5.
  Device Service `profile=core2-hci-gatt` exposes the same exchange plus
  serial/frame/QOM/peer evidence through one `/api/v1` lease.
  The remaining native boundary is still the classic ESP32
  controller/radio/timer path, not UIFlow2's Python BLE API.

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
  Current optional patches cover WiFi user-net and BLE advertising control.
  The HCI-offload lane closes host-side link/GATT behavior for a test build,
  but does not replace the native controller/radio model.

## Acceptance milestone

First vertical slices are StickS3, CoreS3, Cardputer ADV, StopWatch, AtomS3R,
PaperColor and PaperMono. Each runs one UIFlow2 image in one QEMU guest that
simultaneously shows a non-black frame, accepts a physical key/touch event,
reads device state and audio where available, associates with the virtual
WiFi SSID, obtains DHCP, completes a controlled HTTP request, and completes
BLE GATT discovery/write. Each session exposes all checks through one
`/api/v1` lease and retains a combined evidence bundle.

Status: **PASS for the simulation-only StickS3, CoreS3, Cardputer ADV,
StopWatch, AtomS3R, PaperColor and PaperMono slices** through
`runtime=qemu-ble`, the seven unified profiles, and retained Device Service evidence ZIPs containing
serial, frame, audio PCM where present, QOM, network, BLE peer log and
manifest hashes. All probes use an open virtual AP on one fixed channel;
WPA2/WPA3 security behavior is not modelled. BLE is host-controller HCI data
over an HCI-UART test build, not a native ESP32-S3 radio/controller model.

The S3 NIC models the guest-visible MAC, DMA descriptors, interrupt and
user-net frame path, but not a complete PHY/rate/security/RF model. The classic
ESP32 LX6 path still contains separate PHY bring-up stubs. A successful boot log
or PHY-ready register therefore does not by itself mean that the device is
online.

For the rollout, repeat the same contract on NanoC6/Nesso N1 and then Core2.
Each device gets explicit network and board-peripheral status; no
family-wide PASS is inferred from another device's result.

