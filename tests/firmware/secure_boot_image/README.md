# Secure Boot v2 image signature-sector analysis

This static fixture verifies that the FirmwareManifest distinguishes:

- a correctly structured RSA Secure Boot v2 signature sector whose embedded
  SHA-256 image digest matches the bytes before the sector;
- ECDSA P-256/SHA-256 and P-384/SHA-384 signature-sector parsing;
- a signature sector whose image digest no longer matches after tampering;
- a Secure Boot v2 configuration with no signature sector.

The fixture also checks that a structurally valid signature block remains
`signature_authenticity=not-verified` and `trust_root=not-verified`. It does
not perform RSA-PSS/ECDSA verification, compare the embedded public-key digest
with live eFuse contents, or execute boot ROM/bootloader verification.

Run:

```bash
PYTHONPATH=platform/tools python3 \
  tests/firmware/secure_boot_image/run_test.py \
  --out-dir /tmp/m5-secure-boot-image
```

The committed evidence is
[`evidence-2026-10-25-secure-boot-image.json`](../evidence-2026-10-25-secure-boot-image.json).
