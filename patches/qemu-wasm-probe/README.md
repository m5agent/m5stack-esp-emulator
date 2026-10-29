# Experimental QEMU WASM backport

These patches began as research and remain outside the native runtime bootstrap.
The public C/QEMU browser build now uses a fixed subset, with exact ordering and
source hashes in [the build lock](../../scripts/qemu-wasm-build/sources.lock.json).
The historical CLI/control results below do not establish firmware, display,
input, Unit, networking or hardware compatibility. Current CoreS3 browser scope
is recorded in [the Pages evidence](../../docs/evidence/2026-10-28-qemu-wasm-pages/README.md);
see also [the investigation](../../docs/qemu-wasm-port-research.md).

## Source and order

`0001` applies to Espressif QEMU 9.2.2, commit
`40edccac415693c5130f91c01d84176ae6008566`, **after** the complete 30-layer
`PATCHES` sequence in `scripts/bootstrap-unit-runtime.py` at this repository
revision. It is a complete WASM delta; do not first apply the historical local
candidate. It changes 22 common host/build files. All 111 other files from the
112-file board/Unit stack retain their pre-port hashes; `meson.build` is the
only shared file.

The backport uses official QEMU WASM support inspected at
[`v10.1.0`](https://github.com/qemu/qemu/tree/f8b2f64e2336a28bf0d50b6ef8a7d8c013e9bcf3).
Upstream commits used, in order:

```text
7748cdbae899f54f672e2e5ecd2c556c256b2b08
604ac1d87bd650db2c25adcac238577c6aeb5bee
16704598bf3fa8578880e7146a0196d9411ea098
4cd5a25557cab10f8ef81407bed0dd6512526c1c
4c7c05171902d2da678f85c035efdf412ce91c4f
45e82e495d6a9bf59ee80ed2d4c362596f1b559e
208808242f8a34ac93e73c1c1dbafe4c00498f5e
0f46bf659f015d4860c7212b4a6f0656b312d4f4
1a8964424036cdfe1bd11180953d4e95123990f5
8e72b0eb1842ac9813228ad9d9c29203f3823d99
5b78d120ffa2c343728600082777a49cbc825ee1
ccc403ed5844613849deeaf18cba380b55b6e9bf
```

Adaptations retain 9.2's `sysemu/` paths, `os_mlock(void)` ABI and existing
`is_daemonized` stub; handle older anonymous RAM allocation; disable unsupported
host file/shared-memory backends; and locate static gpg-error through the
gcrypt dependency directory only on Emscripten. GLib callback signatures are
made explicit. No peripheral registers or guest API results are fabricated.

`0002` applies to the official libgpg-error 1.51 release archive. It introduces
the wasm32 pthread lock ABI measured by an actual Emscripten 3.1.50 C probe
(size 24, alignment 4, zero initializer). This is a toolchain-specific value;
remeasure it before changing SDK or architecture.

`0003` applies to the official libgcrypt 1.11.0 release archive. On Emscripten
it selects libgcrypt's existing real `getentropy` path instead of the
unavailable Linux/RHEL `getrandom(GRND_RANDOM)` branch. The SDK uses browser
`crypto.getRandomValues` or Node's `crypto.randomFillSync`; there is no entropy
stub. Static WASM crypto/mutex tests passed; the full upstream suite did not run.

`0004` applies to QEMU after `0001`; it retains `system/main.c`'s MIT header.
With `EXIT_RUNTIME=1`, Emscripten explicitly calls `exit(qemu_main())` after
QEMU's normal cleanup, matching native C main's process-exit intent even when
proxy-main keepalive references remain. The native branch is unchanged.
It does not call force-exit or skip cleanup. The separate copied-source build
passed browser version, machine enumeration and machine-none QMP quit with
exit code 0 and all four Workers naturally gone before harness cleanup.
The exact keepalive/fiber source remains a hypothesis, not a measured result.

## Verification and licenses

`0001` passed `git apply --reverse --check` on the built source, and forward
application to a separate reconstruction of the pre-WASM index reproduced
all 22 changed file hashes. The dependency patches passed checks against
their declared release sources. Source/archive and output hashes are in
[the summary](../../docs/evidence/2026-10-28-qemu-wasm-build/summary.json).
`0004` passed application against the original main source and independent
forward/reverse replay, reproducing the main source used for its object build.

QEMU as a whole is GPL-2.0; individual source files and patch portions retain
their respective license headers (the upstream default for files without
headers is GPL-2.0-or-later). Imported `os-wasm` source retains MIT and
`coroutine-wasm` retains LGPL-2.0-or-later headers. The
dependency patches retain their respective LGPL-2.1-or-later terms. Root MIT
does not relicense these changes. No upstream archive, compiled runtime,
firmware or ROM is included here. Distribution of a future linked runtime
requires the corresponding source/build material and applicable notices.

The inherited 2 GiB setting is a template, not a measured minimum. The same
objects were also linked and browser-tested with 256 MiB initial memory,
2 GiB maximum, memory growth and `EXIT_RUNTIME=1`. The final control/exit test
additionally uses `0004`. That earlier control receipt did not run guest firmware; the later CoreS3 experiment below is separate.

## Later CoreS3 experiment (2026-10-28)

The new source reconstruction follows the bootstrap's 30-layer list and
**explicitly appends** `0064-esp32-intmatrix-pending-irq-remap.patch` from
main `f3bab9c0dfcb8a1928fc3f2e064d973a9ac252c9` before `0001`/`0004`.
The native bootstrap list itself was not changed. This 31-layer stack touches
114 files; 113 retain their pre-port bytes, with the shared `meson.build`
receiving host build adaptations. The SHA callback patch below then makes a
small, declared additional C ABI correction.

For the 64KiB configuration, apply QEMU research patches in this order:
`0001`, `0004`, `0005`, `0006`, `0009`, `0010`. Do **not** apply historical
`0007`. Library patches `0002` and `0003` still apply to their own sources.
Use optional `0008` only for the diagnostic receipt. The latest-main context
port, when used, is declared separately below and in the execution summary. Each new patch passed
forward/reverse checks in an independent Git root, including byte-for-byte
comparison with the C sources used by the candidate objects. Do not run a
replay under a parent repository and accept a successful `Skipped patch` result.

- `0005` records the 256 MiB initial/2 GiB maximum growth configuration,
  `EXIT_RUNTIME=1` and exported `ENV`/`callMain` needed by the real board
  environment. This is host configuration, not a measured guest minimum.
- `0006` replaces seven forced compressor casts with three exactly typed
  `void` wrappers around the original int-returning SHA224/256/512 functions.
  WASM had trapped in `esp_sha_start`; native calling conventions had tolerated
  the discarded return. The SHA algorithms and controller values are unchanged.
- `0007` explicitly selects 2 MiB main/default pthread C stacks and overflow
  checks. This is a historical negative diagnostic: it delayed overflow but did
  not stop MMU-entry SP descent. It is excluded from the final 64 KiB profile.
- `0008` adds bounded Flash/fiber stack and heap diagnostics to the WASM source;
  it does not modify controller state or skip operations. It is opt-in research
  instrumentation and is not part of the native bootstrap.
- `0009` saves a const C SP before the main `cpu_exec_setjmp` and restores it
  through Emscripten `stackRestore` on the nonzero return, before original QEMU
  cleanup. The SDK 3.1.50 Asyncify Fiber/SjLj interaction reproduces without
  QEMU in the [C/libffi experiment](../../tests/browser-qemu/fiber_sjlj/README.md).
  Both 2 MiB and 64 KiB compatibility variants have zero drift and natural
  runtime exits; real 64 KiB CoreS3 Flash-MMU entries are also flat. The separate
  `cpu_exec_step_atomic` setjmp is unmodified and unverified.
- `0010` adds an explicit Emscripten-only VM elapsed-time divisor, default 1.
  `vm-div8` selects fixed 8 before vCPUs start. The signed parser rejects values
  outside 1..1024, including negative-wrap inputs; actual C parser/clock
  arithmetic controls passed 24 cases. Enable offset and clock reads share the
  scaled source; host monotonic and `cpu_get_ticks` remain unchanged. The guest
  timers, CCOUNT/CCOMPARE and WDT follow slow virtual time. **WDT expiration is
  also later in wall time**; this is not original physical timing. Combining a
  divisor greater than 1 with icount fails. REALTIME radio pacing is outside
  this offline profile.

Default wallclock r11 remains PARTIAL because the second guest raised a real
LVGL `schedule queue full`; auto and fixed-shift single/icount controls did not
close it. The explicit slow-clock profile is a separate bounded result, not a
claim that the original timing problem was repaired.

The exact CoreS3 fixture, actual Chromium runtime, complete RGB frame matching,
two evidence ZIPs and natural six-Worker exits are summarized in the
[CoreS3 evidence](../../docs/evidence/2026-10-28-qemu-wasm-cores3/README.md).
They establish a bounded virtual-device path, not other devices, hardware,
public browser admission, persistent Flash or Pages deployment.

## Latest main context port (805925d8)

The project worktree merges `805925d8` in `0f003ea1`. Its native `0065` and
`0066` patches are **not applied unchanged** to the frozen 31-layer research
source: their context includes optional Xtensa diagnostic hooks and a different
board source-list layout. `0011-wasm-main805-native-context-compat.patch`
places the original new high-priority IRQ/cooperative-yield and classic RMT
code at the corresponding function points. It adds no replacement controller
behavior. Native bootstrap and native patches are untouched.

Pinned originals:

- `0065-xtensa-high-priority-irq-cooperative-yield.patch`:
  `f03b988372c17147f1b5f8c2fa2dc46366df362626d69b48febe45d48ab35560`
- `0066-esp32-classic-rmt-legacy.patch`:
  `c88b1a85d7c00ae05aef995c3613a28684f011d0d13f0fbe845184136f4882d7`

The source preparation receipt compares added nonempty code lines in all
12 affected files with the originals; the comparison passes. The final build
recompiles 14 objects, including all ten dependencies of changed `helper.h`
and the new RMT object. This is **31 baseline layers plus two explicit context
ports**, not a claim of 33 original patches applying without changes.
The measured diagnostic sequence is `0001 → 0004 → 0005 → 0006 → 0009 →
0010 → 0008 → 0011`; `0008` is optional instrumentation. New high-priority IRQ
TCG helper calls may add host overhead even when icount is disabled; classic
ESP32 RMT guest behavior is not validated by the CoreS3 fixture. Set the actual final link options explicitly to
`-sSTACK_SIZE=64KB -sDEFAULT_PTHREAD_STACK_SIZE=64KB -sSTACK_OVERFLOW_CHECK=2`;
these are not supplied by `0005`, and applying `0007` would select the wrong
stack size. Exact source/build/runtime fingerprints and execution limits are
in the CoreS3 summary.


## Browser stdio QMP context

`0012-wasm-stdio-qmp-main-loop.patch` selects the existing default main-loop
QMP context for Emscripten **stdio only**. Apply it after `0011`; native and
other chardevs keep the original selection. Both guest vCPU threads, original
QMP parsing/dispatch/response, C controllers and framebuffer producer remain.

The r16 negative control proves a narrower failure: guest heartbeats and the
QEMU main loop continue, the UNIX socket stays present for the full 40-second
observation, but the independent QMP context stops calling fd0's poll callback.
The first screendump stays unread in the JavaScript queue. This does not prove
the underlying GLib/watch mechanism; `0012` is an explicit host I/O-thread
configuration that avoids that path. It adds no periodic QMP or keepalive.

This branch no longer offers QMP OOB; the transport never negotiated OOB and
ordinary in-band commands retain their original implementation. The actual
branch logs `M5_WASM_QMP_CONTEXT stdio=1 context=main-loop use_io_thread=0
oob_offered=0` once after installing handlers. Runtime acceptance requires
fresh guest interactions, evidence, stop/reopen and separate idle/reconnect
controls; patch application alone is not PASS.

## Host display and wait path (2026-10-29)

`0013` is a context port of native `0068`/`0069` from `0769ae7c`: attach
Core2's panel to both SPI2/SPI3 and allow the ESP-IDF WDT feed write while
WDTPROTECT remains locked. The frozen classic SPI path already defers panel
DMA until its transaction and consumes it once; native `0074` has a different
preimage and is not applied or claimed. Diagnostic native `0070`–`0073`/`0075`
are not inherited. Subsequent main `32213028` changes only documentation.

`0014` adds an opt-in `M5_WASM_FRAMEBUFFER=1` display listener and the
`shared-rgb565-v1` transport. It snapshots the real QEMU console surface after
its existing controller refresh, with a bounded static buffer, dimensions,
stride and odd/even sequence. Readers copy into private memory and check the
sequence before validating metadata and after the copy. Dirty surface updates
are distinct from repeated browser requests; a static scene must not acquire
an invented animation FPS. QMP screendump remains an explicitly requested
same-guest diagnostic control and the legacy transport, never an automatic
fallback hiding a bad shared snapshot. Native and opt-out paths are unchanged.

`0015` addresses the pinned SDK 3.1.50 `__syscall_poll`, which ignores its
`timeout`. QEMU's proxied host pthread checks readiness immediately and sleeps
in at most five-millisecond host slices only when there is no event. This
preserves zero-timeout, ready-fd and error results, uses host monotonic time,
and does not scale guest clocks, throttle vCPUs or change WDT semantics. The
main-loop call releases BQL/replay locks before waiting. Native poll/ppoll
branches remain unchanged. Deterministic C controls and the real SDK
poll/pipe/pthread experiment are in
[`poll_wait`](../../tests/browser-qemu/poll_wait/README.md); actual browser CPU,
input and exit results still require their own runtime-bound evidence.

## Cardputer-ADV keyboard matrix (`0016`)

`0016-cardputer-keyboard-qcode-map.patch` follows `0015` in the browser build
lock. It changes only the Cardputer-ADV keyboard helpers in
`hw/m5stopwatch/m5_spi_panel.c`; other panel, button and touch paths retain
their behavior. Native bootstrap is unchanged.

QEMU's `QKeyCode` values follow PC scan-code order, so subtracting
`Q_KEY_CODE_A` from an alleged alphabetical A..Z range maps keys to unrelated
matrix cells and misses others. The patch explicitly maps symbolic key codes
to the physical 4x14 matrix, including right-side modifier aliases. `COMPOSE`
is the board-specific carrier for the physical Fn key. Logical Escape,
Delete and navigation events enter the existing FIFO as Fn plus the physical
key; key-down precedes key-up, and each chord releases its key before Fn.
The TCA8418 FIFO, guest I2C registers and original UIFlow decoder remain the
data plane; no decoded character is injected through UART or Python.

The source inputs are fixed independently:

- [Espressif QEMU `qapi/ui.json`](https://github.com/espressif/qemu/blob/40edccac415693c5130f91c01d84176ae6008566/qapi/ui.json),
  commit `40edccac415693c5130f91c01d84176ae6008566`, SHA256
  `0b25e722122221301f0cee76b775a5fda569e45ec9bc73676fb8aad55df903eb`;
- [UIFlow2 2.5.3 `hardware/keyboard/__init__.py`](https://github.com/m5stack/uiflow-micropython/blob/50e440780492aa847378c7d3477ab912f7063bac/m5stack/libs/hardware/keyboard/__init__.py),
  commit `50e440780492aa847378c7d3477ab912f7063bac`, SHA256
  `ca22657f704da629e9659ba50b769f169af077aca16d9dae1c94b269ae85fd33`.

`platform/tests/fixtures/cardputer_qkeycode_40edccac.json` preserves the
nonalphabetical enum and physical matrix. The C replay in
`platform/tests/test_cardputer_keyboard_qcode_patch.py` compiles the actual
patch helpers and checks 204 position, press, release, Fn-order and invalid-key
conditions; the original preimage is a required failing control. These are
mapping controls, not a browser guest result. Browser acceptance separately
requires the same firmware's original `KeyboardI2C` FIFO decoding, matrix
coordinates, counter/frame changes and release state for each declared case.
GPIO interrupt delivery and arbitrary simultaneous modifiers remain separate
validation boundaries. See the
[fixture contract](../../tests/browser-qemu/board_display/README.md).

## Periodic SYSTIMER deadlines (`0017`)

`0017-wasm-systimer-periodic-deadline.patch` changes only the WASM branch of
`esp_systimer_notify`. The old calculation advances an overdue periodic alarm
one interval at a time. A one-millisecond alarm serviced 50 milliseconds late
therefore produces 51 host callbacks in one timer-list pass, including when
its interrupt level is already pending. The extra callbacks cannot deliver
additional guest interrupts while that level remains asserted.

For positive periods, the patch advances the next deadline by whole periods
to the first deadline strictly after the current virtual time. Alarm phase,
elapsed counter updates, raw interrupt state and one-shot behavior retain
their original paths. `__EMSCRIPTEN__` limits this change to the browser build;
native behavior is unchanged. Zero periods, including periods rounded to zero
by the existing conversion, deliberately retain their original semantics.

The checkout-only control in
`platform/tests/test_wasm_systimer_periodic_patch.py` compiles the actual patch
preimage and postimage with the fixed QEMU counter, IRQ and timer-list
functions. The fixture retains their original GPL/MIT headers and hashes.
Late and pending-level cases require the old redundant-callback result as a
negative control; early, exact, zero-period, counter-wrap, disabled-counter
and one-shot cases check preservation. A native compilation must match the
preimage. No `.work` cache, download or guest is needed for these controls.

These controls establish the redundant host-callback defect. A specific
firmware's watchdog stability still requires its own browser guest evidence
bound to the resulting runtime, firmware and normal-clock profile.

## TCA8418 key interrupt acknowledgement (`0018`)

`0018-tca8418-cfg0-key-interrupt.patch` follows `0017` and changes only the
TCA8418 read/W1C branches in `hw/m5stopwatch/m5sw_i2c_devs.c`. The physical
matrix mapping, FIFO bytes and original `KeyboardI2C` decoder remain unchanged.
The native bootstrap patch list does not acquire this browser-build layer.

The authority is [TI TCA8418 SCPS215G](https://www.ti.com/lit/ds/symlink/tca8418.pdf),
sections 8.6.2.1, 8.6.2.2 and 8.6.2.4, pages 28–30. The PDF retrieved on
2026-10-29 has SHA256
`fdd74a30911f0a92a592be42f5f040600ce41609a1ce5d87b287ce435df6a944`.
CFG register `0x01`, bit 4 selects `INT_CFG`. In mode 0, unread FIFO data
prevents clearing `K_INT` (`INT_STAT 0x02`, bit 0); reading the last event
alone does not acknowledge the latched interrupt. The fixed UIFlow2 2.5.3
driver from commit `50e440780492aa847378c7d3477ab912f7063bac` uses this mode:
it drains the FIFO and then writes one to clear `K_INT`.

The old model raises GPIO11 when the last event is read and unconditionally
clears `K_INT` on W1C. A new release between the empty-FIFO check and W1C can
therefore remain queued with `K_INT=0`; the original driver's next poll skips
the FIFO because it first tests that flag. Mode 0 now retains the active-low
IRQ until acknowledgement and preserves `K_INT` if unread events remain.
Other W1C bits and FIFO order are preserved. Mode 1 retains its legacy code
path: the required 50-microsecond deassert/reassert timing is not modeled or
validated by this patch. Interrupt-enable gating and other interrupt sources
are outside this key-interrupt control.

`platform/tests/test_tca8418_irq_patch.py` compiles the actual queue function
and read/write case bodies retained in the bounded GPL-licensed fixture
`platform/tests/fixtures/tca8418_irq_post45.json`, with small register/GPIO
stubs. Required failing preimage controls demonstrate both premature GPIO
deassertion and queued-release/cleared-flag interleaves. Postimage controls
check last-read versus W1C ordering, zero writes, preservation of other status
bits, FIFO byte order and unchanged legacy mode-1 behavior. They need no
`.work` cache or download and establish a C register-contract result only.
The resulting runtime still requires its own same-Flash browser guest
keyboard press/release, serial, framebuffer and cleanup evidence.
