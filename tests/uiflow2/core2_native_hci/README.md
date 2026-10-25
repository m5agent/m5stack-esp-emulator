# Core2 native HCI transport

Last reviewed: `2026-10-25`

This directory validates the QEMU-side `CORE2-01` data plane from the
`esp32-native-hci` H4 chardev through the stock firmware HLI/API boundary to
Bumble and the Device Service evidence bundle. It does not execute a
bit-exact Bluetooth controller/baseband or physical RF model.

| Stage | Status | Evidence |
| --- | --- | --- |
| `HCI-1` host transport | `PASS` | `evidence-2026-10-24-transport-pass.json` |
| `HCI-2` guest H2C | `PASS` | `evidence-2026-10-24-guest-h2c.json`; first Reset capture, extended by the complete `HCI-3b` flow |
| `HCI-3a` guest C2H callback | `DIAGNOSTIC PASS` | `evidence-2026-10-24-c2h-delivery.json` and `evidence-2026-10-24-c2h-delivery-5x.json`; Reset Complete then next H2C. This narrow callback route is not the production C2H backend |
| `HCI-3b` HLI event | `PASS` | `evidence-2026-10-24-hli-event-5x.json`; pool-allocated Reset Complete through event 13 advances `01030c00` to `01011000` in 5/5 runs |
| `HCI-3b` complete HCI/GATT | `PASS` | `evidence-2026-10-24-hli-api-gatt-5x.json`; 15-byte probe / 17-byte ATT PDU completes discovery, subscription, write, Python handler, notification and Bumble ACK in 5/5 runs |
| `HCI-4` repeated lease | `PASS` | `evidence-2026-10-24-hci4-service-5x.json`; five independent `/api/v1` leases pass frame, 27-node QOM, WiFi/public network, NUS GATT, pcap and evidence with `gdb_bridge=false` |
| `CORE2-02` extended run | `PASS` | `evidence-2026-10-24-hci4-halted-gate-5x.json`, `evidence-2026-10-24-hci4-hold60-3x.json`, `evidence-2026-10-24-hci4-hold120-2x.json` and `evidence-2026-10-24-hci4-active-ble-hold120-2x.json`; two 5-attempt batches with 10-second holds passed `10/10`, three 60-second holds passed `3/3`, two 120-second holds passed `2/2`, and two active-BLE 120-second holds passed `2/2`. Every attempt has `hli-errors=0` and zero HLI/meta queue depth |
| `CORE2-02` active-BLE 600s hold | `PASS` | `evidence-2026-10-24-hci4-active-ble-hold600-2x.json`; two independent leases pass with `ble_linger_seconds=660`; the peer stays connected for 600 seconds, HLI is 45/45 and all queue/error counters are zero |
| Core2 upper-PSRAM MMU bank switch | `3/3 PASS` | `tests/firmware/core2_psram_himem/run_test.py`; three independent leases map two distinct upper-memory blocks through the same virtual window, verify both after remap, and report `physical_himem_bytes=4456448`, reserve `262144` and QOM `8388608` |
| Core2 guest PSRAM sustained stress | `3/3 PASS` | `evidence-2026-10-25-core2-psram-sustained-8m-3x120.json`; the QOM PSRAM device is 8 MiB while the normal ESP32 DRAM1 heap remains 4 MiB. Three independent 120-second leases each allocate 1 MiB and complete 35/35/35 readback sweeps while repeating HTTP/network checks. Physical cache/PSRAM timing remains `NOT RUN` |
| Core2 guest PSRAM 600-second stress | `1/1 PASS` | `evidence-2026-10-25-core2-psram-sustained-1x600.json`; one 600-second lease completes 179 readback sweeps, 51 controlled HTTP rechecks and 18 public rechecks while active BLE, bounded TCG, frame/QOM, pcap and cleanup remain PASS |
| `CORE2-02` artifact-bound 7200s hold | `FUNCTIONAL PASS / RSS REVIEW` | `evidence-2026-10-24-hci4-active-ble-hold7200-artifact-bound-1x.json`; launch firmware/ELF/QEMU hashes are frozen before the first lease and do not drift. Frame/QOM, WiFi, public DNS/HTTP, external NUS GATT, pcap, evidence, HLI `45/45` and cleanup pass. QEMU host RSS grew from `744160` to `1202176 KiB`; later `vmmap` evidence attributed the growth to the unbounded TCG translation buffer |
| Core2 bounded TCG memory | `PASS / 120s` | `evidence-2026-10-24-hci4-tb128-hold120-1x.json`; `tb-size=128` keeps the 120-second run fully functional while RSS delta is `-16 KiB` and phys-footprint delta is `-17408 KiB` |
| `CORE2-02` final bounded 7200s | `PASS` | `evidence-2026-10-25-hci4-active-ble-hold7200-tb128-artifact-bound-1x.json`; one artifact-bound 7200-second lease passes `bounded_tcg_cache`, frame/QOM, WiFi/public DNS/HTTP, active NUS GATT, pcap, HLI `45/45`, active peer and cleanup. Across 240 samples, RSS `323536→252992 KiB`, phys footprint `250880→188416 KiB`; launch firmware/ELF/QEMU and runner/service/accelerator/limits hashes remain unchanged |
| `CORE2-02` same-guest reconnect | `PASS` | `evidence-2026-10-24-hci4-reconnect20-3x.json`; three independent stock-firmware leases complete twenty full NUS GATT cycles each. Every lease balances HLI 577/577, delivers 397 events and 180 ACLs, leaves HLI/meta queues empty and returns the connection/L2CAP/GATT pools to their 3/9/3 free baseline. The earlier ten-cycle evidence remains as `evidence-2026-10-24-hci4-reconnect10-3x.json`; the forbidden Bumble Command Status for no-response opcode `0x0c35` was the historical stale-ACK root cause |
| `CORE2-02` 30-cycle reconnect | `PASS` | `evidence-2026-10-24-hci4-reconnect30-3x.json`; three independent stock-firmware leases complete thirty full NUS GATT cycles each. Every lease balances HLI 857/857, delivers 587 events and 270 ACLs, with zero errors, empty queues and connection/L2CAP/GATT pools back at 3/9/3 |
| `CORE2-02` 60-cycle reconnect | `PASS` | `evidence-2026-10-24-hci4-reconnect60-3x.json`; three independent leases complete sixty cycles each with HLI 1697/1697, 1157 events, 540 ACLs, zero errors and pools back at 3/9/3 |
| `CORE2-02` 120-cycle reconnect | `PASS` | `evidence-2026-10-24-hci4-reconnect120-3x.json`; three independent leases complete 120 cycles each with HLI 3377/3377, 2297 events, 1080 ACLs, zero errors/dropped packets and pools back at 3/9/3 |
| `CORE2-02` 121-cycle readiness budget | `FIXED` | `evidence-2026-10-25-hci4-reconnect121-readiness-timeout-1x.json`; the first run completed 29 cycles and started cycle 30 before a fixed 180-second budget stopped a healthy session. The runner and Device Service now share `reconnect_workload_timeout_seconds()` |
| `CORE2-02` reconnect accelerator sampling | `FIXED` | `evidence-2026-10-25-hci4-reconnect121-accelerator-sampling-fail-1x.json`; a reconnect-only run completed all functional checks but did not sample the QEMU accelerator because that sampling lived only in the hold loop |
| `CORE2-02` 121-cycle three-lease gate | `3/3 PASS` | `evidence-2026-10-25-hci4-reconnect121-3x.json`; three independent artifact-bound leases each complete 121 cycles with identical firmware/ELF/QEMU/tool hashes, `tb-size=128`, WiFi/public network, NUS GATT, frame/QOM, pcap, evidence and cleanup. Every lease has HLI 3405/3405, 2316 events, 1089 ACLs and zero queue/error/drop/peer-close/panic |
| `CORE2-02` active stop/recovery | `3/3 PASS` | `evidence-2026-10-25-core2-active-stop-recovery-3x.json`; three consecutive sessions are deleted while their BLE peer is still in the linger window. Each stop reaches `stopped` with no error, terminates HTTP/BLE companions, reaps both BLE and QEMU PIDs, releases the worker lease, and is followed by a new ready session with the same network/GATT/QOM health |
| `CORE2-02` no-stagger concurrency | `8/8 + 6/6 PASS` | two independent two-instance `4x120s` runs pass `8/8`; two independent three-instance `3x120s` runs pass `6/6`. `0008` preallocates real guest event buffers and ACL mbufs; every lease records 36/9 fast-path event/ACLs, HLI 45/45 and zero errors/reset/panic. Three-instance startup exposed a fixed 40-second peer scan budget that expired before guest BLE init, then a sweep threshold calibrated only for lower concurrency; peer scan now follows session readiness within 120 seconds and the sustained floor is `hold/5` |

Build the patched QEMU, then run:

```bash
python3 tests/uiflow2/core2_native_hci/test_transport.py
```

The test starts `m5core2` paused with an empty flash image, attaches a socket
chardev, sends one H4 event and one fragmented ACL packet, and checks QOM
counters and queue state. It then fills the 32-packet queue and verifies the
next packet is counted as dropped. It also verifies peer disconnect accounting
and requires a clean QEMU shutdown.

Transport-only evidence:
`evidence-2026-10-24-transport-pass.json`.

## Guest H2C and C2H callback

The second targeted test receives the first stock-firmware H2C packet without
starting a GDB bridge. The device reads the ELF-known `vhci_env_p` pointer and
polls the real VHCI H2C buffer/length fields through QEMU's address space.

```bash
python3 tests/uiflow2/core2_native_hci/test_guest_h2c.py \
  --image /path/to/stock/core2-uiflow2.bin \
  --enable-c2h \
  --out-dir /tmp/core2-guest-h2c
```

The test resolves the matching ELF `vhci_env_p`, registered callback table and
`malloc`. It captures `01030c00`, sends the target reset command a complete
event, invokes `notify_host_recv`, calls send-available, and requires the guest
to emit `01011000`. Its committed evidence is one packet, not a complete
Bluetooth sequence.

## Full HCI/GATT diagnostic

`run_full.py` starts a Bumble controller/peer, runs the stock image through QEMU
native HCI without GDB, and requires external NUS service discovery, write,
notification and guest ACK:

```bash
PYTHONPATH=.work/py python3 tests/uiflow2/core2_native_hci/run_full.py \
  --image /path/to/stock/core2-uiflow2.bin \
  --out-dir /tmp/core2-native-hci-full
```

The HLI event/ACL diagnostic uses the matching ELF and adds `--hli-c2h`:

```bash
PYTHONPATH=.work/py python3 tests/uiflow2/core2_native_hci/run_full.py \
  --image /path/to/stock/core2-uiflow2.bin \
  --elf /path/to/matching/micropython.elf \
  --hli-c2h \
  --out-dir /tmp/core2-native-hci-hli
```

This flag requires a QEMU build with the committed `0002`-`0004`
HLI/API-boundary patches. The runner and the Device Service share the same
`core2_native_hci_device_args()` ELF resolver, so the arguments are not
duplicated between test and service.

The final `HCI-3b` diagnostic passes. The earlier timeout was caused by the
21-byte `M5_CORE2_NATIVE_PROBE` payload: its ATT PDU is 24 bytes, which
exceeds the guest's default 23-byte ATT MTU, so `ble_l2cap_rx` drops it before
ATT dispatch. The default 15-byte `M5_CORE2_PROBE` produces a 17-byte ATT PDU
and completes the full NUS GATT exchange.

The final full GATT evidence is
`evidence-2026-10-24-hli-api-gatt-5x.json`; the older
`evidence-2026-10-24-hci3b-diagnostic.json` is retained as a failure record.

Temporary instrumentation showed that `malformed-packets` in this run were
non-final writes to the VHCI H2C length field, not corrupted H4 receive data.
Valid full-length H2C packets and all generated C2H packets reached the correct
transport side; callback status was 0. The unresolved boundary is the
controller-response lifecycle and the vCPU safe point/context used to enter
firmware callbacks, not the H4 byte parser.

A follow-up safe-point audit also saved and restored common caller-saved Xtensa
special registers (`SAR`, `LITBASE`, loop registers, `M0-M3`, `THREADPTR`,
`ATOMCTL` and related state) before invoking callbacks at arbitrary CPU0 safe
points. The guest still returned ACK 12 twice and crashed with
`LoadProhibited`. Direct callback injection is therefore not a valid general
controller-notification context. Evidence:
`evidence-2026-10-24-hci3b-safe-point-audit.json`.

A second controller-entry audit called the firmware's real
`r_eif_send -> vhci_send` C2H path, which invokes the registered receive
callback and updates VHCI flow state. Invoking that entry as a nested guest RPC
failed with a cache-disabled memory access and did not return normally.
Evidence:
`evidence-2026-10-24-hci3b-controller-entry-audit.json`.

Controller delivery must therefore be a device/IRQ event with valid cache and
flow-control context, or an in-process controller model. It cannot be a
synchronous QEMU-to-guest internal-function call.

## HLI event delivery

The firmware build has `CONFIG_BTDM_CTRL_HLI=1`. NimBLE runs on core 1 and the
BT controller on core 0. QEMU can follow `g_rw_schd_queue` into the dynamic
`hli_queue_t`, write an 8-byte controller work item, append the queue handle
to the 4-byte meta queue, and raise HLI software interrupt 29.

An initial event-13 callback to `ets_printf` made the guest print
`Fatal error in queue_signal: s_meta_queue full`. QOM reported no HLI error,
and both HLI/meta queue depths returned to zero. This proves the guest HLI ISR
and controller task consume a QEMU-posted work item through a valid task/IRQ
context. The retained follow-up test now allocates an event through
`ble_transport_alloc_evt(0)`, writes HCI bytes without the H4 type byte and
delivers it through `ble_transport_to_hs_evt_impl`. Five consecutive runs
advance the stock guest from `01030c00` to `01011000`, with
`hli-posts=1`, `hli-consumed=1`, `hli-event-buffers=1`, `hli-errors=0` and
empty HLI/meta queues.

The original marker evidence remains at
`evidence-2026-10-24-hci3b-hli-queue-diagnostic.json`. The real-event result is
`evidence-2026-10-24-hli-event-5x.json`, reproduced by
`test_hli_event.py`.

The retained `0003` patch extends this seam to ACL ownership through
`ble_transport_alloc_acl_from_ll` and `ble_transport_to_hs_acl_impl`, with an
explicit API-boundary H2C transaction and flow control. That is what closes
the complete external GATT sequence in `HCI-3b`.

A local C2H experiment invoked the guest `vhci_send` address and made the
function return, but the firmware still timed out waiting for the controller
acknowledgement. That confirms `vhci_send` is not a direct H4 packet-ingest
entry point and the experiment is not part of this patch. The committed path
uses the firmware-observed callback contract and QOM
queued/delivered/error/status counters.

## API-boundary audit

The internal-controller relay and the external Bumble controller cannot both
own the same VHCI transaction. A later no-GDB experiment installed a QEMU CPU
hook at `API_vhci_host_send_packet`, captured the real H2C arguments directly,
returned at the wrapper call site, and kept the firmware controller out of the
data path.

The GDB diagnostic established the required pre-entry return contract:

- API PC is `0x403064d8`;
- the wrapper call site is `0x402670a8`;
- `WINDOW_BASE` remains unchanged at the breakpoint;
- rotating the Xtensa window at this pre-entry point corrupts the caller and
  causes a cache-disabled panic.

With the corrected return semantics, the best API-hook run completed
advertisement, connection, NUS service discovery and CCCD subscription without
HCI parser errors or dropped packets. Bumble sent the NUS write, but the final
guest callback/notification transaction did not complete. This is a partial
advance, not an `HCI-3b` PASS.

Evidence:
`evidence-2026-10-24-hci3b-api-boundary-audit.json`.

With the legal 17-byte ATT PDU, the HLI/API-boundary path is stable:

- 39 HLI events and 9 ACL buffers;
- no L2CAP MTU rejection, malformed packet or dropped packet;
- ATT write, Python GATT handler and Python notify path for the NUS RX data;
- Bumble receives `ACK:M5_CORE2_PROBE`;
- five consecutive passes with no transaction H2C errors.

The HCI peer may be closed immediately after `BLE_BUMBLE_PASS`; any later
`EIO` is recorded under `post_sequence_teardown` and is not part of the GATT
transaction result.

## Device Service repeated lease

`run_service_5x.py` drives the real `/api/v1` control plane. It uploads one
firmware and matching ELF, creates five independent `qemu-unified` sessions
with `profile=core2-native-hci`, and checks each session for:

- a 320x240 PNG frame and a non-empty QOM snapshot;
- WiFi DHCP/controlled HTTP and public IPv4 DNS/HTTP;
- external Bumble NUS discovery/subscription/write/notify;
- QEMU pcap and the complete, session-bound evidence ZIP;
- transport string `ESP32 native HCI device + HLI to Bumble`.
- native HLI health from QOM: valid path, balanced posts/consumption,
  `hli-errors=0`, empty HLI/meta queues, and nonzero event/ACL delivery.

```bash
python3 run_service_5x.py \
  --image /path/to/unified-core2.bin \
  --elf /path/to/matching/micropython.elf \
  --qemu /path/to/qemu-system-xtensa \
  --attempts 5 \
  --hold-seconds 10 \
  --out-dir /tmp/m5-core2-native-hci-service-5x
```

The committed evidence is
`evidence-2026-10-24-hci4-service-5x.json`. The profile is supported only
under trusted-host isolation. It is not bit-exact controller, RF, malware
sandbox or physical-hardware validation. The legacy `core2-native-vhci`
profile remains available for diagnosis but is not the canonical path.

Two concurrent 120-second leases can be exercised with a 30-second startup
stagger:

```bash
python3 run_service_5x.py \
  --image /path/to/unified-core2.bin \
  --elf /path/to/matching/micropython.elf \
  --qemu /path/to/qemu-system-xtensa \
  --attempts 2 \
  --concurrency 2 \
  --stagger-seconds 30 \
  --hold-seconds 120 \
  --require-psram \
  --out-dir /tmp/m5-core2-concurrent-2x120
```

The canonical HTTP fixture for `core2-native-hci` now uses a per-session QEMU
`guestfwd` command, so concurrent QEMUs do not share host port 18089. The
committed `2/2 PASS` evidence is
`evidence-2026-10-25-core2-concurrent-2x120-stagger30.json`. Two failure
controls preserve the initial shared-port collision and the no-stagger
second-guest `ble_hs_hci_process_ack` `LoadProhibited`.

The no-stagger path was diagnosed and closed for two concurrent instances:

1. A one-pair run passed `2/2` after extended GATT request and notification
   timeouts were raised to 30 seconds.
2. An expanded four-lease run then failed `3/4`: every HCI packet was
   eventually delivered, but attempt 3 ended with `hli-errors=3`.
3. QEMU patch `0007` now refuses to schedule HLI delivery until the previous
   poll observed a valid guest scheduler/meta queue. With that gate, the
   first four-lease run passed `4/4`.
4. An independent four-lease confirmation still hit
   `ble_hs_hci_process_ack` `LoadProhibited`. Packet trace showed Bumble
   returned Command Status in about `4.6ms`, but ACL mbuf allocation blocked
   HLI delivery for about `3.660s`, beyond the guest's `2s` HCI ACK budget.
5. QEMU patch `0008` preallocates two real guest event buffers and two ACL
   mbufs while CPU0 is idle. Busy CPU0 no longer needs nested guest calls to
   fill those objects.
6. Two independent final `4x120s` runs pass `4/4` each (`8/8` total).
   Every lease reports 36 events and 9 ACLs on the fast path, two spare
   objects of each type, HLI `45/45`, `hli-errors=0`, no scheduler reset and
   no panic. The measured Command Status delivery delay is about `0.328s`.
7. Extending each batch to three simultaneous leases initially failed `0/3`:
   the fixed 40-second BLE peer scan window expired before guest BLE
   initialization completed in about 55 seconds.
8. The peer scan window is now derived from the session readiness budget and
   bounded to `120s`; GATT request and notification timeouts remain separate.
9. The next three-instance run completed guest/network/GATT/PSRAM work, but
   two leases produced 29 sweeps against an over-tight 30-sweep floor. The
   sustained gate now uses a conservative `hold/5` floor while still
   requiring contiguous sweeps, heartbeats, HTTP and public-network rechecks.
10. Two independent three-instance `3x120s` runs then passed `3/3` each
    (`6/6` total).

Evidence:

- `evidence-2026-10-25-core2-concurrent-2x120-simultaneous-timeout30-pass.json`
- `evidence-2026-10-25-core2-concurrent-4x120-hli-errors-fail.json`
- `evidence-2026-10-25-core2-concurrent-4x120-simultaneous-pass.json`
- `evidence-2026-10-25-core2-concurrent-4x120-simultaneous-confirm-fail.json`
- `evidence-2026-10-25-core2-concurrent-4x120-prealloc-pass-a.json`
- `evidence-2026-10-25-core2-concurrent-4x120-prealloc-confirm-pass-b.json`
- `evidence-2026-10-25-core2-hli-preallocation-latency.json`
- `evidence-2026-10-25-core2-concurrent-3x120-peer-timeout-fail.json`
- `evidence-2026-10-25-core2-concurrent-3x120-scan120-threshold-fail.json`
- `evidence-2026-10-25-core2-concurrent-3x120-pass-a.json`
- `evidence-2026-10-25-core2-concurrent-3x120-confirm-pass-b.json`

The historical failure is retained. Two instances pass `8/8`; two independent
three-instance runs pass `6/6`. The fixed `40s` peer scan budget and the
three-instance PSRAM sweep calibration failure are also retained. The final
scope remains the bound stock firmware/ELF/QEMU and current hook ABI; it does
not claim more than three instances, physical controller timing or RF.

`run_service_teardown.py` exercises process-stop ordering rather than another
hold. It creates a ready Core2 session, captures pre-stop frame/QOM/network/
peer/pcap evidence while the BLE peer is still active, deletes the session,
and verifies state, companion termination, PID reaping and worker-lease
release. The next attempt must create a new QEMU session successfully:

```bash
python3 run_service_teardown.py \
  --image /path/to/unified-core2.bin \
  --elf /path/to/matching/micropython.elf \
  --qemu /path/to/qemu-system-xtensa \
  --attempts 3 \
  --linger-seconds 120 \
  --out-dir /tmp/m5-core2-active-stop-recovery
```

The committed `3/3` evidence is
`evidence-2026-10-25-core2-active-stop-recovery-3x.json`. This closes the
active-stop companion/QEMU cleanup gate; it does not establish controller,
physical cache/PSRAM, throughput, cross-host or hardware equivalence.

`--hold-seconds` keeps each lease running after network evidence and checks
session stability during the hold. The failed attempt is retained even when
READY, network collection or evidence retrieval raises an error; the aggregate
JSON must be `FAIL`, not a traceback-only partial run. The historical failure
record is `evidence-2026-10-24-extended-run-fail.json`:

- one request for 10 attempts with 10-second holds passed attempts 1-3, then
  attempt 4 failed before READY with `InstrFetchProhibited` and `PC=0`;
- a separate one-attempt hold run passed READY, WiFi/public network and BLE
  connection, then panicked first with `IllegalInstruction` at
  `semphr_give_wrapper` (`components/bt/controller/esp32/bt.c:677`) and
  rebooted into `InstrFetchProhibited` at `PC=0`;
- the peer reached connect and later timed out in GATT discovery or
  notification. The failure is therefore after the network layer and around
  controller-task/BLE lifecycle or teardown, not a WiFi/DNS result.

The follow-up fix has two parts:

- restore `LBEG/LEND/LCOUNT/SAR/BR/LITBASE/SCOMPARE1/ACCLO/ACCHI/M0-M3/
  THREADPTR/ATOMCTL/CPENABLE` around nested guest calls;
- defer HLI allocator/callback injection until the target vCPU is
  halted/idle, so guest code is not re-entered from a cache-disabled WiFi or
  controller execution context.

The intermediate special-register-only build passed 4/5 and still hit a
WiFi `Cache error`; the halted-gate build then passed two independent
5-attempt, 10-second-hold batches, `10/10` total. The earlier failure remains
tracked as history. A further `3×60s` run passed `3/3`, and `2×120s` passed
`2/2`, including the normal BLE peer-close tail; `last-error=3` is accepted
only when `peer-closed>0`, while every HLI error must remain zero. This closes
the short/two-minute virtual extended-run gate and the final bounded two-hour
host-memory gate, not physical cache/PSRAM equivalence, 121 reconnect cycles
or hardware. The old unbounded RSS-growth object is attributed to the TCG
translation buffer; the `tb-size=128` rerun stayed below its start RSS and
physical footprint.

The runner now also sets `network.ble_linger_seconds` to
`max(20, hold_seconds + 60)`. Keeping the peer connected through the full
hold produced two active-BLE `600s` PASS runs with `peer-closed=0`,
`tx-queue-depth=0` and `last-error=0`; both still passed frame/QOM, WiFi,
public DNS/HTTP, external NUS GATT, pcap and evidence.

`--ble-reconnect-cycles N` asks the same external BLE peer process to perform
`N` complete scan/connect/NUS/write/notify/disconnect cycles in one guest.
For `N=10`, three independent stock-firmware leases now pass; the earlier
`N=5` baseline remains in
`evidence-2026-10-24-hci4-reconnect5-3x.json`, and the original `N=2`
baseline remains in
`evidence-2026-10-24-hci4-reconnect2-3x.json`. The historical
failure was not in QEMU HLI, NimBLE connection state or QEMU packet ordering:
the Bumble compatibility layer incorrectly returned Command Status for the
no-response `HCI_Host_Number_of_Completed_Packets (0x0c35)` command. Its stale
ACK was consumed by the next `LE Set Advertising Data` command and produced
`BLE_HS_ECONTROLLER (12)`. The earlier ten-cycle evidence is
`evidence-2026-10-24-hci4-reconnect10-3x.json`; the current twenty-cycle
evidence is `evidence-2026-10-24-hci4-reconnect20-3x.json`, and the
thirty-cycle evidence is
`evidence-2026-10-24-hci4-reconnect30-3x.json`; the sixty-cycle evidence is
`evidence-2026-10-24-hci4-reconnect60-3x.json`; the 120-cycle evidence is
`evidence-2026-10-24-hci4-reconnect120-3x.json`. The contract range is now
1-121 cycles and 122 is rejected; three independent leases at 120 cycles each
pass. The first 121-cycle attempt stopped after 29 completed cycles because
the runner and service still shared a fixed 180-second readiness budget; the
guest had no panic and cycle 30 had started. They now use the same
workload-aware timeout. A later reconnect-only run exposed accelerator sampling
only inside the hold loop; after moving that sample to first-running state,
three independent artifact-bound 121-cycle leases pass.
The replacement artifact-bound two-hour hold passes the functional gate with
HLI `45/45`, zero errors/queues/dropped packets and unchanged launch assets.
The final `tb-size=128` rerun binds launch assets and tools, then passes
`240` host-resource samples with RSS `323536→252992 KiB` and phys footprint
`250880→188416 KiB`. The next execution gates are 121 cycles, throughput and
physical cache/PSRAM equivalence.
The fix is covered by
`platform/tests/test_ble_probe.py`; failure history remains in
`evidence-2026-10-24-reconnect2-fail.json`. The first ten-cycle attempt
exposed a separate service wait bug: a 30-second cap terminated the valid
peer workload after cycle 6 started. That failure is retained in
`evidence-2026-10-24-hci4-reconnect10-timeout-fail.json`; the wait now uses
the session ready timeout and has a regression test in
`platform/tests/test_device_service.py`.
The first 121-cycle attempt exposed that a fixed session timeout is still not
enough for the maximum reconnect workload. Its failure remains in
`evidence-2026-10-25-hci4-reconnect121-readiness-timeout-1x.json`; both
layers now use `reconnect_workload_timeout_seconds()` and the failure was
classified as a readiness-budget mismatch, not a controller failure.
The next reconnect-only run passed `121/121` functional checks but showed
`qemu_accelerator=null` because the old sampler was reachable only inside the
hold loop. The runner now samples after first `running`; the final single
lease passes `bounded_tcg_cache` and every other required check:
`evidence-2026-10-25-hci4-reconnect121-1x.json`. Two additional leases then
complete the same gate; aggregate evidence is
`evidence-2026-10-25-hci4-reconnect121-3x.json`.

After the external Bumble peer closes, the stock firmware can continue issuing
HCI commands until a native-HCI queue fills. The runner therefore also accepts
`last-error=2` (`QUEUE_FULL`) only when `peer-closed>0` and either
`dropped-packets>0` (RX) or `tx-queue-depth>0` (TX); HLI errors, HLI/meta
queue depth and queue-full without peer teardown remain failures.

`core2-native-hci` requires the stock internal-controller app built from
`build-M5STACK_Core2`. Do not compose this profile from
`build-M5STACK_Core2-hciuart3`; that image expects UART HCI-offload and fails
with NimBLE `HCI wait for ack returned 19`. Build the stock unified image with:

```bash
python3 tests/uiflow2/unified_core2/make_image.py \
  --base platform/.cache/firmware/core2/uiflow2.bin \
  --build-dir .work/uiflow-core2-2.5.3/m5stack/build-M5STACK_Core2 \
  --littlefs .work/uiflow-core2-2.5.3/tools/littlefs/prebuilt/littlefs2 \
  --out /tmp/core2-native-hci-unified.bin
```
