# Repository guidance

This is an M5Stack multi-device firmware simulation and review platform.
UIFlow2 has the strongest validated coverage; compatible Arduino, ESP-IDF,
MicroPython and other firmware are also in scope. Read the current source and
generated contracts before relying on README prose or an earlier chat.

## Start here

| Question | Authority |
| --- | --- |
| Current capability and limitations | [Project status](docs/project-status.md) |
| Open work, priority and acceptance | [Project backlog](docs/project-backlog.md) |
| Dated results and exact execution identities | [Validation ledger](docs/validation-ledger.md) |
| Known runtime gaps and closure conditions | [Runtime model gaps](docs/runtime-model-gap-register.md) |
| Generated device/task/test inventory | [Project snapshot](docs/project-snapshot.md) |
| Source and verification entry points | [Code map](docs/code-map.md) |

The backlog is the only execution queue. Keep dynamic counts, per-device PASS
tables and release history out of AGENTS files. Topic pages and historical
evidence do not override the authority pages above.

Read the applicable local guide before editing a complex area:

- [Service and Python tools](platform/tools/AGENTS.md)
- [Browser and model integration](platform/web/AGENTS.md)
- [Device catalog and onboarding](devices/AGENTS.md)
- [Runtime regression fixtures](tests/AGENTS.md)
- [QEMU and firmware patches](patches/AGENTS.md)
- [Documentation maintenance](docs/AGENTS.md)

Local guides add area-specific rules; they do not replace these shared rules.

## Preserve the workspace

- Preserve unrelated edits, assets, sessions and processes. Do not reset or
  stash the user's work to make a checkout clean. Use an isolated worktree when
  necessary and stage an explicit file whitelist; never use `git add -A`.
- Ports `8787` and `8830` belong to the user's testing services. Do not use,
  stop or restart them for agent tests. Use an agent-owned port and separate
  state directory/control token. Stop only processes and sessions you own.
- Do not commit credentials, private endpoints, device serial numbers, MAC
  addresses, firmware/ROM binaries or mutable Flash images.
- Keep raw ZIPs, traces, frame series, Flash/source snapshots and full command
  responses in ignored storage or a reviewed artifact archive. Commit bounded
  summaries, hashes and reproduction commands. `check_pr_scope.py` checks the
  entire branch history: each evidence summary is limited to 64 KiB and new
  evidence to 1 MiB per PR. Small curated documentation illustrations are
  allowed under [docs/AGENTS.md](docs/AGENTS.md); raw frame series are not.
- A fresh clone has no `.work/` runtime cache. Ordinary checkout tests must not
  require local raw evidence; historical external-evidence audits are separate
  opt-in checks.

## Verification and publication

Start with the narrowest affected tests. Use Python 3.12+ for repository tools
and checks; a pinned guest or build recipe may specify its own toolchain.
Run affected Python modules in `platform/tests/`, the relevant Node contracts
for browser changes, and the catalog/profile/coverage validators when their
inputs change. Documentation-only work uses documentation/link checks and
visual inspection; it does not require a guest run or native peripheral matrix.

Before a source-code PR or shared-platform handoff, run the full platform suite
and the affected validators:

```sh
PYTHONPATH=platform/tools python3 -m unittest discover \
  -s platform/tests -p 'test_*.py'
python3 platform/tools/runtime_coverage.py --check
python3 platform/tools/peripheral_catalog.py --check
python3 platform/tools/qemu_profiles.py --check
python3 platform/tools/project_snapshot.py --check
```

Full runtime matrices have a different purpose and cost. Follow
[tests/AGENTS.md](tests/AGENTS.md): run affected cases first, and broaden for a
shared runtime change or a corresponding release claim. Do not run a complete
guest matrix after every small edit. Record skipped or unavailable checks as
`NOT RUN`, with a concrete reason; static/build checks are not guest execution.

For an external claim, release note, issue reply or PR, bind each functional
result to the same firmware SHA, runtime hash/profile and device. Include the
actual input, serial, framebuffer or relevant output, controller/data-plane
observations, and cleanup. Keep native-service, browser-WASM and physical
hardware results separate. A later PASS never erases an earlier FAIL.

Use `virtual-device validation` for QEMU/esp-emu/browser execution. Such a run
can satisfy a functional publication gate, but cannot establish physical RF,
power, acoustics, optics, mechanics, electrical behavior, memory timing or
hardware security. One firmware/profile/controller result does not transfer to
another image, board or execution lane.

Before delivery, review the exact diff for unrelated changes, secrets, binary
assets, UTF-8 damage and unsupported claims. Run `git diff --check` and
`python3 platform/tools/check_pr_scope.py --base <base> --head HEAD` for a PR.

## Functional-test routing

- General firmware behavior tests, including uploaded UIFlow2 applications,
  use a dedicated Device Service `/api/v1` session so execution is visible and
  retained. Compose/upload firmware, collect same-session serial/frame/input/
  QOM evidence, request its ZIP before stop, and stop with `purge=0`. Mutable
  Flash is released by default; use `retain_flash=1` only when a Flash snapshot
  or diff is required evidence.
- Explicit browser-WASM validation uses the exported static site on an
  agent-owned port or an authorized Pages URL. Retain browser-local session
  identity, source/runtime/firmware hashes, actual guest input/output and
  iframe/Worker cleanup. This lane has no Device Service lease; do not splice
  native-service results into it.
- Direct QEMU, `run_profile_ui_test.py` and `run_peripheral_matrix.py` are for
  checked-in regression development and reproduction, not an alternative path
  for testing a user's arbitrary application. The firmware-review control
  plane is only for explicitly requested M5Burner review/publication work; its
  workers must still create observable Device Service sessions.
- When asked to pause runtime work, stop owned background matrix/QEMU jobs.
  Do not leave stale guests running or terminate unrelated user sessions.

## Firmware and peripheral contracts

- Accept firmware only when chip, board profile, Flash/PSRAM, partition layout,
  eFuse/security mode, controller coverage and merged/segmented image metadata
  are explicitly compatible. Successful intake is not application readiness.
- Never bypass the emulated SoC controller, bus, DMA/FIFO/endpoint or board
  wiring with Python-level fake values. A `simulated` component requires its
  data plane, injection/source interface and device-local runtime evidence.
- Every non-display catalog capability maps to a peripheral component; every
  simulated component has a device-local case, `case_models` mapping and
  `tested_devices` entry. `partial`/`planned` need concrete blockers and the
  dated incomplete-device allowlist. See the
  [peripheral contract](platform/peripherals/README.md).
- Preserve runtime state ordering with `qom_steps`, `qom_sequence_settle` and
  serial markers where needed. Same-VM UIFlow probes should keep nonce state in
  a dedicated `sys.modules` key, not attributes on built-in `sys`/`os` modules
  without proof on that exact firmware.
- `runtime=network` is a diagnostic/provisioning lane. Core2's native-HCI path
  is not bit-exact baseband or RF; native-VHCI remains diagnostic. Tab5 and
  CardputerZero use separate backends and cannot inherit ESP32 results.
- Trusted-host networking, `user,restrict=yes`, loopback forwarding and the
  namespace runner are not an untrusted-firmware sandbox. Do not weaken
  fail-closed policy or infer guest IPv6 support from host policy tests.

## Closeout records

Update the relevant authority page and generated snapshot when a task changes
their facts; append dated evidence without closing a whole workstream from one
passing case. Archive verifiable work in `~/Documents/agent-work-logs` following
that repository's `docs/work-record-workflow.md` and `docs/redaction-policy.md`.
Public reproducible summaries belong in `records/`; raw or unreproducible
internal diagnostics belong in `internal/records/`.
