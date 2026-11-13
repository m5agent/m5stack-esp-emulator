# Native raw-frame orientation metadata — 2026-11-13

**Virtual-device validation: PASS for five original StickS3 BINs.** The default
PNG stays in raw panel coordinates. An explicit `orient=display` request returns
a losslessly rotated derivative of the same capture. The direction comes from
the actual controller MADCTL and fixed glass geometry; no firmware name map or
image/text recognition selects it.

| Original firmware | Clockwise angle | Same-sample pixel oracle | Visual review | Cleanup |
| --- | --- | --- | --- | --- |
| Bruce 1.16.1 | 90° | PASS | PASS | stopped; lease and mutable Flash released |
| M5Launcher 3.0 | 90° | PASS | PASS | stopped; lease and mutable Flash released |
| PulseOS 1.4 | 270° | PASS | PASS | stopped; lease and mutable Flash released |
| AirMouseS3 1.0 | 180° | PASS | PASS | stopped; lease and mutable Flash released |
| 小智 2.2.6 | 0° | PASS | PASS | stopped; lease and mutable Flash released |

Each run uploads the exact original BIN, uses ordinary merged-image padding,
and creates an observable Device Service session. The guest application is
unchanged. The raw and display replies share a capture sequence; an independent
Pillow transpose matches every output pixel. Evidence ZIPs include the raw PNG
and matching controller metadata before stop; history remains available.
The five retained frames were also replayed through the final service code.

The first two guest captures precede two small service changes: explicit
`coordinate_space` in persisted metadata and rejection of empty `orient` query
values. Their controller observer and pixel-transform implementation are
identical. The [bounded summary](summary.json) records both source identities,
all raw/normalized firmware hashes, runtime hash, capture/ZIP hashes, controller
geometry, independent comparisons and cleanup booleans. It excludes raw frames,
logs, session identities and host paths.

The native patch exposes a read-only observer and monotonic generation. A
changed generation across capture yields `unstable`, including A-to-B-to-A
changes. Mirror states are explicit; unsupported/legacy controllers remain
`unknown`. Those states preserve raw capture but reject the optional rotation.
No raw scanout, guest RAM write, physical 3D texture or touch coordinate changes.
The host C control executes the actual MADCTL/reset handler and observer after
full patch replay, including partial-window invariance and read-only behavior.
Host/API regression groups passed 51 and 141 tests respectively.

The initial isolated-service prerequisites/readiness failures remain recorded.
An additional untouched UIFlow reference UART probe did not synchronize with
the REPL and was stopped with its lease released. It supplies no guest mirror
or reset proof; those cases have host C evidence only. None of these failures
is rewritten as a passing firmware run.

Reproduce with the [same-BIN fixture](../../../tests/firmware/frame_presentation/README.md).
The API contract is in [Device Service API](../../device-service-api.md) and
[OpenAPI](../../device-service.openapi.yaml). Full native matrix, integrated
platform checks and resident deployment are separate gates owned by the parent
workstream. Browser-WASM and physical hardware were not run for this change;
other application features and physical display properties are not claimed.
