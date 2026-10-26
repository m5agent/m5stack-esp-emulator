# Unknown required capability fail-closed probe

Date: `2026-10-26`

This probe checks that firmware-declared required capabilities are fail-closed.
An unknown required declaration cannot be matched against a device profile, so
the importer and Device Service must reject it. An unknown optional declaration
remains a warning and keeps the firmware as a candidate.

The probe uses one public StickS3 image with a fixed source SHA. It runs:

- merged image with known `wifi` required → `PASS`;
- merged image with unknown required capability → `REJECTED`, exit code `1`;
- merged image with unknown optional capability → `PASS` with warning;
- WebBurner package with known `wifi` required → `PASS`;
- the same WebBurner content in a second differently named package root →
  identical `manifest_id`;
- WebBurner package with unknown required capability → `REJECTED`.

The merged and WebBurner baseline runs must normalize to the same full-flash
SHA256 and 8 MiB image.

```bash
python3 tests/firmware/unknown_required_capability/run_test.py
```

The default input is the local public-firmware cache. Pass `--image` to use a
matching cached copy elsewhere. The image binary is not committed.

This is static manifest validation. It does not prove that a declared known
capability is exercised at runtime, that boot or networking succeeds, that
Secure Boot executes, or that physical hardware exposes the capability.
