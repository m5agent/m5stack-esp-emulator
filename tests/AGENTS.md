# Runtime regression and evidence fixtures

The [root guidance](../AGENTS.md) applies. Use [the test index](README.md) and
[the code map](../docs/code-map.md) to select a lane: UIFlow2/device, firmware,
network/worker, Unit or independent Linux backend. Platform unit/Node contracts
live separately in `platform/tests/`.

## Choose the execution route

User-application and general agent-triggered firmware behavior tests use a
visible, dedicated Device Service `/api/v1` session. Explicit browser-WASM work
uses an isolated exported site or authorized Pages URL. Keep those results and
their identities separate.

Direct runners here are allowed for developing or reproducing checked-in
regressions. They are not a shortcut for an arbitrary uploaded application.
Read each case's README and CLI before running it; `.work/` assets, host tools
and backend/profile availability must be established. Missing prerequisites mean
`NOT RUN`, not a passing static substitute.

## Native peripheral regression loop

Start with the affected case:

```sh
PYTHONPATH=.work/py python3 tests/uiflow2/run_peripheral_matrix.py \
  --case <case-id> --out-dir /tmp/m5-<case-id>
```

For a controller shared by one device group:

```sh
PYTHONPATH=.work/py python3 tests/uiflow2/run_peripheral_matrix.py \
  --device <device-id> --out-dir /tmp/m5-<device-id>
```

Run the complete native matrix for shared native SoC/controller/build changes,
several affected device classes, a native matrix/release claim, or when targeted
cases cannot establish the regression boundary:

```sh
PYTHONPATH=.work/py python3 tests/uiflow2/run_peripheral_matrix.py \
  --out-dir /tmp/m5-uiflow2-peripheral-matrix
```

Browser-only changes use their browser gate; they do not inherit this matrix's
results. Do not run a full guest matrix for a documentation-only edit. Keep
owned long-running jobs observable and stop them when asked to pause; do not
stop unrelated sessions or the user's reserved services.

## Assertions and evidence

- Exercise the original guest driver/API through controller, bus, DMA/FIFO or
  endpoint data planes. No host fake values, direct private-ISR calls or manual
  polling that bypasses the user path under test.
- Bind input, protocol/controller observations, serial, actual frame/output
  and cleanup to one firmware SHA, runtime/profile and session/run. Application
  ready, upload accepted and process running are different assertions.
- Preserve ordering in `qom_steps`; use `qom_sequence_settle` and guest markers
  when state changes race. Same-VM probe state belongs in a dedicated
  `sys.modules` key unless the exact firmware proves another storage API.
- Negative controls must retain the behavior that makes them negative. A later
  PASS is a separate run; keep the first failure, observer/fixture mistakes,
  actual pulse durations and evidence gaps visible. Do not lower thresholds or
  lengthen inputs to turn an unobserved event into PASS.
- Keep raw logs, firmware/ROM, frame series and Flash snapshots outside source
  Git. A reusable test takes explicit artifact identities; ordinary contract
  tests do not depend on one machine's `.work/` cache.
- Browser teardown measures real Worker targets before context closure;
  service teardown requests evidence before stop and retains history with
  `purge=0`. Neither lane establishes physical-hardware behavior.

Register new runtime cases and their exact models in
`platform/peripherals/runtime-coverage.json` and `catalog.json`, including the
device-local case group. A runnable test/patch directory needs a README with
prerequisites, invocation and explicit scope. Update the ledger/current status
only to the extent established by the new evidence.
