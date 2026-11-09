# Cardputer K132 native board validation

The native board has its own ESP32-S3 machine, no PSRAM, a 240 × 135 ST7789V2
panel, two GP-SPI controller paths and the G2/G1 Grove I²C wiring. The original
74HC138 decoder uses G8/G9/G11 to select the active-low sense signals on
G13/G15/G3/G4/G5/G6/G7. The source [official pin map](https://docs.m5stack.com/en/core/Cardputer)
and [keyboard driver](https://github.com/m5stack/M5Cardputer/blob/bf64d3178ab43928fa02365fbe3937cec99716ad/src/utility/Keyboard/KeyboardReader/IOMatrix.cpp)
establish those assignments.

All three unmodified stock firmware cases passed the display and input path in
the dedicated Device Service. A and Q opened the two factory launcher
versions. Fn on V0.9 changed the actual visual indicator while held and
restored it after release. In UIFlow2 v2.5.4, F12 drove G0 and changed the offline
screen to the application menu. The firmware, QEMU, ROM, eFuse, per-run frame
and ZIP digests are bound in the [summary](summary.json).

The failed filesystem replacement controls are also retained in the summary.
The [guest probe](../../../tests/firmware/cardputer_k132_stock/overlay_probe.py) was placed in a newly composed LittleFS VFS
using the exact original v2.5.4 image and its partition offsets. The composed
image reached ROM bootloader entry and stayed blank on both tested QEMU builds.
The failure cause is still open. The passing run used the unmodified UIFlow2
image with the final Grove-aware build.

The reproduction entry point is [the stock firmware service fixture](../../../tests/firmware/cardputer_k132_stock/README.md).
Firmware binaries and raw captures stay outside Git.
