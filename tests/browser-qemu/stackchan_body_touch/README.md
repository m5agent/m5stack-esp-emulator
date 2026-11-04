# StackChan three body-touch browser probe

This independent case tests the three visible roof touch areas through the
default official UIFlow workbench. It does not inherit the PMIC button or LCD
touch result from another runner. Preparation and syntax/model contracts are
**not guest execution**; run this case separately on the exact exported runtime.

```sh
M5_PUBLIC_SITE="$PWD/.work/public-site" \
M5_PUBLIC_QEMU_OUT="$PWD/.work/stackchan-body-touch-run1" \
M5_WASM_NODE_MODULES="$PWD/platform/tests/node_modules" \
M5_WASM_CHROME="/path/to/system/chrome" \
node platform/tests/test_public_stackchan_body_touch_guest.mjs
```

Use a new output directory under ignored `.work/`, the source-matching static
export with UART support and the public StackChan keyboard help. Default base
path is `/showcase/`; `M5_PUBLIC_BASE_PATH` must match the export. Run one guest
at a time, without concurrent builds or timing probes. The script uses a random
agent-owned static port and blocks Device Service routes.

The public model maps focused **Z / X / C** to Front / Middle / Back, retaining
**P** for the separate PMIC key. The runner checks these actual aliases and
visible help; it never installs a test keymap or calls `component.press()`.
For each of the three areas it sends a real Playwright keydown/up and a real
mouse down/up, each with a fixed requested 250 ms hold. Mouse coordinates come
from actual mounted geometry and must pass both the normal viewer raycast and
the topmost canvas check. Missing edges fail; no retry or longer fallback pulse
can turn that attempt into PASS.

The existing public path is:

```text
actual touch-N component state
  -> model-shell capacitive-touch(zone=N, down)
  -> public runtime input / private iframe port
  -> QMP /machine/si12t touch-bits read/modify/write/readback
  -> original guest I2C address 0x68, output register 0x10
  -> Si12T.get_touch_status() -> hardware.StackChan.get_touch()
```

The source basis is official UIFlow `release/2.5.3`, commit
`db526eccc003335a89c3237112fcf2d1eb2d0904`:

- `m5stack/libs/hardware/stackchan.py`: I2C1 SDA12/SCL11 at 100 kHz;
  `StackChan(i2c=1, uart=1)` exposes its original Si12T driver as `touch`.
  `get_touch()` reverses the three raw register slots.
- `m5stack/libs/driver/si12t.py`: 7-bit address `0x68`, output register `0x10`,
  two bits per raw slot with levels 0–3; a failed read returns `None`.
- The bundled official StackChan controller docs document `get_touch()` and
  demonstrate reading it from `M5.update()` loops. The driver files above are
  unchanged between that release tag and the inspected local upstream source.

| Public area | QMP bits while held | Original raw driver slots | Original public `get_touch()` |
| --- | --- | --- | --- |
| Front / touch-1 | `0x30` | `[0,0,3]` | `[3,0,0]` |
| Middle / touch-2 | `0x0c` | `[0,3,0]` | `[0,3,0]` |
| Back / touch-3 | `0x03` | `[3,0,0]` | `[0,0,3]` |

Each release must return all three slots and the QMP readback to zero. The
observer calls the original board API and original public driver; it injects
no Python state, fake I2C bytes or private ISR. Because the board wrapper masks
read errors as zero, an additional real driver read must succeed. Observations
are emitted only when its raw sample and the board API sample agree; a genuine
transition between these two I2C transactions is sampled again. A nonce,
sequence, guest clock and both original API results bind each observed edge.
The constructor initializes the board; the observer never enables servo power
or commands a servo movement.

The raw report binds the observer/executed source, control script, pointer
helper, model/viewer/button sources, programming firmware registry, exact
Flash/WASM/export and actual model events, QMP readbacks and guest output. It
also requires raw-REPL interruption and normal exit0, no fallback termination,
actual nested pthread disappearance while the iframe is held, and all CDP
Worker targets gone before context closure. `summary.json` is bounded below
64 KiB; firmware, ROM, screenshots, full serial and full CDP records stay in
ignored raw output.

This only covers six isolated 250 ms keyboard/pointer pulses through three
logical regions. Electrode boundaries in the visual target are inferred.
Physical capacitance, touch thresholds, analog sensitivity, gestures, overlapping
regions, arbitrary hold durations and physical timing are outside this case.
The old fixed StackChan script's 400 ms body logger and its LCD/PMIC acceptance
cannot establish these new default-workbench results.
