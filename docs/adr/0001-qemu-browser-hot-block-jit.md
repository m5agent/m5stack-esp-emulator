# ADR-0001: Retain one QEMU runtime

## Status

Architecture decision accepted, `2026-11-03`: retain the existing QEMU TCI
browser execution layer. The internal QEMU JIT candidate is not admitted.
Its four isolated Factory controls all encountered a guest fault; final
delivery-runtime acceptance remains a separate gate.

The filename is retained for existing links. No second SoC backend is added.

## Context

The user requested faster startup and more continuous execution while keeping
QEMU as the project's core. Native QEMU uses TCG translation; the browser build
uses TCI to interpret translated operations. Downloading, hashing, compiling
WASM, guest CPU/controller work and UI delivery are separate costs.

Two diagnostic alternatives were evaluated: an independent esp32sim SoC model
and a WebAssembly TCG JIT inside QEMU. The former would add a second device-model
and admission stack. The latter changes 16 files (+6,167/-15 lines), adds ten
host-backend files, and uses a forked 64-bit TCI plus a direct TLB RAM path.
Turning its JIT off does not restore the product's 32-bit TCI. It also bypasses
the product's typed-helper adapter, so adoption is an execution-layer port
with CPU, helper ABI, MMU, invalidation, exception and Asyncify obligations.

Actual generated-Wasm ctpop and shared-memory growth controls caught and
corrected defects before firmware execution. Same-candidate JIT-off/JIT-on
controls then ran the identical official Factory Flash at clock divisor 1,
with both single-instruction and default multi-instruction blocks. Actual
getter/counter observations confirmed the selected execution path. Both JIT-off
controls triggered a watchdog; both JIT-on controls encountered exceptions.
The original exception causes differ and are retained separately. This does
not prove every fault was caused by JIT, but establishes no stable acceptance
result for adopting this candidate.

## Decision

Deliver the existing single QEMU browser runtime with **TCI**. Do not integrate
the experimental JIT, its CPU selection API or counter polling, the alternate
esp32sim backend, or the single-thread wall-clock scheduling experiment.
Preserve their source snapshots and execution results as diagnostic history.

Retain the existing board, memory, controller, DMA/FIFO, interrupt and firmware
paths. The selected changes are:

- Explicit final-link `-O3`, audited from effective commands, and typed helper
  calls with the existing libffi fallback for unsupported signatures.
- Bounded GPIO transactions: remove unused private timestamp work, reuse stable
  data within one transaction, and restrict eligible OUT/ENABLE bank writes to
  the raw changed-register mask. The bank path requires the active S3 controller,
  size-4 writes and one of the twelve supported addresses. Keep unknown/legacy
  resolution, full register storage, IRQ calls, all-revisions-before-callback
  ordering and callback-aware fallbacks. Public capture/notify phases each use
  a real virtual-clock sample.
- Native SHA-256, parallel loading of verified immutable runtime/ROM assets,
  bounded verified asset caches and compiled-WASM reuse. Each run still creates
  fresh guest memory, Flash, eFuse, engine and pthreads. Cached code is not a
  saved guest session; corrupted assets never become an unverified fallback.
- Independent, bounded frame, output and orientation polling. Preserve private
  ports, owner/generation fences, cancellation and normal-exit verification.
- Independent native-service frame/output delivery, with actual StackChan QOM
  observations feeding the existing 3D bridge. Automatic mode prefers a
  connected compatible native service; explicit browser mode remains browser.
- Opt-in CSTACK diagnostics: with tracing unset, skip diagnostic-only stack,
  heap, ID and logging work. Exact `M5_WASM_CSTACK_TRACE=1` retains the original
  trace contract. This does not suppress a guest watchdog or exception.

The complete dance Flash SHA-256
`c854d3ac6b958439ad30c5277266575d8765f228febf75de243da5d011904542`
selects the StackChan dance variant's `oneInsnPerTb: true` and normal clock
divisor `1`. Its unique accelerator argument is
`tcg,thread=multi,one-insn-per-tb=on`, without `-icount` or a CPU-count override.
The independently tested StopWatch publisher image
`d231d8523c8b448e8b920777d298c575989dbafc57fc3f432851bcaeb61b1898`
also selects this normal-clock policy. Its provenance identifies the original
published BIN, and its null ready marker does not claim application readiness.
The unstable Factory variant is withdrawn. Unknown hashes keep their existing
execution configuration.

This variant requires
`patches/qemu-wasm-probe/0027-gpio-bounded-transactions.patch`, SHA-256
`43685da86d9b959b2e769cd9cda5785a5c4039b5076f73f3b9d6033d1d161bdf`.
Both the public runtime and engine validate that source-patch identity against
the runtime manifest. Bind it to the complete firmware SHA and its provenance;
do not pin a WASM hash that may differ across fresh CI builds. A clock override
clears the admitted variant, single-instruction flag and patch requirement.

## Consequences and validation boundary

One QEMU peripheral implementation remains the maintenance target. Firmware
bytes, normal watchdog behavior and the controller data plane remain part of
acceptance. No requested servo target or input echo may replace an actual
controller observation.

Single-instruction blocks trade additional dispatch for shorter translated
blocks. This is a measured, exact-firmware policy, not a universal default or a
claim about physical timing. GPIO phase timestamps are an intentional contract
refinement; host C tests check it separately from fixed-clock behavior parity.

Host contracts, source provenance and a successful build are separate from
guest validation. Prototype results cannot admit the fresh runtime. Its final
browser gate must bind the exact runtime/firmware/configuration to serial,
framebuffer, real input, raw SCS state, actual rendered joints, stack guards and
Worker cleanup. Native-service results remain a separate validation lane.

## References

- [Performance repair plan](../plans/2026-11-03-emulator-performance.md)
- [Source build and provenance](../../scripts/qemu-wasm-build/README.md)
- [GPIO transaction patch](../../patches/qemu-wasm-probe/0027-gpio-bounded-transactions.patch)
- [Firmware execution profiles](../../platform/web/qemu-browser-profiles.json)
- [Recorded performance evidence](../evidence/2026-11-03-emulator-performance/README.md)
- [JIT host-backend review](../evidence/2026-11-03-emulator-performance/jit-host-backend-review-summary.json)
- [JIT integration cost](../evidence/2026-11-03-emulator-performance/jit-integration-cost-summary.json)
- [Four executed JIT controls](../evidence/2026-11-03-emulator-performance/jit-four-lane-summary.json)
- [Current status](../project-status.md) and [remaining work](../project-backlog.md)
