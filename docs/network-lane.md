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

For the BLE proof, add `--ble --no-wifi`. That path creates the real UIFlow2
`BLEUARTServer`, then uses a separate Bumble controller as the BLE peer to
scan, connect, discover the Nordic UART GATT service, subscribe and write. It
requires the write to arrive in guest Python before recording BLE PASS.

WiFi and BLE currently run as separate UIFlow2 scenarios: a combined
same-instance exercise showed a complete BLE GATT exchange but did not progress
WiFi association afterward in `esp-emu 0.50.0`. That coexistence limit is
tracked explicitly rather than hidden in one PASS.

The `esp-idf-http` profile runs the upstream `http_throughput` firmware. It
validates WiFi association, DHCP, an HTTP request through the user-mode
gateway, and a complete 1 MiB response body. This C/ESP-IDF path avoids the
UIFlow factory image's WebREPL task competing for the MicroPython console.

The `esp-idf-smoke` profile runs the upstream comprehensive smoke image. It
asserts WiFi/DHCP and, when `--ble` is requested, NimBLE advertising and the
smoke summary.

The `generic-observe` profile runs an arbitrary compatible image for the
observation window. Without `--expect` it records `PARTIAL` plus serial output;
repeat `--expect MARKER` to turn application output into explicit PASS/FAIL
checks. This is the fallback for firmware whose startup protocol is not known
in advance.

Every run writes `serial.log`, `ble-probe.log` and `evidence.json` under the
selected output directory. Binary hashes identify the exact firmware, ELF and
emulator used. Passwords are redacted from the command and evidence.

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
workstation workflow. Untrusted firmware still requires a disposable VM or a
network namespace with egress restrictions and packet capture.

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

Device-level service sessions have also passed the same WiFi/DHCP/HTTP checks
for CoreS3 (`ESP32-S3`), NanoC6 and Nesso N1 (`ESP32-C6`). The C6 build uses
no PSRAM argument, while the StickS3/CoreS3 runs use `8M`.

The fixture hashes and machine-readable checks are stored with the run evidence
and work record rather than copied into this document.
