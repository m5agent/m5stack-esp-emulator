# UIFlow2 device-local network probe

This runner replaces only `/boot.py` and `/main.py` in an official UIFlow2
full-flash image, executes a WiFi scan, connects to the network lane's
virtual AP, requires an `192.168.4.x` DHCP lease, and submits the resulting
image to `platform/tools/network_lane.py`.

It supports the official ESP32-S3 and ESP32-C6 device entries in
`tests/uiflow2/device_matrix.json`. It intentionally excludes Tab5 and
classic ESP32 Core2.

```bash
PYTHONPATH=.work/py python3 tests/uiflow2/network_probe/run_test.py \
  --device cores3 --out-dir /tmp/uiflow2-cores3-wifi
```

For a local UART-REPL build whose partition layout differs from the official
catalog image, override the base and VFS geometry:

```bash
PYTHONPATH=.work/py python3 tests/uiflow2/network_probe/run_test.py \
  --device sticks3 --base /path/to/local-merged.bin \
  --vfs-offset 0x651000 --vfs-size 0x1AE000 \
  --out-dir /tmp/uiflow2-sticks3-wifi
```

The run writes a session-isolated image, network evidence and a combined
`evidence.json`. A PASS proves UIFlow2 WiFi scan/association/DHCP in the
emulator only. A board firmware that hangs in its C-level `M5.begin()` before
entering `boot.py` is a board-runtime coverage failure, not a WiFi result.
