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
`docs/project-backlog.md`, and code/evidence entry points in
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

Do **not** run the full 67-case matrix after every small peripheral edit. Run
it only when:

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

- Tab5 remains `partial`: the closed-source `esp-emu 0.50.0` P4 backend lacks
  dynamic I2C/RTC injection, I2S/PCM, MIPI-CSI, USB Host, SDIO control and
  controller-level ST7123 touch.
- Tab5 is still usable for virtual `esptool write-flash`, UIFlow2 boot,
  framebuffer/touch tests, RS-485, C6 ESP-Hosted and static I2C probes. Do not
  describe `partial` as “unusable”; document the flashing layout and ROM/eFuse
  compatibility boundary when reviewing a production image.
- Core2 peripheral, UI, radio and unified runs use deterministic TCG/icount
  after the idle interrupt-WDT reproduction. Peripheral/UI matrices reject
  configured retries by default; the latest full matrix passed 67/67 cases
  with every case on its first attempt. RX8130/PCF8563 advance on the QEMU
  virtual clock so guest RTC sleeps remain coherent. This does not prove
  physical cache/PSRAM timing.
- S3/C6 use device-level QEMU WiFi MAC/DMA plus SLiRP in the 11 unified
  profiles. This is functional virtual networking, not a complete PHY, RF,
  antenna, WPA2/WPA3 or security model.
- Core2 exposes environment-gated `core2-unified` with OpenMAC WiFi and
  UART1 HCI-offload BLE when `M5_CORE2_RADIO_QEMU` selects the matching QEMU.
  DHCP, controlled HTTP, public DNS/HTTP and deterministic TCG/icount startup
  are validated.
- The standalone stock Core2 UIFlow2 native-VHCI runner uses a GDB bridge to
  hand HCI to Bumble and passed external NUS GATT 5/5 without rebuilding for
  UART HCI. The extended `unified_core2` runner also combines board, frame,
  touch, audio, QOM, WiFi/public network and native-VHCI BLE in one guest,
  3/3. Device Service `core2-native-vhci` now exposes the same path in one
  `/api/v1` lease with frame/QOM/pcap/peer/bridge evidence. This is
  stock-firmware controller-boundary evidence, not a bit-exact Espressif BT
  baseband/controller model. The GDB backend and physical cache/PSRAM
  equivalence remain open.
- The separate `esp-emu` `runtime=network` lane is for diagnosis, provisioning
  portals and unreworked firmware. It does not provide same-instance board
  framebuffer/input/QOM evidence.
- Linux `egress=allowlist` enforces exact IPv4 IP/protocol/port with nftables
  input/output default-drop rules. External IPv4 uses a per-session veth and
  temporary NAT table; required DNS/HTTP/HCI/GDB loopback ports are explicit
  internal exceptions. External IPv6, CIDRs and domain-to-multiple-IP grants
  are not implemented and must fail rather than become implicit allow rules.
- `user,restrict=yes` and loopback `hostfwd` are not an untrusted-firmware
  sandbox. The Linux fail-closed namespace runner and guest path are validated;
  filesystem/resource isolation and formal worker/VM lifecycle remain open.

## Remaining work

Current device capability and the latest validation snapshot are maintained in
`docs/project-status.md`. Only unfinished work belongs in
`docs/project-backlog.md`.

The main open streams are:

- Linux namespace CI integration, DHCP renewal, real AP loss/recovery, a
  two-device lab fabric and external IPv6 endpoint enforcement;
- production Core2 VHCI backend, bit-exact BT controller and physical
  cache/PSRAM equivalence, coexistence and soak;
- SPIFFS inventory, runtime permissions/license policy, production
  security-key flows, streaming upload and broader cross-firmware compatibility;
- remote worker supervision, warm pools, multi-host scheduling and hardened
  untrusted-firmware isolation;
- Tab5 missing P4 data paths behind the closed-source backend;
- physical-hardware validation and per-device visual fidelity.

The v1 local Device Service is implemented by `platform/tools/device_service.py`
and exposed by `platform/tools/serve.py`. It supports leased QEMU-backed ESP32
sessions, QEMU unified radio profiles, a partial Tab5 esp-emu session, the
separate network diagnostic lane, reference or uploaded firmware, and
serial/frame/input/QOM/evidence APIs, QEMU pcap summaries,
`network-fault` reconnect control, and versioned firmware-manifest intake.
CardputerZero remains an independent
Linux backend and is not managed by `/api/v1`. Its contract is
`docs/device-service-api.md` and `docs/device-service.openapi.yaml`.
