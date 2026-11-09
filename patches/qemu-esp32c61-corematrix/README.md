# ESP32-C61 CoreMatrix diagnostic QEMU

The base is Espressif QEMU `esp-develop` commit
[`8fd40d7f1a5151c1747375b920c3e2d5cff0b0dc`](https://github.com/espressif/qemu/commit/8fd40d7f1a5151c1747375b920c3e2d5cff0b0dc).
The diagnostic retains the upstream C61 CPU, ROM, boot Flash and CLIC wiring.
Its board option is `-M esp32c61,m5corematrix=on`.

- `0001` corrects a source-build dependency result when slirp is disabled.
- `0002` maps the C61 digital HP I²C controller at `0x60004000` with CLIC
  source 45. The command engine uses C61 opcodes, a 32-byte TX/RX FIFO, eight
  command slots, repeated start, STOP, END, NACK and interrupt state.
  The separate upstream analog master remains in place.
- The optional C158 board wiring connects SDA/GPIO0 and SCL/GPIO1 logical bus
  0 to M5PM1 at `0x6e`, M5IOE1 at `0x4f` and TM1680 at `0x72`. M5IOE1 IO4
  drives the matrix power rail. TM1680 commands and RAM writes produce the
  16×16 monochrome console. Standard QEMU A/B/C key down/up updates the
  active-low M5PM1 GPIO G0/G1/G2 and their latched status bits.

The supported scope is the IDF probe's controller, key and display path.
M5PM1 power-key and external interrupt wire, M5IOE1 peripheral channels,
BMI270, SPI microSD, buzzer, WiFi and 8 MiB Quad PSRAM remain unvalidated or
unmodeled here. The QEMU option is for the opt-in diagnostic. Production
firmware admission and browser runtime stay disabled for this candidate.

## Build and replay

Use a separate checkout with the normal QEMU host dependencies, including
GLib, Pixman, Ninja, pkg-config and libgcrypt. The C61 ECC/ECDSA QOM devices
depend on libgcrypt even when this probe uses neither accelerator.

```sh
git clone https://github.com/espressif/qemu.git qemu-c61
git -C qemu-c61 checkout --detach 8fd40d7f1a5151c1747375b920c3e2d5cff0b0dc
git -C qemu-c61 apply "$SIM_ROOT"/patches/qemu-esp32c61-corematrix/*.patch
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
git -C qemu-c61 apply --reverse --check "$SIM_ROOT"/patches/qemu-esp32c61-corematrix/*.patch
```

`SIM_ROOT` is the absolute simulator checkout path. The build config is for
the isolated guest probe. For a static libgcrypt installation, make its
pkg-config and libgpg-error linker flags visible to configure.

The exact fixture, stock baseline and recorded execution are in the
[CoreMatrix feasibility test](../../tests/firmware/corematrix_backend_feasibility/README.md).

Hardware and driver sources are the [C158 official pinout](https://docs.m5stack.com/en/core/CoreMatrix),
[ESP-IDF C61 I²C LL](https://github.com/espressif/esp-idf/blob/735507283d5b2f9fb363a1901172dbd9e847945d/components/hal/esp32c61/include/hal/i2c_ll.h),
[M5PM1 driver](https://github.com/m5stack/M5PM1/tree/315d2899c863ae34b59197392b9f4c59490751ef/src),
[M5IOE1 driver](https://github.com/m5stack/M5IOE1/tree/8401119bf171cb8f906fbe22e7490989077bbee8/src)
and the [M5GFX TM1680 packet layout](https://github.com/m5stack/M5GFX/blob/1b6a793a28fd298deeb9c79f0c412170713ea556/src/lgfx/v1/panel/Panel_TM1680.inl).
