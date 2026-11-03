# Emulator performance repair and comparison

Date: `2026-11-03`. Category: **virtual-device validation**. Scoped performance
and the final 19-board/20-case browser regression pass. Overall compatibility
remains **PARTIAL** because the official Factory browser path still faults.
Hardware validation and production deployment are **NOT RUN**.

## Final browser QEMU, original dance image

The final site uses the existing QEMU TCI and the original complete Flash
`c854d3ac6b958439ad30c5277266575d8765f228febf75de243da5d011904542`.
Its exact-image policy selects normal clock divisor 1 and
`tcg,thread=multi,one-insn-per-tb=on`, bound to the audited GPIO patch.
There is no test-only CPU, clock or accelerator override and no added backend.

| Observation | Before | Final cold | Final same-page repeat | Comparison site |
| --- | ---: | ---: | ---: | ---: |
| Run click to application-ready UART | 11.674 s | 3.559 s | 2.746 s | 2.684 s |
| Actual position-change observations / 20 s | 2 | 165 | 163 | 262 |

The remote comparison uses the same BIN but different cache/network conditions.
The old product profile used divisor 6; the repaired exact-image profile uses
normal divisor 1. This is a user-visible product-configuration comparison, not a
fixed-clock CPU benchmark. The repeat reuses immutable bytes and a compiled
module while creating fresh guest memory, Flash, eFuse, Workers and session.
Different engines' position counts use different sampling cadences/units and
are **not servo FPS or a cross-engine speed ratio**.

The two final runs observe 168/166 real controller packets and
30/30 UART cues. Actual rendered joints change
712/701 times, including
637/632 intermediate poses. Raw QOM,
DOM values, captured calibrated targets, firmware and session binding agree.
All observed frame/controller/render gaps remain in the summary; pixel updates
and presentation interpolation do not establish completed application-frame FPS.
The independent eight-second input run records a trusted 509.0 ms press and
the actual guest restart marker 96.80 ms after press, while held.
No earlier post-ready restart marker exists and the whole response window
precedes the 16-second automatic routine boundary. Real QOM input changes 48→0.
This is one observed application response, not a general latency guarantee.
Normal exit, iframe removal and actual engine/pthread target closure pass.

The cold run includes a 1.262 s render-event interval and 1.297 s frame interval
near startup. The warm raw trace has the same early static interval; its render
endpoint falls 2.67 ms before the window and is excluded by the existing
window-only render-gap metric. Matching firmware source explicitly holds the
boot card for 1250 ms and delays the first dance by 1500 ms. Both gaps precede
the first action, with unchanged joints/packet count, consistent with that
intentional static period. The viewer emits render events only when needed.
Screenshots/full snapshots occur after sampling. These facts do not prove
the absence of host-thread stalls; no CPU profile was collected in these runs.
[Startup-gap audit](startup-gap-summary.json) retains all original metrics.
[Independent target derivation](stackchan-final-independent-summary.json)
recomputes the model formula from 398 raw position observations; physical
calibration remains unmeasured.

- [Final same-site dance and touch](browser-final-stackchan-summary.json).
- [Final 19-board / 20-case gate](admitted-browser-summary.json): every admitted
  fixed fixture is rerun; candidate-only Dial is excluded. It does not admit
  arbitrary firmware, other peripherals or the separate Factory sample.
- [Original CoreS3 reference composition](browser-stock-compose-summary.json):
  identical Flash `78961297…bd3f` and original source `7672397e…f3cb` improve
  from 27.577/26.808 s under the former divisor-8 policy to 13.151/11.876 s under
  the exact-image normal-clock policy. The SDK candidate remains a separate
  choice; unknown uploads keep the base profile. Fresh input buffers and guest
  sessions are checked independently from immutable module/asset reuse.
- [R4 browser controls](browser-r4-summary.json) retain the same WASM's official
  StopWatch first-nonblack result, 15.735→5.655/5.083 s, with actual A+B input,
  application markers and all four complete static menu ROIs. They also retain
  the earlier dance/default-CoreS3/Factory observations under their own site
  identities; they are not relabeled as final-site executions.

The fresh runtime has **72 patches**, 160 verified source postimages and a
complete fresh dependency/QEMU build. Independent reverse/forward replay
preserves the original build. WASM SHA-256 is
`0bd9478743d640484cad4762b9d7f7ae57a222f83ebf12a2114eb764a05194ea`,
12,759,914 bytes versus baseline 24,031,527 bytes. Effective C compilation is
O2 and the final link is O3; this is not an all-C-O3 claim. All configured
64 KiB vCPU shadow stacks and guard settings remain unchanged.
[Fresh build and replay](build-r4-summary.json) bind the actual source/commands.
The prior 71-patch [r2 build](build-summary.json) and r2 measurements are
superseded history and do not admit this runtime.

## Correctness fixes and preserved failures

An async predicate in the old Playwright pixel wait could pass a Promise before
its false result resolved. That incomplete five-case gate is invalid and was
abandoned. The replacement explicitly awaits each evaluation, keeps one owned
frame snapshot, and independently validates typed sequence/time and both counter
ROI hashes. Four synthetic-browser controls reproduce the old failure and test
the correction; they are host-only. The final guest gate checks the actual
CoreS3 zero→one pixels, real input and retained RGB565 independently.
[Oracle correction](oracle-correction-summary.json) preserves the failure.

The next gate exposed a Cardputer-ADV presentation failure; host replay
reproduced a retained-frame orientation gap.
The browser presentation callback now repaints the retained actual pixels when
orientation changes, without generating a guest frame or incrementing sequence.
A host before/after negative/positive control and the final real Cardputer case
pass. The final guest's first diagnostic sample is already converged; it does
not directly observe a same-sequence orientation transition. The old run lacked
fresh QOM and two-phase target evidence, which remain NOTCAPTURED rather than
being filled retrospectively. [Orientation repair](orientation-repaint-summary.json).

[Final host checks](host-production-checks-summary.json) are separate from the
real browser/native executions. Raw failures and superseded measurements remain
outside Git; bounded summaries retain their identities and limitations.

## Official Factory boundary

The official Factory full Flash `39910815…97da` remains a browser compatibility
gap. Its original product block policy triggers an interrupt WDT; the withdrawn
single-instruction candidate also encounters a double exception. Faster first
pixels do not establish stability or application readiness. The final normal
product-path Factory control still faults and is retained in the R4 summary.
[Publisher input identity](input-artifacts-summary.json),
[exact-binary diagnosis](factory-panic-diagnosis-summary.json) and
[CSTACK diagnostics](cstack-diagnostics-summary.json) do not claim a matched ELF
or a definitive root cause. Diagnostic opt-in removes host logging work without
suppressing real watchdogs or exceptions.

Two separate native controls run the same Factory Flash for 20 seconds without
panic/reset but remain on Welcome. The recorded between-buttons input proves
ACK only, not navigation. [Native controls](native-factory-control-summary.json),
[source comparison](native-factory-source-summary.json) and
[fresh-state audit](factory-warm-cache-audit-summary.json) retain these limits.

## QEMU JIT assessment

The isolated QEMU TCG WebAssembly host backend changes 16 files (+6,167/-15
lines), adds ten backend files and a forked 64-bit TCI/direct-TLB path. JIT off
does not restore the product interpreter. Four real Factory controls exercise
JIT off/on under single-instruction and default blocks: both off controls hit
watchdogs, both on controls hit exceptions. Actual counters confirm execution;
the distinct causes are retained separately. These controls do not prove JIT
caused every failure and do not establish stable admission. The delivery keeps
one QEMU peripheral implementation and its current TCI, with no JIT integration.

- [Four executed controls](jit-four-lane-summary.json).
- [Integration cost](jit-integration-cost-summary.json).
- [Asyncify and backend review](jit-host-backend-review-summary.json).
- [Opt-in logging host contract](cstack-opt-in-host-contract-summary.json).

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

- [Fresh-build candidate r1](build-candidate-r1-summary.json), [candidate browser observations](candidate-r1-summary.json) and [reset IRQ regression](gpio-reset-summary.json) preserve the superseded candidate and the actual C negative/positive control. They do not admit the final 72-patch runtime.
- [Earlier controls and failures](intermediate-summary.json) retain the preceding slow-clock and zero-motion results.
- [Structured native summary](native-summary.json) binds exact firmware/runtime,
  source hashes, per-run checks and artifact hashes.
- [Final native output-path equivalence](native-final-path-summary.json)
  checks unchanged delivery code and output contracts after registry edits;
  it is source comparison, not a new native guest execution.
- [Native reproduction and boundaries](native-validation.md).
- [Repair plan](../../plans/2026-11-03-emulator-performance.md).
- [QEMU CPU execution decision](../../adr/0001-qemu-browser-hot-block-jit.md).

Raw logs, ZIPs and frame sequences remain outside source Git. The summaries
remove endpoints, credentials, server paths and raw session identifiers. No
firmware or ROM is bundled.
