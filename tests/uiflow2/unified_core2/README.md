# Core2 unified runtime probe

This probe runs the Core2 320x240 display, touch, AXP2101, INA3221,
MPU6886, PCF8563, NS4168 speaker, SPM1423 microphone, WiFi, public IPv4
DNS/HTTP and `BLEUARTServer` in one UIFlow2 guest.

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
The scheduling fix is `tcg,thread=single` plus
`icount shift=auto,align=off,sleep=off`. QOM values are written while the guest
runs because QMP stop/continue during early board setup reproducibly triggered
an interrupt-watchdog failure.

`evidence-2026-10-23-icount-public.json` records ten independent first-attempt
PASS runs, including public DNS/HTTP. The older
`evidence-2026-10-23.json` remains as pre-mitigation history.

BLE in this unified profile remains UART1 HCI-offload to Bumble. Native ESP32
controller advertising enable is proven separately. The
`tests/uiflow2/core2_native_vhci/` runner now keeps the stock
internal-controller build and bridges the real VHCI boundary to Bumble,
reaching external NUS GATT 5/5. Its GDB bridge is not yet part of this unified
lease, and bit-exact Espressif BT baseband/controller execution remains
`NOT RUN`.

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
`evidence-2026-10-23-native-vhci.json` as 3/3 PASS. It requires the classic
ESP32 BB idle-readback patch and a matching symbol ELF. It remains a
standalone GDB bridge rather than a Device Service profile.
