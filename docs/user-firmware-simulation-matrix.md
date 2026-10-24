# User firmware simulation matrix

Last reviewed: `2026-10-24`

`platform/tools/user_firmware_matrix.py` selects the most-downloaded compatible
M5Burner images for each simulated ESP device, excludes baseline UIFlow2 when
possible, uploads each merged image through the Device Service `/api/v1`, boots
it, injects a small board-appropriate input probe set, captures serial and
frame evidence after every probe, and stops the session with `purge=0`.

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

## Status

- `PASS`: the board rendered a non-blank application frame, the session stayed
  running, no configured fatal serial signature was observed, and at least one
  probe changed the frame or the serial transcript.
- `PARTIAL`: boot or application output exists, but frame, input, device
  lifecycle or full application readiness is incomplete.
- `FAIL`: boot did not reach the application, the session failed, or a fatal
  panic/watchdog/assert was observed.
- Devices without a display can only reach `PARTIAL`; serial boot alone is not
  application success.
- `runtime_model_gap`: boot/application reached a stable runtime signature
  explained by an unmodeled device capability. This remains `PARTIAL`, keeps
  the original serial/error evidence and is not reported as firmware `FAIL`.

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
- Core2 sessions expose the supported 4 MiB PSRAM model. Radio/unified runs
  now use deterministic TCG/icount scheduling and passed 10/10 independent
  first attempts; the reproduced failure was interrupt-WDT/timer starvation,
  not a proven cache fault. This does not prove physical cache/PSRAM timing.
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
  `3/3`, two `120s` holds pass `2/2`, and two active-BLE `120s` holds pass
  `2/2`, with zero HLI errors and empty HLI/meta queues. Three independent
  stock-firmware leases complete 20, 30, 60 and 120 same-guest reconnect gates.
  Bit-exact Espressif BT controller behavior, physical cache/PSRAM equivalence,
  more than 120 reconnect cycles, multi-hour coexistence/soak and hardware validation remain
  `NOT RUN`.
