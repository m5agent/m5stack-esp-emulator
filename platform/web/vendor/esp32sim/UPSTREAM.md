# Browser execution glue

These four ES modules are copied without modification from
[`zhuzhe1983/esp-online-tester`](https://github.com/zhuzhe1983/esp-online-tester/tree/3cd3db3b7202e9fc559328c7247c11134c0437f9),
an MIT fork of [`mikroverk/esp32sim`](https://github.com/mikroverk/esp32sim).
`source.json` pins the exact commit, source paths, byte counts and SHA-256 of
every copied file. `LICENSE` preserves the upstream copyright and permission.
This is a different emulator from the older `platform/runtime/wasm/esp_emu.js`.

The glue runs the Rust emulator in a module Worker. `public-browser-runtime.js`
admits only the PaperS3 and StopWatch board profiles. It supplies firmware bytes,
loads the S3 ROM, and receives serial and RGB565 output from the emulated board
controllers. StopWatch uses the interpreter because the upstream V0.5 IMU path
has a known JIT non-response. These profiles are partial; native QEMU board,
UIFlow2, Unit, networking and hardware results do not transfer to this backend.

Build from the fixed source commit with the fixed compiler:

```sh
rustup toolchain install 1.99.1 --profile minimal --target wasm32-unknown-unknown
python3 platform/tools/bootstrap_browser_runtime.py --fetch-rom
python3 platform/tools/build_public_site.py \
  --base-path /m5stack-esp-emulator/ \
  --browser-runtime .work/browser-runtime
```

The bootstrap uses an exact Git archive in a clean temporary directory,
`Cargo.lock`, offline Cargo resolution, and the upstream production flags. It
writes the WASM, reviewed Espressif ROM and provenance into ignored `.work/`.
No firmware is fetched. The site export verifies each runtime file against its
manifest before copying it into the deployment artifact. ROM and WASM binaries
must not be added to source Git. `--rom` can supply an existing matching S3 ROM
ELF instead of downloading the pinned Espressif release archive.

`--diagnostic-wasm` is a separate, explicitly labelled path for the reviewed
deployed binary. It does not claim a source build; exporting it additionally
requires `--allow-diagnostic-runtime`. Ordinary checkout tests use offline
fixtures and do not require `.work` runtime caches.

The adapter does not save mutable Flash or SD contents. Reset creates a fresh
guest from the original input bytes. Application readiness requires observed
serial/frame/input results; the Worker `started` response only proves that CPU
execution was started. Neither category proves physical hardware behavior.
