# Dial rotary input: deferred GPIO callback state loss

The exact official Dial UIFlow2 v2.5.3 base has SHA256
`6a0187dad13c491129e9228ca36b9e04adb46ebf9d8d51fca8eca5f9b7332a53`.
The original `hardware.Rotary` / `RotaryIRQ` driver was exercised with its
normal display, touch, button and RTC program. Each test had its own composed
firmware, nonce-bound serial, GPIO/QOM evidence, framebuffer and retained ZIP;
all VMs were stopped after collecting evidence. This is virtual-device
validation, not physical-hardware timing or optical/electrical evidence.

An experimental runtime exposed the physical input source's edge period as a
QOM parameter; it never read, rewrote or compensated the guest counter.
Candidate runtime SHA256:
`8ee45be1baa8a038478bc2a0c120233ceac82787036b0c0198ab9ab08ca23871`.
Only Dial's input-source timing code differed from the fixed native baseline.
Each independent VM received physical targets `3, -2, 0`, repeated five times.
Every sequence delivered exactly 200 real GPIO41/40 quadrature edges and ended
with physical target/delivered target zero.

| Edge interval | Exact guest target matches | GPIO edges | Final guest value | Composed firmware SHA256 |
| --- | ---: | ---: | ---: | --- |
| 5 ms | 4/15 | 200 | 1 | `a74580354eb595096454747e7f9dc91611945d9419886224f21ea0f4a09134fa` |
| 25 ms | 1/15 | 200 | 2 | `5ca0fd9e120e74a1fb904cd8ee2e360665fe62df02f3ee8a856c84aa4020bc90` |
| 50 ms | 15/15 | 200 | 0 | `ba65914cf2ae4b6ae455b081c859474bf0df5f532557b8165ed1848607cee5cd` |

The 50 ms result is one validated slow input operating point for this exact
program/runtime. It is not a fix, a hardware timing specification, or proof
that arbitrary firmware never loses rotary steps. The timing candidate was
not merged into the native recipe or WASM source lock. Dial rotary remains
partial/candidate.

A separate 25 ms diagnostic observed the actual original Python callback and
FSM without replacing its counting logic. The physical sequence contained
40 edges and produced 40 GPIO Pin callbacks. GPIO40/41 retained their normal
any-edge interrupt configuration (`0x2180`). `GPIO_STATUS1` was already clear
when the Python callbacks ran, consistent with the native ISR acknowledging
the interrupt before scheduling Python work.

The decisive adjacent callbacks were:

| Callback | Pin | Time in guest microseconds | Live CLK/DT | FSM before → after | Guest value |
| --- | ---: | ---: | --- | --- | ---: |
| 16 | 40 | 2483919 | 11 | 6 → 32 | 3 → 2 |
| 17 | 41 | 2539211 | 00 | 32 → 0 | 2 → 2 |
| 18 | 40 | 2539463 | 00 | 0 → 0 | 2 → 2 |

Callback 17 should have observed the intermediate `01` state. It ran late,
then callback 18 ran 252 microseconds later; both read the current `00` pin
state. The original full-step FSM therefore lost that intermediate state and
one reverse detent. In this diagnostic, the loss occurred after interrupt
scheduling, rather than from missing GPIO edge callbacks. Other workloads
still require their own controller/IRQ evidence.

A QOM `detents` acknowledgement is only the physical input target. It must
never be displayed as an observed guest count. Future closure should validate
the original firmware's deferred-IRQ behavior and virtual-time/input delivery
under representative load, with bidirectional/reversal tests and the same
firmware/runtime evidence. Python `M5.getBoard()` is the firmware's compiled
`BOARD_ID`; board GPIO/controller readback remains a separate validation layer.
