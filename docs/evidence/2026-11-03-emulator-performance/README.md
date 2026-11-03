# Emulator performance repair and comparison

Date: `2026-11-03`. Validation category: **virtual-device validation**.

Overall status is **PARTIAL** pending the 72-patch final-runtime controls and
all-admitted-board gate. The prior r2 exact-image browser startup/motion and
native service delivery are independently validated; neither establishes
physical timing. The new build does not inherit r2's measurements.

## Browser QEMU, original dance image

The validated r2 runtime retains QEMU TCI, without an additional JIT/backend. The exact
16 MiB Flash SHA is `c854d3ac6b958439ad30c5277266575d8765f228febf75de243da5d011904542`.
The production registry selects normal clock and QEMU's existing
`tcg,thread=multi,one-insn-per-tb=on`, bound to the exact GPIO patch identity.
No test-only CPU, accelerator or clock override is used.

| Observation | Before | r2 first run | r2 same-page repeat | Comparison site |
| --- | ---: | ---: | ---: | ---: |
| Run click to application ready | 11.674 s | 3.289 s | 2.497 s | 2.684 s |
| Position-change observations / 20 s | 2 | 166 | 158 | 262 |

Startup includes local firmware/runtime preparation and boot. The comparison
site is remote; cache/network conditions are recorded rather than assumed
identical. The before/after product configurations include changing the dance
clock divisor from 6 to the normal 1; this is not a fixed-clock CPU benchmark.
The repeat verifies compiled-module and immutable-resource reuse,
with fresh guest state. Position observations have different sampling cadences
between engines and are **not servo FPS or a cross-engine speed ratio**.

The two r2 runs observe 173/164 new real controller packets and 30/30 UART
dance cues. Actual viewer renders contain 719/683 changing joint angles and
643/613 intermediate poses; raw QOM positions, DOM, calibrated targets, session
and firmware binding agree. Pixel changes are about 26.35/26.45 per second,
including guest drawing in progress, not completed application-frame FPS.
Both runs pass normal shutdown and actual Worker disappearance before closing
their browser contexts. An independent eight-second input run records a trusted
508 ms front-surface press and the guest's routine-restart UART marker 75.685 ms
after press, while still held. No earlier post-ready restart marker exists and
the entire response window precedes the 16-second automatic routine boundary.
QOM input changes 48→0 and cleanup passes. This is one observed application
response, not a general short-press latency guarantee. All-board acceptance is
recorded separately.

The r2 full source build and all dependencies are fresh. Its WASM is
`437c854e359386febfe56a90532aae41a261f1e4da32a516c928dc2b9ca6e7a7`
(12,760,672 bytes), down from the baseline's 24,031,527 bytes.
The [build summary](build-summary.json) binds all 71 patches, 160 source
postimages, effective O3/stack settings and corresponding source.

## Vendor-firmware boundary under investigation

The official Factory image is a separate firmware path. Its original block
policy still triggers an interrupt WDT. The exact-image one-instruction policy
reduces first nonblack display time, but a second fresh VM reaches an unhandled
double exception. It is **not a stability PASS**. The relevant input binaries
and FF-padding relation are explicit in [input artifacts](input-artifacts-summary.json);
`sourceKind: published-firmware-binary` never claims matching source code or
an application-ready marker.

Two native QEMU controls run the same Factory Flash for 20 seconds without
panic/reset. Both retain the Welcome screen; the recorded input lands between
buttons and proves ACK only. [Native controls](native-factory-control-summary.json),
[actual source comparison](native-factory-source-summary.json) and
[fresh-VM/cache audit](factory-warm-cache-audit-summary.json) preserve their limits.
The [exact-binary panic diagnosis](factory-panic-diagnosis-summary.json) identifies
the final double-exception stub without guessing symbols from an unmatched ELF.
The original [CSTACK log audit](cstack-diagnostics-summary.json) proves additional
host work but does not establish the fault's cause. Instrumented runs remain
diagnostics, with their own source/runtime identity, rather than release tests.

## QEMU JIT assessment

The isolated QEMU TCG WebAssembly host backend adds 16 changed files
(+6,167/-15 lines) and a forked 64-bit TCI. Disabling its JIT does not restore
the existing product interpreter. It therefore requires broader execution-layer
validation, beyond reusing the same SoC/peripheral source.

Four actual Factory controls compare JIT off/on under both single-instruction
and default multi-instruction blocks. Actual counters confirm execution;
both off controls trigger a watchdog and both on controls reach exceptions.
The distinct exception causes remain separate. These results do not identify
every fault's root cause and do not justify product admission. The current
delivery retains the original TCI; the unstable Factory-specific fast profile
is withdrawn.

- [Four executed controls](jit-four-lane-summary.json).
- [Integration cost and unchanged native boundary](jit-integration-cost-summary.json).
- [Asyncify and host-backend review](jit-host-backend-review-summary.json).
- [CSTACK opt-in host controls](cstack-opt-in-host-contract-summary.json).

## Native public workbench

Four sequential guest executions use identical firmware and native QEMU within
each pair. The controller module alone selects before/after delivery behavior;
the current workbench also connects actual SCS state to the 3D model.

| Device | Before | After | Meaning |
| --- | ---: | ---: | --- |
| StackChan | 1.25/s | 27.17/s | Applied changed PNG updates, 12-second window |
| CoreS3 | 1.42/s | 8.42/s | Applied changed PNG updates, 12-second window |

All 46 scoped checks pass. Automatic mode selected the native service while a
browser profile was also available. No browser QEMU binary was requested. The
same StackChan guest supplied 70 changed SCS observations, raw DOM values and
366 rendered intermediate poses; requested target positions never substitute
for observed positions. CoreS3 actual touch reaches the guest callback.

Evidence ZIPs were requested before stop, all included file hashes were checked,
and stopped sessions retain metadata and frames. Every guest, browser and
agent-owned service was reaped.

Startup improvement was **NOT RUN** as a native before/after claim: Flash cache
warmth differs between the first and second runs. Full atomic application-frame
fidelity is **REVIEW**; snapshots can capture guest drawing in progress.

- [Fresh-build candidate r1](build-candidate-r1-summary.json), [candidate browser observations](candidate-r1-summary.json) and [reset IRQ regression](gpio-reset-summary.json) preserve the superseded candidate and the actual C negative/positive control. They do not admit the final r2 runtime.
- [Earlier controls and failures](intermediate-summary.json) retain the preceding slow-clock and zero-motion results.
- [Structured native summary](native-summary.json) binds exact firmware/runtime,
  source hashes, per-run checks and artifact hashes.
- [Final native output-path equivalence](native-shared-path-final-summary.json)
  checks unchanged delivery code and output contracts after registry edits;
  it is source comparison, not a new native guest execution.
- [Native reproduction and boundaries](native-validation.md).
- [Repair plan](../../plans/2026-11-03-emulator-performance.md).
- [QEMU CPU execution decision](../../adr/0001-qemu-browser-hot-block-jit.md).

Raw logs, ZIPs and frame sequences remain outside source Git. The summaries
remove endpoints, credentials, server paths and raw session identifiers. No
firmware or ROM is bundled.
