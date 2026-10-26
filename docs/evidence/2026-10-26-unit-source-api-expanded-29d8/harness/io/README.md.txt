# Expanded CoreS3 IO source-API acceptance

Default-ready freeze: `pir`, `dual-button`, `limit`, `key`, `angle`, `light`, `fan`, `rs485`, `hub`. RGB already has separate evidence. This authoring agent only prepared files; it made no API/session call and built no BIN.

Root executes against the idle, current local service:

```sh
M5_UNIT_WEB_BRIDGE=1 M5_PYTHON_DEPS=.work/py312 PYTHONPATH=.work/py312 \
  /opt/miniconda3/bin/python3.12 -B \
  .work/unit-source-io-expanded-20261026/run_expanded_io.py \
  --execute --out-dir .work/unit-source-io-expanded-20261026/live-default9-r1
```

Use `--case pir`, or repeat `--case`, for a subset. Default runtime SHA is `29d8f6ecdc83f4cbd2ca013291b05bc9ef44fb438a115b0ca97f7b5d46d8d28d`; base SHA is `1324f12d3ddd5392f47a9eff537f9ce0b01a8e6e36d829b6bd22cdf82d2c1264`. Existing bridge Node/Chrome environment overrides are honored. Every run needs a fresh child directory here.

```sh
M5_PYTHON_DEPS=.work/py312 PYTHONPATH=.work/py312 \
  /opt/miniconda3/bin/python3.12 -B \
  .work/unit-source-io-expanded-20261026/run_expanded_io.py \
  --prepare-only --out-dir .work/unit-source-io-expanded-20261026/new-preparation

M5_PYTHON_DEPS=.work/py312 PYTHONPATH=.work/py312 \
  /opt/miniconda3/bin/python3.12 -B \
  .work/unit-source-io-expanded-20261026/run_expanded_io.py \
  --check --out-dir .work/unit-source-io-expanded-20261026/live-default9-r1
```

The source request contains every original Python file from `tests/units/io_probe`, plus the exact original prepare config (CASE, WHITE=1, YELLOW=2, IR_CALLBACK_ROOT_PATCH=False). All twelve official driver manifest entries are checked against caller bytes, and the MIT text is retained separately. Preparation calls only the original read-only `driver_manifest` and pure `attachments`; it never calls `prepare`, `build_control_image`, `build_image` or a patch subprocess.

Execution calls the original `validate_io` and `validate_evidence` functions directly, with original assertion source hashes frozen. A subclass of original `Observations` saves copies of real serial/state/input/QOM results; each wait evaluates its original predicate and additionally requires bytes newer than the last accepted input's actual serial cursor. It does not replace responses or return host-computed peripheral values. Same-state ADC zero remains a baseline UI action; subsequent nonzero inputs must use actual product controls. The original per-case checks remain mandatory.

HUB keeps the original ENV-III + NCIR + TVOC topology, initial values and all three child injections. Angle/Light keep the original ideal SAR oracle and application-bound synthetic ADC fixture; their ZIP must include a real `applied` receipt bound to the frozen fixture, without changing identity/security fields. RS485 retains its direct API oversized FIFO rejection and binary RX/echo checks. PIR IRQ disable/rearm, dual-button click states, LIMIT alias/edge/reset, Key native RMT colors and Fan LEDC frequency/duty assertions remain unchanged.

The independent offline checker rechecks fresh guest UART values and real QOM state for every default case, alongside raw HTTP backing, real browser DOM/readback/POST records, direct PID/executable SHA/worker generation, canonical source CAS, session source pin and firmware provenance in ZIP. Every created session attempts ZIP before `DELETE ?purge=0`, then checks retained history/frame, owned PID exit, mutable Flash release and health active count zero. Cleanup failure stops the batch. Frame checks establish nonempty native PNGs; readable-UI acceptance needs a visual review.

`--case ir` and `--case buzzer` explicitly prepare/run original known-gap diagnostic controls with unchanged drivers and original assertions. They are excluded from default execution. A protocol success in such a control is `REVIEW_REQUIRED`, never an automatic original-driver PASS. `--flavor custom` fails closed in this freeze: the separate callback-root/arity guest copies, exact patch hashes and source bindings are pending; no automatic guest patch is applied. See `flavor-boundaries.json` in preparation output.

`source_api_common.py` is frozen from the previously passing five-case source API harness. Only its transparent HTTP recorder, source provenance checker, native PNG checks, canonical JSON and read-only PID checks are reused. The live transport is the existing real `Client`/`WebUIBridge`. No fake Client or binary-upload shim exists.
