# Network and BLE simulation lane

Date: `2026-10-22`

The network lane runs a complete ESP image in `esp-emu` while the regular
QEMU/board lane continues to own display, touch and board peripherals. Results
from the two lanes are separate simulation evidence; neither is real-hardware
validation.

## Implemented entry point

```bash
PYTHONPATH=.work/py python3 platform/tools/network_lane.py \
  --profile uiflow2-sticks3 \
  --chip esp32s3 \
  --firmware /path/to/sticks3-uiflow2.bin \
  --elf /path/to/micropython.elf \
  --out-dir /tmp/m5-sticks3-network
```

The `uiflow2-sticks3` profile:

1. runs the full flash image with `--net user`, a virtual WPA2/WPA3 SoftAP and
   the documented SoftAP/DHCP topology;
2. interrupts the factory boot menu at its UART marker and enters a UART REPL
   build;
3. executes the real UIFlow2 `network.WLAN` API for scan, association and DHCP.

For BLE only, add `--ble --no-wifi`. The combined WiFi+BLE proof uses
`--ble --wifi`; both data planes run in the same UIFlow2 guest instance. The
runner stages the BLE setup, WiFi preparation, timer arming and association
command behind unique output markers so UIFlow2's WebREPL task cannot consume
later REPL input. This path creates the real UIFlow2
`BLEUARTServer`, then uses a separate Bumble controller as the BLE peer to
scan, connect, discover the Nordic UART GATT service, subscribe and write. It
requires the write to arrive in guest Python before recording BLE PASS.

The `esp-idf-http` profile runs the upstream `http_throughput` firmware. It
validates WiFi association, DHCP, an HTTP request through the user-mode
gateway, and a complete 1 MiB response body. This C/ESP-IDF path avoids the
UIFlow factory image's WebREPL task competing for the MicroPython console.

The `esp-idf-smoke` profile runs the upstream comprehensive smoke image. It
asserts WiFi/DHCP and, when `--ble` is requested, NimBLE advertising and the
smoke summary.

The `idf-dns-udp` profile runs `tests/network/idf_dns_udp`. It requires a
successful `example.com` DNS lookup, a UDP datagram at the disposable host
peer on port `19000`, the prefixed reply back in the guest, and the final
`DNS_UDP_RESULT: PASSED`. DNS currently uses the host forwarder and is not yet
an isolated resolver.

The `esp-idf-coex` profile runs ESP-IDF's `bleprph_wifi_coex` example with its
matching ELF. It requires DHCP, keeps the WiFi ping path active, and uses
Bumble to scan `nimble-bleprph`, connect, discover the security-test GATT
service, write the static characteristic and verify the readback.

The `generic-observe` profile runs an arbitrary compatible image for the
observation window. Without `--expect` it records `PARTIAL` plus serial output;
repeat `--expect MARKER` to turn application output into explicit PASS/FAIL
checks. Its `--ble` option starts the external Bumble observer and adds GATT
connect/discover/write plus guest-delivery checks; a matching ELF is required
by `esp-emu` for HCI interception. The Device Service selects
`user,restrict=yes` for this profile by default. This is the fallback for
firmware whose startup protocol is not known in advance.

For a generic run that does not reach its required markers, `evidence.json`
includes a non-fatal `diagnosis` object. The categories distinguish board
detection, crash/assert, reboot, peripheral initialization, guest marker
timeout and console/boot visibility. The classification is based on explicit
native log signatures where possible and does not change the guest or convert
an unverified result into PASS.

The diagnosis also reports `blocking_layer`, observed `board_ids`, and
`network_data_plane`. A board/peripheral/console failure records the network
data plane as `NOT RUN`; a later guest crash records it as `UNKNOWN`. A normal
`auto detect board:<id>` message is context only and is not by itself classified
as a board-detection failure.

Every run writes `serial.log`, `ble-probe.log` and `evidence.json` under the
selected output directory. Binary hashes identify the exact firmware, ELF and
emulator used. Passwords are redacted from the command and evidence.
Unknown firmware should use `--console-mode auto` so ESP-IDF's selected
UART or USB-Serial/JTAG console can provide observation markers.

For board drivers that stop before networking on identity/bootstrap reads,
`--i2c-dev PORT:ADDR[,width=N,fill=0xNN,reg=0xRR=0xVV]` attaches the static
register-file endpoint provided by `esp-emu` behind the emulated SoC I2C
controller. This can move a firmware past board detection, but it does not
model the real keyboard, PMIC, touch controller or sensor data plane. Such a
run must keep board behavior `PARTIAL` while reporting WiFi/BLE only from their
own data-plane assertions.

The classic ESP32/Core2 QEMU path has a separate Ethernet fixture at
`tests/network/core2_openeth/`. It selects `CONFIG_ETH_USE_OPENETH` explicitly,
passes DHCP and a complete 1 MiB HTTP download, and records `wifi_claimed:
false`. This is not interchangeable with stock Core2 firmware, whose
`network.WLAN` or `esp_wifi_*` path still requires a classic ESP32 WiFi
MAC/PHY model.

An optional QEMU bring-up patch under
`patches/qemu-core2-openmac-wifi/` imports the OpenMAC classic-ESP32 WiFi
device. A stock Core2 UIFlow2 scan probe now reaches the real network driver:
`network.WLAN(...).active(True)` succeeds and `scan()` returns three virtual
APs in every recorded run. Probe, authentication and association management
frames are exchanged, DHCP completes, and UIFlow2 reports `10.0.2.15/24` with
gateway `10.0.2.2`. A controlled host HTTP GET returns `200 OK`; DNS, external
internet access and BLE beyond advertising enable are still `NOT RUN`.

A following classic-ESP32 BT bootstrap patch maps the missing `0x3ff70000`
Bluetooth RAM/control window and models the ROM core identities, clock
handshake and fine-timer-mask state. Stock UIFlow2 now prints
`CORE2_BLE_ACTIVE True`, completes GAP configuration and returns from
`gap_advertise()` with `CORE2_BLE_RESULT: PASSED`. No external device has
observed the advertisement or completed GATT discovery/write, so this is a
controller/control-plane PASS, not a full BLE data-plane PASS. The Device
Service exposes both paths as environment-gated `qemu-wifi` and `qemu-ble`
runtimes while keeping catalog `network_status: unverified`.

The UIFlow2 device-local WiFi probe under `tests/uiflow2/network_probe/`
replaces only the user scripts in a compatible S3/C6 image and requires the
guest to emit scan, association and DHCP success markers. A StickS3 local
UART-REPL UIFlow2 build passes this path directly through `generic-observe`.
ESP32-C6 UIFlow2 images built with USB-Serial/JTAG console must use the
matrix-provided `network_console=usb-jtag`; the app otherwise blocks in
`mp_hal_stdout_tx_strn` waiting for a TX notification while UART0 appears
silent.
Board images that call `M5.begin()` before Python starts still need their
board I2C/SPI models in the same `esp-emu` instance; otherwise a pre-Python
hang must be recorded as board coverage `BLOCKED`, not WiFi `FAIL`.

The Device Service wraps the same runner as a one-shot
`runtime=network` session. It returns the normal session lifecycle, serial
read/log/evidence endpoints and `GET /sessions/{id}/network`; network sessions
do not expose board framebuffer, input, QOM or same-instance device state.

## Evidence boundary

A PASS proves only the listed data planes in the emulator. It does not prove:

- real radio, antenna, RF calibration or hardware timing;
- public internet access or a stable DNS service;
- TLS certificate or cloud-service behavior;
- Bluedroid, Classic Bluetooth or arbitrary phone interoperability;
- firmware safety, isolation or malware containment.

The `user` network backend is suitable for functional tests in a trusted
workstation workflow. The Device Service defaults `generic-observe` to
`user,restrict=yes`, which blocks off-guest egress while retaining guest DHCP.
An explicitly selected `user` backend is still not a malware boundary:
untrusted firmware requires a disposable VM or a network namespace with egress
restrictions and packet capture.

## Current proof

The first live run used:

- full StickS3 UIFlow2 v2.5.3 image built from the local UIFlow MicroPython
  checkout with UART REPL enabled;
- matching `micropython.elf`;
- `esp-emu 0.50.0`;
- `network.WLAN` scan, association and DHCP to `192.168.4.2`;
- controlled TCP request/response; and
- UIFlow2 `BLEUARTServer` with an external Bumble scan, connection, NUS GATT
  discovery, subscription and write.

TCP was verified separately with the ESP-IDF `http_throughput` fixture:
`1048576` bytes completed in `280081` emulated microseconds (`29.95 Mbit/s`
reported) against the disposable loopback HTTP server.

Device Service sessions using the corresponding `ESP32-S3` and `ESP32-C6`
network profiles have also passed the controlled WiFi/DHCP/HTTP fixture on
CoreS3, NanoC6 and Nesso N1. This proves the chip-level network data plane;
CoreS3's stock UIFLow2 board initialization still needs separate same-instance
coverage. The C6 build uses no PSRAM argument, while the StickS3/CoreS3 runs
use `8M`.

A same-instance StickS3 UIFlow2 run passes BLE scan/connect/GATT/write together
with WiFi association and DHCP to `192.168.4.2`.

The UIFlow2 `--ble` probe also passed on same-source NanoC6 (4 MB) and Nesso N1
(16 MB) C6 builds. Each run used its matching ELF, selected USB-Serial/JTAG
console, associated and received DHCP at `192.168.4.2`, and completed an
external Bumble NUS connect/discover/subscribe/write followed by the guest-side
`LANE_BLE_RX b'M5_LANE'` marker. Device Service session
`48e27f5fb7b44c69852b99993787fa78` repeated the NanoC6 path through the public
session API.

The Device Service catalog exposes this evidence boundary as `network_status`.
All modeled ESP32-S3 devices (StickS3, AtomS3R, CoreS3, StopWatch, Cardputer
ADV, StackChan, PaperColor, PaperMono and StamPLC) and C6 devices (NanoC6 and
Nesso N1) currently use `validated`. The S3 results use observable UART-REPL
test builds; the stock images disable the REPL, so their UART0 I2C logs are not
evidence that the apps failed to start. Tab5 remains `not-supported`; Core2
radio paths remain environment-gated experimental profiles and are not
promoted to `validated`.
Public firmware can still stop in a separate board-detection or peripheral
self-test path before networking; that blocker must not be reported as a
WiFi/BLE regression.

The fixture hashes and machine-readable checks are stored with the run evidence
and work record rather than copied into this document.
