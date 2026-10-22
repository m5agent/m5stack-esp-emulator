# Core2 OpenMAC WiFi scan probe

This optional regression exercises the ESP32 classic WiFi MAC and user-net path added by
`patches/qemu-core2-openmac-wifi/`.

It is a QEMU board-lane development test. Agent-triggered functional firmware
tests must still use the Device Service.

## Scope

The probe replaces only `/boot.py` and `/main.py` in the cached official Core2
UIFlow2 image. It starts the real `network.WLAN(network.STA_IF)`, activates it,
runs `scan()`, associates with the emulated `myssid` AP, obtains DHCP and
performs a controlled HTTP GET through QEMU user networking. It requires:

- `CORE2_WIFI_MAIN_START`;
- a positive `CORE2_WIFI_SCAN_OK` count;
- at least the configured `myssid` test AP;
- connected state and a non-zero `CORE2_WIFI_IP`;
- `HTTP/1.x 200 OK` from the host HTTP probe;
- `CORE2_WIFI_RESULT: PASSED`.

The model responds to probe requests and emits beacon/probe-response frames.
This proves the stock WiFi MAC/PHY initialization, scan, association, DHCP,
basic IP configuration and controlled TCP/HTTP path in simulation. It does not
prove DNS, external internet access, BLE or real RF.

## Apply the QEMU patch

Apply the patch to the current patched M5 QEMU checkout:

```bash
git -C .work/M5StopWatch-QEMU/build/qemu apply \
  "$PWD/patches/qemu-core2-openmac-wifi/0001-esp32-openmac-wifi-model.patch"
```

Build:

```bash
ninja -C .work/M5StopWatch-QEMU/build/qemu/build qemu-system-xtensa
```

The current proof was independently built in a temporary copy of QEMU 9.2.2.

## Run

```bash
PYTHONPATH=.work/py python3 \
  tests/network/core2_openmac_wifi/run_test.py \
  --qemu .work/M5StopWatch-QEMU/build/qemu/build/qemu-system-xtensa \
  --out-dir /tmp/core2-openmac-wifi
```

The runner writes an isolated flash copy, serial/stdout/stderr logs, and
`evidence.json`. It retries by default five times because the existing Core2
cache startup panic is still intermittent and occurs before WiFi activation.

## Known boundary

The AP name and QEMU user-net topology are fixed by the bring-up model. DNS,
external internet access and BLE are not covered.
