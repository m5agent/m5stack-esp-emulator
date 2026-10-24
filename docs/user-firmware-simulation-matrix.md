# User firmware simulation matrix

Last reviewed: `2026-10-25`

`platform/tools/user_firmware_matrix.py` selects the most-downloaded compatible
M5Burner images for each simulated ESP device, excludes baseline UIFlow2 when
possible, uploads each merged image through the Device Service `/api/v1`, and
executes the SHA-bound review expectation for that sample. The default
`ui-interactive` mode injects a small board-appropriate input probe set and
captures serial/frame evidence after every probe. Explicit `headless-serial`
and `network-first` modes validate their declared guest markers and network
evidence without requiring a UI frame. Every path stops the session with
`purge=0`.
Each run resolves the current public version and force-refreshes the selected
BIN. `--resume` keeps the selected samples and completed-result history, but
still re-downloads every selected BIN and rebinds its SHA before execution. A
cached file is never treated as the current artifact merely because its
firmware ID and version ID are unchanged; public CDN objects have been observed
to change behind those identifiers. Result keys include
`device:firmware:sha256`, so changed bytes cannot reuse a completed result.
The real metadata/download path was exercised with `--resume --plan-only`:
four cached samples were force-refreshed and the temporary plan was rewritten
without creating a Device Service session.

All PASS/PARTIAL counts below are bound to the SHA-256 values stored in the
committed evidence. They describe those historical artifacts, not whatever the
same public firmware ID serves today. A refreshed file must go through Device
Service again before its boot, frame, input or network result can inherit an
older PASS.

This is virtual-device validation evidence. It may support an external fix,
issue reply, review or release note when the selected firmware boots, reaches a
non-blank application frame, responds to the configured input and records no
fatal serial signature. Results must still be labeled as virtual-device
validation rather than physical-hardware measurements.

## Run

Start the Device Service and run selected devices:

Set `M5_DEVICE_SERVICE_URL` or pass `--service-url` to point the matrix at the
service instance.

```bash
python3 platform/tools/serve.py 8787 \
  --state-dir platform/.cache/service \
  --max-sessions 8 --max-per-device 4 --session-ttl 1800

export M5_DEVICE_SERVICE_URL=http://device-service:8787
export USER_FIRMWARE_OUT="$PWD/artifacts/user-firmware"

python3 platform/tools/user_firmware_matrix.py \
  --service-url "$M5_DEVICE_SERVICE_URL" \
  --devices atoms3r,cardputer-adv,core2,cores3,nanoc6,nesso-n1 \
  --per-device 3 --jobs 3 --observe-seconds 45 \
  --out-dir "$USER_FIRMWARE_OUT"
```

Use `--resume` with the same output directory to retry missing or intentionally
removed sample results without changing the stored hot-firmware selection.
Storage-dependent PaperMono tests can add a session-isolated SD fixture:

```bash
python3 platform/tools/sd_image.py \
  --out /tmp/m5-sd.img --format fat32-mbr --size-mib 64

python3 platform/tools/user_firmware_matrix.py \
  --devices papermono --sd-image /tmp/m5-sd.img ...
```

The fixture SHA becomes part of the result key, so a firmware cannot reuse a
PASS obtained without the required SD media.

## SHA-bound review expectations

FirmwareManifest describes artifact facts; it does not guess whether an
application should expose a UI. Operator review intent therefore stays in a
separate JSON file validated by
[`user_firmware_expectations.schema.json`](../platform/tools/user_firmware_expectations.schema.json):

```bash
python3 platform/tools/user_firmware_matrix.py \
  --devices atoms3r \
  --expectation-file /tmp/m5-review-expectations.json \
  --out-dir /tmp/m5-user-firmware-review
```

Example:

```json
{
  "schema_version": 1,
  "expectations": [
    {
      "device_id": "atoms3r",
      "firmware_id": "1897200000000000358",
      "sha256": "b3597fcabbff57c98618caa8754af84745e9eac35b2868ab3c4cb0935b7c59b3",
      "mode": "network-first",
      "runtime": "qemu-wifi",
      "ready_marker": "got ip:",
      "required_markers": [
        "wifi:connected with myssid",
        "got ip:"
      ],
      "network": {
        "profile": "generic-observe",
        "wifi_ssid": "myssid",
        "wifi_auth": "open",
        "attempts": 1,
        "capture_pcap": true,
        "expected_markers": ["got ip:"]
      },
      "network_observe_seconds": 8,
      "nvs": {
        "partition_label": "nvs",
        "image_path": "review-config.nvs"
      }
    }
  ]
}
```

Supported modes:

| Mode | Required evidence |
| --- | --- |
| `ui-interactive` | Non-blank frame plus observable input response; default behavior |
| `headless-serial` | Declared serial markers, running session and no fatal signature |
| `network-first` | Declared serial markers plus Device Service network status `PASS`; when `capture_pcap=true`, a finalized pcap summary and SHA are also required |

The expectation is matched by `device_id + firmware_id + sha256`. If the public
BIN changes behind an unchanged ID, execution fails closed with an expectation
SHA mismatch instead of reusing the old intent. The expectation digest, NVS
fixture SHA and optional SD fixture SHA are part of the result key.

`wifi_password` literals are rejected. Use `wifi_password_env` and provide the
value through the worker environment; the password is sent to the requested
session but omitted from the result's public expectation echo. Network-first
runs fetch the finalized `/sessions/{id}/network` evidence after session stop,
so DHCP, DNS, TCP and pcap digests stay with the same result.

These modes do not weaken the standard matrix. A missing required marker
remains `PARTIAL`; a forbidden marker is `FAIL`; a running session alone is
never enough for `PASS`.

The first same-session integration run is committed in
[`network-first-review-expectation.json`](../tests/firmware/evidence-2026-10-25-network-first-review-expectation.json):
the public OpenAI BIN with an isolated synthetic NVS fixture reached
`wifi:connected` and DHCP, returned network status `PASS`, resolved
`api.openai.com`, opened a TCP/443 flow and produced a 37-packet pcap while
correctly avoiding a UI-frame requirement. Voice, real OpenAI credentials,
Realtime/WebRTC, WPA2 physical security and hardware remain `NOT RUN`.

## Status

- `PASS`: the selected expectation was fully met. The default UI path requires
  a non-blank application frame, a running session, no fatal serial signature
  and an observable input response. Headless/network modes require their
  declared markers and, for network-first, network status `PASS`.
- `PARTIAL`: boot or application output exists, but frame, input, device
  lifecycle or full application readiness is incomplete.
- `FAIL`: boot did not reach the application, the session failed, or a fatal
  panic/watchdog/assert was observed.
- Devices without a display still require an explicit `headless-serial`
  expectation with application markers; serial boot alone is not application
  success.
- `runtime_model_gap`: boot/application reached a stable runtime signature
  explained by an unmodeled device capability. This remains `PARTIAL`, keeps
  the original serial/error evidence and is not reported as firmware `FAIL`.
- `runtime_fixture_gap`: the firmware reached an application/error page that
  depends on a device fixture the generic Device Service session did not
  attach, such as initialized SD media. This remains `PARTIAL` and is not
  firmware `FAIL`.

The tool records the selected firmware ID, download count, SHA-256, static
partition/image analysis, Device Service session ID, frame metrics, input
response, per-probe frame hashes, `status_reason`, unmet requirements, serial
digest and a bounded set of fatal error lines. Service startup failures are
reported separately as `device_service_startup_failed`; they are not attributed
to the firmware.

## Public cross-vendor sample evidence

The committed
[`cross-vendor-runtime-model-gaps.json`](../tests/firmware/evidence-2026-10-24-cross-vendor-runtime-model-gaps.json)
snapshot covers 18 hot public samples on six S3/C6 devices: 8 official and 10
community builds. All 18 pass static image/partition analysis and execute
through Device Service; 10 reach a non-blank frame, remain running and show an
observable input response, while 8 remain `PARTIAL` for a missing frame, input
response, serial-only device, fatal runtime evidence or an explicit model gap.

### Current public-artifact refresh checkpoint

On `2026-10-25`, a fresh selection resolved four changed public artifacts:
two AtomS3R voice-assistant builds and two PaperMono reader builds. Their
download, static-image analysis, FirmwareManifest import and Device Service
functional execution are now bound to the same SHA-256 values. The committed
21-sample matrix remains a historical hash-bound baseline; it is not used to
inherit results for these refreshed bytes.

The exact refreshed SHA-256 values and static checks are committed separately:
[`refreshed-public-artifacts-static.json`](../tests/firmware/evidence-2026-10-25-refreshed-public-artifacts-static.json).
That record remains the historical `STATIC_PASS / FUNCTIONAL_NOT_RUN`
checkpoint. The later functional run is tracked independently in
[`evidence-2026-10-25-refreshed-four-functional-sd-mbr/evidence.json`](../tests/firmware/evidence-2026-10-25-refreshed-four-functional-sd-mbr/evidence.json).

Full FirmwareManifest imports are also retained in
[`refreshed-public-artifacts-manifest.json`](../tests/firmware/evidence-2026-10-25-refreshed-public-artifacts-manifest.json):
all four manifest validations are `PASS`, all four static reviews remain
`REVIEW_REQUIRED`. Sparse inputs can produce a normalized full-flash SHA
different from the downloaded source SHA; both hashes are recorded.

Device Service execution of the refreshed bytes completed with
`3 PASS / 1 PARTIAL / 0 FAIL`:

| Firmware | SHA-256 | Result | Observed boundary |
| --- | --- | --- | --- |
| `XiaoZhi Voice Assistant For AtomS3R` | `74e714fcef825025c5df61cffeaefed3d5c01b97da4298b42be098740127dae4` | `PASS` | 128x128 Wi-Fi provisioning UI, frame and input response. Six nonfatal ES8311 audio writes failed; voice, audio, provisioning completion and cloud connectivity are `NOT RUN` |
| `OpenAI Voice Assistant For AtomS3R` | `b3597fcabbff57c98618caa8754af84745e9eac35b2868ab3c4cb0935b7c59b3` | `PARTIAL` | The matrix UI/input rule remains `PARTIAL`, but the black-frame root cause is separated from runtime security. The public NVS partition is erased; a dedicated WPA2-PSK probe completes M1-M4, pairwise CCMP RX, DHCP, DNS and TCP/443. A wrong password is rejected at M2 MIC and retries without DHCP. Voice/cloud/audio, WPA3 and physical RF remain `NOT RUN` |
| `阅读卡片 \| EDC Book` | `06eb3b595fc47bc5d35f760a16cdc5795ea8c0fad6295bcee8db5268cf906986` | `PASS` | 480x800 EDC Book launch/continue-reading screen with observable input change. External book-file ingestion and longer reader navigation remain `NOT RUN` |
| `CrossPoint-PaperMono-CJK` | `e2dee32b468da1d743b9fe8889eca959f5c0acdbe09c8f4cc3e69c69f8ebe935` | `PASS` | With a deterministic 64 MiB FAT32+MBR SD fixture mounted as a session-isolated writable drive, the firmware reaches the recent-books main menu and responds to input. Book ingestion, EPUB rendering, Wi-Fi/OPDS and persistence remain `NOT RUN` |

An earlier run without storage produced `2 PASS / 2 PARTIAL`: CrossPoint
initialized the SD controller but could not mount a card and rendered
`SD card error`, classified as `runtime_fixture_gap`, not firmware `FAIL`.
That historical result remains in
[`refreshed-four-functional/evidence.json`](../tests/firmware/evidence-2026-10-25-refreshed-four-functional/evidence.json).
The final run supersedes only the storage axis. A separate
[`openai-nvs-precondition.json`](../tests/firmware/evidence-2026-10-25-openai-nvs-precondition.json)
checkpoint supersedes the OpenAI root-cause ambiguity: the public NVS partition
is entirely erased, and the application requires `config/wifi_ssid`,
`config/wifi_password` and `config/openaikey`. Both the synthetic Open fixture
and the WPA2-PSK fixture now reach association, DHCP, `api.openai.com` DNS and
TCP/443. The WPA2 path additionally completes M1-M4 and pairwise CCMP RX; a
wrong-password control is rejected at M2 MIC, deauthenticated and retried
without DHCP. The black frame is no longer treated as evidence that NVS,
display initialization or the WiFi security path failed.

The probe uses `runtime=qemu-wifi` plus the generic ESP32-S3
`generic-observe` profile. That profile runs an arbitrary complete S3 image
with the QEMU board and WiFi NIC but does not require UIFlow/HCI markers, BLE
or a UI frame. It is intended for network-first and headless firmware; its
result remains separate from `qemu-unified` board/WiFi/BLE PASS.

The final run retains four Device Service sessions, final screenshots, serial
digests, normalized artifact hashes, session storage SHA and exact
input/frame observations. The matrix now includes the storage fixture SHA in
the result key and never mounts the source artifact directly.

Two samples are classified as `runtime_model_gap`:

- NanoC6 Zigbee HA light blocks `Zigbee_main` and triggers the task watchdog;
  the current C6 profile has no Zigbee radio/controller model.
- Nesso N1 Meshtastic first enters the C6 ROM/application but a later
  `LP_SW_HPSYS` reset reports chip id 12 instead of 13, exposing a QEMU C6
  software-reset model defect.

The historical snapshot classified both samples as `runtime_model_gap`.
`RUNTIME-01` is now fixed: the C6 flash model distinguishes legacy three-byte
program/erase commands from four-byte reads, and reset clears stale PMP state.
The same Meshtastic SHA was rerun through Device Service with
`runtime_model_gaps=[]`; its state is now
`PARTIAL/fatal_after_application_frame`, not `Invalid chip id`.

`RUNTIME-02` Zigbee/802.15.4 remains `OPEN`. Exact scope and closure evidence
are maintained in the
[runtime model-gap register](runtime-model-gap-register.md).

### Core2 public firmware extension

A separate 90-second Core2 run adds the three most-downloaded public Core2
images. Combined with the six-device snapshot, current sample coverage is
seven devices and 21 public non-baseline images: 10 `PASS`, 11 `PARTIAL` and
zero `FAIL`.

| Firmware | SHA-256 | Current result | Runtime model gap |
| --- | --- | --- | --- |
| `UIFlow_Core2` | `18d77e28adfacf7e719a167bd0c3450b78357d13cb1d2f2a8b7bccc2248a909a` | `PARTIAL` | AXP address/chip-id probe passes; the next address-`0x51` RTC-candidate transaction is not acknowledged on the legacy controller path |
| `Core2FactoryTest` | `4dbddb210d382ed3ca536fc07c962521b238c025016213c947fb4ff7a1bbd4ef` | `PARTIAL` | AXP discovery succeeds; legacy controller/board-bus routing fails during PMIC/RTC initialization and leaves no frame |
| `Core2_For_AWS` | `22ee8c0f5d3c9640be370cb1a89496ed265b685d573b0e41d62320cf6288ff3a` | `PARTIAL` | ATECC608 secure element is not modeled; firmware aborts |

The `UIFlow_Core2` sample was rerun with both default AXP2101 and the narrow
`M5SW_CORE2_PMIC=axp192` runtime override. Both variants produce the same
`OSError: I2C bus error (19)` and black frame. Focused I2C tracing later
confirmed that the AXP2101 chip id `0x4a` is readable. The next controller
transaction targets address `0x51` with no ACK before another address-`0x34`
PMIC read occurs. Frozen BM8563 qstrs, the RTC address and the call stack point
to the legacy controller-to-board-bus routing/handoff path rather than a
proven PMIC register value mismatch.

These are tracked as `RUNTIME-03` for Core2 legacy I2C controller/board-bus
routing and `RUNTIME-04` for the Core2 for AWS ATECC608 secure element. They
remain `OPEN` until the relevant guest data paths complete.

Evidence:
[`core2-public-firmware-model-gaps.json`](../tests/firmware/evidence-2026-10-24-core2-public-firmware-model-gaps.json).

The 90-second run also exposed and fixed a matrix-client timeout: the HTTP
`/wait` request used 90 seconds while the server was allowed to wait 90 seconds
for a frame. The client now derives its request timeout from
`observe_seconds + 15`; failed short-window and client-timeout snapshots remain
separate.

The evidence retains serial hashes and bounded error lines while keeping the
model-vs-firmware boundary explicit. PARTIAL samples are not promoted to
functional PASS.

## Boundaries

- CardputerZero is an ARM64 Linux device and has no CardputerZero entry in the
  M5Burner ESP firmware catalog.
- Some Burner device names have fewer than three compatible, non-baseline
  samples. The plan records the exact partial coverage instead of substituting
  an incompatible image.
- NanoC6 has no display. Its serial-only runs remain `PARTIAL` by design even
  when boot, input injection and serial output pass.
- Tab5 service sessions attach the documented PI4IOE, INA226, RX8130 and
  BMI270 register devices to I2C1. Uploaded Tab5 images still lack a matching
  ELF, so AP-frame and touch capture remain unavailable.
- Core2 has 8 MiB physical PSRAM, but the current QEMU machine supports at most
  a 4 MiB emulated PSRAM model. Generic-firmware sessions can use that 4 MiB
  model. Native-controller runs request CLI `-m 0`, which the current
  `m5core2` machine resolves to a 4 MiB QOM memory with `has_psram=true`.
  These are separate runtime-memory configurations, and neither proves
  physical cache/PSRAM timing. Radio/unified runs now use deterministic
  TCG/icount scheduling and passed 10/10 independent first attempts; the
  reproduced failure was interrupt-WDT/timer starvation, not a proven cache
  fault.
  Stock VHCI paths pass external
  NUS GATT 5/5 standalone and board+WiFi+public+BLE 3/3 in one guest, but
  the QEMU native-HCI path is now canonical. `HCI-4` passed five independent
  Device Service leases with frame/QOM, WiFi/public network, external NUS
  GATT, pcap and evidence, without a GDB bridge. The prior timeout was caused
  by a 21-byte probe producing a 24-byte ATT PDU over the default 23-byte MTU.
  A 15-byte probe produces a 17-byte ATT PDU and reaches the ATT write
  handler, Python notification and Bumble ACK. HLI event/ACL delivery,
  API-boundary H2C and CCOUNT TB-yield are retained in the `0003` and `0004`
  QEMU patches. `0005` restores caller-saved sregs around nested guest calls
  and gates HLI allocation/callback injection to halted/idle vCPU state.
  Two independent `5×10s` batches pass `10/10`, three `60s` holds pass
  `3/3`, two `120s` holds pass `2/2`, and two active-BLE `600s` holds pass
  `2/2`, with zero HLI errors and empty HLI/meta queues. One `7200s`
  active-BLE WiFi/public-network/GATT hold is `DIAGNOSTIC_PASS` because the
  QEMU path was rebuilt during that run. A replacement run with pre-launch
  firmware/ELF/QEMU hash binding passes the two-hour functional gate, including
  frame/QOM, WiFi, public DNS/HTTP, external GATT, pcap, HLI health and cleanup.
  Its QEMU host RSS rises from `744160` to `1202176 KiB`; `vmmap` later
  attributed the growth to the unbounded TCG translation buffer. A
  `tb-size=128` 120-second run is stable; the final artifact-bound two-hour
  rerun also passes with RSS `323536→252992 KiB` and phys footprint
  `250880→188416 KiB`. Three independent
  stock-firmware leases complete 20, 30, 60 and 120 same-guest reconnect gates.
  Bit-exact Espressif BT controller behavior, physical cache/PSRAM
  equivalence and hardware validation remain `NOT RUN`; three independent
  artifact-bound 121-cycle reconnect leases pass.
