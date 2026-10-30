# QEMU and firmware patch maintenance

The [root guidance](../AGENTS.md) applies. [The patch index](README.md) is the
entry point; each group README defines its exact upstream base and layer order.
Native ESP32, C6, Linux ARM64, firmware SDK and browser-WASM groups are different
source/build lanes. Numeric filenames across groups are not one global order.

## Produce a replayable change

1. Read the official protocol/schematic and the actual guest driver path before
   implementing a peripheral. Identify the controller/bus/DMA/FIFO/endpoint and
   board wiring that must carry the data.
2. Use an isolated source tree at the declared base. Generate a patch from its
   actual diff; exclude unrelated dirty files and instrumentation. Preserve
   controller state, timing and reset semantics outside the intended change.
3. Replay the required layers in their declared order. Verify forward apply and
   `git apply --reverse --check` against the intended source state.
4. Update the owning bootstrap/source lock and provenance where needed. Native
   and WASM patch selections are independent; do not import a mutable native
   list into a pinned browser build or silently reorder context ports.
5. Rebuild the affected target, then run an actual affected guest case. A host C
   replay can prove a source-level negative/positive control, but does not grant
   guest or physical PASS.

The common native Xtensa incremental build is:

```sh
ninja -C .work/M5StopWatch-QEMU/build/qemu/build qemu-system-xtensa
```

This command does not build C6, Linux ARM64 or WASM targets. Follow their own
recipes. For a publishable new WASM runtime, use the isolated source build in
[scripts/qemu-wasm-build](../scripts/qemu-wasm-build/README.md), verify actual
compiled source/build hashes and corresponding-source output, and repeat its
affected browser acceptance. Do not reuse old QEMU objects as a fresh-build
claim; reviewed dependency reuse must be explicit.

## Scope and closure

- Patch presence and successful compilation are not evidence that a device,
  firmware family or physical interface passes.
- Preserve old failing controls and independent test oracles. Do not derive
  expected pixels/register values from the new output under test.
- Register device/model coverage and blockers with the catalog tools; use the
  narrow case/group loop in [tests/AGENTS.md](../tests/AGENTS.md), then the full
  relevant gate for shared runtime or release claims.
- If a closed backend lacks the required controller/injection path, record a
  concrete `partial` blocker rather than adding a host fake data path.
- Commit patch source, pins and concise evidence only; no emulator binaries,
  ROM, firmware, raw traces or source/build snapshots.
