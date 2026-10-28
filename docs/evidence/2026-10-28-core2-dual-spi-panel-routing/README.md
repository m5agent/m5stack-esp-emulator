# 2026-10-28: Core2 legacy dual-SPI panel routing

## Scope

The public UIFlow `v1.15.4` Core2 display path uses the classic ESP32
HSPI/SPI2 controller, while UIFlow2 Core2 uses VSPI/SPI3. The `m5core2`
board model previously attached the panel sink only to SPI3. Legacy LCD
DMA transfers therefore reached a controller with no panel model.

This result is **virtual-device validation**. Physical display timing,
electrical behavior and hardware are `NOT RUN`.

## Negative control

The original public firmware was booted with the matching LittleFS2 VFS,
`runtime=qemu-wifi`, and a post-boot legacy `lcd` drawing probe.

With the SPI3-only board model:

- `M5SW_ESP32_SPI_DMA_TRACE=1` observed `412` DMA writes at
  `other addr=104`;
- the panel controller observed `0` DMA writes;
- the displayed frame remained `320x240` with `0` nonblack pixels.

This isolates the failure to physical-controller routing rather than the
Python `m5stack`/`lcd` API: the guest drawing calls completed, but their
controller had no panel attached.

## Fix

`0068-core2-dual-spi-panel-routing.patch` attaches the same ILI9342 panel
sink to both `s->spi[2]` (HSPI) and `s->spi[3]` (VSPI), both using DC GPIO15.
Only one guest controller is expected to own the bus at a time.

The patch is replayed after the retained QEMU patch stack and its reverse
preimage check passes. The board only has one panel object; this is bus
routing, not a second display.

## Device Service validation

The fixture keeps the original public `boot.py` SD-card setup, then executes
the legacy `from m5stack import *` and LCD drawing path, prints a completion
marker, and stays alive for frame capture.

| Item | Value |
| --- | --- |
| Test image SHA256 | `49b7f8840ee1cfaf75ecb1a41743b428f2aa86204c86ccddcf660694a9ae8ae6` |
| VFS SHA256 | `e62094d77f18136317b2b8169ff0e7520b1a37c1a9fb691110cb855f518b9419` |
| QEMU SHA256 | `6ff2aca091909ea078e5b9805b420cb04c11e3f9928b52c2fac199e33e45b2ef` |
| Runtime | Device Service `/api/v1`, `qemu-wifi`, `core2-openmac` |
| Pause | `120.000000030 s` |
| Serial | `652` bytes, SHA256 `8c0dc777…` |
| Frame | `320x240`, `1422` nonblack pixels, `2` colors |
| Frame SHA256 | `55249d07a37cf4b3f00825a4834c3ec99bf7aab466de8296a5ac11a9011f787b` |
| Session ID SHA256 | `92683e855c955328f9b7762529e8fd6c3c85d2737905cc852b158df4eab866aa` |

Serial markers:

```text
CORE2_LEGACY_ORIGINAL_BOOT_START
CORE2_LEGACY_ORIGINAL_BOOT_DONE
CORE2_LEGACY_DISPLAY_PROBE_DONE
```

The frame visibly contains `CORE2 LEGACY` and `PANEL ROUTING`.

## Remaining `RUNTIME-03` work

The original public startup UI with the same dual-SPI routing still does not
complete a meaningful frame, and normal-WDT still enters a TG0 system reset.
The probe PASS closes the panel-controller routing defect only; it is not an
original application startup PASS.

## Boundaries

- Only virtual-device validation.
- The probe changes `/flash/boot.py` to draw and remain alive.
- No physical panel, SPI signal integrity, brightness, touch or timing claim.
- No RF, electrical or hardware validation.
