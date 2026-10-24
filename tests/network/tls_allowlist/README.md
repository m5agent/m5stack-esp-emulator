# TLS host allowlist probe

Status: `PASS` on ESP32-S3 QEMU in both trusted-host and Linux private
namespace after `0027-esp32s3-gdma-external-memory.patch`.

The intended assertion is that an ESP32-S3 UIFlow2 guest can:

1. associate with the QEMU virtual AP and obtain DHCP;
2. verify a namespace-local HTTPS endpoint against a generated test CA;
3. receive 200 for `allowed.lab.test`;
4. receive 403 for `denied.lab.test` from the same TLS gateway;
5. retain pcap and request-decision evidence.

The certificate and private key are generated in a temporary directory and are
never committed.

On a trusted workstation:

```bash
PYTHONPATH=.work/py python3 tests/network/tls_allowlist/run_test.py \
  --qemu .work/M5StopWatch-QEMU/build/qemu/build/qemu-system-xtensa \
  --rom-dir .work/M5StopWatch-QEMU/build/qemu/pc-bios \
  --out-dir /tmp/m5-tls-allowlist
```

On a Linux worker, add `--isolation namespace`. The TLS gateway and QEMU guest
then run in the same private network namespace with no external route.

Historical blocker: before the GDMA external-memory fix, the guest stalled
while constructing `ssl.SSLContext`, and QEMU logged
`[AES] Error reading from GDMA buffer`. The failed snapshot remains in
[`evidence-2026-10-23-blocked.json`](evidence-2026-10-23-blocked.json).

The passing run loads the generated PEM CA into the VFS because the validated
UIFlow2 build exposes `SSLContext.load_verify_locations(cafile=...)`. The test
certificate deliberately starts at the Unix epoch so it remains valid in a
guest that has not completed SNTP yet. The successful snapshot is
[`evidence-2026-10-23-pass.json`](evidence-2026-10-23-pass.json).

Linux arm64 QEMU was rebuilt from the same source with patch `0027` and run
inside a private network namespace. That run additionally reports
`private_namespace=true`, `no_external_route=true`, and no DNS responses.
Evidence:
[`evidence-2026-10-24-linux-namespace-pass.json`](evidence-2026-10-24-linux-namespace-pass.json).

The namespace run also installs a private temporary `resolv.conf` in a mount
namespace. A controlled UDP resolver returns `10.0.2.2` for
`allowed.lab.test`, NXDOMAIN for `denied.lab.test`, and NXDOMAIN for background
UIFlow/NTP names. The host resolver configuration is not modified globally.
Evidence:
[`evidence-2026-10-24-controlled-dns-pass.json`](evidence-2026-10-24-controlled-dns-pass.json).

The resolver model also accepts exact A and AAAA addresses for one allowlisted
name. Contract coverage sends both query types over UDP, verifies the AAAA
record type/payload and NXDOMAIN for an unknown name, and rejects malformed,
unspecified, multicast and oversized record values. Evidence:
[`evidence-2026-10-24-controlled-dns-aaaa.json`](evidence-2026-10-24-controlled-dns-aaaa.json).
This is resolver-level validation; an ESP firmware guest completing IPv6
DNS/HTTP is tracked separately as `NET-06`.

The namespace lane now also installs nftables input/output default-drop rules.
The guest TLS request is allowed only for the exact endpoint
`10.0.2.2:18443/tcp`; required DNS and control ports are internal loopback
exceptions. Evidence:
[`evidence-2026-10-24-ip-port-nftables-pass.json`](evidence-2026-10-24-ip-port-nftables-pass.json).

The test covers a namespace-local TLS gateway allowlist. It does not claim
arbitrary public-internet allowlisting, certificate pinning, mutual TLS,
hardware RF behavior or malicious-firmware safety.
