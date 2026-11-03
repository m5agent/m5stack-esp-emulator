# Emulator performance repair and comparison

Date: `2026-11-03`. This is the design and acceptance record for the user's
startup/responsiveness request and same-firmware comparison. The architecture
retains one QEMU device-model implementation. The delivery candidate uses the
existing TCI. The isolated QEMU TCG WebAssembly JIT assessment did not establish
stable Factory execution and requires a larger execution-layer port.
The [ADR](../adr/0001-qemu-browser-hot-block-jit.md) records the decision boundary.
Current capability and the only execution queue remain
[project status](../project-status.md) and [project backlog](../project-backlog.md).

The revised GPIO-reset source build has exact-firmware dance validation.
The official Factory sample still has intermittent watchdog/double-exception
failures in the browser TCI lane. Its native control remains a separate result.
No host-backend prototype timing or motion count admits a product runtime.

## Implementation scope

Preserve QEMU board/controller wiring, memory and interrupt behavior, the user's
firmware bytes and normal watchdogs. Separate startup costs, actual guest
progress and presentation latency so that a faster transport cannot hide a
slow guest.

The selected CPU/controller changes are audited final-link `-O3`, typed helper
calls with libffi fallback, bounded GPIO transactions and opt-in CSTACK logging.
The logging gate skips diagnostic-only work while retaining real guest faults.
The GPIO
bank path requires the active S3 controller, size-4 writes and one of the twelve
OUT/ENABLE addresses. It selects raw changed-register bits even when the pad
level is unchanged. It keeps full raw register bits and legacy/unknown resolution,
commits all pad revisions before callbacks, preserves IRQ calls, and falls back
for selected legacy listeners or enabled level interrupts. Dynamically registered listeners
and synchronous mutations retain fresh post-callback IRQ reads. Timestamp
batching uses one actual virtual-clock sample for each before/commit phase;
this intentional time contract is tested separately from behavior parity.

The branch registry limits the dance translated-block policy to complete Flash
SHA-256 `c854d3ac6b958439ad30c5277266575d8765f228febf75de243da5d011904542`:

- Profile `stackchan-wasm-dance-wallclock`, clock divisor `1`, and
  `oneInsnPerTb: true` produce the sole accelerator argument
  `tcg,thread=multi,one-insn-per-tb=on` without `-icount` or a CPU-count override.
- `requiredRuntimePatch` binds
  `patches/qemu-wasm-probe/0027-gpio-bounded-transactions.patch` to SHA-256
  `43685da86d9b959b2e769cd9cda5785a5c4039b5076f73f3b9d6033d1d161bdf`.
  Host and engine checks reject older/mismatched runtime manifests.
- The complete firmware SHA, ready marker and variant remain bound together.
  Unknown hashes keep the original profile. A diagnostic clock override clears
  the variant, single-instruction flag and required patch; it cannot inherit
  the admitted execution setting. No cross-CI WASM hash is hardcoded.

The exact publisher StopWatch Flash has a separate provenance-bound row and
normal-clock single-instruction policy. Its null ready marker does not invent
an application-ready event. The Factory-specific row was withdrawn after its
intermittent faults; its diagnostic results do not admit a product variant.

Startup work includes native SHA-256, parallel runtime/ROM fetching and module
compilation, bounded verified memory/CacheStorage asset caches, and a bounded
compiled `WebAssembly.Module` cache. Bind reuse to SHA and byte length, revalidate
persisted bytes, retain buffer ownership across transfers, and instantiate fresh
memory/Flash/eFuse and workers for every run. User firmware and mutable Flash are
not asset-cache data.

Browser shared-frame polling runs independently of QMP output/orientation
requests. Native-service frame and SCS-output polling run independently of
serial/status traffic. Each lane is bounded to one in-flight request and keeps
owner, generation, stop and cancellation fences. The native bridge displays
validated raw QOM positions through the existing model interpolation; it never
creates guest position values. Automatic mode prefers a compatible connected
native service; explicit browser mode remains isolated browser execution.

## Acceptance and evidence

Use the same complete Flash SHA, device/profile, host, browser/GPU and real inputs
for before, after and the comparison runtime. Run measurements serially without
concurrent builds or guests. Identify verified hardware GPU rendering and keep
cold/warm cache states explicit.

For the exact fresh runtime, retain serial/application-ready markers, first
nonblack framebuffer, changed-pixel observations and intervals, raw SCS
position/packet progression, genuine controller input/readback, actual rendered
joint angles and intermediate poses, and normal Worker disappearance. Record
the factory's actual arguments and runtime source/asset hashes. Verify the real
WASM stack guards, including the configured small vCPU stacks. Source-level
array accounting and host C execution are not a stack-safety PASS.

Changed framebuffer snapshots measure pixel updates, not completed application
frames or physical display FPS. Interpolated 3D motion alone does not prove
guest speed. Compare position-change counts within each lane; raw tick values
and another engine's degree values are different units. Keep remaining visual
fidelity and input/model limitations explicit.

Native-service tests use a dedicated authenticated service, evidence ZIPs before
stop, and retained session history. Browser tests use isolated static exports,
browser-local session identities and actual iframe/engine/pthread cleanup before
context closure. Native PASS cannot be spliced into browser acceptance. A shared
runtime change also needs the affected existing admitted-board regression scope.

## Retained diagnostics and handoff

Preserve the original browser failures, slow-clock controls, JIT/TCI and GPIO
prototype comparisons, withdrawn RR/esp32sim experiments, harness failures and
their exact identities. They explain the investigation; they do not establish
the fresh runtime's PASS or coverage of another firmware/device.

Keep raw traces, ZIPs, frames and source/build snapshots in ignored evidence
storage. Publish only reviewed bounded summaries with exact hashes, configuration,
reproduction and cleanup. Do not bundle firmware/ROM or expose credentials,
endpoints, server paths or raw session/device identifiers. Update authority
documents and archive the final reproducible result only after its real guest
gate; use the [recorded evidence](../evidence/2026-11-03-emulator-performance/README.md)
for separately completed native validation and its limits.
