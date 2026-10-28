# Opt-in Fiber/SjLj compatibility reproducer

This is a standalone C program, with no QEMU, firmware, ROM, guest, Device
Service or peripheral model. It is deliberately excluded from platform CI and
ordinary test discovery. Run it explicitly when investigating the Emscripten
3.1.50 Asyncify Fiber/SjLj interaction.

The same `repro.c` is compiled as baseline and compatibility configurations.
Each configuration runs a direct C call and an unmodified libffi call, 1,000
times each. Every helper visits a real Emscripten Fiber and returns to the
leader before calling `longjmp`. Stack pointers are recorded before/after the
Fiber swap and around setjmp/longjmp. The core is the C reproducer used during
the local QEMU investigation, retaining its 608-byte helper frame and both call
paths.

The compatibility configuration saves a `const uintptr_t` C stack pointer
before `setjmp`, then invokes `stackRestore(saved_sp)` through `EM_JS` after
the nonzero return. It does not replace the jump value or its control flow.
Baseline and compatibility use identical source except for
`M5_RESTORE_AFTER_LONGJMP=0/1`.

## Requirements and commands

- Emscripten **3.1.50**; `build.py` rejects another version.
- Unmodified **libffi 3.4.7**, compiled for wasm32 pthreads with this SDK, and
  its installed headers. Do not use the abandoned JavaScript catch candidate.
- Python 3, Node.js 18+, Playwright and an installed Chromium browser.

Activate the pinned SDK with its normal `emsdk_env.sh`, then run:

```sh
python3 tests/browser-qemu/fiber_sjlj/build.py \
  --emcc emcc \
  --ffi-include "$LIBFFI_PREFIX/include" \
  --ffi-library "$LIBFFI_PREFIX/lib/libffi.a" \
  --out-dir "$PWD/.work/fiber-sjlj-explicit-exit"

node tests/browser-qemu/fiber_sjlj/run.mjs \
  --out-dir "$PWD/.work/fiber-sjlj-explicit-exit"
```

The build's `--out-dir` must be new, preserving earlier attempts. The runner
also refuses to replace an existing `report.json`. Keep generated assets,
commands, receipts, logs and reports in ignored local storage. The runner accepts
`--playwright-module <module-directory>` and `--browser-executable <path>`
when those dependencies are installed outside normal Node resolution. It
serves only the generated assets on its own ephemeral loopback port with
COOP/COEP headers, then closes the browser and server. It refuses the reserved
Device Service ports 8787 and 8830.

All variants pin `-O2 -pthread -DWASM_BIGINT -fexceptions`,
`-sWASM_BIGINT=1 -sASYNCIFY=1 -sASYNCIFY_IMPORTS=ffi_call_js`,
`-sPROXY_TO_PTHREAD=1 -sEXIT_RUNTIME=1 -sSTACK_OVERFLOW_CHECK=2`,
`-sASSERTIONS=2 -sINITIAL_MEMORY=32MB`. Main/default pthread stacks are both
2 MiB for `baseline-2m` and `compat-2m`, and both 64 KiB for `compat-64k`.
The build receipt preserves the actual commands, explicit variant profiles,
source/libffi hashes and the size/SHA256 of each generated HTML, JavaScript,
WASM and Worker file. The runner requires a passing receipt, the current
`repro.c` hash and the expected variant profiles. It verifies the assets before
launch and again when serving each browser request, and requires all four
files to be loaded for every variant. The report records the receipt, source,
libffi, build-script and harness hashes, profiles and served asset hashes;
results from a stale or changed build directory do not receive PASS.

## Assertions and limits

The baseline is an expected negative control: its two lanes must each emit
1,000 rows, report 2,000 restoration mismatches and 1,998 drifting entries in
total, and show a negative post-longjmp stack delta. Fiber swap entry/return
SPs must still match. The compatibility variants require zero restoration
mismatches, zero entry drift, unchanged Fiber swap SPs and exactly 2,000
callbacks and Fiber visits.

`M5_SETJMP_RESULT` preserves the C check result (1 for the reproduced baseline,
0 for compatibility). After recording that result, main calls normal libc
`exit(0)` explicitly, matching the QEMU research process-exit adaptation.
The harness independently requires exit code 0 and every Worker to close
naturally before page/context cleanup; a completion print alone is insufficient.
No `force_exit`, Worker termination or stack-check suppression is used.
Browser and static-server cleanup run in nested `finally` blocks. A browser
close failure still closes the server and leaves a failing report.

This reproduction and compatibility experiment are specific to the pinned
SDK/configuration. They do not establish arbitrary SDK, QEMU, firmware or
hardware support. QEMU's separate `cpu_exec_step_atomic` setjmp path is not
covered or modified by the associated main-loop compatibility patch.
