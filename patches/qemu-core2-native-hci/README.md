# QEMU classic ESP32 native HCI transport

Last reviewed: `2026-10-24`

This patch adds the first QEMU-side slice of `CORE2-01`:

- `esp32-native-hci`, a user-creatable QEMU device;
- chardev-backed H4 command/event/ACL/SCO framing;
- bounded RX/TX queues;
- peer open/close, byte/packet, malformed, dropped and last-error counters;
- reset and shutdown cleanup;
- a C helper for future H2C submission through the same transport;
- optional `env-pointer-address=<ELF-symbol>` polling of the real VHCI H2C
  buffer/length fields.
- optional `c2h-allocator-address=<ELF-symbol>` and `c2h-scratch-size` guest
  buffer allocation for controller-to-host packet delivery;
- registered VHCI `notify_host_recv` and send-available invocation from a
  vCPU-safe QEMU work item, with QOM delivery/status/error counters.
- firmware HLI queue/meta-queue injection with `INTSET[29]`, guest
  `ble_transport_alloc_evt(0)` event buffers and event-13 callback delivery
  from the firmware controller task.

The optional poller captures guest H2C packets from real VHCI shared memory
without GDB. `HCI-3a` now delivers a controller event through the firmware's
registered receive callback and verifies the guest emits its next H2C command.
The HLI event test delivers a pool-allocated HCI Reset Complete through
`ble_transport_to_hs_evt_impl`; the guest advances from `01030c00` to
`01011000` in 5/5 runs.
Complete Bumble initialization/GATT is still open as `HCI-3b`; see
[the native HCI design](../../docs/core2-native-hci-backend.md).

Apply after `patches/qemu-core2-ble-controller/`:

```bash
git apply /path/to/patches/qemu-core2-native-hci/0001-esp32-native-hci-transport.patch
git apply /path/to/patches/qemu-core2-native-hci/0002-esp32-native-hci-hli-event.patch
ninja -C build qemu-system-xtensa
python3 tests/uiflow2/core2_native_hci/test_transport.py
python3 tests/uiflow2/core2_native_hci/test_guest_h2c.py \
  --image /path/to/stock/core2-uiflow2.bin --enable-c2h
python3 tests/uiflow2/core2_native_hci/test_hli_event.py \
  --image /path/to/stock/core2-uiflow2.bin
```

The evidence for the transport-only slice is
`tests/uiflow2/core2_native_hci/evidence-2026-10-24-transport-pass.json`.
The C2H callback evidence is
`tests/uiflow2/core2_native_hci/evidence-2026-10-24-c2h-delivery.json`.
The HLI real-event evidence is
`tests/uiflow2/core2_native_hci/evidence-2026-10-24-hli-event-5x.json`.
Neither is a complete guest BLE or bit-exact controller PASS.
