# 2026-10-29: Core2 legacy contended-CAS hold intervals

## Result

`0086-esp32-legacy-cas-episode-profile.patch` extends the default-off
`RUNTIME-03` handoff trace with bounded cross-core CAS episodes. An episode
starts when one CPU observes another CPU holding a lock, records subsequent
failed attempts and closes on success, lock change or an I/O-capable helper
observation.

The patch also fixes the diagnostic itself. The first episode implementation
called `qemu_clock_get_ns(QEMU_CLOCK_VIRTUAL)` from a no-I/O translation block
and QEMU terminated with `Bad icount read`. Sampling now skips that unsafe
state without changing the guest instruction stream or CAS result.

This milestone makes the lock-budget observations stable; it does not close
`RUNTIME-03` or change Core2 startup/watchdog behavior.

## Evidence

Two independent 10-second exact-time freezes used the same normalized public
firmware and QEMU binary. One retained the normal watchdog; the other used the
established WDT-off diagnostic control. Both sessions stopped with `purge=0`,
retained history, released the lease and left no QEMU process.

| Field | Normal WDT | WDT off |
| --- | ---: | ---: |
| QEMU / patch / firmware | `0a63c37f…` / `4e86512c…` / `18d77e28…` / `4d2d648b…` | same |
| Freeze | `10.000000000 s` | `10.000000031 s` |
| CAS episodes | `238` | `253` |
| Episode time | `9.316534114 s` | `7.825981502 s` |
| Longest episode | `631 ms` | `581 ms` |
| Incomplete at freeze | `2` | `2` |
| `0x3ffbf2cc` episodes | `162` | `166` |
| `0x3ffbf2cc` episode time | `6.743534018 s` | `6.600981470 s` |
| `0x3ffbf2cc` maximum hold | `482.823328 ms` | `581.176638 ms` |
| `0x3ffbf2cc` failed attempts | `1,001`, max `53` | `1,145`, max `65` |
| Longest inter-attempt gap | `110.034978 ms` | `80.997600 ms` |

The normal-WDT run also measured `31` episodes on `0x3ffb7ab0`, totaling
`2.559000096 s` with a `631 ms` maximum. The WDT-off run measured `30`
episodes on that lock, totaling `1.133000000 s` with a `274 ms` maximum.

Normal-WDT CPU PCs at freeze were CPU0 `0x40087986` and CPU1 `0x40095c3c`;
WDT-off PCs were CPU0 `0x4008798b` and CPU1 `0x400871fb`. These remain
BIN-bound addresses because the matching legacy ELF/MAP is unavailable.

## Scheduler attribution

The BIN contains one 32-bit literal for `0x3ffbf2cc` at VMA `0x40081174`.
Its callers and surrounding instruction/control structure match the public
ESP-IDF v3.3.5 `xTaskQueueMutex` implementation:

- `0x4009582d` uses the lock while walking delayed/ready lists, matching
  `xTaskIncrementTick`;
- `0x40096554` enters the same lock before selecting the next task, matching
  `vTaskSwitchContext`;
- the acquire loop at `0x40095a98`/`0x40095ba8` matches
  `vTaskEnterCritical`/`vTaskExitCritical`.

The second hot lock, `0x3ffb7ab0`, is `queue + 76`, matching the `portMUX`
field in ESP-IDF v3.3.5 `Queue_t`. Its waiters at `0x40094e8d`,
`0x400951cb` and `0x40095255` are in queue send/receive paths.

This is instruction/control-flow attribution against the public IDF source,
not symbol lookup from a matching application ELF. The names are therefore
provisional until the exact legacy ELF/MAP is available.

Reference:
[`tasks.c`](https://github.com/m5stack/esp-idf/blob/03810c4a065a1ecdd24a803b2c9dc4e834c7dab5/components/freertos/tasks.c)
and
[`portmacro.h`](https://github.com/m5stack/esp-idf/blob/03810c4a065a1ecdd24a803b2c9dc4e834c7dab5/components/freertos/include/freertos/portmacro.h).

## Failed-CAS yield A/B

The existing default-off `M5SW_XTENSA_CONTENDED_CAS_YIELD` exits the current
TCG slice after a failed conditional store. Episode profiling exposes an
effect that the previous reset-only comparison did not:

| Freeze | Control | Episodes | Episode time | `xTaskQueueMutex` time | `queue+76` time |
| --- | --- | ---: | ---: | ---: | ---: |
| 10 s WDT-off | baseline | `253` | `7.825981502 s` | `6.600981470 s` | `1.133000000 s` |
| 10 s WDT-off | failed-CAS yield | `64` | `1.400290688 s` | `0.446291456 s` | `0.953999232 s` |
| 15 s WDT-off | baseline | `597` | `6.090325855 s` | `5.236325055 s` | `0.825000736 s` |
| 15 s WDT-off | failed-CAS yield | `101` | `5.383785888 s` | `0.849786112 s` | `4.533999776 s` |

At 10 seconds, yield removes most `xTaskQueueMutex` waiting. By 15 seconds,
the dominant budget has moved to the queue mutex: episode count falls
substantially, but total episode time remains about `5.4 s`. This explains why
the previously measured normal-WDT stage-1 boundary did not move: yield
redistributes waiting rather than eliminating all scheduler/queue work.

## Interpretation

The main `0x3ffbf2cc` budget is not a stream of isolated single-instruction
collisions. It consists of repeated multi-attempt hold intervals lasting from
tens to hundreds of milliseconds. CPU1 is the last observed holder in both
runs. Disabling the watchdog does not remove the contention pattern, so the
episode is a cause of elapsed pre-boot work rather than the watchdog model
itself.

The measurements do not prove malformed Xtensa atomics. Correctly emulating
the guest's spinlock loop can still produce long virtual-time waits. The next
step is to bind the exact queue object and map to an independent
IDF/hash-equivalent build, then distinguish host-vCPU scheduling delay from a
guest critical section that genuinely remains held.

## Reproduction

```bash
M5_QEMU_XTENSA_ROM_DIR=/path/to/qemu/pc-bios \
PYTHONPATH=platform/tools python3 \
  tests/firmware/core2_handoff_trace/run_pause_sweep.py \
  --image /path/to/runtime03-original-vfs-probe/image.bin \
  --qemu /path/to/qemu-system-xtensa \
  --pause-seconds 10 --runtime qemu-wifi \
  --expected-image-sha256 \
  4d2d648bd8707a1789d540366015a1b90dc816b66a04163048626ea29e333ed4 \
  --service-port 8921 \
  --out-dir /tmp/m5-core2-cas-episodes-wdtoff
```

Omit `--disable-wdt` for the normal-WDT control. Raw serial, stderr, session
state, ZIPs and frame files remain in ignored or temporary storage; only the
hashes, bounded counters and reproduction command are retained here.

Set `M5SW_XTENSA_CONTENDED_CAS_YIELD=1` for the failed-CAS yield controls.

## Boundaries

- All results are `virtual-device validation`; hardware validation is
  `NOT RUN`.
- The WDT-off run is a diagnostic control, not a supported product fix.
- No physical scheduling, CPU frequency, watchdog, cache, PSRAM, Flash or
  electrical timing is claimed.
- `Bad icount read` was a defect in the opt-in diagnostic path, not a guest
  firmware failure.
- IDF function and queue-field names are instruction-structure matches, not
  matching application symbols.
- `RUNTIME-03` remains `OPEN`: the normal-WDT stage-1 reset, startup UI,
  setup/REPL and complete application frame are still unresolved.
