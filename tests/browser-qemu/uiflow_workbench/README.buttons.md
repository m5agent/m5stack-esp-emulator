# Browser UIFlow button observer

`button_observer.py` executes in the same browser virtual device through the
public MicroPython UART runner. It calls `M5.begin()`, `M5.update()` and the
original public `Button` methods. A per-run nonce, board identity, guest time,
button states and event methods are emitted as `M5_BUTTON_OBSERVER` JSON.
It does not call private ISRs or substitute host input echoes for guest state.

StopWatch's original PM1 firmware defaults to single-click reset with a 250 ms
recognition limit. The observer explicitly configures a **user-application
button-IRQ mode**. The exact StopWatch and StickS3 images use the tested
`driver.m5pm1.M5PM1` API: `disable_single_click_reset()` and
`set_button_timing(BUTTON_TIMING_CLICK,500)`. The PaperColor image does not
provide that Python module. PaperColor and PaperMono explicitly select public
`machine.I2C.readfrom_mem/writeto_mem` register configuration instead; there
is no exception-driven fallback or inserted replacement module. The ready
receipt records the selected `configuration_api` and actual API path.

Both paths set register0x49 bit0 and bits2:1 to the documented 500ms click
encoding, using `(before & 0xf8) | 0x05`. No IRQ/status register is read by
setup; only the original `M5.update/BtnPWR` consumes button events.
All four use I2C1/address0x6e; StopWatch, StickS3 and
PaperMono use SCL48/SDA47, while PaperColor uses **SCL2/SDA3**. These mappings
come from the pinned original board tables. The setup preserves unrelated
configuration bits, verifies actual register0x49 readback, and emits that setup
in the ready receipt. The actual input pulse stays 250 ms. This is not default
Flash, C-runtime or clock modification. It does not grant unconfigured-mode
BtnPWR acceptance: the retained first unconfigured runtime75 run failed to
observe PWR, and independent public-Power/default and configured original
BtnPWR diagnostics established the configuration distinction. Each other PM1
board still requires its own exact-image guest run; it cannot inherit the
StopWatch result. Boards outside the explicit PM1 registry remain unchanged.

The opt-in runner requires an exported site with the UIFlow workbench default
and UART-capable QEMU runtime. Run one device at a time, without concurrent
builds or guests:

```sh
M5_PUBLIC_SITE="$PWD/.work/public-site" \
M5_QEMU_DEVICE=stickc-plus \
M5_PUBLIC_QEMU_OUT="$PWD/.work/buttons-stickc-plus" \
M5_WASM_CHROME="/path/to/chrome" \
node platform/tests/test_public_qemu_buttons_guest.mjs
```

`M5_PUBLIC_BASE_PATH` must match the export's base path (default `/showcase/`).
The output directory must be new and under the checkout's ignored `.work/`.
`M5_QEMU_BUTTON_HOLD_MS` defaults to 250 ms; the report records both the
requested pulse and actual keydown-to-keyup wall-clock interval. A missing
guest edge fails that run; a longer pulse is a separate diagnostic run and
must not erase the first failure.

Each physical component is tested separately through focused keyboard input
and a real mouse press/release. The pointer helper rotates the mounted model
to expose front/side/top controls, projects actual cap geometry or weighted
native-surface centres, and requires the normal viewer raycast to hit that
exact component. The page's topmost element must also be the canvas. It does
not invoke `button.press()` or synthetic pointer hooks. Both paths retain
actual model source events, pulse duration and original guest observations.

`platform/tests/public_qemu_button_cases.mjs` declares each board's physical
model component, original UIFlow object and expected behavior. GPIO buttons
and Core2's FT-controller-backed touch areas require guest press and release
states. PMIC power keys require an original guest event (`wasPressed`,
`wasClicked` or `wasHold`) followed by a released heartbeat; PMIC event IRQs
are not sustained GPIO levels. Plus2's power key is a GPIO35 button and uses
the edge test. Core2 A/B/C use the controller's raw bottom touch band.

Cardputer-ADV's keyboard has its separate FIFO/display runner. Its G0/Boot
model switch uses the F12 transport carrier and original BtnA GPIO0 path. The
profile requires the exact compiled input patch; old runtimes fail before startup.
Patch presence and these source contracts do not establish guest button PASS. StackChan
body-touch zones are separate Si12T inputs and are outside the PMIC observer.
Hardware reset and power sliders also require their own lifecycle tests.

Evidence includes source/probe/input-registry hashes, runtime and firmware
receipts, actual public-model keyboard and mouse inputs, guest observations, interrupt/REPL
completion, and actual CDP Worker disappearance before browser context closure.
Future failures retain the actual post-stop cleanup metadata and actual CDP
Worker closure separately from the pre-stop failure state. The first
unconfigured StopWatch failure had neither post-stop normal-QMP metadata nor
independent CDP closure captured; later diagnostics cannot fill that gap.
The provenance closure also binds `public-uiflow-firmware.js` and
`uiflow-workbench-profiles.json`, so a different default programming image cannot
borrow this run's result. The [full publication gate](README.md) invokes this
runner separately after each board's full editor case and retains its own
`uiflow-buttons/<device>` output. A gate plan or host contract is not button
guest evidence.
Syntax checks and a skipped opt-in runner are not virtual-device validation.
## ET047TC1 candidates

PaperDIY checks its independent A/B inputs through the original M5 Button
API. Each key is exercised through both focused keyboard and 3D pointer input. The
first 250 ms GPIO pulse follows two fresh idle polling intervals observed in
both guest and host time. The ready marker alone does not establish that the
continuous update loop has started.
PaperS3 projects a real pointer event to `(270,400)` on the modeled display
and checks the original GT911 logical coordinates and release through
`M5.Touch`. Its PMS150G power actuator remains outside this input contract.
