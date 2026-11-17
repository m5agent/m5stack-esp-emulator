# Cardputer native STA fixture

This ESP-IDF probe connects over the ordinary S3 Wi-Fi driver. It verifies
DHCP, the HTTP response body, one A record, one NXDOMAIN, and the exact
binary UDP response including its embedded NUL. Changing just the UDP
response must leave connected transport and produce `udp=0`.

Build with ESP-IDF v5.5.4 for ESP32-S3 and merge the ESP-IDF flash layout:

```sh
idf.py -C tests/network/native_sta_peers -B <build-dir> -D M5_NAMESPACE_DNS=ON build
esptool --chip esp32s3 merge_bin --fill-flash-size 8MB \
  --flash_mode dio --flash_size 8MB --flash_freq 80m -o <probe.bin> \
  0 <build-dir>/bootloader/bootloader.bin \
  0x8000 <build-dir>/partition_table/partition-table.bin \
  0x10000 <build-dir>/native_sta_fixture.bin
```

For the controlled Linux worker, import the merged image and create an
isolated `qemu-wifi` session with a complete `network` object:

```json
{
  "profile": "generic-observe",
  "wifi_ssid": "m5-native-sta",
  "http_fixture": true,
  "udp_fixture": {
    "port": 19192,
    "request_hex": "4d352d007ffeff4142",
    "response_hex": "41434b4d352d007ffeff4142"
  },
  "policy": {
    "isolation": "namespace",
    "egress": "allowlist",
    "dns": "controlled",
    "allowed_hosts": ["lab.test", "native-sta.test"]
  },
  "capture_pcap": true,
  "expected_markers": ["STA_FIXTURE_PEERS http=1 dns_a=1 dns_nxdomain=1 udp=1"]
}
```

The Linux path routes DNS through the guest's SLiRP resolver. This live
namespace case requires a Linux worker with the existing admission controls
available. The firmware diagnostics are terminal and do not start a portal.

For a bounded macOS diagnostic build, omit `M5_NAMESPACE_DNS`. The same
stock driver sends direct DNS queries to the controlled test peer on port
15353. Run a separate Device Service and restrict the emulator process to
the three controlled loopback endpoints. This route qualifies the guest
and peer data plane without changing production namespace admission.
Obtain the same-session evidence ZIP before stop and compare the finalized
PCAP. The guest marker and the UDP peer receipt serve separate purposes.

[Bounded run summary](summary.json)

The [original SkyCompass replay](original_skycompass/README.md) uses the
unmodified v3.6 Cardputer ADV firmware to verify Wi-Fi UI, DHCP, DNS and SNTP
on a dedicated Unix-only test peer. It withholds the NTP reply in the
same-path negative case.
