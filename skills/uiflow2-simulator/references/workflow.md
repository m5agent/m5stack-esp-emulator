# Configuration and operational details

The helper calls the configured Device Service `/api/v1` endpoints. It uses only HTTP APIs and packaged Python files, never another repository's runtime cache.

| Variable | Meaning |
| --- | --- |
| `AIFLOW_SIMULATOR_BASE_URL` | Service origin, e.g. `http://127.0.0.1:18787`. HTTP supports loopback or an explicitly configured RFC1918 IPv4 LAN address; public services require HTTPS. |
| `AIFLOW_SIMULATOR_TOKEN_FILE` | Operator-provisioned control-token file, readable by the agent runtime. Never print/read it into model text. |
| `AIFLOW_SIMULATOR_TOKEN` | Direct CLI-only alternative secret from the environment. Prefer token-file integration in AIFlow. |
| `AIFLOW_SIMULATOR_PUBLIC_URL` | Optional browser-accessible origin for the Live sessions link. This does not change the API destination or grant access. |

An AIFlow operator enables this package in the service's runtime Skill selection and configures the simulator origin. This distribution preserves the upstream `uiflow2-simulator` name and `AIFLOW_SIMULATOR_*` environment/CLI contract for the existing selector. Copying the package alone does not enable an integration that has not configured Skill selection and simulator access.

Use an explicitly configured, dedicated Device Service for agent functional tests. Its port, state directory and control token must be separate from the shared user service; do not test against, stop or restart port `8787`. For example, set `AIFLOW_SIMULATOR_BASE_URL=http://127.0.0.1:18787` only after an operator has provisioned that dedicated service. The helper has no implicit service target.

An optional operator-created `config.local.json` beside `SKILL.md` contains only service origins:

```json
{"base_url":"http://127.0.0.1:18787","public_url":"https://simulator.example.invalid"}
```

Nonempty environment configuration overrides this file. Do not include operator-local configuration in a distributable archive. Provision the control token separately through `AIFLOW_SIMULATOR_TOKEN_FILE`; that file must be readable on the machine running AIFlow, outside public project workspaces and Skill sources. Never package or paste the real token. Do not disable authentication or widen sandbox permissions to all hosts to make a request succeed. The helper honors the runtime's HTTP(S) proxy and `NO_PROXY` settings and refuses redirects, preserving network-sandbox routing.

For a user-confirmation flow in the current AIFlow runtime, use `deploy_mode=agent`: the first task runs and reports the preview without pushing, and a later explicit user confirmation authorizes the physical deployment step after checking that code/resources still match. The current runtime does not offer simulator side effects in `none`, while `server` pushes automatically at coding completion. Other versions must be checked against their actual selector and deployment policy. The helper only manages virtual Preview/Run resources; it cannot enforce a physical gate in an incompatible outer workflow.

## Packages

The helper's `--file` preserves paths relative to `--project-dir`; `--manifest` is a JSON object mapping local paths to guest paths. For example:

```json
{"main.py":"main.py","src/view.py":"view.py","assets/logo.png":"res/img/logo.png"}
```

An explicit manifest is the complete snapshot. Paths must stay inside the project; symlinks, traversal, hidden/internal files, sensitive configuration and `boot.py` are rejected. The service admits at most 64 files, 1 MiB total decoded data and a 2 MiB JSON envelope; source-only legacy requests have different limits. Guest paths are relative to the managed package root. The program's resource references must match those deployed paths. Pure-bytecode `.mpy` dependencies still need the actual firmware's version/small-int compatibility; native emitters are unsupported.

## Inputs and actual state

After `discover --device ...`, inspect the selected Unit's declared `inputs`, including `readOnly` and `creation_only`. `unit-input.json` contains the attachment `id` and a `values` object. For an admitted PIR exposing `motion`, an example is:

```json
{"id":"motion","values":{"motion":true}}
```

Host input uses the existing session input schema, such as a touch event only when supported by that target:

```json
{"kind":"touch","x":120,"y":100,"settle_seconds":0.3}
```

Touch above is a tap. For a held host key, use `{"kind":"key","key":"a","action":"down","settle_seconds":0.02}` and then the same payload with `"action":"up"`. Always send the matching release for explicit held keys. Use the service-returned controls and schema if they differ; not all boards expose touch or the same buttons. Preview input adds the current owner epoch/Run fence automatically. Do not call raw QOM to bypass an unsupported Unit. State/frame/serial are separate observations, not an atomic sample.

### Environment scenarios

To test a temperature/humidity application, discover the requested host and
choose an admitted `env-iii` with its returned port. For example, after live
discovery admits CoreS3 and that port, save `assembly.json` as:

```json
[{"id":"env","unit_id":"env-iii","port_id":"<admitted-port>","initial":{"temperature-c":25.0,"humidity-pct":50.0,"pressure-pa":101325}}]
```

Create a Preview using `create --device cores3 --units-json assembly.json`,
with this example's port replaced by the admitted value. Submit the complete
application package using `run`. Initialize the real `ENVUnit` driver using
the Preview's frozen pins; use the official UIFlow docs for the target
firmware's constructor/API. Do not add host fixture APIs or mock returned
sensor values in application code. The app must keep sampling for live
changes to be visible; a one-time boot read will not automatically refresh.

First `inspect` to capture the baseline, then save `env-input.json`:

```json
{"id":"env","values":{"temperature-c":35.0,"humidity-pct":80.0,"pressure-pa":100800}}
```

Apply it to the active Run and inspect again:

```bash
python3 <skill-dir>/scripts/simulator.py --state .aiflow/simulator-state.json input --unit-json env-input.json
python3 <skill-dir>/scripts/simulator.py --state .aiflow/simulator-state.json inspect --out-dir artifacts/simulator/hot-humid
```

The helper wraps this Unit command in Preview owner/Run fences; do not post
directly to its managed session. Wait for the sensor conversion and app
polling interval, then compare fresh serial, Unit controller/state and the
Run-bound PNG. Use schema units/limits: ENV III exposes Celsius, percent RH
and Pa, while UIFlow `ENVUnit.read_pressure()` returns hPa. Allow justified
sensor conversion/rounding tolerance. Verify the actual displayed values
and any application-defined threshold, alarm, color or actuator response.

Apply a recovery condition with the same `input` command and inspect again
to test stateful recovery. Record each condition, order and observation time;
for ramps/time-series, schedule explicit successive writes and observations.
These are modeled inputs for attachment `env`, not a global environment
automatically shared by other sensors. Changing live temperature/humidity
does not require another Run; adding/removing/rewiring Units requires a new
Preview. Unsupported variables/assemblies remain model gaps. An input
receipt alone does not establish that the app read or reacted to the values.

## Recovery

| Observation | Action |
| --- | --- |
| 401 / 403, or `preview_auth_unavailable` | Report missing/invalid operator configuration; do not print credentials or disable authentication. |
| 409 owner/generation mismatch | Read status and resolve current ownership; preserve pending receipt/key and do not replace another editor's Run. |
| Timeout after a POST | Execution may have happened. Keep persisted original request/key, recover by replay/query, and report unknown until confirmed. |
| `program_package_quota_exceeded` / resource capacity | Close owned unused previews and report capacity. Closing does not promise revision garbage collection; do not purge shared history. |
| Run/error traceback | Capture the current serial window, fix the actual code or documented API mismatch, then submit a new complete snapshot. |
| Unsupported board/Unit or model gap | State the exact limitation. Use a documented supported subset only with clear scope; do not fabricate a virtual PASS. |
| Frame 409 / 410 | The Run changed or has no matching retained sample; requery the active Run rather than presenting an older screen as current. |
| Cancellation unconfirmed | Keep the unknown/cancelling status. Do not assume Ctrl-C cleared native resources or launch duplicates. |

START acknowledges entry into execution, not application readiness. Add a meaningful READY marker after actual initialization when useful. Check serial provenance against execution/Run identity; echoed source containing the marker is not proof that it executed. Retain application errors even when the HTTP request succeeded.

## Preview lifetime and sharing

The server accepts a 30–3600 second lease. Read-only polling and image views do not renew it. `renew` explicitly extends the preview within service limits. A public URL is only a location: the user still needs authorized access to the simulator console. This local control API uses a shared principal and is not an internet multi-tenant service. Never expose it publicly merely to share a screenshot.

The helper returns `/platform/web/sessions.html` plus `session_id`; the current page has no verified per-session deep-link contract. AIFlow's own page is not an embedded simulator. Publish screenshots as normal task artifacts and offer the separate Live sessions console for interactive viewing. Continuous token-by-token preview, checkpoint events, integrated SSE and a native virtual-target UI are separate product work.
