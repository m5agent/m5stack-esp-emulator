# Device Service workflows

This reference is usable without a simulator source checkout. Obtain the
deployment's OpenAPI contract from its operator, or retrieve the documented
`GET /api/v1/openapi.yaml` endpoint on the configured service. Check the
returned version, `servers`, paths and schemas before advanced operations.
Do not invent a contract URL, infer an operation from a UI label, or assume a
different deployment implements every example below. A missing or conflicting
contract is a limitation to report, not permission to guess fields.

All paths below are relative to the configured `/api/v1` base. JSON examples
contain placeholders that must be replaced with verified values. Use the
configured credential through a secret-safe client; never put it in a URL,
source file, tool output or evidence. Use the operator's dedicated agent-test
service, with separate port, state directory and control token. Do not start,
stop or reconfigure a user's shared testing service.

This is an HTTP reference, not a list of helper subcommands. Run the packaged
helper's `--help` for its actual typed commands. Use a credential-safe HTTP
client for unsupported advanced operations only after checking the current
contract and preserving the same owned session identity. Do not pretend the
helper supports an operation merely because it appears here.

## Discover and select a target

1. `GET /devices` returns `{devices: [...]}`. Match the user's exact product;
   require `supported`, `creatable` and `backend_ready`. Inspect
   `missing_runtime_files`, `reference_available`, `display`, `features`,
   `network_profiles`, `network_status`, warnings and the selected firmware's
   requirements. Catalog presence alone is insufficient.
2. `GET /devices/{device_id}` returns that target's metadata. For external
   Units, also read `GET /units?device_id={device_id}`. Its `units[]` use `id`,
   `inputs`, `outputs`, `runtime` and `host_admission`; wiring is in
   `hosts[].ports`. A physical connector or a rendered Unit is not admission.
   `host_admission` describes standalone/default-initial `runtime=qemu`
   placement; another runtime, initial fixture or HUB topology still needs
   full create-time admission.
3. Record the intended chip/board, flash and effective PSRAM, image layout,
   firmware SHA, security mode, runtime/profile, Units, fixtures and expected
   behavior before allocating the guest. Do not substitute a similar board.

## Import generic firmware

Upload actual bytes first:

```http
POST /artifacts
Content-Type: application/octet-stream
X-Artifact-Name: application.bin

<binary bytes>
```

The `201` response includes `artifact_id`, `sha256` and `size`. Compare them to
the local file's SHA256 and byte count. Artifact metadata GET does not download
the bytes. Never upload private keys, firmware credentials or unrelated files.

Choose one intake path; do not mix their request fields:

| Path | Request to `POST /firmware` |
| --- | --- |
| Merged flash at offset zero | `{"device_id":"<device>","kind":"merged","artifact_id":"<uploaded-id>"}` |
| Segmented image | `{"device_id":"<device>","kind":"segmented","segments":[{"offset":"<declared-offset>","artifact_id":"<segment-id>"}]}` |
| Already produced versioned manifest | `{"device_id":"<device>","kind":"manifest","manifest":<complete-manifest-object>}` |

For segmented input, upload each segment separately. Use the offsets from that
exact build's flash arguments/package, not a generic ESP32 offset template.
Offsets accept integers or numeric strings. Segments must be nonempty,
nonoverlapping and within the selected flash size. A bare application BIN is
not automatically a merged flash image.

For a `.bin` merged flash or `.zip`/`.m5burner`/`.webburner` package, the
recommended reviewed intake is:

```http
POST /firmware/import
Content-Type: application/json

{"device_id":"<device>","artifact_id":"<uploaded-package-id>",
 "required_capabilities":["<documented-required-capability>"],
 "optional_capabilities":[]}
```

Omit the capability arrays when none are declared. They belong to import or
the versioned manifest, not arbitrary fields added to merged/segmented compose.
Do not relabel a required feature as optional to pass admission. Import selects
the format using the uploaded artifact name, normalizes segments/padding and
produces a manifest and stored flash image. Unknown required capabilities or
target/security/memory mismatch return `409 unsupported_firmware_capability`
with structured `issues`; invalid packages return `400 invalid_firmware_package`.

Direct manifest submission requires the complete versioned
`m5stack-firmware-manifest` object, including `schema_version`, `kind`,
`artifact`, `target`, `security`, `provenance` and `validation`. Upload the
manifest's normalized `merged-flash` artifact first; bind its actual artifact
ID/hash/size. Use an operator-provided or importer-produced manifest and its
schema. Do not fabricate security or validation blocks, remove contradictory
evidence, or edit an existing `manifest_id` without recomputing its defined
canonical identity.

The firmware response's `firmware_id` and `sha256` identify normalized stored
flash bytes. The uploaded artifact SHA can differ after padding/composition.
Retain both identities. `POST /firmware/analyze` with
`{"firmware_id":"<stored-id>"}` performs static analysis;
`GET /firmware/{firmware_id}/analysis` reads it. Composition, import and static
analysis do not establish boot or functional PASS.

## Create one visible, owned session

```http
POST /sessions
Content-Type: application/json

{"device_id":"<device>","firmware_id":"<stored-firmware-id>",
 "runtime":"qemu","ttl_seconds":600,
 "idempotency_key":"<persisted-random-create-key>",
 "owner":"agent-test"}
```

Omitting `firmware_id` deliberately selects that device's cached reference;
record the resulting firmware SHA. For ordinary sessions, the stable creation
key is the JSON **`idempotency_key` field**, not Preview's HTTP header. Persist
the exact request/key before POST; after an ambiguous response, replay that
same request/key, never allocate a speculative replacement. Different content
under the same key is a conflict.

Creation returns `202`; poll `GET /sessions/{session_id}`. `running` means the
process/control channel are alive. Confirm application behavior using fresh
serial and frames, or call:

```http
POST /sessions/{session_id}/wait
Content-Type: application/json

{"timeout_seconds":30,"ready":{"serial_markers":["APP_READY"],
 "frame_nonblank":true,"require_all":true}}
```

Only require a frame on a display target. Use an application-owned marker
that really executes after initialization; an echoed string or boot logo is
insufficient. `GET /sessions/{id}/serial?offset=0&limit=65536` returns
`offset`, `next_offset`, `data`, `bytes`; continue using byte `next_offset`,
not character length. Keep windows for each test action. Read `/logs`,
`/events`, `/device-state`, `/frame.png` and `/units` where supported.

| Runtime | Selection and evidence boundary |
| --- | --- |
| `qemu` | Board execution; use the exact compatible profile and model coverage. Radio behavior is not inferred. |
| `qemu-unified` | Same guest board plus radio, with a device-admitted `network.profile` and that profile's firmware/ELF/peer prerequisites. |
| `qemu-wifi` / `qemu-ble` | Selected radio paths; whole-device coverage depends on the actual profile. |
| `network` | Separate diagnostic/provisioning lane. No same-guest framebuffer, board input or QOM, and no QEMU pcap path. |

For a QEMU radio session add a verified `network` object, for example
`{"profile":"<device-admitted-profile>","capture_pcap":true}` with the
required firmware/ELF and fixture fields from the current contract. Some
profiles need specially built HCI firmware; a profile name does not make an
arbitrary binary compatible. Core2 `core2-native-hci` requires
`network.elf_artifact_id` from the exact firmware build; legacy native-VHCI is
a diagnostic compatibility path.

For an explicitly diagnostic generic image, `runtime:"network"` can use
`network:{"profile":"generic-observe","timeout_seconds":60,
"expected_markers":["APP_READY"],"net_mode":"user,restrict=yes"}` when
that target admits it. Without meaningful assertions it remains observational
PARTIAL. Do not combine this session with a second board session to claim one
device passed. Restricted user networking is not an untrusted-firmware sandbox.

## Inputs, Units and data planes

Configure Units at creation, for example only after that host/port is admitted:

```json
{"units":[{"id":"motion","unit_id":"pir","port_id":"<admitted-port>"}]}
```

Merge this field into the session request. Read returned frozen `units[].pins`
and initialize the real firmware driver accordingly; callers do not choose
QOM paths or supply substitute GPIO wiring. HUB children use a parent attachment
`parent_id` and its documented downstream `port_id`; do not parallel conflicting
addresses/GPIOs. Changing assembly requires a new session.

For an ordinary owned session, `POST /sessions/{id}/unit-input` accepts exactly
`{"id":"motion","values":{"motion":true}}` for an admitted PIR. Other
Units use their frozen `inputs` schema. Outputs are read-only; creation-only
fields belong in attachment `initial`, not live writes. Then read
`GET /sessions/{id}/units` and verify actual guest consumption in serial,
screen or controller observations. Injection success alone is not a PASS.

Board controls use `POST /sessions/{id}/input`: a supported QEMU key is
`{"kind":"key","key":"<supported-qcode>","action":"tap"}`; a supported
touch target accepts `{"kind":"touch","x":20,"y":20,"settle_seconds":0.3}`.
Use actual board mapping and frame coordinates. Held `down` requires matching
`up`; do not guess a key from the button's label.

QOM is an advanced controller interface, not a replacement for missing models:
`GET /sessions/{id}/qom/list?path=/machine`, then GET `/qom` with URL-encoded
`path` and `property`. A documented writable input can be set using
`POST /qom` with `{"path":"<observed-path>","property":"<input>","value":1}`.
Never write computed output or return values to manufacture success.
`POST /qom-snapshot` accepts `{"path":"/machine","depth":2,"max_nodes":500}`;
compare returned IDs using `GET /qom/diff?before=<id>&after=<id>`.

### Environment scenarios

Example: test a temperature/humidity application using ENV III. Discover the
requested host first; continue only if its `env-iii` admission and port are
available. Merge this assembly into the creation request, replacing the port:

```json
{"units":[{"id":"env","unit_id":"env-iii","port_id":"<admitted-port>","initial":{"temperature-c":25.0,"humidity-pct":50.0,"pressure-pa":101325}}]}
```

`initial` sets modeled sensor inputs before boot. The firmware must initialize
its actual compatible sensor driver using the session's frozen wiring and
keep reading it; attaching a Unit does not add application code. Capture a
baseline with `observe` and save this as `env-input.json`:

```json
{"id":"env","values":{"temperature-c":35.0,"humidity-pct":80.0,"pressure-pa":100800}}
```

Apply it to the owned ordinary session, then observe that same execution:

```bash
python3 <skill-dir>/scripts/emulator.py --state .m5-emulator/run.json request POST /api/v1/sessions/<owned-session-id>/unit-input --json env-input.json
python3 <skill-dir>/scripts/emulator.py --state .m5-emulator/run.json observe --frame --out-dir artifacts/emulator/hot-humid
```

Allow the guest's sensor conversion and polling interval, then check fresh
serial and Unit state (`GET /sessions/{id}/units`) and actual screen/actuator
changes. The existing ENV III controller contract uses Celsius, percent RH
and Pa; consult the deployed input schema for limits. Sensor quantization
means guest readings need a justified tolerance, not exact JSON equality.
UIFlow's `ENVUnit.read_pressure()` returns hPa; multiply by 100 when comparing
it with `pressure-pa`. Other firmware drivers may use different units.

For threshold testing, apply a recorded baseline, a value above the
application's threshold, and a recovery value in order; assert the intended
behavior after each step. Keep one guest/assembly so this also tests stateful
recovery. Step values are explicit simulated environmental inputs, not
physical measurements or a global weather model. A temperature change here
does not implicitly change NCIR, IMU or unrelated sensors. A ramp/time-series
requires the caller to schedule successive input requests and observations.
Add/remove/reconnect Units by creating a new assembly/session; use Preview's
fenced `/previews/{id}/input` for managed Preview sessions instead of this
ordinary-session mutation route.

## Network, storage and Flash evidence

`GET /sessions/{id}/network` gives the same session's network evidence. On QEMU
radio paths, pcap is normally captured and finalized on stop; evidence includes
`network/capture.pcap` and `network/pcap-summary.json`. Do not invent a `/pcap`
download endpoint. The `packet_capture` summary reports observed flow/DNS/DHCP
evidence; it does not grant RF or whole-device success.

An authorized reconnect test uses `POST /sessions/{id}/network-fault` with
`{"target":"radio","action":"down"}`, followed by the corresponding
`"up"`. `target:"link"` controls `wifi0`; radio requires a modeled
`radio-enabled` property. Verify guest failure/recovery and fresh network
delivery; a successful control call does not establish reconnect PASS.

For a target with `features.storage`, upload a prepared raw SD image and add
`storage:{"sd_image_artifact_id":"<artifact-id>"}` at session creation.
Its filesystem/partition layout must match the firmware. For a QEMU guest,
an exact-sized NVS partition fixture can use
`nvs:{"partition_label":"nvs","image_artifact_id":"<artifact-id>"}`.
These are isolated writable copies/overlays, not permission to use real
credentials or proof that arbitrary filesystem content is supported.

While the owned guest's mutable Flash exists:

- `GET /sessions/{id}/flash?format=sha256` reads current metadata;
  `format=bin` downloads actual Flash bytes.
- `POST /sessions/{id}/flash-snapshot` stores a snapshot. Take another after
  the action, then `GET /sessions/{id}/flash/diff?before=<id>&after=<id>`.
  This reports changed ranges/byte counts, not a second whole-image download.

## Export, stop and confirm cleanup

Before stopping, download and verify
`GET /sessions/{id}/evidence?include=manifest,serial,frames,logs,qom` as a ZIP.
Record ZIP SHA256 and verify its members. Add `flash` only when full mutable
Flash is required. Keep raw packages, images, traces and ZIPs outside source
Git in the operator's artifact location.

Stop only the session recorded as owned by this task:
`DELETE /sessions/{id}?purge=0&retain_flash=0`. Use `retain_flash=1` only if
post-stop raw Flash or snapshots/diffs are explicitly required. Poll the same
session while `stopping`/`stop_pending`; confirm terminal state and lease
release. History/logs/last frame remain, but full Flash is released by default.
An interrupted or failed export does not silently become successful evidence.
If pcap finalization is part of the test, read final `/network` and export
retained evidence again after stop as well as taking the before-stop ZIP.
Do not bulk-purge history or change worker/service lifecycle to clean one task.

## UIFlow-only advanced lane

Generic firmware sessions do not imply a MicroPython REPL. Use UIFlow live
programming only when `/devices` advertises `uiflow-live` and the target's
actual firmware/runtime admits it. For iterative UIFlow use
`POST /previews` with HTTP `Idempotency-Key`, then complete
`POST /program-revisions` checkpoints and `/previews/{id}/runs`. Runs require
`revision_id`, `expected_owner_epoch` and `expected_generation`; poll their
receipts and use Run-bound frames. Preserve every module/resource in each
complete snapshot. These are specialized API operations, not guaranteed
typed commands in the generic helper.

If a session has `management_binding`, it belongs to Preview: use Preview
`input`, `renew`, run cancellation and `close`, never ordinary session mutation
routes. `main.mpy` requires that exact session's current verified loader
capability. Same-VM replacement is interrupt-only; native state, timers, IRQs
and threads may survive. No save-to-boot, arbitrary hotplug or SSE support is
implied. Generic binaries must instead be rebuilt and admitted as firmware.
