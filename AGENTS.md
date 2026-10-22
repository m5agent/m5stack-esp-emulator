# AGENTS.md

## Project

This repository is an M5Stack multi-device UIFlow2 simulator and Device Center
adapter. It combines:

- device manifests under `devices/`;
- peripheral contracts under `platform/peripherals/`;
- ESP32 QEMU board models and patches under `patches/`;
- UIFlow2 and external probes under `tests/`;
- browser/Device Center surfaces under `platform/`.

The source of truth is the current worktree plus the generated validators, not
the README prose or previous chat summaries.

## Non-negotiable rules

1. Simulation PASS is not hardware PASS. Never describe a QEMU result as
   real-hardware validation.
2. Before an external-facing claim, release note, issue reply, PR/MR or public
   report, follow the M5Stack external verification gate in the managed
   `AGENTS.md`. If the target hardware is unavailable, validate the same path
   on a substitute device or keep the result internal.
3. Do not bypass the emulated SoC controller, DMA/FIFO/endpoint or board wiring
   with Python-level fake values. A peripheral is not `simulated` unless its
   data plane and device-local runtime evidence exist.
4. Do not commit credentials, tokens, private endpoints, serial numbers, MAC
   addresses or firmware/ROM binaries.
5. Do not use `git add -A`. The worktree can contain unrelated user assets or
   experiments; stage an explicit file whitelist.

## Validation strategy

### Every change

Run the narrowest relevant checks:

```bash
PYTHONPATH=platform/tools python3 -m unittest discover \
  -s platform/tests -p 'test_*.py'
python3 platform/tools/runtime_coverage.py --check
python3 platform/tools/peripheral_catalog.py --check
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
`docs/work-record-workflow.md` and `docs/redaction-policy.md`. Keep
simulation-only findings in `internal/records/` until real-hardware
verification exists.

## Known boundaries

- Tab5 remains `partial`: the closed-source `esp-emu 0.50.0` P4 backend lacks
  dynamic I2C/RTC injection, I2S/PCM, MIPI-CSI, USB Host, SDIO control and
  controller-level ST7123 touch.
- Core2 has an intermittent flash/cache startup panic; retries may let a
  simulation case pass but do not prove the startup issue is fixed.
