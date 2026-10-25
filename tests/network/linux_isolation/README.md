# Linux network-namespace guest test

Last reviewed: `2026-10-25`

This test runs the validated StickS3 UIFlow2 image through
`platform/tools/network_sandbox.py`. The QEMU guest and controlled HTTP server
share a newly created Linux network namespace with no external route.

Run on a Linux worker with a QEMU build containing the M5Stack board models:

```bash
python3 tests/network/linux_isolation/run_test.py \
  --qemu /path/to/qemu-system-xtensa \
  --image /path/to/sticks3-8mib.bin \
  --rom-dir /path/to/qemu/pc-bios \
  --out-dir /tmp/m5-linux-isolation
```

Required observations:

- private network namespace created and no external route;
- guest scan, association and DHCP;
- `/unified` reaches the namespace-local HTTP fixture;
- a public DNS query is visible in pcap but receives no response;
- no TCP/UDP destination has global or QEMU-SLiRP-redirect scope;
- serial reaches `UNIFIED_STICKS3_READY`.

`evidence-2026-10-23-linux.json` records the first full PASS. The QEMU binary
was built from `M5StopWatch-QEMU@32d86576e783988fef1a489cb362dfda92a7aeda`
for `xtensa-softmmu` on Linux arm64.

This fixture intentionally proves DNS denial and no external route. The
separate [`tls_allowlist`](../tls_allowlist/) fixture adds controlled
A/NXDOMAIN and TLS Host allow/deny behavior inside the same namespace model;
do not read this page as “DNS policy is unavailable”.
