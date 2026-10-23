# Cardputer ADV unified runtime probe

This probe runs the Cardputer ADV display, TCA8418 keyboard, BMI270 IMU,
ES8311/NS4150B speaker, WiFi scan/association/DHCP/HTTP and
`BLEUARTServer` in one UIFlow2 guest.

It is simulation-only. WiFi uses the QEMU ESP32-S3 MAC/DMA model and an open
virtual AP on one fixed channel. BLE requires an HCI-UART UIFlow2 test build
and an external Bumble controller/peer.

The required HCI-UART configuration uses UART1 RX/TX on GPIO15/16. GPIO32/33
are not available because Cardputer ADV uses GPIO33-38 for the display:

```text
CONFIG_BT_CONTROLLER_DISABLED=y
CONFIG_BT_NIMBLE_TRANSPORT_UART=y
CONFIG_BT_NIMBLE_TRANSPORT_UART_PORT=1
CONFIG_BT_NIMBLE_UART_RX_PIN=15
CONFIG_BT_NIMBLE_UART_TX_PIN=16
CONFIG_BT_NIMBLE_HCI_UART_BAUDRATE=921600
CONFIG_BT_NIMBLE_HCI_UART_FLOW_CTRL=0
```

Run one unified QEMU guest and external BLE peer:

```bash
PYTHONPATH=.work/py python3 \
  tests/uiflow2/unified_cardputer/run_test.py \
  --image /path/to/cardputer-adv-unified.bin \
  --out-dir /tmp/m5-cardputer-unified
```

The controlled HTTP fixture listens on host port `18082`.
