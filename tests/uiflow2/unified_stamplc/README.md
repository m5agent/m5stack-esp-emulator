# StamPLC unified runtime probe

This probe runs the StamPLC ST7789 240x135 display, PI4IOE keys/RGB,
AW9523 relay/input banks, INA226, LM75, RX8130 RTC, TWAI CAN, PWR-485,
the G44 buzzer, WiFi and `BLEUARTServer` in one UIFlow2 guest.

It is simulation-only. WiFi uses the QEMU ESP32-S3 MAC/DMA model and an open
virtual AP on one fixed channel. BLE uses UART1 HCI-offload to an external
Bumble controller/peer. UART2 remains dedicated to PWR-485 on G0/G39/G46.

HCI-UART build configuration:

```text
CONFIG_BT_CONTROLLER_DISABLED=y
CONFIG_BT_NIMBLE_TRANSPORT_UART=y
CONFIG_BT_NIMBLE_TRANSPORT_UART_PORT=1
CONFIG_BT_NIMBLE_UART_RX_PIN=40
CONFIG_BT_NIMBLE_UART_TX_PIN=41
CONFIG_BT_NIMBLE_HCI_UART_BAUDRATE=921600
CONFIG_BT_NIMBLE_HCI_UART_FLOW_CTRL=0
```

G40/G41 are the custom pins on the publicly documented StamPLC-Bus. They do
not overlap the board's I2C, SPI, CAN, RS-485, buzzer, LCD, RTC or key pins.

Build the image:

```bash
PYTHONPATH=.work/py python3 \
  tests/uiflow2/unified_stamplc/make_image.py \
  --base platform/.cache/firmware/stamplc/uiflow2.bin \
  --build-dir .work/uiflow-core2-2.5.3/m5stack/build-M5STACK_StamPLC-hciuart \
  --out /tmp/stamplc-unified.bin
```

Run one unified QEMU guest and external BLE peer:

```bash
PYTHONPATH=.work/py python3 \
  tests/uiflow2/unified_stamplc/run_test.py \
  --image /tmp/stamplc-unified.bin \
  --out-dir /tmp/m5-stamplc-unified
```

The controlled HTTP fixture listens on host port `18088`. The runner enables
the CAN and PWR-485 peers, pauses the guest after board setup to inject LM75,
INA226, AW9523 and RX8130 state, then tests key input after readiness.
`evidence-2026-10-23.json` records three consecutive PASS runs. The result is
simulation-only evidence.
