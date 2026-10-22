# Core2 HCI-offload BLE GATT proof

This lane runs the stock Core2 UIFlow2 application base with a test build whose
NimBLE host uses an external HCI controller over UART1. QEMU exposes its real
UART1 FIFO/channel as a TCP chardev. A Bumble controller consumes the H4 byte
stream, and a second Bumble controller/link peer scans, connects, discovers the
NUS service, subscribes, writes, and receives the guest notification.

This is an HCI-offload proof, not a native ESP32 Bluetooth radio model. It does
not claim RF, coexistence, security/pairing or hardware behavior.

## Test build

The local UIFlow2 checkout used for bring-up is:

```text
.work/uiflow-core2-2.5.3
```

Its Core2 `hciuart` variant disables the built-in controller and selects:

```text
CONFIG_BT_NIMBLE_TRANSPORT_UART=y
CONFIG_BT_NIMBLE_TRANSPORT_UART_PORT=1
CONFIG_BT_NIMBLE_UART_RX_PIN=32
CONFIG_BT_NIMBLE_UART_TX_PIN=33
CONFIG_BT_NIMBLE_HCI_UART_BAUDRATE=921600
CONFIG_ESP_INT_WDT_TIMEOUT_MS=10000
```

The wider interrupt-watchdog budget is test-only. QEMU services flash and
interrupt work cooperatively on CPU1, and the stock 800 ms budget can expire
while both guest CPUs are still making progress. A real 10-second lockup still
trips the watchdog.

Build:

```bash
REPO_ROOT=$(pwd)
cd .work/uiflow-core2-2.5.3/m5stack
export IDF_PATH="$REPO_ROOT/.work/esp-idf-v5.5.4"
export ADF_PATH="$REPO_ROOT/.work/uiflow-core2-2.5.3/esp-adf"
source "$IDF_PATH/export.sh"
python "$IDF_PATH/tools/idf.py" \
  -B build-M5STACK_Core2-hciuart3 \
  -DMICROPY_BOARD=M5STACK_Core2 \
  -DMICROPY_BOARD_VARIANT=hciuart \
  -DBOARD_TYPE=core2 \
  -DUSER_C_MODULES="$PWD/cmodules/cmodules.cmake" \
  build
```

## Run

```bash
PYTHONPATH=.work/py python3 tests/uiflow2/core2_hci_ble/run_test.py \
  --out-dir /tmp/core2-hci-ble
```

The default run requires three consecutive full passes. The first milestone
run used five attempts and passed 5/5:

1. external peer finds the Core2 advertisement;
2. connects and discovers NUS;
3. subscribes to TX and writes `M5_CORE2_HCI` to RX;
4. guest prints `CORE2_HCI_BLE_RX`;
5. guest notifies `ACK:M5_CORE2_HCI`;
6. external peer validates and prints `BLE_BUMBLE_PASS`.

The image is assembled by preserving the public UIFlow2 NVS/phy partitions,
replacing bootloader/partition/app from the test build, and overlaying a VFS
created with the checkout's own LittleFS2 packer. Do not use the generic
`mklittlefs-v1` image for this firmware: its newer on-disk version does not
mount in the UIFlow2 runtime.

Evidence is written to `evidence.json`; firmware and logs stay under the
selected output directory and are not committed.
