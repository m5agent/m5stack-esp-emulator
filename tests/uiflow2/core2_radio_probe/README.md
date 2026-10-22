# Core2 UIFlow2 radio baseline probes

These diagnostics replace only `/boot.py` and `/main.py` in the official
Core2 UIFlow2 v2.5.3 LittleFS partition and execute the firmware's real WiFi
or BLE path.

The QEMU `m5core2` machine has an OpenETH Ethernet device, but no classic
ESP32 WiFi MAC/PHY or Bluetooth controller model. The probes record the exact
point reached by the stock paths and must not be mixed with the separate
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
