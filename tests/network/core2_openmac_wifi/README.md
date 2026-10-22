# Core2 OpenMAC WiFi scan probe

This optional regression exercises the ESP32 classic WiFi MAC path added by
`patches/qemu-core2-openmac-wifi/`.

It is a QEMU board-lane development test. Agent-triggered functional firmware
tests must still use the Device Service.

## Scope

The probe replaces only `/boot.py` and `/main.py` in the cached official Core2
UIFlow2 image. It starts the real `network.WLAN(network.STA_IF)`, activates it,
runs `scan()`, and requires:

- `CORE2_WIFI_MAIN_START`;
- a positive `CORE2_WIFI_SCAN_OK` count;
- at least the configured `myssid` test AP;
- `CORE2_WIFI_RESULT: PASSED`.

The model responds to probe requests and emits beacon/probe-response frames.
This proves the stock WiFi MAC/PHY initialization and scan management-frame
path in simulation. It does not prove DHCP, IP connectivity or real RF.

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
`evidence.json`.

## Known boundary

Association management frames are reachable, but the first DHCP discover data
frame currently crashes the OpenMAC AP-to-user-net bridge. Do not claim Core2
IP connectivity until that data path is fixed.
