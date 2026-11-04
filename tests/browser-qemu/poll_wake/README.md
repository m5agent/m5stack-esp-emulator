# Wakeable host poll control

This opt-in probe compiles the actual candidate `0032` poll and EventNotifier
functions against Emscripten **3.1.50**. It runs under Node with real pipes,
pthreads, SDK proxy calls and futex waits. It does not build QEMU or run a guest.
The patch is registered in the 75-patch source lock as a candidate experiment;
browser admission still requires the affected real guest gate.

Activate the pinned SDK (including its local `EM_CONFIG` and an appropriate
`EM_CACHE`), then run with a new ignored output directory:

```sh
python3 tests/browser-qemu/poll_wake/build.py \
  --emcc /path/to/emsdk/upstream/emscripten/emcc \
  --node node --out-dir .work/poll-wake-control
```

The driver preserves source, patch, fixture, actual function and artifact hashes,
commands, logs and a JSON receipt. It refuses an existing output directory.
Each topology (`PROXY_TO_PTHREAD=1/0`) runs the original poll body, the new
binary's legacy-wait control (`M5SW_POLL_WAKE=0`), and the wakeable branch.
The legacy-wait control retains the new binary's epoch read/once check, and
all modes share the actual notifier's unconditional atomic increment/wake;
these controls are not byte-identical to the old binary. Each lane performs 24 notifier writes
and 24 writes without a notifier, retaining real readiness/revents/data checks,
finite/infinite waits and two independent waiters. The C program prints the
latency result before later checks, so failure does not discard completed data.

Cancellation runs separately with bounded phase logs and an external timeout.
A real pipe input may permit cooperative recovery, but that fallback never
counts as cancellation PASS. A cancellation failure produces overall `PARTIAL`
and driver exit 2 even when positive readiness checks pass. The SDK cancellation
limitation must remain visible; QEMU QMP quit and browser Worker cleanup need
their own real guest gate. The probe does not alter the SDK to force a PASS.

The ordinary compiler contract needs no SDK/cache/network:

```sh
python3 -m unittest discover -s platform/tests -p 'test_wasm_poll_*patch.py'
```

It replays U3 hunks against curated unmodified runtime74 functions, compiles
the actual old/new poll and notifier bodies, and checks 32 deterministic
controls. Independent negative mutations detect a late epoch snapshot, a wake
before the real write/error result, and treating a wake as descriptor readiness.
Host fixtures model time and I/O; they do not establish actual SDK or guest
timing. Native poll branches remain byte-identical.

`--positive-only` rechecks readiness/latency without repeating cancellation;
`--cancel-only` runs the separate bounded cancellation observer. Each omitted
lane remains `NOT RUN` and overall status remains `PARTIAL` (exit 2). Earlier
failures must be retained under their original source/artifact identities.

The poll path freezes `M5SW_POLL_WAKE` through `pthread_once`; only `0` selects
the legacy wait. The low-level notifier performs no option lookup or once wait.
A real notifier write/EAGAIN updates a shared 32-bit epoch and
wakes all host waiters. Poll snapshots the epoch before checking descriptors,
then requests compare-wait slices of at most 5 ms (1 ms on the main runtime thread), servicing
queued calls and cancellation. Every wake rechecks actual `g_poll`. Unrelated
wakes, spurious wakes and epoch wrap cannot manufacture readiness; the finite
fallback still covers JS-only descriptors. Guest clocks, watchdogs, block I/O,
MMIO and Flash contents are unchanged by the patch.
These are requested host wait slices, not a hard wall-clock response bound;
SDK/browser/OS scheduling can delay return beyond a requested slice.
