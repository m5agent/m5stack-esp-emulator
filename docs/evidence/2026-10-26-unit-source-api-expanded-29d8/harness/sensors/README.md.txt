# CoreS3 sensor source-API acceptance

Prepared 2026-10-26. **Runtime NOT RUN by the preparing agent.** Only root may
invoke the explicit execution command. All outputs stay below this harness.

The seven functional cases are `color`, `tof`, `ncir`, `heart`, `tvoc`,
`ultrasonic-i2c`, `thermal`. `--case all` selects these seven, not the independent
`thermal-missing-fixture` negative control. NCIR uses the original sensor probe,
not the earlier guide or another session's PASS.

## Commands

Use Python 3.12 and the same dependencies as the prior source-API batch:

```bash
PYTHONPATH=.work/py312 /opt/miniconda3/bin/python3.12 \
  .work/unit-source-sensors-expanded-20261026/run_source_sensor_acceptance.py \
  --prepare-only --case all \
  --out-dir .work/unit-source-sensors-expanded-20261026/prepared-new
```

The delivered `prepared-r1/` is a source-only preparation, not firmware execution.
Do not reuse an existing output directory; failed runs are preserved.

```bash
PYTHONPATH=.work/py312 /opt/miniconda3/bin/python3.12 \
  .work/unit-source-sensors-expanded-20261026/run_source_sensor_acceptance.py \
  --check-prepared \
  --out-dir .work/unit-source-sensors-expanded-20261026/prepared-r1
```

Root-only real API/visible-browser execution, against an already idle generation
11 service. This command is documentation; the preparing agent has not run it:

```bash
M5_UNIT_WEB_BRIDGE=1 PYTHONPATH=.work/py312 /opt/miniconda3/bin/python3.12 \
  .work/unit-source-sensors-expanded-20261026/run_source_sensor_acceptance.py \
  --execute --case all --expected-worker-generation 11 \
  --out-dir .work/unit-source-sensors-expanded-20261026/live-r1
```

Select the non-Thermal six explicitly when desired:

```bash
M5_UNIT_WEB_BRIDGE=1 PYTHONPATH=.work/py312 /opt/miniconda3/bin/python3.12 \
  .work/unit-source-sensors-expanded-20261026/run_source_sensor_acceptance.py \
  --execute --case color --case tof --case ncir --case heart --case tvoc \
  --case ultrasonic-i2c --expected-worker-generation 11 \
  --out-dir .work/unit-source-sensors-expanded-20261026/live-six-r1
```

Run Thermal's missing-calibration negative separately; PASS here means the NACK
control passed, never a working thermal-sensor claim:

```bash
M5_UNIT_WEB_BRIDGE=1 PYTHONPATH=.work/py312 /opt/miniconda3/bin/python3.12 \
  .work/unit-source-sensors-expanded-20261026/run_source_sensor_acceptance.py \
  --execute --case thermal-missing-fixture --expected-worker-generation 11 \
  --out-dir .work/unit-source-sensors-expanded-20261026/live-thermal-negative-r1
```

Independent replay of captured bytes makes no HTTP call or process launch:

```bash
PYTHONPATH=.work/py312 /opt/miniconda3/bin/python3.12 \
  .work/unit-source-sensors-expanded-20261026/run_source_sensor_acceptance.py \
  --check --out-dir .work/unit-source-sensors-expanded-20261026/live-r1
```

Deny API/socket/process/BIN while testing offline preparation and the preserved
numeric/thermal validators. `self-check-r1/self-check.json` is the delivered
successful receipt; reruns need another fresh output name:

```bash
PYTHONPATH=.work/py312 /opt/miniconda3/bin/python3.12 \
  .work/unit-source-sensors-expanded-20261026/run_source_sensor_acceptance.py \
  --self-check --out-dir .work/unit-source-sensors-expanded-20261026/self-check-new
```

## Source and scope

- Every guest `.py` except the explicitly generated `probe_config.py` is copied
  byte for byte from `tests/units/sensors_probe`. All original driver imports,
  startup/negative checks, UI, conversion delays and TVOC's real 15-second
  initialization remain unchanged. The official driver manifest and MIT
  license are frozen. Thermal's public EEPROM/subpages, reference expected
  values, synthetic-plus16 data, Apache license and notice are frozen separately.
- `sensor_contract.py` contains the byte-exact `CASES`, `reading_matches`,
  `thermal_reading`, `validate_evidence` host fragments from the repository's
  `run_sensor_cases.py`; `contract-origin.json` binds original source SHA/lines.
  It does not import the old runner or any image builder. The guest is parsed
  for syntax and serialized as text; it is never executed on the host.
- `source_api_common.py` is byte-exact from the prior five-case source-API
  observer. Its transparent HTTPRecorder records original request/response
  bodies, status, response size/SHA; returned bytes are unchanged. Root execution
  uses the real repository Client and Web bridge. The intake subclass only
  rejects binary/artifact paths; it never redirects or fabricates an upload.
- `POST /firmware/uiflow` precedes `POST /sessions` with exact firmware ID and
  caller-source pin. Base is `1324f12d…`, runtime is `29d8f6ec…`, expected worker
  generation defaults to 11. Only a localhost API is accepted for direct PID
  proof. No local BIN/image/ELF is created or uploaded.
- Source limits are 128 files, 256 KiB per file and 1 MiB aggregate UTF-8 source;
  independently the complete serialized HTTP JSON body must fit 1 MiB. Actual
  default-Client serialization size is recorded in each prepared row.

## Runtime and offline assertions

All required negative markers use anchored `SENSOR_CHECK <name> PASS` lines.
Ordinary sensors require the original initial vector and both original changed
vectors; ToF and Ultrasonic use both mm/cm outputs. Every changed input has an
actual before-cursor response, contiguous serial chunks after the input, raw
fresh bytes, before/after Unit QOM state, a native PNG, and captured browser
field POSTs. Reading/finite/tolerance matches are replayed from bytes, not a
stored boolean. The Heart wrapper still calls the firmware's native cdriver;
there is no medical HR/SpO2 claim.

Thermal requires the original EEPROM/two-subpage fixture, then only the raw
frame0/frame1 synthetic-plus16 values through the Unit input. Both phases must
reproduce 768 finite pixels, nine reference indices and min/max/mean within
0.05 C. No host temperature-array injection is substituted. The separate
missing-fixture control requires NACK, `raw-fixture-ready=false`, no fabricated
thermal reading, and is labeled `negative-runtime-control`.

Each case retains actual chip I2C transactions/read-bytes/written-bytes,
samples-generated and crc-errors HTTP/QOM responses. Positive sensor cases
require nonzero traffic and samples; TVOC also requires its deliberate invalid
argument CRC to increment the chip counter. Actual product DOM properties are
cross-checked against captured browser HTTP, with real gestures for all changed
fields. Initial/changed/final PNGs and retained history frames are preserved.

Evidence ZIP is requested before stop. Both the original sensor ZIP validator
and source/PID/worker/provenance validator run. Replay checks ZIP member hashes,
source CAS, source pin, registry hashes, initial/changed readings, original
negative markers and every recorded serial HTTP byte range. Finally
`DELETE ?purge=0` preserves metadata/serial/frame, releases mutable Flash,
checks the owned QEMU PID exit and health/worker active count 0. Cleanup errors
stop the remaining batch and remain alongside the original failure.

The checker verifies the retained recordings; it cannot re-inspect an exited
PID. Physical sensors, optical/gas/acoustic/electrical/timing fidelity and
hardware are NOT RUN. Seven passing cases cannot close original Buzzer/IR,
other-host, other-firmware or shared-runtime full-matrix gates.
