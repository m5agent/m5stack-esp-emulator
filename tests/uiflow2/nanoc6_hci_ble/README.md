# NanoC6 board + HCI BLE QEMU probe

This probe runs the NanoC6 GPIO9 button, GPIO7 blue LED, GPIO19/20 WS2812,
GPIO3 IR output, QEMU ESP32-C6 WiFi scan/association/DHCP/HTTP and UART1 HCI
BLE in one ESP32-C6 QEMU guest.

Official board mapping used here:

- GPIO9 active-low button;
- GPIO7 blue LED;
- GPIO19 RGB power enable and GPIO20 WS2812 data;
- GPIO3 IR LED;
- UART0 GPIO16/17 testpoints are used by the test build for UART1 HCI routing.

The controlled BLE peer is Bumble. The result is simulation-only.
The HTTP endpoint is a controlled host peer reached through QEMU SLiRP.

Build configuration:

```text
CONFIG_BT_CONTROLLER_DISABLED=y
CONFIG_BT_NIMBLE_TRANSPORT_UART=y
CONFIG_BT_NIMBLE_TRANSPORT_UART_PORT=1
CONFIG_BT_NIMBLE_UART_RX_PIN=16
CONFIG_BT_NIMBLE_UART_TX_PIN=17
CONFIG_BT_NIMBLE_HCI_UART_BAUDRATE=921600
CONFIG_BT_NIMBLE_HCI_UART_FLOW_CTRL=0
```

The C6 UART differs from C3: `RX_TOUT_EN` and `RX_TOUT_THRHD` live in
`UART_TOUT_CONF` at `0x64`, while `CONF1` contains only FIFO thresholds.
Inheriting the C3 layout left six-byte HCI replies in the hardware FIFO without
an RX-timeout interrupt, so the host repeatedly sent HCI Reset. The C6 model
now implements its own `CONF1`, `CONF0_SYNC` FIFO reset, `MEM_CONF` and
`TOUT_CONF` register behavior.

Build and run:

```bash
PYTHONPATH=.work/py python3 tests/uiflow2/nanoc6_hci_ble/make_image.py \
  --base platform/.cache/firmware/nanoc6/uiflow2.bin \
  --build-dir .work/uiflow-core2-2.5.3/m5stack/build-M5STACK_NanoC6-hciuart \
  --out /tmp/m5-nanoc6-hci-ble.bin

PYTHONPATH=.work/py python3 tests/uiflow2/nanoc6_hci_ble/run_test.py \
  --image /tmp/m5-nanoc6-hci-ble.bin \
  --out-dir /tmp/m5-nanoc6-hci-ble
```
