# Device Service device-spec boundary

Date: `2026-10-30`

Status: `PASS` for the stateless device-spec boundary extraction.

## Result

`SVC-03` now moves device catalogue and runtime-profile selection out of
`device_service.py` into `platform/tools/device_service_specs.py`:

- `DeviceSpec`
- `load_device_specs`
- matrix/profile/catalog paths
- QEMU backend path and ROM-directory overrides
- Core2 radio QEMU selection
- network/runtime profile names and status validation

`device_service.py` imports and re-exports the same objects. Existing callers,
service construction, HTTP payloads, session records and evidence fields are
unchanged.

## Verification

- dedicated device-spec boundary tests: `5/5 PASS`;
- public symbol identity is preserved for `DeviceSpec`,
  `load_device_specs`, backend helpers and profile constants;
- all 14 catalog entries load with the existing Core2/Tab5/CardputerZero
  boundaries;
- executable and non-executable `M5_CORE2_RADIO_QEMU` controls preserve
  fail-closed profile admission;
- platform full suite: `1,604` run, `1,603 PASS + 1 skip`;
- existing Service suite: `125/125 PASS`;
- QEMU profile contracts: `20/20 PASS`;
- runtime coverage, peripheral catalog, QEMU profiles and project snapshot:
  `PASS`;
- compileall, Ruff `E9/F` and `git diff --check`: `PASS`.

This is a source-boundary refactor only. It does not alter QEMU behavior,
network policy, session state, evidence fields or hardware behavior.
