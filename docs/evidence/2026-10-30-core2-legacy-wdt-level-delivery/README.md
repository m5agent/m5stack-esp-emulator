# Core2 legacy WDT level delivery

Date: 2026-10-30

Validation category: **virtual-device validation**

Hardware validation: `NOT RUN`

Status: normal-WDT legacy startup `PASS`; setup/REPL and complete factory
application remain separate checks.

## Result

`0035-esp32-timg-wdt-int-ena.patch` historically required
`INT_ENA.WDT` before raising the classic ESP32 watchdog level output. That
assumption is wrong for the legacy task watchdog. Public ESP-IDF 3.3.5
(`03810c4a065a1ecdd24a803b2c9dc4e834c7dab5`) registers
`ETS_TG0_WDT_LEVEL_INTR_SOURCE` through `esp_intr_alloc`, sets
`TIMERG0.wdt_config0.level_int_en`, and never writes `INT_ENA.WDT`.
The masked status therefore remained zero, the stage-0 ISR was unreachable,
and the stage-1 action reset the SoC.

`0095-esp32-legacy-wdt-level-delivery.patch` preserves
`INT_ST = INT_RAW & INT_ENA` and the existing `INT_ENA` mask for every
non-WDT timer-group source. Only the WDT level output now follows
`INT_RAW.WDT` while `WDTCONFIG0.LEVEL_INT_EN` is set. The WDT edge path is
unchanged. Newer ESP-IDF also programs `INT_ENA.WDT`; the model remains
compatible with that path because the level enable and raw bit are both set.

## Runtime matrix

All three runs used the same public firmware and QEMU binary through the
visible Device Service API:

| Field | Value |
| --- | --- |
| Firmware | `4d2d648bd8707a1789d540366015a1b90dc816b66a04163048626ea29e333ed4` |
| QEMU | `001a938503e7b1d813f388022d849c24bab4f5298602211f70042a5184fcb62d` |
| Patch SHA256 | `df008a1f34324c1b4b0d7bc4640f03bb5f9b42b109cfedadfee0b31631411894` |
| Runtime | `qemu-wifi`, `core2-openmac` |
| Flash | real public image plus strict `deviceCfg` session overlay |
| Effective Flash | `b30f3014b75f762f50be3284010502e047b3bd0494b0f0b72a673c2756baffd7` |
| Accelerator | `thread=single`, `tb-size=128`, `icount shift=2` |
| Per-vCPU budget | default `10 us` |
| Watchdog | normal |
| Result | `3/3 PASS` |

| Run | Trace tail covered | Boot/reconnect markers | Serial SHA256 |
| --- | ---: | --- | --- |
| 1 | `315.55-335.55 s` | boot done, two reconnect starts, one finish | `7e7f425d4c7aea4b15fdd5146d264fe111aa4671fd63bcecf3e45e3bf9824dbd` |
| 2 | `310.55-330.55 s` | boot done, reconnect start | `eca858f08edcc6cd015d5b01b720375be724220f9c936b237d456caa744b3929` |
| 3 | `320.55-340.55 s` | boot done, three reconnect cycles | `73cb13dd239245c86d8e0a5a657845e2d2b2bd5f94d38e14e2771a8c4bae5f2e` |

The trace tail is the bounded last 8 MiB retained by the runner. These ranges
are therefore minimum observed virtual-time coverage, not QEMU wall time.
No run contains `TG0WDT_SYS_RESET` or a second boot banner.

Each retained stage-0 timeout occurs at a `5.001124 s` interval. The relevant
sequence is:

```text
TG0 timeout ... stage=0 mode=1
TG0 wdt-int level-raised int_ena=00000002 int_raw=00000004 int_st=00000000
TG0 WDTFEED
TG0 INT_CLR old=00000004 clear=00000004
```

This proves that the watchdog interrupt is delivered while the ordinary masked
status remains zero, then the guest executes its task-watchdog feed and clears
the raw source.

## Startup frame

All three sessions retained the original Core2 API Key startup screen:

| Field | Value |
| --- | ---: |
| Frame | `320x240` |
| Nonblack pixels | `75,559` |
| Unique colors | `512` |
| PNG bytes | `12,478` / `12,478` / `12,542` |
| PNG SHA256 | `b9cef48d…` / `b9cef48d…` / `a8f77474…` |

The two 12,478-byte PNGs are byte-identical. The third screenshot has the same
pixel metrics and visible content but a different PNG encoding/hash.

## Legacy WiFi configuration UI

One additional normal-WDT session used the same firmware, QEMU and strict
`deviceCfg` overlay. At `CORE2_LEGACY_ORIGINAL_BOOT_DONE`, the runner sent one
Ctrl-C input sequence and captured the resulting frame before stopping.

The visible screen changed to the real `Wi-Fi Connect` page with
`Connecting to myssid`; it is not a host-injected frame:

| Field | Value |
| --- | ---: |
| Frame | `320x240` |
| Nonblack pixels | `75,373` |
| Unique colors | `306` |
| PNG bytes | `11,614` |
| PNG SHA256 | `cf7ad5ab8ff981a0fa405e224097f3c9c971f3872bf30f143b3bd8c2dea7d44f` |
| Serial SHA256 | `923380826ceb9be6107e6437dcb690be6a67bdccaade80164ab6537b7f458d0d` |

This run also observed repeated stage-0 level delivery, `WDTFEED` and
`INT_CLR`, with no TG0 stage-1 reset. The Ctrl-C sequence did not produce a
MicroPython REPL prompt, so setup/REPL remains a separate test rather than a
claim from this frame.

## Regression

The same final QEMU completed the Core2 UIFlow2 device group `6/6 PASS`
(`core2-peripherals`, `core2-audio`, `core2-mic`,
`core2-power-monitor`, `core2-imu`, `core2-axp192`), one attempt per case and
no retry. Matrix summary SHA256:
`6eaa60697c000f4013232668f55d3c879b43451d22df1e62d1938703ae3a3216`.

The patch contract test verifies that only `TIMG_WDT_INT` uses the independent
level gate, `INT_ST` is not rewritten, all other sources retain `INT_ENA`
masking, and the patch contains no watchdog-disable, timeout-extension,
environment-controlled, or clock-warp shortcut.

## Reproduction

Build the runtime patch stack through `scripts/bootstrap-unit-runtime.py`,
then run the same public firmware through `/api/v1` with:

- `device_id=core2`;
- `runtime=qemu-wifi`;
- `profile=core2-openmac`;
- normal WDT;
- `M5_CORE2_ICOUNT_SHIFT=2`;
- default per-vCPU budget;
- a 600-second observation window.

The test runner captures serial, frame, QEMU stderr tail, session metadata and
events before stopping with `purge=0`. Verify that the resulting QEMU process
is absent after cleanup.

## Boundaries

- This is virtual-device validation, not physical-hardware validation.
- It proves the tested classic ESP32 TIMG WDT level/status behavior through
  the public guest driver path. It does not establish electrical timing,
  physical reset behavior, RF, or analog measurements.
- Setup/REPL interaction and a complete factory application remain separate
  checks. A stable API Key startup screen is not a claim that every legacy
  application path is complete. The WiFi configuration screen proves one
  additional real guest UI path, not a successful network connection.
