# Core2 classic I2C compatibility regression

2026-10-26: the one-line `0036` candidate repairs the legacy AXP192 case and
passes all six Core2 peripheral regression cases. The frozen Device Service
executable was not replaced during this test.

The exact same AXP192 guest image SHA is used for both sides:
`eae0f22f52e8e43cb9db20b3978a467adaa1bef225271a6d0f66776e2bd6f1e3`.
The five-patch runtime `1880891d…` displays red `OSError(19,)`; the six-patch
candidate `a8fe15db…` displays green PASS with `id=3 st=24 mv=3899 ma=300`.
Both final frames were visually inspected. `summary.json` retains full hashes.

The Unit routing change had added a call to
`m5stopwatch_soft_i2c_set_hardware_active_on_bus()` in the classic controller.
That helper permanently disables bit-banged decoding on the bus. Core2's
M5GFX/Power path returns to software I2C after hardware access, unlike the S3
one-way handoff. `0036` removes only this classic call, retaining connector
selection, controller transactions, chip models and the S3 handoff.

`core2-group/` contains each of the six result/check/frame pairs. These are
repository regression runs, not Device Service Unit acceptance or physical
hardware measurements. Firmware/ROM binaries remain in ignored work storage.
The microphone PCM stays with the original ignored regression evidence; its
source result and assertions are preserved here.

`source-replay.json` verifies all 106 patched source files from the public base,
six forward/reverse patch applications, a restored clean replay checkout, and
the candidate build hash. A fresh official clone was also prepared with the
updated bootstrap and passed `--check`; its exact source receipt is retained.
Fresh bootstrap preparation does not claim a second native build.

No S3, C6, P4, Linux, browser or full-matrix result is inherited from this
candidate's focused Core2 regression. Final service switching and broader
regression evidence are recorded separately.
