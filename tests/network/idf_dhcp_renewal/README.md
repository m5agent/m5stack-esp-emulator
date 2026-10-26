# ESP-IDF DHCP renewal probe

Last reviewed: `2026-10-26`

This ESP32-S3 program joins the QEMU `myssid` lab AP, obtains an initial DHCP
lease, calls `netifapi_dhcp_renew()` on the live lwIP netif, waits for renewal,
then performs a controlled HTTP request.

Expected serial markers:

```text
DHCP_RENEW_INITIAL: supplied=1 ...
DHCP_RENEW_SENT: err=0 ...
DHCP_RENEW_AFTER: supplied=1 ...
DHCP_RENEW_HTTP: PASSED HTTP/...
DHCP_RENEW_RESULT: PASSED
```

The serial markers prove the guest requested renewal and retained its address.
The definitive renewal evidence comes from the QEMU pcap summary:
`dhcp.renewal_requests >= 1`, `dhcp.renewal_acks >= 1`, and a transaction whose
sequence contains `REQUEST`, `ACK` with `renewal=true`.

Build with ESP-IDF 5.5.4:

```bash
. .work/esp-idf-v5.5.4/export.sh
idf.py -C tests/network/idf_dhcp_renewal \
  -B tests/network/idf_dhcp_renewal/build_esp32s3 \
  -DIDF_TARGET=esp32s3 build
```

Run through the Device Service `qemu-wifi`/`qemu-unified` path so the pcap,
controlled HTTP fixture and serial evidence belong to one guest.

Automated runner:

```bash
python3 tests/network/idf_dhcp_renewal/run_test.py \
  --out-dir /tmp/m5-dhcp-renewal
```

The runner starts an isolated Device Service when `--service-url` is omitted,
normalizes the IDF build through FirmwareManifest, uploads it, waits for guest
and pcap evidence, stops the session with `purge=0`, and writes `evidence.json`.

Validated evidence:
[`evidence-2026-10-24-renewal-pass.json`](evidence-2026-10-24-renewal-pass.json).
