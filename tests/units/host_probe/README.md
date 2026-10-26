# Device-local host integration probes

`run_host_cases.py` prepares and runs AtomS3R, StickS3 and StopWatch boot
controls plus Button, Relay and ENV III cases. Preparation alone is not runtime
acceptance. The runner does not modify `runtime-profiles.json` or the service
registry; a missing host/Unit admission still fails closed.

```sh
M5_PYTHON_DEPS="$PWD/.work/py312" PYTHONPATH=.work/py312 \
  /opt/miniconda3/bin/python3.12 tests/units/run_host_cases.py \
  --device sticks3 --prepare-only --out-dir .work/unit-host-preparation
```

The runner parses the actual reference's first-party partition table, requires
one aligned and non-overlapping LittleFS partition, and remounts each generated
image to compare every guest Python byte. It records the effective VFS rather
than copying the old matrix offset. Current StickS3 is `0x651000/0x1AE000`;
AtomS3R remains `0x641000/0x1BE000`, StopWatch `0x820000/0x7DF000`.

Profiles explicitly choose rotation, framebuffer dimensions, text bounds,
UART0 TX43/RX44, internal I2C1 and external I2C0. AtomS3R internal SDA/SCL is
47/0; StickS3 and StopWatch use 47/48. Grove pins come from the confirmed main
connector in `host-ports.json`. StopWatch uses a central text area inside the
round display. Header and value rows each use an explicit cursor position;
ENV values occupy three short rows. The explicit-row layout was subsequently
validated in all nine gen9 native frames linked below. StickS3 assumes no HAT
is attached; StopWatch assumes its
external USB/UART mux remains in the default UART position. These are declared
probe conditions, not physical power/mux validation.

Guest code uses unchanged firmware-bundled ButtonUnit, RelayUnit and ENVUnit
drivers. It reads the real onboard BMI270 CHIP_ID over the internal controller
before Unit construction, afterwards and between external operations. ENV III
must scan exactly `0x44/0x70` on the external connector, accept two independent
physical-value inputs and preserve the internal `0x68` identity. Button covers
both GPIO levels and the original driver's IRQ counter; Relay covers actual
guest output and QOM readback. No ADC fixture is applied.

Execution requires an explicit `--expected-runtime-sha256`, a local
service and already-admitted host/Unit combination. It captures the actual live
PID executable hash, uses visible `/api/v1` sessions, requests the evidence ZIP
before stopping even on failure, and verifies `purge=0` metadata/frame history.
Use a fresh output directory; existing prepared evidence is never overwritten.

Three no-Unit boot controls passed on frozen runtime `1880891d…`; see
[`unit-host-boot-controls/summary.json`](../../../docs/evidence/2026-10-26-unit-host-boot-controls/summary.json).
They establish only that those exact guests initialized the display and kept
the onboard BMI270 identity readable on each declared internal bus. StopWatch
reported a 468×468 guest canvas at rotation 0 while its native framebuffer was
466×466; the profile checks these two dimensions separately. Historical boot
evidence predates the explicit-row layout change and is preserved unchanged.

The nine Button/Relay/ENV III combinations passed the guest data-plane and
strict real-Web checks on generation 9, runtime `a8fe15db…`, with zero retries:
[`host9 evidence`](../../../docs/evidence/2026-10-26-unit-host-web-gen9-a8fe/README.md).
Each case binds its own visible session, direct PID/runtime hash, firmware,
controller evidence and ZIP-before-stop. These nine results do not cover the
other 24 Units per host, ADC calibration or physical electrical behavior.
All nine native frames are complete. The three ENV browser screenshots have
sticky-header occlusion at the session card title/top edge and are separately
classified as framing **PARTIAL**; functional PASS does not imply full visual
acceptance. Historical `1880891d…` boot evidence remains unchanged and is not
spliced with the gen9 executions.
