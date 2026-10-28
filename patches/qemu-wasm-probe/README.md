# Experimental QEMU WASM backport

Research only. These patches are **not** part of the native runtime bootstrap
or public browser runtime. Build and browser CLI/control evidence does not
establish firmware, display, input, Unit, networking or hardware compatibility.
See [the investigation](../../docs/qemu-wasm-port-research.md).

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
additionally uses `0004`. None of these configurations has run guest firmware.
