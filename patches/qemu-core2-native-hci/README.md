# QEMU classic ESP32 native HCI transport

Last reviewed: `2026-10-25`

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
- `0003` adds API-boundary H2C ownership, HLI ACL mbuf delivery, controller
  work-item wake semantics and optional protocol-stack tracing.
- `0004` ends a translated block after `rsr.ccount` so tightly polling Core2
  guests observe the virtual clock advancing.
- `0005` restores caller-saved Xtensa special registers around QEMU guest
  calls and defers HLI allocator/callback injection until the target vCPU is
  halted/idle, preventing nested guest execution from a cache-disabled WiFi
  or controller context.
- `0006` adds opt-in H4 packet tracing, HCI command/reset/advertising trace
  counters, HLI deferred-delivery counters and connection/L2CAP/GATT pool
  counters. Packet tracing is enabled only by
  `M5_CORE2_HCI_PACKET_TRACE=1`.
- `0007` schedules HLI delivery only after the latest guest-queue observation
  succeeded. Before this gate, a no-stagger `4x120s` run balanced all
  `45/45` HLI packets but still recorded three invalid scheduling attempts;
  the gate removes the counter errors without suppressing the health signal.
- `0008` keeps two guest HCI-event buffers and two guest ACL mbufs
  preallocated while CPU0 is idle. If CPU0 is busy, QEMU fills those real
  guest objects and queues the inherited HLI descriptor without nesting guest
  calls. This prevents an ACL FIFO head from delaying a Command Status/LE Meta
  event beyond NimBLE's two-second command-ack budget.
- `0009` expands that real-guest reserve to eight HCI-event buffers and four
  ACL mbufs. Four simultaneous cold starts consumed the two-packet reserve
  before CPU0 reached another idle point, so later Command Complete events
  waited behind NimBLE's two-second HCI ACK budget. The larger reserve covers
  the startup burst without synthesizing ACKs or nesting guest calls. Two
  independent four-instance `4x120s` batches then pass `4/4` each (`8/8`).
- `0010` adds opt-in ACK-state tracing at `ble_hs_hci_rx_evt`, its
  semaphore-count branch, and the HCI context's `hci_ack` pointer. It changes
  no default runtime behavior and is enabled only with
  `M5_CORE2_HCI_PACKET_TRACE=1`. The new evidence shows that zero-stagger
  five-instance failures begin with HLI response readiness/delivery ordering,
  not an initially stale ACK pointer/semaphore state or physical
  PSRAM/cache fault. The measured `4.506306s` is a host-trace timestamp
  delta, not guest virtual time.

The optional poller captures guest H2C packets from real VHCI shared memory
without GDB. `HCI-3a` now delivers a controller event through the firmware's
registered receive callback and verifies the guest emits its next H2C command.
The HLI event test delivers a pool-allocated HCI Reset Complete through
`ble_transport_to_hs_evt_impl`; the guest advances from `01030c00` to
`01011000` in 5/5 runs.
`HCI-3b` now completes external NUS GATT in 5/5 runs. The previous timeout
used a 21-byte probe whose ATT PDU is 24 bytes, exceeding the default 23-byte
MTU. The default 15-byte probe produces a 17-byte PDU and reaches ATT, the
Python write/notify path and the Bumble ACK. See
[the native HCI design](../../docs/core2-native-hci-backend.md).
`HCI-4` runs the same path through five independent Device Service
`core2-native-hci` leases, with frame/QOM/WiFi/public-network/NUS-GATT/pcap
evidence and no GDB bridge. The extended-run gate adds a 10-second stable hold
and requires `hli-errors=0`, balanced posts/consumption, zero queue depth and
nonzero event/ACL delivery in every lease.

Current extended validation for this patch set:

- two independent active-BLE `600s` leases pass `2/2`;
- one artifact-bound active-BLE `7200s` lease passes the functional,
  bounded-TCG, HLI-health, pcap and cleanup gate;
- three independent artifact-bound `121`-cycle reconnect leases pass `3/3`
  with identical firmware/ELF/QEMU/tool hashes.
- one no-stagger `4x120s` concurrent run with `0007` passes `4/4` and records
  `hli-errors=0`; an independent confirmation run still hits the original
  no-stagger guest `LoadProhibited` at `ble_hs_hci_process_ack`, so the gate
  is a local HLI scheduling fix rather than a concurrent cold-start closure.
- with `0008`, two independent no-stagger `4x120s` gates pass `4/4` each
  (`8/8` total). Every lease records the real fast path for all 36 events
  and 9 ACLs, two spare objects of each type, `hli-errors=0`, balanced
  `45/45` delivery and no scheduler reset or panic.
- after extending to three simultaneous leases, two independent `3x120s`
  gates pass `3/3` each (`6/6` total). The first failures were harness
  calibration, not a controller data-plane regression: a fixed 40-second
  BLE peer scan window expired before guest initialization, then a
  30-sweep floor was one above the observed three-instance rate. Peer scan
  now follows session readiness within 40-120 seconds and sustained PSRAM
  uses a conservative `hold/5` floor.
- with the expanded `0009` reserve, two independent four-instance `4x120s`
  gates pass `4/4` each (`8/8` total). Every lease accepts the real network
  and GATT lifecycle, records HLI `45/45`, 36 events / 9 ACLs, ends with
  `8/4` spare guest objects, and has no HCI error, scheduler reset or panic.
  One first-batch lease records two transient refill failures before the pool
  reaches its target; the follow-up health checks and the independent
  confirmation batch still complete. This covers four simultaneous cold
  starts, not unbounded concurrency or physical controller equivalence.
  The `0009` source build also passes the Core2 six-case UIFlow2 peripheral
  group `6/6` with `24/24` checks, one attempt per case and no retry.

The detailed gate and evidence index remain in
[`docs/core2-native-hci-backend.md`](../../docs/core2-native-hci-backend.md).
These are virtual-device functional results, not physical cache/PSRAM,
bit-exact controller/baseband or hardware validation.

Apply after `patches/qemu-core2-ble-controller/`:

```bash
git apply /path/to/patches/qemu-core2-native-hci/0001-esp32-native-hci-transport.patch
git apply /path/to/patches/qemu-core2-native-hci/0002-esp32-native-hci-hli-event.patch
git apply /path/to/patches/qemu-core2-native-hci/0003-esp32-native-hci-api-transaction.patch
git apply /path/to/patches/qemu-core2-native-hci/0004-xtensa-ccount-tb-yield.patch
git apply /path/to/patches/qemu-core2-native-hci/0005-esp32-native-hci-guest-call-sregs.patch
git apply /path/to/patches/qemu-core2-native-hci/0006-esp32-native-hci-observability.patch
git apply /path/to/patches/qemu-core2-native-hci/0007-esp32-native-hci-require-valid-guest-queue.patch
git apply /path/to/patches/qemu-core2-native-hci/0008-esp32-native-hci-preallocate-hli-objects.patch
git apply /path/to/patches/qemu-core2-native-hci/0009-esp32-native-hci-expand-hli-preallocation.patch
git apply /path/to/patches/qemu-core2-native-hci/0010-esp32-native-hci-ack-observability.patch
ninja -C build qemu-system-xtensa
python3 tests/uiflow2/core2_native_hci/test_transport.py
python3 tests/uiflow2/core2_native_hci/test_guest_h2c.py \
  --image /path/to/stock/core2-uiflow2.bin --enable-c2h
python3 tests/uiflow2/core2_native_hci/test_hli_event.py \
  --image /path/to/stock/core2-uiflow2.bin
PYTHONPATH=.work/py python3 tests/uiflow2/core2_native_hci/run_full.py \
  --image /path/to/stock/core2-uiflow2.bin \
  --elf /path/to/matching/micropython.elf \
  --hli-c2h
python3 tests/uiflow2/core2_native_hci/run_service_5x.py \
  --image /path/to/unified/core2-uiflow2.bin \
  --elf /path/to/matching/micropython.elf \
  --qemu build/qemu-system-xtensa \
  --attempts 5 \
  --hold-seconds 10 \
  --out-dir /tmp/m5-core2-native-hci-service-5x
```

The evidence for the transport-only slice is
`tests/uiflow2/core2_native_hci/evidence-2026-10-24-transport-pass.json`.
The C2H callback evidence is
`tests/uiflow2/core2_native_hci/evidence-2026-10-24-c2h-delivery.json`.
The HLI real-event evidence is
`tests/uiflow2/core2_native_hci/evidence-2026-10-24-hli-event-5x.json`.
The full HLI/API-boundary GATT evidence is
`tests/uiflow2/core2_native_hci/evidence-2026-10-24-hli-api-gatt-5x.json`.
The Device Service repeated-lease evidence is
`tests/uiflow2/core2_native_hci/evidence-2026-10-24-hci4-service-5x.json`.
The ten-cycle reconnect evidence is
`tests/uiflow2/core2_native_hci/evidence-2026-10-24-hci4-reconnect10-3x.json`;
it records three independent leases with 297/297 balanced HLI posts and
consumption, 207 events, 90 ACLs, empty HLI/meta queues and connection,
L2CAP and GATT pools back at their `3/9/3` free baseline. The first
ten-cycle attempt is retained in
`evidence-2026-10-24-hci4-reconnect10-timeout-fail.json`; it exposed a
Device Service 30-second peer-completion wait cap, not a controller failure.
The extended-run pass evidence is
`tests/uiflow2/core2_native_hci/evidence-2026-10-24-hci4-halted-gate-5x.json`;
the preceding identical-build confirmation batch is
`tests/uiflow2/core2_native_hci/evidence-2026-10-24-hci4-halted-gate-confirm-5x.json`;
the longer three-by-60-second hold evidence is
`tests/uiflow2/core2_native_hci/evidence-2026-10-24-hci4-hold60-3x.json`;
the earlier failure is retained as
`tests/uiflow2/core2_native_hci/evidence-2026-10-24-extended-run-fail.json`.
The earlier notification-fail evidence is retained as the negative case that
identified the default-MTU probe-size error. These are virtual-device results,
not bit-exact controller or physical hardware validation.
