# Network simulation plan

Date: `2026-10-23`

## Current state

Network support exists in the `esp-emu` runtime, but it is not yet integrated
as a validated feature of every M5Stack virtual host.

What is already available:

- `esp-emu` exposes WiFi SoftAP support, WPA2/WPA3, DHCP, user-mode networking,
  TAP/vmnet backends, DNS and `hostfwd`;
- the bundled WASM runtime exposes WiFi configuration and Ethernet-frame
  injection/drain APIs;
- Tab5 starts the C6 ESP-Hosted network adapter process with `--net user`;
- CardputerZero has a separate SR9900A Ethernet path and frame round-trip.

Validated through `2026-10-23`:

- `platform/tools/network_lane.py` runs isolated `esp-emu` sessions and emits
  hashed `evidence.json`;
- StickS3 and CoreS3 ESP-IDF WiFi association, DHCP and a controlled 1 MiB
  HTTP/TCP download pass;
- NanoC6 and Nesso N1 pass the same WiFi/DHCP/HTTP path on ESP32-C6;
- ESP-IDF C6 `bleprph_wifi_coex` passes WiFi/DHCP while Bumble connects,
  discovers GATT, writes and reads back a characteristic;
- StickS3 UIFlow2 `network.WLAN` scan, association and DHCP have passed;
- StickS3 UIFlow2 `BLEUARTServer` passes external Bumble scan, connection, NUS
  GATT discovery, subscription, write and guest-side receive callback;
- a StickS3 unified QEMU profile keeps display/buttons/IMU/audio, WiFi
  scan/association/DHCP/HTTP, and HCI-UART BLE NUS in one guest process and
  exposes the combined evidence through one Device Service lease;
- a CoreS3 unified QEMU profile keeps display/touch, AXP2101/BMI270/audio,
  WiFi scan/association/DHCP/HTTP, and HCI-UART BLE NUS in one guest process
  and exposes the combined evidence through one Device Service lease;
- a Cardputer ADV unified QEMU profile keeps display/keyboard, BMI270/audio,
  WiFi scan/association/DHCP/HTTP, and HCI-UART BLE NUS in one guest process
  and exposes the combined evidence through one Device Service lease;
- a StopWatch unified QEMU profile keeps display/touch, M5PM1,
  M5IOE1/AW8737A audio, BMI270, WiFi scan/association/DHCP/HTTP, and
  HCI-UART BLE NUS in one guest process and exposes the combined evidence
  through one Device Service lease;
- an AtomS3R unified QEMU profile keeps display/button, BMI270, BMM150,
  LP5562, WiFi scan/association/DHCP/HTTP, and HCI-UART BLE NUS in one guest
  process and exposes the combined evidence through one Device Service lease;
- a PaperColor unified QEMU profile keeps display/buttons, M5PM1, SHT40,
  ES8311/AW8737A audio, WiFi scan/association/DHCP/HTTP, and HCI-UART BLE
  NUS in one guest process and exposes the combined evidence through one
  Device Service lease;
- a PaperMono unified QEMU profile keeps display/touch, M5PM1/IP2315,
  BMI270, RX8130, RGB, GPIO42 speaker, WiFi scan/association/DHCP/HTTP and
  HCI-UART BLE NUS in one guest process and exposes the combined evidence
  through one Device Service lease;
- a StackChan unified QEMU profile keeps display/touch, camera,
  IMU/magnetometer, power/audio/IR/NFC/servo, WiFi
  scan/association/DHCP/HTTP and UART2 HCI BLE NUS in one guest process and
  exposes the combined evidence through one Device Service lease;
- a StamPLC unified QEMU profile keeps display/keys/RGB, relay/input banks,
  INA226, LM75, RX8130, TWAI CAN, PWR-485, buzzer, WiFi
  scan/association/DHCP/HTTP and UART1 HCI BLE NUS in one guest process and
  exposes the combined evidence through one Device Service lease;
- the environment-gated Core2 unified profile keeps display/touch,
  AXP2101/INA3221, MPU6886, PCF8563, NS4168 speaker, SPM1423 microphone,
  OpenMAC WiFi DHCP/HTTP and UART1 HCI BLE NUS in one `m5core2` guest;
- NanoC6 runs RGB/button/IR, QEMU ESP32-C6 WiFi scan/association/DHCP/HTTP
  and UART1 HCI BLE NUS in one C6 guest and one Device Service lease;
- Nesso N1 runs its display/touch/peripheral set, QEMU ESP32-C6 WiFi
  scan/association/DHCP/HTTP and UART1 HCI BLE NUS in one C6 guest and one
  Device Service lease;
- the same UIFlow2 guest instance passes WiFi association/DHCP together with
  the BLE GATT exchange;
- same-source UIFlow2 NanoC6 and Nesso N1 builds pass WiFi scan/association/
  DHCP plus external Bumble NUS discovery/write and guest receive in one
  `esp-emu` instance, using their matching ELF and USB-Serial/JTAG console;
- the same NanoC6 path passes through Device Service `runtime=network`;
- the ESP-IDF DNS/UDP fixture passes host-forwarder DNS resolution and a
  controlled UDP request/reply through the user-mode gateway;
- the Device Service exposes `runtime=network` one-shot sessions and a
  `/sessions/{id}/network` evidence endpoint;
- Device Service `network` sessions expose `firmware_ap_password` and up to
  eight loopback-only `hostfwd` entries, allowing an `esp-emu` guest to join a
  firmware-created SoftAP and serve its provisioning portal through
  `127.0.0.1`; physical-phone captive-portal behavior is not modeled;
- the classic ESP32 QEMU machine's `open_eth` device reaches DHCP and downloads
  a complete 1 MiB HTTP body in the `core2_openeth` ESP-IDF fixture.
- an optional OpenMAC WiFi model imported into QEMU 9.2.2 lets stock Core2
  UIFlow2 `network.WLAN` activate, scan three virtual APs, associate and obtain
  DHCP address `10.0.2.15`, with observable 802.11 management frames and a
  controlled HTTP `200 OK`.
- the classic ESP32 BT bootstrap patch lets the same stock Core2 UIFlow2 image
  activate NimBLE, configure its GAP name and return from `gap_advertise()`.
- a Core2 UIFlow2 HCI-UART test build connects NimBLE through the QEMU UART1
  FIFO/chardev to a Bumble controller; a second peer passes scan, connect, NUS
  discovery, subscription, write, guest receive and notify readback in 5/5
  repeated runs.
- Device Service `runtime=qemu-ble` / `profile=core2-hci-gatt` runs that exchange
  in the same QEMU session and exposes serial, frame, QOM, peer log and hashed
  network evidence through `/api/v1`.
- C6 QEMU models GigaDevice/ISSI QIO status-register semantics,
  `MODEM_SYSCON_CLK_CONF1`, the C6 WiFi MAC/PHY register windows, DMA
  descriptor rings, TX completion and RX injection. A stock UIFlow2 guest
  resolves `example.com` and receives a public HTTP `200 OK`.

What is not yet proven:

- an unmodified UIFlow2 firmware connecting to a virtual SSID and reaching a
  controlled TCP/UDP endpoint;
- automatic internet access for every cardputer-zero and Tab5 path; the
  validated S3 and C6 unified profiles use QEMU SLiRP and have controlled HTTP
  coverage;
- simultaneous board-level QEMU peripherals and WiFi/BLE in one guest instance
  for the remaining CardputerZero and Tab5 backends;
- packet capture, DNS policy, TLS/HTTP test services and multi-device isolation
  in the regular regression matrix;
- stock Core2 UIFlow2 DNS and external internet access: the optional OpenMAC
  patch completes scan, association, DHCP and controlled HTTP, but DNS and
  external internet behavior remain unverified;
- stock Core2 UIFlow2 BLE beyond advertising enable through the native ESP32
  controller: no external peer has observed that controller's advertisement,
  connection, GATT service or ACL exchange yet. The separate HCI-offload lane
  above is complete, but it is not a native radio/controller model;
- security conclusions about untrusted firmware based only on network traffic.

The QEMU S3/C6 models cover the guest-visible MAC, DMA descriptors, interrupts
and QEMU user-net frame path, but not a complete PHY, rate, security or RF model.
The classic ESP32 LX6 path still contains PHY bring-up stubs. A successful boot
log or PHY-ready register therefore does not by itself mean the device is online.

## Device coverage

| Device class | Current network path | Status |
| --- | --- | --- |
| StickS3, CoreS3, Cardputer ADV, StopWatch, AtomS3R, PaperColor, PaperMono, StackChan and StamPLC | QEMU `misc.esp32s3.wifi` + board model + UART1/2 H4 BLE | Unified Device Service lease PASS for display/input/device state/audio where available, WiFi DHCP/HTTP and external BLE GATT |
| Remaining modeled ESP32-S3 boards | `esp-emu` WiFi SoftAP + user/TAP backend | Diagnostic lane exists; device-local QEMU unified migration pending |
| ESP32-C6 boards, including NanoC6 and Nesso N1 | QEMU `misc.esp32c6.wifi` + board model + UART1 H4 BLE | Unified Device Service lease PASS for board peripherals, WiFi DHCP/HTTP and external BLE GATT |
| ESP32-P4 Tab5 | C6 `network_adapter` over ESP-Hosted, C6 process has `--net user` | Transport starts; P4 UIFlow2 end-to-end association/DHCP/DNS/TCP is pending |
| ESP32 LX6 Core2 | Optional OpenMAC WiFi, UART1 HCI BLE and board models in one `m5core2` guest; separate OpenETH fixture | `core2-unified` PASS 3/3 first attempts for board/peripherals + WiFi DHCP/HTTP + external BLE GATT; native-controller peer/GATT, DNS and external internet `NOT RUN`; wider cache startup boundary remains |
| CardputerZero | Linux SR9900A Ethernet through the independent ARM64 backend | Ethernet frame path exists; this is not WiFi and not the UIFlow2 ESP32 path |

“All simulated devices online” means one Device Service lease and one guest per
device. StickS3, CoreS3, Cardputer ADV, StopWatch, AtomS3R, PaperColor,
PaperMono, StackChan, StamPLC, NanoC6 and Nesso N1 meet that simulator-only
bar. A PASS from the diagnostic `esp-emu` lane or from another device cannot be
inherited. Environment-gated Core2 also meets the unified bar through its
separate classic-ESP32 OpenMAC/HCI path.

## Recommended architecture

The primary architecture puts board and network data planes in the same guest:

```text
Device Service lease
        |
        +--> one QEMU process
              +-- board: display, touch, I2C, I2S, camera, USB
              +-- WiFi MAC/DMA or equivalent virtual radio path
              +-- BLE controller or HCI data path
              +-- serial, frame, input, QOM and network evidence
```

Separate `esp-emu` or network-only sessions remain useful for fault isolation,
protocol development and regression. They are diagnostic lanes: their result
cannot be combined with a QEMU board session to claim that a complete simulated
device passed.

## Network modes

### Isolated user-mode lab

Use `--net user` with a controlled host service. This is zero-setup, gives the
guest DHCP/DNS and can expose test servers through `hostfwd`.

Recommended for:

- firmware functional tests;
- HTTP/WebSocket/MQTT test endpoints;
- DNS and reconnect tests;
- untrusted-firmware observation with restricted egress.

### Controlled internet egress

Use a user-mode NAT with an allowlist/proxy. Do not give untrusted firmware
direct access to the workstation LAN or credentials.

Recommended for:

- cloud onboarding tests against disposable accounts;
- firmware update and certificate tests;
- deterministic allow/deny behavior.

### TAP/vmnet LAN

Use a TAP bridge or macOS vmnet backend when testing mDNS, discovery, LAN
scanning, multiple virtual devices, or host-to-device connections.

This mode requires host networking privileges and must run in an isolated
network namespace/VM for untrusted firmware.

### Firmware SoftAP

For firmware that starts its own AP, let the emulator join it and use
`hostfwd` from the host. This tests captive portal and local provisioning flows
without a physical phone or router.

The Device Service exposes this as `network.firmware_ap_password` plus
`network.hostfwd` on `runtime=network`. Forwards bind only to loopback. The
portal path is usable while the one-shot session is running, but automated
captive-portal HTTP assertions and a virtual phone network namespace are still
pending.

## Required test matrix

| Capability | Minimum assertion |
| --- | --- |
| Scan/associate | Firmware sees the configured SSID and connects with the expected security mode |
| DHCP | Guest receives an address, gateway and DNS server |
| DNS | Query reaches the controlled resolver; allow and deny cases are recorded |
| TCP | Request/response completes against a host test server |
| UDP | Datagram is received by a host peer |
| Reconnect | Link loss, wrong password and DHCP renewal are observable |
| Security modes | Open, WPA2, WPA3 and wrong-credential behavior are tested |
| Multi-device | Two virtual devices can communicate only through the intended lab fabric |
| Packet evidence | Host captures DNS/TCP/UDP metadata and payload hashes without storing secrets |

The first acceptance target should be one S3 or C6 device with a small UIFlow2
program printing `WIFI_CONNECTED`, `DHCP_OK`, `DNS_OK` and `TCP_OK`.

## Security boundary

The network lane is an observation environment, not a malware sandbox by
itself. For untrusted firmware:

- run each build in a disposable VM or isolated network namespace;
- block workstation LAN, credentials, cloud metadata and host services;
- capture only metadata and payload hashes by default;
- record both “observed behavior” and the limits of the observation;
- never conclude that firmware is safe merely because no suspicious traffic was
  observed in one run.

## Delivery plan

| Phase | Work | Estimate |
| --- | --- | --- |
| N0 | One-device UIFlow2 WiFi proof through `esp-emu` | DONE for StickS3 WLAN/DHCP and C6 NanoC6/Nesso WiFi+BLE; ESP-IDF adds TCP |
| N1 | Reusable harness: SSID/password, DHCP/DNS/TCP/UDP assertions, packet summary, `hostfwd` | WiFi/DHCP/DNS/TCP/UDP, BLE and loopback hostfwd API DONE; isolated resolver, automated SoftAP portal assertions and pcap policy pending |
| N2 | Attach the harness to all S3/C6/P4 profiles and add reconnect/security cases | 3–5 working days |
| N3 | Tab5 P4 ↔ C6 ESP-Hosted end-to-end network proof | 2–4 working days |
| N4 | Isolated CI runner, egress policy and multi-device lab fabric | 3–5 working days |
| N5 | Core2 ESP32 LX6 WiFi/PHY and BLE controller path or alternative runtime | WiFi data path DONE; native controller/advertising DONE; HCI-offload external GATT DONE; same-instance `core2-unified` board + WiFi + external GATT PASS 3/3 first attempts; native-controller peer/GATT, DNS and external network remain open |
| N6 | Same-instance QEMU board + WiFi/radio model | DONE for all validated S3 slices, both C6 boards and environment-gated Core2 board+WiFi+BLE HCI-offload in one guest; native BT controller/radio closure remains open |

N6 is the primary product contract. N0–N3 remain the reusable fixture layer,
and N5 closes the Core2 SoC-specific gap. “All simulated devices online” requires
N6 completion per device; no across-device inference is allowed.
