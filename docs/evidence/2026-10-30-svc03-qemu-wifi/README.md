# Device Service QEMU WiFi semantic boundary

Date: `2026-10-30`

Status: `PASS` for the stateless boundary extraction.

## Result

`SVC-03` moves the QEMU WiFi security parser and environment projection out of
`device_service.py` into `platform/tools/device_service_qemu_wifi.py`:

- `parse_qemu_wifi_security`
- `apply_qemu_wifi_environment`

`device_service.py` re-exports both functions as the same object instances.
Open/WPA2-PSK validation, password normalization, SSID bounds and the
S3-only WPA2 trace gate are unchanged.

## Verification

- dedicated QEMU WiFi boundary tests: `4/4 PASS`
- existing Device Service unit tests: `126/126 PASS`
- platform full suite: `1,678` run, `1,677 PASS + 1 skip`
- runtime coverage, peripheral catalog, QEMU profiles and project snapshot:
  `PASS`
- Python compileall, scoped Ruff `E9/F`, `git diff --check`: `PASS`

This is a source-boundary refactor only. It does not alter HTTP routes,
network configuration, QEMU execution, session state, evidence fields or
hardware behavior. Physical hardware/RF/electrical validation remains
`NOT RUN`.
