# CoreS3 unified runtime probe

This probe runs the CoreS3 display, touch, AXP2101 power, BMI270 IMU,
AW88298 speaker, WiFi scan/association/DHCP/HTTP and
`BLEUARTServer` in one UIFlow2 guest.

It is simulation-only. WiFi uses the QEMU ESP32-S3 MAC/DMA model and an open
virtual AP on one fixed channel. BLE requires an HCI-UART UIFlow2 test build
and an external Bumble controller/peer.

The required test image is a 16 MiB CoreS3 UIFlow2 image whose internal BT
controller is disabled and whose NimBLE host uses UART1 H4:

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
  tests/uiflow2/unified_cores3/run_test.py \
  --image /path/to/cores3-unified.bin \
  --out-dir /tmp/m5-cores3-unified
```

The controlled HTTP fixture listens on host port `18081`; StickS3 remains on
`18080`, so both unified device probes can run concurrently.
