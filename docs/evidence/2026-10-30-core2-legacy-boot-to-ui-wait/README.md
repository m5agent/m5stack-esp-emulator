# 2026-10-30: Core2 legacy boot reaches the WiFi/UI startup thread

Validation category: **virtual-device validation**

Hardware validation: `NOT RUN`

## Result

This control changes only deterministic `-icount` timing and the existing
per-vCPU fairness cap. It does not change guest instructions, watchdog
configuration, the Flash/SSI data plane or any peripheral model.

With the default `shift=5` and a `1 us` fairness cap, the public legacy image
still reaches only the MicroPython banner before the normal-WDT stage-1 reset
window. Lowering the timebase and fairness cap moves the same image much
further:

| Timing control | BOARD/APIKEY | Legacy boot.py | State before normal-WDT stage 1 |
| --- | ---: | ---: | --- |
| `shift=3`, cap `10 us` | `9.840556680/9.841684880 s` | not reached | both CPUs `waiti` at 15 s |
| `shift=3`, cap `1 us` | `8.384395696/8.385523896 s` | `14.191426034-14.380873848 s` | both CPUs active at 15 s |
| `shift=2`, cap `1 us` | `4.659620404/4.660179256 s` | `8.340878020-8.504887849 s` | both CPUs `waiti` at 15 s |

The `shift=2`, cap `1 us` run is the strongest result. It completes the matching
original `/flash/boot.py` marker sequence under a normal, enabled watchdog.
It still produces the same 302-byte black frame and does not reach the factory
startup UI.

## The next wait is not a Flash scan

Two independent WDT-off runs, at 15 and 20 seconds, both stopped at Waiti
`0x4026306e` on CPU0 and CPU1. The 20-second run retained exactly the same
serial hash as the 15-second run, and its last cache-sync activity was at
`9.358926093 s`. SSI/cache counters did not advance after boot.py completed.

An auxiliary FRC timer trace continued to record timer callbacks through at
least `9.277506536 s`. This rejects the simple hypotheses that all guest timers
stopped or that the firmware was still inside an unbounded Flash scan.

## Guest-side blocking stack

An explicit diagnostic UART FIFO injected an interrupt after boot.py. At
virtual time `9.267433433 s`, the guest reported the first thread exception:

```text
Unhandled exception in thread started by <function _thread_task>
  File "wifiWebCfg.py", line 84, in _thread_task
  File "menu/wifi.py", line 22, in __init__
  File "m5stack_ui.py", line 526, in __init__
KeyboardInterrupt:
```

The UART injection is a host-side diagnostic control, not a product path.
It establishes that the startup path after the original boot script reaches
the WiFi configuration/UI thread. The trace already existed before the
injected interrupt; the injection only samples the active Python stack.

The immediate next investigation target is therefore the legacy
`wifiWebCfg/menu/wifi/m5stack_ui` initialization wait, followed by display
flush completion if that path returns. It is no longer accurate to describe
the first current failure as a permanent cache/Flash handoff deadlock.

## Timing controls that do not qualify as fixes

- `shift=2`, cap `10 us` still had no BOARD output through the `5.8 s` freeze;
  TG0 stage 0 timed out at `5.549765707 s`.
- `shift=5`, cap `1 us` still had no BOARD output by 15 seconds; TG0 stage 0
  timed out at `7.242745536 s`.
- `shift=2`, cap `1 us` and `shift=3`, cap `1 us` are useful diagnostic
  controls because they expose the post-boot wait. They are not product fixes
  because neither produces the factory UI or a stable running application.

The existing default (`shift=5`, cap `10 us`) remains unchanged. Its prior
normal-WDT reset boundary was `17.242875841 s`, with no BOARD/APIKEY, REPL or
non-empty frame.

## Evidence identity

- normalized firmware SHA256:
  `4d2d648bd8707a1789d540366015a1b90dc816b66a04163048626ea29e333ed4`;
- final QEMU SHA256:
  `568079f3b9e818ef1cc29b9e7cd1c5c036af19196668a12174ed79ec96c262ed`;
- `shift=2`, cap `1 us`, normal-WDT evidence SHA256:
  `2335c80d9d6bd0c68fb9199456137bc4ba00ea8d3b2cf9358422099f4bf59eeb`;
- `shift=2`, cap `1 us`, WDT-off 20-second evidence SHA256:
  `c7dd1ccdce8fcc08a5ce44a7fe3f344e01d616f7ecc9cee02d0fe198eda5e2ea`;
- `shift=3`, cap `1 us`, normal-WDT evidence SHA256:
  `3431323166046b5a45ecd7ad9edd3496d5b389f98ab7dcf5725299ea213826cd`;
- UART-stack evidence SHA256:
  `b80c94c00453b0f78bb4e94b5fc44eb367c6c55a45ec445fad2afb69683749e9`;
- black-frame SHA256:
  `57580743a08a3f4ebdf57240cbcc997002ef63b7234531f946127f1495973f43`.

## Reproduction

The normal-WDT timing point is reproducible through the existing Device
Service runner:

```bash
M5_CORE2_ICOUNT_MAX_PERCPU_NS=1000 \
PYTHONPATH=platform/tools .work/py312/bin/python \
  tests/firmware/core2_handoff_trace/run_pause_sweep.py \
  --image /path/to/normalized-UIFlow_Core2-v1.15.4.bin \
  --expected-image-sha256 \
    4d2d648bd8707a1789d540366015a1b90dc816b66a04163048626ea29e333ed4 \
  --qemu /path/to/qemu-system-xtensa \
  --pause-seconds 15 --capture-frame --uart-trace \
  --trace-sample 1024 --runtime qemu-wifi --icount-shift 2 \
  --out-dir /tmp/core2-legacy-shift2-cap1
```

The UART-stack trace used a diagnostic host FIFO wrapper around Device Service;
that wrapper is not a repository product path. The raw guest record is bound by
the SHA256 values above and remains outside source Git.

## Boundaries

- Only virtual-device validation; physical hardware is `NOT RUN`.
- The timing controls do not establish hardware clock, cache, PSRAM or RF
  equivalence.
- The UART injection is diagnostic input and does not alter the observed
  pre-interrupt serial sequence.
- `RUNTIME-03`, factory startup UI, REPL/setup and a non-empty application
  frame remain `OPEN`.
