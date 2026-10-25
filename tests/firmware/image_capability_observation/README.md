# Firmware image capability observation

Last reviewed: `2026-10-25`.

This static-manifest probe records low-confidence capability signatures from a
normalized full-flash image and verifies that a required capability unsupported
by the target remains a structured capability mismatch.

```bash
python3 tests/firmware/image_capability_observation/run_test.py \
  --image /path/to/public-firmware.bin \
  --device-id sticks3 \
  --flash-size 8388608 \
  --require-capability wifi \
  --optional-capability display \
  --expect-observed wifi \
  --expect-observed display \
  --out-dir /tmp/m5-image-capability-observation
```

`capabilities.observed` is intentionally separate from sdkconfig
`capabilities.detected`:

- observed entries use an allowlisted token set recorded as
  `source=image-signature` and `confidence=low`;
- observed evidence can produce review warnings but never becomes a hard
  capability failure by itself;
- required capabilities still use the device profile and produce
  `unsupported_capability` when the target does not expose them;
- required observable capabilities missing from the image produce
  `required_capability_not_observed` warning;
- image signatures not named by required/optional declarations produce
  `observed_capability_not_declared` warning.

The scan covers at most the first 64 MiB of the normalized image and records
`SCANNED` or `TRUNCATED` coverage. A token match does not prove that code calls
the capability at runtime. Boot, UI, network, secure-boot execution and
hardware remain separate validation layers.
