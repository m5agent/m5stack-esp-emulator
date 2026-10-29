# CoreS3 LVGL wallclock scheduling candidate

This is the explicit `sdk-python-single-schedule-v1` SDK candidate lane, derived
from `cores3_lvgl_pir`. It is not stock-firmware scheduling evidence.

The pinned official `m5ui/port.py` uses a 30 ms `m5utils.Timer`. Its FreeRTOS
callback first queues Python `timer_cb`; `timer_cb` queues `task_handler` a
second time. `max_scheduled` limits only the second stage. That stage can raise
`schedule queue full`, while failed first-stage `mp_sched_schedule` calls
silently drop timer events. Advancing LVGL by a fixed 30 ms per callback then
loses elapsed time. Exceptions also leave the stock `scheduled` count elevated.

`candidate_lvgl_loop.py` explicitly replaces only `m5ui.port.event_loop` and
registers itself as `_m5emu_lvgl_loop_candidate` in `sys.modules`. The original
M5UI display, flush, touch, filesystem and widget implementations remain in
use. The first callback already executes in the Python VM, so it calls the
LVGL handler directly. `time.ticks_diff` advances LVGL by real elapsed guest
milliseconds, including callback delays or drops. `finally` releases the
execution guard; exceptions remain visible. Stale owned callbacks after deinit
become no-ops, and initialization finishes before starting the timer.

This Python-only candidate does not coalesce the first-stage C Timer queue or
change generic Timer callback semantics. A successful run proves only this
explicit fixture lane. Bounded pending C callbacks require a separate opt-in
SDK Timer correction.

Package all three Python files. Use a dedicated static browser test port and
the normal VM clock (divisor 1); do not use `vm-div8`, icount or disabled WDT.
Record source, firmware and runtime hashes, actual serial/frame/input results,
browser JSON evidence before stop (native Device Service ZIP if that lane is
run), retained history and Worker cleanup. The fixture adds an
actual 100 ms LVGL timer moving a star based on elapsed guest time. Heartbeats
report guest and LVGL clocks, handler/callback counts, exceptions and animation
samples. Compare their rates with host monotonic time; a quiet error log alone
does not prove queue progress or correct clock speed.

Recheck real touch pressed/released/clicked, two button increments and PIR
false/true/false using controller inputs. Observe readable frames and the
moving star. Keep original and candidate results separate; neither is a
hardware or physical timing measurement.

`compose.py` verifies the contract's three source hashes and raw/normalized base
identity, uses the repository's `uiflow_source` builder, and writes only local
`candidate.bin` plus hash/readback provenance. It requires Python 3.12+ with a
compatible `littlefs-python` installed. Keep its output in ignored storage:

```sh
python3 tests/browser-qemu/cores3_lvgl_wallclock/compose.py \
  --base /path/to/pinned-local-base.bin --output-dir .work/lvgl-wallclock-fixture
M5_PUBLIC_SITE=.work/qemu-fast-site \
  node platform/tests/test_public_qemu_wallclock_guest.mjs
```

The browser runner creates a dedicated static server on an ephemeral loopback
port and a test harness using the real `PublicQemuRuntime`. It explicitly sets
`allowCandidateProfiles` and `clockDivisor=1`; the original production demo
identity is not modified. It hashes the exported runtime/web assets and fixture,
observes the actual guest, and exports evidence before stopping. Its current
PIR bridge can read back `motion`, but not `input-level` or `input-events`; the
report identifies those controller observations as unavailable rather than
claiming the entire fixture oracle. It does not start native services or QEMU.
