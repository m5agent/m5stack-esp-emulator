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
| `HCI-3a` guest C2H callback | `PASS` | `evidence-2026-10-24-c2h-delivery.json` and `evidence-2026-10-24-c2h-delivery-5x.json`; Reset Complete then next H2C |
| `HCI-3b` complete HCI/GATT | `OPEN` | Bumble may initialize and connect, but the full sequence is not stable |
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

A local C2H experiment invoked the guest `vhci_send` address and made the
function return, but the firmware still timed out waiting for the controller
acknowledgement. That confirms `vhci_send` is not a direct H4 packet-ingest
entry point and the experiment is not part of this patch. The committed path
uses the firmware-observed callback contract and QOM
queued/delivered/error/status counters.
