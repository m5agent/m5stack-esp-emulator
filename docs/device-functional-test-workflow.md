# Virtual-device functional-test workflow

Status: implemented routing rule, reviewed `2026-10-25`.

Last reviewed: `2026-10-26`. Current capability and open tasks live in the
[project status](project-status.md) and [project backlog](project-backlog.md).

This document separates two workflows that previously shared the same Agent
context:

| User intent | Entry point | Persistent result |
| --- | --- | --- |
| Test firmware functions or a UIFlow2 image | Device Service on `8787` | Live/history session with frame, serial, state and evidence |
| Review, approve, reject or publish an M5Burner pending version | Firmware review control plane on `8790` | Review job and linked Device Service history |

A functional test is not a firmware review request. The review control plane
may call the Device Service when a review needs execution, but it is not the
general virtual-device entry point.

## Required device-service flow

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
