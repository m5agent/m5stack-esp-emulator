# Core2 flash/cache handoff trace

`M5SW_ESP32_HANDOFF_TRACE=1` enables a default-off diagnostic stream spanning:

- cross-core interrupt level writes;
- ESP32 DPORT APPCPU, cache-control and cache-sync events;
- TIMG watchdog config/feed/arm/timeout events;
- ESP32 UART interrupt enable/clear/status transitions;
- ESP32 SPI transaction and receive-data phases.

Each line records QEMU virtual time, current CPU, guest PC and four
component-specific values. `M5SW_ESP32_HANDOFF_TRACE_SAMPLE=N` samples routine
events; WDT timeout, interrupt and reset events are always emitted.

`M5SW_ESP32_HANDOFF_PC_SAMPLE_NS=1000000` additionally records both guest PCs
every virtual millisecond. The PC sampler is off by default because
high-frequency sampling perturbs scheduling; use it as a separate diagnostic
control.

Run the same flash image with:

```bash
M5SW_ESP32_HANDOFF_TRACE=1 \
M5SW_ESP32_HANDOFF_TRACE_SAMPLE=1024 \
timeout 90 qemu-system-xtensa \
  -snapshot -machine m5core2 ...

M5SW_DISABLE_WDT=1 \
M5SW_ESP32_HANDOFF_TRACE=1 \
M5SW_ESP32_HANDOFF_TRACE_SAMPLE=1024 \
timeout 120 qemu-system-xtensa \
  -snapshot -machine m5core2 ...

M5SW_ESP32_HANDOFF_TRACE=1 \
M5SW_ESP32_HANDOFF_TRACE_SAMPLE=1024 \
M5SW_ESP32_HANDOFF_PC_SAMPLE_NS=1000000 \
timeout 30 qemu-system-xtensa \
  -snapshot -machine m5core2 ...
```

Use `-no-reboot` for the normal-WDT run so the first system reset terminates
the process and preserves the pre-reset trace.

Summarize retained logs with:

```bash
python3 tests/firmware/core2_handoff_trace/summarize.py \
  --normal-stderr normal.stderr \
  --normal-serial normal.log \
  --wdt-off-stderr wdt-off.stderr \
  --wdt-off-serial wdt-off.log \
  --trace-off-serial trace-off.log \
  --pc-stderr pc-sample.stderr \
  --pc-serial pc-sample.log \
  --image normalized-flash.bin \
  --qemu qemu-system-xtensa \
  --patch patches/qemu-m5stack-peripherals/0037-esp32-handoff-trace.patch \
  --pc-symbolization \
  tests/firmware/core2_handoff_trace/pc-symbolization-2026-10-26-core2-handoff.json \
  --firmware-name UIFlow_Core2 \
  --firmware-source-sha256 <public-source-sha256> \
  --normal-sample 1024 \
  --wdt-off-sample 1024 \
  --normal-wall-timeout 90 \
  --wdt-off-wall-timeout 120 \
  --pc-sample-ns 1000000 \
  --core2-summary /tmp/core2-summary.json \
  --full-matrix-summary /tmp/full-matrix-summary.json \
  --platform-tests-passed 504 \
  --docs-contract-tests-passed 41 \
  --qemu-profile-tests-passed 19 \
  --out summary.json
```

The ELF-derived PC mapping is stored separately from raw trace output so a
summarizer rerun does not discard it. It remains explicitly unbound from the
public BIN unless the ELF and image provenance are proven byte-identical.

The trace is diagnostic only. It does not prove physical cache timing or close
`RUNTIME-03`.
