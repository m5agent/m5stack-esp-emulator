# Latest UIFlow2 regression repairs

Date: 2026-11-05. Native results are **virtual-device validation**. Physical
hardware and browser-WASM validation are NOT RUN. Host checks are recorded separately; CI and delivery use the permanent work
record. This page does not close all issue reports.

The repairs distinguish image/observer defects from actual controller behavior.
Actual partition tables drive VFS composition, stock files and all non-VFS bytes
are preserved, classic/S3 eFuse fields are bounded, and expected driver differences
are bound to exact firmware hashes. Real UART0 observation exposes the original
PaperColor, Dial and AtomS3 Lite programs. Synthetic ADC calibration remains an
explicit application-byte-bound virtual fixture, with unchanged numeric oracles.

## Native controllers and inputs

AXP2101 reports charger/current direction fields. ED2208 accepts inclusive 0x83
windows and 0x17 A5/A7 AUTO refresh while preserving the legacy protocol. AtomS3
has an explicit `m5atoms3-st7735` LCD profile; original `m5atoms3` GC9107 is
preserved. Latest/previous official controls use the frozen fresh native runtime.

Basic's earlier standalone A/B/C PASS is retained. The first frozen device matrix
reproduced a missing B after A redraw: 17 PASS / 1 FAIL. A real guest redraw fence
now separates inputs while keeping the 450 ms pulse; measured ACK intervals are
0.456461/0.453950/0.451503 s. The independent fenced case and a new full device run
pass (18/18). This is a fixture synchronization repair, not a changed button model.

The first full peripheral run remains 67 PASS / 1 FAIL: Core2 Mic had a successful
guest result but its sampled (4,4) frame pixel was black. A separate draw-fenced
followup observes nonzero PCM, both result/draw markers and the unchanged green
pixel assertion. It does not rewrite the original 68-case run into a full PASS.
The existing Unit Buzzer default timer-zero failure is separate and remains open.

## Tab5 and storage boundaries

The Tab5 double VFS injection corrupted latest application bytes; composition
now preserves the entire app, rejects stale ELF symbols and gives esp-emu an owned
virtual eFuse copy. The first shared virtual seed save-back lacked a before hash;
its earlier byte preservation is not claimed. Later copy checks preserve source
hash and mtime. The independent 0.51 followup observes an actual DSI PHY lock wait before
MicroPython creation; timers advance. [Actual BIN/MMIO evidence](tab5-phy-followup-summary.json)
uses no old ELF symbols or ready-bit bypass. Latest official Python/UI/touch still lacks readiness evidence;
old merged-image UI/touch/RS-485 PASS is a separate control. **#188 remains open.**

The engineering-storage cleanup removed only verified regenerable cache/objects
and deduplicated byte-identical immutable blobs after write-policy checks. The
allocated/du total is 46,361,821,184 B (43.177811 GiB); current runtime, firmware,
ELF, source, sessions, metadata and valid evidence were retained. Additional
same-inode/hash and metadata readback is included; a hash-mismatched candidate was
left untouched. Concurrent `df` changes are reported separately.

## Bounded evidence and reproduction

- [Summary and identities](summary.json): issue dispositions, runtime hashes,
  storage accounting, boundaries and final pending gates.
- [Matrix and Flash transport](matrix-transport-summary.json): original failures,
  exact-firmware expectations, stock esptool guest-stub and complete Flash readback.
- [Runtime provenance and ADC](service-adc-summary.json): replay/build boundaries,
  executed-runtime identity, calibration values and retained Buzzer failure.
- [S3 startup and Tab5](startup-tab5-summary.json): original programs, UART/EPD
  observations, unchanged latest Tab5 app, old-image controls and seed boundary.
- [Fresh native integration](root-integration-summary.json): initial/final device
  matrices, previous firmware
  controls, exact base/derived-image/serial/frame hashes and measured Basic input.
- [Fresh native peripherals](root-peripheral-summary.json): the complete first
  67 PASS / 1 FAIL run (part 1), with [part 2 and independent Mic followup](root-peripheral-more-summary.json), separately bound
  to actual firmware/runtime/ROM and data-plane/frame checks.

Use checked-in `tests/uiflow2/run_device_matrix.py`, `run_peripheral_matrix.py`
and Unit host runners at the final published source commit with these exact
firmware/runtime identities. Root summaries bind raw evidence by SHA rather than
publishing host paths or mutable Flash. Final local platform suite passes 2,020 tests with one skip; Unit has 303 passes
and one skip, and all 30 Node scripts pass. [Host gate summary](host-gates-summary.json)
retains earlier failures. CI, source/record permalinks and delivery use the work record.

Additional bounded followups: [native dependency freeze audit](native-freeze-audit-summary.json)
and [final generated-build/cache cleanup](storage-followup-summary.json).

[Linux CI portability followup](ci-followup-summary.json) retains the first failed
checks and verifies native executable lookup without probing the wrong host OS.
