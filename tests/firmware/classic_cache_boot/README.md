# Classic cache handoff and original UIFlow boot

This fixture separates a classic ESP32 cache-model performance defect from
the independent SPI hardware-CS routing defect. It uses the unchanged Core2
UIFlow 1.15.5 merged image, SHA-256
`3b389eea45b2c1a45b65c29e6de969635e19c486cd5876a048724d6c551f7d1b`.
Firmware and raw service evidence are not checked in.

The original driver reads Flash into PSRAM in 32-byte chunks. Each chunk
coordinates both cores and disables/restores caches. In the old model, a clean
cache enable unconditionally notified a full 4 MiB ROM-region flush, although
no mapped bytes had changed. Each cache-control write also rebuilt the address
space separately for DROM, IROM and PSRAM. Patch 0193 emits the ROM notification
only after dirty MMU pages are processed and batches the three memory-region
changes before the cache-ready IRQ. Explicit cache flush, changed MMU entries,
illegal-access handling, Flash decryption selection and shared PSRAM aliases
retain their existing semantics.

`summary.json` preserves three separate 330-second Device Service observations.
The first `BOARD NAME: M5STACK-CORE2` marker occurred at 220, 175 and 70 seconds
for the baseline, dirty-notification-only candidate and complete 0193 candidate.
These are single-run host wall times, sampled every five seconds, not hardware
timing or a controlled performance benchmark. All three runs still had black
frames: their SPI panel model did not route hardware CS to the panel. The
serial marker is initialization progress, **not application readiness**.

A separate 180-second control adds the reviewed hardware-CS preview to complete
0193. The same BIN then shows the UIFlow logo at 30 seconds and the original
Core2 V1.15.5 Wi-Fi Config screen at 120 seconds, stable through 180 seconds.
There is one boot and no watchdog/Guru marker. The preview patch and actual
compiled runtime have separate hashes in the summary. This validates the local
configuration screen; it is not the final full-0192 runtime, configured Internet
access, a cloud pairing result, or proof of every UI interaction.

Read-only LittleFS inspection of the original BIN found a valid filesystem
with 35 files. Actual SPI Flash reads during initialization map to the original
705,644-byte `/res/ding.wav` and UI resources. The audio/file was neither
shortened nor replaced. No firmware instruction, watchdog, delay or scheduler
quantum was changed.

## Reproduction

Use Python 3.12+, a local dedicated Device Service configured with the native
Xtensa runtime under test, and the exact original BIN. Supply the compiled
executable behind any diagnostic wrapper. Use an agent-owned port and state
directory. Raw output contains firmware-generated identifiers; keep it in
ignored storage and redact any public summary.

```sh
python3 tests/firmware/classic_cache_boot/run_original.py \
  --service "$DEVICE_SERVICE_URL" --token-file "$TOKEN_FILE" \
  --firmware "$ORIGINAL_BIN" --runtime-binary "$QEMU_BINARY" \
  --out-dir .work/core2-cache-reproduction --seconds 330
```

The runner uploads the untouched artifact, requests the `qemu-wifi` lane with
the real network controller and no HTTP fixture, samples serial/frame output,
requests the ZIP before stopping, and uses `purge=0` without retaining mutable
Flash. It records observation, not an automatic UI PASS. Inspect the frames and
serial together. The diagnostic runs also used a separate HMP monitor to read
CPU/SPI/GPIO registers and briefly enable the existing Flash transaction trace;
those observations did not write guest memory or peripherals.

The host regression replays the complete native prefix against the pinned
upstream DPORT source and runs its extracted C functions with ASan/UBSan. It
retains the old redundant-work negative control and checks MMU remapping,
explicit cache flush with changed backing bytes, invalid mappings, decryption
branch selection and PSRAM writes surviving cache gates. Its memory shims do
not establish hardware cache/writeback timing or cryptographic correctness.

```sh
PYTHONPATH=platform/tools:platform/tests python3 -m unittest \
  test_classic_cache_dirty_sync_patch test_core2_wifi_irq_cache_gate_patch \
  test_core2_psram_himem_runner test_xtensa_high_priority_irq_cooperative \
  test_xtensa_inactive_irq_yield_guard_patch
```

The integrated native peripheral matrix and full platform suite belong to the
final combined-runtime gate. Browser-WASM, physical hardware, cloud pairing
and publication to Burner are NOT RUN by this fixture.
