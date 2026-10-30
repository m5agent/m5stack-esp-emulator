# Core2 TIMG watchdog feed rescheduling

Date: 2026-10-30

Status: `SEMANTIC_FIX`; `RUNTIME-03` remains `OPEN`.

## Result

`0091-esp32-timg-feed-reschedule.patch` changes the classic ESP32 TIMG
watchdog stage timer from `timer_mod_anticipate_ns()` to `timer_mod_ns()`.
QEMU's anticipate API deliberately keeps an earlier pending deadline.  That is
correct for operations which must not postpone work, but it is wrong after a
successful `WDTFEED`: the feed restarts stage 0 and must replace any pending
later-stage deadline with the newly armed one.

The patch changes only the shared TIMG watchdog stage timer call.  It does not
disable the watchdog, change timeout values, alter interrupt masks, warp the
virtual clock or bypass guest MMIO.

## Validation

- The patch applies forward to the retained QEMU preimage and reverses from
  the rebuilt diagnostic source.
- `test_esp32_timg_wdt_reschedule_patch.py` locks the `timer_mod_ns()` call and
  rejects watchdog-disable, clock-warp and config-changing shortcuts.
- The existing protected-feed contract and Core2 legacy status/CAS contracts
  pass.
- A source rebuild with the patch was exercised through `runtime=qemu-wifi`
  with the public normalized legacy firmware SHA
  `4d2d648bd8707a1789d540366015a1b90dc816b66a04163048626ea29e333ed4`.
  At the `8.0 s` virtual-time snapshot, QEMU produced a live `320x240` frame
  with `3,651` nonblack pixels and `36` colors; frame SHA256 was
  `35aedd447284a3e812e6cd9bec3e3167559a50f2c121eb43482dcfc7ab108fcc`.

The original firmware still reached TG0 stage-1 and emitted
`TG0WDT_SYS_RESET` in the longer control at about `15.56 s`.  Therefore this
record does not claim a completed legacy startup, factory UI, REPL or stable
application frame.  It closes only the watchdog-feed rescheduling semantic
gap; the remaining startup lifecycle block is still tracked by `RUNTIME-03`.

## Reproduction

```bash
patch -p1 --dry-run \
  < patches/qemu-m5stack-peripherals/0091-esp32-timg-feed-reschedule.patch

python3 platform/tests/test_esp32_timg_wdt_reschedule_patch.py
python3 platform/tests/test_esp32_timg_wdt_feed_patch.py
python3 platform/tests/test_core2_legacy_status_cas.py
```

All runtime evidence is virtual-device validation.  Physical watchdog timing,
Core2 cache/PSRAM timing and hardware behavior are `NOT RUN`.
