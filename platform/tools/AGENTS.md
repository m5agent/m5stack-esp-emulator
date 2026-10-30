# Service and Python tools

The [root guidance](../../AGENTS.md) applies. This directory owns Device Service
HTTP/runtime orchestration, firmware intake, program/Preview state, network and
worker policy, and catalog/build tools. Use the [code map](../../docs/code-map.md)
to find the responsible module before extending `device_service.py`.

## Stable boundaries

- `serve.py` owns HTTP adaptation; `device_service.py` owns session orchestration.
  Existing `device_service_*` parser modules are deliberately separate. Preserve
  their compatibility re-exports, exception identity, error code/status/payload,
  defaults and validation order when refactoring.
- Keep validation/parsing separate from process launch and mutation. Preserve
  fail-closed checks for manifests, capabilities, runtime ACLs, image layouts,
  storage ownership and security configuration.
- Session/worker lifecycle changes must retain lease/generation ownership,
  idempotency, cancellation, restart/reattach fences, bounded timeouts and
  cleanup of owned processes/companions. A successful control request is not
  proof that a guest application completed.
- A worker fence for plain QEMU proves termination of the owned process. A
  `qemu-unified` fence also needs that session's HTTP fixture, BLE peer and pcap
  finalization; neither proves unrelated external effects or controller state.
- Program/Preview changes must preserve same-guest and Run identity, revision
  hashes, CAS, single-owner UART, late-response fencing and immutable evidence.
  Do not perform UIFlow user code on the host. A frame-cache sample must remain
  bound to its generation; default evidence capture remains fresh.
- `unit_runtime.py` bridges declared inputs and QOM observations. It must not
  implement a substitute Python peripheral protocol or synthesize guest output.
- Network grants are bounded protocol/address-or-CIDR/port endpoints. Preserve
  minimum IPv4 `/16` and IPv6 `/48` prefixes, special-use/SLiRP rejection and
  IPv4-mapped handling. Domain suffixes match label boundaries; every resolved
  answer must be bound to an allowed endpoint. Host isolation tests do not grant
  guest IPv6, RF or untrusted-firmware sandbox claims.

The API and lifecycle contract is in
[device-service-api.md](../../docs/device-service-api.md) and
[device-service.openapi.yaml](../../docs/device-service.openapi.yaml).

## Verification

Run the affected `platform/tests/test_<area>.py` modules first. Parser extraction
also needs original import/re-export and error-contract checks; lifecycle,
ownership, auth and retention changes need failure/cancellation tests, not only
the successful HTTP response. Broaden under the root PR/shared-platform rule.

When a public API changes, update Markdown/OpenAPI and their contract tests
together. When adding a top-level tool, update the complete inventory in
`docs/code-map.md`. Do not add a new handwritten status/count table here.

Catalog, peripheral, runtime-coverage and profile tools are cross-directory
contracts. Edit their declared source registries; regenerate only outputs owned
by a generator, such as device JSON/README files, rather than patching those
outputs. `project_snapshot.py --write` runs after the final source/document
edits, followed by `--check`.

For live testing, use the root routing rules and a separate port/state/token;
never reuse the user's `8787`/`8830` service. Read backend readiness before
creating a session: a static catalog response does not prove `.work/` assets
are available. Use the service's evidence-before-stop/history workflow.
