# Unified Device Runtime Contract

Date: `2026-10-24`

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

### Current conclusion

- The product contract is still one lease, one guest, one firmware and one
  evidence bundle. It is not satisfied by joining separate emulator lanes.
- Eleven S3/C6 profiles satisfy the current board + WiFi + HCI-UART BLE slice;
  StickS3 and Nesso N1 also have opt-in public DNS/HTTP evidence.
- Core2 `core2-native-hci` satisfies the five-lease functional baseline:
  frame, QOM, WiFi/public network, external NUS GATT, pcap and evidence, with
  no GDB bridge.
- Core2 short extended-run is now **PASS**. Historical hold failures included
  `IllegalInstruction` in `semphr_give_wrapper` and `InstrFetchProhibited`
  at `PC=0`. They were tied to nested guest execution from non-halted
  cache-disabled WiFi/controller contexts and incomplete caller-saved sreg
  restoration. `0005` fixes both; two independent `5×10s` batches pass
  `10/10`, three independent `60s` holds pass `3/3`, and two independent
  `120s` holds pass `2/2`, with zero HLI errors and empty queues. This is not
  a multi-hour soak, more than twenty reconnect cycles or physical cache/PSRAM proof.
  A further two `120s` holds keep the BLE peer connected for the full hold,
  with `peer-closed=0`, zero TX queue depth and no last error.
- Same-guest reconnect is **PASS** for twenty cycles. The historical failure was
  caused by the Bumble compatibility layer returning a forbidden Command
  Status for `HCI_Host_Number_of_Completed_Packets (0x0c35)`; the next
  `LE Set Advertising Data (0x2008)` consumed the stale ACK and received
  `BLE_HS_ECONTROLLER (12)`. Three independent stock-firmware leases now
  complete twenty NUS GATT cycles each, with guest RX and notification in every
  cycle, zero reset traces, 577/577 HLI posts/consumption and
  connection/L2CAP/GATT pools back at `3/9/3`. Active-link hold and reconnect
  remain separate gates, but both now pass. The first ten-cycle attempt exposed
  a Device Service 30-second completion-wait cap; the wait now uses the
  session ready timeout and has a regression test.
- Current blockers, not historical explanations, are owned by
  [project status](project-status.md) and [Backlog](project-backlog.md). The
  device bullets below preserve implementation evidence and must not be read
  as a second current-status page.

### Per-device evidence detail

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
  10/10 with no retry. The same scheduler now applies to all six Core2
  peripheral cases and the Core2 UI matrix; the latest 67-case full matrix
  passed every case on its first attempt with automatic retries disabled.
- A separate stock UIFlow2 Core2 runner leaves the built-in controller build
  unchanged and intercepts the firmware's real `esp_vhci_host_*` boundary.
  H2C/C2H are bridged to Bumble, and an external peer completes NUS discovery,
  subscription, write, guest receive and notify ACK 5/5. The GDB-mediated
  path is retained only as a diagnostic/compatibility profile.
- The same stock VHCI transport is now selectable in
  `tests/uiflow2/unified_core2/run_test.py --ble-transport native-vhci`.
  Display/touch, audio, QOM, WiFi/DHCP, public DNS/HTTP and the external NUS
  GATT exchange share one QEMU guest and passed 3/3. Device Service exposes
  the same path as legacy `qemu-unified/profile=core2-native-vhci` with a
  matching `elf_artifact_id`.
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
- Linux runs the same StickS3 guest inside a private network namespace with no
  external route. Controlled DNS returns allow A / deny NXDOMAIN, a generated
  test CA exercises TLS Host allow/deny as HTTP 200/403, and pcap records the
  same decisions. A separate nftables policy enforces exact IPv4
  IP/protocol/port endpoints and uses veth/NAT for allowed external traffic.
  This is not a worker VM sandbox or external IPv6 implementation.
- `esp-emu` has validated WiFi/BLE behavior on S3/C6, including same-instance
  WiFi + BLE inside one `esp-emu` guest.
- The QEMU classic-ESP32 path contains the OpenMAC `misc.esp32_wifi` model and
  completes scan, association, DHCP and controlled HTTP in the same guest.
  A following BT bootstrap exposes the 64 KiB BT RAM/control page and lets
  stock UIFlow2 activate NimBLE and enable advertising.
- Device Service `profile=core2-native-hci` is now the canonical stock
  internal-controller path. `HCI-4` passed five independent `/api/v1`
  leases, each combining a 320x240 frame, 27-node QOM snapshot, WiFi
  DHCP/HTTP, public DNS/HTTP, external NUS GATT, pcap and a session-bound
  evidence ZIP. The profile resolves QEMU hook and HLI addresses from the
  matching ELF and does not start a GDB bridge.
  Legacy `profile=core2-native-vhci` still resolves fixed VHCI call addresses
  from the ELF, but GDB pauses the guest, injects callbacks and supplies the
  synthetic return. Its repeated-lease result was `1/2`, so it remains an
  explicit diagnostic/compatibility path only.
  A separate HCI-offload build also routes NimBLE's H4 traffic through QEMU
  UART1 to Bumble and passes external scan/connect/NUS write/notify 5/5.
  The remaining boundary is a bit-exact classic ESP32 controller/baseband,
  physical cache/PSRAM equivalence, more than twenty reconnect cycles, multi-hour
  coexistence/soak and hardware, not UIFlow2 API or Device Service integration.
- The replacement QEMU native-HCI path has passed the staged gates:
  `HCI-1` host transport passes, `HCI-2` captures the first stock Reset
  `01030c00` without GDB, and `HCI-3a` is a diagnostic single-packet check
  that invokes the registered receive callback with status 0, emits
  send-available and observes the guest's next H2C command. The callback
  route is not accepted as the production controller-to-host backend.
  The retained HLI patch delivered a real Reset Complete in 5/5 runs, and the
  `0003` API-boundary transaction plus `0004` CCOUNT TB-yield now complete the
  full external NUS GATT sequence in 5/5 runs. The previous notification
  timeout was a probe-size error: 21 payload bytes produced a 24-byte ATT PDU
  over the default 23-byte MTU. A 15-byte probe yields a 17-byte ATT PDU and
  reaches L2CAP, ATT, the Python GATT write handler, notify and the Bumble ACK.
  `HCI-3b` is closed in the standalone runner. `HCI-4` repeated Device
  Service leases now pass on `core2-native-hci` with `gdb_bridge=false`.
  The legacy GDB profile remains available for diagnosis only.

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
  while HCI-UART offload remains a separate test build. The canonical
  `core2-native-hci` profile uses ELF-derived API/HLI hooks without a
  debugger. None of these paths executes the bit-exact Espressif BT
  baseband/controller.

## Acceptance milestone

First vertical slices are StickS3, CoreS3, Cardputer ADV, StopWatch, AtomS3R,
PaperColor, PaperMono, StackChan, StamPLC, NanoC6, Nesso N1 and
environment-gated Core2. Each runs one UIFlow2 image in one QEMU guest that
simultaneously exercises its board peripherals, associates with the virtual
WiFi SSID, obtains DHCP, completes a controlled HTTP request, and completes
BLE GATT discovery/write. Each session exposes all checks through one
`/api/v1` lease and retains a combined evidence bundle.

Status: **PASS for the eleven S3/C6 slices and the five-lease Core2
`core2-native-hci` functional baseline** through `runtime=qemu-unified`
(legacy `qemu-ble` remains accepted). Core2 `5×10s` / `3×60s` / `2×120s`
extended-run is also **PASS**; multi-hour soak remains open. The eleven
S3/C6 unified profiles retain Device Service evidence ZIPs containing
serial, frame, audio PCM where present, QOM, network, BLE peer log and
manifest hashes. QEMU radio leases also retain a pcap and a payload-hash-only
summary. S3/C6 probes use one open fixed-channel virtual AP; Core2
OpenMAC advertises its open test-AP set and associates with `myssid`.
WPA2/WPA3 security behavior is not modelled. Device Service BLE remains
host-controller HCI data over an HCI-UART test build. The separate stock Core2
path reaches external GATT without that firmware rebuild. Its canonical
`core2-native-hci` service profile uses an in-process QEMU device, firmware
HLI/API-boundary hooks and Bumble, with no GDB bridge, and passed five
  independent leases. The legacy `core2-native-vhci` profile uses a GDB bridge
  and is diagnostic only. Two independent `5×10s` batches, three `60s` holds,
  two `120s` holds, plus two active-BLE `120s` holds pass with
  `hli-errors=0` and empty queues. Three independent leases also complete twenty
  reconnect cycles each. Core2 still misses bit-exact controller/baseband,
  physical cache/PSRAM equivalence, more than twenty connection cycles,
  multi-hour coexistence and hardware validation.
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
private network namespace and refuses to fall back when namespace creation
fails. `lab-only` has no external route; `allowlist` may use a per-session
veth/NAT only with nftables default-drop rules. Namespace proof does not
establish RF behavior or malicious-firmware safety.

Each device gets explicit network and board-peripheral status; no
family-wide PASS is inferred from another device's result.

