# Research browser QEMU transport

This experimental launcher lets a dedicated Device Service own a process and
its session while the existing C/QEMU WASM build executes in a headless Chromium
browser. The emulated CPU, controllers, board wiring, display and Unit models
run in the browser. Node handles local files, UNIX sockets and browser lifecycle;
it does not provide register values, guest responses or substitute device frames.

This tool is outside the native runtime bootstrap and public browser backend.
It is not a GitHub Pages production backend. Build and no-firmware transport
checks do not establish firmware, LVGL, input, Unit or hardware compatibility.
See [the port research](../../docs/qemu-wasm-port-research.md) for the build
sources and evidence boundaries.

## Requirements and entry point

- Node.js 20 or later, Playwright and its Chromium browser. Neither Node,
  Playwright nor a browser is bundled here.
- A separately built, reviewed QEMU WASM runtime containing
  `qemu-system-xtensa.js`, `qemu-system-xtensa.wasm` and
  `qemu-system-xtensa.worker.js`. The current experiment uses pthreads,
  Asyncify, `EXIT_RUNTIME=1`, and exported `FS` and `ENV` runtime methods.
- A UNIX platform for the Device Service socket transport.

Run `scripts/qemu-wasm-browser/qemu-browser`. The shell entry uses
`M5_WASM_NODE` when set, otherwise `node` from `PATH`.

| Environment variable      | Meaning                                                                                                                                                           |
| ------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `M5_WASM_RUNTIME_DIR`     | Required directory containing the three reviewed runtime files. There is no implicit build selection.                                                             |
| `M5_WASM_NODE_MODULES`    | Optional explicit `node_modules` directory containing Playwright. Omit it to use normal Node package resolution from the launcher.                                |
| `M5_WASM_CHROME`          | Optional Chromium executable. Omit it to use Playwright's installed default Chromium.                                                                             |
| `M5_WASM_SOURCE_RECEIPT`  | Optional reviewed source/build receipt JSON; its SHA256 and contents are attached to the runtime receipt. Keep local/private details in ignored evidence storage. |
| `M5_WASM_SESSION_ROOT`    | Optional explicit ownership root, principally for a no-drive test. Otherwise the first drive's parent directory owns session outputs.                             |
| `M5_WASM_MAX_LIFETIME_MS` | Owned launcher lifetime limit, default `600000` milliseconds.                                                                                                     |
| `M5_WASM_CLOCK_PROFILE`   | Optional explicit clock profile, default `wallclock`. See the research profiles and their limits below.                                                           |

For example, install the optional dependency into ignored local storage and
select its browser without changing the repository's native runtime:

```sh
npm install --prefix .work/qemu-wasm-node playwright
.work/qemu-wasm-node/node_modules/.bin/playwright install chromium
export M5_WASM_NODE_MODULES="$PWD/.work/qemu-wasm-node/node_modules"
export M5_WASM_RUNTIME_DIR="$PWD/.work/qemu-browser-stage2/build"
```

For a dedicated research Device Service, set `M5_QEMU_XTENSA` to the absolute
path of this launcher and provide the environment above. Use a separate port,
state directory and control token. Ports `8787` and `8830` are reserved; the
launcher's own HTTP listener also rejects those ports. Keep the service's normal
session, lease, evidence and stop workflow. A service session still uses its
generic QMP lane; the `BROWSER_QEMU_RECEIPT` identifies the actual browser engine.
This selection does not change the native executable or bootstrap.

## Clock profiles

Clock selection is explicit and recorded in the adapter report and runtime
receipt. The launcher accepts these values for `M5_WASM_CLOCK_PROFILE`:

| Profile | Behavior and evidence boundary |
| --- | --- |
| `wallclock` | Default. Adds no `-icount` option and no VM clock divisor. The reviewed runtime retains divisor 1 behavior. |
| `vm-div8` | Offline slow-VM research profile. Passes `M5_WASM_VM_CLOCK_DIVISOR=8` to the separately reviewed Emscripten runtime with the clock patch. It cannot be combined with `-icount`. |
| `icount-single` | The icount-auto negative control: adds `-accel tcg,thread=single -icount shift=auto,align=off,sleep=off`. The recorded CoreS3 fixture did not reach its ready marker. |
| `icount-fixed-8` | The icount-fixed8 negative control: adds the same single-thread accelerator with `-icount shift=8,align=off,sleep=off`. The recorded fixture reached the UI but reported a guest runtime error. |

The two icount profiles are failed firmware controls, not validated alternatives.
A no-firmware QMP check for either profile does not override those failures.
Select `vm-div8` only with the matching reviewed runtime; the environment name
alone does not prove that another build implements the divisor. Check the actual
runtime hash and its `M5_WASM_SLOW_CLOCK divisor=8` startup log.

With `vm-div8`, QEMU virtual time advances at one eighth of host elapsed time
while the VM runs and still stops when the VM is paused. A watchdog driven by
that virtual clock also takes about eight times as much host wall time for the
same guest timeout. Host monotonic/realtime clocks and service lease deadlines
are not scaled. This profile changes guest timing; it does not establish the
device's original frequency, real-time behavior or performance. Native runtime
clocks and the browser's default divisor 1 behavior remain unchanged. Results
from the slow profile must name it and cannot establish a default-clock PASS.

## Transport contract

- The service's UNIX QMP endpoint is mapped to the original QEMU stdio monitor.
  Requests go to the browser's stdin queue. QMP responses and events originate
  from that same QEMU instance.
- External request IDs are replaced internally and restored on replies, so a
  late response for a disconnected client is not delivered to a new client.
  A new connection is accepted even if the previous socket's close callback is
  still pending; overlaps are recorded as `qmp_client_overlap`.
- A QMP or UART socket error closes only that client and is recorded as
  `client_socket_error`. A reply for an already closed QMP client is discarded
  with `qmp_response_discarded`; it cannot become a new client's reply.
- A reconnect receives the original greeting. Because the underlying stdio
  monitor remains negotiated, an empty `qmp_capabilities` request is adapted to
  a real `query-status`. Only a successful status response permits a generated
  empty capability ACK. This adaptation is recorded as
  `reconnect_capabilities_reused`; it is not a second negotiation. Optional
  capabilities cannot be renegotiated through this path.
- ROM files, declared drives and `M5_UNIT_CONFIG` are preloaded into MEMFS.
  Approved `M5SW_*` environment values are passed to the actual QEMU runtime.
- Serial file outputs use browser FS devices and append the emitted bytes to
  the session's host log. The `program-console` UNIX socket is mapped to a QEMU
  pipe chardev for bidirectional bytes. This mapping alone does not validate a
  particular guest's UART REPL or source upload workflow.
- `screendump` runs in the original QMP path. After QEMU acknowledges success,
  the actual MEMFS PPM bytes are copied into the session's requested file and
  the temporary MEMFS file is removed. A screenshot of the browser host page
  is not a device framebuffer.
- SIGTERM/SIGINT request QMP quit when ready. Startup cancellation, fatal paths
  and bounded cleanup own the BrowserServer process, sockets and local HTTP
  listener. Reports distinguish natural runtime exit from browser termination.

The launcher writes a structured `BROWSER_QEMU_RECEIPT` line at start and exit
to stdout. It records the engine, browser version, actual arguments, original
argument hash, runtime hashes, optional source receipt and Worker/cleanup
observations. The session also retains `browser-wasm-adapter.json`. These are
local execution evidence, not source files to commit.

## Current limits

Drives are copied into one browser instance's MEMFS; there is no persistent
browser filesystem or automatic export of guest writes. Mutable Flash/eFuse/SD
contents in MEMFS are **not written back** to the host and are lost when that
instance exits. Host Flash snapshots and `retain_flash` therefore retain the
host input copy, not subsequent guest writes. Reopening from that copy is not a
Flash persistence test. Audio and other environment-selected file data planes are not
automatically preloaded or exported. Network, radio peer, GDB and arbitrary
native socket transports are outside this adapter's scope. Unknown native
command-line options fail rather than silently changing the requested path.

This is a trusted local research transport, not an untrusted-firmware sandbox.
Actual Pages deployment, interactive public-browser integration, performance,
firmware features and physical-device equivalence need their own evidence.

Only these small sources, the no-firmware self-test and this README belong in Git. Keep WASM, ROM,
firmware, SDKs, dependency directories, session reports, raw logs and screenshots
in ignored storage. The self-test exercises no-firmware QMP, pipe/HMP,
cancellation, repeated immediate reconnects, and unread/late replies to closed
local clients. The disconnect case requires a real socket error, a discarded
late QMP reply, healthy subsequent `query-status`, and natural runtime cleanup.
Independent startup-cancel and
fatal-cleanup checks remain in the ignored research directory. None grants
device-functional PASS.

With the environment above, run a narrow reconnect regression or all five
no-firmware cases. Use a new ignored output directory for each run; logs and
reports are never written alongside these sources.

The research runtime with patch `0012` binds its Emscripten stdio QMP monitor
to QEMU's default main context. It does not offer the optional `oob` capability;
normal in-band QMP commands continue through the original monitor. This host
monitor placement leaves the two guest CPU cores unchanged. Other platforms
and QMP chardevs retain their existing placement.

The no-firmware self-test defaults to `--expected-workers 4`: the reviewed
runtime prewarms a fixed pool of four browser Workers. Removing the independent
QMP monitor I/O thread does not reduce that prewarmed pool. Select another
explicit expected count only when the chosen runtime requires it. This count
is for `-machine none`; it does not identify guest CPU count, native thread
count or device-functional compatibility. Every case still requires the exact
expected number of Workers to close naturally, zero Workers before browser
close, and runtime exit code zero.

```sh
python3 scripts/qemu-wasm-browser/selftest.py \
  --case reconnect --reconnect-count 20 \
  --out-dir .work/qemu-wasm-browser-selftest/reconnect-01

python3 scripts/qemu-wasm-browser/selftest.py \
  --case all --reconnect-count 20 \
  --out-dir .work/qemu-wasm-browser-selftest/all-01
```

Syntax checks require no browser or firmware:

```sh
node --check scripts/qemu-wasm-browser/qemu-browser.mjs
node --check scripts/qemu-wasm-browser/browser.mjs
node --input-type=module --check < scripts/qemu-wasm-browser/page.js
sh -n scripts/qemu-wasm-browser/qemu-browser
```
