# Tab5 ST7123 board detection and native touch

Build this ESP Part with Rust 1.88.0 and the locked esp-emu v1.1.0 ESP Part SDK.

```sh
rustup target add --toolchain 1.88.0 wasm32-unknown-unknown
RUSTUP_TOOLCHAIN=1.88.0 python3 platform/esp-parts/tab5-st7123-gpio/build.py \
  --output "$PWD/.work/tab5-st7123-gpio-board"
```

The tested WASM SHA-256 is
`0999697f5aad5b87d8802f628c0313425866a9d3ad232c1b5e0db15b2fe12e87`.
Set `M5_TAB5_ST7123_TOUCH_PART` to the absolute path of that module and select
`st7123` in the [Device Service configuration](../../../docs/device-service-api.md#create-a-reference-uiflow2-device).

M5GFX uses software I²C for Tab5 board detection. The Part listens to the
master's actual SDA/SCL transitions on GPIO31/32 and drives the SDA input
during slave ACKs and reads. It serves the PI4IO addresses `0x43`/`0x44` and
ST7123 firmware version 3 at address `0x55`, register `0x0000`.
After boot, the native Part attaches to HP I²C1, serves the existing board
register devices, and models the status and seven-byte ST7123 contact
report. It drives GPIO23 low until the guest reads the full coordinates
or the release. Unread reports expire. Taps and holds use raw 720×1280
coordinates. Holds keep the coordinate visible to polling on the guest
clock, with refresh IRQs no more often than every 16 ms. Refresh reads
are counted separately from contact and release.
[M5GFX detector](https://github.com/m5stack/M5GFX/blob/28d47949bdc84f30881623476f555398e2194313/src/board_detect/m5/esp32p4.inl)
· [M5GFX runtime touch driver](https://github.com/m5stack/M5GFX/blob/28d47949bdc84f30881623476f555398e2194313/src/lgfx/v1/platforms/esp32p4/Touch_ST7123.inl)

See the [guest controller probe](../../../tests/firmware/tab5_st7123/README.md)
for version, panel geometry, IRQ, coordinate and release verification.
Drag, multitouch, reset-pin electrical timing, and other panel revisions are
outside this ST7123 model.
