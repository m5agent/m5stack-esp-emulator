# Tab5 deferred backlog

Date: `2026-10-22`

Last reviewed: `2026-10-24`. The evidence baseline remains the focused
`2026-10-22` probes; no newer Tab5 data plane is implied.

## Status

Tab5 is usable as a partial virtual host, but its full peripheral data plane is
deferred. It must not be described as a complete replacement for a physical
Tab5, and its current virtual flashing path is not yet a universal production
firmware flasher.

## What already works

- Official UIFlow2 P4 firmware boots through `esp-emu 0.50.0`;
- M5GFX renders a physical landscape `1280x720` frame;
- touch injection reaches the UIFlow2 application through the test mailbox;
- SIT3088 RS-485 passes through UART1 G20/G21 and direction G34;
- C6 ESP-Hosted starts and the P4 side runs the official UIFlow2 path;
- static I2C register probes cover INA226, RX8130 and PI4IOE;
- a merged image can be written by real `esptool` in 1 MiB chunks to a 16 MiB
  virtual flash, byte-verified, and booted from that same image.

On 2026-10-22 a focused probe rebuilt the Tab5 UI image, flashed it through
`esptool`, verified the virtual flash, booted it, and reached `TAB5_UI_DRAWN`.
This proves virtual flash/boot capability only; it does not close the missing
peripheral data planes.

## Flashing boundary

The current path requires:

1. a 16 MiB merged image produced for the emulator build;
2. the matching P4 ROM, eFuse and ELF files;
3. a partition layout whose populated regions stay below the current P4
   download-mode address limit;
4. the emulator-specific `factory/sys/vfs/storage` layout used by the test
   image.

Therefore “Tab5 can be flashed” is true for the validated emulation image, but
“any production Tab5 image can be flashed unchanged” is not yet proven.
Production images must be checked for address range, partition layout, ROM
revision, eFuse state and image size before being used.

## Deferred data planes

| Area | Missing capability | Acceptance condition |
| --- | --- | --- |
| Dynamic I2C | Host updates device state while the guest is running | BMI270 samples, RX8130 progression, INA226 alert, PI4IOE IRQ and IP2326 state transitions are readable without restart |
| Audio | P4 I2S/GDMA and codec endpoints | ES7210 microphone RX and ES8388 speaker TX produce verified PCM |
| Camera | MIPI-CSI/DMA and SCCB camera model | SC2356 configuration and deterministic frame reach `camera.snapshot()` |
| USB Host | P4 DWC host controller and endpoints | Chapter 9 enumeration and at least one functional endpoint |
| Storage | SDIO block backend | Guest block I/O is visible in a host image |
| Touch | Controller-level ST7123 model | Touch coordinates arrive through the I2C controller, not a GDB mailbox |
| Charger | IP2326 analog/current/termination state machine | Charging, current limit and termination states change at runtime through the normal power API |

## Rough effort

With a rebuildable or extensible P4 backend:

| Group | Estimate |
| --- | --- |
| Dynamic I2C + PMIC/RTC/IMU/charger | 3–5 working days |
| P4 I2S/PCM | 2–4 working days |
| MIPI-CSI/SC2356 | 3–5 working days |
| USB Host | 4–7 working days |
| SDIO | 2–4 working days |
| ST7123/IP2326 | 2–3 working days |
| Integration, regression and real-device retest | 3–5 working days |

This is roughly 4–6 serial work weeks, or 2–3 weeks with independent
workstreams. Keeping the current closed-source backend gives no reliable
completion estimate for these interfaces.

## Resume conditions

Resume the backlog when any of the following becomes true:

- a firmware under review requires camera, audio, USB, SDIO or dynamic power
  telemetry on Tab5;
- ST7123 touch or IP2326 charging behavior becomes part of a release gate;
- a rebuildable P4 backend is selected;
- a production image cannot be represented by the current emulator partition
  layout and therefore needs a compatibility pass.

## Required evidence before closing

- one reproducible Tab5 profile runs the full scenario set without preloaded
  host-only values;
- every catalog component is `simulated`, not `partial`;
- the completion-policy exemption is removed;
- flash, boot, display, touch, audio, camera, USB, storage and power evidence
  are linked from the same run;
- real-hardware validation is completed before any external claim that the
  fix is production-ready.
