# Core2 contended-CAS scheduler attribution

Date: `2026-10-29`

Validation category: **virtual-device validation**

This milestone adds a default-off host scheduler diagnostic for the final
`RUNTIME-03` contention path. It shows that single-threaded TCG's normal
`100 ms` round-robin quantum amplifies cross-core Xtensa spinlock waits. It does
not close `RUNTIME-03`: normal-WDT startup still resets at TG0 stage 1.

## Patch

`0088-xtensa-contended-cas-fair-yield.patch`:

- checks the existing real S32C1I result and holder CPU;
- only treats a failed conditional store with another CPU as contended;
- exits the current TCG slice as before;
- requests a `1 ms` RR quantum for the immediately following CPU turn;
- leaves the default `100 ms` RR behavior, guest atomics, WDT deadlines,
  `-icount shift=5` and all peripheral data planes unchanged.

QEMU SHA256:
`75e7fa97424c859c6e1fe918dda203aa2c6509e9c81937893a15d2a4a46b6714`

## Same-binary A/B at 5 seconds

Both runs used the same public firmware and QEMU binary. The control omitted
`M5SW_XTENSA_CONTENDED_CAS_FAIR_YIELD`; the candidate set it to `1`. Both
disabled only the watchdog to freeze before its normal reset.

| Metric | Control | 1 ms contended RR |
| --- | ---: | ---: |
| CPU0 PC at freeze | `0x40087986` | `0x400951fe` |
| CPU1 PC at freeze | `0x4000bff0` | `0x40095c2e` |
| S32C1I operations | `1,070,625` | `91,465` |
| Cross-core contended operations | `984,964` | `2,702` |
| CAS episodes | `212` | `16` |
| Episode time total | `2.239772672 s` | `1.017736288 s` |
| Longest episode | `378.000032 ms` | `246.999968 ms` |
| `xTaskQueueMutex` episodes | `138` | `16` |
| `xTaskQueueMutex` episode time | `1.861772640 s` | `1.017736288 s` |
| SSI `0x05` commands | `2,078` | `2,086` |
| SSI `0xBB/64` commands | `2,386` | `2,394` |

The approximately equal SSI counts show that both executions performed the same
class of Flash work by the same virtual deadline. The candidate removed almost
all repeated CAS contention and moved CPU0 out of the
`0x40087980..8e` handoff-spin cluster.

## Twenty-second control

With WDT disabled, the control and candidate remained on the same firmware and
QEMU binary. The candidate reduced CAS operations from `4,219,480` to `545,962`,
contended operations from `3,700,764` to `13,758`, episode count from `494` to
`103`, and total episode time from `15.330116502 s` to `10.449083200 s`.
Both runs recorded exactly `12,897` `0x05` and `11,845` `0xBB/64` SSI commands.
Neither produced `BOARD NAME` or `APIKEY` by 20 seconds.

## Quantum boundary

A `100 us` probe reduced the 5-second episode count to `1` and episode time to
`183.823232 ms`, but CPU0 remained at the handoff-spin cluster
`0x40087986`; at 10 seconds it was still `0x40087982`. The `1 ms` policy is
therefore the retained candidate: it leaves enough work in each turn to move
the guest beyond the handoff cluster while removing the repeated
100-millisecond lock amplification.

## Normal-WDT result

On the same binary:

- control: TG0 stage-1 timeout at `17.249439933 s`, reset at `17.249535709 s`;
- contended-RR candidate: TG0 stage-1 timeout at `17.248017950 s`, reset at
  `17.248020126 s`.

Both serial logs contain `TG0WDT_SYS_RESET`; neither reached `BOARD NAME`,
`APIKEY`, setup/REPL or an application frame. The candidate is scheduler
attribution, not a `RUNTIME-03` fix.

## Reproduction

```bash
M5_QEMU_XTENSA_ROM_DIR=/path/to/qemu/pc-bios \
PYTHONPATH=platform/tools python3 \
  tests/firmware/core2_handoff_trace/run_pause_sweep.py \
  --image /path/to/UIFlow_Core2-v1.15.4.bin \
  --qemu /path/to/qemu-system-xtensa \
  --pause-seconds 5 --runtime qemu-wifi --disable-wdt \
  --out-dir /tmp/m5-core2-cas-control
```

Set `M5SW_XTENSA_CONTENDED_CAS_FAIR_YIELD=1` for the candidate lane. Omit
`--disable-wdt` for the normal-WDT control.

## Boundaries

- Only virtual-device validation; physical hardware is `NOT RUN`.
- WDT-off is a diagnostic control, not a supported fix.
- The patch changes only single-threaded TCG RR scheduling after a real
  cross-core failed CAS. It does not alter the CAS result, lock owner or guest
  critical section.
- MTTCG is not a usable substitute in this configuration: QEMU rejects
  `thread=multi` with `-icount`, and removing deterministic icount still
  produced `TG0WDT_SYS_RESET`.
- `RUNTIME-03`, startup UI, setup/REPL, non-empty application frame and stable
  normal-WDT execution remain `OPEN`.
