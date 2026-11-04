# Browser UIFlow programming startup

These files start the actual board-specific official UIFlow2 firmware in a
programming state. `M5.begin()` initializes its original board implementation;
the application then returns to the real MicroPython REPL. There is no fixed
display or button test application and no host-side Python execution.

This is **official UIFlow2 runtime plus a programming startup script**, not an
unmodified factory menu. All firmware bytes outside the existing LittleFS VFS
are preserved. Native-UART builds keep their original console; USB-console
builds use the same UART0/dupterm setup as the existing browser fixtures.

`compose.mjs` builds the exact images with the source-built browser LittleFS
WASM. It writes only packaging identities and source text to
`platform/web/uiflow-workbench-profiles.json`. Firmware stays in ignored storage.
Run from the repository root:

```sh
node tests/browser-qemu/uiflow_workbench/compose.mjs \
  --runtime <browser-littlefs-directory> \
  --firmware-cache <ignored-official-base-directory> \
  --out-dir .work/uiflow-workbench-images --write-registry
```

The cache stores official downloads as `<sha256>.bin`. `--download` explicitly
permits fetching missing hash-pinned official CDN bases. `--devices` accepts a
comma-separated subset for diagnosis; a partial run does not write the full
registry. `--check` checks registry/source/profile consistency without a local
firmware cache. Composition is **not guest execution**. Every board still needs
its own browser startup, source execution, inputs/outputs and Worker cleanup
validation before a functional claim.

The actual public editor and UART path have a separate opt-in guest test:

```sh
M5_PUBLIC_SITE="$PWD/.work/public-site" \
M5_WASM_CHROME="/Applications/Google Chrome.app/Contents/MacOS/Google Chrome" \
M5_QEMU_DEVICE=cores3 \
node platform/tests/test_public_uiflow_guest.mjs
```

It uses a random-port static server and the exported Service Worker, requires
hardware ANGLE rendering, and rejects Device Service requests. The cases use
the actual editor for UTF-8, multiline and larger raw-paste transfers, syntax
and runtime exceptions, file import, infinite-loop interruption and subsequent
execution in the same VM. Color display boards retain the real guest red-frame
check. PaperMono uses the original `M5.Display` API at rotation 0, verifies its
480x800 EPD identity, and draws a black left half and white right half inside
`startWrite()` / `endWrite()` so the real driver flushes. Every observed RGB565
pixel must match that pattern; reports retain actual color counts, dimensions,
frame sequence and SHA. Host syntax/planning checks do not establish that the
new PaperMono guest path passes.
The full run also pauses/resumes an active program and performs a hardware
reset: the old UART console owner must be cancelled before code can execute in
the newly booted console epoch. This reset keeps the browser session identity;
it does not claim Python state survives a hardware reset.
`M5_UIFLOW_SMOKE_ONLY=1` limits the run to startup and two source executions;
the report preserves that narrower scope. Both modes require normal guest exit
and independent CDP Worker disappearance before closing the browser context.

Button behavior is tested separately by
`platform/tests/test_public_qemu_buttons_guest.mjs`, using the original UIFlow
Button API and actual public-model inputs. The programming tests do not grant
all-device button or firmware-compatibility acceptance.

The publication gate runs the exported public registry in full by default:

```sh
M5_PUBLIC_SITE="$PWD/.work/public-site" \
M5_WASM_CHROME="/path/to/chrome" M5_WASM_GPU=hardware \
M5_QEMU_GATE_REQUIRE_ALL=1 \
node platform/tests/test_public_qemu_admitted_boards.mjs
```

For each public board it runs the full editor first and the keyboard/pointer
button observer next. Atom Matrix, StickC Plus, Cardputer-ADV G0 and CoreS3
come first; the other boards follow the exported registry. It then runs the
independent fixed examples. The current registry plans 19 editor + 19 button
+ 20 fixed cases; these are planned cases, not guest PASS results. A new public
board without its own workbench identity, compiled runtime or button case fails
preflight. Candidate boards cannot inherit admission.

Outputs live in separate `uiflow-editor/<device>`, `uiflow-buttons/<device>` and
`fixed/<device>[-example]` directories below a new ignored output root. The
bounded gate report records each child status and report/source SHA, and stops
at the first failure. It clears inherited smoke-only, remote URL, upload,
clock-override and frame-diagnostic options, pins button pulses to 250 ms, and
uses the same explicit Chrome executable for every runner. It
requires the exact default workbench Flash, WASM and export identity for the
two UIFlow lanes. Raw child reports and screenshots remain separate.

For diagnosis, `M5_QEMU_GATE_PHASE` accepts only `all` (default), `uiflow`,
`editor`, `buttons` or `fixed`; `M5_QEMU_GATE_DEVICES` accepts an explicit
comma-separated public-device subset. Such a reduced run reports
`DIAGNOSTIC_PASS` with `publication_eligible=false`, never full publication PASS.
The workflow sets `M5_QEMU_GATE_REQUIRE_ALL=1`, which rejects reduced selections
before starting a guest. Its 240-minute ceiling includes source build/setup and
the sequential matrix, including at least 77 boots for the current full plan;
it is not a measured startup guarantee. Actual guest execution is still required.

Source transfer preserves ordinary tabs/newlines/CR/form-feed and backslash
escapes, but rejects literal serial control characters before taking ownership
of UART. Use Python string escapes when such a value is needed. Raw REPL uses
EOT bytes to terminate stdout/stderr; arbitrary binary stdout containing EOT
is not a transparent binary transport and can terminate a stream early. The
editor is a text console, not a binary-file transfer interface.
