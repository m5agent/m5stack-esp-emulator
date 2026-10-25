# ESP-IDF wrong-password regression

Last reviewed: `2026-10-25`

This P0 case joins the emulator lab AP with an intentionally wrong password and
requires all of the following in one guest run:

1. at least one authentication attempt;
2. an authentication rejection;
3. at least one retry and a second rejection;
4. no DHCP lease;
5. no HTTP throughput progress;
6. the firmware failure marker; and
7. the SoftAP wrong-password diagnostic.

Run:

```bash
python3 tests/network/wrong_password/run_test.py \
  --out-dir /tmp/m5-wrong-password
```

The default firmware is the ESP32-S3 `http_throughput` test build already used
by the network-lane regression. Override `--firmware`, `--elf` and
`--emulator` for another matching build.

The runner delegates emulator execution to `platform/tools/network_lane.py`,
then removes host paths and the redacted password command from the retained
evidence. It keeps only artifact roles, sizes and SHA256s, the required
checks, serial hash and declared boundaries.

Validated evidence:
[`evidence-2026-10-24-wrong-password-pass.json`](evidence-2026-10-24-wrong-password-pass.json).

This is virtual-device validation. It does not prove physical RF behavior,
WPA3-only behavior, DHCP-server failure handling or a malicious-firmware
sandbox.
