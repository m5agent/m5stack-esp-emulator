# AGENTS.md

## Project

This repository is an M5Stack multi-device firmware simulation and review
platform with a Device Center adapter. UIFlow2 is the strongest validated
firmware family, but generic full-flash firmware is a supported architecture
goal. It combines:

- device manifests under `devices/`;
- peripheral contracts under `platform/peripherals/`;
- ESP32 QEMU board models and patches under `patches/`;
- UIFlow2, generic-firmware and external probes under `tests/`;
- browser/Device Center surfaces under `platform/`.

The source of truth is the current worktree plus the generated validators, not
the README prose or previous chat summaries.

Current capability is summarized in `docs/project-status.md`, open work in
`docs/project-backlog.md`, dated validation history in
`docs/validation-ledger.md`, and code/evidence entry points in
`docs/code-map.md`. Topic documents explain or preserve a narrower result; they
must not override the current status/backlog pages.

## Non-negotiable rules

1. Virtual-device PASS and hardware PASS are distinct validation categories.
   Never describe a QEMU or `esp-emu` result as a physical-hardware
   measurement, but either category can satisfy the publication gate when the
   same firmware/user path and reproducible evidence are available.
2. Before an external-facing claim, release note, issue reply, PR/MR or public
   report, follow the M5Stack external verification gate in the managed
   `AGENTS.md`. A validated virtual device is accepted evidence; include the
   firmware hash, runtime/profile, input, serial, framebuffer and relevant
   data-plane results.
3. Do not bypass the emulated SoC controller, DMA/FIFO/endpoint or board wiring
   with Python-level fake values. A peripheral is not `simulated` unless its
   data plane and device-local runtime evidence exist.
4. Do not commit credentials, tokens, private endpoints, serial numbers, MAC
   addresses or firmware/ROM binaries.
5. Do not use `git add -A`. The worktree can contain unrelated user assets or
   experiments; stage an explicit file whitelist.
6. Do not describe the repository as UIFlow2-only. Accept another firmware only
   when its chip, board profile, controller coverage, flash/partition layout,
   eFuse/security mode and merged or segmented image are explicit and compatible.

## Validation strategy

### Every change

Run the narrowest relevant checks:

```bash
PYTHONPATH=platform/tools python3 -m unittest discover \
  -s platform/tests -p 'test_*.py'
python3 platform/tools/runtime_coverage.py --check
python3 platform/tools/peripheral_catalog.py --check
python3 platform/tools/qemu_profiles.py --check
python3 platform/tools/project_snapshot.py --check
```

### Peripheral change

Run only the affected matrix cases first:

```bash
PYTHONPATH=.work/py python3 tests/uiflow2/run_peripheral_matrix.py \
  --case <case-id> --out-dir /tmp/m5-<case-id>
```

For shared QEMU controller changes, run the affected device group:

```bash
PYTHONPATH=.work/py python3 tests/uiflow2/run_peripheral_matrix.py \
  --device <device-id> --out-dir /tmp/m5-<device-id>
```

### Milestone/full regression only

Do **not** run the full matrix after every small peripheral edit. Run it only
when:

- the change touches shared SoC/QEMU controllers or builds;
- a release or public handoff is requested;
- several device classes changed together;
- targeted cases cannot establish the regression boundary.

Full matrix:

```bash
PYTHONPATH=.work/py python3 tests/uiflow2/run_peripheral_matrix.py \
  --out-dir /tmp/m5-uiflow2-peripheral-matrix
```

Stop background full-matrix/QEMU jobs when the user asks to pause; do not leave
stale `qemu-system-*` processes running.

### Iteration cost

The main cost of peripheral work is not typing the model. It is usually:

- finding authoritative datasheet or schematic evidence for register maps,
  addresses, pins and controller topology;
- reproducing the exact UIFlow2 or vendor driver path through I2C, SPI, I2S,
  DMA, CSI, USB or SDIO;
- debugging guest/host ordering and boot races;
- preserving reproducible logs, screenshots, PCM and patch evidence.

A full matrix run takes roughly 20–30 minutes. Targeted iteration is commonly
3–5 times faster, so use the narrow loop until a milestone boundary is reached.
Pausing a full run does not relax the release gate: record the latest full run
as `NOT RUN` and rerun it before a full-matrix or release claim.

Before implementing a new peripheral, identify the official hardware evidence
and the real driver path first. If the closed-source backend has no usable
controller or injection interface, mark the model `partial` with a concrete
blocker instead of spending more time on host-side workarounds.

## Peripheral contract

- Every non-display capability in `devices/catalog.source.json` must map to a
  component in `platform/peripherals/catalog.json`.
- Every simulated model needs a data plane, injection/source interface and
  `tested_devices`.
- Every matrix/external case must appear in `case_models`.
- Every simulated component on a device needs a device-local case; do not
  inherit coverage from another board.
- `partial` and `planned` models need an explicit blocker. Incomplete devices
  need a dated allowlist entry and must not be called complete.
- Runtime state transitions belong in `qom_steps`; use
  `qom_sequence_settle` and serial wait markers where ordering matters.

## Virtual-device functional-test routing

- General firmware functional tests, including uploaded UIFlow2 images, must
  use the Device Service at `/api/v1` on port `8787`: upload/compose firmware,
  create a visible session, collect serial/frame/state/input/QOM evidence, and
  stop it with `purge=0` so metadata, logs and the last frame remain in history.
  Request the evidence ZIP before stop. The full mutable virtual Flash is
  released on stop by default; add `retain_flash=1` only when flash
  snapshots/diffs or the raw image are part of the required evidence.
- Do not start `run_profile_ui_test.py`, `run_peripheral_matrix.py`, or QEMU
  directly for an agent-triggered functional test. Direct runners are for
  repository regression development and do not create observable sessions.
- The firmware review control plane is only for explicit M5Burner pending
  review, approval, rejection, or publication workflows. A functional test is
  not a firmware review request.
- Calls made through the review control plane must still use Device Service
  sessions, so the same execution is visible in Live sessions and retained
  after the review worker finishes.

## Device onboarding

1. Add the device to `devices/catalog.source.json`.
2. Add the device/model contract to `platform/peripherals/catalog.json`.
3. Add all non-display components, interfaces, addresses/GPIOs and official
   documentation or schematic evidence.
4. Add a QEMU board profile or an external backend.
5. Add a device-local UIFlow2 probe for every model.
6. Register matrix/external cases in `runtime-coverage.json`.
7. Add targeted cases to the matrix runner and `case_models`.
8. Run the device-level cases; run the full matrix only for the milestone gate.

The device templates are:

- `platform/peripherals/device-template.json`
- `platform/peripherals/model-template.json`

## QEMU patches

- Patch base and ordering are documented in
  `patches/qemu-m5stack-peripherals/README.md`.
- Generate patches from the exact QEMU worktree and verify with
  `git apply --reverse --check`.
- Do not include unrelated dirty files from the QEMU worktree.
- Rebuild with:

```bash
ninja -C .work/M5StopWatch-QEMU/build/qemu/build qemu-system-xtensa
```

## Work logs

For verifiable engineering work, archive the result in
`~/Documents/agent-work-logs` according to that repository's
`docs/work-record-workflow.md` and `docs/redaction-policy.md`. Reproducible
virtual-device validation may be published in `records/` after passing the
external verification gate; keep raw internal-only logs and unreproducible
diagnostics in `internal/records/`.

## Known boundaries

This file defines stable engineering rules. It is not a second current-status
page. Do not add per-release profile counts, test counts, sample counts,
long-soak results or per-device PASS tables here; those facts change and must
remain in their authority documents:

- current capabilities, evidence level and known risks:
  `docs/project-status.md`;
- unfinished tasks, dependencies and acceptance:
  `docs/project-backlog.md`;
- dated milestones and exact URLs/hashes:
  `docs/validation-ledger.md`;
- known runtime-model gaps and closure conditions:
  `docs/runtime-model-gap-register.md`;
- machine-readable device/task/test inventory:
  `docs/project-snapshot.md`.

Stable boundaries that must survive count changes:

- Virtual-device PASS is not hardware PASS. QEMU/esp-emu functional networking
  does not establish RF, antenna, channel/rate/roaming, power, acoustic, optical,
  mechanical or electrical behavior. The S3 WPA2-PSK path proves RSN, EAPOL,
  pairwise CCMP and guest DHCP/DNS/TCP delivery only; WPA3-SAE, group-key
  multicast and physical-link security remain separate validation questions.
- A full-flash image is supported only when chip, board profile, flash/PSRAM,
  eFuse/security mode, partition layout, controller coverage and merged or
  segmented image metadata are explicit and compatible.
- `runtime=network` is a diagnostic/provisioning lane. Do not splice its result
  with a separate board run to claim one-device functional PASS.
- Worker partition fencing has separate evidence layers. The plain QEMU lane
  proves the worker-local QEMU process was stopped. The `qemu-unified` lane
  additionally requires the same session's HTTP fixture, BLE peer and pcap
  summary to terminate or finalize. Neither lane proves
  guest/controller-internal state or external effects not owned by the worker.
- `core2-native-vhci` is a diagnostic/compatibility path; new Core2 work uses
  `core2-native-hci`. The current native-HCI boundary is a validated virtual
  controller/HCI path, not a bit-exact Espressif baseband or RF model.
- Core2 physical cache/PSRAM timing and the difference between board PSRAM
  capacity and the current QEMU memory model remain separate validation
  questions. A launch flag or QOM property alone is not a physical-memory PASS.
- Tab5 remains `partial` while the closed-source P4 backend lacks required
  dynamic I2C/RTC, I2S/PCM, MIPI-CSI, USB Host, SDIO and controller-level
  ST7123 data planes. `partial` means usable in its documented subset, not
  unusable.
- `user,restrict=yes`, loopback `hostfwd`, trusted-host user networking and the
  current namespace runner are not an untrusted-firmware sandbox. Production
  review still requires disposable isolation, resource limits, auditable
  evidence and fail-closed policy creation.
- Linux egress policy covers IPv4 and IPv6 `protocol + address-or-CIDR + port`
  endpoints. IPv4 rules are at least `/16` and IPv6 rules at least `/48`;
  broad, special-use, IPv4-mapped and QEMU SLiRP synthetic CIDRs fail closed.
  Controlled domain suffixes match only on DNS label boundaries, and every
  suffix answer must be explicitly bound to an address covered by an allowed
  endpoint. A domain grant must never authorize arbitrary addresses returned by
  an outside resolver. Guest IPv6 availability must still be proven per
  firmware configuration and is not inherited from the host policy test.
- Closing one firmware family, sample or model gap never grants the same
  result to another firmware SHA, board profile or controller path.

## Remaining work

The only execution queue is `docs/project-backlog.md`. Read it at task start
and do not recreate a second ordered list here. The stable P0 families are:

- network isolation, DNS/egress policy, packet evidence, negative connection
  tests, recovery and multi-device service productization;
- Core2 native controller, long-duration WiFi/BLE coexistence, cache/PSRAM and
  physical equivalence;
- FirmwareManifest, WebBurner intake, security configuration, capability
  mismatch and runtime model-gap handling across firmware families;
- same-implementation-path hardware validation for externally published
  claims.

When a task closes, update the generated snapshot and the relevant authority
document, append dated evidence when necessary, and archive reproducible work
in `agent-work-logs`. Do not mark a whole workstream complete from a passing
subcase.

The v1 local Device Service is implemented by `platform/tools/device_service.py`
and exposed by `platform/tools/serve.py`. It supports leased QEMU-backed ESP32
sessions, QEMU unified radio profiles, a partial Tab5 esp-emu session, the
separate network diagnostic lane, reference or uploaded firmware, and
serial/frame/input/QOM/evidence APIs, QEMU pcap summaries,
`network-fault` reconnect control, and versioned firmware-manifest intake.
CardputerZero remains an independent
Linux backend and is not managed by `/api/v1`. Its contract is
`docs/device-service-api.md` and `docs/device-service.openapi.yaml`.
