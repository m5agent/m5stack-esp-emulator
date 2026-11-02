#!/bin/sh
# Build the M5StickT2 bare-metal probe ELF.
#
# Requires the Espressif xtensa-esp-elf toolchain with the ESP32 dynconfig:
#   XTENSA_GNU_CONFIG=.../xtensa-esp-elf/lib/xtensa_esp32.so
set -eu
HERE=$(cd "$(dirname "$0")" && pwd)
CC=${CC:-/Users/m5agent/.espressif/tools/xtensa-esp-elf/esp-14.2.0_20260121/xtensa-esp-elf/bin/xtensa-esp-elf-gcc}
export XTENSA_GNU_CONFIG=${XTENSA_GNU_CONFIG:-/Users/m5agent/.espressif/tools/xtensa-esp-elf/esp-14.2.0_20260121/xtensa-esp-elf/lib/xtensa_esp32.so}
OUT=${1:-$HERE/build}
mkdir -p "$OUT"
"$CC" -mabi=call0 -nostdlib -ffreestanding -O0 -mlongcalls \
    -T "$HERE/link.ld" -o "$OUT/stickt2-probe.elf" \
    "$HERE/start.S" "$HERE/probe.c" -lgcc
ls -l "$OUT/stickt2-probe.elf"
