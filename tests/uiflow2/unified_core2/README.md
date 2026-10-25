# Core2 unified runtime probe

Last reviewed: `2026-10-25`

This probe runs the Core2 320x240 display, touch, AXP2101, INA3221,
MPU6886, PCF8563, NS4168 speaker, SPM1423 microphone, PSRAM allocation/readback,
WiFi, public IPv4 DNS/HTTP and `BLEUARTServer` in one UIFlow2 guest.

It is simulation-only. WiFi uses the QEMU classic ESP32 OpenMAC model and
QEMU user networking. BLE uses UART1 HCI-offload to an external Bumble
controller/peer. This combines the board, WiFi and BLE data planes in the
same `m5core2` process.

Build configuration:

```text
CONFIG_BT_CONTROLLER_DISABLED=y
CONFIG_BT_NIMBLE_TRANSPORT_UART=y
CONFIG_BT_NIMBLE_TRANSPORT_UART_PORT=1
CONFIG_BT_NIMBLE_UART_RX_PIN=32
CONFIG_BT_NIMBLE_UART_TX_PIN=33
CONFIG_BT_NIMBLE_HCI_UART_BAUDRATE=921600
CONFIG_BT_NIMBLE_HCI_UART_FLOW_CTRL=0
```

Build the complete image from the public Core2 base and the existing
`build-M5STACK_Core2-hciuart3` app:

```bash
PYTHONPATH=.work/py python3 \
  tests/uiflow2/unified_core2/make_image.py \
  --base platform/.cache/firmware/core2/uiflow2.bin \
  --build-dir .work/uiflow-core2-2.5.3/m5stack/build-M5STACK_Core2-hciuart3 \
  --littlefs .work/uiflow-core2-2.5.3/tools/littlefs/prebuilt/littlefs2 \
  --out /tmp/core2-unified.bin
```

Run one unified QEMU guest and external BLE peer:

```bash
PYTHONPATH=.work/py python3 \
  tests/uiflow2/unified_core2/run_test.py \
  --image /tmp/core2-unified.bin \
  --out-dir /tmp/m5-core2-unified
```

The controlled HTTP fixture listens on host port `18089`. The runner records
every attempt, but the current evidence uses first attempts with no retries.
The scheduling fix is `tcg,thread=single,tb-size=128` plus
`icount shift=auto,align=off,sleep=off`. QOM values are written while the guest
runs because QMP stop/continue during early board setup reproducibly triggered
an interrupt-watchdog failure.

`evidence-2026-10-23-icount-public.json` records ten independent first-attempt
PASS runs, including public DNS/HTTP. The older
`evidence-2026-10-23.json` remains as pre-mitigation history.

## PSRAM probe

The current probe reads `esp32.idf_heap_info(esp32.HEAP_DATA)`, selects the
largest external heap, allocates a 1 MiB `bytearray`, writes a deterministic
pattern plus a two-byte address tag in every 4 KiB block, checks the initial
buffer and then keeps verifying it after READY. The serial markers are
`UNIFIED_CORE2_PSRAM_ALLOC`, `UNIFIED_CORE2_PSRAM_INIT_PASS`,
`UNIFIED_CORE2_PSRAM_SWEEP`, `UNIFIED_CORE2_PSRAM_STRESS_PASS` and
`UNIFIED_CORE2_STRESS_HEARTBEAT`.

The canonical service gate is opt-in because historical images do not contain
these markers:

```bash
python3 tests/uiflow2/core2_native_hci/run_service_5x.py \
  --image /tmp/core2-native-hci-psram-stress.bin \
  --elf .work/uiflow2-core2-symbols/micropython.elf \
  --qemu .work/M5StopWatch-QEMU/build/qemu/build/qemu-system-xtensa \
  --attempts 3 --hold-seconds 120 --require-psram \
  --out-dir /tmp/m5-core2-psram-gate
```

Three independent 120-second leases from the same firmware passed with a
4 MiB effective external heap, a 1 MiB guest allocation, 35/35/36 sweeps
(106 full-buffer checks), 30 controlled HTTP rechecks, 10 public rechecks and
all board/network/BLE/frame/QOM/pcap checks. A separate 600-second lease
completed 179 sweeps, 51 controlled HTTP rechecks and 18 public rechecks with
active BLE, bounded TCG, frame/QOM, pcap and cleanup still passing. This is sustained virtual PSRAM
data-path validation; the board's physical 8 MiB capacity, cache/PSRAM timing
and hardware remain `NOT RUN`.

BLE in this unified profile remains UART1 HCI-offload to Bumble. Native ESP32
controller advertising enable is proven separately. The
`tests/uiflow2/core2_native_vhci/` runner now keeps the stock
internal-controller build and bridges the real VHCI boundary to Bumble,
reaching external NUS GATT 5/5. The same transport is selectable in this
unified runner, but bit-exact Espressif BT baseband/controller execution
remains `NOT RUN`.

The same runner can instead select the stock native-VHCI transport:

```bash
python3 tests/uiflow2/unified_core2/run_test.py \
  --image /tmp/core2-native-vhci-unified.bin \
  --out-dir /tmp/core2-native-vhci-unified \
  --ble-transport native-vhci \
  --attempts 3 --require-all-attempts
```

This path keeps display/touch, audio, QOM, WiFi, public DNS/HTTP and native
VHCI BLE in one guest and is recorded in
`evidence-2026-10-24-native-vhci-pinned.json` as 3/3 PASS. The runner parses
the matching Xtensa ELF with `xtensa_elf_symbols.py` and passes the three VHCI
addresses as fixed environment values, so GDB no longer performs symbol
lookup. It requires the classic ESP32 BB idle-readback patch.

The GDB path remains available through Device Service as legacy
`qemu-unified/profile=core2-native-vhci`; its service-side run is recorded in
`evidence-2026-10-23-native-vhci-service.json`. GDB still pauses the guest,
invokes firmware callbacks and supplies the synthetic send-frame return.
Repeated-lease stability is currently `1/2`, recorded in
`evidence-2026-10-24-native-vhci-service-stability.json`. The failed lease was
rejected while injecting the C2H Command Complete for `LE Set Event Mask`,
then the guest raised a debug exception and rebooted. Removal of that GDB
control plane is complete in the canonical `core2-native-hci` profile, whose
`HCI-4` evidence is
`tests/uiflow2/core2_native_hci/evidence-2026-10-24-hci4-service-5x.json`.
Use native-HCI for new validation; keep this lane for diagnosis only.

## Reconnect probe boundary

The UIFlow2 test source uses a `BLEUARTServer` subclass that schedules one
test-only re-advertisement 500 ms after disconnect. This behavior exists only
to exercise the second-connect lifecycle; it is not a proposed product fix.

The stock/native-HCI Core2 guest passes 20, 30, 60 and 120 complete cycles in
separate three-lease gates. The 120-cycle gate has HLI 3377/3377, 2297 events,
1080 ACLs and pools back at 3/9/3. Device Service, Bumble and the service
runner accept 1-121 cycles; three independent leases at 120 cycles each pass.
The first 121-cycle run completed 29 cycles and started cycle 30 before a
fixed 180-second readiness budget terminated a healthy session with no panic.
Runner and Device Service now share a workload-aware budget. A replacement
single-lease run passes `121/121` after the runner also moved QEMU accelerator
sampling out of the hold-only path; two more independent leases complete the
`3/3` gate. Both the functional and bounded-TCG two-hour holds pass. The next
required gates are long-run throughput/teardown and physical equivalence. The former
`NimBLE: HCI process ack returned 12` failure came from the external Bumble
compatibility layer returning a forbidden Command Status for the no-response
`HCI_Host_Number_of_Completed_Packets (0x0c35)` command. Removing that reply
allows the next `LE Set Advertising Data`/advertising-enable transaction to
complete normally. Evidence:
`../core2_native_hci/evidence-2026-10-24-hci4-reconnect20-3x.json`; the earlier
ten-cycle milestone is
`../core2_native_hci/evidence-2026-10-24-hci4-reconnect10-3x.json`, the
five-cycle milestone is
`../core2_native_hci/evidence-2026-10-24-hci4-reconnect5-3x.json`, and the
original two-cycle milestone is
`../core2_native_hci/evidence-2026-10-24-hci4-reconnect2-3x.json`; historical
failure: `../core2_native_hci/evidence-2026-10-24-reconnect2-fail.json`.
