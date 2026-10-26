# Final IO Unit validation

2026-10-26: eleven CoreS3 official-driver cases **PASS** through visible Device
Service sessions on frozen QEMU
`1880891da692de06612aa0a10b2026c0209875f4641e837df29dc818bb3ac81d`.
`summary.json` selects the exact reports for PIR, Dual Button, LIMIT, Key, RGB,
Angle, Light, Buzzer, Fan, RS485 and the passive HUB with three child drivers.
IR remains **PARTIAL**; this directory does not claim twelve-case completion.

`ir-custom-callback-root/` is a separate supplemental **PASS** for an explicitly
patched custom guest. It retains the same nested callback on the wrapper
instance before native construction. Normal GC is enabled and forced after
registration; valid RX, malformed leader, NEC repeat and the next valid RX all
pass. Its own live PID executable SHA matches the frozen runtime. The original
vendor source is unchanged; the exact patch/original/patched hashes and guest
flavor are in its report. `summary.json` keeps it in `custom_guest_cases`, apart
from the eleven original-driver cases.

Every selected report preserves its serial, framebuffer, exact probe/config,
pre-stop evidence ZIP and `purge=0` history checks. No firmware, ROM or mutable
Flash binary is archived. ZIP members and their hashes are validated by the
runner; `archive-manifest.json` indexes the archived files.

All selected ZIP manifests have worker `worker-b71031d2aef3428b`, generation 5.
`runtime-worker-provenance.json` links them to the frozen service and exact
source-replay receipts. Fan independently sampled its running executable and
verified the frozen SHA. The other ten cases have an indirect association with
the fixed service generation; no direct per-case executable observation is
claimed for them.

`attempts/` preserves the original IR failure, a read-only native-state IR
diagnosis, a GC-disabled comparison, and the HUB QMP-timeout attempt. The final
HUB report selects the later independent successful session. Failed attempts
are retained and do not enter the positive selection.

IR transmit checks distinguish the unchanged public wrapper's raw 16+16-bit
payload from a separate native `uint16.send()` call with complementary NEC8
bytes. The original wrapper does not manufacture the complement bytes.
Read-only RX diagnosis proves that actual RMT memory, IRQ delivery, the IDF
receive path and the native parser produced address `0xed12` and command
`0xcb34`. With normal GC, the original wrapper callback was not observed.
Disabling GC before receiver registration made that original callback appear;
this is a diagnostic comparison, not a general callback PASS or a firmware fix.

The GC comparison's report subsequently says `FAIL` because the old negative
oracle matched `IO_IR_RX_REG` and `IO_IR_RX_MEM32` debug records as callbacks.
The serial retains callback count 1 after the malformed leader. The runner now
matches only anchored `IO_IR_RX ` callback records. This correction has not yet
been rerun and does not turn that saved attempt into a PASS.

`attempts/ir-original-forced-gc-control/` reruns the exact original wrapper with
the same current probe and enabled, forced GC. It observes the first callback,
then fails with `NameError: CASE` in the main probe module. This unstable
original-driver result and its exception are preserved; the callback gap is
not described as a deterministic absence on every run. The custom wrapper
comparison above completes all required stages. A separate initial patched
attempt stopped before RX because a timed second TX overwrote the first TX
observation; `attempts/ir-patched-tx-phase-race/` retains that failure. The final
probe advances to the second TX only after the first real RX callback.

These results establish only their exact virtual-device/controller paths.
Electrical characteristics, physical ADC accuracy, switch mechanics, light,
sound, motor behavior and physical-hardware equivalence remain untested.

Reproduction of the eleven positive cases uses the compatible reference image
and existing dependencies, for example:

```sh
M5_PYTHON_DEPS="$PWD/.work/py312" PYTHONPATH=.work/py312 \
  /opt/miniconda3/bin/python3.12 tests/units/run_io_cases.py \
  --case pir --case dual-button --case limit --case key --case rgb \
  --case angle --case light --case buzzer --case fan --case rs485 --case hub \
  --out-dir .work/io-unit-validation-final-reproduction
```

Use a fresh output directory. Functional execution must remain visible through
Device Service; direct QEMU or regression runners are not this acceptance path.
