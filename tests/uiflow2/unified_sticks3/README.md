# StickS3 unified runtime probe

This single UIFlow2 program exercises the StickS3 display, A button, M5PM1
power telemetry, BMI270 IMU, ES8311 speaker, `network.WLAN`, a controlled
HTTP endpoint and `BLEUARTServer` from one guest.

The probe is intentionally simulation-only. The acceptance runner must start
one QEMU process, route UART1 H4 to the external BLE controller, collect
framebuffer and QOM evidence, and record the resulting bundle as `PARTIAL`
until every data plane and the unified Device Service lease pass.

## Required test image

Use a StickS3 UIFlow2 image whose internal BT controller is disabled and whose
NimBLE host uses UART1 H4:

```text
CONFIG_BT_CONTROLLER_DISABLED=y
CONFIG_BT_NIMBLE_TRANSPORT_UART=y
CONFIG_BT_NIMBLE_TRANSPORT_UART_PORT=1
CONFIG_BT_NIMBLE_UART_RX_PIN=32
CONFIG_BT_NIMBLE_UART_TX_PIN=33
CONFIG_BT_NIMBLE_HCI_UART_BAUDRATE=921600
CONFIG_BT_NIMBLE_HCI_UART_FLOW_CTRL=0
```

Preserve the public merged image's NVS, PHY and flash layout, then replace its
bootloader, partition table, app, system filesystem and user filesystem with
the matching local build. The user filesystem must contain these probe files.
The resulting image must remain exactly 8 MiB.

## Run

The runner owns the Bumble controller/peer and a controlled HTTP server on
port `18080`, launches one `m5sticks3` QEMU process with
`misc.esp32s3.wifi`, and writes a hashed evidence bundle:

```bash
PYTHONPATH=.work/py python3 \
  tests/uiflow2/unified_sticks3/run_test.py \
  --image /path/to/sticks3-unified.bin \
  --out-dir /tmp/m5-sticks3-unified
```

The evidence bundle checks display/button redraw, M5PM1 power, BMI270 IMU,
ES8311 speaker PCM and PA state, WiFi scan/association/DHCP, controlled HTTP,
and external BLE NUS discovery/subscription/write/guest-RX/notify.

This is simulation-only evidence. The WiFi model is an open AP on one fixed
virtual channel, and BLE is host-controller HCI over UART1 rather than a
native ESP32-S3 radio/controller model.
