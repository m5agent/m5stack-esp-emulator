# CoreS3 SPI microSD probe

Uses `machine.SDCard(slot=3, width=1)` on `SCK=G36`, `MOSI=G37`,
`MISO=G35`, `CS=G4`. The pin mapping is the CoreS3 row of the official
UIFlow2 `M5Unified/src/M5Unified.cpp` SPI pin table; the QEMU board attaches
its SPI SD model at CS4 in `hw/m5stopwatch/m5cores3.c`.

The device-local matrix case writes and reads a deterministic 512-byte sector,
checks its contents independently in the retained host disk image, and checks
the green screen marker and serial result. Device Service API sweep fixtures
add FAT mount, file write, sync, remount and an independent host FAT parser.
The boot file explicitly selects `main.py` and UART0 output, matching the
visible Device Service probes; the matrix waits for readiness and completion
markers before its final capture. The native SD block probe finishes before
the display draws its marker, so its SPI bus lifecycle stays explicit.
All results are virtual-device validation, with physical hardware NOT RUN.
