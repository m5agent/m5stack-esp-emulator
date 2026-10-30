# Core2 WiFi IRQ cache handoff gate

Date: 2026-10-30

Status: `SEMANTIC_FIX`; `RUNTIME-03` remains `OPEN`.

## Result

The legacy Core2 image can assert the level-triggered WiFi MAC IRQ while one
CPU has its instruction cache disabled for the Flash operation handoff. QEMU
then injected that IRQ into cached ISR code, producing:

```text
Guru Meditation Error: Core 0 panic'ed
(Cache disabled but cached memory region accessed)
```

`0092-esp32-wifi-irq-cache-gate.patch` exports each CPU's instruction-cache
ready state from DPORT to the ESP32 interrupt matrix. While the cache is
disabled, INTMATRIX holds only `ETS_WIFI_MAC_INTR_SOURCE`. The level remains
latched and is reevaluated when the cache is restored, so the interrupt is
delayed rather than discarded.

Cross-core IRQs, timer sources and the cache-illegal-access source are not
gated. This keeps the Flash handoff and exception path able to make progress.
The patch does not disable the watchdog, change timeout values, warp the
virtual clock or change the guest.

## Validation

### Before the gate

The diagnostic QEMU
`54d31e90e2eff273b17f11388015e9bf16a1cf6877fbf7681c207eb73b68286f`
used the original normalized firmware
`4d2d648bd8707a1789d540366015a1b90dc816b66a04163048626ea29e333ed4`
with the session-isolated legacy WiFi config overlay. Serial reached:

```text
BOARD NAME: M5STACK-CORE2
APIKEY marker
CORE2_LEGACY_ORIGINAL_BOOT_START
CORE2_LEGACY_ORIGINAL_BOOT_DONE
```

It then entered the cache-disabled panic above and kept a 302-byte black
frame.

### After the gate

The rebuilt product source, including `0091` and `0092`, has QEMU SHA256:

```text
a4cfa2b8c3aa7e62b11423fa456c57ec01da7c7e43086a90bdded0eec6241249
```

The same original firmware and config overlay ran through
`runtime=qemu-wifi` with normal watchdog and the default per-vCPU budget:

- `icount shift=2`;
- no WDT-disable or per-vCPU budget override;
- serial again reached BOARD marker, API key marker, boot start and boot done;
- no `Cache disabled but cached memory region accessed` message occurred;
- the frame became `320x240` with `75,559` nonblack pixels and `512` colors;
- PNG SHA256
  `737df08a0c5d21fe23a46e38f79b7a580508f8dfa7c63c9bc552be19a3106c96`.

The rendered screen is the original UIFlow API-key/setup page. The firmware
then entered `TG0WDT_SYS_RESET`; the IRQ cache panic is gone, but normal-WDT
startup was not yet stable in this milestone. The later
[WDT level-delivery record](../2026-10-30-core2-legacy-wdt-level-delivery/README.md)
removes that reset and keeps the startup UI running beyond 300 seconds virtual
time.

### Regression

The patched final QEMU completed the Core2 UIFlow2 device group:

- `6/6 PASS`;
- peripherals, audio, microphone, power monitor, IMU and AXP192;
- one attempt per case and no retry;
- matrix summary SHA256
  `432504a9561a3e3cb4156817edd9c0565848dae8a18f64cb92a09cd2476ac419`.

The patch applies forward to the retained QEMU tree and reverses from the
patched source. The dedicated source contract checks that only the WiFi MAC
source is gated and rejects watchdog-disable and clock-warp shortcuts.

Platform verification:

- WiFi IRQ cache-gate source tests: `3/3 PASS`;
- documentation contracts: `50/50 PASS`;
- platform full suite: `1,599` run, `1,598 PASS + 1 skip`;
- runtime coverage, peripheral catalog, QEMU profiles and project snapshot:
  `PASS`;
- compileall, Ruff `E9/F` and `git diff --check`: `PASS`.

## Boundary

This is virtual-device validation only. It closes the
WiFi-IRQ/cache-handoff interaction. The normal-WDT reset observed at this
milestone was later fixed by `0095`; setup/REPL, complete factory application,
physical cache/PSRAM timing, RF and electrical behavior remain outside this
result.
