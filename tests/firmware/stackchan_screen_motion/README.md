# StackChan screen input while its servos move

This diagnostic runs the original StackChan-BSP motion task and the original
M5Unified/M5GFX screen input driver together. It distinguishes the FT6336U
screen (`M5.Touch`) from the three Si12T top electrodes
(`M5StackChan.TouchSensor`). A top touch does not establish screen coverage.

Use the pinned BSP commit `e2f3b02dbe7f28e26a02adc72bef3aa2c545e4a0` from
`https://github.com/m5stack/StackChan-BSP`. Keep the BSP source unchanged in the
ignored build project's `lib/StackChan-BSP`; `sources.lock.json` records the
observed source/dependency identity. Build with PlatformIO 6.1.18 and `-j2`.

`screen_polling` calls `M5StackChan.update()` every loop, reports screen
press/release coordinates and visible counters, and alternates real Motion
targets after twenty seconds. The UI goes green while pressed and blue when
released. It does not use serial or host callbacks to manufacture touch data.
The motion task sends actual UART1/SCS commands. Touch telemetry does not call
synchronous UART angle reads. It reports the last/max input polling gap and
individual update, small-field draw, report and Motion-command costs; actual
shaft acceptance uses independent same-guest QOM present positions and rejects
invalid-ReadPos fallback logs. The passive FT6336U reads use the guest's original
I2C API, and do not supply or alter M5.Touch results. Version 2 reports touch
edges before drawing and changes only a small counter/status field. Version 1's
large redraw and synchronous angle reads could delay release reporting, so its
results must not be silently relabelled as the lighter version. Version 3
keeps the serial counters/timing and changes only an 8x8 status block during
input polling, with a distinct nonce and composed-firmware identity; earlier
versions and their failures remain separate.

`screen_blocked_control` is an intentional application negative control. After
40 seconds it prints `blocked_begin`, issues a slow move and calls real
`delay(6000)` without polling M5 input. The BSP motion task remains scheduled.
A screen pulse wholly inside this interval need not produce an application
event; a held contact can be sampled after polling resumes. This demonstrates
the distinction between controller input and an application that does not
sample it. It does not establish the cause of an unavailable user firmware.

The fixed official `examples/Servo/Dance/Dance.ino` likewise calls
`M5StackChan.update()` outside its dance frame loop, then performs
`Motion.move(...); delay(frame.interval)` inside the loop. The Motion task and
the M5 touch polling paths do not share Motion's mutex. Those source facts
alone do not establish emulator behavior, scheduler timing or physical behavior.

Copy this source/config into a new ignored `.work/` project, clone or link the
fixed BSP, build each environment and compose a 16 MiB image with
`tests/firmware/stackchan_arduino_nvs/merge.py`. Raw firmware, ROM, frame series
and serial traces must remain outside source Git. No hardware, native guest or
browser PASS is implied by a successful build.

The opt-in browser runner is
`platform/tests/test_stackchan_screen_motion_guest.mjs`. It requires explicit
`M5_PUBLIC_SITE`, `M5_STACKCHAN_WASM_SHA256`,
`M5_STACKCHAN_MANIFEST_SHA256`, `M5_STACKCHAN_SCREEN_IMAGES_JSON` and a new
`M5_STACKCHAN_OUT` directory beneath `.work/`. The image JSON maps
`screen_polling` and `screen_blocked_control` to relative `path` plus measured
`sha256`, and `reference` to the exact public profile's composed-firmware
`sha256`. No image is embedded in the runner. Select cases through
`M5_STACKCHAN_SCREEN_CASES`; without a site it explicitly skips.

The runner checks real DOM pulses of 100/300/800 ms while idle and moving,
independent UART1/SCS present-position changes during those held intervals,
screen coordinates and actual texture pixels. A raw-frame 300 ms touch is a
separate diagnostic, not a replacement for the moving-screen pointer path.
The exported public UIFlow2 reference is a third case using its actual browser
composer and exact profile firmware bytes. Its original Touch API is the I2C delivery
witness; independent raw FT register telemetry is confined to this Arduino
probe, not spliced into the reference result. All stopped instances must reach
zero independent CDP Worker targets before closing their browser context.
