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

```bash
python3 run_service_5x.py \
  --image /path/to/unified-core2.bin \
  --elf /path/to/matching/micropython.elf \
  --qemu /path/to/qemu-system-xtensa \
  --attempts 5 \
  --out-dir /tmp/m5-core2-native-hci-service-5x
```

The committed evidence is
`evidence-2026-10-24-hci4-service-5x.json`. The profile is supported only
under trusted-host isolation. It is not bit-exact controller, RF, malware
sandbox or physical-hardware validation. The legacy `core2-native-vhci`
profile remains available for diagnosis but is not the canonical path.
