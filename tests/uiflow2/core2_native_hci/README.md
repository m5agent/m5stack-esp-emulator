# Core2 native HCI transport

Last reviewed: `2026-10-24`

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
| `CORE2-02` same-guest reconnect | `PASS` | `evidence-2026-10-24-hci4-reconnect20-3x.json`; three independent stock-firmware leases complete twenty full NUS GATT cycles each. Every lease balances HLI 577/577, delivers 397 events and 180 ACLs, leaves HLI/meta queues empty and returns the connection/L2CAP/GATT pools to their 3/9/3 free baseline. The earlier ten-cycle evidence remains as `evidence-2026-10-24-hci4-reconnect10-3x.json`; the forbidden Bumble Command Status for no-response opcode `0x0c35` was the historical stale-ACK root cause |
| `CORE2-02` 30-cycle reconnect | `PASS` | `evidence-2026-10-24-hci4-reconnect30-3x.json`; three independent stock-firmware leases complete thirty full NUS GATT cycles each. Every lease balances HLI 857/857, delivers 587 events and 270 ACLs, with zero errors, empty queues and connection/L2CAP/GATT pools back at 3/9/3 |

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
the current short/two-minute virtual extended-run gate, not physical
cache/PSRAM equivalence, more than thirty reconnect cycles, multi-hour coexistence
or hardware.

The runner now also sets `network.ble_linger_seconds` to
`max(20, hold_seconds + 60)`. Keeping the peer connected through the full
hold produced two active-BLE `120s` PASS runs with `peer-closed=0`,
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
`evidence-2026-10-24-hci4-reconnect30-3x.json`. The accepted range is 1-30
cycles and 31 is rejected; three independent leases at 30 cycles each now
pass. The next execution gate is more than thirty cycles and multi-hour
coexistence. The fix is covered by
`platform/tests/test_ble_probe.py`; failure history remains in
`evidence-2026-10-24-reconnect2-fail.json`. The first ten-cycle attempt
exposed a separate service wait bug: a 30-second cap terminated the valid
peer workload after cycle 6 started. That failure is retained in
`evidence-2026-10-24-hci4-reconnect10-timeout-fail.json`; the wait now uses
the session ready timeout and has a regression test in
`platform/tests/test_device_service.py`.

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
