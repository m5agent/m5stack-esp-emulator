# Core2 classic WiFi station timing and data path

Date: 2026-10-30

Validation category: **virtual-device validation**

Hardware validation: `NOT RUN`

## Result

`0093-esp32-classic-wifi-virtual-time.patch` moves classic ESP32 beacon,
injected-frame and generated 802.11 timestamp scheduling from QEMU realtime to
virtual time. This makes scan, association, DHCP and watchdog ordering
independent of host wall-clock speed under deterministic icount.

`0094-esp32-classic-wifi-station-data.patch` keeps association and station data
on the normal WLAN/Ethernet/slirp path. Host frames now return to the guest
through the same model, and a DHCP server reply transitions the model from
`ASSOCIATED`/`STA_DHCP` to `STA_ASSOCIATED`. The old synthetic DHCP branch and
the separate `STA DATA` unimplemented branch are removed.

The Device Service now applies `wifi_ssid`, password and authentication to
both classic `misc.esp32_wifi` and `misc.esp32s3.wifi` sessions. Previously
only the S3 model received the requested values.

## Stock Core2 WiFi regression

The same Core2 UIFlow2 WiFi probe completed five independent first attempts:

| Check | Result |
| --- | --- |
| Runtime | `qemu-wifi`, `core2-openmac`, `icount shift=5` |
| QEMU binary | `3e61aa644074598e7b37e2cd9d4e7c1e194d2073b453f4fd9fdc5ffce62738f8` |
| Base firmware | `b228c0e2d877e77a8a352e917ed84f4da8ea92d15b25e28f431a2999620fe3c4` |
| Generated firmware | `b57b196fada9cbfd7e41bd1a4e742e8c63935c25dfcc2c0c51b71f1fd5257220` |
| Attempts | `5/5 PASS` |
| Association | authenticated and associated |
| DHCP IPv4 | `10.0.2.15` |
| Host HTTP | `HTTP/1.0 200 OK` and `CORE2_WIFI_RESULT: PASSED` |
| Evidence SHA256 | `b2559537f3e8fa972f4904241df9f4df115fb629488a93af1177b3d35875c908` |

The default-off trace contains `host-tx` and `host-rx` events with EtherType
`0x0800`/`0x0806` and reports state `5` (`STA_ASSOCIATED`) after the DHCP
server reply. This proves that both directions use the controller data plane,
not a host-injected connected state.

The same final binary completed the Core2 UIFlow2 device group `6/6 PASS`
(peripherals, audio, microphone, power monitor, IMU and AXP192), one attempt
per case and no retry. Matrix summary SHA256:
`3533de10b6e4a24730b06203f25124083d2ff763e7225b5ab00b249aba9b6b02`.

## Legacy Core2 control

The public legacy firmware
`4d2d648bd8707a1789d540366015a1b90dc816b66a04163048626ea29e333ed4`
under `runtime=qemu-wifi`, `icount shift=2`, a diagnostic `1 us` per-vCPU
cap and normal WDT reaches:

```text
BOARD NAME: M5STACK-CORE2
APIKEY: 7621FAE2
CORE2_LEGACY_ORIGINAL_BOOT_START
CORE2_LEGACY_ORIGINAL_BOOT_DONE
```

The frame is the original `320x240` API-key page:

| Field | Value |
| --- | ---: |
| Nonblack pixels | `75,559` |
| Unique colors | `512` |
| PNG SHA256 | `737df08a0c5d21fe23a46e38f79b7a580508f8dfa7c63c9bc552be19a3106c96` |
| Normal-WDT serial SHA256 | `8abafb47b4cfa3f6d0fe65b2b45f084b0d76e7993bb1f315485eff80a8a1d38e` |

Normal WDT still emits `TG0WDT_SYS_RESET`, so this is not a `RUNTIME-03`
product pass. The WDT-disabled diagnostic control is used only to distinguish
the WiFi/UI path from watchdog termination.

The final QEMU binary was also run through a 600-second WDT-disabled diagnostic
window. It reached guest virtual `457.794095092 s` with no reset, retained
`reconnect start ...` / `reconnect finish ...`, and kept the same API-key page:

| Field | Value |
| --- | ---: |
| Serial SHA256 | `f2dfc8140b5d857ab81594966cf58ec66bc5e0a9ee9cd77000960df15b76790c` |
| PNG SHA256 | `a8f77474b218113073732d6b6f5e8f3c18b1fac23593054bf209d0d6f6864bf7` |
| Nonblack pixels | `75,559` |
| Unique colors | `512` |

## Reproduction

```bash
M5SW_CLASSIC_WIFI_TRACE=1 PYTHONPATH=.work/py python3 \
  tests/network/core2_openmac_wifi/run_test.py \
  --qemu path/to/qemu-system-xtensa \
  --timeout 30 \
  --attempts 5 \
  --out-dir /tmp/core2-openmac-wifi
```

## Boundaries

- Only virtual-device validation; physical hardware is `NOT RUN`.
- This proves the classic WiFi controller's scan, association, DHCP, IPv4 and
  controlled HTTP data path for the tested firmware.
- It does not prove RF, antenna, electrical, physical cache/PSRAM timing,
  WPA3, roaming or coexistence behavior.
- At this milestone, normal-WDT legacy startup still reset. The later
  [WDT level-delivery record](../2026-10-30-core2-legacy-wdt-level-delivery/README.md)
  fixes that reset and keeps the startup UI running beyond 300 seconds virtual
  time. Setup/REPL completion and a complete factory application remain
  separate checks.
