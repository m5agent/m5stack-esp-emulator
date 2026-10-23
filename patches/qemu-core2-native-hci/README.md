# QEMU classic ESP32 native HCI transport

Last reviewed: `2026-10-24`

This patch adds the first QEMU-side slice of `CORE2-01`:

- `esp32-native-hci`, a user-creatable QEMU device;
- chardev-backed H4 command/event/ACL/SCO framing;
- bounded RX/TX queues;
- peer open/close, byte/packet, malformed, dropped and last-error counters;
- reset and shutdown cleanup;
- a C helper for future H2C submission through the same transport.

It intentionally does not touch classic ESP32 VHCI shared memory, raise a
guest interrupt or call `notify_host_recv`. Guest H2C/VHCI integration is
HCI-2/HCI-3 in [the native HCI design](../../docs/core2-native-hci-backend.md).

Apply after `patches/qemu-core2-ble-controller/`:

```bash
git apply /path/to/patches/qemu-core2-native-hci/0001-esp32-native-hci-transport.patch
ninja -C build qemu-system-xtensa
python3 tests/uiflow2/core2_native_hci/test_transport.py
```

The evidence for the transport-only slice is
`tests/uiflow2/core2_native_hci/evidence-2026-10-24-transport-pass.json`.
It is not a guest BLE or controller PASS.
