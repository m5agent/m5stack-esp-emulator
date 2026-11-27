# Migrating Device Service sessions to esp32sim

CoreS3 and Cardputer-ADV select `esp32sim` when you omit `runtime`.
Use `"runtime":"qemu"` to select the frozen native QEMU path. Tab5 also
accepts `"runtime":"esp32sim"`. Its qualified firmware and panel pairs select
it automatically when the runtime assets are ready and the request uses the
basic session path. Other Tab5 sessions default to esp-emu. Explicit `qemu`
and `esp-emu` both select that fallback and return `runtime: "qemu"`.
The new S3, classic ESP32 and C6 models can select `runtime="esp32sim"`.
Default changes for paired backends require two stock, docs and regression
runs with the same firmware and variant. M5Stick and StickT2 default to esp32sim.
Their existing QEMU firmware/kernel modes run outside Device Service.
CardputerZero uses a separate Linux backend.

Select `runtime_variant` using the values in `runtimes.esp32sim.variants`.
AtomS3 and AtomS3R offer `st7735s` and `gc9107`. Core2 selects the modeled PMIC
that M5Unified detects on the bus, `axp2101` by default or `axp192` for that
hardware revision. Tab5 accepts `gt911-ili9881c` and `st7123` and retains the
operator panel selection when omitted. Basic v2.7 accepts `flash-4mb` for a
matching merged artifact or reference. A bootloader or partition layout
requiring more Flash cannot use that variant. NanoC6 offers `enviii` for the
fixed ENV III fixture.

```json
{"device_id":"tab5","firmware_id":"<stored firmware ID>","runtime":"esp32sim"}
```

Check `GET /api/v1/devices/{device_id}` before allocating a session.
`runtimes` shows per-backend readiness. Tab5's
`runtimes.esp32sim.default_firmware_sha256s` lists normalized Flash digests
for the operator's panel configuration. The bootstrap provisions the
native executable, pinned ROMs, service control patch and optional Tab5 ESP-Hosted 2.0.13 C6
images. Follow the [deployment guide](deployment.md#部署-esp32sim-设备服务).

| API or behavior | esp32sim contract |
| --- | --- |
| Upload and compose | Use the existing artifact, merged/segmented firmware and reference routes. Creation checks bootloader and app chip IDs, partition bounds and declared PSRAM against the board. The runtime prepares an isolated Flash copy and applies supported preboot fixtures. |
| Runtime selection | The device and session return the selected runtime. `runtime_identity` binds the backend commit, executable SHA, ROM SHA, board and memory. Tab5 adds the P4 ROM revision and C6 ROM/image hashes. Absent or altered pinned assets return `503 backend_not_ready` on an explicit request. |
| Serial and readiness | Read the `console` channel by byte offset. A retained `usb-serial-jtag` channel appears when the guest emits USB data. A live program session reserves UART0 for the guest REPL. Use a serial marker or frame assertion for guest readiness. |
| Screenshots | `GET /sessions/{id}/frame.png?max_age_ms=0` reads a fresh panel frame at a guest scheduler boundary. Tab5 exposes 720 × 1280 raw panel coordinates. Before the first frame, expect `409 frame_unavailable`. Use the default `orient=panel` because an application rotation hint is unavailable. |
| Touch and keyboard | Use `touch` with panel-native `x/y` on boards that model touch. Actions include `tap`, `hold`, `down` and `up`. Both Cardputer models accept physical matrix keys with `kind="keyboard"` and G0 with `kind="button", control="boot"`. GPIO buttons use their board control identifier. Nesso N1 expander buttons use explicit `down` and `up`. Compose key chords and touch paths with explicit edges. |
| Rotary input | Dial accepts `{"kind":"encoder","delta":3,"edge_period_ms":35}`. It schedules quadrature on board GPIO in guest time and rejects overlapping motion. StickT2 accepts a signed detent delta for its I2C encoder with no custom edge period. |
| Sensors and tag fixtures | Dial `rfid` takes an eight-digit hexadecimal `uid`. StackChan and PaperMono `nfc-tag` take an eight- or fourteen-digit `uid`. Send null to remove the tag. StickS3 `ir-nec` takes integer `address` and `command`. PaperColor `sht40` and NanoC6's `enviii` take `temperature_c/humidity_pct`. StackChan `head-touch` takes `pad` 0–2 and `strength` 0–3. |
| Power and PLC | StickS3/StopWatch `battery` use `mv/charging` and `pm1-gpio` uses `channel/high`. PaperColor/PaperMono add optional `vbus_mv`. Basic v2.7 uses `bars/charging/full`. Core2 AXP2101 uses `mv/percent/charging` and AXP192 uses `mv/ma`. Nesso N1 uses `mv/ma/percent/vbus`. M5Stick, StickC, StickC Plus and StickC Plus SE accept battery `mv`. StamPLC `plc-input` uses `channel/high` and `plc-temperature` uses `temperature_c`. |
| Controller and peripheral injection | Use `kind="imu"` with `accel` in g and `gyro` in degrees/s, plus optional CoreS3 `mag` in µT. Use CoreS3 `battery` with `mv/percent/charging/vbus` and `als` with `ch0/ch1/proximity`. Tab5 `battery` uses `mv/ma/charging`. `adc` uses `gpio/volts` on S3. These are whole controller samples. |
| Tab5 USB and multi-touch | Send `{"kind":"usb-hid","action":"attach","device":"gamepad"}`, then `action="report"` with a 3-byte gamepad or 8-byte keyboard report. Send a neutral report to release and `action="detach"` to disconnect. For multi-touch use `kind="touch-contact"`, `contact_id` 0–4, panel `x/y`, and `action="down"` or `"up"`. |
| QOM and raw state | When `service_features` contains `state-snapshot`, use QOM read, list, snapshot and diff with modeled paths below `/machine/board` and `/machine/soc`. Existing QEMU property names have device-specific mappings. StamPLC retains its LM75 write and StackChan retains its yaw and pitch reads. Legacy drag, double-click and Unit attachments use their advertised runtime. |
| Media | Attach a session-local SD image before boot. Modeled SPI slots include CoreS3, StackChan, both Cardputers, Basic v2.7, Core2, PaperDIY, PaperS3, PaperColor and StamPLC. Tab5 uses SDMMC. Stop with `purge=0` to export the card. `sd-media` enables eject/reinsert and write stamps. `spi-sd-read-stats` enables the Cardputer and Cardputer-ADV controller counters. Check `flash-snapshot` for live Flash export and final retained readback. |
| Audio and camera | Provision a mono 16 kHz PCM16 microphone WAV at creation. `speaker_capture=true` retains bounded mono PCM with a sample-rate receipt. The legacy Tab5 UserDemo four-channel recording contract and ADV live audio staging require the legacy runtime. CoreS3, StackChan, AtomS3R-CAM and AtomS3R-M12 accept a camera artifact before boot. Use P6 PPM or BMP for CoreS3/StackChan and a supported board-matched JPEG or uncompressed image for the AtomS3R cameras. |
| Network | Omit `network` for offline mode. `profile="esp32sim-sta"` supports a virtual AP with explicit `policy.isolation="trusted-host"` and native NAT for trusted firmware. When the runtime reports `net-restricted`, use `mode="restricted"` to keep traffic in the emulator's virtual network. Namespaces, device identity provisioning, BLE and the legacy review network profiles require their advertised runtime. |
| Programming and reset | CoreS3 and Core2 support `uiflow-live` over UART0. Managed Preview, ADV live programming and official UIFlow2 cloud startup continue to use their existing QEMU lanes. Reset is a guest hardware-reset request for ordinary esp32sim sessions. |
| Dial encoder | `dial-encoder-state` exposes target and delivered detents and actual GPIO transitions. Submit a new rotation once the prior one finishes. |
| Evidence and stop | Request the ZIP before stopping. It contains the requested serial, frames, logs, input timeline and `runtime/identity.json`. Include `audio` and `network` for available captures. Add `qom`, `flash` or `telemetry` when their runtime features are available. Stop retains session history with `purge=0` and releases the lease. A modeled guest power-off ends the lease with `stop_reason="guest_poweroff"` and retains the final panel frame. Service restart restores history. |

An input receipt confirms the controller command was accepted. Check the guest
screen or protocol for application completion. Invalid input syntax returns
`400 invalid_input`, a rejected controller command returns
`409 runtime_input_rejected`, and a closed control stream returns
`503 runtime_control_unavailable`.

The browser workbench uses a separate WASM runtime. On CoreS3 and ADV choose
the browser engine picker or `engine=qemu-wasm` for the frozen alternative.
Cardputer K132 can select `engine=esp32sim` and load a compatible merged image.
Its legacy QEMU-WASM entry remains the default.
Tab5 browser execution is NOT RUN. The export and Worker currently admit S3
profiles and deliver only the S3 ROM. Tab5 requires P4 revision-specific ROM
loading, C6 Flash/ROM admission, and P4 input and Worker cleanup verification.
See [Pages deployment](pages-deployment.md) and the [HTTP API](device-service-api.md#native-esp32sim-sessions).

Use [paired radio leases](device-service-api.md#paired-esp32sim-radios) for
Cardputer-ADV CAP LoRa/CC1101, PaperMono or Nesso LoRa, and NanoC6 Thread or
Zigbee. The service allocates two leases and returns a joint evidence ZIP.
The pinned LoRa and CC1101 models synchronize over loopback TCP in guest time.
The NanoC6 link advances two Cooja controller models and forwards frames on
the matching virtual channel.
See the [radio synchronization evidence](https://github.com/m5agent/agent-work-logs/tree/c2f333ff576220a0a22c8460297f772c00037be4/records/esp32sim/2026-11-27-radio-peer-synchronization)
and the [pinned Arduino docs defects](arduino-docs-defects-2026-11-27.md).
