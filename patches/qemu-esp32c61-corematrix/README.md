# ESP32-C61 CoreMatrix QEMU

The base is Espressif QEMU `esp-develop` commit
[`8fd40d7f1a5151c1747375b920c3e2d5cff0b0dc`](https://github.com/espressif/qemu/commit/8fd40d7f1a5151c1747375b920c3e2d5cff0b0dc).
The diagnostic retains the upstream C61 CPU, ROM, boot Flash and CLIC wiring.
Its board option is `-M esp32c61,m5corematrix=on`.

- `0001` corrects a source-build dependency result when slirp is disabled.
- `0002` maps the C61 digital HP I²C controller at `0x60004000` with CLIC
  source 45. The command engine uses C61 opcodes, a 32-byte TX/RX FIFO, eight
  command slots, repeated start, STOP, END, NACK and interrupt state.
  The separate upstream analog master remains in place.
- `0003` maps the WLAN microsecond counter at `0x600ad800` to QEMU virtual time.
  Stock PHY initialization uses this counter to bound its SDM polling loop.
- `0004` adds the command and completion paths for the idle RF front-end
  estimator, TX DC detector, SAR detector, frequency sequencer and MAC reset.
  It also implements the bidirectional USB Serial/JTAG endpoint and interrupt.
  The boot model assumes no RF input and does not exchange Wi-Fi packets.
- `0005` transfers a full 64-byte USB Serial/JTAG CDC IN packet as soon as
  it fills. Partial packets continue to use the endpoint's WR_DONE command.
- The optional C158 board wiring shares SDA/GPIO0 and SCL/GPIO1 between the
  software I²C probe and HP I²C controller. The bus contains M5PM1 at `0x6e`,
  M5IOE1 at `0x4f` and TM1680 at `0x72`. M5IOE1 PIN4, mask `0x08` in the
  port mode and output registers, drives the matrix rail. The HP controller
  leaves its target selected after END while the batch is idle.
  TM1680 commands and RAM writes produce the
  16×16 monochrome console. Standard QEMU A/B/C key down/up updates the
  active-low M5PM1 GPIO G0/G1/G2 and their latched status bits.

The unmodified UIFlow2 v2.5.4 image reaches its stock missing-SSID cross and
MicroPython prompt on C158. The isolated Device Service reproduces the startup
frame, USB REPL drawing and A/B/C interactions. The stock guest reported
internal heap only.
M5PM1 power-key and external interrupt wire, M5IOE1 peripheral channels,
BMI270, SPI microSD, buzzer, Wi-Fi packet I/O and 8 MiB Quad PSRAM remain
unvalidated or unmodeled here.

## Build and replay

Use a separate checkout with the normal QEMU host dependencies, including
GLib, Pixman, Ninja, pkg-config and libgcrypt. The C61 ECC/ECDSA QOM devices
depend on libgcrypt even when this probe uses neither accelerator.

```sh
git clone https://github.com/espressif/qemu.git qemu-c61
git -C qemu-c61 checkout --detach 8fd40d7f1a5151c1747375b920c3e2d5cff0b0dc
for patch_file in "$SIM_ROOT"/patches/qemu-esp32c61-corematrix/*.patch; do
    git -C qemu-c61 apply --check "$patch_file" &&
        git -C qemu-c61 apply "$patch_file" || exit
done
mkdir -p qemu-c61/build
(
    cd qemu-c61/build
    ../configure --target-list=riscv32-softmmu --enable-gcrypt --enable-fdt=internal \
        --disable-docs --disable-werror --disable-gtk --disable-cocoa --disable-sdl \
        --disable-gnutls --disable-nettle --disable-vnc --disable-slirp \
        --disable-curl --disable-libssh --disable-zstd --disable-bzip2 \
        --disable-curses --disable-auth-pam --disable-dbus-display --disable-tpm --disable-tools
    ninja qemu-system-riscv32
)
```

`SIM_ROOT` is the absolute simulator checkout path. The build config is for
the isolated guest probe. For a static libgcrypt installation, make its
pkg-config and libgpg-error linker flags visible to configure.

The exact fixture, stock baseline and recorded execution are in the
[CoreMatrix feasibility test](../../tests/firmware/corematrix_backend_feasibility/README.md).

Hardware and driver sources are the [C158 official pinout](https://docs.m5stack.com/en/core/CoreMatrix),
[ESP-IDF C61 I²C LL](https://github.com/espressif/esp-idf/blob/735507283d5b2f9fb363a1901172dbd9e847945d/components/hal/esp32c61/include/hal/i2c_ll.h),
[ESP-IDF C61 USB Serial/JTAG LL](https://github.com/espressif/esp-idf/blob/v5.5/components/hal/esp32c61/include/hal/usb_serial_jtag_ll.h#L150-L167),
[M5PM1 driver](https://github.com/m5stack/M5PM1/tree/315d2899c863ae34b59197392b9f4c59490751ef/src),
[M5IOE1 driver](https://github.com/m5stack/M5IOE1/tree/8401119bf171cb8f906fbe22e7490989077bbee8/src)
and the [M5GFX power sequence pinned by UIFlow2 v2.5.4](https://github.com/m5stack/M5GFX/blob/eef855b41c8ab7611a235055cc9afca76751ea95/src/board_detect/m5/pmic_ops.hpp).
