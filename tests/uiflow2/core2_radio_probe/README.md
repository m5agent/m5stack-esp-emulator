# Core2 UIFlow2 radio baseline probes

These diagnostics replace only `/boot.py` and `/main.py` in the official
Core2 UIFlow2 v2.5.3 LittleFS partition and execute the firmware's real WiFi
or BLE path.

The probes run with deterministic TCG/icount. The optional QEMU radio patches
provide the classic ESP32 WiFi data path and Bluetooth controller bootstrap;
the bootstrap alone does not create external BLE connections.

Run:

```bash
PYTHONPATH=.work/py python3 tests/uiflow2/core2_radio_probe/run_test.py \
  --probe wifi
PYTHONPATH=.work/py python3 tests/uiflow2/core2_radio_probe/run_test.py \
  --probe ble
```

The run writes the image, serial log and hashed `evidence.json` under the
selected output directory.

For an experimental radio build containing the OpenMAC WiFi and BT bootstrap
patches:

```bash
PYTHONPATH=.work/py python3 tests/uiflow2/core2_radio_probe/run_test.py \
  --probe ble \
  --qemu <patched-qemu-system-xtensa> \
  --out-dir /tmp/core2-ble-probe \
  --attempts 5 \
  --retry-after-main-failure
```

`--retry-after-main-failure` keeps retrying only when the image reached
`main.py` but did not complete the requested radio result. It remains a
diagnostic option; PASS evidence uses first attempts.

For the current stock-firmware path, use QEMU native-HCI through Device
Service profile `core2-native-hci`; its `HCI-4` evidence is
`tests/uiflow2/core2_native_hci/evidence-2026-10-24-hci4-service-5x.json`.
No GDB bridge is involved.

For historical external-GATT comparison through the GDB-mediated stock
internal-controller VHCI path, use:

```bash
PYTHONPATH=.work/py python3 tests/uiflow2/core2_native_vhci/run_test.py \
  --attempts 5
```

The same guest board/WiFi path is available through:

```bash
PYTHONPATH=.work/py python3 tests/uiflow2/unified_core2/run_test.py \
  --image /tmp/core2-native-vhci-unified.bin \
  --out-dir /tmp/core2-native-vhci-unified \
  --ble-transport native-vhci \
  --attempts 3 --require-all-attempts
```
