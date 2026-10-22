# Core2 QEMU OpenETH probe

This fixture proves the classic ESP32 QEMU path can exchange real Ethernet
frames through the Espressif `open_eth` device, obtain DHCP through libslirp,
and download a complete 1 MiB HTTP body.

It deliberately does **not** prove ESP32 WiFi. Stock UIFlow and arbitrary WiFi
firmware select the ESP-IDF WiFi path, while this fixture selects
`CONFIG_ETH_USE_OPENETH` and `esp_eth_mac_new_openeth()`. A PASS here is an
Ethernet/IP data-plane milestone and keeps the Core2 WiFi path `PARTIAL`.

Build and run:

```bash
python3 tests/network/core2_openeth/run_test.py
```

Expected terminal markers:

```text
CORE2_OPENETH_TRANSFER: bytes=1048576 expected=1048576 complete=1
CORE2_OPENETH_RESULT: PASSED
```
