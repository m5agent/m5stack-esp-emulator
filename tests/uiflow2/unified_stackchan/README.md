# StackChan unified runtime probe

This probe runs the StackChan 320x240 ILI9342 display, FT6336 display
touch, Si12T body touch, GC0308 camera, BMI270/BMM150, AXP2101,
AW9523/M5IOE1 RGB, INA226, LTR553, PCF8563-compatible RTC, two SCS
servos, ES7210 microphone, AW88298 speaker, ST25R3916 NFC, NEC IR,
WiFi and `BLEUARTServer` in one UIFlow2 guest.

It is simulation-only. WiFi uses the QEMU ESP32-S3 MAC/DMA model and an open
virtual AP on one fixed channel. BLE requires an HCI-UART UIFlow2 test build
and an external Bumble controller/peer.

Required HCI-UART configuration:

```text
CONFIG_BT_CONTROLLER_DISABLED=y
CONFIG_BT_NIMBLE_TRANSPORT_UART=y
CONFIG_BT_NIMBLE_TRANSPORT_UART_PORT=2
CONFIG_BT_NIMBLE_UART_RX_PIN=31
CONFIG_BT_NIMBLE_UART_TX_PIN=32
CONFIG_BT_NIMBLE_HCI_UART_BAUDRATE=921600
CONFIG_BT_NIMBLE_HCI_UART_FLOW_CTRL=0
```

UART1 GPIO6/7 remains dedicated to the two StackChan SCS servos. UART0
GPIO43/44 carries the audit log. Moving HCI to UART2 avoids the servo bus,
audio I2S WS33, camera DVP D6/D7 on GPIO48/47, and the rest of the board
pin map.

Build the image:

```bash
PYTHONPATH=.work/py python3 \
  tests/uiflow2/unified_stackchan/make_image.py \
  --base platform/.cache/firmware/stackchan/uiflow2.bin \
  --build-dir .work/uiflow-core2-2.5.3/m5stack/build-M5STACK_StackChan-hciuart \
  --out /tmp/stackchan-unified.bin
```

Run one unified QEMU guest and external BLE peer:

```bash
PYTHONPATH=.work/py python3 \
  tests/uiflow2/unified_stackchan/run_test.py \
  --image /tmp/stackchan-unified.bin \
  --out-dir /tmp/m5-stackchan-unified
```

The controlled HTTP fixture listens on host port `18087`. The runner pauses
the guest at the IMU setup marker so QMP can inject sensor values after the
driver's configuration writes, then resumes and injects display touch and
Si12T body-touch state after ready. `evidence-2026-10-23.json` records three
consecutive PASS runs. The result is simulation-only evidence.

QEMU must map ESP32-S3 UART2 to the third serial chardev. The corresponding
incremental patch is `patches/qemu-m5stack-peripherals/0021-esp32s3-uart2-chardev.patch`.
