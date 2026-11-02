/* Bare-metal entry for the M5StickT2 virtual-device probe.
 *
 * QEMU's classic ESP32 machine can load an ELF image with -kernel; the probe
 * runs without ESP-IDF so the Lepton VoSPI/CCI and ST7789 panel paths are
 * driven through the same memory-mapped controllers as a real firmware. */
    .section .text.start, "ax"
    .global _start
    .type _start, @function
_start:
    movi    a0, 0
    movi    sp, 0x4009f000
    call0   probe_main
1:  j       1b
