# Device Service storage/NVS execution parsing boundary

Date: `2026-10-30`

Status: `PASS` for the stateless boundary extraction.

## Result

`SVC-03` moves the storage and NVS execution request parsers out of
`device_service.py` into
`platform/tools/device_service_execution_parsing.py`:

- `parse_storage_execution`
- `parse_nvs_execution`

The new module depends only on `ServiceError`, the shared SHA-256 validator
and the `DeviceSpec` protocol. `device_service.py` re-exports both functions
as the same object instances.

Error codes, status codes, unknown-field rejection, SD capability checks,
NVS partition-label bounds and returned dictionaries are unchanged.

## Verification

- dedicated execution parser tests: `5/5 PASS`
- existing Device Service unit tests: `126/126 PASS`
- platform full suite: `1,670` run, `1,669 PASS + 1 skip`
- runtime coverage, peripheral catalog, QEMU profiles and project snapshot:
  `PASS`
- Python compileall, scoped Ruff `E9/F`, `git diff --check`: `PASS`

This is a source-boundary refactor only. It does not alter HTTP routes,
execution request semantics, session state, evidence fields, QEMU behavior or
hardware behavior. Physical hardware remains `NOT RUN`.
