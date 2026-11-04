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
execution in the same VM. Display boards also verify a real guest red frame.
`M5_UIFLOW_SMOKE_ONLY=1` limits the run to startup and two source executions;
the report preserves that narrower scope. Both modes require normal guest exit
and independent CDP Worker disappearance before closing the browser context.

Button behavior is tested separately by
`platform/tests/test_public_qemu_buttons_guest.mjs`, using the original UIFlow
Button API and actual public-model inputs. The programming tests do not grant
all-device button or firmware-compatibility acceptance.
