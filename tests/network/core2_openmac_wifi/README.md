# Core2 OpenMAC WiFi scan probe

Last reviewed: `2026-10-26`

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
This probe specifically proves scan, association, DHCP, basic IP configuration
and controlled TCP/HTTP. Later `tests/uiflow2/unified_core2/` runs add public
IPv4 DNS/HTTP and BLE in the same guest. This probe and those later runs do not
prove real RF, WPA2/WPA3, roaming or coexistence.

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
`evidence.json`. It performs one attempt by default. Use `--attempts N`
explicitly for a diagnostic repeat run; a later attempt is not allowed to
replace a failed first-attempt result in evidence.

Core2 radio launches use `tcg,thread=single,tb-size=128` plus deterministic
`icount`.
That scheduling change removed the previously observed first-attempt
interrupt-WDT reproduction and passed 10/10 independent runs. It does not prove
physical cache/PSRAM timing.

The runner now passes those flags explicitly to the QEMU process. A direct
run without them reproduced a cache error at `WAITI` in both idle tasks even
though this README described deterministic scheduling. With the flags present,
five independent WiFi-only runs passed scan/association/DHCP/HTTP:
[`evidence-2026-10-24-deterministic-5x.json`](evidence-2026-10-24-deterministic-5x.json).

## Known boundary

This probe itself covers scan, association, DHCP and controlled IPv4 HTTP. The
separate `tests/uiflow2/unified_core2/` path adds public DNS/HTTP plus BLE in
the same guest, including the stock native-VHCI variant. The AP name and QEMU
user-net topology remain fixed by the bring-up model, and RF/coexistence are
still out of scope.
