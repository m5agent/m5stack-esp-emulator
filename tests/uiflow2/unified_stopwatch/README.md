# StopWatch unified runtime probe

This probe runs the StopWatch 466x466 display, touch, M5PM1 power,
M5IOE1 G10 amplifier enable, BMI270 IMU, ES8311/AW8737A speaker, WiFi
scan/association/DHCP/HTTP and `BLEUARTServer` in one UIFlow2 guest.

It is simulation-only. WiFi uses the QEMU ESP32-S3 MAC/DMA model and an open
virtual AP on one fixed channel. BLE requires an HCI-UART UIFlow2 test build
and an external Bumble controller/peer.

Required HCI-UART configuration:

```text
CONFIG_BT_CONTROLLER_DISABLED=y
CONFIG_BT_NIMBLE_TRANSPORT_UART=y
CONFIG_BT_NIMBLE_TRANSPORT_UART_PORT=1
CONFIG_BT_NIMBLE_UART_RX_PIN=32
CONFIG_BT_NIMBLE_UART_TX_PIN=33
CONFIG_BT_NIMBLE_HCI_UART_BAUDRATE=921600
CONFIG_BT_NIMBLE_HCI_UART_FLOW_CTRL=0
```

Run one unified QEMU guest and external BLE peer:

```bash
PYTHONPATH=.work/py python3 \
  tests/uiflow2/unified_stopwatch/run_test.py \
  --image /path/to/stopwatch-unified.bin \
  --out-dir /tmp/m5-stopwatch-unified
```

The controlled HTTP fixture listens on host port `18083`.
