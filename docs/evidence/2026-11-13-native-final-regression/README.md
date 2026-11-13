# Fresh native runtime high-load regression

Date: `2026-11-13`. Validation: `virtual-device validation`.

Both complete rounds passed: **69/69 + 69/69**, with one attempt per case and
no retries. Each round used three fixed scopes of 23 cases. All 1,269 recorded
one-minute host-load samples during actual case execution were at least 10.

| Round | Cases | Samples | Minimum load | Maximum load | Median load |
| --- | --- | --- | --- | --- | --- |
| 1 | 69 PASS | 636 | 11.1304 | 16.9243 | 12.4849 |
| 2 | 69 PASS | 633 | 10.3735 | 14.6060 | 12.3833 |

The executed source commit was `890acf8fd4f51af400cdfa96100d5dcac7903338`.
Later evidence/documentation commits do not change the frozen execution files.
The fresh runtime identities are:

- Xtensa, 146 patches: `35c35ef2427e121dcd232215339c5219b7e22bc6c63821c92e356c9573d42b26`.
- C6, 19 patches: `3679e74e893670a5fd665345addcf00e0e49b9f708c6d4093960f8dc228b0db4`.

[The bounded summary](summary.json) binds the runtime/ROM hashes, reference
images, source pins, full sample-series hash, supervisor policy and six scope
summaries. Each scope records the composed firmware, actual guest oracles,
serial/frame/composition hashes, exit status and per-case load observations.
Warmup observations do not substitute for actual case samples. Bounded
low-priority compute support is recorded separately from the actual guests.

All owned processes and QMP sockets were cleared; final source, firmware and
runtime pins matched their initial values. The platform suite passed 2,139 of
2,147 tests; seven optional source-checkout controls and one optional pinned
compiler reproduction were skipped because those local dependencies were
unavailable. All 33 Node contract commands and the coverage/catalog/profile/
snapshot validators passed. These host checks are separate from guest results.

This closes the two-round regression requirement for #192, including the
StackChan/Core2 readiness paths and the added Core2 SD case. Earlier executions
with failures or insufficient load coverage remain in their historical records.
This result does not itself establish main publication, resident deployment,
arbitrary application approval, browser-WASM behavior or physical properties.

Original-firmware acceptance remains separately bound to its runtime:
[Xtensa applications](../../../tests/firmware/classic_factory/final-0194-0198-summary.json)
and [C6 applications and clock controls](../../../tests/firmware/esp32c6_mwdt_clock/final-runtime-summary.json).
The RFID reboot, unsupported P4 paths and other application limits are not
overridden by the peripheral matrix. No Burner submission was made.
