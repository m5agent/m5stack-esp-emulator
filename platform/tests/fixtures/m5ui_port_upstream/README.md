# Pinned UIFlow2 LVGL event-loop regression source

`port.py` is the complete, unchanged upstream file from UIFlow2 commit
`3a86d8f611b3639cca755a933e01a5a829771ef1`. `source.json` records its exact
repository path, public source URL and SHA256, together with the unchanged MIT
`LICENSE` from that commit. The source retains M5Stack's SPDX copyright notice.

`test_m5ui_scheduler_patch.py` checks the preimage, applies the reviewable
`0026-m5ui-single-vm-schedule.patch` in a temporary directory, checks the resulting
hash and reverse applicability, then extracts and executes the actual
`event_loop` class from both sources. Controlled LVGL, clock, FreeRTOS Timer and
MicroPython queue interfaces exercise callback scheduling and lifecycle
behavior without requiring a local SDK checkout or `.work` cache.

Run from the repository root:

```sh
PYTHONPATH=platform/tools python3 -m unittest discover \
  -s platform/tests -p 'test_m5ui_scheduler_patch.py' -v
```

These are offline behavioral regressions. They do not establish browser, native
virtual-device or physical-hardware PASS, or first-stage C Timer coalescing.
