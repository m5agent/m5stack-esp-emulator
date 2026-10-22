# Core2 UIFlow2 radio baseline probes

These diagnostics replace only `/boot.py` and `/main.py` in the official
Core2 UIFlow2 v2.5.3 LittleFS partition and execute the firmware's real WiFi
or BLE path.

The default QEMU `m5core2` binary has no classic ESP32 WiFi MAC/PHY or complete
Bluetooth data-plane model. The probes therefore default to recording the
exact point reached by the stock paths and must not be mixed with the separate
OpenETH fixture.

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
`main.py` but did not complete the requested radio result. It exists for the
known intermittent Core2 cache startup issue and does not turn a failed radio
marker into a PASS.
