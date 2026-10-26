# CoreS3 Unit explicit evidence selection, a8fe

This is an explicit **16 + 11** selection: 16 passing records from worker generation 7 and 11 passing supplemental records from generation 8. The strict checker returns PASS for 27 selected guest/controller records, 27 corresponding live-browser records and the independent all-27 form/lifecycle contract. Every guest/browser pair selects the same outer report, original pre-stop evidence ZIP, session, device, runtime and firmware SHA. Both runtime layers use direct live PID/executable evidence bound to `a8fe15dbe7299c5be4b52eeac68a6d0012578950d267287630760bf8bec7d047`; no service-generation inference is used.

The generation-7 attempt was interrupted: its original [attempt summary](../2026-10-26-unit-web-cohort-a8fe/attempt-summary.json) retains 16 PASS, 4 FAIL, one interrupted Angle wrapper and six NOT RUN cases. This selection is **not one uninterrupted 27-case PASS**. The failed generation-7 records are not rewritten; the eleven explicit supplemental paths remain separate. [Provenance](provenance.json) records every chosen path/hash, both service receipts, their exact source differences and each case's frozen tool hashes. Missing generation-7 helper provenance is left unrecorded rather than reconstructed from generation 8.

| Service generation | Selected Unit records | Tools and service boundary |
| --- | --- | --- |
| 7 | button, relay, env-iii, joystick-v11, encoder, 8encoder, cardkb, rfid2, color, tof, ncir, heart, thermal, ultrasonic-i2c, limit, rgb | Original available-data bridge and original service startup path; all sixteen passing reports retain their original source snapshots. |
| 8 | tvoc, pir, dual-button, key, angle, light, buzzer, fan, ir, rs485, hub | Browser transport waits for actual product running/enabled controls; the service fixes QMP startup connection ownership and failed-handshake socket cleanup. All eleven are separate sessions and retain their own tool snapshots. |

The runtime binary is unchanged between these groups. The orchestration source changes are independently covered by the [readiness regression](../2026-10-26-unit-web-readiness-regression/README.md) and generation-8 receipt. The selected bridge layer is [UnitPanel's all-27 lifecycle contract](../2026-10-26-unit-panel-lifecycle-regression/report.json). The readiness report has a narrower browser transport scope and is not used as an all-27 bridge contract.

IR explicitly selects `custom-guest-ir-callback-root-patch`, including its original/patched driver hashes and limitation. The original published IR wrapper is not established as PASS. The remaining 26 records keep `reference-app-with-original-unit-drivers`. No result here establishes another firmware SHA or another host's Unit validation.

The checker validates the wrapper-committed raw controller assertions separately from its browser assertions: **266 guest/controller assertions**, **189 live-browser wrapper assertions**, **617 detailed browser snapshots**, and **27 committed, decoded before-evidence UI screenshots**. The independent archive audit decodes 67 published PNG files and verifies 523 entries in the two published SHA256 manifests. Inputs, outputs and missing physical bindings retain their original report scope. A successful web/virtual data plane is not mechanical, optical, acoustic, electrical, RF or hardware equivalence; hardware execution is NOT RUN.

Reproduce from the repository root with the project's Python/Pillow environment:

```sh
PYTHONPATH=tests/units:.work/py312 python3.12 tests/units/check_batch_evidence.py \
  --selection docs/evidence/2026-10-26-unit-final-selection-a8fe/selection.json \
  --strict-direct \
  --write docs/evidence/2026-10-26-unit-final-selection-a8fe/summary.json
```

The selection pins actual report bytes. No `latest` discovery, attempt scanning, automatic successful-attempt replacement or missing-evidence substitution is performed. Historical selections remain unchanged. The checker summary reports SHA256 of its own source; re-running a changed checker produces a new summary and requires refreshing this directory's SHA256 manifest.
