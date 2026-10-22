# Network simulation plan

Date: `2026-10-22`

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

Validated on `2026-10-22`:

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
- the classic ESP32 QEMU machine's `open_eth` device reaches DHCP and downloads
  a complete 1 MiB HTTP body in the `core2_openeth` ESP-IDF fixture.
- an optional OpenMAC WiFi model imported into QEMU 9.2.2 lets stock Core2
  UIFlow2 `network.WLAN` activate, scan three virtual APs, associate and obtain
  DHCP address `10.0.2.15`, with observable 802.11 management frames and a
  controlled HTTP `200 OK`.

What is not yet proven:

- an unmodified UIFlow2 firmware connecting to a virtual SSID and reaching a
  controlled TCP/UDP endpoint;
- automatic internet access for every S3/C6/P4 device profile;
- simultaneous board-level QEMU peripherals and WiFi in one guest instance;
- packet capture, DNS policy, TLS/HTTP test services and multi-device isolation
  in the regular regression matrix;
- stock Core2 UIFlow2 DNS and external internet access: the optional OpenMAC
  patch completes scan, association, DHCP and controlled HTTP, but DNS,
  external internet behavior and BLE remain unverified;
- stock Core2 UIFlow2 BLE: the local baseline panics in `btdm_app_ref_init`
  on `0x3ff7120c` because the classic ESP32 Bluetooth controller block is
  absent;
- security conclusions about untrusted firmware based only on network traffic.

The QEMU ESP32-S3/LX6 board path currently contains PHY bring-up stubs, not an
RF or WiFi MAC/PHY model. A successful boot log or PHY-ready register therefore
does not mean the device is online.

## Device coverage

| Device class | Current network path | Status |
| --- | --- | --- |
| All modeled ESP32-S3 boards | `esp-emu` WiFi SoftAP + user/TAP backend | All nine S3 devices pass UIFlow2 WiFi+BLE on same-instance UART-REPL test builds |
| ESP32-C6 boards, including NanoC6 and Nesso N1 | `esp-emu` WiFi SoftAP + user/TAP backend | Device-local UIFlow2 WiFi+BLE PASS on same-source NanoC6 and Nesso N1 builds; ESP-IDF coexist also PASS |
| ESP32-P4 Tab5 | C6 `network_adapter` over ESP-Hosted, C6 process has `--net user` | Transport starts; P4 UIFlow2 end-to-end association/DHCP/DNS/TCP is pending |
| ESP32 LX6 Core2 | Optional OpenMAC QEMU WiFi model; separate OpenETH fixture | Stock UIFlow2 WiFi scan + association + DHCP/IP + controlled HTTP PASS; DNS/external internet and BLE `NOT RUN` |
| CardputerZero | Linux SR9900A Ethernet through the independent ARM64 backend | Ethernet frame path exists; this is not WiFi and not the UIFlow2 ESP32 path |

Therefore “all simulated devices online” needs two scopes:

1. **First scope:** S3/C6/P4 devices through the `esp-emu` network lane.
2. **Full scope:** add a Core2 ESP32 LX6 network path and decide whether
   CardputerZero network tests belong to the same product matrix.

## Recommended architecture

Start with a separate network test lane instead of replacing the existing
board/UI lane:

```text
merged UIFlow2 image
        |
        +--> QEMU board lane: display, touch, I2C, I2S, camera, USB
        |
        +--> esp-emu network lane: WiFi/AP/DHCP/DNS/TCP/UDP + packet evidence
```

This allows UI/peripheral regression and network review to progress
independently. The same firmware image can be tested in both lanes, but a
network PASS and a board-peripheral PASS remain separate evidence.

For devices whose required peripheral controllers are only in QEMU, running the
same firmware in two lanes is the low-risk first step. Unifying board models
and WiFi in one QEMU instance is a later engineering project, not a prerequisite
for a useful network test harness.

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
| N1 | Reusable harness: SSID/password, DHCP/DNS/TCP/UDP assertions, packet summary, `hostfwd` | WiFi/DHCP/DNS/TCP/UDP and BLE harness DONE; isolated resolver and pcap policy pending |
| N2 | Attach the harness to all S3/C6/P4 profiles and add reconnect/security cases | 3–5 working days |
| N3 | Tab5 P4 ↔ C6 ESP-Hosted end-to-end network proof | 2–4 working days |
| N4 | Isolated CI runner, egress policy and multi-device lab fabric | 3–5 working days |
| N5 | Core2 ESP32 LX6 WiFi/PHY path or alternative runtime | Scan, association, DHCP/IP and controlled HTTP DONE behind an optional QEMU patch; DNS/external network and BLE remain open |
| N6 | Optional same-instance QEMU board + WiFi/radio model | 2–4 weeks |

N0–N3 are the recommended scope before claiming “all S3/C6/P4 simulated
devices can go online.” N5 extends the claim to Core2. N6 is only needed if a
test must exercise WiFi and board peripherals in one guest process at the same
time.
