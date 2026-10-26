# Control/Web host evidence contract candidate

This directory is isolated candidate work. No product source, runtime profile,
raw execution report or frozen execution source was changed. Root owns promotion
after the actual batches are complete.

## Why a separate explicit contract

The existing host-nine contract requires two actual runtime observers, including
`host_runtime_provenance` from `proc_pidpath`, and outer `attachments`. The new
control wrapper executed the original CONTROL assertions unchanged and produced
one actual common-bridge direct-PID observer plus raw controller/browser/ZIP
attachment records. The process has already stopped. A second historical kernel
observation cannot be recreated, and adding one to the old raw report would be
false evidence.

`evidence_contract: device-service-control-web-v1` identifies that executed path.
The previous/default `host-probe-dual-observer-v1` branch retains the original
second-observer assertions. Unknown contracts fail. Selection/report/evidence/
firmware/PID fields remain checked by the existing shared test around both
branches.

## Candidate files

- `candidate/platform/tests/test_unit_runtime.py`: the explicit branch and import;
  the previous dual-observer assertions remain intact.
- `candidate/platform/tests/_unit_host_control_evidence.py`: validates the exact
  original unit-specific CONTROL keys, raw artifact graph, direct process proof,
  worker identity, normalized attachment routing, fresh host serial observations,
  native frame identity and actual clean stopped history.
- `candidate.patch` and `manifest.json`: final patch and source fingerprints.

`git apply --check candidate.patch` passed against the named base. Do not apply
while any execution still depends on that frozen source cohort.

## Normalization receipt schema

The new host-validation metadata adds:

```json
{
  "evidence_contract": "device-service-control-web-v1",
  "native_readability": "PARTIAL",
  "normalization_receipt": "<repository-relative receipt path>",
  "normalization_receipt_sha256": "<receipt SHA256>"
}
```

The existing identity/report/selection/evidence/runtime fields are unchanged.
Each pinned normalization receipt has:

```json
{
  "schema_version": 1,
  "evidence_contract": "device-service-control-web-v1",
  "scope": "controller-and-browser-functionality",
  "native_readability": "PARTIAL",
  "report": "<unchanged raw outer report path>",
  "report_sha256": "<raw outer report SHA256>",
  "source_freeze": {"path": "<original source-before.json>", "sha256": "<SHA256>"},
  "source_snapshot_root": "<archive source-snapshot directory>",
  "preparation_readiness": {"path": "<original prepared-readiness.json>", "sha256": "<SHA256>"},
  "history_snapshot": {"path": "<actual post-execution history response>", "sha256": "<SHA256>"},
  "preparation_only_fields": {
    "guest_execution": "NOT RUN",
    "web_execution": "NOT RUN",
    "admission": "<exact original preparation admission object>"
  }
}
```

Use the original preparation row's exact `admission` object, not the placeholder
string above. The actual execution authority is the unchanged outer report and
same-session ZIP/browser/controller evidence. The receipt explicitly labels
historical preparation fields; it never rewrites them to PASS.

Archive paths may change; raw report bytes and internal artifact-relative paths
must remain unchanged. Preserve the original 380-entry source map and its text
source snapshots. The helper reads
`source_snapshot_root/platform/units/host-ports.json.txt`, checks its hash against
the execution source map and ZIP `contract.source_hashes['host-ports.json']`, and
then checks confirmed host routing. It does not assume the contract contains a
full host map. Binary source dependencies remain hash-bound; this candidate does
not pretend to archive every runtime binary.

History must be an actual read-only post-execution observation or an explicitly
provenance-labelled safe projection of that observation, never a fabricated
stopped/Flash-release fixture. It must bind same session/device/runtime/firmware,
`state == stopped`, and literal boolean `flash_retained == false`. Keep private
raw response bytes internal if publication redaction is required; retain their
hash and projection provenance in the publication receipt.

## Verification completed

- Five unchanged real AtomS3R raw reports, controller/browser/ZIP artifacts and
  actual post-execution history responses pass the candidate's complete
  `test_host_pass_metadata_binds_exact_device_firmware_and_direct_runtime_evidence`
  path in isolated temporary metadata/selection envelopes.
- Nineteen semantically distinct mutations are rejected after dependent report,
  artifact, receipt and selection hashes are recomputed where appropriate:
  missing original CONTROL assertion; wrong worker; late fresh BMI offset;
  wrong geometry; wrong attachment request; changed source-freeze map; failed
  history; retained Flash; missing Flash field; numeric zero instead of false;
  unknown contract; rewritten preparation result; wrong selection host; wrong
  selected proof pointer; wrong selected firmware flavor; wrong selected report
  SHA; changed frozen host-ports source; false browser DOM comparison; altered
  history frame.
- The twelve existing UnitRuntime tests pass using the candidate module and the
  current legacy host-nine metadata. No HTTP/socket/child process is allowed by
  either offline harness.
- `real-artifact-contract-results-r2.json` records 5 positives + 19 negatives;
  `legacy-contract-regression.json` records the unchanged legacy behavior.
- The earlier `offline-contract-results.json` used explicitly synthetic history
  shape fixtures before real history was supplied. It is only a schema test and
  is superseded for real-artifact support by the r2 results above.

## Remaining boundaries

These five executions prove AtomS3R control/Web functionality. The current
multirow native font layout is PARTIAL for Joystick/Encoder/8Encoder; CardKB's
final `key 65` and RFID's final `No card` are readable, without intermediate
multirow visual proof. New readable native firmware must be prepared and tested
under its own hash. No other host or physical hardware inherits these results.
