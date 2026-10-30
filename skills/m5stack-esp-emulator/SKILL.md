---
name: m5stack-esp-emulator
description: Use a deployed M5Stack firmware simulator through its Device Service API to discover boards and Units, upload or compose compatible firmware, run virtual devices, change modeled sensor environments and device inputs, inspect serial/screens/controller/network/Flash evidence, and retain reproducible results. Use for firmware simulation and diagnosis beyond UIFlow or AIFlow.
---

# M5Stack firmware simulator

Use the operator's deployed Device Service, with explicit endpoint and credential configuration. This skill works independently of AIFlow and supports firmware simulation rather than physical flashing. The service is not a universal ESP32 emulator or an untrusted-firmware sandbox: admission and evidence remain specific to a board, firmware SHA, runtime/profile and controller path.

The bundled standard-library Python helper is standalone; it does not require the simulator source tree, QEMU, ROMs or another skill on the Agent machine:

```bash
python3 <skill-dir>/scripts/emulator.py --help
```

`<skill-dir>` means the directory containing this file. Set `M5_EMULATOR_BASE_URL` to the operator-provided origin and `M5_EMULATOR_TOKEN_FILE` to a readable private control-token file, or provide `M5_EMULATOR_TOKEN` through the environment. Optional `M5_EMULATOR_PUBLIC_URL` is the browser-facing origin. Never put credentials into a URL, prompt, package or evidence summary. No endpoint is selected implicitly.

Read [references/api-workflows.md](references/api-workflows.md) for exact requests and configuration; read [references/capabilities-and-evidence.md](references/capabilities-and-evidence.md) when choosing a runtime, interpreting model gaps, testing networking or reporting validation.

## Discover before choosing an execution path

```bash
python3 <skill-dir>/scripts/emulator.py discover
python3 <skill-dir>/scripts/emulator.py discover --device <device-id>
```

Check `supported`, `creatable`, `backend_ready`, `missing_runtime_files`, reference availability, runtime profiles, `program_modes` and model limitations. A healthy HTTP server and a catalog row do not prove a runnable device. Missing QEMU/ROM/firmware-preparation assets are operator setup failures; report them rather than claiming firmware failure or toggling metadata to pass.

For Units, query the exact host and use `host_admission.admitted`, allowed `port_ids`, documented topology and the session's frozen pins. Catalog presence, a 3D shell and protocol implementation are distinct from host admission and functional evidence. Check declared `inputs`, including `readOnly` and `creation_only`. Never guess bus addresses or copy a GPIO tuple from another board.

Choose the path matching the user's actual firmware and goal:

| Goal | Path |
| --- | --- |
| Test a known reference image | Create a session only when its cached reference exists; omit uploaded firmware deliberately. |
| ESP-IDF, Arduino, MicroPython or another full-flash image | Upload artifact(s), compose/import explicit compatible firmware metadata, then create a session with its `firmware_id`. |
| Board plus WiFi/BLE in one guest | Use the device's admitted `qemu-unified` profile and same-session evidence. |
| Provisioning/network diagnosis | Use `runtime=network` explicitly; its separate execution cannot supply missing board evidence for another session. |
| Continuous UIFlow2 source/resource editing | Use the documented Preview → immutable checkpoint → Run flow; it needs an admitted UIFlow reference/compatible base and actual session capabilities. |

The separate `uiflow2-simulator` skill is the AIFlow-specific UIFlow2 workflow. It is optional; this skill's references explain the public API without importing AIFlow configuration or requiring that skill to be installed.

## Prepare firmware and create one owned session

Inspect chip, board profile, Flash/PSRAM, merged or segmented offsets, partition layout, eFuse/security mode and required capabilities. A filename or a caller's firmware-family label is not compatibility evidence. Preserve original artifact and normalized firmware SHA identities separately. Do not lower declared capability requirements merely to get past a model gap. Prefer versioned Manifest/package import when the image's compatibility metadata is available.

```bash
python3 <skill-dir>/scripts/emulator.py upload firmware.bin
python3 <skill-dir>/scripts/emulator.py compose --json firmware.json
python3 <skill-dir>/scripts/emulator.py --state .m5-emulator/run.json create --json session.json --wait 30
```

`firmware.json` and `session.json` contain explicit reviewed API fields; see the reference for minimal merged/segmented examples. Include only intended firmware and fixture files, never recursively upload a workspace. Units/wiring are fixed at creation; changing assembly requires a new session, not hotplug.

The state journal binds the origin, owned session and original creation request/idempotency key. A timeout may mean a session was created. Recover the original operation rather than discarding state and allocating duplicates. Use a separate state file per independent execution. Never stop, reset or inject input into another task's session.

In this repository, Agent functional tests require a dedicated Device Service with its own port, state directory and control token. Port `8787` is the user's testing service; do not use, stop or restart it for Agent tests. For another deployment, use the service explicitly authorized by that operator. Do not start QEMU, direct regression runners or firmware-review workers as a substitute for an observable service session.

## Observe real guest behavior and interact

```bash
python3 <skill-dir>/scripts/emulator.py --state .m5-emulator/run.json status
python3 <skill-dir>/scripts/emulator.py --state .m5-emulator/run.json observe --frame --out-dir artifacts/emulator
```

Use incremental serial offsets and actual guest output to identify compile/runtime errors, resets, boot loops and missing peripherals. `running` means the guest control plane is alive; it is not application READY. Use application-owned markers, expected data changes and actual frame pixels as separate checks. Open the returned PNG when the model can inspect images; otherwise state that visual review was not performed. Do not diagnose UI layout from a hash.

The helper's `request` command covers documented routes beyond its narrow convenience commands:

```bash
python3 <skill-dir>/scripts/emulator.py --state .m5-emulator/run.json request POST /api/v1/sessions/<owned-session-id>/input --json input.json
python3 <skill-dir>/scripts/emulator.py --state .m5-emulator/run.json request GET /api/v1/sessions/<owned-session-id>/network
```

Replace the ID with the journal's actual owned session. Build inputs from the deployed schema, and use Unit source/fixture inputs rather than writing outputs. QOM is a controller inspection/injection surface, not permission to fabricate driver return values. Record pre/post guest serial, frame and relevant device/Unit/controller state. Momentary key-down needs its corresponding release. For network faults, pcaps, Flash snapshots/diffs and Preview Runs, follow the reference's exact route and ownership/fencing rules.

For environment-driven applications, attach an admitted sensor Unit at creation and initialize its real guest driver. Change its published inputs during that same session: ENV III exposes temperature, relative humidity and pressure. Follow the [environment scenario example](references/api-workflows.md#environment-scenarios) to set initial conditions, apply successive conditions, and check fresh guest readings plus the expected UI/alarm/actuator behavior after each change. Record units, values, order and observation times; a requested ramp requires repeated timed inputs, not an assumed automatic weather simulation. Unit wiring changes require a new session. Environment inputs affect the selected attachment; do not assume they also change every sensor or board temperature.

Samples are not atomic across serial, frame, Unit and network endpoints. Correlate session/firmware/execution/revision identity and capture times. A retained last frame is historical; an unmatched frame or interrupted stream must remain unknown. UIFlow START does not mean app readiness, and same-VM replacement remains interrupt-only rather than a complete native/timer/IRQ/thread reset.

## Preserve evidence and release owned resources

```bash
python3 <skill-dir>/scripts/emulator.py --state .m5-emulator/run.json stop --out-dir artifacts/emulator --wait 20
```

The helper requests the evidence ZIP before stopping and uses `purge=0`, retaining metadata, serial and last frame. Mutable Flash is released by default; add `--retain-flash` only when raw Flash or snapshot/diff evidence is required. Report export or cleanup failures separately; a stop request is not proof of completed teardown. Explicitly renew a needed lease within service limits; reading the page or polling does not renew it.

Give the user the helper's live console URL and session ID in ordinary response text, plus local screenshots/results where useful. Do not invent a per-session browser deep link. A localhost URL works only on the service machine, and a shared control token does not create tenant isolation. Do not expose the service publicly to share a preview.

Report the actual firmware SHA, board/assembly, runtime/profile, input, relevant serial/frame/data-plane observations, evidence digest and cleanup state. Separate application failure, unsupported firmware/model/fixture, infrastructure failure and unconfirmed execution. A passing virtual path does not establish RF, power, acoustic, optical, mechanical, electrical, security-root or physical-memory equivalence. Hardware deployment, firmware approval/publication and worker/service administration need their own explicit authorization; this skill does not grant it.

License: [MIT](LICENSE).
