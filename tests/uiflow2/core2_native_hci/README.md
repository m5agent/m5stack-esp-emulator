# Core2 native HCI transport

Last reviewed: `2026-10-24`

This targeted test validates the first QEMU-side slice of `CORE2-01`: the
`esp32-native-hci` chardev frontend frames controller-to-host H4 packets,
keeps a bounded receive queue, and exposes observable QOM counters.

It does **not** connect guest VHCI shared memory, deliver C2H packets to a
firmware callback, or execute a Bluetooth controller/baseband. The current
GDB bridge remains the guest-side diagnostic path.

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
