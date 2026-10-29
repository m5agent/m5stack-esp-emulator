# Browser QEMU source build

This is the C/QEMU engine used by the reviewed offline CoreS3 fixture. It does
not use the Rust research engine or the Node transport adapter. Python 3.12+,
Git, a native C/C++ compiler, make and standard Unix tools are required. Linux
Actions can install `build-essential git python3-venv xz-utils` and run:

```sh
python3 platform/tools/bootstrap_qemu_browser_runtime.py --check
python3 platform/tools/bootstrap_qemu_browser_runtime.py \
  --cache .work/qemu-browser-runtime-build --output .work/qemu-browser-runtime --jobs 2
```

Allow up to 90 minutes in CI for SDK/dependency/source downloads, full object
compilation and source compression. All build tools stay in the owned cache;
no global packages or services are changed. A reviewed archive cache and an
existing isolated SDK can be reused with `--downloads` / `--sdk-dir`; inputs
are checked and the QEMU/dependency build directories remain separate.
`--prepare-only` prepares source without installing tools or executing code.
Existing unowned directories, changed locks or populated exports are rejected.
Keep old outputs and use a new cache/output when the recipe or pins change.
For local iteration, `--reuse-dependencies <owned-cache>` explicitly reuses only
completed, hash-verified library outputs from this exact source lock. QEMU still
gets a new source/build directory and every QEMU object is compiled there. CI
does not need this option and builds the dependency sources itself.

`sources.lock.json` freezes the Espressif QEMU commit, **36 explicit native
layers**, 15 QEMU WASM patches, dependency patches/archives, subprojects,
Emscripten 3.1.50 and host tool versions. It never imports the mutable native
bootstrap patch list. Patches 0065/0066 are context-ported through 0011;
0008 instrumentation is included in the reviewed source sequence; 0007's
historical 2 MiB stack expansion is excluded. Link flags explicitly select
64 KiB main/pthread stacks and stack checking. Meson's command-line options
preserve the complete Emscripten link list and take precedence over QEMU's
later cross file. Before compiling, the builder checks the actual Ninja link
command for missing or conflicting stack settings and records its argument
hash in the build receipt and runtime manifest. The 153 affected source-file
hashes bind this recipe to the final reviewed source.

Native layers `0085` through `0089` register separate AtomS3, AtomS3 Lite,
StickC, StickC Plus, StickC Plus SE, StickC Plus2, Dial, Atom Lite, Atom Matrix
and Atom Matrix v1.1 machines. AtomS3 uses
the documented GC9107 wiring and MPU6886; Lite has no display and observes
its GPIO35 WS2812 through RMT, with the GPIO41 button reaching the guest
through the GPIO controller. Classic Atom GPIO27 WS2812 output uses the original ESP32 RMT controller and
GPIO-matrix route; Dial uses GPIO41/40 quadrature edges, GC9A01 and FT3267.
The ESP32 flash QIOR phase bridge selects the attached flash model's mode/dummy
count while keeping the PSRAM route separate. The Stick variants retain their own panel,
power-controller, memory and IMU topology. These source registrations and
`compiled_profiles` do not grant browser admission or device functional PASS.
The builder validates the native/WASM patch boundary from the lock rather
than assuming a fixed number of native patches. Keyboard patch `0016` keeps
the same C changes with updated context so it composes with the optional
StickC Plus2 GPIO power button. The historical incremental reference predates
these machines and cannot be repackaged as this source lock; rebuild QEMU.

Every object is built from that prepared source. A fresh Linux/macOS build
records its own WASM hash: it is not claimed byte-identical to the historical
incremental `42f90385…` artifact. Perform the real browser acceptance again for
the exact built output. Building/packaging never executes a guest or claims a
functional/hardware PASS. The unsupported resolver shim reports HOST_NOT_FOUND;
it is not guest networking support.

The output contains an ES module, WASM, pthread worker, `runtime.json`, `NOTICE`
and `corresponding-source.tar.xz`. Preserve **all** of them when exporting or
redistributing. The source archive includes the actual modified QEMU host
source, exact dependency archives and patches, Emscripten linked support/library
sources/licenses, and this build recipe. Binary ROM/firmware/test images are
excluded. QEMU is GPL-2.0 and individual files/libraries keep their licenses;
the repository's MIT license does not relicense QEMU or linked dependencies.
When using the recipe from an extracted corresponding-source archive, first run
`cp LICENSE.project LICENSE` in that archive's root: the source package preserves
the project's license under `LICENSE.project`, and the export step reads
`LICENSE`. The archive has been hash-audited; a complete offline QEMU rebuild
from that archive has not been validated.
The earlier local `fresh-v4` archive retained QEMU's unrelated
`tests/qemu-iotests/sample_images/grub_mbr.raw.bz2` boot-sector fixture. That
frozen archive remains part of its original local acceptance evidence. The
current packager excludes the entire sample-images directory and opaque image
suffixes through compression wrappers; the final public package will be built
and guest-tested again in CI. This packaging change leaves compilation and link
settings unchanged.

No ROM, UIFlow2 base, derived Flash, credentials, local logs or machine-specific
command logs are exported. `required_rom` points to the fixed official
Espressif QEMU raw URL and exact required SHA/size. Its independent redistribution
license is not confirmed, so obtain it directly in the browser or from a user
file; do not add it to Pages/CI artifacts. UIFlow2 public source licenses do not
establish redistribution permission for the exact prebuilt base; the browser
composer edits the user's/upstream's base locally instead.

For static export, import `runtime_files` from
`platform/tools/bootstrap_qemu_browser_runtime.py`; it validates the complete
asset allowlist, sizes, hashes and source/distribution lock before returning
bytes. Incremental reference packaging requires explicit opt-in and cannot be
labelled a fresh full-object build. Public-site and Pages workflows must not
fetch or bundle firmware/ROM. Source Git contains no runtime binaries.
The manifest binds the recipe and lock inside its corresponding-source archive;
later validator improvements do not invalidate an unchanged frozen build.

The source lock also describes the `shared-rgb565-v1` display ABI and the
compiled Xtensa machines. `compiled_profiles` means the binary contains a
machine, not that the public site admits or validates it. Public admission
comes from the canonical per-board registry, selected against this compiled
set, and the Pages job must run the real fixed guest for each public board.
The legacy `profiles` field retains the original CoreS3 build baseline.
An explicit candidate export is ineligible for publication.

Host patches `0014`/`0015` retain the original emulated display/controller and
guest timing paths. The shared frame transport removes QMP/PPM work from
ordinary capture. The poll patch supplies host-thread waiting missing from the
pinned SDK's `poll` implementation. Build PASS alone proves neither frame
rate nor reduced CPU: use the browser benchmark and same-guest input/frame/
cleanup receipts, and keep compiler/background-load and GPU renderer details
with resource measurements.

Patch `0017` coalesces expired positive-period SYSTIMER host callbacks in WASM
while retaining the next alarm's phase. The elapsed counter, pending interrupt
level and guest tick accounting remain unchanged. Its `__EMSCRIPTEN__` guard
preserves native behavior, and zero periods keep the original semantics. The
actual-function C controls establish the redundant-callback defect; they do not
establish that a particular guest watchdog failure is resolved.

Patch `0018` follows the TI TCA8418 SCPS215G interrupt contract (sections
8.6.2.1/2/4, pages 28–30) for the original keyboard driver's `INT_CFG=0` path.
The last FIFO read leaves the key interrupt latched until W1C, and an event
arriving between drain and acknowledgement keeps `K_INT` asserted. The
bounded actual-C pre/post controls require the old premature GPIO rise and
stranded-release result as negative controls, then check FIFO order and
unrelated status bits. The legacy `INT_CFG=1` path is unchanged; its required
50-microsecond pulse and interrupt-enable/other-source behavior are not granted
coverage. See the [patch provenance and boundaries](../../patches/qemu-wasm-probe/README.md#tca8418-key-interrupt-acknowledgement-0018).
These checkout-only controls do not execute a guest. A new build must repeat
the exact firmware's browser acceptance, including every keyboard release;
results from the preceding runtime do not transfer to the new binary hash.
