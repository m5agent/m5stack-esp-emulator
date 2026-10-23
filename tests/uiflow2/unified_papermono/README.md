# PaperMono unified runtime probe

This probe runs the PaperMono 480x800 four-gray e-paper, FT6336 touch,
GPIO keys, M5PM1/IP2315 power path, RGB LED, BMI270, RX8130 RTC,
GPIO42 speaker, WiFi scan/association/DHCP/HTTP and `BLEUARTServer` in one
UIFlow2 guest.

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

GPIO32/33 are free of the e-paper SPI, shared I2C, touch interrupt, keys,
speaker and PDM microphone pins. The audit serial console uses UART0 on
GPIO43/44.

Run one unified QEMU guest and external BLE peer:

```bash
PYTHONPATH=.work/py python3 \
  tests/uiflow2/unified_papermono/make_image.py \
  --base platform/.cache/firmware/papermono/uiflow2.bin \
  --build-dir .work/uiflow-core2-2.5.3/m5stack/build-M5STACK_PaperMono-hciuart \
  --out /tmp/papermono-unified.bin
PYTHONPATH=.work/py python3 \
  tests/uiflow2/unified_papermono/run_test.py \
  --image /tmp/papermono-unified.bin \
  --out-dir /tmp/m5-papermono-unified
```

The controlled HTTP fixture listens on host port `18086`. The runner injects
an IP2315 charging state before boot, then QMP touch and key events after the
WiFi/BLE exchange. The unified result is simulation-only evidence.
