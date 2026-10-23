# TLS host allowlist probe

Status: `FAIL` on the current ESP32-S3 QEMU path. This runner is wired but is
not a TLS PASS.

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

Current blocker: the guest completes WiFi/DHCP and loads the generated CA DER
buffer, but stalls while constructing `ssl.SSLContext`. QEMU concurrently logs
`[AES] Error reading from GDMA buffer`. The runner records this as
`ssl_context_creation_stalls_after_esp32s3_aes_gdma_read_error`; it must pass
without that blocker before the TLS/Host allowlist item is closed.
The sanitized status snapshot is
[`evidence-2026-10-23-blocked.json`](evidence-2026-10-23-blocked.json).

The test covers a namespace-local TLS gateway allowlist. It does not claim
arbitrary public-internet allowlisting, certificate pinning, mutual TLS,
hardware RF behavior or malicious-firmware safety.
