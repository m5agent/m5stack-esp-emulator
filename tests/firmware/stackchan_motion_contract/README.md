# StackChan official SDK motion contract probes

These are diagnostic firmware sources using the unmodified official
[StackChan-BSP](https://github.com/m5stack/StackChan-BSP) at
`e2f3b02dbe7f28e26a02adc72bef3aa2c545e4a0`. All three motion environments and the separate Dance observer were compiled
with PlatformIO 6.1.18 and the fixed dependencies in `sources.lock.json`.
The lock records the actual source, dependency-tree, ELF, segment and merged
16 MiB image identities. Firmware binaries and execution traces are excluded.
Fresh binaries can differ with build paths or timestamps: record their new
hashes before a runtime test.

| Environment | Actual guest driver path | Behavior under test |
| --- | --- | --- |
| `motion_lifecycle` | Original BSP `Motion` and SCSCL UART1 | Spring updates, both axes, intermediate reversal, auto torque release, explicit torque recovery, rail loss/recovery and same-instance RESET |
| `motion_calibration` | Guest IDF NVS plus original BSP `Motion` | Store zero positions 520/700 before initialization, write pending 550/720, reload only after same-instance RESET |
| `scs_command_edges` | Original SCSCL/PY32IOExpander, one UART caller | Repeat torque=1 during a four-second move via WRITE, REG_WRITE+ACTION and SYNC_WRITE; restore min100/max900 after official PWM-to-position mode switch |

`motion_*` waits for actual top Si12T touch before enabling torque. It ends in
`await_reset`; use the same runtime's RESET, wait for boot2 `ready`, then touch
the top again for `reset_home_done`. `scs_command_edges` starts autonomously;
it deliberately does not call `M5StackChan.begin()` so the BSP Motion task
cannot overwrite its low-level commands. It finishes with a `done` record.

Version2 starts each hold after display output and the real command setup. The SCS
case uses raw time4000ms and hold5000ms; runtime validation must prove all seven
repeats were mid-motion and completion did not restart after a repeat. Version1
counted display work inside holds and is retained as a failed diagnostic.

The lifecycle firmware passively observes original `uart_write_bytes` calls
with a linker wrapper. It forwards every call to the real driver and preserves
its return value. The observer decodes real position packets, including
20 ms time and raw speed0, and reports per-axis counts and intervals. It does
not supply servo positions, ACKs, or controller state.

## Rebuild in ignored storage

Run from the repository root. Use an existing PlatformIO 6.1.18 environment or
install it into a dedicated virtual environment. This only builds files; it
never flashes hardware or starts a guest.

```sh
mkdir -p .work/stackchan-motion-contract/lib
cp tests/firmware/stackchan_motion_contract/platformio.ini .work/stackchan-motion-contract/
cp -R tests/firmware/stackchan_motion_contract/src .work/stackchan-motion-contract/
git clone --no-checkout https://github.com/m5stack/StackChan-BSP.git .work/stackchan-motion-contract/lib/StackChan-BSP
git -C .work/stackchan-motion-contract/lib/StackChan-BSP checkout --detach e2f3b02dbe7f28e26a02adc72bef3aa2c545e4a0
python3 tests/firmware/stackchan_motion_contract/verify_sources.py --bsp .work/stackchan-motion-contract/lib/StackChan-BSP
pio run --project-dir .work/stackchan-motion-contract -j2
```

The source verifier checks bytes and optional BSP identity; it does not claim
compilation or execution. The portable config removes only the machine's
absolute `core_dir` and `build_cache_dir` from the actual compiled config.
PlatformIO may use its normal package cache, or an explicitly selected
`PLATFORMIO_CORE_DIR`.

Compose each full Flash with the existing merge helper (replace the environment
and the framework package path for your build):

```sh
python3 tests/firmware/stackchan_arduino_nvs/merge.py \
  --build-dir .work/stackchan-motion-contract/.pio/build/motion_lifecycle \
  --boot-app0 "$HOME/.platformio/packages/framework-arduinoespressif32/tools/partitions/boot_app0.bin" \
  --output .work/stackchan-motion-contract/motion_lifecycle-16mb.bin
```

The merge helper creates a new file and prints segment/full-image hashes. Keep
new binaries and raw execution evidence under ignored storage.

## Validation boundary

These diagnostics are intentionally different from the official Dance example.
The original Dance leaves torque disabled; an explicit-torque variant is a
separate experiment. A controller or virtual-device PASS does not establish
physical servo speed, load, inertia, torque or mechanical calibration.

Bind browser validation to one locally uploaded image SHA, runtime/WASM SHA and
same-instance serial, actual QOM present positions and framebuffer. Compare
actual model LCD scene-matrix center and normal against independent pitch-X
then yaw+Y transforms, and verify the base/USB remain fixed. Also compare the
LCD pixels with the same guest's framebuffer. Comparing only angle fields is
insufficient.

Host mapping uses fixed mechanical zero positions460/620. Guest NVS520/700
makes SDK logical0 correspond to raw520/700 and therefore model18.75°/25°.
A later NVS change must not make the existing physical pose jump. Preserve raw
out-of-range pitch positions while the visual model clamps to0..90° and reports
`visual-range`.

The original UITK Spring implementation may advance discontinuously when
retargeting midway through a move after `updateWithDelta` calls. These sources
preserve that SDK behavior. A host-code reproduction is a diagnostic clue;
only the actual guest UART trace can bind it to a tested firmware/runtime.


## Three-dance release observer

`dance_idle_release/` is a separate PlatformIO project, with the same pinned BSP
and dependencies. Its source retains all 14/8/8 official dance keyframes and
original delays, uses the explicitly documented diagnostic torque enable, and
adds one `idle_release` UART record when a real SDK `TouchSensor.update()` sees
all three physical touch channel intensities0. It never supplies touch values.
The diagnostic SDK angle reads and serial output introduce observation overhead.
It is a different firmware SHA from the unmodified official Dance.

Build it in another ignored project copy using the same pinned library checkout
and `pio run --project-dir <ignored-copy> -j2`. Wait for a new `idle_release`
record before each actual mouse press. Record DOM pointer targets, model hits,
QOM-confirmed touch-bit down/up results and guest `top_pressed`/`finished`
records. The original blocking Dance loop does not update touch during a dance;
a host delay alone cannot prove the guest consumed the released state.


## Observe ordering and RESET separately

Console UART records and immediate QOM output reads are asynchronous. Do not
assign the last QOM change to a delayed UART phase marker. Record every real
`outputs` acknowledgement, including `unchanged` confirmations, use the guest's
original SDK UART feedback at `phase_end` for that phase, and compare the full
ordered QOM torque/rail/shaft sequence. Stable outputs need not emit new events.

For an exact controller RESET pose boundary, pause the CPUs, perform a real QOM
output read, issue RESET while still paused, and read QOM again before resuming.
Require identical raw shaft ticks on those two real snapshots. Then separately
validate resumed BSP initialization: the unmodified `Servo::init()` converts
ReadPos ticks to integer decidegrees, teleports its animation, calls `update()`,
and only then disables torque. Its rounding can issue a one-tick position
command. Match that real UART command and actual output; do not classify a
commanded boot movement as controller pose loss, and never zero the host model
from a firmware NVS change.


The detailed lifecycle observer does **not** prove a 100ms guest retarget. The
next phase redraws the LCD and serial logging can block before the next real
`Motion.move`; the retained 2026-10-29 aa2ea4ef runtime run recorded 3117ms between its two
actual target records. Keep that mid-animation timing question `partial` and
report the actual wire timestamps. A host-only UITK reproduction cannot close
this guest or hardware boundary.

The 2026-10-29 aa2ea4ef runtime evidence also retains an actual isolated `ReadPos=-1` SDK
fallback during one lifecycle attempt. A single identical-image recheck after
native regression ended passed without fallback. This is a bounded comparison,
not a confirmed host-load root cause or a reliability guarantee. The original
SDK10ms timeout remains unchanged.

## Portable opt-in browser regression

The tracked harnesses serve an explicit public export without changing its
production files. A normal checkout without `M5_PUBLIC_SITE` reports `SKIP`;
no local firmware cache is required for ordinary static checks. To run the
guests, provide the export, exact runtime and firmware SHA256 values, and a
fresh output directory under `.work/`. Existing output directories fail rather
than overwrite prior evidence. The harness records its own SHA and the export
provenance; raw serial, screenshots and detailed reports remain ignored.

Create an image manifest outside source Git. Every selected case needs a
path (relative to this JSON file or absolute) and the actual merged-image SHA:

```json
{
  "scs_command_edges": {"path": "scs_command_edges-16mb.bin", "sha256": "<64 hex>"},
  "motion_calibration": {"path": "motion_calibration-16mb.bin", "sha256": "<64 hex>"},
  "motion_lifecycle": {"path": "motion_lifecycle-16mb.bin", "sha256": "<64 hex>"},
  "dance": {"path": "dance_torque_explicit_idle_release-16mb.bin", "sha256": "<64 hex>"},
  "original": {"path": "dance_original-16mb.bin", "sha256": "<64 hex>"}
}
```

Use the release-observed three-dance diagnostic and the unmodified official
Dance negative control as separate firmware images. Run from the repository
root, replacing the example paths and SHA placeholders with actual values:

The negative control's rebuild source is the pinned BSP's
`examples/Servo/Dance/Dance.ino` (source SHA256
`8863092f75b55999fab8752edc3dba9db818119b190903471f65be4487280180`).
Build that unmodified source in an ignored project copy with the same locked
PlatformIO/BSP dependencies; do not add torque enable. Merge it with the helper
above and put the actual new image SHA in the `original` manifest entry.

```sh
M5_PUBLIC_SITE=.work/public-export \
M5_STACKCHAN_WASM_SHA256='<WASM SHA256>' \
M5_STACKCHAN_MANIFEST_SHA256='<public-site-manifest.json SHA256>' \
M5_STACKCHAN_IMAGES_JSON=.work/stackchan-motion-contract/images.json \
M5_STACKCHAN_OUT=.work/stackchan-motion-guest-attempt-1 \
node platform/tests/test_stackchan_motion_guest.mjs

M5_PUBLIC_SITE=.work/public-export \
M5_STACKCHAN_WASM_SHA256='<WASM SHA256>' \
M5_STACKCHAN_MANIFEST_SHA256='<public-site-manifest.json SHA256>' \
M5_STACKCHAN_POWER_IMAGE=.work/stackchan-motion-contract/dance_torque_explicit_idle_release-16mb.bin \
M5_STACKCHAN_POWER_SHA256='<merged firmware SHA256>' \
M5_STACKCHAN_OUT=.work/stackchan-power-guest-attempt-1 \
node platform/tests/test_stackchan_power_guest.mjs
```

The motion harness defaults to all five cases. `M5_STACKCHAN_CASES` may select a
comma-separated subset, and the report preserves that exact scope. Each case
must independently reach zero live CDP Worker targets before its browser
context is closed; every runtime must create exactly six observed targets. The power
harness checks actual input acknowledgement, a six-second model PWR hold,
guest-originated SHUTDOWN/exit0, unmodified DOM removal, and independently
observed destruction of all six CDP Worker targets. It retains no iframe/window
references and never grants cleanup PASS merely because the browser was closed.

Both use Playwright from `platform/tests/node_modules` by default. Set
`M5_WASM_NODE_MODULES` to another `node_modules` directory and `M5_WASM_CHROME`
to an installed Chrome executable when needed. `M5_WASM_GPU=hardware` selects
the existing hardware-GPU test convention; the default uses SwiftShader.
No native Device Service, user's test port, hardware or public deployment is
used by these static-export browser tests.
