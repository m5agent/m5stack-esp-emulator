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

The Linux path routes DNS through the guest's SLiRP resolver. Use a Linux
arm64 worker with the native Xtensa patch series through 0224, the S3 ROM,
`iproute2`, `nftables`, and Python 3.12 namespace support. For the contained
probe, the outer Linux container runs with no network and has NET_ADMIN and
SYS_ADMIN for its own namespace and DNS mount. No host ports are published.
Start an isolated Device Service with its own token and state. Upload and
register the same merged fixture separately for Cardputer and ADV. The
firmware diagnostics are terminal and do not start a portal.

Wait for the complete guest assertion and collect the session ZIP before
stopping. At stop, use `purge=false` and the default Flash release. Verify
`/network` and the retained ZIP both bind the finalized pcap hash, one DORA,
one bidirectional TCP payload flow and three bidirectional UDP payload flows.
Inspect the namespace receipt for explicit default-drop, no external route and
no gateway. The reviewer exercises the same Device Service via the real
execution-plan, session admission and finalized transport reader.
Repeat with only the last response byte changed from `42` to `43`.
The guest should still receive HTTP and both DNS results and report `udp=0`.
The same namespace request on a worker without the capabilities should return
`503 network_isolation_unavailable` before any lease is allocated.
[Linux virtual-device evidence](linux-session-summary.json).

### Local POST and raw TCP checks

Add `-D M5_FIXTURE_LOCAL_STREAMS=ON` to the ESP32-S3 namespace build to
exercise HTTP POST and a separate binary TCP peer after the existing GET,
DNS and UDP checks. Merge the 8 MiB image as above and use the same image on
Cardputer and Cardputer ADV. The listener addresses below belong to the
session-local loopback in the Linux namespace.

| Operation | Endpoint | Request hex | Expected reply hex |
| --- | --- | --- | --- |
| HTTP POST | `10.0.2.2:18193`, `post.native-sta.test`, `/native-sta-post` | `4d35504f5354007fff11` | `41434b2d504f5354007fff11` |
| Raw TCP | `10.0.2.2:19193` | `4d355443500080fe22` | `41434b2d5443500080fe22` |

POST uses a binary body and checks HTTP 200, `Content-Length` and the response
bytes. TCP carries a two-byte big-endian payload length in each direction.
For a control, change only the final POST reply byte to `12` or the final TCP
reply byte to `23` in the respective peer configuration. Keep the exact same
firmware bytes for both controls. Each operation emits one terminal line,
`STA_FIXTURE_HTTP_POST matched=1` or `STA_FIXTURE_TCP matched=1`. The expected
control emits `matched=0` for only the changed operation. Require separate
peer receipts and finalized capture before attributing a failure to reply
contents. Continue checking the original GET, DNS and UDP markers.

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

## Classic Core2 DNS and binary UDP

The same probe has a classic ESP32 build that leaves HTTP off. Use the
ESP-IDF v5.5.4 checkout and the 16 MiB Core2 configuration.

```sh
idf.py -C tests/network/native_sta_peers -B <build-dir> \
  -D IDF_TARGET=esp32 -D SDKCONFIG=<owned-sdkconfig> \
  -D SDKCONFIG_DEFAULTS=sdkconfig.defaults.esp32 \
  -D M5_NAMESPACE_DNS=ON -D M5_FIXTURE_UDP_ONLY=ON build
esptool --chip esp32 merge_bin --fill-flash-size 16MB \
  --flash_mode dio --flash_size 16MB --flash_freq 40m -o <probe.bin> \
  0x1000 <build-dir>/bootloader/bootloader.bin \
  0x8000 <build-dir>/partition_table/partition-table.bin \
  0x10000 <build-dir>/native_sta_fixture.bin
```

Use the outer Linux container with no network, the separate Device Service
state and token, and the namespace settings from the Cardputer example.
Configure the classic radio executable through `M5_CORE2_RADIO_QEMU` and
register the image for `device_id=core2`. Set `network.profile=core2-openmac`,
`network.http_fixture=false`, `network.policy.allowed_hosts=["lab.test"]`
and keep the same binary UDP peer. Require one DORA exchange and
`STA_FIXTURE_PEERS dns_a=1 dns_nxdomain=1 udp=1`. The wrong-reply variant must
keep DHCP and DNS while producing `udp=0`, even if the finalized PCAP still
has three bidirectional UDP flows. Omit namespace capability in a separate
control and require preallocation rejection. Verify teardown and compare the
ZIP's PCAP hash with the finalized transport receipt.

The [Core2 Linux run](core2-linux-summary.json) also exercises the actual
reviewer's execution plan, session admission and finalized transport reader.
This scoped result covers the local IPv4 probe and Open Wi-Fi on the native
Core2 model. HTTP, WLAN security variants and original cloud applications
require their own evidence.

### Classic Core2 fixed HTTP

Omit `M5_FIXTURE_UDP_ONLY` when building the same source for classic ESP32
to exercise HTTP as well. On the isolated `core2-openmac` profile, set
`network.http_fixture=true` and add exact host `native-sta.test` to the
controlled allowlist alongside `lab.test`. The guest requires HTTP 200 and
the exact fixed body, as well as DHCP, DNS and the binary UDP reply.

In a second run with the same BIN, remove only `native-sta.test` from the
allowlist. Require the peer's HTTP 403 receipt and guest `http=0`, while the
other guest checks still pass. The passive PCAP retains one bidirectional TCP
flow in both cases. Deny a third identical request before lease allocation
when namespace capability is unavailable.

The [Core2 HTTP Linux run](core2-http-linux-summary.json) exercises the
reviewer's plan, admission and finalized transport reader. A newer Device
Service advertises `native_network.sta.http_fixture=true` for this explicit
fixture. Its absence on an older backend leaves the earlier Core2 DNS/UDP
review path available. The reception result is limited to this fixed local
HTTP service and does not cover arbitrary applications or HTTPS.

## Saved-snapshot application review

The Reviewer accepts a saved-snapshot `validation.native_sta_operation`.
Use the exact local names and paths above, the UDP request and response
bytes, and the firmware's literal terminal result lines. Supply no
top-level `network` when requesting the fixture. The review derives the
Open Wi-Fi and controlled DNS policy for the requested board. The
final evidence ZIP must contain the same stopped guest's PCAP and UART.

The [saved review comparison](saved-sta-operation-summary.json) covers
Cardputer, ADV and Core2. On ADV, replacing the final byte of the fixture's
UDP response preserves the DHCP and bidirectional flows. The guest
reports that the response failed its application check and the scoped
assertion becomes `FAIL`. A worker without namespace capability
continues the offline board review and records an admission `PARTIAL`.
The headless ESP-IDF probe leaves display readiness `PARTIAL`.
