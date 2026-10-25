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

The initial ELF-derived PC mapping is stored separately from raw trace output.
A later same-VMA audit rejected it: the public `UIFlow_Core2 v1.15.4` BIN and
local `UIFlow2 v2.5.3` ELF differ at all three CPU0 sample addresses. The
rejected names remain in metadata only to document the correction; current
analysis must not reuse them.

Run the binding audit with:

```bash
python3 tests/firmware/core2_handoff_trace/audit_elf_bin_mapping.py \
  --image normalized-flash.bin \
  --image-label normalized-UIFlow_Core2-v1.15.4.bin \
  --elf .work/uiflow2-core2-symbols/micropython.elf \
  --elf-label UIFlow2-v2.5.3-Core2-micropython.elf \
  --app-offset 0x10000 \
  --address 0x400843ac \
  --address 0x400843af \
  --address 0x400843b1 \
  --window 16 \
  --out pc-mapping-audit.json
```

`BIN_ELF_BYTES_MATCH` is required before using an ELF symbol as evidence for a
PC sampled from a different image.

`0037` is predecessor-bound: it applies after `0036` on the retained
M5StopWatch-QEMU-derived tree. It is not a standalone patch against raw
upstream QEMU or the unpatched `da100c9` source commit. The recorded apply
check reverses `0037` from that predecessor tree, then verifies forward apply
and reverse apply again.

`0038-esp32-handoff-pause.patch` adds an exact-virtual-time freeze control:

```bash
M5SW_ESP32_HANDOFF_TRACE=1 \
M5SW_ESP32_HANDOFF_TRACE_SAMPLE=1024 \
M5SW_ESP32_HANDOFF_PAUSE_NS=15300000000 \
qemu-system-xtensa -snapshot -machine m5core2 ...
```

At the target timestamp QEMU emits a `component=cpu event=pause` line and
raises `SIGSTOP`. A debugger can then inspect both vCPUs without the scheduling
disturbance of `M5SW_ESP32_HANDOFF_PC_SAMPLE_NS`. The paired controls freeze
near the final feed and inside the feed-to-timeout gap. They show that the
earlier fixed UART/VM PC cluster was sampling-dependent and that the late
window converges on a Flash/cache-handshake source pattern.

`0039-esp32-handoff-state-dump.patch` extends the pause callback with
artifact-bound CPU, handoff-flag, DPORT/cache, SSI and cross-core counters.
`M5SW_ESP32_HANDOFF_PAUSE_ACTION=exit` makes one isolated Device Service lease
collect one virtual-time point without a debugger:

```bash
python3 tests/firmware/core2_handoff_trace/run_pause_sweep.py \
  --image path/to/normalized-core2.bin \
  --qemu path/to/qemu-system-xtensa \
  --pause-seconds 14.8 \
  --pause-seconds 15.3 \
  --pause-seconds 15.9 \
  --out-dir /tmp/core2-handoff-state-sweep
```

The artifact-bound sweep in
`evidence-2026-10-26-core2-handoff-state-sweep.json` recorded CPU0 at
`0x40087980` at both 14.8 and 15.3 seconds while CPU1 changed PC. Cache-sync
calls increased `16144 → 16180 → 17444`; changed-page work plateaued at
`6679`, while SSI transactions continued `6984 → 6998 → 7506` and
cross-core writes increased `40274 → 40566 → 43584`. This rejects a permanent
two-core stop but does not identify the operation that consumes the watchdog
budget.

`0040-xtensa-handoff-pc-trace.patch` adds a default-off,
`M5SW_XTENSA_PC_TRACE` comma-separated PC list. Only selected BIN-bound
instructions emit virtual time, CPU, PRID, PS, INTENABLE and INTSET:

```bash
python3 tests/firmware/core2_handoff_trace/run_pc_trace.py \
  --image path/to/normalized-core2.bin \
  --qemu path/to/qemu-system-xtensa \
  --observe-seconds 18 \
  --out-dir /tmp/core2-handoff-pc-trace
```

The retained run records first stage-0 WDT timeout at `5.913935 s`, first
reset at `15.914787 s`, and 4,376 complete-flag setter hits before reset.
Complete-clear/can-start set/clear setters each hit 4,377 times. Serial still
stopped before setup/REPL and the frame SHA remained the 302-byte black frame.
The repeated completed handoffs reject the simple permanent-deadlock
explanation; the remaining failure is cumulative handoff/flash service time or
a separate liveness bug that runs concurrently with those cycles.

An exploratory change that skipped `memory_region_flush_rom_device()` when
`changed_pages == 0` was rejected. The same firmware still entered
`TG0WDT_SYS_RESET`, reset PC `0`, and the same black-frame hash. That change
is not part of the retained patch series.

The trace is diagnostic only. It does not prove physical cache timing or close
`RUNTIME-03`.
