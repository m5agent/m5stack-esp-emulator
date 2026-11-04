# Cardputer-ADV public keyboard IRQ acceptance

This independent opt-in lane tests all 56 physical keyboard components through
the public workbench's default Cardputer-ADV image. Each subject key receives
focused browser keyboard input and, separately, a real mouse down/up on its
raycast-verified model geometry. It does not extend the result of the older
eleven-key fixed fixture, which manually invokes a private ISR. G0/Boot uses the
separate original BtnA button case; reset and power sliders are separate controls.

Run only when the shared browser guest slot is available. An exported site,
its exact source/runtime manifest, the default UIFlow registry image, Chromium,
and Playwright are required. No build or guest is started by a syntax check.

```sh
M5_CARDPUTER_KEYBOARD_IRQ=1 \
M5_PUBLIC_SITE="$PWD/.work/public-site" \
M5_PUBLIC_QEMU_OUT="$PWD/.work/cardputer-keyboard-irq-first" \
M5_WASM_NODE_MODULES="/path/to/node_modules" \
M5_WASM_CHROME="/path/to/chrome" \
node platform/tests/test_public_uiflow_cardputer_keyboard_guest.mjs
```

`M5_PUBLIC_BASE_PATH` must match the export (default `/showcase/`). The output
directory must be new and under ignored `.work/`. Startup has a bounded 300 s
default timeout, each missing IRQ observation fails after 30 s, and the complete
run has a 15 minute bound. The formal pulse is fixed at 250 ms and releases
before waiting for a guest acknowledgement. The report retains requested and
observed wall-clock duration, browser trust, actual component/control edges,
controller input acknowledgements and guest observations. A slow or missing IRQ
fails; no hold-until-ack, private-ISR or manual-FIFO fallback is available.

The observer is entered through the actual editor Run button and public UART
MicroPython runner. It uses only `MatrixKeyboard()`, `set_callback()`,
`get_key()` inside the callback, `is_key_pressed()`, `is_pressed()` at readiness,
and `deinit()` on interruption. It neither calls `tick()` nor installs its own
GPIO handler. The original public constructor selects KeyboardI2C on ADV,
configures TCA8418 at address 0x34 over SDA8/SCL9, installs GPIO11 IRQs, and
schedules the original key-event handler. Public `is_key_pressed()` reads the
state that this IRQ path updates; it does not read the FIFO. Press callbacks
alone do not pass: both public press and release states are required.

The independent expected code table binds the inspected official source at
[`50e440780492aa847378c7d3477ab912f7063bac`](https://github.com/m5stack/uiflow-micropython/tree/50e440780492aa847378c7d3477ab912f7063bac/m5stack/libs/hardware).
Its four source hashes are recorded in `public_qemu_cardputer_keyboard_cases.mjs`.
The public interface is documented in the official UIFlow Cardputer Adv
controller documentation. The inspected source is an oracle, not proof that
an official binary has executed: every firmware must independently pass the
real guest lane. Tab is 43 and Enter is 10 in this original ASCII driver.

Fn has no standard PC `KeyboardEvent.code` counterpart in the canonical table.
The mounted public model exposes `keymap.Fn`; this runner uses Chromium's native
CDP `Input.dispatchKeyEvent` with code/key `Fn` for that existing alias, retaining
the actual trusted DOM event and normal viewer routing. It does not dispatch a
synthetic DOM event or directly call a model component. This does not establish
that a physical PC keyboard emits Fn events.

The original `KeyEvent.convert()` returns default code 0 for standalone Fn
because its Fn exemption checks position `(0,2)`, while Fn is `(2,0)`. The Fn
case therefore requires the documented Fn+grave -> ESC (27) chord, its public
pressed/released states, and the separately observed code-0 Fn release. Code 0
alone cannot pass. With keyboard input, both keys use native keyboard events.
With pointer input, Fn itself receives the verified real mouse down/up and
grave is a separately recorded keyboard companion; one mouse cannot hold two
physical keys. The 250 ms timer begins after both downs, so Fn's actual subject
hold includes the companion command overhead. That duration is retained.

Each result binds the Cardputer row of `uiflow-workbench-profiles.json`, exact
derived Flash SHA, original base SHA, startup sources, runtime asset hashes,
executed observer source, model/keymap sources and one nonce/session/console.
It does not borrow another board's runtime/firmware result. Success also requires
public interruption, driver deinit, raw-REPL return, normal QMP quit and actual
CDP Worker disappearance before browser-context closure. Earlier FAIL remains
visible if a later run passes. Host contracts and skipped opt-in runs are
**NOT RUN** for guest acceptance, speed and physical-hardware behavior.

An interrupt of a running editor program sends one Ctrl-C. Requests repeated
within that same execution share the original UART operation and cannot inject
another exception into its `finally` or public driver `deinit()`. Session,
console epoch, UART ownership, transfer and pause checks still apply to repeat
requests. The separate initial REPL connection handshake retains CR/Ctrl-C/
Ctrl-C; it is not the running-program interrupt. The observer's `finally`,
public `deinit()` call and required deinit marker remain mandatory.

The complete admitted-board gate includes this independent lane. Each runtime
and exact default image must establish its own public IRQ, cleanup and input
results; a preparation receipt cannot replace that execution.
