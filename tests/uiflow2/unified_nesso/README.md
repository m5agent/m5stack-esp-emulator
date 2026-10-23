# Nesso N1 unified QEMU runtime

This probe runs the Nesso N1 135x240 ST7789 display and touch, PI4IOE power
rails and button input, BQ27220 gauge, AW32001 charger status, BMI270,
SX1262 LoRa loopback, GPIO9 NEC IR, GPIO11 buzzer, QEMU ESP32-C6 WiFi
scan/association/DHCP/HTTP and UART1 HCI BLE in one ESP32-C6 QEMU guest.

The network lane uses the repository's open virtual AP and QEMU user networking.
BLE is an HCI-offload path to Bumble, not a native C6 controller/radio claim.

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

Build and run:

```bash
PYTHONPATH=.work/py python3 tests/uiflow2/unified_nesso/make_image.py \
  --base platform/.cache/firmware/nesso-n1/uiflow2.bin \
  --build-dir .work/uiflow-core2-2.5.3/m5stack/build-Nesso_N1-hciuart \
  --out /tmp/m5-nesso-unified.bin

PYTHONPATH=.work/py python3 tests/uiflow2/unified_nesso/run_test.py \
  --image /tmp/m5-nesso-unified.bin \
  --out-dir /tmp/m5-nesso-unified
```
