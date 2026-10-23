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

For external GATT through the stock internal-controller VHCI path, use:

```bash
PYTHONPATH=.work/py python3 tests/uiflow2/core2_native_vhci/run_test.py \
  --attempts 5
```
