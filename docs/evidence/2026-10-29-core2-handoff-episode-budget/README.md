# Core2 legacy flash handoff episode budget

Date: `2026-10-29`

Validation category: **virtual-device validation**

Hardware validation: `NOT RUN`

## Result

The BIN-bound `M5SW_XTENSA_PC_TRACE` path previously aborted under
deterministic `-icount` with `Bad icount read`. `0089` ends a matching
translation block with `translator_io_start()` and keeps a defensive
`can_do_io` guard in the helper.

After the fix, two normal-WDT runs reached the existing TG0 reset and measured
the complete flash/cache handoff cycle before reset:

| Phase | Counts | Total durations | Mean | p50 | p95 | Max |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| CPU1 block wait | `12,645 / 12,693` | `9.851852864 / 9.828771008 s` | `779.110 / 774.345 us` | `782.400 / 781.824 us` | `813.312 / 804.704 us` | `6.655552 / 6.781792 ms` |
| can-start to complete | `12,645 / 12,693` | `9.848500512 / 9.825450848 s` | `778.845 / 774.084 us` | `782.144 / 781.568 us` | `813.056 / 804.448 us` | `6.655296 / 6.781536 ms` |
| complete to next block | `12,645 / 12,692` | `5.047361117 / 5.071124609 s` | `399.158 / 399.552 us` | `227.008 / 227.424 us` | `397.184 / 398.432 us` | `589.996 / 589.997 ms` |

The block-wait budget is `57.1% / 57.0%` of the reset-to-WDT interval;
block-wait plus the gap to the next block covers `86.4% / 86.4%`. The largest
single block wait is only about `6.7-6.8 ms`, while each cumulative total is
almost ten seconds. This rejects a single long handshake deadlock and
identifies a high-frequency cumulative operation budget: about
`733-736` completed handoff episodes per virtual second.

The run still reset with `TG0WDT_SYS_RESET`. It did not reach `BOARD NAME`,
`APIKEY`, setup/REPL or a non-empty application frame.

## Pre-fix control

The same PC trace on QEMU built before `0089` reached the trace window and then
terminated with:

```text
qemu-system-xtensa: Bad icount read
```

The control is retained as tooling failure evidence, not as a firmware
classification.

## Evidence identity

- normalized firmware SHA256:
  `18d77e28adfacf7e719a167bd0c3450b78357d13cb1d2f2a8b7bccc2248a909a`;
- fixed QEMU SHA256:
  `7d9b1f43ecc5a9b842c370dd52981ae7eab1c71e996f5dbf26a61bb3b2c0f353`;
- patch SHA256:
  `14326ad71d3c93ee564173387bba6b6efc38b61f24830e363134261e8e2b0dde`;
- runtime: `qemu-wifi`;
- deterministic `-icount shift=5`;
- normal WDT enabled;
- default-off contended-CAS fair-yield candidate enabled only to match the
  current RUNTIME-03 attribution lane.

## Next boundary

The next optimization target is not a lock timeout or WDT extension. It is the
cost and frequency of the normal flash/cache handoff cycle and the guest
startup operations that generate it. Any future change must preserve the
same controller data plane and show fewer operations or lower per-operation
virtual cost under normal WDT.
