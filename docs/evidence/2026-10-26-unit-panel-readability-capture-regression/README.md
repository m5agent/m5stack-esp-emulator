# CardKB readability and screenshot preparation regression

This new offline contract preserves the earlier evidence directories unchanged.
The only product change is CSS for the `keys` input grid: adequate minimum
column width, caption-sized text and no word splitting. All complete key names,
50 physical key IDs, accessible names, event handlers and electrical mappings
remain unchanged. The complete 27-Unit Panel suite PASSes at 1440, 1024, 768
and 390 pixels, including per-key text-fit/no-wrap/ID checks and the existing
input, lifecycle, HUB, readback and release contracts. The 390/768 CardKB PNGs
were opened and visually checked; long labels remain readable on one line.

The bridge's screenshot path now scrolls to the page top and waits one browser
layout frame immediately before the native screenshot call. Its actual
preparation coordinates are recorded read-only on the snapshot. The fixture
first scrolls to the bottom, then verifies preparation coordinates `(0,0)` and
its sticky navigation at the resulting screenshot top. Playwright may then
align the target card to its own top; this native behavior is preserved. The
resulting PNG was opened and its navigation is at the top, not the middle.
The full bridge transport/readiness contract PASSes: 31 real HTTP POSTs and
12 trusted pointer events. These are fixture/browser results; firmware and
physical hardware execution are NOT RUN. No new Device Service session was
created for these changes. Fan attachments and mechanical behavior are unchanged.

Commands:
- `M5_UNIT_PANEL_OUT=.work/unit-panel-readability-20261026 node platform/tests/test_unit_panel.mjs`
- `M5_UNIT_WEB_BRIDGE_TEST_OUT=.work/unit-web-capture-regression-20261026-r3 node platform/tests/test_unit_web_bridge.mjs`

Earlier internal capture-test attempts remain unchanged. The first attempt
expected scrollY to stay exactly zero after Playwright's native card alignment
and correctly exposed that overstrict assumption. Final assertions check the
actual pre-screenshot preparation coordinates and sticky navigation placement.
