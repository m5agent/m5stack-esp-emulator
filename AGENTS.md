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
  3/3. The canonical `core2-native-hci` profile now combines
  frame/QOM/WiFi/public-network/GATT/pcap/evidence in five independent
  `/api/v1` leases with no GDB bridge. Legacy `core2-native-vhci` remains as
  a diagnostic/compatibility path because its repeated-lease result was
  `1/2`. This is stock-firmware controller-boundary evidence, not a bit-exact
  Espressif BT baseband/controller model. Physical cache/PSRAM equivalence
  remains open.
- The QEMU native-HCI replacement has passed its staged gates: `HCI-1` host transport,
  `HCI-2` H2C, `HCI-3a` diagnostic callback and `HCI-3b` full external NUS
  GATT pass. `HCI-4` also passes five independent Device Service `/api/v1`
  leases with the canonical `core2-native-hci` profile: frame, QOM, WiFi
  DHCP/HTTP, public DNS/HTTP, external NUS GATT, pcap and evidence bundle all
  pass without a GDB bridge. `0003-esp32-native-hci-api-transaction.patch`
  owns H2C at the firmware API boundary, delivers event/ACL data through the
  real HLI `g_rw_schd_queue`/meta queue and interrupts the guest controller
  task.
  `0004-xtensa-ccount-tb-yield.patch` preserves deterministic CCOUNT polling.
  With a 15-byte probe (17-byte ATT PDU), discovery, subscription, write,
  Python GATT handler, notification and Bumble ACK pass in 5/5 independent
  runs. The earlier 21-byte probe failed because its 24-byte ATT PDU exceeded
  the guest default MTU of 23; it was not a controller ACK defect.
  `core2-native-vhci` remains a compatibility/diagnostic profile because its
  GDB bridge is not a stable production backend. Bit-exact
  controller/baseband, coexistence and physical cache/PSRAM equivalence
  remain open. Do not describe this virtual HCI boundary as RF or a finished
  bit-exact controller.
- `HCI-4` is a five-lease functional baseline. The later hold-enabled crash
  was traced to QEMU guest-call context: nested calls did not restore all
  caller-saved Xtensa sregs, and HLI allocation/callback injection could run
  from a non-halted cache-disabled WiFi/controller context. `0005` fixes both.
  Two independent `5×10s` hold batches pass `10/10`, and three `60s` holds
  pass `3/3`. Two independent `120s` holds also pass `2/2`, with
  `hli-errors=0` and empty HLI/meta queues in every attempt.
  Historical
  `semphr_give_wrapper`, `PC=0` and Cache-error evidence remains tracked.
  This closes the repeated-start/two-minute virtual gate, not multi-hour soak,
  physical cache/PSRAM equivalence, more than ten reconnect cycles or
  bit-exact controller behavior. Ten-cycle same-guest reconnect now passes in
  three independent stock-firmware leases, with 297/297 HLI posts/consumption
  in each lease and all connection/L2CAP/GATT pools back at their free
  baseline. A historical 30-second wait cap in Device Service terminated a
  valid ten-cycle peer after cycle 6 started; the wait now uses the session
  ready timeout and has a regression test. The former `ack returned 12`
  failure was caused by the external Bumble compatibility layer returning an
  invalid Command Status for the no-response
  `HCI_Host_Number_of_Completed_Packets (0x0c35)` command; the next
  `LE Set Advertising Data` consumed that stale ACK. Do not reintroduce a
  response for `0x0c35`, and keep the no-response unit test.
- The separate `esp-emu` `runtime=network` lane is for diagnosis, provisioning
  portals and unreworked firmware. It does not provide same-instance board
  framebuffer/input/QOM evidence.
- Linux `egress=allowlist` enforces exact IPv4 IP/protocol/port with nftables
  input/output default-drop rules. External IPv4 uses a per-session veth and
  temporary NAT table; required DNS/HTTP/HCI/GDB loopback ports are explicit
  internal exceptions. External IPv6, CIDRs and domain-to-multiple-IP grants
  are not implemented and must fail rather than become implicit allow rules.
- The two-guest lab fabric is a separate virtual-device path. The passing
  fixture runs two StickS3 QEMU guests through an L2 switch inside a private
  Linux network namespace, with reserved DHCP addresses, real guest TCP,
  two-sided pcap, MAC-bound client slots and no host/public/metadata route.
  The QEMU evidence uses a socket switch; the namespace bridge/TAP plus DHCP
  helper is an independently tested host primitive. Neither result is
  RF/WPA2/WPA3 validation or a production multi-tenant worker boundary.
- `user,restrict=yes` and loopback `hostfwd` are not an untrusted-firmware
  sandbox. The Linux fail-closed namespace runner and guest path are validated;
  filesystem/resource isolation, companion/evidence continuity and formal
  worker/VM lifecycle remain open. The local worker registry covers identity,
  generation, heartbeat, drain/resume and restart lease classification. A
  running local QEMU is re-attached only after PID start-time, session QMP
  socket ownership and `query-status=running` checks. The remote directory and
  durable job queue add idempotent enqueue, capability-matched claim, lease
  heartbeat, expiry retry and stale/stopped worker reconciliation. The
  separate `worker_agent.py` executes a claimed job through the public HTTP
  API, downloads and hashes an evidence ZIP, stops the session and reports the
  terminal result on the same host. When an API token is configured,
  worker-only mutations require a worker/generation-derived HMAC over method,
  path, timestamp, nonce and body. Cross-host TLS/mTLS and credential rotation
  remain open.

## Remaining work

Current device capability and the latest validation snapshot are maintained in
`docs/project-status.md`. Only unfinished work belongs in
`docs/project-backlog.md`.

Dynamic platform-test counts and full-matrix counts belong only in
`docs/project-status.md`; dated historical values belong in
`docs/validation-ledger.md`. README, the documentation index and the workflow
ledger should link to those pages instead of copying values that will drift.
When a QEMU profile or device catalog records validation date/status, the two
snapshots must agree and CI enforces that cross-check.

The main open streams are:

- cross-host job execution, TLS/mTLS and credential rotation,
  companion/evidence continuity, cross-host QEMU re-attach, multi-host
  scheduling and external IPv6 endpoint enforcement;
- Core2 more than ten reconnect cycles, multi-hour coexistence, bit-exact BT
  controller/baseband, physical cache/PSRAM equivalence and hardware
  validation;
- runtime permissions/license policy, production security-key flows and
  broader cross-firmware compatibility;
- warm pools, multi-host scheduling and hardened untrusted-firmware isolation;
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
