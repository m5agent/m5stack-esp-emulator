# Tab5 GT911 ESP Part

Build the GT911/ILI9881C Tab5 model with Rust 1.88.0 and the locked ESP Part
SDK at esp-emu v1.1.0.

```sh
rustup target add --toolchain 1.88.0 wasm32-unknown-unknown
RUSTUP_TOOLCHAIN=1.88.0 python3 platform/esp-parts/tab5-gt911/build.py \
  --output "$PWD/.work/tab5-gt911-board"
```

The tested macOS arm64 build prints module SHA-256
`f80d7bbb35fdbd9a260832846b96b64e8bb04d88c9f548cdb2354218852e1286`.
Use the resulting `m5_tab5_gt911.wasm` with the [Device Service settings](../../../docs/device-service-api.md#create-a-reference-uiflow2-device).
The service admits this exact module and uses the checked-in board wiring.

The Part claims the Tab5 HP I²C port 1 register devices, GT911 address
`0x14`, and GPIO23 for GT911 INT. It publishes single-contact reports at
16 ms virtual scan intervals. The guest reads coordinates over I²C and clears
status register `0x814e` to acknowledge each report. A tap holds for 180 ms of
virtual time after latching the initial report. Coordinates use the native
720×1280 panel. Calibration, multitouch, reset sequencing and other Tab5 touch
controller variants are outside the model.

The part also models the standard BMI270 configuration upload at address
`0x68` on HP I²C1. The guest supplies the configuration bytes and requests
initialization. The model validates a complete upload before reporting
success through `INTERNAL_STATUS`.
