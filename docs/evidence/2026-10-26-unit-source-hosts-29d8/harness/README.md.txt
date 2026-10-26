# Three-host source-API acceptance harness

Authoring scope: AtomS3R / StickS3 / StopWatch × Button / Relay / ENV III,
9 combinations. **No API, browser, guest or QEMU execution has been performed
by this authoring agent.** The offline self-check prepares all nine combinations
and verifies source identity plus lower/upper UART-window guards.

`run_source_hosts.py` copies the four Python files under
`tests/units/host_probe/` byte for byte, then generates only `probe_config.py`
using the exact original `run_host_cases.prepare` config expression. Thus each
request has five Python files. It uploads no driver package: the program uses
the original reference firmware's bundled `unit/hardware/driver` modules.
Those bundled driver bytes are not separately uploaded, patched, rebuilt or
claimed to match an independently reconstructed upstream driver version.

The original `run_host_cases.HOSTS`, `validate_case` and `validate_bundle` are
retained. In particular, the guest keeps native display/canvas setup, the
onboard BMI270 CHIP_ID=0x24 reads before/after init and after external operations,
Button's four GPIO edges/IRQ counters, Relay's two guest output states, and
ENV III's [0x44,0x70] external scan, two vectors and internal-bus isolation.
Original binary-building `prepare`/`build_control_image` are never invoked.

`source_api_common.py` is a byte-exact copy from the accepted expanded IO
harness; [common-origin.json](common-origin.json) pins both hashes. Only its
transparent HTTP recorder and pure JSON/hash/save/time/PID helpers are used.
Its CoreS3-specific source-provenance, base, frame and execution functions are
not used. Host provenance and PNG checks use each row's actual base and native
geometry, while preserving the original host evidence validator.

The authoring snapshot observed these actual references; every fresh preparation
rehashes the current matrix's real image and parses its partition table again:

| Host | Reference SHA256 | Native PNG | Guest canvas |
| --- | --- | --- | --- |
| atoms3r | `91c0f97c904271d4c47d240165fbf5589d44aa0d753ca17d685bfdce5bff199a` | 128×128 | 128×128 |
| sticks3 | `c45d4514e21d94a6c069185e08f05851c75b4747d354c1423decdefa625e1dd3` | 135×240 | 135×240 |
| stopwatch | `ef5e81b6da17ba04a0356b3bde782e9f0f8f93b217701a4414a52a8d8d8532c0` | 466×466 | 468×468 |

Default authoring/preparation is offline and requires a fresh child output:

```sh
M5_PYTHON_DEPS=.work/py312 PYTHONPATH=.work/py312 \
  /opt/miniconda3/bin/python3.12 -B \
  .work/unit-source-hosts-expanded-20261026/run_source_hosts.py \
  --prepare-only \
  --out-dir .work/unit-source-hosts-expanded-20261026/authoring-preparation-r1
```

Do not execute from the existing authoring preparation. Root must first finish
its current repository commit and fetch/sync, inspect the resulting actual HEAD,
and then run a **fresh** preparation/execution in a new output directory with
that exact commit passed as `--source-context-commit`. The script reads HEAD
without spawning Git and refuses a mismatch. It records root's supplied
post-sync identity; it does not fetch or claim it independently proved a fetch.

Only root may execute after confirming the service is idle. Set the task-specific
`UNIT_HOST_SOURCE_COMMIT` to that verified 40-character commit first:

```sh
M5_UNIT_WEB_BRIDGE=1 M5_PYTHON_DEPS=.work/py312 PYTHONPATH=.work/py312 \
  /opt/miniconda3/bin/python3.12 -B \
  .work/unit-source-hosts-expanded-20261026/run_source_hosts.py \
  --execute --source-context-commit "${UNIT_HOST_SOURCE_COMMIT}" \
  --out-dir .work/unit-source-hosts-expanded-20261026/live-post-sync-r1
```

The default exact runtime SHA is
`29d8f6ecdc83f4cbd2ca013291b05bc9ef44fb438a115b0ca97f7b5d46d8d28d`.
Worker identity and generation come from the direct-PID live sampler and are
bound again in session/ZIP metadata. No generation is hard-coded; optionally
pass `--expected-worker-generation` for the generation root actually verified.
Repeat `--device` / `--case` to select a subset.

Execution sends only the five-file Python request to `firmware/uiflow`, pins
the exact host-specific base SHA and canonical source CAS, then supplies the
returned CAS as `uiflow_source_sha256` at visible session creation. There is no
BIN upload shim or alternate merged-image path. Every accepted input saves its
actual pre-input UART cursor and original predicate completions. Live waits
require the original predicate in the new suffix; offline replay also rejects
an observation extending into the next input's cursor window.

The original bundle validator is called unchanged. Its required `pid` is an
alias of the exact same direct sampler's `observed_pid`, not a second inferred
identity. Added checks bind actual browser DOM cells to real browser HTTP,
source files/provenance and original contracts to ZIP, and ZIP acquisition to
before `DELETE ?purge=0`. History/source/frame remain, mutable Flash must be
released, the owned PID must exit and saved cleanup health must be idle. A
cleanup failure halts the batch. Nonblank native PNG checks do not by themselves
establish readable UI or hardware equivalence.

Root can replay a terminal bundle without service contact:

```sh
M5_PYTHON_DEPS=.work/py312 PYTHONPATH=.work/py312 \
  /opt/miniconda3/bin/python3.12 -B \
  .work/unit-source-hosts-expanded-20261026/run_source_hosts.py \
  --check --out-dir .work/unit-source-hosts-expanded-20261026/live-post-sync-r1
```

`self_check.py` is offline, blocks socket/HTTP/Client/subprocess/legacy prepare/
BIN builder calls, and uses explicitly synthetic data only to test UART cursor
bounds. Its `self-check-r1/result.json` is an authoring check, never a guest PASS.
The delivered authoring input must be re-prepared after root's commit+fetch.
