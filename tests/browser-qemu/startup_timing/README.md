# Existing fixed-case startup timing observer

This generator makes the timing collector used for the runtime75 Atom Matrix
and StickC Plus observations reproducible from a checkout. It adds the same
call-through `performance.now()` hooks to the existing fixed-firmware runners.
It does not start a browser or guest, change the product, select a faster
execution profile, or create a new benchmark.

The source-pinned bases are
`platform/tests/test_public_qemu_headless_guest.mjs` (SHA256
`365b3ad482344880f0f9ace686ecedcfe0765a818ebf5925c1bb9fc8141fa4dd`)
and `platform/tests/test_public_qemu_board_guest.mjs` (SHA256
`2eff0c6093609ce21c4139a2ecbc6b8a2b91d148d48c9d022aebb6653a8778d4`).
Source drift is refused; review a changed runner and explicitly update the
transform rather than silently changing the comparison.

## Prepare without execution

Use Python 3.12+ from the repository root:

```sh
python3 tests/browser-qemu/startup_timing/prepare.py \
  --out .work/startup-timing-75-portable-v1
python3 tests/browser-qemu/startup_timing/test_prepare.py
node --check .work/startup-timing-75-portable-v1/runtime75-headless-startup.mjs
node --check .work/startup-timing-75-portable-v1/runtime75-board-startup.mjs
node --check .work/startup-timing-75-portable-v1/runtime75-fixed-preflight.mjs
```

The destination must be new and below this checkout's `.work`. Existing files,
directories, `.work` itself, path escapes and symlinked output components are
rejected. The generator does not modify the bases, site, earlier observers or
reports. It emits both runners, the existing identity wrapper, copies of the
bases, readable diffs, and `preparation.json`. Absolute repository/import paths
are computed at generation time and occur only in ignored output. The receipt
records generator/template/rule hashes, every emitted artifact hash, commands,
and ordered original assertion/check lines.

For a local audit against retained executed runtime75 observers, add:

```sh
python3 tests/browser-qemu/startup_timing/prepare.py \
  --out .work/startup-timing-75-reference-audit-v1 \
  --reference-dir .work/perf-audit-harness
```

This optional check requires the exact retained artifacts; ordinary source
contracts do not require `.work` evidence. The recorded historical observer
hashes are headless
`e4b4393462aa39aa1936299349f12d710bad12dfa17546bbb4e8cefe087f870f`,
board `cd1ad0ef104b5c09879c147bf33b112108b05055405e0eb189cf62600476342b`,
and identity wrapper
`d513d9c1f30aaa865c539bd241e3b0a9cbe6698eecb6893e9a5678c5ef02ea4e`.
The audit requires identical observer bodies, identical ordered control lines,
and identical complete scripts after normalizing only two helper import URLs
and the repository binding. These path relocations change whole-file hashes;
the receipt preserves both identities. The runtime75 observation label stays
unchanged and identifies this instrumentation version.
Repository normalization accepts only the two historical `resolve` expressions
or one complete JSON-string assignment; an extra statement on that line is
rejected rather than hidden by normalization.

Relative to the uninstrumented bases, the retained observer also records its
executed source hash, adds timing to success/failure reports, reads HTTP files
before sending success headers, and adds normal-stop/CDP fences to the
headless failure cleanup. These existing changes are visible in the generated
diffs. The timing hooks, runtime call arguments and original assertions remain
unchanged. There are 25/63 static lines containing `assert`/`check` in the two
complete scripts; the actual selected Matrix/Plus runs must still pass their
original **15/26 executed checks**. Static counts are not guest results.

## Execute one allocated guest

Prerequisites are a strict source-built public static export, its verified
WASM SHA256, the original fixed firmware composer/dependencies, Playwright
installed under `platform/tests/node_modules` (or `M5_WASM_NODE_MODULES`), and
an explicitly selected system Chrome executable. The historical hardware-GPU
lane uses ANGLE Metal; choose a compatible host and verify the reported actual
renderer. Retain the ordinary runner's prerequisites and exact firmware path.
Request an execution slot before running alongside other runtime work.
Set `M5_PUBLIC_BASE_PATH` to the export's `public-site-manifest.json` base path;
the historical local export used `/showcase/`.

```sh
M5_PUBLIC_SITE="$PWD/.work/<strict-export>" \
M5_PUBLIC_BASE_PATH=/showcase/ \
M5_PUBLIC_QEMU_OUT="$PWD/.work/<new-matrix-report>" \
M5_EXPECT_WASM_SHA256='<verified-64-character-WASM-SHA256>' \
M5_QEMU_DEVICE=atom-matrix M5_PUBLIC_UI=1 M5_WASM_GPU=hardware \
M5_WASM_CHROME='<absolute-system-Chrome-executable>' \
M5_QEMU_READY_TIMEOUT_MS=600000 \
M5_QEMU_UPLOAD= M5_QEMU_CLOCK_DIVISOR= M5_QEMU_FRAME_DIAGNOSTIC= \
M5_PROVENANCE_REPO= \
node .work/startup-timing-75-portable-v1/runtime75-fixed-preflight.mjs
```

Then run `M5_QEMU_DEVICE=stickc-plus` with another new report directory. The
identity wrapper preserves the existing strict public admission, original
firmware SHA, divisor 1, TCG icount shift 5, no one-instruction override,
original check counts and normal Worker/CDP cleanup requirements. It accepts
only these two fixed cases. It does not select UIFlow workbench firmware.
The new report directory must not exist; preserve failures and use another
name for a later run. Raw reports remain ignored and may contain local URLs,
serial output and browser-local identities; publish bounded redacted evidence.

`report.json` contains the original functional checks plus `timing`: actual
Start-click and runtime-entry timestamps, asset load/cache observations,
compilation/cache observations, state changes, serial delivery, first device
state/frame and input delivery. Subtract `click_ms` from `guest_ready_ms` for
the existing click-to-ready observation, and retain the raw fields and cache
classification. The ready timestamp is the browser receive hook seeing the
existing fixed-probe ready marker, not a physical boot measurement. Hooks call
through to the original implementations and retain their overhead. No profiler
or block-statistics operation is added.

This directory reproduces the existing single-run startup collector. It does
not implement the separate same-page warm lifecycle experiment, establish a
speedup by itself, add guest acceptance, or transfer either board's result to
another firmware, runtime, device or host. Preparation and syntax contracts
are `PREPARED_NOT_EXECUTED` / `NOT RUN` for guest validation.
