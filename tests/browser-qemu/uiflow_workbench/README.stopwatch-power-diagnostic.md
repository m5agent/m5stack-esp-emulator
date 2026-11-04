# StopWatch PM1 power-key diagnostic

This bounded guest source is a diagnostic, separate from the formal button
gate. It must use the exact default StopWatch Flash and runtime in a fresh
browser VM for each mode. Input remains a real focused keyboard or raycast
mouse down/up through the public model, with the original 250 ms host pulse.
No input extension, private ISR, host-generated event or C clock change is used.
The host must retain nonce-bound UART, actual model/controller inputs, exact
source/runtime/Flash hashes, and ordinary QMP/CDP cleanup. A diagnostic result
does not replace the retained first formal failure.

Prepend `RUN_NONCE`, `POWER_MODE` and `POWER_CONFIG` before submitting
`stopwatch_power_diagnostic.py` through the public editor/UART. Each program
finishes after 15 guest seconds. Select only one consumer per VM:

- `metadata`: only non-consuming configuration and public telemetry, with no
  input pulse and no key-event reader.
- `button`: original `M5.update()` and public `M5.BtnPWR` methods.
- `power`: public consuming `M5.Power.getKeyState()`; no `M5.update()`.
- `registers`: actual guest I2C reads of IRQ0x42 and status0x48; no public
  key consumer. Status0x48 clears its edge latch on read.

The initial real I2C configuration read uses the board's original PM1 path:
I2C1, SCL48, SDA47, address0x6e. Reading registers0x49/0x4a does not consume a
button event. The public machine.I2C route is also used by the existing native
StickS3 PM1 firmware case; it is not host QOM injection or replacement data.

`POWER_CONFIG="default"` makes no PM1 configuration writes. The runtime75 C
default for BTN_CFG1 is 0x2a: a recognized single click requests reset, and its
maximum single-click duration is 250 ms. The real state machine recognizes
`hold <= 250 ms`; an actual hold slightly above 250 ms and below the long
threshold generates no click. That is a hypothesis consistent with the first
failure, not a measurement of that run's private PM1 register or virtual hold.

`POWER_CONFIG="irq500ms"` is a separately labeled application mode. Through
real guest I2C it sets BTN_CFG1 bit0 to disable single-click reset and selects
the 500 ms recognition window in bits2:1, preserving all other bits and
verifying readback. It changes neither the 250 ms input pulse nor expected
public event. A passing configured-mode run cannot be relabeled default-mode
PASS. No formal gate expectations or native C defaults are changed here.

Runtime75 `co5300.c` routes QKeyCode P/3 to `m5sw_pwr_button()`, which invokes
the actual PM1 state machine. The pinned original M5Unified public BtnPWR path
consumes PM1 IRQ_STATUS3 flags0/2 through `Power.getKeyState()`; it must not
race another consuming observation. Host replay of the unmodified75 functions
separately demonstrates the 249/250/251 ms boundaries under configurations
0x2a, 0x2b and 0x2d. That replay establishes controller semantics only; actual
official firmware behavior still requires the independent guest diagnostic.
