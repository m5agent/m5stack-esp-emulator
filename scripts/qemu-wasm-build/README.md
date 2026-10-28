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

`sources.lock.json` freezes the Espressif QEMU commit, **31 explicit native
layers**, nine QEMU WASM patches, dependency patches/archives, subprojects,
Emscripten 3.1.50 and host tool versions. It never imports the mutable native
bootstrap patch list. Patches 0065/0066 are context-ported through 0011;
0008 instrumentation is included in the reviewed source sequence; 0007's
historical 2 MiB stack expansion is excluded. Link flags explicitly select
64 KiB main/pthread stacks and stack checking. Meson's command-line options
preserve the complete Emscripten link list and take precedence over QEMU's
later cross file. Before compiling, the builder checks the actual Ninja link
command for missing or conflicting stack settings and records its argument
hash in the build receipt and runtime manifest. The 144 affected source-file
hashes bind this recipe to the final reviewed source.

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
