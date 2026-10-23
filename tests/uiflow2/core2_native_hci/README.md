# Core2 native HCI transport

Last reviewed: `2026-10-24`

This targeted test validates the first QEMU-side slice of `CORE2-01`: the
`esp32-native-hci` chardev frontend frames controller-to-host H4 packets,
keeps a bounded receive queue, and exposes observable QOM counters.

The first test is transport-only. The second targeted test captures real guest
H2C and, with `--enable-c2h`, delivers one controller event through the
firmware's registered VHCI receive callback. It does not execute a Bluetooth
controller/baseband or prove a complete GATT sequence.

| Stage | Status | Evidence |
| --- | --- | --- |
| `HCI-1` host transport | `PASS` | `evidence-2026-10-24-transport-pass.json` |
| `HCI-2` guest H2C | `PARTIAL` | `evidence-2026-10-24-guest-h2c.json`; first Reset only |
| `HCI-3a` guest C2H callback | `DIAGNOSTIC PASS` | `evidence-2026-10-24-c2h-delivery.json` and `evidence-2026-10-24-c2h-delivery-5x.json`; Reset Complete then next H2C. This narrow callback route is not the production C2H backend |
| `HCI-3b` complete HCI/GATT | `OPEN` / diagnostic `FAIL` | Internal-controller relay resets after the second ATT request. The API-boundary audit reaches GATT discovery and subscription but stalls in the final write/notify transaction |
| `HCI-4` repeated lease | `OPEN` | Still provided by the GDB diagnostic bridge at `1/2` |

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

The current diagnostic fails at `HCI-3b`. The peer finds and connects to the
advertiser, the first ATT request/response exchange crosses both directions,
and the second ATT request reaches QEMU. The guest then logs
`HCI process ack returned 12`, sends HCI Reset again, and service discovery
times out.

Evidence:
`evidence-2026-10-24-hci3b-diagnostic.json`.

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

The next implementation must make H2C send, matching C2H delivery,
`notify_host_recv`, and `notify_host_send_available` one explicit transaction.
It cannot depend on nested guest `cpu_exec()` timing or an idle safe point.
