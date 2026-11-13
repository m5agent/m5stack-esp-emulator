# C6 SPI2 chip-select host regression

This fixture compiles actual production SPI transaction, register-write, reset,
GPIO output-matrix, and GPIO listener code. It checks physical pin levels and
slave callback observations rather than treating a transaction's success or a
rendered image as proof that the right slave was selected.

The fixed upstream base is Espressif QEMU
`febae182e132e4055529be423a818225ebddaa3a`, with the C6 bootstrap prefix through
0015. `gpio-preimage.c` retains the GPIO register/data-plane functions and their
state; `spi-register-preimage.c` adds the SPI register-write and reset functions
to the six transaction functions in the sibling `c6_spi_data_length` fixture.
`registers.h` contains only the register constants needed by those functions.
The actual 0015 and 0016 patches are applied to these bounded fragments, with a
reverse-application check. No local runtime/source cache or network is needed
for normal checkout tests.

Run after both model patches are present:

```sh
python3 platform/tests/test_c6_spi_chip_select_patch.py -v
```

Independent pre-merge review can pass `--patch15 /path/to/0015.patch` and
`--patch16 /path/to/0016.patch` explicitly. These options do not modify the
candidate files.

The 24 cases execute both the pre-0016 code and the patched code under ASan and
UBSan. All 24 pass after the patch. The prior code fails 20 negative cases and
retains four passing controls: manual panel selection, manual radio isolation,
rejecting unsupplied DMA before asserting CS, and SPI1's existing SSI path.
Negative results require an assertion, not merely any failing process.

The independent signal/register expectations are taken from ESP-IDF v5.5.4's
ESP32-C6 GPIO and SPI headers: output matrix base `0x554`, four-byte stride,
eight-bit signal ID, OUT_INV bit 8, OEN_SEL bit 9, OEN_INV bit 10; SPI2 CS0 signal
68 and CS1..CS5 signals 101..105; SPI_MISC CS disable bits 0..5, polarity bits
7..12, and CS_KEEP_ACTIVE bit 30. The test configures these registers through
the real GPIO/SPI write handlers.

Assertions cover both slaves deselected, manual panel/radio selection, hardware
CS0..CS5, a wrong output signal, disabled CS, GPIO inversion, SPI positive CS
polarity, both inversions together, peripheral versus GPIO output enable,
inverted output enable, held CS across consecutive transfers, MISC release,
reset release, GPIO-matrix remapping, hardware radio selection, rejected DMA,
and SPI1 isolation. GPIO listeners capture actual falling/rising edges. The
panel callback verifies its CS pin is low when it receives the exact command
byte; the radio callback verifies its own selection. Endpoint callbacks and
the GDMA transport are explicit host-test stubs. They are not emulator-side
substitute peripherals.

This does not claim panel pixels, original-firmware boot, full radio protocols,
RF, electrical contention when multiple slaves are selected, physical timing,
browser execution, or chained DMA coverage. The same-BIN Device Service panel
probe and application runs are separate virtual-device evidence. The existing
radio-CS gate already suppressed panel writes when the radio was selected;
the reproduced new negative is that **both CS pins high still delivered a
display command** before 0016.

The 2026-11-13 independent run used 0016 patch SHA-256
`7a0173bc469263d2d8be333465544f7b463710eaebf26b7ffaf8a4738919cfe9`
and 0015 patch SHA-256
`559c7dd083e6eae5247762cbdbd3a531e11774f475e400acd60a08595e638cc8`.
All 48 positive/negative outcomes matched the expectations. A separate full
prefix replay from the pinned upstream commit matched the fresh build source
byte for byte, and all 21 retained function definitions matched that source.
The final complete-file SHA-256 values were:

| File | SHA-256 |
| --- | --- |
| `hw/ssi/esp32c3_spi.c` | `09e07a26e13ccf078e1fce4fe7f53fb750d03c0e8d75d87382666b866d111fa2` |
| `hw/gpio/esp32_gpio.c` | `e162b0940354e1509a88a77572feaf9cbac851a8fbd2f882f5b353f10b03048c` |

These source-level results do not replace the original-firmware guest results
or the final integrated platform test suite.
