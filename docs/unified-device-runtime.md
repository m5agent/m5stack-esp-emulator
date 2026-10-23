# Unified Device Runtime Contract

Date: `2026-10-23`

Current device availability is tracked in
[Project current status](project-status.md); unfinished work is tracked in the
[project backlog](project-backlog.md). This document defines the acceptance
contract for a complete virtual device, not the deployment status page.

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
- The StackChan machine uses the same NIC with its 320x240 ILI9342 display,
  FT6336/Si12T touch, GC0308 camera, BMI270/BMM150, power monitors, audio,
  NFC, IR and two-servo bus. WiFi DHCP/HTTP and external UART2 HCI BLE run in
  the same guest while UART1 remains dedicated to the servos.
- The StamPLC machine keeps its display, keys/RGB, relay/input banks, CAN,
  PWR-485 and buzzer in the same guest as WiFi DHCP/HTTP and external UART1
  HCI BLE. UART2 remains the PWR-485 bus on G0/G39/G46.
- The environment-gated Core2 machine combines display/touch,
  AXP2101/INA3221, MPU6886, PCF8563, NS4168/SPM1423 audio, OpenMAC WiFi
  DHCP/HTTP, public IPv4 DNS/HTTP and UART1 HCI BLE in one `m5core2` guest.
  QOM injection does not pause the guest, and radio launches use deterministic
  `tcg,thread=single` plus `icount`; ten independent first attempts passed
  10/10 with no retry.
- A separate stock UIFlow2 Core2 runner leaves the built-in controller build
  unchanged and intercepts the firmware's real `esp_vhci_host_*` boundary.
  H2C/C2H are bridged to Bumble, and an external peer completes NUS discovery,
  subscription, write, guest receive and notify ACK 5/5. This is validated
  controller-boundary behavior, not a bit-exact Espressif BT baseband model.
- The same stock VHCI transport is now selectable in
  `tests/uiflow2/unified_core2/run_test.py --ble-transport native-vhci`.
  Display/touch, audio, QOM, WiFi/DHCP, public DNS/HTTP and the external NUS
  GATT exchange share one QEMU guest and passed 3/3. Device Service exposes
  the same path as `qemu-unified/profile=core2-native-vhci` with a matching
  `elf_artifact_id`.
- NanoC6 combines real UIFlow2 RGB/button/IR paths, QEMU ESP32-C6 WiFi
  scan/association/DHCP/HTTP and UART1 HCI BLE in one C6 guest.
- Nesso N1 combines its display/touch and peripheral set with QEMU ESP32-C6
  WiFi DHCP/HTTP and UART1 HCI BLE in one C6 guest.
- The StickS3 unified HCI-UART build routes real NimBLE H4 traffic through
  QEMU UART1 to a Bumble controller. An external peer completes NUS discovery,
  subscription, write, guest receive and notify ACK in the same QEMU process.
- The StickS3 and Nesso N1 unified runners can additionally require public
  DNS and an IPv4 HTTP request in that same guest. This is an opt-in
  host-network check because external availability is not deterministic in
  CI; the default regression path remains a controlled local HTTP fixture.
- `esp-emu` has validated WiFi/BLE behavior on S3/C6, including same-instance
  WiFi + BLE inside one `esp-emu` guest.
- The QEMU classic-ESP32 path contains a `misc.esp32_wifi` model and
  completes scan, association, DHCP and controlled HTTP in the same guest.
  A following BT bootstrap exposes the 64 KiB BT RAM/control page and lets
  stock UIFlow2 activate NimBLE and enable advertising.
- Device Service `profile=core2-native-vhci` now exposes the stock
  internal-controller path through one `/api/v1` lease. A real lease passed
  board/display/touch, QOM, audio, WiFi/DHCP, controlled HTTP, public DNS/HTTP
  and external NUS GATT, and retained frame, pcap, bridge and peer evidence.
  A separate HCI-offload build also routes NimBLE's H4 traffic through QEMU
  UART1 to Bumble and passes external scan/connect/NUS write/notify 5/5.
  The remaining native boundary is removing the GDB dependency and executing
  a bit-exact classic ESP32 controller/baseband, not UIFlow2's Python BLE API
  or Device Service integration.

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
  The stock VHCI bridge now closes external advertising/connection/GATT at the
  controller API boundary in both BLE-only and same-guest unified runners,
  while HCI-UART offload remains a separate test build. Neither executes the
  bit-exact Espressif BT baseband/controller.

## Acceptance milestone

First vertical slices are StickS3, CoreS3, Cardputer ADV, StopWatch, AtomS3R,
PaperColor, PaperMono, StackChan, StamPLC, NanoC6, Nesso N1 and
environment-gated Core2. Each runs one UIFlow2 image in one QEMU guest that
simultaneously exercises its board peripherals, associates with the virtual
WiFi SSID, obtains DHCP, completes a controlled HTTP request, and completes
BLE GATT discovery/write. Each session exposes all checks through one
`/api/v1` lease and retains a combined evidence bundle.

Status: **PASS for the simulation-only StickS3, CoreS3, Cardputer ADV,
StopWatch, AtomS3R, PaperColor, PaperMono, StackChan, StamPLC, NanoC6,
Nesso N1 and Core2 slices** through `runtime=qemu-unified` (legacy `qemu-ble`
remains accepted), the twelve unified profiles, and retained Device Service
evidence ZIPs containing
serial, frame, audio PCM where present, QOM, network, BLE peer log and
manifest hashes. QEMU radio leases also retain a pcap and a payload-hash-only
summary. S3/C6 probes use one open fixed-channel virtual AP; Core2
OpenMAC advertises its open test-AP set and associates with `myssid`.
WPA2/WPA3 security behavior is not modelled. Device Service BLE remains
host-controller HCI data over an HCI-UART test build. The separate stock Core2
VHCI runners reach external GATT without that firmware rebuild, including a
same-guest board+WiFi+public-network variant, but use a GDB-to-Bumble
controller bridge rather than a bit-exact ESP32 controller. That bridge is
available as `qemu-unified/profile=core2-native-vhci`; replacing the debug
backend is the open production item.
StickS3 and Nesso N1 also pass public DNS and HTTP when their runners are
started with `--require-public-network`; this does not imply TLS validation or
stable access to arbitrary internet services. Core2 now includes public DNS
and HTTP in the default unified evidence.

The S3/C6 NIC models the guest-visible MAC, DMA descriptors, interrupt and
user-net frame path, but not a complete PHY/rate/security/RF model. The classic
ESP32 LX6 path still contains separate PHY bring-up stubs. A successful boot log
or PHY-ready register therefore does not by itself mean that the device is
online.

Untrusted sessions can request
`network.policy.isolation=namespace` on a Linux worker. The runner creates a
private network namespace with no external route and refuses to fall back when
namespace creation fails. Namespace proof does not establish RF behavior or
malicious-firmware safety.

Each device gets explicit network and board-peripheral status; no
family-wide PASS is inferred from another device's result.

