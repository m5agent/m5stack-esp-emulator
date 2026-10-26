# CoreS3 expanded controls source-API acceptance

Prepared only. No API/session/QEMU execution has been performed by the preparing agent.

The output directory must be a fresh child of this harness directory. Keep every prior failed run.
Run from `/Users/yunyu/.codex/worktrees/unit-runtime-integration/m5stack-esp-emulator`:

```sh
env M5_UNIT_WEB_BRIDGE=1 M5_PYTHON_DEPS=.work/py312 \
  PYTHONPATH=platform/tools:platform/tests:tests/units:.work/py312 \
  /opt/miniconda3/bin/python3.12 -B \
  .work/unit-source-controls-expanded-20261026/run_source_controls.py \
  --execute --api-url http://127.0.0.1:8787 \
  --out-dir .work/unit-source-controls-expanded-20261026/live-r1 \
  --expected-runtime-sha256 29d8f6ecdc83f4cbd2ca013291b05bc9ef44fb438a115b0ca97f7b5d46d8d28d
```

Use `--case joystick-v11`, `--case 8encoder`, `--case cardkb`, or `--case rfid2` to select a subset. The default runs all four in that order. Unit TTL is 1800 seconds; CardKB deliberately retains the full key-table exercise.

Offline evidence replay:

```sh
env M5_PYTHON_DEPS=.work/py312 \
  PYTHONPATH=platform/tools:platform/tests:tests/units:.work/py312 \
  /opt/miniconda3/bin/python3.12 -B \
  .work/unit-source-controls-expanded-20261026/run_source_controls.py \
  --check --out-dir .work/unit-source-controls-expanded-20261026/live-r1
```

Default or `--prepare-only` prepares transparent source requests without building BIN files. `--check` on a prepared directory validates source packaging without treating it as execution evidence. `--self-test` must use a fresh child output directory and denies socket/API/process/BIN operations during preparation and checking. It also verifies that source drift is rejected. The guard probes themselves are mocked and never reach the network or start a process.

Read `contract.json` for the precise source/runtime/driver/display flavor and retained assertions. The checked-in product and driver files are not edited by this harness. `original-assertion-block.py.txt` preserves the exact extracted host assertion block. Logs and raw serial retain their original bytes; manifests exclude Python caches.
