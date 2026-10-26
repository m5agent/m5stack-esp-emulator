# Unit Web readiness and executable provenance regression

These are offline fixture/contract tests, not firmware execution or hardware
validation. The real UnitPanel is loaded from a local fixture server. The
controlled booting fixture exposes available QOM data with disabled inputs;
input, trusted touch and double-click calls must stay pending without a POST
until the fixture updates the real product session to running. A second fault
keeps an actual DOM input disabled even while the session is running; the
bridge must wait for that input to be enabled. The test then exercises the
existing transport/readback/empty-DOM rejection contract: 31 real HTTP POSTs
and 12 trusted pointer events PASS.

The Python suite passed 9 tests. It covers strict Linux `/proc/<pid>/exe`
resolution, no short-comm fallback on missing `/proc`, absolute macOS `ps`
paths, rejection of relative comm names, nested worker confirmation,
generation changes, unknown worker fields, required-hash failure receipts
and redacted browser failure receipts. Linux branch tests use controlled
filesystem mocks on the macOS host; native Linux execution is not claimed.

Commands: `node platform/tests/test_unit_web_bridge.mjs` and
`python3 -m unittest discover -s tests/units -p 'test_web_ui_bridge.py' -v`.
Exact changed test sources and hashes are retained in this directory.
