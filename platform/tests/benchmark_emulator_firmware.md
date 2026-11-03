# Same-firmware browser performance observer

`benchmark_emulator_firmware.mjs` is an opt-in executable observer. It loads the
same explicit, SHA-256-pinned merged Flash image through the production local-file
UI in an exported QEMU site or the public `esp-online-tester` site. It does not
replace firmware, CPU, controller, input or framebuffer values. Run the two
engines serially, with heavy builds and other owned guests stopped.

Requirements: a desktop Chromium browser, Playwright, an exported static QEMU
site, and a local merged `.bin`. Neither firmware nor ROM is committed. All
output must be in a new directory below the checkout's ignored `.work/`.
The runner serves QEMU exports on an ephemeral agent-owned port and blocks any
attempt to use a Device Service or the user-reserved ports.

```sh
M5_BENCH_ENGINE=qemu \
M5_BENCH_SITE="$PWD/.work/baseline-site" \
M5_BENCH_DEVICE=stackchan \
M5_BENCH_IMAGE=/absolute/path/to/merged.bin \
M5_BENCH_IMAGE_SHA256=<full-sha256> \
M5_BENCH_OUT="$PWD/.work/benchmark-before" \
M5_BENCH_RUNS=2 \
node platform/tests/benchmark_emulator_firmware.mjs

M5_BENCH_ENGINE=esp32sim \
M5_BENCH_DEVICE=stackchan \
M5_BENCH_IMAGE=/absolute/path/to/the-same-merged.bin \
M5_BENCH_IMAGE_SHA256=<the-same-full-sha256> \
M5_BENCH_OUT="$PWD/.work/benchmark-other-engine" \
node platform/tests/benchmark_emulator_firmware.mjs
```

`M5_BENCH_DEVICE` accepts `stackchan` and `stopwatch`. Optional controls:

- `M5_WASM_NODE_MODULES`: absolute directory containing Playwright.
- `M5_WASM_CHROME`: browser executable, defaulting to system Chrome on macOS.
- `M5_BENCH_SAMPLE_MS`: steady observation window, default 20,000 ms.
- `M5_BENCH_TIMEOUT_MS`: first-frame/ready deadline, default 120,000 ms.
- `M5_BENCH_READY_MARKER`: optional guest UART marker; the known StackChan dance
  SHA defaults to `StackChan auto-dance started`.
- `M5_BENCH_URL`: other engine's platform URL. Its actual WASM/worker/JIT/pacing
  and runtime source hashes are recorded. `M5_BENCH_WASM_SHA256` can require a
  particular WASM identity.
- `M5_BENCH_CANDIDATE_CLOCK=1`: explicitly test a QEMU clock candidate through
  the adapter's existing candidate override. Such output is marked
  `publication_eligible=false`; it cannot confer acceptance on the production
  profile. Firmware and controller values are unchanged.
- `M5_BENCH_PROFILE_MS=10000`: collect CDP CPU profiles for the actual dedicated
  Worker targets. Profiled runs are explicitly marked and must not be compared
  as uninstrumented performance samples.
- `M5_BENCH_WARM_POSITION_MINIMUM=100`: with multiple runs, continue to the
  same-page warm run only if the first run observed at least this many position
  changes. This saves optional sampling time; it does not change any functional
  assertion or establish a performance acceptance threshold. The selection and
  actual observations are recorded in the report.
- `M5_BENCH_REQUIRE_RENDERED_MOTION=1`: for QEMU StackChan motion cases, require
  actual joint angles sampled from the workbench viewer's render event to
  change through intermediate poses. Raw QOM positions, DOM labels, calibrated
  model targets, browser session and firmware SHA must agree. Rendered angles
  are recorded separately from controller observations; neither is a physical
  servo measurement. Older reports without this trace remain unmeasured.
- `M5_BENCH_INPUT=known-device-controls`: after the performance window, send the
  documented StopWatch A+B 1000 ms combination through actual focused model
  keyboard events. StackChan uses the real front capacitive surface (QEMU model
  ray-pick plus mouse, or the other workbench's Digit1 mapping) for 500 ms.
  Record controller receipts, new serial and separate before/after frame PNGs;
  the observer does not infer an application-level response from input ACKs.

The report distinguishes first guest UART, a requested guest ready marker,
first nonblack framebuffer, delivered frames, actual pixel changes and real
servo-controller observations. Frame gaps include the interval crossing the
start of the steady window; this preserves a long freeze after the first frame.
WASM CPU profiles preserve full function indices and byte columns even when the
binary has no names; profiling alone does not identify a source-level hotspot.

Screenshots, exact serial, executed harness, resource timings, runtime/site
hashes and CDP Worker lifecycle observations remain in the output directory.
Normal QEMU shutdown and actual Worker disappearance are checked before closing
the browser context. The required CDP target count is derived from each run's
actual pthread and engine Worker creation receipts, and every observed target
must disappear. The SHA-bound production StackChan profile additionally requires
its declared runtime patch to match the runtime manifest and the engine's actual
Module arguments to contain the exact admitted one-instruction-per-block setting.
This uses the normal product registry and runtime; it does not inject candidate
clock, CPU or accelerator overrides.
The other engine's documented dispose terminates its
Worker; that lifecycle is recorded as that engine's dispose behavior, not QEMU
natural exit.

For short publisher images, prepare the same full-capacity file for both
engines by adding only `0xff` bytes after the original bytes. Record the original
publisher SHA/length and the padded file SHA/length separately. Do not compare
different reference examples or silently combine startup results from different
Flash/NVS contents. This benchmark establishes virtual-device behavior only,
not physical timing, electrical properties, or arbitrary-firmware compatibility.

Recompute old and new reports with the same metrics algorithm, preserving the
original reports and binding the derived summary to their SHA-256 values:

```sh
node platform/tests/derive_emulator_benchmark.mjs --self-test
node platform/tests/derive_emulator_benchmark.mjs .work/comparison-summary.json \
  .work/benchmark-before/report.json .work/benchmark-after/report.json \
  .work/benchmark-other-engine/report.json
```

The derived output uses exclusive creation and will not overwrite earlier data.
It reports QEMU `packet_delta` relative to the last state at/before the steady
window, or the first observed state when no earlier one exists. The initial
servo packets are therefore not counted as steady progress. Both engines also
report `position_change_observations`, comparing successive id/position vectors
within that engine only; initial, order-only and metadata-only observations do
not count as movement, and tick values are not compared with degree values.
Benchmark acquisition/cleanup success does not establish a performance target
or motion acceptance: a measured run with zero position changes must retain
that negative result even when its screen animation and command timing advance.

For the fixed default CoreS3 composition path, use the normal reference UI,
without uploading a local image or overriding the reference's execution clock:

```sh
M5_BENCH_ENGINE=qemu M5_BENCH_SITE=.work/public-site M5_BENCH_DEVICE=cores3 \
M5_BENCH_SOURCE=default-compose \
M5_BENCH_IMAGE_SHA256=78961297e751ec9c743b4cdf89cc2c137e7e2c801dda3ead9df2ea45d59fbd3f \
M5_BENCH_OUT=.work/default-compose M5_BENCH_RUNS=2 M5_BENCH_SAMPLE_MS=20000 \
node platform/tests/benchmark_emulator_firmware.mjs
```

This mode records the composer source and asset identities, verifies the
resulting Flash SHA at the actual runtime, and requires a new Flash input
buffer, new guest session and fresh guest boot in each run. The warm run must
reuse the immutable compiled QEMU module. It is labeled `default-compose` and
must not be mixed with a local-file path as evidence of CPU execution speed.

Test the exact c854 firmware's application touch response separately from the
20-second performance window. Set `DANCE_IMAGE` to the original full-flash BIN
and `DANCE_SOURCE` to its matching, audited source; neither is bundled here.
Use a fresh output directory and the same normal exported product site:

```sh
M5_BENCH_ENGINE=qemu M5_BENCH_SITE=.work/public-site M5_BENCH_DEVICE=stackchan \
M5_BENCH_IMAGE="$DANCE_IMAGE" \
M5_BENCH_IMAGE_SHA256=c854d3ac6b958439ad30c5277266575d8765f228febf75de243da5d011904542 \
M5_BENCH_OUT=.work/dance-touch M5_BENCH_RUNS=1 M5_BENCH_SAMPLE_MS=8000 \
M5_BENCH_INPUT=known-device-controls \
node platform/tests/benchmark_emulator_firmware.mjs
node platform/tests/derive_emulator_touch_response.mjs \
  .work/dance-touch/report.json .work/dance-touch/response-validation.json \
  "$DANCE_SOURCE"
```

The derived validation requires actual trusted pointer down/up events, the
controller's press/release readback, and a same-guest `DANCE restart in 650 ms`
marker between pointer down and 1500 ms after release. It rejects an earlier
post-ready 650 ms restart and keeps the complete response window before the
source's first automatic 16-second boundary. A marker during the hold is valid:
the firmware reacts to a press. Input ACKs, frame changes or a marker after an
ordinary 20-second sample alone cannot establish this application response.

For a private diagnostic export, `M5_BENCH_STOP_ON_DIAGNOSTIC=M5_DOUBLE`
retains the full generation-bound diagnostic stream and stops after the first
matching observer message, real guest panic or guest reset. It drains 150 ms
of trailing messages before graceful cleanup and skips the remaining planned
VMs after a fault. This option rejects publication-eligible exports.

`M5_BENCH_PROFILE_MS=10000` collects raw CDP CPU profiles from the actual
Worker targets after the first frame. A diagnostic fault stops profiling early;
the shorter raw start/end timestamps and sample arrays are retained. Profile
coverage is checked against the run's actual observed targets and receipted
Worker count after cleanup. These are instrumented diagnostic observations,
not uninstrumented performance samples. Bind symbol maps to the exact WASM
bytes (or explicitly verified matching code sections), keep dynamic modules
separate, and do not describe sample counts or residence intervals as CPU time.
