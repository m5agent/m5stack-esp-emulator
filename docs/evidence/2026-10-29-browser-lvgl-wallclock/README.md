# Browser LVGL normal-clock SDK candidate — 2026-10-29

The explicit CoreS3 SDK candidate passed 25 browser virtual-device checks at
normal VM clock divisor 1, with the original watchdog behavior and no icount.
This is the three-file candidate fixture, not stock frozen-SDK scheduling PASS.
The original M5UI display, touch, filesystem and PIR driver paths remain in use.

The final frozen runtime is QEMU WASM
`9c94a9407893fa7d953d1bf1932769ff52e90b3b1455f98a90185ff2bf05cba1`;
the composed firmware is
`e9500994f4c0e1708ec35f5a46146225ac330d210a2427e1fc537c33635d9554`.
The same guest produced the ordered boot markers, readable 320×240 text and
expected RGB pixels, the negative background-touch control, two complete
pressed/released/clicked sequences, and both count/button text-region changes.
PIR guest values were `0 → 1 → 0`, with QOM `motion` readback, a real MOTION
frame-region change and exact CLEAR restoration. Ready/MOTION/final PNGs were
visually inspected. The actual LVGL timer moved the star in subsequent frames.

| Steady heartbeat observation | Measured result |
| --- | --- |
| Host first-to-last sample span | 18,359.92 ms |
| Guest / LVGL elapsed advance | 18,344 / 18,347 ms |
| Guest / LVGL rate relative to host | 0.999133 / 0.999296 |
| Largest elapsed-to-LVGL tick difference | 20 ms |
| Handler runs / animation samples | 264 → 875 / 66 → 222 |
| Python scheduler errors / pending guard | 0 / 0 |

Pause stopped serial progress; resume produced a new heartbeat from the same
guest. JSON evidence was exported before QMP quit. Exit code was 0, five Workers
reached zero, explicit disposal completed, the iframe was removed, and local
history retained the firmware/runtime receipt, serial and frame hash. No native
Device Service or protected-port request occurred.

The official `m5utils.Timer` already dispatches `m5ui.port.timer_cb` in the
MicroPython VM. The stock Python callback schedules LVGL a second time, can
raise `schedule queue full`, advances only a fixed 30 ms after delayed/dropped
callbacks, and leaves its guard elevated after an exception. Candidate patch
`0026` runs LVGL from the existing VM callback, advances real elapsed guest
ticks, releases its guard in `finally`, and makes stopped callbacks inert.

The complete MIT-licensed SDK preimage is pinned to UIFlow2 commit
`3a86d8f611b3639cca755a933e01a5a829771ef1`. Eight independent regressions apply
the patch, verify pre/post hashes and reverse applicability, and execute its
actual class against the unmodified preimage. The explicit guest fixture has
six separate regressions. Neither test substitutes for guest execution.

Real Chromium packaging passed 19 positive/negative cases. The original API
still produces `78961297…bd3f`, including a manifest without the new variant.
The named wallclock API produces `e9500994…9554`, equal to the independently
composed Python image, after remounting and reading back all three sources.
Both retain 15 original files and require the exact whole-Flash hash. Source,
module, base, clock/candidate identity, missing-variant/file and cancellation
negative controls fail closed. The old top-level manifest and demo API remain
compatible; the new variant uses independent source asset paths.

`summary.json` contains only compact identities, check counts and boundaries.
Raw Flash, ROM, serial, frames, exported evidence and exact executed-source
snapshots remain in ignored storage. This lane does not establish stock SDK
scheduler PASS, C Timer first-stage coalescing, native firmware validation or
physical hardware timing. The browser PIR bridge currently exposes `motion`
readback, but not controller `input-level` or `input-events`.

Reproduce the offline SDK check:

```sh
PYTHONPATH=platform/tools python3 -m unittest discover \
  -s platform/tests -p 'test_m5ui_scheduler_patch.py' -v
```

Composition and the dedicated normal-clock browser runner are documented in
[`cores3_lvgl_wallclock`](../../../tests/browser-qemu/cores3_lvgl_wallclock/README.md).
The runner starts only an owned static loopback server and uses the real
`PublicQemuRuntime`; it exports browser JSON before stop, then checks QMP exit,
Worker disposal, iframe removal and retained local history. It never starts a
Device Service or a native QEMU process.
