# Firmware security preflight fail-closed

Date: `2026-10-26`

This static fixture verifies that Device Service security preflight cannot be
bypassed by understating `security.secure_boot` or
`security.flash_encryption` in a submitted manifest.

The fixture creates synthetic 8 MiB ESP32-S3 images and checks:

- no secure-boot or Flash Encryption evidence → compatibility `PASS`;
- aggregate secure-boot evidence → rejected;
- sdkconfig secure boot while aggregate is `unknown` → rejected;
- signed Secure Boot v2 image while aggregate/config are `unknown` → rejected;
- invalid Secure Boot v2 image evidence → rejected;
- sdkconfig Flash Encryption while aggregate is `unknown` → rejected;
- package-provided eFuse claims for secure boot / Flash Encryption while
  aggregate is `unknown` → rejected;
- missing required security fields and invalid security enums → structural
  rejection;
- schema accepts explicit `disabled` secure-boot / Flash Encryption config.

```bash
python3 tests/firmware/security_preflight/run_test.py
```

The report is static compatibility evidence. It does not authenticate package
metadata, read live eFuse, execute ROM/bootloader verification, prove Flash
Encryption runtime state or validate physical hardware.
