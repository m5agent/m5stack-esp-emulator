# Tab5 ST7123 GPIO I²C board detection

Build this ESP Part with Rust 1.88.0 and the locked esp-emu v1.1.0 ESP Part SDK.

```sh
rustup target add --toolchain 1.88.0 wasm32-unknown-unknown
RUSTUP_TOOLCHAIN=1.88.0 python3 platform/esp-parts/tab5-st7123-gpio/build.py \
  --output "$PWD/.work/tab5-st7123-gpio-board"
```

The tested WASM SHA-256 is
`6eaa3664fd81ce7e8f56bc0f84ad124ca2afcce21c947e74bbb41f1d9802d106`.
Set `M5_TAB5_ST7123_I2C_PART` to the absolute path of that module and select
`st7123` in the [Device Service configuration](../../../docs/device-service-api.md#create-a-reference-uiflow2-device).

M5GFX uses software I²C for Tab5 board detection. The Part listens to the
master's actual SDA/SCL transitions on GPIO31/32 and drives the SDA input
during slave ACKs and reads. It serves the PI4IO addresses `0x43`/`0x44` and
ST7123 firmware version 3 at address `0x55`, register `0x0000`. The esp-emu
hardware I²C controller remains independently attached for the firmware's
subsequent hardware-bus operations. [M5GFX detector](https://github.com/m5stack/M5GFX/blob/28d47949bdc84f30881623476f555398e2194313/src/board_detect/m5/esp32p4.inl)

The verified scope is board detection and the original Arduventure DSI
startup. The part covers the digital behaviors needed in those transactions.
ST7123 contact events, multi-master arbitration, component electrical
timing, and other Tab5 panel revisions are outside this model.
