# StickS3 PM1 native regression

Use the unmodified M5Burner StickS3 PMIC Upgrade M5PM1-O image
(`1897200000000001767`). The runner checks its SHA-256 and the independent
digest of the embedded PM1 app. The valid update also needs the completion
marker from the original guest's USB Serial/JTAG CDC stream. Build the
canonical native Xtensa runtime with patches 0171, 0173 and 0177 and
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

[Terminal CDC evidence](terminal-cdc-evidence-summary.json) records the eight
stock captures, bad CRC, no-capture strap and separate Bit Pirate OTG controls.
It also preserves the wall-clock missing marker and the first input-clock
control.

The separate controller check uses QTest with the CPUs stopped. It checks
zero-length IN completion before the next SOF, full-FIFO automatic flush,
interrupt masking and clearing, and a held packet across pad detach and
reattach.

```sh
python3 tests/firmware/sticks3_pm1/check_cdc_mmio.py \
  --qemu "$OWNED_QEMU" --rom-dir "$OWNED_ROM_DIR"
```

This lane covers the native PM1 digital protocol and boot strap. PM1 app
instructions, physical power rail behavior, USB electrical behavior and the
browser runtime are outside this test.
