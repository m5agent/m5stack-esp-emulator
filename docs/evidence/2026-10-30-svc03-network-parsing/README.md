# Device Service network parsing boundary

Date: `2026-10-30`

Status: `PASS` for the stateless boundary extraction.

## Result

`SVC-03` now moves network policy and CNAME request normalization out of
`device_service.py` into `platform/tools/device_service_network.py`:

- `parse_network_policy`
- `parse_dns_cname_records`

`device_service.py` imports and re-exports both functions, preserving public
symbol identity. Error codes, status codes, implicit endpoint merging and
bounded CNAME validation are unchanged.

## Verification

- dedicated network boundary tests: `6/6 PASS`
- existing parser boundary tests: `7/7 PASS`
- network-focused platform tests: `90/90 PASS`
- platform full suite: `1,589` run, `1,588 PASS + 1 skip`
- runtime coverage, peripheral catalog, QEMU profiles and project snapshot:
  `PASS`
- Python compileall and `git diff --check`: `PASS`

The change is a source-boundary refactor only. It does not alter HTTP routes,
network policy semantics, sandbox execution, session state, evidence fields or
hardware behavior. Physical hardware, RF and electrical validation remain
`NOT RUN`.
