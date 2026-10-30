---
name: uiflow2-simulator
description: Preview and debug AIFlow-generated UIFlow2 MicroPython code on M5Stack virtual devices. Use inside AIFlow coding workspaces to select supported boards and Units, change modeled sensor environments and device inputs, inspect guest errors and screens, and share a live preview; physical deployment is a separate authorized workflow.
---

# AIFlow UIFlow2 virtual-device preview

Use this skill after writing or changing UIFlow2 code when the configured simulator can run the requested board/Unit combination. Use `uiflow2-coder` for firmware APIs and `uiflow2-ui-designer` for UI design when available. This skill runs code through the Device Service; it does not flash or push to physical hardware.

The bundled helper is standalone Python 3.9+ on macOS/Linux, with no third-party dependencies. Run it from the current project workspace:

```bash
python3 <skill-dir>/scripts/simulator.py --help
```

`<skill-dir>` is the directory containing this SKILL.md. Keep state in `.aiflow/`; put user-viewable results under `artifacts/simulator/`. Do not upload either as firmware resources.

This package is the AIFlow-specific UIFlow2 simulation workflow. The current AIFlow runtime uses `deploy_mode=agent` for a two-task confirmation gate: the first task creates and checks the preview without pushing; only a later explicit user confirmation authorizes hardware deployment. `none` disables simulator and device side effects in that runtime; `server` automatically pushes when coding finishes and cannot wait at this gate. Do not infer deployment confirmation from a simulation pass. This simulator helper itself never invokes a physical push.

Configure the simulator origin explicitly through `AIFLOW_SIMULATOR_BASE_URL` or an operator-created `config.local.json`; no endpoint or credential is bundled. The AIFlow operator provisions a separate readable `AIFLOW_SIMULATOR_TOKEN_FILE`. Agent-triggered functional tests use a dedicated Device Service with an independent port, state directory and control token; do not test against, stop or restart the shared service on port `8787`.

For workflows outside AIFlow, the sibling skill named `m5stack-esp-emulator` covers the general Device Service workflow (repository directory `skills/m5stack-esp-emulator/`). This package includes its own helper and reference and works without that sibling or the AIFlow source repository.

## Select the actual assembly

1. Run `discover`, then `discover --device <device-id>`. Choose the user's confirmed product. If unspecified, ask only when board choice changes the implementation; a proposed virtual demo can use a clearly stated supported board. Never silently replace an unsupported requested product with a different one and claim it passed.
2. Check the returned `program_modes`/`program_features`, backend readiness, Unit `host_admission.admitted`, permitted `port_ids`, host port pins and model limitations. Catalog presence, a visual model, and a successful import do not establish functional support. Do not hard-code the list of supported boards or Units.
3. Write an explicit assembly JSON, for example only if live discovery admits this pairing:

```json
[{"id":"motion","unit_id":"pir","port_id":"port-a"}]
```

Attachment IDs are local logical names, not hardware identifiers. Use the pins frozen in the created session for driver constructors. HUB children require the returned topology contract; do not infer addresses, channels or GPIOs. See [references/workflow.md](references/workflow.md) for inputs and limitations.

```bash
python3 <skill-dir>/scripts/simulator.py discover
python3 <skill-dir>/scripts/simulator.py discover --device cores3
python3 <skill-dir>/scripts/simulator.py --state .aiflow/simulator-state.json create --device cores3 --units-json assembly.json --ttl 600 --wait 45
```

Use one state file per preview. Creating a Preview prepares the reference firmware once. Poll `status` after a pending allocation; do not create duplicates. To change board, firmware or Unit wiring, close the old Preview and create a new one. There is no running hotplug.

## Submit complete code and resources

Submit an explicit file whitelist; do not recursively upload the workspace. Include every module and image/audio/config resource the application needs. Never include `.env`, credentials, `.claude`, `.aiflow`, `.git`, simulator evidence, or private host files. Do not send `boot.py`.

```bash
python3 <skill-dir>/scripts/simulator.py --state .aiflow/simulator-state.json run --project-dir . --file main.py --file ui.py --file res/img/logo.png --wait 30
```

For a single file, specify only `--file main.py`. Use `--manifest <json-file>` for explicit local-file to guest-path mappings. The entrypoint is `main.py`; pure bytecode dependencies are subject to guest compatibility. Do not assume stock firmware supports `main.mpy` as an entrypoint.

Each Run stores an immutable **complete** package revision and executes it in the same MicroPython VM. Keep the full whitelist on later submissions: the helper rejects accidentally omitted prior files. Use `--allow-delete` only for intentional removal from the new complete snapshot. Edit local files, submit again, and retain revision/Run identity in the result. Do not rewrite application logic to use host-side fake sensor APIs just to make it pass.

The helper persists idempotency keys before mutating requests. After a transport timeout or ambiguous response, retry the same command with the same files/state to recover the original receipt, or inspect status. Do not discard pending state, generate a new key, or assume the previous code never ran. On generation/owner conflict, inspect the current state and reconcile; do not fight another editor.

## Diagnose, interact and refine the UI

```bash
python3 <skill-dir>/scripts/simulator.py --state .aiflow/simulator-state.json inspect --out-dir artifacts/simulator --ready-marker APP_READY
python3 <skill-dir>/scripts/simulator.py --state .aiflow/simulator-state.json input --unit-json unit-input.json
python3 <skill-dir>/scripts/simulator.py --state .aiflow/simulator-state.json input --host-json host-input.json
```

`inspect` collects bounded incremental serial, actual device/Unit state and a Run-bound PNG. Use an application-specific READY marker only when the program prints it after initialization; do not interpret helper success, VM running, Run START or a boot logo as application success. Check the current Run's traceback and outputs before concluding whether the program worked. A long-lived UI loop need not reach DONE.

For screen work, open/read the returned local PNG when image inspection is available. Check actual target dimensions, clipping, font support, contrast, spacing and interaction states; revise the source and Run again. Read a fresh image after each meaningful UI change. If the current model cannot inspect images, report that visual review was not performed and provide the screenshot/live preview for the user. Do not infer visual quality from a PNG hash.

Input is fenced to the current Run. Use published host-control payloads or Unit `inputs`; respect `readOnly` and `creation_only`, and do not guess property names. Inspect again after each input and compare the guest log, Unit output and screen. A Unit fixture is simulated input, not a physical measurement.

For sensor applications, actively test the requested environment. An admitted ENV III can start with initial temperature/humidity/pressure, then receive changed conditions in the same running Preview using `input --unit-json`. Follow the [environment scenario example](references/workflow.md#environment-scenarios): check a baseline, changed conditions and recovery, including fresh driver readings and the expected display/alarm/actuator response at each step. Do not replace sensor reads with constants. Assembly changes require a new Preview; live environment values change only the selected modeled input and do not automatically propagate to other sensors.

Report the browser URL returned by the helper and its session ID so the user can select the visible session in **Live sessions**. A local-only URL works on the service machine; it is not a remotely accessible preview. Never put a Bearer token into a URL. The current AIFlow client exposes downloaded artifacts; it does not automatically embed the simulator or stream screenshots while the agent types.

## Keep preview lifecycle explicit

```bash
python3 <skill-dir>/scripts/simulator.py --state .aiflow/simulator-state.json status
python3 <skill-dir>/scripts/simulator.py --state .aiflow/simulator-state.json renew --ttl 600
python3 <skill-dir>/scripts/simulator.py --state .aiflow/simulator-state.json cancel --wait 20
python3 <skill-dir>/scripts/simulator.py --state .aiflow/simulator-state.json close --wait 30
```

Keep the bounded preview lease alive while the user is reviewing it, and state its expiry. Renew explicitly if review continues; do not promise permanent availability. Close previews no longer needed. Close requests the service's before-stop evidence ZIP receipt and retains history/logs/last frame while releasing guest resources. Check final close/evidence status; a close request alone does not prove cleanup or export succeeded.

Use Preview controls for managed sessions. Do not directly invoke QEMU, regression runners, the firmware-review control plane, or legacy session mutation routes. Do not stop or modify sessions belonging to another task. Same-VM replacement only interrupts the old program; native state, timers, IRQs, threads and peripheral state may survive. If that affects the result, create a fresh Preview explicitly and state why.

## Result and hardware handoff

Summarize the board/Unit assembly, firmware/revision/Run identity, observed behavior, error (if any), screenshot/live-preview location and lease expiry. Separate:

- code/guest exception;
- unavailable model, unsupported assembly or fixture;
- service/transport failure or unknown execution state;
- successful virtual execution and any unverified UI/physical behavior.

In the current AIFlow runtime, use `deploy_mode=agent` for the preview-first flow and finish the first task after reporting the preview. Wait for a later user message explicitly confirming deployment; then verify that the retained preview matches the current code/resources before a separately authorized `aiflow-device-push` action with the client's real target. `server` automatically pushes at task completion and this skill cannot pause it. `none` offers no simulator side effects in that runtime. Never substitute a virtual ID for a physical device ID. A simulation pass does not establish electrical, timing, RF, acoustic, optical or mechanical behavior. Other AIFlow versions must be checked against their actual mode/skill-selection policy rather than assuming these labels enforce a gate.

Read [references/workflow.md](references/workflow.md) for configuration, request limits, inputs and error recovery.

License: [MIT](LICENSE).
