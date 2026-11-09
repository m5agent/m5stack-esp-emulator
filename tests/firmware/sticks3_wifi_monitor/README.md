# StickS3 Wi-Fi monitor fixture

This virtual-device regression uses the normal Device Service session API and
existing ESP32-S3 MAC. The service verifies a paused VM with one emulated Wi-Fi
NIC and zero host network backends. The positive case enables the fixed
`m5-monitor-lab` AP on channel 1. The negative case disables the virtual radio
on that same controller before boot.

## Build and run

Use Python 3.12+, ESP-IDF v5.5.4 and a project native Xtensa QEMU with
`m5sticks3`, its S3 ROM and the `radio-enabled` QOM property. Follow the
[Device Service setup](../../../docs/device-service-api.md#session) to start a
private loopback instance with its own token and state directory. For a separate
worktree, set `M5_QEMU_XTENSA`, `M5_QEMU_XTENSA_ROM_DIR` and
`M5_SERVICE_ESP_EMU` to the installed runtime files. The latter is required by
service backend readiness. This fixture boots using QEMU.

After loading the ESP-IDF environment, create the source-built monitor probe in
an ignored or external output directory.

```sh
idf.py -C tests/firmware/sticks3_wifi_monitor -B "$OUTPUT_DIR/build" \
  -DSDKCONFIG="$OUTPUT_DIR/sdkconfig" -DIDF_TARGET=esp32s3 \
  merge-bin --fill-flash-size 8MB -o "$OUTPUT_DIR/monitor.bin"

python3 tests/firmware/sticks3_wifi_monitor/run_test.py \
  --service "$PRIVATE_SERVICE_URL" --token-file "$PRIVATE_TOKEN_FILE" \
  --firmware "$OUTPUT_DIR/monitor.bin" --out-dir "$OUTPUT_DIR/probe"
```

The probe uses the unmodified SDK `esp_wifi_set_promiscuous_rx_cb` in
`WIFI_MODE_NULL`. It first requires no matching callback while promiscuous mode
is disabled. After enabling it, the positive guest parses the beacon SSID and
reports the received MPDU. The runner matches that report to the controller's
81-byte management frame, 129-byte RX DMA including RX metadata and guest MAC
IRQ clear. In the negative guest, promiscuous mode starts and no matching
beacon or controller RX DMA is observed.

The positive probe then uses the SDK `esp_wifi_80211_tx` to send one benign
43-byte Probe Request in STA mode. The runner checks the 47-byte controller
frame, TX DMA outlink, MAC TX-complete IRQ, guest clear and the virtual AP's
75-byte Probe Response. The evidence records TX metadata. It does not export
arbitrary raw TX payload bytes.

For the exact public M5Gotchi v0.7 BIN, use the same runner with `--stock` and a
new output directory. It pins the original SHA-256 and its 8 MiB normalized
Flash, reads the unmodified firmware's startup scan results, collects its
frame and evidence ZIP, and stops each guest with retained session history.
The firmware sees one AP in each of two startup scans with the fixture and
zero in each scan with the virtual radio disabled. The stock observation uses
the Arduino scanner. The SDK probe independently establishes the promiscuous
callback path.

## Raw MPDU fixture

With native patch `0175`, run the same source-built probe with `--raw`. The
runner sends a custom vendor Action frame through the existing Device Service
QOM endpoint. The original SDK callback returns every injected byte, including
the FCS. A wrong-FCS request fails before DMA. A separate session with the same
raw mode and no input waits through the receive window and captures no frame.

The SDK's benign Probe Request then crosses the real TX DMA path. The raw QOM
readout contains the latest full 47-byte TX DMA buffer, including the SDK's
four-byte placeholder after its 43-byte request. Capture occurs before the
model's MAC rewriting and before the IRQ returns control to the guest.
The service stores an input digest and omits raw frame bytes from automatic
QOM snapshots. [Raw execution summary](raw-summary.json).

See [the execution summary](evidence-2026-11-09.json) for exact identities. This
scope covers the fixed channel and demonstrated management frames. The
[original Evil-StickS3 scan follow-up](evil-stock-summary.json) used its
Scan WiFi and Select Network menu entries. The radio-on list showed the
synthetic AP and the radio-off list was empty. Evil promiscuous mode,
protected or QoS RX, continuous TX capture, RF/PHY and attack behavior
are `NOT RUN`. The fixture has zero host network backends.
