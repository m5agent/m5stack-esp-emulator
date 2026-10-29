# Reproducible Xtensa source prelude for external Units

Date: `2026-10-27`.

The Unit patches are built from public source, rather than by modifying the
published executable. This directory supplies the missing source prelude; the
new Unit implementation stays in `qemu-m5stack-peripherals/0033` through `0035`,
followed by the narrow classic-I2C compatibility fix in `0036` and the scoped
S3 LEDC duty-register readback fix in `0037` and the GPIO-route observation
candidate in `0038`, then the independent bounded Scroll controller in `0043`
and dual GPIO 2Relay in `0044`, then the partial AW3641E GPIO-edge/timer
FlashLight model in `0045`, then scoped route-lifecycle invalidation in `0046`.
`0047` adds controller-owned cold-pad observation, and `0048` adds the
official UIFlow2-compatible 8Servos HAT, 8Servos Unit, Joystick2 and NFC Unit
register/controller attachments.
`0049` keeps the Core2 WiFi controller present when no WiFi network backend
is configured, with its synthetic radio disabled.
`0050` fixes the classic SPI panel's DMA transaction boundary and FIFO stream.
No firmware, ROM, executable or credential is added by these patches.

## Exact source and order

1. Clone `https://github.com/espressif/qemu.git`, tag
   `esp-develop-9.2.2-20260417`.
2. Verify the resolved **commit** is
   `40edccac415693c5130f91c01d84176ae6008566`. The tag object itself is
   `6cdce334bfa5541a5e46c860a9b40a4fe5a13aae`; these are different Git objects.
3. Apply `0001-reconstructed-xtensa-source.patch` from this directory.
4. Apply `0002-wifi-radio-lifecycle-compat.patch` from this directory.
   Apply `qemu-m5stack-peripherals/0034-xtensa-ccompare-equal-deadline.patch`
   before the Unit layers. The reconstructed source otherwise retains the
   older timer arithmetic that defers an equal CCOMPARE deadline by 2^32
   cycles. This existing timer fix is independent of the Unit I2C patch with
   the same numerical prefix.
5. Apply `qemu-m5stack-peripherals/0033-unit-runtime-core-and-routing.patch`,
   `0034-unit-i2c-sensors.patch`, `0035-unit-i2c-controls.patch`, then
   `0036-core2-soft-i2c-handoff-compat.patch`, then
   `0037-s3-ledc-duty-readback.patch`, then
   `0038-unit-pwm-route-refresh.patch`, then
   `0043-unit-scroll-controller.patch`, then
   `0044-unit-2relay-gpio.patch`, then
   `0045-unit-flashlight-aw3641.patch`, then
   `0046-unit-flashlight-route-lifecycle.patch`, then
   `0047-unit-flashlight-cold-pad-observation.patch`, then
   `0048-unit-servos8-joystick2-nfc.patch`, then
   `0049-core2-offline-wifi-controller.patch`, then
   `0050-esp32-spi-panel-dma-transaction.patch`.
6. Build `xtensa-softmmu`. These instructions do not rebuild the separate C6
   branch or the P4/Linux backends.

`0033` intentionally references the new C files supplied by `0034` and `0035`;
all three must be applied before configuring/building. Do not apply the older
historical board/peripheral snapshots on top of this prelude again.

`0036` removes the new permanent software-I2C handoff from the classic ESP32
hardware transaction path. Core2 M5GFX/Power may return to bit-banged I2C after
hardware access; the S3 one-way handoff is not a classic-controller contract.
The patch leaves S3 handoff and Unit bus routing unchanged. The same AXP192
guest image fails with OSError(19) on the five-patch runtime and passes on the
six-patch candidate; the six Core2 regression cases also pass. Earlier five-patch
runtime receipts remain historical evidence for their exact binary SHA.

`0037` adds only ESP32-S3 channel DUTY/DUTY_R reads: addresses below `0xa0`,
channel stride `0x14`, offsets `0x8` and `0x10`, returning the existing
`channel_duty_reg` low 19 bits. Classic ESP32 reads, duty writes and PWM output
observation are unchanged. Register readback is not forced to zero by
`sig_out_en` or timer pause.

This is a **settled set+update readback** repair within the existing immediate
duty model. It does not implement pending/current-cycle separation, an active
latch, fade intermediate values, HPOINT or exact next-period commit timing.
The official IDF API says `set_duty` needs `update_duty`, and `get_duty` returns
the present PWM cycle, which can differ from a newly requested value. Those
semantics remain model gaps; DUTY and DUTY_R are not claimed to be universal
hardware synonyms. The fixed-source references are Espressif IDF commit
`b774170ff46c393eeb5e495ea37936038d3f4f4f`:

- [S3 register layout](https://github.com/espressif/esp-idf/blob/b774170ff46c393eeb5e495ea37936038d3f4f4f/components/soc/esp32s3/register/soc/ledc_reg.h)
  defines the two offsets and 19-bit fields.
- [S3 LEDC low-level API](https://github.com/espressif/esp-idf/blob/b774170ff46c393eeb5e495ea37936038d3f4f4f/components/hal/esp32s3/include/hal/ledc_ll.h)
  shifts integer duty into/out of the register by four bits.
- [Driver API](https://github.com/espressif/esp-idf/blob/b774170ff46c393eeb5e495ea37936038d3f4f4f/components/esp_driver_ledc/include/driver/ledc.h)
  documents update and current-cycle behavior; reviewed bytes have SHA256
  `8ac4036faeca0c487f67af316baa944dc07e4ca689a683f9b2dba13843410378`.

Source replay and static/fragment contract checks do not establish a firmware
or hardware PASS. A new runtime needs a cold source build, the same diagnostic
guest with its exact firmware SHA, and the shared-controller regression gate.
Use a fresh `--source-dir` for the current patch stack; the bootstrap intentionally
rejects an older source receipt instead of resetting it.

`0038` is a GPIO-route observation candidate for `UNIT-HOST-20`. An actual
GPIO matrix OUT_SEL mutation notifies realized LEDC instances of the same SoC
layout; they recompute Unit observations from the existing live timer, channel
configuration and duty registers. The callback never replays an MMIO write or
`led_set_intensity`. Unrealized LEDC instances are removed from the observer
list, and the Unit observer also filters `g->s3` to prevent cross-layout writes.

Zero duty retains a configured frequency; `sig_out_en` and timer pause/reset
continue to mask observed duty only. Removing a route retains the existing
getter gate returning zero; restoring or reassigning it refreshes current LEDC
state. DUTY/DUTY_R reads are unchanged. This does not implement a PWM waveform,
inversion semantics, pending/current-cycle commit timing, fade, new clocks or
physical behavior. Offline C/source replay and a cold build establish only a
candidate. The recorded d1ba build has since passed same-firmware Device Service
initialization and shared-controller regression gates; `UNIT-HOST-20` is FIXED
for route observation only. Full-cycle/fade and physical behavior remain OPEN.
See the [scoped evidence](https://github.com/m5agent/m5stack-esp-emulator/blob/a37342f61c05964c060719a6e35c2d568c828e84/docs/evidence/2026-10-26-unit-pwm-route-d1ba/README.md);
a later build or firmware still needs its own verification.

`0043` adds a separate `CONTROL_SCROLL` at the real routed I2C bus. It preserves
the pinned ae60717a application's int32 registers, pointer-time increment
snapshot/clear, finite TX continuation and original UIFlow low16 API. Physical
source ticks remain separate from writable/reset logical counts. The model is
partial: bounded non-rollover TIM16 input with signed-overflow rejection;
synchronous quiescent RGB latest-value behavior without the MCU queue;
no bootloader, configuration Flash persistence, address-zero unicast or mechanical
angle calibration. A rejected completed frame increments `command-errors`;
it does not retroactively create a wire NACK. See the
[protocol audit](../../docs/unit-research/scroll-roller485.md).

`0045` observes U152 yellow EN pad edges using QEMU virtual nanoseconds and
independent timers. Flash/Torch mode is a synthetic creation fixture, frozen
after all initial properties are applied. Flash decode qualifies 1–16 pulses
only on the supported GPIO route and within the recommended 750–10000 ns
HI/LO window; other waveforms produce unknown output. Waiting 500 us at stable
high before decode and measuring timeout from the first rise are model policies,
not datasheet claims. The timer cancels stale deadlines, keeps the last decoded
code after timeout, and exposes a bounded chronological edge trace. Torch
supports static EN only. Reset observation, dynamic S1, PWM modulation,
bit-exact timing, current, optical, thermal and electrical equivalence remain
outside this source implementation; source checks do not establish guest PASS.

`0046` observes actual GPIO matrix OUT_SEL lifecycle changes for the same SoC
layout and EN pin. Leaving or restoring a route withdraws old FlashLight
qualification, all pending reset/settle/timeout timers and low-interval origins.
Unsupported pad callbacks cannot establish a reset baseline. Route writes do
not add pad edges or decoded programs; recovery requires a new observed GPIO
falling edge and a complete long-low reset. New-runtime Device Service checks
establish only the scoped route-history admission below; the independent full
matrix retains its Core2 IMU failure (UNIT-HOST-21), not an all-green release.
Cold-route/no-edge recovery, dynamic S1, PWM and physical behavior remain OPEN.

`0048` adds only device-local I2C register/controller paths for issue fixes:
StickS3 Hat2-Bus `servo8-hat` at `0x36`, CoreS3 Port B `8servos` at `0x25`,
CoreS3 Joystick2 at `0x63`/`0x64`, and the existing deterministic ST25R3916
fixture as an NFC Unit at `0x50`. It models guest-visible registers,
transactions and synthetic fixture state. It does not model servo motion,
current, RF, antenna behavior, electrical limits or physical hardware.

`0049` fixes a separate Core2 board-wiring omission. A default Ethernet NIC
can consume the unnamed QEMU network configuration before WiFi initialization;
with no explicit WiFi NIC, the old path omitted the on-chip MAC register map
and interrupt route entirely. Core2 now realizes the existing WiFi MAC/DMA/IRQ
model even without a backend, and immediately disables its `radio-enabled`
property to cancel synthetic AP beacons and queued injections. It creates no
host network backend and supplies no Python WLAN values. Explicit WiFi NICs
retain their configured backend and radio behavior; other boards retain their
existing initialization. This is controller availability for offline driver
initialization, not proof of connectivity, RF behavior or physical hardware.

`0050` fixes visible LVGL text corruption in the classic ESP32 SPI panel path.
The existing implementation streamed the DMA chain immediately on OUT_LINK,
then streamed stale FIFO bytes again on USR, repeating the last FIFO pixel for
the remainder. OUT_LINK now only arms the descriptor chain. The following USR
clocks descriptor bytes through SSI and the panel once, bounded by MOSI length,
and clears the pending chain. Ordinary long non-DMA writes repeat the selected
FIFO bank rather than reading past it or synthesizing a last-pixel tail.
The real driver path is LVGL `gfx_lvgl_flush` through M5GFX `pushImage`,
`Panel_LCD::writePixels` and classic `Bus_SPI::writeBytes`; it is not a Python
display shortcut. The same UIFlow2 probe rendered torn full-width lines before
this patch and readable text at its requested coordinates afterwards.

This change covers transmit data delivery and its transaction boundary. It does
not add descriptor-owner/writeback semantics, DMA error/IRQ status, receive DMA
or descriptor continuation across several USR commands. Short chains deliver
only their actual bytes, and a bounded descriptor walk prevents cyclic chains
from hanging the host. Physical display timing remains outside this validation.

## Why a prelude is necessary

The historical patch directories preserve snapshots from several development
trees. They do not form one mechanically applicable sequence. The following
were reproduced on the fixed public source:

- `zqqf16/M5StopWatch-QEMU` v0.1.0, commit
  `32d86576e783988fef1a489cb362dfda92a7aeda`, supplies its five public patches.
- The repository's peripheral `0003` applies after those five patches, but its
  Meson file refers to five absent files: `m5_can_peer.c`, `m5_scs_servo.c`,
  `m5_spi_sd.c`, `m5_uart_peer.c`, and `m5_i2s_esp32.c`. Their complete new-file
  hunks are present in historical peripheral `0002`; those files were recovered
  from that source, without editing the old patch.
- Peripheral `0004` already has its S3 PCM fix in the `0003` snapshot, while its
  classic I2S fix still needs applying to the recovered classic source.
- The shared I2C BQ27220/ES8389 layers needed by peripheral `0006` are in the
  Linux patch group's `0001`/`0002`. They were recovered as shared source;
  this does not claim a Linux backend rebuild or validation.
- Later Xtensa/S3 peripheral layers and Core2 OpenMAC/BT/native-HCI layers
  were merged into that tree. The separate C6 controller layer is not substituted
  into the Xtensa tree. Historical ARM camera/USB model material is retained
  only as source; `xtensa-softmmu` does not compile or validate it.
- The UART2 comment/context in peripheral `0023`, the WLAN formatting/context
  in `0028`, and includes/AP setup context in `0029` differ from the recovered
  source. The equivalent source changes were merged and then exported from Git.
- `radio_enabled` and real WLAN cleanup were only context in the later patches,
  rather than complete source. `0002` is a new compatibility implementation of
  the existing `radio-enabled` QOM/network-fault contract: actual frame gating,
  AP timers, queue cleanup, and deauthentication through guest RX DMA.

`0001` was generated from the exact reconstructed Git worktree. It contains the
pre-Unit source delta only. `0002` and the Unit patches remain separate review
units. The original historical patches have not been rewritten.

## Local bootstrap

The current product recipe is the `PATCHES` tuple in
`scripts/bootstrap-unit-runtime.py`. Its 2026-10-29 integration retains the
previous 37 logical layers and adds the five expanded-board layers
`0085`–`0089`, for 42 applied patches. Historical `0065`, `0066`, `0069` and
`0070` were based on a different diagnostic/Unit context and did not replay on
the reconstructed source. Native `0003`–`0006` preserve their functional C
changes while re-anchoring those contexts. Native `0007` applies the `0088`
Atom board and RMT improvements after the existing `0066` implementation;
it does not create the same controller, declaration, SoC call or Meson entry
twice. Its final classic RMT source matches portable `0088` byte for byte.

The already-excluded historical `0071`–`0084` files are not silently added by
this integration. Their presence in the patch directory does not make them
part of the product recipe or grant their functionality to this build.
The browser recipe uses a different native prefix and explicit WASM suffix;
its patch count and runtime validation must be reported separately.

The isolated source-only replay on the pinned `40edccac` source passed all
42 forward and reverse checks, returned to a clean upstream tree, and
reproduced the same 124 patched-file hashes. Offline checks additionally
compare the context-port changes, replay the RMT delta against `0066`, and
execute the native protected-WDT-feed branch. This establishes source
integration only. A local native build with `--disable-slirp` also compiles;
that configuration is a functional-test candidate with no SLiRP networking.
Its own Device Service regression remains required before replacing an
existing runtime or transferring a guest PASS from a different recipe.

Use Python 3.10 or newer:

```bash
python3 scripts/bootstrap-unit-runtime.py --check
python3 scripts/bootstrap-unit-runtime.py --prepare-only
python3 scripts/bootstrap-unit-runtime.py --check
python3 scripts/bootstrap-unit-runtime.py --jobs 8
```

The script builds under `.work/unit-runtime-source/` and
`.work/unit-runtime-build/`. `--source-dir` and `--work-dir` allow alternate
isolated locations. `--check` does not download or build: before preparation it
reports `not-prepared`; afterwards it verifies the pinned source HEAD, patch
hashes, every patched source hash and the absence of unrelated checkout changes.
It refuses to reset an existing unowned/changed checkout. If a patch changes,
select fresh source/build directories instead of resetting the previous tree.
Source receipts record patch hashes and all resulting source-file hashes.

On macOS, the system `python3` may be 3.9; use an installed Python 3.10+ interpreter
for every command above. The script does not replace the system Python.

Host requirements are a C compiler, `make`, Git, Python `venv`, and existing
GLib/pixman development packages discoverable by pkg-config. The script does
not run Homebrew/apt or install global packages. It builds pinned pkgconf,
libgpg-error and libgcrypt from SHA256-checked official archives, and builds
libslirp from its official Git repository at
`26be815b86e8d49add8c9a8b320239b9594ff03d` (the QEMU wrap pin). Ninja and Meson
are installed only into the local build venv.

The resulting runtime has user networking and uses the matching source tree's
`pc-bios` directory. It has no native graphical window; the Device Service reads
the guest framebuffer and encodes its own PNGs. This build does not bundle the
host's GLib/pixman libraries or promise a relocatable binary.
`build-manifest.json` records the resulting executable SHA256. Repeating a
source preparation verifies the same source bytes; a different host/compiler
may produce a different executable hash.

```bash
M5_QEMU_XTENSA="$PWD/.work/unit-runtime-source/qemu/build/qemu-system-xtensa" \
M5_QEMU_XTENSA_ROM_DIR="$PWD/.work/unit-runtime-source/qemu/pc-bios" \
python3 platform/tools/serve.py 18879 \
  --state-dir .work/unit-runtime-service \
  --api-token-file .work/unit-runtime-service.token
```

Prepare a separate private token file and check that the selected port is
available. Port `8787` belongs to the user's testing service. Service Python
dependencies and compatible reference/uploaded firmware must be prepared
separately. Firmware execution and input tests must use visible
Device Service sessions, collect evidence before stop, and retain history with
`purge=0`. Building, source replay, or `--version` is not a firmware PASS.

## Unit implementation boundaries

The linked source dispatch covers the following 28 catalog IDs. This inventory
records implementation scope, not the per-Unit functional acceptance result.

| Source | Catalog IDs |
| --- | --- |
| `m5_unit_runtime.c` | `button`, `relay`, `env-iii` |
| `m5_unit_gpio.c` | `pir`, `dual-button`, `limit`, `key`, `rgb`, `angle`, `light`, `buzzer`, `fan`, `ir`, `rs485`, `hub` |
| `m5_unit_i2c_sensors.c` | `color`, `tof`, `ncir`, `heart`, `tvoc`, `ultrasonic-i2c`, `thermal` |
| `m5_unit_i2c_controls.c` | `joystick-v11`, `encoder`, `8encoder`, `cardkb`, `rfid2`, `scroll` (partial) |

- Unit configuration is session-scoped `M5_UNIT_CONFIG` JSON; the manager exposes
  `/machine/units/schema-version=1`. Unknown Unit IDs and unavailable controller
  paths fail closed. Attachments are fixed at machine construction.
- I2C slaves live on connector-specific physical buses. A hardware controller
  reaches that bus only when both its SDA/SCL input and output GPIO-matrix
  routes match the connector. S3 software-I2C handoff is scoped to each bus;
  classic ESP32 retains its pre-Unit software/hardware switching behavior.
- GPIO input, edge/level IRQ, output observation, SAR ADC channel selection,
  LEDC registers, RMT memory/interrupts and UART FIFO remain in QEMU C. Python
  and browser code only set physical fixtures or read model state.
- ADC conversion uses an explicitly ideal 12-bit attenuation transfer; it does
  not establish calibrated ADC accuracy or electrical timing. PWM observation
  currently follows the configured divider/resolution with the APB clock path;
  alternate clock calibration is a separate boundary.
- RGB/IR/UART Unit paths currently use the S3 controllers. The same Unit is
  rejected on the classic Core2 path when its controller route is unavailable.
  RMT frames shorter than the requested LED chain count remain incomplete and
  never produce a fabricated complete LED frame.
- RMT non-DMA TX consumes the configured physical memory in order, raises the
  real half-buffer threshold interrupt, waits for guest acknowledgement/refill,
  and publishes a completed capture only at the hardware stop/EOF condition.
  The finite capture is capped at 4096 symbols; overflow raises TX error.
  APB and XTAL divider paths are decoded; RC_FAST calibration, DMA and continuous
  loops remain outside this validated path. Pulse conversion widens before
  multiplying ticks by microseconds, preserving long NEC leaders.
- Thermal requires the explicit EEPROM/raw-frame fixture contract in `0034`;
  absent raw evidence is NACKed. Synthetic test fixtures are not physical
  calibration or hardware validation.
- Each Unit/host/firmware path still needs its own Device Service evidence.
  A passing Unit does not grant another Unit, firmware SHA or controller path
  the same result. Current acceptance belongs in the status/backlog/ledger.


The historical `0045`-only FlashLight admission covers continuous qualified
GPIO. Its route mismatch only suppresses the getter and can expose an old
qualification after restoration. That original host C reproduction is retained
as `UNIT-HOST-38`; `0046` targets it with an internal lifecycle invalidation.
New source checks alone do not grant guest/Web/hardware PASS. Runtime `3f1617`
has since passed four-host/eight-lane actual same-VM API and CoreS3 mounted Web
route-history checks. The independent full matrix is 66 PASS / 1 Core2 IMU FAIL;
UNIT-HOST-38 closes only for the documented OUT_SEL path. Cold-route/no-edge,
hard-reset, full OEN/IOMUX, dynamic S1, PWM and hardware equivalence remain
separate. See the [scoped evidence](https://github.com/m5agent/m5stack-esp-emulator/blob/a37342f61c05964c060719a6e35c2d568c828e84/docs/evidence/2026-10-27-flashlight-route-history/README.md).

`0047-unit-flashlight-cold-pad-observation.patch` adds controller-owned pad
commits, fresh continuous-low FlashLight reset and explicit weak soft-I2C bus
pull-ups. The first candidate exposed a CoreS3 detection regression; its
failure and the repair are preserved in the [cold-pad record](https://github.com/m5agent/m5stack-esp-emulator/blob/a37342f61c05964c060719a6e35c2d568c828e84/docs/evidence/2026-10-27-flashlight-cold-pad/README.md).
New Unit API/Web and a new full matrix remain unrun at this wrap-up boundary;
C/source/build checks must not upgrade the older guest validation records.
