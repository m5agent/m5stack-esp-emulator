# Virtual-device functional-test workflow

Status: implemented routing rule.

Last reviewed: `2026-10-30`. Current capability and open tasks live in the
[project status](project-status.md) and [project backlog](project-backlog.md).

Choose the execution path from the user intent:

| User intent | Entry point | Persistent result |
| --- | --- | --- |
| Test firmware functions or a UIFlow2 image | Dedicated agent Device Service, separate port/state/token | Live/history session with frame, serial, state and evidence |
| Explicitly test browser-WASM execution | Exported static site / authorized Pages URL | Browser-local session, source/runtime/firmware SHA, serial/frame/input and cleanup evidence |
| Review, approve, reject or publish an M5Burner pending version | Configured firmware review control plane | Review job and linked Device Service history |

A functional test is not a firmware review request. The review control plane
may call the Device Service when a review needs execution, but it is not the
general virtual-device entry point.

Use an agent-owned port, state directory and control token; preserve services
and sessions owned by others. Follow the reserved-port rules in
[AGENTS.md](../AGENTS.md). Browser-WASM acceptance has no remote lease or `/api/v1` session;
it executes the guest entirely in the browser. Follow the same-guest evidence
rules, preserve the exact exported artifact and keep browser results distinct
from native/service and physical hardware results. See [Pages deployment](pages-deployment.md).

## Required device-service flow

Before intake, verify the selected chip/board profile, controller coverage,
Flash/PSRAM/eFuse and image layout. Acceptance of an upload does not establish
that the image can execute on that device.

1. Upload the exact source artifact with `POST /api/v1/artifacts`.
2. Compose the matching merged or segmented image with
   `POST /api/v1/firmware`.
3. Create `POST /api/v1/sessions` with `device_id`, `firmware_id`, TTL and
   application readiness conditions.
4. Wait through `POST /api/v1/sessions/{id}/wait`; `state=running` alone is not
   an application PASS.
5. Collect serial, frame, normalized device state, input/QOM evidence and the
   evidence ZIP through the session API.
6. Stop with `DELETE /api/v1/sessions/{id}` and no `purge=1`; collected
   metadata, logs and the last frame remain, while the full mutable Flash is
   released unless `retain_flash=1` is requested.
7. Re-read `GET /api/v1/sessions` or the Live sessions page and confirm the
   stopped session, last frame and lifecycle events are retained.

## Required browser-WASM flow

1. Use the exact exported artifact on an isolated static origin or an authorized
   Pages URL; record its manifest plus runtime/source/firmware hashes.
2. Start one browser-local instance and wait for the actual guest ready marker.
3. Exercise the real DOM input path, then read that guest's serial,
   framebuffer/model texture and relevant controller state.
4. Download its local run record before stopping. Record normal Stop, guest
   exit, nested pthread and engine Worker targets independently, before closing
   the browser context. A closing notification or forced context teardown alone
   does not establish clean shutdown; preserve failures as `PARTIAL`/`FAIL`.
5. Keep browser-local evidence separate from Device Service lease/history/ZIP
   results and from physical hardware. Do not call `/api/v1` to fill a missing
   browser observation. Publication acceptance is defined in the
   [Pages guide](pages-deployment.md), not by a build or screenshot alone.

## Persistence behavior

Each session directory now contains:

- `session.json`: identity, device, firmware, lifecycle and timestamps;
- `events.json`: lifecycle timeline;
- `last-frame.png` and `last-frame.json`: retained visual evidence;
- `serial*.log`, QEMU logs and optional QOM/device-state files;
- `virtual-flash.bin` while active, or after stop when `retain_flash=1` is
  explicitly requested.

Stopped/failed history is retained within configured age, count and byte
limits. A background janitor uses `GET /api/v1/storage` for observability and
prunes unreferenced artifact/firmware/prepared-flash caches after the configured
grace period.

On startup, a stopped/failed record is restored as history. For an active
QEMU/QMP record, the service may re-attach only when the original PID,
process start token, QMP socket ownership and `query-status=running` all match.
Trusted-host unified sessions additionally recreate the HTTP fixture from
durable request generations and adopt a BLE peer only after PID, start-time and
full command-SHA256 checks. They report
`recovery_scope=qemu-control-plane+companions`; namespace-managed, Tab5 and
cross-host companions remain unsupported. If ownership cannot be proven, the
record becomes `failed`, `interrupted=true`, with an explicit error; it is
never presented as running.

## Boundaries

- Label QEMU results as virtual-device validation, not physical-hardware
  measurements. A validated virtual device is accepted validation evidence for
  the external verification gate when it exercises the same firmware path and
  retains reproducible session evidence.
- Agent-triggered direct QEMU runners bypass session observability and must not
  be used for functional-test requests.
- The browser's default view shows active sessions and sessions completed in
  the last 30 minutes; “显示全部历史” expands the retained history.
