# Secure Boot v2 image signature-sector analysis

This static fixture verifies that the FirmwareManifest distinguishes:

- a correctly structured RSA Secure Boot v2 signature sector whose embedded
  SHA-256 image digest matches the bytes before the sector;
- RSA-PSS and ECDSA P-192/P-256/P-384 signature mathematics against the
  block-embedded public keys;
- a signature sector whose image digest no longer matches after tampering;
- a Secure Boot v2 configuration with no signature sector.
- matching, mismatching and unavailable public-key digest comparisons against
  a package-provided `espefuse` summary.
- below, satisfied and unavailable application `secure_version` comparisons
  against the summary's `SECURE_VERSION`.

The fixture also checks that a structurally valid signature block remains
`signature_authenticity=not-verified`, and that both the per-image
`trust_root=not-verified` and top-level `security.trust_root.status` remain
unverified. A digest match only means the signed image agrees with a
self-asserted package summary; the fixture does not authenticate that summary,
read live eFuse contents, enforce anti-rollback, or execute boot
ROM/bootloader verification.

Run:

```bash
PYTHONPATH=platform/tools python3 \
  tests/firmware/secure_boot_image/run_test.py \
  --out-dir /tmp/m5-secure-boot-image
```

The committed evidence is
[`evidence-2026-10-25-secure-boot-image.json`](../evidence-2026-10-25-secure-boot-image.json).
