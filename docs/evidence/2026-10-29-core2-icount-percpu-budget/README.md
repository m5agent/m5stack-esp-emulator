# Core2 per-vCPU icount fairness budget

Date: `2026-10-29`

Validation category: **virtual-device validation**

Hardware validation: `NOT RUN`

## Result

`0090-icount-percpu-fairness-cap.patch` adds a validated per-vCPU
virtual-time cap to multi-vCPU deterministic `-icount` scheduling. The shared
Core2 accelerator configuration now sets the cap to `10000 ns` by default;
`M5_CORE2_ICOUNT_MAX_PERCPU_NS=0` restores the uncapped control.

The same public legacy firmware, normal WDT, `runtime=qemu-wifi`,
`icount shift=5`, QEMU binary and BIN-bound PC list produced:

| CPU1 initiator metric | uncapped | `10 us` cap | Change |
| --- | ---: | ---: | ---: |
| `can_start` to IPC call return, mean | `563.667 us` | `56.249 us` | `-90.0%` |
| peer flash-block wait, mean | `728.443 us` | `184.689 us` | `-74.6%` |
| queued wait to callback enter | `24.620 us` | `24.336 us` | effectively flat |
| callback return to next prepare | `181.869 us` | `34.074 us` | `-81.3%` |

The result identifies the large fixed cost as the single-threaded icount
round-robin budget assigned from the next guest timer deadline. It is not a
Flash command, SPI payload length, WDT mask or interrupt-matrix defect.

## Product-path regression

The final QEMU binary ran all Core2 UIFlow2 device cases with the default
`10000 ns` cap and no retry:

- `core2-peripherals`: PASS;
- `core2-audio`: PASS;
- `core2-mic`: PASS;
- `core2-power-monitor`: PASS;
- `core2-imu`: PASS;
- `core2-axp192`: PASS.

The aggregate result is `6/6 PASS`. A separate default-path
`core2-peripherals` run also passed `1/1`.

The repository platform suite passed `1574` tests with `1` skip after the
snapshot refresh. The focused `qemu_accel`, handoff-PC trace and Device
Service suites also passed.

## Remaining RUNTIME-03 failure

The capped legacy firmware still fails normal startup. A 90-second wall-time
run reached `17.242875841 s` virtual time and triggered `TG0WDT_SYS_RESET`
stage 1 at `7.242815742 s` timeout + ten seconds. Serial contained the
MicroPython banner but no `BOARD NAME`, `APIKEY`, setup or `>>>`; the final
frame remained the 302-byte black PNG.

The short capped trace reached only about `5.39 s` virtual time, so its absent
timeout is not evidence that WDT was fixed. `RUNTIME-03`, startup UI,
REPL/setup, non-empty application frame, physical cache/Flash timing and
hardware remain `OPEN`/`NOT RUN`.

## Reproduction

Uncapped control:

```bash
M5_CORE2_ICOUNT_MAX_PERCPU_NS=0 \
python3 tests/firmware/core2_handoff_trace/run_pc_trace.py \
  --image path/to/normalized-core2.bin \
  --qemu path/to/qemu-system-xtensa \
  --observe-seconds 22 \
  --runtime qemu-wifi \
  --icount-shift 5 \
  --ipc-phases \
  --out-dir /tmp/core2-icount-uncapped
```

Capped/default run:

```bash
python3 tests/firmware/core2_handoff_trace/run_pc_trace.py \
  --image path/to/normalized-core2.bin \
  --qemu path/to/qemu-system-xtensa \
  --observe-seconds 22 \
  --runtime qemu-wifi \
  --icount-shift 5 \
  --ipc-phases \
  --out-dir /tmp/core2-icount-capped
```

## Evidence identity

- normalized firmware SHA256:
  `4d2d648bd8707a1789d540366015a1b90dc816b66a04163048626ea29e333ed4`;
- final QEMU SHA256:
  `568079f3b9e818ef1cc29b9e7cd1c5c036af19196668a12174ed79ec96c262ed`;
- patch SHA256:
  `4c122ab3722c8fa17f9a518c51863f5ff879bd84afb9c78b2ca63516808245e7`;
- PC-trace runner SHA256:
  `bf2e064885ef298345dbbd167df102ac09890766199368d534753d1d7e98c246`;
- uncapped trace stderr SHA256:
  `7192827c8fd9af1834a19f55d0fefaf27d08d85f0546b11311295f29c38bd4be`;
- capped trace stderr SHA256:
  `bca93053084ecbbcea8eb396f3c6d00516714b3ee2658a50db3de57923e5a1bd`;
- black-frame SHA256:
  `57580743a08a3f4ebdf57240cbcc997002ef63b7234531f946127f1495973f43`.

All results are virtual-device validation. The cap changes host vCPU
scheduling granularity only; it does not establish wall-clock equivalence,
physical cache/Flash timing, RF behavior or hardware validation.
