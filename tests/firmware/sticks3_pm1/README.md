# StickS3 PM1 native regression

Use the unmodified M5Burner StickS3 PMIC Upgrade M5PM1-O image
(`1897200000000001767`). The runner checks its SHA-256 and the independent
digest of the embedded PM1 app. The valid update also needs the completion
marker from the original guest's USB Serial/JTAG CDC stream. Build the
canonical native Xtensa runtime with patches 0171 and 0173 and
start a dedicated loopback Device Service using that binary and its matching
ROM directory. Set `M5_SERVICE_API_TOKEN` in the runner environment to the
service control token.

```sh
python3 tests/firmware/sticks3_pm1/run.py \
  --service http://127.0.0.1:18871/api/v1 \
  --firmware /path/to/1897200000000001767.bin \
  --runtime-binary /path/to/qemu-system-xtensa \
  --output-dir /tmp/sticks3-pm1-iap --mode iap
```

Run `bad-crc` and `strap` with separate output directories. The first
changes only the PM1 CRC inside the ESP32 guest, then repairs the outer ESP
image checksum and digest. The guest must transfer the complete image and
the PM1 model must keep address 0x54 after rejecting RUN. The strap case
checks the real ESP32-S3 ROM serial banner after PWR release, then presses
PWR briefly to boot back to Flash. Each case uses a separate session and
retains its evidence before stopping.

This lane covers the native PM1 digital protocol and boot strap. PM1 app
instructions, physical power rail behavior, USB electrical behavior and the
browser runtime are outside this test.
