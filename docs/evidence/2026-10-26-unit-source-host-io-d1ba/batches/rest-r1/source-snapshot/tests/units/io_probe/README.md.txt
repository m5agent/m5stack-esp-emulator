# IO Unit guest probes

These probes target the CoreS3 reference UIFlow2 image. UART0 on TX43/RX44
captures all readiness, observations and exception traces. RS485 traffic uses
UART1 on the external connector; it never replaces the logging UART.

The `io_drivers/` files are unchanged official Unit drivers at commit
`3a86d8f611b3639cca755a933e01a5a829771ef1`. Their URLs, SHA256 values and MIT
notices are retained. They use the reference firmware's original `hardware`,
`driver` and native controller modules. The HUB case uses that firmware's
bundled ENV III, NCIR and TVOC drivers on one physical bus. Its only address
scan is the four real child-chip addresses; a passive HUB has no address.

```bash
python3 tests/units/run_io_cases.py --prepare-only --out-dir /tmp/m5-unit-io
python3 tests/units/run_io_cases.py --case angle --out-dir /tmp/m5-unit-io-angle
```

Use a Python 3.10+ environment with the repository's LittleFS and Pillow
dependencies. The first command makes no API requests. It packages with
LittleFS `prog_size=32`, then remounts each image and verifies every guest
Python file byte for byte. A prepared image does not establish a runtime PASS.

Execution always uses visible `/api/v1` Device Service sessions. The runner
checks the exact firmware hash, original guest markers, live QOM output and
controller counters appropriate to each interface. It validates the complete
evidence ZIP and nonblank 320×240 framebuffer before stopping with `purge=0`,
then reads retained metadata and the last frame again.

The tests cover GPIO edges/IRQ disable for PIR, independent dual-button click
machines, LIMIT/Button IRQ counting/reset, Key raw active-low input and LED
brightness, complete GRB chains and incomplete-frame rejection, white-line
SAR ADC selection, separate light digital input, actual LEDC frequency/duty,
Haptic one-shot completion, native NEC RMT transmit/receive with a bad-frame
control, UART FIFO binary traffic/capacity, and three independent HUB leaves.

`KeyUnit.get_key_state()` is checked against the official source's raw return
value (0 pressed, 1 released). It differs from the bundled API prose. Angle
raw/u16/uv readings are checked against the explicit synthetic eFuse fixture
and unchanged IDF integer curve-fitting oracle. Its voltage result deliberately
retains that IDF nonlinear correction rather than equating uv with the fixture's
input voltage. These checks do not establish hardware ADC accuracy.

The IR test keeps two paths separate. Unchanged `IRUnit.tx(cmd8, data8)` must
faithfully transmit the original native code's raw 16+16-bit fields, including
the absent complement bytes. A second explicit native `uint16.send` call sends
the mutually complementary NEC8 payload; that controller result does not grant
the wrapper NEC8 interoperability. RX requires a valid frame, malformed-leader
rejection, a real NEC repeat and a second valid frame after rearming. The probe
requires enabled GC and explicitly collects after receiver registration.

The default still packages the exact original drivers. Their published IR
callback has a GC-lifetime gap; the original failure and GC-disabled diagnostic
remain separate evidence. `--ir-callback-root-patch` explicitly applies
`patches/uiflow2-unit-ir/0001-root-native-receive-callback.patch` only to the
generated guest copy. It retains the same nested callback on `self`, without
changing native parsing or QEMU. Reports record the original, patch and patched
hashes and label the result `custom-guest-ir-callback-root-patch`; that result
does not grant the original published wrapper a PASS. See the patch README.

Electrical, optical, acoustic, motor and physical-hardware measurements remain
outside these virtual-device checks.
