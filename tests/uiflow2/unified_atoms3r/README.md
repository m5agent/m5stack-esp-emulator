# AtomS3R unified runtime probe

This probe runs the AtomS3R 128x128 display, GPIO41 button, BMI270
accelerometer/gyroscope, BMM150 magnetometer, LP5562 RGB PWM, WiFi
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
  tests/uiflow2/unified_atoms3r/run_test.py \
  --image /path/to/atoms3r-unified.bin \
  --out-dir /tmp/m5-atoms3r-unified
```

The controlled HTTP fixture listens on host port `18084`.
