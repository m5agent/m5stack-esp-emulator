# Classic RMT symbol deadlines

Native layer `0189-classic-rmt-symbol-timing.patch` replaces the fixed 1 ms
progress timer with per-channel deadlines derived from the selected APB or
REF_TICK clock, divider, and both duration fields of each RMT memory word.
Half-nanosecond carry preserves the 80 MHz clock without accumulating rounding
error. An asserted threshold interrupt does not pause transmission. Memory is
read one symbol at a time, including after wrap, so the guest owns refilling it.
Late callbacks retain the original deadlines; the model does not extend a
guest's refill allowance or change CPU cycle counts.

The hardware basis is the ESP32 TRM v5.9, chapter 30, especially sections
30.2.4–30.2.6 and the clock, threshold, and wrap register descriptions:
[Espressif technical reference manual](https://www.espressif.com/sites/default/files/documentation/esp32_technical_reference_manual_en.pdf).
The guest path resembles the byte-buffer custom driver in
[FastLED 3.5.0](https://github.com/FastLED/FastLED/blob/3.5.0/src/platforms/esp/32/clockless_rmt_esp32.cpp);
the addresses and constants below were independently checked in the original
BIN, without rebuilding or modifying it. This does not assert its exact
FastLED release version.

## Original firmware diagnosis

Original AtomMatrix image SHA-256:
`24892fcf5d5f8c97ee30a5ffb4fec166dca1c254cc6f54861af28abc8732ba2f`.

| Original code location | Observed behavior |
| --- | --- |
| `0x400d45f4`–`0x400d460a` | Constructor arguments: GPIO27, timing cycles 72/72/144, eight channels, two memory blocks |
| `0x400d316c` | Constructs pulse words and `mMaxCyclesPerFill = 27648` |
| `0x40081528` | Reads CCOUNT at TX start and saves `mLastFill` |
| `0x40081660` | Custom ISR calls refill with time checking enabled for the threshold interrupt |
| `0x40090698` | Refill routine; reads CCOUNT at `0x4009069e` |
| `0x400906a9`–`0x400906b1` | If elapsed cycles exceed the limit, sets `mCur = mSize`, causing zero termination |

The observed RMT configuration is APB 80 MHz, divider 2, 128-word capacity,
threshold 64, and wrap enabled. Zero and one pulse words are `0x0024800c` and
`0x00188018`; both total 48 RMT ticks. Thus each symbol lasts 1.2 µs, each refill
is due after 76.8 µs, and the driver's compiled 240 MHz cycle conversion allows
115.2 µs. The frequency is inferred from the original instructions, not a
physical measurement or a sampled runtime CPU clock.
The previous 1 ms cadence exceeded that limit. The retained baseline virtual
device produced 8,396 completions, 1,074,688 symbols and 16,792 threshold events:
exactly 128 symbols and two threshold events per completion, instead of the
600 symbols required for 25 RGB pixels. Those counters diagnose the old model;
they are not post-fix guest acceptance.

## Reproducible host controls

Python 3.12+, Git and a host C compiler are required. No local firmware, QEMU
cache, network or running guest is required:

```sh
PYTHONPATH=platform/tools:platform/tests python3 -m unittest \
  test_classic_rmt_timing_patch test_classic_atom_rmt_patch \
  test_bootstrap_unit_runtime_recipe test_esp32_classic_rmt_patch -v
```

The new test replays the checked-in native RMT source layers, compiles the
actual C controller against a deterministic virtual clock, and reverses both
patches back to the seed. A byte-refill/CCOUNT control reconstructed from the
original disassembly retains the 27,648-cycle limit. The unchanged old model
produces 128 symbols; the new model produces all 600 in 720 µs. Deliberately
late guest handling still truncates at 128, proving the limit was not bypassed.
Additional controls cover APB/REF_TICK, divider zero, fractional ticks, zero
terminators, live refill after wrap, continued transmission without interrupt
acknowledgement, delayed timer callbacks, capture bounds, independent channels
and reset cancellation.

[Dated host evidence](host-evidence-2026-11-13.json) records exact source hashes
and result boundaries. These are **host C regression** results. The integrated
native build, same-BIN Device Service run and full native matrix belong to the
integration validation; they are **NOT RUN in this host record**. Browser-WASM
is unchanged. Physical timing, GPIO edges and electrical behavior are not
established by these controls.
