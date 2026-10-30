# Device Service network execution parsing boundary

Date: `2026-10-30`

Status: `PASS` for the stateless boundary extraction.

## Result

`SVC-03` moves the esp-emu network execution request parser out of
`device_service.py` into
`platform/tools/device_service_network_execution.py`:

- `parse_network_execution`

`device_service.py` re-exports the same function object. The parser retains
profile defaults, capability checks, host-forward normalization, PSRAM bounds,
WiFi/BLE/TCP booleans, ELF requirements, expected-marker bounds, I2C
normalization and pcap rejection on this runtime.

## Verification

- dedicated network-execution parser tests: `4/4 PASS`
- existing Device Service unit tests: `126/126 PASS`
- platform full suite: `1,674` run, `1,673 PASS + 1 skip`
- runtime coverage, peripheral catalog, QEMU profiles and project snapshot:
  `PASS`
- Python compileall, scoped Ruff `E9/F`, `git diff --check`: `PASS`

This is a source-boundary refactor only. It does not alter HTTP routes,
network runtime behavior, session state, evidence fields or QEMU execution.
Physical hardware and network transport remain `NOT RUN`.
