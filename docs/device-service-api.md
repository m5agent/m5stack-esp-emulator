# Device Service API v1

Status: local MVP implemented on `2026-10-22`.

The service creates an on-demand virtual M5Stack device, flashes an exact
firmware artifact into an isolated virtual-flash copy, and exposes serial,
frame, input and QOM operations through HTTP.

Current scope:

- enabled: 12 QEMU-backed ESP32 devices;
- excluded: Tab5 and CardputerZero;
- network emulation: disabled;
- sessions: in-memory leases, destroyed when the service process exits;
- evidence: serial/QEMU logs remain under the configured state directory.

The architecture and future pooling direction are documented in
[`simulator-service-architecture.md`](simulator-service-architecture.md).
The machine-readable contract is
[`device-service.openapi.yaml`](device-service.openapi.yaml) and is also
served at `/api/v1/openapi.yaml`.

## Start the service

```bash
python3 platform/tools/serve.py 8080 \
  --state-dir platform/.cache/service \
  --max-sessions 4 \
  --max-per-device 2 \
  --session-ttl 1800
```

For LAN access with a shared token:

```bash
export M5_SERVICE_API_TOKEN='<private-token>'
python3 platform/tools/serve.py 8080 --bind 0.0.0.0
```

When a token is configured, every `/api/v1` endpoint except health requires:

```http
Authorization: Bearer <private-token>
```

The service is intended for a trusted workstation or an isolated worker. Do not
expose it directly to the public internet.

## Base URL

```text
http://127.0.0.1:8080/api/v1
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
- `features.network` is currently always `false`

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

### Session

A session is one exclusive emulator lease. It has one device profile, one
immutable source firmware, one private flash copy, one QEMU process and one
serial log set.

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

## Endpoints

| Method | Path | Purpose |
| --- | --- | --- |
| GET | `/api/v1/health` | Service health and capacity |
| GET | `/api/v1/devices` | Device catalog; add `?include_unsupported=0` to hide disabled rows |
| GET | `/api/v1/devices/{device_id}` | One device profile |
| GET | `/api/v1/capacity` | Global and per-device active lease counts |
| POST | `/api/v1/artifacts` | Upload a binary artifact |
| GET | `/api/v1/artifacts/{artifact_id}` | Artifact metadata |
| POST | `/api/v1/firmware` | Compose a merged or segmented firmware |
| GET | `/api/v1/firmware/{firmware_id}` | Firmware metadata |
| GET | `/api/v1/sessions` | List sessions |
| POST | `/api/v1/sessions` | Create a session |
| GET | `/api/v1/sessions/{id}` | Session status |
| POST | `/api/v1/sessions/{id}/wait` | Wait for running state or a serial marker |
| GET | `/api/v1/sessions/{id}/serial?offset=0&limit=65536` | Incremental serial read |
| GET | `/api/v1/sessions/{id}/logs?offset=0&limit=65536` | Serial plus QEMU stdout/stderr tail |
| GET | `/api/v1/sessions/{id}/frame.png` | Current framebuffer as PNG |
| POST | `/api/v1/sessions/{id}/input` | Key, touch, long press or drag |
| POST | `/api/v1/sessions/{id}/qom` | Set a QOM property |
| GET | `/api/v1/sessions/{id}/qom?path=...&property=...` | Read a QOM property |
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
  http://127.0.0.1:8080/api/v1/sessions
```

The first run prepares and verifies a virtual flash through the backend's
esptool path. Later sessions with the same device and firmware hash copy the
prepared flash cache into a new per-session flash file.

### Wait for boot

```bash
SID='<session-id>'
curl -sS -H 'Content-Type: application/json' \
  -d '{"timeout_seconds":60}' \
  http://127.0.0.1:8080/api/v1/sessions/$SID/wait
```

For firmware with a known serial marker:

```json
{
  "ready_marker": "APP_READY",
  "timeout_seconds": 60
}
```

### Read serial incrementally

```bash
curl -sS \
  'http://127.0.0.1:8080/api/v1/sessions/<session-id>/serial?offset=0&limit=65536'
```

Use `next_offset` on the next request. Serial content is decoded as UTF-8 with
replacement characters; the underlying file remains the authoritative evidence.

### Get a screenshot

```bash
curl -sS \
  http://127.0.0.1:8080/api/v1/sessions/<session-id>/frame.png \
  -o /tmp/device.png
```

The response headers include `X-Frame-Width` and `X-Frame-Height`.

### Inject input

Key:

```json
{"kind":"key","key":"a","settle_seconds":0.3}
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
  http://127.0.0.1:8080/api/v1/sessions/<session-id>/qom
```

QOM is a trusted-local control surface. Do not expose arbitrary QOM access to
untrusted tenants.

### Upload and boot an arbitrary merged image

```bash
curl -sS -X POST \
  -H 'Content-Type: application/octet-stream' \
  -H 'X-Artifact-Name: webburner.bin' \
  --data-binary @webburner.bin \
  http://127.0.0.1:8080/api/v1/artifacts
```

Then create firmware:

```bash
curl -sS -H 'Content-Type: application/json' \
  -d '{"device_id":"cores3","kind":"merged","artifact_id":"<sha256>"}' \
  http://127.0.0.1:8080/api/v1/firmware
```

Then create the session with the returned `firmware_id`:

```bash
curl -sS -H 'Content-Type: application/json' \
  -d '{"device_id":"cores3","firmware_id":"<firmware-id>","ttl_seconds":900}' \
  http://127.0.0.1:8080/api/v1/sessions
```

This accepts a merged image or segmented image. It does not prove that a vendor
artifact is complete; if the source provides only an app image, the caller must
upload the bootloader, partition table and filesystem segments as well.

### Renew or delete

```bash
curl -sS -H 'Content-Type: application/json' \
  -d '{"ttl_seconds":900}' \
  http://127.0.0.1:8080/api/v1/sessions/<session-id>/renew

curl -sS -X DELETE \
  'http://127.0.0.1:8080/api/v1/sessions/<session-id>?purge=1'
```

Without `purge=1`, serial/QEMU logs remain under the state directory. The
session is removed from the active capacity count immediately.

## Concurrency and lifecycle rules

- one session owns one flash copy and one QEMU process;
- a session cannot be shared by two leases;
- `max_sessions` is global;
- `max_per_device` applies to each device model;
- expired sessions are stopped by a janitor thread;
- stopped/failed sessions remain queryable until the service restarts;
- a guest reset does not make a session safe for a different tenant;
- delete and recreate for tenant isolation.
- `running` is an emulator-process state; use serial markers or screenshots to
  establish application and visual readiness.

## Current limitations

- no WiFi/LAN network emulation;
- no Tab5 or CardputerZero;
- sessions are not durable across service restarts;
- reference firmware must already exist in `platform/.cache/firmware`;
- custom firmware must match the selected device's SoC, flash size, partition
  layout and modeled controllers;
- Core2 still has the known intermittent cache panic;
- the API creates simulation evidence only, not real-hardware PASS;
- QEMU stderr/stdout and serial logs can contain firmware-controlled text and
  must be treated as untrusted evidence.
