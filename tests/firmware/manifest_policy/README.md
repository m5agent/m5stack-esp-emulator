# FirmwareManifest policy fail-closed probe

Last reviewed: `2026-10-26`.

This fixture checks that a hand-edited FirmwareManifest cannot bypass the
capability policy or understate security evidence that still exists in the
same document.

Covered cases:

- the root `capabilities` object is required;
- `capabilities.required` and `capabilities.optional` arrays are required;
- a signed Secure Boot image cannot be hidden by changing the aggregate image
  status to `not-found`;
- eFuse summary secure-boot/Flash Encryption values use strict enums;
- a Secure Boot key digest mismatch is rejected;
- an image secure version below the package-provided eFuse version is
  rejected.

Run:

```bash
PYTHONPATH=platform/tools python3 \
  tests/firmware/manifest_policy/run_test.py
```

The evidence proves static manifest compatibility only. Live eFuse,
bootloader execution, Flash Encryption runtime and physical hardware remain
`NOT RUN`.
