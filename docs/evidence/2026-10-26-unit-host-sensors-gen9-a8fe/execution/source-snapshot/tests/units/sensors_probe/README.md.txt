# Official-driver I2C sensor probes

These probes exercise Color/TCS3472, ToF/VL53L0X, NCIR/MLX90614,
Heart/MAX30100, TVOC/SGP30, Ultrasonic-I2C/RCWL and Thermal/MLX90640.
Each executes unchanged official M5Stack driver source on the guest, after
register-level negative assertions. The Heart wrapper calls the firmware's
native `cdriver.MAX30100`; it is not replaced by a Python sensor API.

`sensor_drivers/source-manifest.json` binds each copied file to immutable
upstream commit `3a86d8f611b3639cca755a933e01a5a829771ef1`, its original Git
blob and SHA-256. Copyright/SPDX headers are preserved. The code is MIT;
the public MLX90640 raw dataset has its separate Apache-2.0 license/notice.

Prepare without any API request or runtime execution:

```bash
PYTHONPATH=.work/py312 /opt/miniconda3/bin/python3.12 \
  tests/units/run_sensor_cases.py --prepare-only --case all \
  --out-dir /tmp/m5-sensors-prepared
```

The shared package builder creates actual LittleFS directories for official
relative imports. The runner uses `prog_size=32`, remounts each built image,
and compares every packaged Python file with the original bytes. `BUILT`
only describes this offline preparation.

Execute against an already prepared Device Service:

```bash
PYTHONPATH=.work/py312 /opt/miniconda3/bin/python3.12 \
  tests/units/run_sensor_cases.py --case all \
  --out-dir /tmp/m5-sensor-sessions
```

The default host is CoreS3 with its confirmed Port A. UART0 TX43/RX44 records
markers and exceptions; ordinary USB `print` is not used for assertions.
Other hosts use their UART0 defaults and require independent driver, wiring
and console validation. A CoreS3 PASS cannot be inherited by another host.

Every runtime case uploads its firmware, creates a visible `/api/v1` session,
injects inputs into that same session, checks official guest readings and
real I2C transaction/sample counters, and obtains its evidence ZIP before
`DELETE ?purge=0`. It validates ZIP hashes, firmware/session identity,
negative assertions, changed-input readings, QOM/Unit contracts and a
nonblank application frame. Metadata and the last frame are checked after
stop. Cleanup errors are retained alongside the original failure.

## Assertions and boundaries

| Sensor | Negative/controller checks | Injected driver observation |
| --- | --- | --- |
| Color | command bit, read-only ID, integration delay, ADC saturation | four RGBC raw channels through official `get_color_raw` |
| ToF | reset identity, conversion ready/clear, old/new I2C address | official mm and cm range APIs |
| NCIR | EEPROM write rejection, both SMBus PEC responses | ambient/object temperatures, tolerance 0.021 C |
| Heart | FIFO empty/order/pointer, overflow, reset and shutdown | official native-driver raw IR/red samples; no medical HR/SpO2 claim |
| TVOC | pre-init measurement, real 15-second startup, busy NACK, response CRC, single consumption, invalid CRC/command | eCO2/TVOC/raw-H2/raw-ethanol through official command and CRC handling |
| Ultrasonic | invalid command, pre-ready NACK, 24-bit micrometre units | official mm/cm values |
| Thermal | EEPROM write rejection, control readback, ready/subpage progression | guest EEPROM calibration and `get_frame`, 768 finite values, nine reference pixels and min/max/mean within 0.05 C |

Thermal starts with the public manufacturer-example EEPROM/two subpages,
then injects both subpages of the reproducible raw-IR `+16` variation during
the same lease. New expected temperatures must appear in that guest's serial
output. No direct temperature-array input or fake guest I2C return is used.

The separate negative control verifies that missing raw calibration stays
fail closed; it does not establish a thermal sensor PASS:

```bash
PYTHONPATH=.work/py312 /opt/miniconda3/bin/python3.12 \
  tests/units/run_sensor_cases.py --case thermal --thermal-no-fixture \
  --out-dir /tmp/m5-thermal-unconfigured
```

All runtime results are virtual-device validation. Optical/acoustic accuracy,
gas response, physical timing, electrical properties and hardware equivalence
require separate physical-device evidence. Current acceptance belongs to
the project status/backlog/validation ledger, not this probe description.
