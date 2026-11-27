# Migrating Device Service sessions to esp32sim

CoreS3 and Cardputer-ADV select `esp32sim` when you omit `runtime`.
Use `"runtime":"qemu"` to select the frozen native QEMU path. Tab5 also
accepts `"runtime":"esp32sim"`. Its qualified firmware and panel pairs select
it automatically when the runtime assets are ready and the request uses the
basic session path. Other Tab5 sessions default to esp-emu. Explicit `qemu`
and `esp-emu` both select that fallback and return `runtime: "qemu"`.

```json
{"device_id":"tab5","firmware_id":"<stored firmware ID>","runtime":"esp32sim"}
```

Check `GET /api/v1/devices/{device_id}` before allocating a session.
`runtimes` shows per-backend readiness. Tab5's
`runtimes.esp32sim.default_firmware_sha256s` lists normalized Flash digests
for the operator's panel configuration. The bootstrap provisions the
native executable, pinned ROMs and optional Tab5 ESP-Hosted 2.0.13 C6
images. Follow the [deployment guide](deployment.md#部署-esp32sim-设备服务).

| API or behavior | esp32sim contract |
| --- | --- |
| Upload and compose | Use the existing artifact, merged/segmented firmware and reference routes. Creation checks bootloader and app chip IDs, partition bounds and declared PSRAM against the board. The runtime prepares an isolated Flash copy and applies supported preboot fixtures. |
| Runtime selection | The device and session return the selected runtime. `runtime_identity` binds the backend commit, executable SHA, ROM SHA, board and memory. Tab5 adds the P4 ROM revision and C6 ROM/image hashes. Absent or altered pinned assets return `503 backend_not_ready` on an explicit request. |
| Serial and readiness | Read the `console` channel by byte offset. A retained `usb-serial-jtag` channel appears when the guest emits USB data. A live program session reserves UART0 for the guest REPL. Use a serial marker or frame assertion for guest readiness. |
| Screenshots | `GET /sessions/{id}/frame.png?max_age_ms=0` reads a fresh panel frame at a guest scheduler boundary. Tab5 exposes 720 × 1280 raw panel coordinates. Before the first frame, expect `409 frame_unavailable`. Use the default `orient=panel` because an application rotation hint is unavailable. |
| Touch and keyboard | Use `touch` with `x/y` on CoreS3 or Tab5. Actions include `tap`, `hold`, `down` and `up`. ADV accepts physical matrix keys with `kind="keyboard"` and G0 with `kind="button", control="boot"`. CoreS3 uses `control="power"` for its PMIC key. Compose key chords and touch paths with explicit edges. |
| Controller and peripheral injection | Use `kind="imu"` with `accel` in g and `gyro` in degrees/s, plus optional CoreS3 `mag` in µT. Use CoreS3 `battery` with `mv/percent/charging/vbus` and `als` with `ch0/ch1/proximity`. Tab5 `battery` uses `mv/ma/charging`. `adc` uses `gpio/volts` on S3. These are whole controller samples. |
| Tab5 USB and multi-touch | Send `{"kind":"usb-hid","action":"attach","device":"gamepad"}`, then `action="report"` with a 3-byte gamepad or 8-byte keyboard report. Send a neutral report to release and `action="detach"` to disconnect. For multi-touch use `kind="touch-contact"`, `contact_id` 0–4, panel `x/y`, and `action="down"` or `"up"`. |
| QOM and raw state | QOM reads, writes, lists and snapshots, generic device-state probes, encoder, legacy drag, double-click, legacy Unit attachments and QEMU-specific runtime overrides require the appropriate legacy lane. Use the controller inputs above in place of property writes. Unsupported operations return `409 not_supported_on_runtime` or the endpoint's documented capability code. |
| Media | Attach a session-local SD image before boot. The SPI slots are used on CoreS3/ADV and SDMMC on Tab5. Stop with `purge=0` to export the card. Runtime SD eject/reinsert, QEMU SD counters and write-stamp probes require legacy support. Live Flash, Flash snapshots and stopped Flash export are unavailable. |
| Audio and camera | Provision a mono 16 kHz PCM16 microphone WAV at creation. `speaker_capture=true` retains bounded mono PCM with a sample-rate receipt. The legacy Tab5 UserDemo four-channel recording contract and ADV live audio staging require the legacy runtime. CoreS3 accepts a P6 PPM or BMP camera artifact before boot. |
| Network | Omit `network` for offline mode. `profile="esp32sim-sta"` supports a virtual AP with explicit `policy.isolation="trusted-host"` and native NAT. This mode is for trusted firmware. Restricted policies, namespaces, device identity provisioning, BLE, network fault injection and legacy network profiles need a runtime that implements them. |
| Programming and reset | CoreS3 supports `uiflow-live` over UART0. Managed Preview, ADV live programming and official UIFlow2 cloud startup continue to use their existing QEMU lanes. Reset is a guest hardware-reset request for ordinary esp32sim sessions. |
| Evidence and stop | Request the ZIP before stopping. It contains the requested serial, frames, logs, input timeline and `runtime/identity.json`. Include `audio` and `network` for available captures. QOM trees and live Flash are unavailable. Stop retains session history with `purge=0` and releases the lease. Service restart does not reattach a live esp32sim guest. |

An input receipt confirms the controller command was accepted. Check the guest
screen or protocol for application completion. Invalid input syntax returns
`400 invalid_input`, a rejected controller command returns
`409 runtime_input_rejected`, and a closed control stream returns
`503 runtime_control_unavailable`.

The browser workbench uses a separate WASM runtime. On CoreS3 and ADV choose
the browser engine picker or `engine=qemu-wasm` for the frozen alternative.
Tab5 browser execution is NOT RUN. The export and Worker currently admit S3
profiles and deliver only the S3 ROM. Tab5 requires P4 revision-specific ROM
loading, C6 Flash/ROM admission, and P4 input and Worker cleanup verification.
See [Pages deployment](pages-deployment.md) and the [HTTP API](device-service-api.md#native-esp32sim-sessions).
