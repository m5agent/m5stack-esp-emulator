# esp32sim browser execution glue

The four ES modules and MIT license in this directory are exact copies from the
[M5Stack esp32sim fork](https://github.com/m5agent/esp32sim/tree/4e257b6be8ee0ed706c2e509d8f31ef7472a424b).
The `m5-device-service-20261127` tag integrates the browser API and the native
board models. The browser API descends from the CoreS3 and Cardputer-ADV milestone
`76e8b35710d1879e073f73c4a03bd11b216fb95f`. It adds Web protocol commands for
physical keyboard edges and PMIC power presses, queue acknowledgements, resume,
and ADV presentation rotation. The existing `esp32sim_in_text` WASM export
dispatches input through the board model. The Worker publishes panel RGB565,
console bytes and speaker PCM.

`legacy/` preserves the exact previously reviewed sources from
[esp-online-tester](https://github.com/zhuzhe1983/esp-online-tester/tree/3cd3db3b7202e9fc559328c7247c11134c0437f9)
for PaperS3 and StopWatch. The milestone fork lacks the PaperS3 board. Keeping
both legacy boards on their original pin also preserves StopWatch's interpreter
configuration for the V0.5 IMU example. Each `source.json` records the source
paths, byte counts and SHA-256 values of its modules and license.

```sh
rustup toolchain install 1.99.1 --profile minimal --target wasm32-unknown-unknown
python3 platform/tools/bootstrap_browser_runtime.py --fetch-rom
python3 platform/tools/bootstrap_browser_runtime.py --legacy --fetch-rom
python3 platform/tools/build_public_site.py --output .work/browser-site \
  --browser-runtime .work/browser-runtime \
  --legacy-browser-runtime .work/browser-runtime-legacy
```

The bootstrap uses a clean Git archive, `Cargo.lock`, offline Cargo resolution
and fixed production compiler flags. If Cargo's dependency cache is empty, run
`cargo +1.99.1 fetch --locked --target wasm32-unknown-unknown` in the matching
source checkout first. `--rom` accepts an existing ELF with the reviewed SHA-256.
The build writes the runtime, reviewed ROM and their receipts to ignored storage.
The optional `--diagnostic-wasm` path is limited to the old deployed WASM and
requires explicit diagnostic export. Firmware stays outside the export.

The browser Worker uses ordinary WebAssembly memory. Input receipts confirm
queueing. Serial and controller frames establish what the guest did. Reset
reopens the original Flash bytes and stops the previous Worker. Session Flash
contents do not persist across runs.
