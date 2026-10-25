# Core2 intermittent cache-panic investigation

Last reviewed: `2026-10-26`. Historical root-cause record; current capability
and open production boundaries are maintained in
[Project current status](project-status.md) and
[project backlog](project-backlog.md).

Status: **mitigated for the official UIFlow2 virtual-device path; the legacy
UIFlow `RUNTIME-03` lane is still open, and physical/hardware equivalence
remains open**. This is an emulator scheduling/runtime issue, not a
peripheral-data failure.

> 历史根因页：2026-10-23 的后续定位已把最初 “cache panic” 命名修正为
> interrupt-WDT/timer starvation。当前可用能力见
> [项目当前状态](project-status.md)，剩余生产化项见
> [项目 Backlog](project-backlog.md)。

## 2026-10-23 update

The earlier label "cache panic" was too specific. A fresh failure was captured
after `UNIFIED_CORE2_IO_CONFIG_READY` with both CPUs in:

```text
esp_cpu_wait_for_intr
esp_pm_impl_waiti
esp_vApplicationIdleHook
prvIdleTask
Guru Meditation Error: Core 1 panic'ed (Interrupt wdt timeout on CPU1)
```

The QEMU cache illegal-access callback was not entered. The failed run had no
retry, no QOM pause and no QEMU `-m 0` retry masking. `-accel
tcg,thread=single` alone still reproduced the failure. Adding deterministic
icount scheduling:

```text
-accel tcg,thread=single
-icount shift=auto,align=off,sleep=off
```

then passed 10 independent first attempts, 10/10, with no retry. Every run
covered board peripherals, WiFi DHCP, controlled HTTP, public IPv4 DNS/HTTP,
UIFlow2 touch/audio and external HCI-offload BLE NUS in the same guest.

This strongly points to virtual timer/interrupt starvation while vCPUs are
idle under the default TCG virtual-clock execution model. It also explains the
historic `PANIC_RSN_CACHEERR` classification: the high-interrupt handler could
select that pseudo-cause without entering the QEMU cache trap callback.

What this does **not** prove:

- physical ESP32 cache/PSRAM timing is equivalent;
- every Core2 firmware/configuration is stable;
- icount timing matches real silicon;
- the bit-exact Espressif Bluetooth baseband/controller is modeled.

The separate `tests/uiflow2/core2_native_vhci/` runner now passes external NUS
GATT 5/5 through the stock firmware's VHCI boundary and a Bumble controller.
That closes controller-boundary behavior in this diagnostic runner, but not the
bit-exact internal controller implementation. The
`unified_core2 --ble-transport native-vhci` path also passes 3/3 with board,
WiFi and public network in the same guest after BB idle readback was fixed.

The same deterministic scheduler is now applied to all six Core2 peripheral
cases and the Core2 UI device-matrix path. Automatic retries were removed from
both matrices, and either runner now refuses a case that declares `retries`
unless `--allow-retries` is passed explicitly. A fresh full matrix completed
67/67 cases and 274/274 checks with `attempts=1` and `retry_used=false` for
every case; Core2 completed 5/5 repeated touch/RTC/power probes without a
retry.

The RTC probe exposed a second timing boundary: RX8130 and PCF8563 were based
on host `time(NULL)`, while `time.sleep_ms()` in a deterministic guest follows
QEMU virtual time. Their models now start from a host epoch captured at device
realize and advance on `QEMU_CLOCK_VIRTUAL`. This keeps the power-on date
realistic while making guest sleeps and register ticks coherent.

Do not remove the deterministic runtime options or replace them with
unconditional high retry counts. A future failure with these options should
preserve the exact serial/QMP/QEMU configuration and be treated as a new
blocker.

## Symptom

The official Core2 UIFlow2 v2.5.3 image occasionally prints:

```text
Guru Meditation Error: Core  / panic'ed (Cache error).
Cache disabled but cached memory region accessed
```

after the UIFlow banner. The guest resets, boots again, and the AXP192 or
other peripheral probe then passes normally. The failure is intermittent;
one six-run focused reproduction hit it once.

## Evidence collected

- A failed serial log is preserved as
  `serial.attempt-N.log` by the peripheral matrix.
- A matching UIFlow2 v2.5.3 Core2 ELF was built from `release/2.5.3` with
  ESP-IDF v5.5.4. The official and rebuilt IROM segments have the same load
  address and length; 2,546,199 of 2,559,324 bytes match (99.49%), making
  IROM symbolization reliable.
- The current panic reproduces on the first focused run under load. Symbolized
  PCs are in IRAM:
  - core 0: `spi_flash_op_block_func()` in
    `components/spi_flash/cache_utils.c:109`;
  - core 1: `esp_dport_access_reg_read()` called from
    `cache_ll_l1_disable_cache()` while a LittleFS block read is suspending
    flash caches.
- QEMU's cache illegal-access trap callback was instrumented
  unconditionally. It was not entered before the panic, so the firmware's
  printed `Cache error` string is not proof that
  `esp32_cache_ill_read()` fired. `PANIC_RSN_CACHEERR` is pseudo-cause 7 and
  can be selected by the ESP32 high-interrupt handler when it classifies the
  high-level interrupt source.
- A temporary direct, always-enabled IRAM alias was tested above the cache
  overlay so `IRAM_ATTR` code remains accessible when the cache model is
  disabled. UI and touch still passed, but the intermittent panic remained.
  The experiment was reverted; the failure is not simply the cache overlay
  hiding physical IRAM.
- A temporary DPORT trace showed normal repeated transitions between
  `0x00010020` and `0x00010028` on the PRO cache control register, with
  matching APP cache transitions.
- The QEMU `esp32_cache_ill_read()` trap path was not entered before the
  panic. The failure is therefore not explained by the model's
  illegal-access trap memory firing.
- `-smp 1` was tried; QEMU did not reliably reach the normal UI path on this
  dual-core machine.
- `-accel tcg,thread=single` with two CPUs still reproduced the same cache
  panic and produced a blank frame within the original timeout.

## Current mitigation

- Raw Core2 peripheral/UI cases use `-m 0`.
- Peripheral, UI, radio and unified Core2 runs use
  `tcg,thread=single,tb-size=128` plus deterministic icount.
- Matrix retries are rejected by default and only available through the
  explicit `--allow-retries` diagnostic switch.
- Device Service Core2 radio launches use the same deterministic options.
- RX8130/PCF8563 advance on QEMU virtual time from a boot epoch.

## 2026-10-24 follow-up

Two additional failure contexts were separated from the earlier idle-WDT
finding:

- The WiFi-only runner documented deterministic TCG/icount but did not pass
  those QEMU flags. A direct run then hit a Cache error at `WAITI` in both
  idle tasks. Adding `-accel tcg,thread=single` and
  `-icount shift=auto,align=off,sleep=off` produced five consecutive
  scan/association/DHCP/HTTP PASS runs.
- Core2 native-HCI extended runs could panic after nested guest allocator
  calls. Patch `0005` restores caller-saved Xtensa sregs and defers HLI
  allocator/callback injection until the vCPU is halted/idle. Two independent
  `5×10s` hold batches then passed `10/10`, with zero HLI errors and empty
  HLI/meta queues. Three independent `60s` holds also passed `3/3`; the
  expected BLE peer-close write tail is classified separately from HLI
  errors. Two independent `120s` holds subsequently passed `2/2`, including
  the peer-close TX queue-full tail with zero HLI errors and empty
  HLI/meta queues.

These are virtual-device context fixes. Later same-guest runs cover 20, 30,
60 and 120 reconnect cycles. A later artifact-bound 7200-second active-BLE
hold establishes the functional two-hour gate. Its host RSS growth was later
attributed to the unbounded TCG translation buffer, not guest PSRAM. The final
bounded `tb-size=128` two-hour rerun then passed all functional, asset/tool
hash, HLI and cleanup gates; 240 resource samples ended below their starting
RSS and physical footprint. This does not establish physical cache/PSRAM
timing or hardware equivalence. The later three-lease 121-cycle reconnect gate
also passed and is recorded in the current status page; this historical
investigation does not treat that functional result as a physical cache model.

## 2026-10-26 update

The legacy-UIFlow investigation produced a useful harness correction. An early
ESP-IDF
[`core2_flash_ipc`](../tests/firmware/core2_flash_ipc/) revision placed a
4096-byte local read buffer on a 4096-byte CPU1 task stack. Its stack overflow
corrupted a FreeRTOS queue lock and produced a `spinlock_release()` owner
mismatch before `READ_START`. The PRID values were correct; the lock itself was
inside the overrun stack allocation. That run is no longer model evidence.

The corrected probe uses a static aligned buffer and yields every 50 iterations.
Across current and portable QEMU batches:

- 20/20 first boots reached `CORE2_FLASH_IPC_READ_START`;
- 14/20 completed 1000 CPU1-side 4 KiB `esp_partition_read()` calls;
- 6/20 entered interrupt-WDT after at least 250 reads;
- 0/20 produced a spinlock owner assertion.

In the WDT samples both CPU0 and CPU1 were sampled in the idle
`esp_cpu_wait_for_intr()`/`waiti` path. This supports continued work on virtual
timer/interrupt delivery and host scheduling during long synchronous flash
workloads. It does not prove that legacy UIFlow has the same trigger, and it
does not establish physical timer/cache/PSRAM behavior.

The dated evidence and exact artifact hashes are in
[`evidence-2026-10-26-core2-flash-ipc-wdt.json`](../tests/firmware/core2_flash_ipc/evidence-2026-10-26-core2-flash-ipc-wdt.json).
The invalid early image/ELF hashes and stack-overflow correction are retained in
that evidence file.

## 2026-10-26 equal-deadline follow-up

IRQ-ring sampling then captured the timer ISR writing `CCOMPARE == CCOUNT`
inside the final equal-cycle window. The old `update_ccompare()` expression
subtracted in unsigned arithmetic and scheduled `2^32` ticks, deferring the
next Core2 timer interrupt by roughly 26.8 seconds. On the retained WDT
samples, the CPU1 deadline never advanced again before the interrupt watchdog
entered both CPUs.

[`0034-xtensa-ccompare-equal-deadline.patch`](../patches/qemu-m5stack-peripherals/0034-xtensa-ccompare-equal-deadline.patch)
handles only that equality: it arms the deadline for the next cycle. Every
other 32-bit delta keeps the previous wraparound behavior. The patch contains
no IRQ ring, tracing, timeout extension, guest injection or retry logic.

Post-fix controls passed the minimal probe's full first-boot/read gate in four
artifact-bound batches, with fixed and automatic icount and with tracing on
and off. Exact counts and hashes are in
[`evidence-2026-10-26-core2-ccompare-equal-deadline.json`](../tests/firmware/core2_flash_ipc/evidence-2026-10-26-core2-ccompare-equal-deadline.json).

This closes only the minimal probe's timer-starvation reproducer. The same
public `UIFlow_Core2 v1.15.4` image still emits `TG1WDT_SYS_RESET` and
`TG0WDT_SYS_RESET`, reports reset CPU `PC=0`, and returns only the same black
frame. The legacy firmware investigation therefore continues at watchdog
feed/clear and service-task starvation rather than treating the probe timer
fix as a universal Core2 boot fix.

## 2026-10-26 QIO and cross-core follow-up

The legacy startup trace then exposed two additional model facts.

First, the TIMG model raised the WDT level line even when
`INT_ENA.WDT` was clear. The observed state was
`INT_ENA=0x00000000`, `INT_RAW=0x00000004` and masked status `0`.
[`0035-esp32-timg-wdt-int-ena.patch`](../patches/qemu-m5stack-peripherals/0035-esp32-timg-wdt-int-ena.patch)
now raises the level only when the enable bit is set while preserving raw
status and stage-timer behavior. Two Device Service controls still reached
`TG0WDT_SYS_RESET` with reset PC zero after the mask fix, so this is a
register-semantics correction rather than the `RUNTIME-03` root cause.

Second, CPU1 spent a large part of early boot in QIO Flash reads while
scanning the VFS. The old path forwarded each byte through `ssi_transfer`.
A temporary opt-in shortcut used the same m25p80 `BlockBackend` and compared
direct reads with the following SSI stream. Across 512 sampled transactions
of 64 bytes, every byte matched. The shortcut advanced the temporary run to
the MicroPython setup text and `>>>`, but it bypasses the SSI command, dummy
and data phases. It therefore is not a product implementation; the product
path must add controller-level efficiency without inventing data in the
guest.

Disabling watchdog reset only moved the failure. The run remained at the UI
banner while cross-core IRQ0/IRQ1 continued to toggle. CPU0 remained in
`spi_flash_op_block_func` waiting at `0x3ffc7ec8`; CPU1 remained in the
DPORT safe-read / flash-cache handoff path. This makes the flash operation
block, cross-core acknowledgement, interrupt-matrix routing and DPORT
handoff ordering the next evidence target. It does not yet prove that this
stall is the first cause of the normal-WDT reset.

The summarized logs, byte comparison and boundaries are in
[`evidence-2026-10-26-core2-qio-crosscore-diagnostic.json`](../tests/firmware/evidence-2026-10-26-core2-qio-crosscore-diagnostic.json).
That evidence is explicitly `DIAGNOSTIC_ONLY`; it is not artifact-bound to a
product runtime, and the dirty QEMU worktree remains local.

## 2026-10-26 stateful SSI batch and throughput correction

The temporary direct-read path was replaced with
[`0036-ssi-transfer-buf.patch`](../patches/qemu-m5stack-peripherals/0036-ssi-transfer-buf.patch).
The generic SSI bus now has an optional byte-buffer transfer callback whose
fallback is still the original per-byte `ssi_transfer`. m25p80 uses the fast
path only in `STATE_READ`; command, address, dummy, CS and address-wrap
semantics remain unchanged. ESP32 SPI invokes the buffer path only for a
receive-only data phase.

For the first 512 batches, the new path was executed alongside the original
m25p80 per-byte implementation from the same saved address: all 512
64-byte batches matched. The Core2 UIFlow2 peripheral group passed `6/6`.
Nevertheless, the same legacy firmware still reset under the normal watchdog,
and 180 seconds with watchdog reset disabled did not reach setup text or the
REPL. The earlier direct-read REPL result did not reproduce in the current
rebuild.

A direct memory-state trace adds an important correction to the earlier
hypothesis. `s_flash_op_can_start`, `s_flash_op_complete` and the cross-core
reason words repeatedly transitioned between zero and one. CPU0 was repeatedly
observed in `spi_flash_op_block_func`, while CPU1 appeared in cache/DPORT and
scheduler paths, but this is not a permanent handshake deadlock. Accelerator
controls were also slower: `thread=single` with icount `shift=5` or `shift=0`,
and without icount, did not reach the full banner within their windows.

The leading hypothesis is therefore aggregate throughput: legacy boot performs
many synchronous flash operations and cross-core cache handoffs, and the sum
does not fit inside the watchdog window. The unified trace added by `0037`
below establishes that virtual-time axis before any further model change.

See
[`evidence-2026-10-26-core2-ssi-transfer-buf.json`](../tests/firmware/evidence-2026-10-26-core2-ssi-transfer-buf.json)
for the equivalence, matrix and control results.

## 2026-10-26 unified handoff timeline

[`0037-esp32-handoff-trace.patch`](../patches/qemu-m5stack-peripherals/0037-esp32-handoff-trace.patch)
adds a default-off `M5SW_ESP32_HANDOFF_TRACE` channel. Cross-core writes,
DPORT cache control/sync, SSI transactions and TIMG watchdog events now share
virtual time, CPU and guest-PC fields. Routine events can be sampled with
`M5SW_ESP32_HANDOFF_TRACE_SAMPLE`; WDT timeout, interrupt and reset events are
always retained.

Two independent normal-WDT runs reached the same critical shape:

- TIMG group 1 fed continuously until the final feed, with 12,087 and 12,045
  tracked feeds in the two sampled runs;
- exactly `800,000,000 ns` after that last feed, stage 0 timed out on CPU1;
- roughly `1.6 s` later, stage 1 completed the reset sequence;
- the timeout PC changed between runs, so the failure is not tied to one guest
  instruction address.

The trace therefore narrows the problem from "the watchdog never gets fed" to
"CPU0 stops servicing the feed path for a bounded window at the end of a long
synchronous sequence". It does not yet identify whether the final blocker is a
cache disable, an atomic/IPC wait, TCG scheduling, or another guest task.

For the WDT-disabled control, `sample=1024` and trace-off produced the same
507-byte Serial SHA and the same MicroPython startup banner without setup text
or `>>>`. The sampled trace ran to about `14.19 s` virtual time with repeated
CPU1 SSI read, cache-control, cache-sync and cross-core events, then retained
no timeout or reset. Higher-density tracing perturbs scheduling, so the
`sample=1024` comparison is the accepted control.

A separate 1 ms dual-PC sampler kept the same 800 ms final feed gap but moved
the reset earlier. During that window, all 800 samples fell into only six
CPU0/CPU1 PC pairs:

- CPU0 stayed at `0x400843ac`, `0x400843af` or `0x400843b1`, inside
  `uart_rx_intr_handler_default`;
- CPU1 stayed at `0x4008649c` or `0x4008649e`, inside
  `mp_execute_bytecode`.

At the time of this run, the local UIFlow Core2 ELF mapping was treated as
diagnostic but not artifact-bound. A later same-VMA byte audit rejected that
mapping completely: the public BIN contains different bytes at all three CPU0
sample addresses, so the `uart_rx_intr_handler_default` and
`mp_execute_bytecode` names in this timeline must not be used as the current
explanation. UART `INT_ENA`, `INT_CLR` and IRQ-state tracing recorded no UART
event inside the final 800 ms. The PC sampler itself perturbs scheduling and is
kept off by default.

See
[`evidence-2026-10-26-core2-handoff-timeline.json`](../tests/firmware/core2_handoff_trace/evidence-2026-10-26-core2-handoff-timeline.json).

## 2026-10-26 BIN/ELF address audit

[`audit_elf_bin_mapping.py`](../tests/firmware/core2_handoff_trace/audit_elf_bin_mapping.py)
parses the ESP32 application inside the normalized 16 MiB flash image, locates
the segment covering a virtual address, and compares its bytes with the ELF32
section at the same address.

For public `UIFlow_Core2 v1.15.4`:

- app image offset: `0x10000`;
- segment 3 load address: `0x40080400`;
- CPU0 sample addresses: `0x400843ac`, `0x400843af`, `0x400843b1`;
- all three 16-byte windows differ from local `UIFlow2 v2.5.3` ELF
  `5bec056b…`;
- audit classification: `BIN_ELF_BYTES_MISMATCH`.

The exact BIN bytes around the sample cluster select CPU0/CPU1 DPORT addresses
`0x3ff000e8`/`0x3ff000e4` and access state around `0x3ffc7750`, `0x3ffc7748`,
`0x3ffc7760` and `0x3ffc7758`. That shape is consistent with older ESP-IDF
cross-core Flash/cache-disable handoff code, but without a matching ELF/MAP it
does not prove a function name or a specific waiter.

See
[`evidence-2026-10-26-core2-pc-mapping-audit.json`](../tests/firmware/core2_handoff_trace/evidence-2026-10-26-core2-pc-mapping-audit.json).

## 2026-10-26 exact-time vCPU freeze

[`0038-esp32-handoff-pause.patch`](../patches/qemu-m5stack-peripherals/0038-esp32-handoff-pause.patch)
adds `M5SW_ESP32_HANDOFF_PAUSE_NS`. At the requested QEMU virtual timestamp,
QEMU writes a pause marker and sends `SIGSTOP` to itself, freezing both vCPUs
without enabling the perturbing high-frequency PC sampler.

Two independent first-boot controls produced:

- at `14.800033 s`, no fixed CPU cluster; both CPUs showed `INTSET=0x40`, but
  neither had a pending QEMU hard-interrupt request;
- at `15.301447 s`, CPU0 at `0x40087980`, CPU1 at `0x40084484`; CPU1 had
  `INTSET=0x40` and `CPU_INTERRUPT_HARD` pending;
- both runs retained the same 507-byte banner-only Serial and had not reached
  a WDT timeout or reset.

The public BIN around `0x40087958` clears `0x3ffc7ec8`, sets `0x3ffc7ec9`, then
loops on the first byte. That source pattern matches the old ESP-IDF
`spi_flash_op_block_func`: mark cache hand-off ready and wait for the initiating
CPU to mark the flash operation complete. CPU1's late-window caller and
`0x40084478` helper are in the companion cache hand-off path.

This evidence removes UART ISR/service starvation as the primary explanation
for the sampled cluster and narrows the remaining question to which cache
restore, SSI operation or return path fails to complete within the final
800 ms. The addresses are BIN-bound; the function names are source-pattern
matches, not ELF-symbol-bound.

See
[`evidence-2026-10-26-core2-handoff-pause.json`](../tests/firmware/core2_handoff_trace/evidence-2026-10-26-core2-handoff-pause.json).

## 2026-10-26 exact-time state sweep

[`0039-esp32-handoff-state-dump.patch`](../patches/qemu-m5stack-peripherals/0039-esp32-handoff-state-dump.patch)
makes the exact-time pause self-describing. Before stopping or exiting, QEMU
records:

- both vCPU PCs and QEMU interrupt-request/halted state;
- `0x3ffc7ec8`, `0x3ffc7ec9`, `0x3ffc7750` and `0x3ffc7754`;
- DPORT cache-control/stall state;
- cache-sync, SSI transaction/byte and cross-core write counters.

The artifact-bound 14.8/15.3/15.9-second sweep observed CPU0 at
`0x40087980` at both earlier points while CPU1 changed PC. Cache-sync calls
increased `16144 → 16180 → 17444`; changed-page work stopped increasing at
`6679`; SSI transactions increased `6984 → 6998 → 7506`; cross-core writes
increased `40274 → 40566 → 43584`.

This is not a two-core permanent stop. CPU1 continues entering DPORT/cache,
SSI and cross-core paths while CPU0 waits in the flash-operation block
function.

See
[`evidence-2026-10-26-core2-handoff-state-sweep.json`](../tests/firmware/core2_handoff_trace/evidence-2026-10-26-core2-handoff-state-sweep.json).

## 2026-10-26 completed handoff setter trace

[`0040-xtensa-handoff-pc-trace.patch`](../patches/qemu-m5stack-peripherals/0040-xtensa-handoff-pc-trace.patch)
adds a default-off `M5SW_XTENSA_PC_TRACE` list in the Xtensa translator. It
logs only explicitly selected BIN-bound instructions with CPU, PRID, PS,
INTENABLE and INTSET; there is no periodic sampler.

For the four observed handoff setters:

- `0x40087965`: clear complete;
- `0x4008797a`: set can-start;
- `0x40087a25`: clear can-start;
- `0x40087b02`: set complete.

The first normal-WDT run reached stage-0 timeout at `5.913935 s`, then reset at
`15.914787 s`. Before reset, each setter was hit about `4,377` times. CPU0 is
therefore repeatedly waiting and being released, while CPU1 repeatedly runs
flash/cache operations. The old “one handoff never returns” explanation is
not supported.

An exploratory host-side change that skipped
`memory_region_flush_rom_device()` when `changed_pages == 0` still produced
`TG0WDT_SYS_RESET`, reset PC `0` and the same black frame. The result is
retained as a rejected control and the change is not in the patch series.

At that point, the unresolved question was how roughly 4,376 completed handoff
cycles and about 250 KiB of SSI data before the first reset related to startup
progress. The WDT-off late-state section below narrows the later phase but does
not yet answer this reset-time question.

See
[`evidence-2026-10-26-core2-handoff-pc-trace.json`](../tests/firmware/core2_handoff_trace/evidence-2026-10-26-core2-handoff-pc-trace.json).

## 2026-10-26 WDT liveness reconciliation

Three independent Device Service leases disabled the PC trace and enabled the
TIMG verbose trace for 18 virtual seconds. All three reached the same
classification:
`BOOTLOADER_TG0_STAGE1_RESET_WITH_TG1_LIVE`.

| run | TG0 stage-0 | TG0 stage-1 reset | TG1 feeds | max TG1 interval | last feed to reset |
| --- | ---: | ---: | ---: | ---: | ---: |
| 1 | `5.910698 s` | `15.912522 s` | 6,681 | `8.505 ms` | `1.797 ms` |
| 2 | `5.922631 s` | `15.926661 s` | 6,618 | `10.410 ms` | `4.271 ms` |
| 3 | `5.910705 s` | `15.912004 s` | 6,807 | `8.478 ms` | `1.779 ms` |

The TG0 stage-0 timeout is masked. TG1 records no interrupt-WDT before the
TG0 stage-1 system reset, and there are no TG0 feed, reconfigure or protect
writes after stage-0. The earlier 800 ms feed gap therefore belongs to an
earlier trace configuration and is `NOT_REPRODUCED` by this control; it must
not be treated as the current first-cause path.

See
[`evidence-2026-10-26-core2-wdt-liveness-3x.json`](../tests/firmware/core2_handoff_trace/evidence-2026-10-26-core2-wdt-liveness-3x.json).

## 2026-10-26 WDT-off late state

`0041-esp32-handoff-register-stack-dump.patch` extends the exact-time pause
with A0-A15, PS, selected object forward pointers and an optional bounded stack
window. WDT disable is used only as a diagnostic control so the boot can pass
the normal reset window.

Two independent 45-second and 120-second snapshots converge on the same state:

| item | observed state |
| --- | --- |
| CPU0 | halted in `waiti` at `0x4026306e` |
| CPU1 | running spin at `0x40100049` |
| Flash handoff | `49,848` cache-sync calls, `45,847` changed pages, `49,265` state updates |
| SSI | `22,554` transactions, `671,936` RX bytes |
| last Flash/SSI activity | about `43.91-44.00 s` |
| cross-core writes | `123,476` at 45 s, `139,094` at 120 s |
| CPU1 pointers | `A2+24=1`, `*(A3)=A10`, `A10+28=0` |
| serial | same 507-byte banner-only hash at both snapshots |

The Flash/SSI counters are identical at both snapshots, so the former
"Flash scan has no endpoint" hypothesis is retired. The boot instead reaches a
stable late-loop wait. `RUNTIME-03` remains open because WDT-off is not a
product fix, the object has no matching symbol and the normal-WDT path still
resets at TG0 stage-1 without a non-empty frame.

See
[`evidence-2026-10-26-core2-wdt-off-late-state.json`](../tests/firmware/core2_handoff_trace/evidence-2026-10-26-core2-wdt-off-late-state.json)
and
[`0041-esp32-handoff-register-stack-dump.patch`](../patches/qemu-m5stack-peripherals/0041-esp32-handoff-register-stack-dump.patch).

## Next investigation

1. Preserve the minimal probe's equal-deadline regression gate and keep the
   business patch separate from diagnostic ring/trace code.
2. Preserve the stateful SSI batch path and its byte-equivalence gate.
3. Obtain a matching v1.15.4 ELF/MAP. Until then, follow BIN call/return and data
   accesses around `0x40100049`, `A2+24`, `A3`, and `A10+28` to identify the
   late flag producer and consumer; do not reuse local v2.5.3 symbols.
4. Correlate the last Flash/SSI event at about 44 seconds with the start of the
   CPU1 late loop. Explain which expected event or object transition is absent
   after Flash work ends.
5. Reconcile the normal-WDT TG0 stage-1 reset with the WDT-off late state. Keep
   TG0/TG1 feed/clear, stage, mask, `INTSET`, `INTENABLE`, reset PC `0`, and
   service-task progress on the same virtual timeline.
6. Re-run `Core2FactoryTest` after the shared-I2C fix and keep the Core2
   UIFlow2 device group as the shared-bus regression gate.
7. Keep physical cache/PSRAM timing as `NOT RUN` until real Core2 evidence is
   collected.

## Reproduction

Build the matching ELF:

```bash
python3 tests/uiflow2/build_core2_symbols.py --clean
```

Repeat the focused Core2 boot until a panic is captured:

```bash
PYTHONPATH=.work/py python3 tests/uiflow2/run_profile_ui_test.py \
  --base platform/.cache/firmware/core2/uiflow2.bin \
  --machine m5core2 --files-dir tests/uiflow2/core2_ui_test \
  --vfs-offset 0x820000 --vfs-size 0x7DF000 --flash-size 0x1000000 \
  --expected-size 320x240 --wait 10 --input touch:160,183 \
  --allow-static-frame --efuse-driver none --memory 0 \
  --out-dir /tmp/core2-run
```

Symbolize a captured log:

```bash
python3 tests/uiflow2/symbolize_core2_panic.py \
  /tmp/core2-run/serial.log \
  --elf .work/uiflow2-core2-symbols/micropython.elf
```
