# Device Service API v1

Status: local MVP implemented on `2026-10-22`.

The service creates an on-demand virtual M5Stack device, flashes an exact
firmware artifact into an isolated virtual-flash copy, and exposes serial,
frame, input and QOM operations through HTTP.

Current scope:

- enabled: 12 QEMU-backed ESP32 devices;
- Tab5: enabled through esp-emu, with `peripheral_status=partial` and explicit
  warnings;
- excluded: CardputerZero;
- network emulation: enabled as a separate `runtime=network` one-shot lane for
  S3/C6 devices with validated `esp-emu` profiles;
- sessions: active leases are process-local; stopped/failed metadata, events
  and last-known evidence are restored from each session directory after a
  service restart;
- evidence: serial/QEMU logs remain under the configured state directory.

The architecture and future pooling direction are documented in
[`simulator-service-architecture.md`](simulator-service-architecture.md).
The machine-readable contract is
[`device-service.openapi.yaml`](device-service.openapi.yaml) and is also
served at `/api/v1/openapi.yaml`.

## Start the service

```bash
python3 platform/tools/serve.py 8787 \
  --state-dir platform/.cache/service \
  --max-sessions 12 \
  --max-per-device 8 \
  --session-ttl 1800
```

The defaults can also be overridden without changing the command line:

```bash
M5_SERVICE_MAX_SESSIONS=12 \
M5_SERVICE_MAX_PER_DEVICE=8 \
./start.sh
```

### Capacity sizing

The default of `12` global sessions and `8` sessions per model is a
workstation profile, not a protocol limit. It was measured on the current
Apple M4 host with 10 CPU cores and 32 GB RAM:

Twelve concurrent StickS3 sessions used about 227% of one CPU core in total
(about 2.27 of the host's 10 cores), 1.46 GiB aggregate RSS and 1.12 GiB
physical footprint. All 12 reached a non-black frame; 12 concurrent frame
captures completed in 18-39 ms.

- eight running StickS3 QEMU sessions used about 1.68 CPU cores and 983 MiB
  aggregate RSS;
- twelve running StickS3 QEMU sessions used about 2.27 CPU cores, 1.46 GiB
  aggregate RSS and 1.12 GiB physical footprint;
- all twelve sessions reached a non-black frame;
- twelve concurrent frame captures completed in 18-39 ms wall time;
- `/capacity` remained below 1 ms and the next request returned `429`.

Per-device resource use varies with firmware activity and device backend. Use
the environment variables or CLI flags to tune the limits for the host and
workload. Capacity exhaustion still returns `429` with `Retry-After`; a durable
batch queue is not implemented yet, so large bursts should retry or schedule
leases within the advertised capacity.

For LAN access with a shared token:

```bash
export M5_SERVICE_API_TOKEN='<private-token>'
python3 platform/tools/serve.py 8787 --bind 0.0.0.0
```

When a token is configured, every `/api/v1` endpoint except health requires:

```http
Authorization: Bearer <private-token>
```

The legacy catalog endpoints `/api/devices`, `/api/peripherals` and
`/api/peripheral-interfaces` use the same token when one is configured.

The service is intended for a trusted workstation or an isolated worker. Do not
expose it directly to the public internet.

## Base URL

```text
http://127.0.0.1:8787/api/v1
```

Every JSON response includes `X-Request-ID`. Errors use:

```json
{
  "error": {
    "code": "device_capacity_exhausted",
    "message": "maximum active sessions for sticks3 is 2"
  }
}
```

## Objects

### Device

`GET /api/v1/devices` returns all registered devices. `supported=false` rows
are visible but cannot be leased.

Important fields:

- `device_id`
- `supported`
- `creatable`
- `reference_available`
- `backend_ready`
- `flash_size`
- `display`
- `features.flash/serial/screenshot/input/qom`
- `network_status` separates simulator capability from test evidence:
  `validated`, `unverified`, `board-init-blocked`, or `not-supported`.
- `features.network` is `true` only for a `validated` device-level path.
  `network_profiles` still lists scenarios that can be used for diagnostics on
  an `unverified` or `board-init-blocked` chip; a profile being listed is not a
  PASS claim. Tab5 and Core2 are `not-supported`.
- `network_console` reports the generic-firmware console default declared by
  the device matrix, such as `usb-jtag` for C6 UIFlow2.
- Tab5 `features.qom` is `false`; its touch path uses the GDB mailbox currently
  used by the validated Tab5 runtime.

### Artifact

An artifact is an immutable content-addressed byte blob. Upload the bootloader,
partition table, application or a complete merged image separately.

```http
POST /api/v1/artifacts
Content-Type: application/octet-stream
X-Artifact-Name: firmware.bin
```

Response:

```json
{
  "artifact_id": "<sha256>",
  "sha256": "<sha256>",
  "size": 123456,
  "name": "firmware.bin",
  "content_type": "application/octet-stream",
  "created_at": "..."
}
```

### Firmware

A firmware manifest composes one or more artifacts into a flash-sized image
for a specific device. The resulting file is padded with `0xff`.

Complete merged image:

```json
{
  "device_id": "sticks3",
  "kind": "merged",
  "artifact_id": "<sha256>"
}
```

Segmented image:

```json
{
  "device_id": "sticks3",
  "kind": "segmented",
  "segments": [
    {"offset": "0x0", "artifact_id": "<bootloader-sha256>"},
    {"offset": "0x8000", "artifact_id": "<partition-sha256>"},
    {"offset": "0x10000", "artifact_id": "<app-sha256>"},
    {"offset": "0x210000", "artifact_id": "<filesystem-sha256>"}
  ]
}
```

Offsets may be integers or `0x` strings. Segments cannot overlap or exceed the
target device flash size.

```http
POST /api/v1/firmware
Content-Type: application/json
```

The response includes `firmware_id`, `sha256`, `device_id`, `flash_size`,
`kind`, `source` and `header_magic`.

`artifact_sha256` identifies the uploaded source artifact. `firmware_id` and
`firmware.sha256` identify the composed, flash-sized image after padding and
segment composition. They intentionally do not have to be equal.

### Session

A session is one exclusive emulator lease. It has one device profile, one
immutable source firmware, one private flash copy, one QEMU process and one
serial log set.

`runtime` is `qemu` by default. Set it to `network` to run the firmware through
the separate network/BLE lane. Network sessions do not expose framebuffer,
input, QOM or same-instance board state; those remain in the QEMU lane.

State machine:

```text
provisioning -> flashing -> booting -> running
                                  \-> failed
running -> stopping -> stopped
```

`POST /api/v1/sessions` is asynchronous and returns `202 Accepted` while the
session is provisioning. Poll the session or call `wait`.

`running` means the QEMU process and QMP control channel are alive. It does
not guarantee that the application reached its first frame or a serial marker.
For application-level readiness, provide `ready_marker` in the create request
or call `/wait`, then inspect serial and/or `/frame.png`.

Audio data-plane tests can provide a narrow, trusted-local `runtime_env`
object when creating a session:

```json
{
  "device_id": "cores3",
  "firmware_id": "<firmware-id>",
  "runtime_env": {
    "M5SW_I2S_DMA_IRQ": "1",
    "M5SW_I2S_PCM_FILE": "/private/tmp/session/speaker.pcm",
    "M5SW_I2S_RX_PCM_FILE": "/private/tmp/session/microphone.pcm"
  }
}
```

Only `M5SW_I2S_DMA_IRQ`, `M5SW_I2S_PCM_FILE`,
`M5SW_I2S_RX_PCM_FILE`, and `M5SW_I2S_TRACE` are accepted. This is a
trusted-workstation control surface; do not expose it to untrusted tenants.

Network sessions use a validated scenario:

```json
{
  "device_id": "sticks3",
  "firmware_id": "<firmware-id>",
  "runtime": "network",
  "network": {
    "profile": "esp-idf-http",
    "timeout_seconds": 45
  }
}
```

Profiles are:

- `esp-idf-http`: WiFi, DHCP and a controlled complete HTTP/TCP download;
- `esp-idf-smoke`: WiFi, DHCP and the upstream comprehensive smoke suite;
- `idf-dns-udp`: WiFi, DHCP, host-forwarder DNS and a controlled UDP round
  trip against a disposable host peer;
- `esp-idf-coex`: the upstream NimBLE/WiFi coexistence application plus an
  external Bumble GATT connect/write/readback while WiFi remains active;
- `uiflow2-sticks3`: UIFlow2 network/BLE probe. BLE requires a matching ELF
  uploaded as an artifact and referenced by `elf_artifact_id`.
- `generic-observe`: runs an arbitrary compatible image for the requested
  timeout window. With no `expected_markers` the result is `PARTIAL` and
  proves only that the process/serial path ran; add up to 16 marker strings to
  obtain an application-level PASS/FAIL assertion. Add
  `net_mode=user,restrict=yes` for untrusted firmware. When `ble=true`, the
  profile runs an external Bumble observer and requires
  `elf_artifact_id`; successful BLE requires GATT discovery, subscription,
  write, and guest-side delivery.

`network.net_mode` accepts `user` or `user,restrict=yes`. Validated test
profiles default to `user`; callers may explicitly select restricted mode.
Use `user` for unrecognized firmware only inside a disposable VM.

`network.console_mode` accepts `auto`, `uart0` and `usb-jtag`.
`generic-observe` uses the device's matrix `network_console` value when one is
declared; ESP32-C6 UIFlow2 entries currently use `usb-jtag`. Other generic
devices default to `auto`. Validated lane profiles default to `uart0`.

For StickS3 BLE-only, use
`{"profile":"uiflow2-sticks3","wifi":false,"ble":true,"elf_artifact_id":"..."}`.
The same guest also supports `wifi=true,ble=true`; the runner stages REPL input
around UIFlow2's WebREPL startup and has passed simultaneous association/DHCP
and BLE GATT.

The service stores the latest captured framebuffer as `last-frame.png` and
`last-frame.json`. When a session stops, `frame.png` returns this last-known
frame instead of failing. Session snapshots expose `last_frame_available` and
`last_frame_captured_at`.

Devices with a normalized runtime-state probe also expose
`GET /sessions/{id}/device-state`. StickS3 currently reports M5PM1 power state
and BMI270 IMU values through the same QMP instance. Live sampling is persisted
to the session directory and remains readable as a last-known snapshot after
the session stops. This endpoint does not expose arbitrary QOM internals.

## Endpoints

| Method | Path | Purpose |
| --- | --- | --- |
| GET | `/api/v1/health` | Service health and capacity |
| GET | `/api/v1/devices` | Device catalog; add `?include_unsupported=0` to hide disabled rows |
| GET | `/api/v1/devices/{device_id}` | One device profile |
| GET | `/api/v1/capacity` | Global and per-device active lease counts |
| POST | `/api/v1/artifacts` | Upload a binary artifact |
| GET | `/api/v1/artifacts/{artifact_id}` | Artifact metadata |
| DELETE | `/api/v1/artifacts/{artifact_id}` | Delete an artifact |
| POST | `/api/v1/firmware` | Compose a merged or segmented firmware |
| GET | `/api/v1/firmware/{firmware_id}` | Firmware metadata |
| POST | `/api/v1/firmware/analyze` | Validate image, chip ID, partition table and app descriptor |
| GET | `/api/v1/firmware/{firmware_id}/analysis` | Read stored static analysis |
| GET | `/api/v1/sessions` | List sessions; history is included by default, `include_stopped=0` shows active leases only |
| POST | `/api/v1/sessions` | Create a session |
| DELETE | `/api/v1/sessions?state=stopped&purge=1` | Clear stopped/failed history |
| GET | `/api/v1/sessions/{id}` | Session status |
| GET | `/api/v1/sessions/{id}/events` | Lifecycle event timeline |
| GET | `/api/v1/sessions/{id}/network` | Machine-readable network/BLE evidence |
| GET | `/api/v1/sessions/{id}/device-state` | Live or last-known normalized device state |
| POST | `/api/v1/sessions/{id}/wait` | Wait for serial/frame readiness; `wait_for_completion=true` waits for a one-shot network session to finish |
| GET | `/api/v1/sessions/{id}/evidence` | Download a hashed evidence ZIP |
| GET | `/api/v1/sessions/{id}/serial?offset=0&limit=65536` | Incremental serial read |
| GET | `/api/v1/sessions/{id}/logs?offset=0&limit=65536` | Serial plus runtime stdout/stderr tail |
| GET | `/api/v1/sessions/{id}/frame.png` | Live or last-known framebuffer as PNG |
| POST | `/api/v1/sessions/{id}/input` | Key, touch, long press or drag |
| POST | `/api/v1/sessions/{id}/qom` | Set a QOM property |
| GET | `/api/v1/sessions/{id}/qom?path=...&property=...` | Read a QOM property |
| GET | `/api/v1/sessions/{id}/qom/list?path=/machine` | List QOM properties |
| POST | `/api/v1/sessions/{id}/qom-snapshot` | Store a recursive QOM snapshot |
| GET | `/api/v1/sessions/{id}/qom/diff?before=...&after=...` | Diff stored QOM snapshots |
| GET | `/api/v1/sessions/{id}/flash?format=sha256\|bin` | Read virtual flash hash or bytes |
| POST | `/api/v1/sessions/{id}/flash-snapshot` | Store a virtual flash snapshot |
| GET | `/api/v1/sessions/{id}/flash/diff?before=...&after=...` | Diff flash snapshots |
| POST | `/api/v1/sessions/{id}/reset` | Reset the guest |
| POST | `/api/v1/sessions/{id}/renew` | Extend the lease |
| POST | `/api/v1/sessions/{id}/stop` | Stop the session |
| DELETE | `/api/v1/sessions/{id}` | Stop and optionally purge session files |

## Quick examples

### Create a reference UIFlow2 device

If the reference firmware is cached for the device, `firmware_id` can be
omitted:

```bash
curl -sS -H 'Content-Type: application/json' \
  -d '{"device_id":"sticks3","ttl_seconds":600}' \
  http://127.0.0.1:8787/api/v1/sessions
```

The first run prepares and verifies a virtual flash through the backend's
esptool path. Later sessions with the same device and firmware hash copy the
prepared flash cache into a new per-session flash file.

### Wait for boot

```bash
SID='<session-id>'
curl -sS -H 'Content-Type: application/json' \
  -d '{"timeout_seconds":60,"ready":{"frame_nonblank":true,"frame_min_bytes":1024,"frame_min_nonblack_pixels":16}}' \
  http://127.0.0.1:8787/api/v1/sessions/$SID/wait
```

For firmware with known serial markers:

```json
{
  "timeout_seconds": 60,
  "ready": {
    "serial_markers": ["APP_READY", "UIFLOW_READY"],
    "frame_nonblank": true,
    "frame_min_bytes": 1024,
    "frame_min_nonblack_pixels": 16,
    "require_all": true
  }
}
```

The response includes `ready`, `ready_reason`, matched serial markers,
`first_serial_at`, `first_frame_at` and frame metrics without embedding the
PNG bytes.

### Evidence bundle

```bash
curl -sS \
  'http://127.0.0.1:8787/api/v1/sessions/<session-id>/evidence?include=manifest,serial,frames,logs,qom' \
  -o /tmp/m5-evidence.zip
```

### Wait for a network session

```bash
curl -sS -H 'Content-Type: application/json' \
  -d '{"timeout_seconds":90,"wait_for_completion":true}' \
  http://127.0.0.1:8787/api/v1/sessions/$SID/wait
```

`GET /sessions/{id}/network` returns the final `evidence.json`, including
checks, artifact hashes, log hashes and explicit simulation-only limits.

Add `flash` to include the full isolated virtual flash. The ZIP always contains
`manifest.json` with session timeline, file hashes, device warnings and flash
metadata.

### QOM and flash snapshots

```bash
curl -sS -H 'Content-Type: application/json' \
  -d '{"path":"/machine","depth":2,"max_nodes":500}' \
  http://127.0.0.1:8787/api/v1/sessions/<session-id>/qom-snapshot

curl -sS -H 'Content-Type: application/json' \
  -d '{}' \
  http://127.0.0.1:8787/api/v1/sessions/<session-id>/flash-snapshot
```

Use the returned `snapshot_id` values with the corresponding `diff` endpoint.
Flash snapshot diff reports changed byte count and contiguous ranges, not a
second full-size image.

### Read serial incrementally

```bash
curl -sS \
  'http://127.0.0.1:8787/api/v1/sessions/<session-id>/serial?offset=0&limit=65536'
```

Use `next_offset` on the next request. Serial content is decoded as UTF-8 with
replacement characters; the underlying file remains the authoritative evidence.

### Get a screenshot

```bash
curl -sS \
  http://127.0.0.1:8787/api/v1/sessions/<session-id>/frame.png \
  -o /tmp/device.png
```

The response headers include `X-Frame-Width`, `X-Frame-Height` and
`X-Frame-SHA256`. The Live Sessions page polls active framebuffers independently
from session metadata, targets about 8 FPS, and skips texture updates when the
frame hash is unchanged. For a recently stopped session it returns the persisted
last-known frame.

### Inject input

Key:

```json
{"kind":"key","key":"a","settle_seconds":0.3}
```

Physical hold uses separate key-down and key-up requests. The Live Sessions 3D
shells use this form so a model button is down only while the pointer is held:

```json
{"kind":"key","key":"a","action":"down","settle_seconds":0.02}
{"kind":"key","key":"a","action":"up","settle_seconds":0.02}
```

Touch:

```json
{"kind":"touch","x":67,"y":160,"settle_seconds":0.3}
```

Long press:

```json
{"kind":"longpress","x":67,"y":160,"hold_seconds":1.0}
```

Drag:

```json
{"kind":"drag","x1":20,"y1":200,"x2":100,"y2":200}
```

### Set a QOM value

```bash
curl -sS -H 'Content-Type: application/json' \
  -d '{"path":"/machine/bmi270","property":"accel-x","value":0.25}' \
  http://127.0.0.1:8787/api/v1/sessions/<session-id>/qom
```

QOM is a trusted-local control surface. Do not expose arbitrary QOM access to
untrusted tenants.

### Upload and boot an arbitrary merged image

```bash
curl -sS -X POST \
  -H 'Content-Type: application/octet-stream' \
  -H 'X-Artifact-Name: webburner.bin' \
  --data-binary @webburner.bin \
  http://127.0.0.1:8787/api/v1/artifacts
```

Then create firmware:

```bash
curl -sS -H 'Content-Type: application/json' \
  -d '{"device_id":"cores3","kind":"merged","artifact_id":"<sha256>"}' \
  http://127.0.0.1:8787/api/v1/firmware
```

Then create the session with the returned `firmware_id`:

```bash
curl -sS -H 'Content-Type: application/json' \
  -d '{"device_id":"cores3","firmware_id":"<firmware-id>","ttl_seconds":900}' \
  http://127.0.0.1:8787/api/v1/sessions
```

This accepts a merged image or segmented image. It does not prove that a vendor
artifact is complete; if the source provides only an app image, the caller must
upload the bootloader, partition table and filesystem segments as well.

### Renew or delete

```bash
curl -sS -H 'Content-Type: application/json' \
  -d '{"ttl_seconds":900}' \
  http://127.0.0.1:8787/api/v1/sessions/<session-id>/renew

curl -sS -X DELETE \
  'http://127.0.0.1:8787/api/v1/sessions/<session-id>?purge=1'
```

Without `purge=1`, `session.json`, the event timeline, serial/QEMU logs, the
last frame and device state remain under the state directory. The session is
removed from the active capacity count immediately and is restored as history
after a service restart.

## Concurrency and lifecycle rules

- one session owns one flash copy and one QEMU process;
- a session cannot be shared by two leases;
- `max_sessions` is global;
- `max_per_device` applies to each device model;
- capacity limits can be changed with `--max-sessions`, `--max-per-device`,
  `M5_SERVICE_MAX_SESSIONS`, or `M5_SERVICE_MAX_PER_DEVICE`;
- expired sessions are stopped by a janitor thread;
- stopped/failed sessions remain queryable across service restarts;
- a session that was still active when the service stopped is restored as
  `failed`, with `interrupted=true`, an explicit error and an `interrupted`
  lifecycle event; it never consumes active capacity;
- `GET /sessions?include_stopped=0` hides stopped/failed history from a UI;
- the web dashboard shows active leases plus sessions completed in the last
  30 minutes when a last-known frame or serial-only view is available;
  “显示全部历史” expands the list;
- `DELETE /sessions?state=stopped&purge=1` removes old sessions and their
  per-session flash copies;
- a guest reset does not make a session safe for a different tenant;
- delete and recreate for tenant isolation.
- `running` is an emulator-process state; use serial markers or screenshots to
  establish application and visual readiness.
- capacity errors return `429` with `Retry-After: 2`.

## Current limitations

- network sessions are a separate lane and do not combine board peripherals
  with the same guest instance;
- Core2 has no `esp-emu` network/PHY path yet;
- CardputerZero is not enabled;
- Tab5 camera/audio/USB/SDIO and dynamic peripheral state remain incomplete;
- uploaded Tab5 firmware can boot, but screenshot/input currently require the
  matching reference ELF;
- normalized `device-state` probes currently exist for StickS3; other devices
  expose session metadata, framebuffer and serial without inventing component
  values;
- emulator processes are not resumed across service restarts; only stopped,
  failed and interrupted history is reconstructed;
- reference firmware must already exist in `platform/.cache/firmware`;
- custom firmware must match the selected device's SoC, flash size, partition
  layout and modeled controllers;
- Core2 still has the known intermittent cache panic;
- CoreS3 UIFlow startup palette/alpha PNG images have a known striped-rendering
  boundary; ordinary opaque drawing is unaffected. See
  [`cores3-image-rendering-boundary.md`](cores3-image-rendering-boundary.md);
- the API creates simulation evidence only, not real-hardware PASS;
- QEMU stderr/stdout and serial logs can contain firmware-controlled text and
  must be treated as untrusted evidence.
