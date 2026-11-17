# Tab5 ST7123 GPIO IRQ and I²C probe

This ESP-IDF v5.5.4 guest reads the ST7123 over HP I²C1 at address 0x55
after a GPIO23 falling edge. It verifies the reported geometry, the
seven-byte coordinate report and the release with no active coordinates.

```sh
idf.py -C tests/firmware/tab5_st7123 -B "$BUILD_DIR" set-target esp32p4
idf.py -C tests/firmware/tab5_st7123 -B "$BUILD_DIR" build
(cd "$BUILD_DIR" && python -m esptool --chip esp32p4 merge_bin -o merged.bin @flash_args)
```

Configure a separate [native Device Service worker](../../../docs/device-service-api.md#create-a-reference-uiflow2-device)
with the ST7123 Touch ESP Part and admit the fixture's normalized 16 MiB
Flash SHA as `st7123`. Execute the fixture via the same API as an uploaded
firmware image. Use a disposable state directory and a separate control token.

```sh
python3 tests/firmware/tab5_st7123/run_service.py \
  --base-url "$DEVICE_API" --token-file "$CONTROL_TOKEN_FILE" \
  --firmware "$BUILD_DIR/merged.bin" --output "$EVIDENCE_DIR"
```

The runner observes an idle no-IRQ control, then sends three taps at
(0,1279), (719,0), and (310,608). On a hold-capable Part, it also holds
(240,780) for 1.2 guest seconds. It verifies a single unchanged coordinate
across the separate IRQ readbacks, ESP timer duration, and one release on the
same guest's UART. On a drag-capable Part, two opposing drags verify the
initial point, five moves, single release and the application's own
drag-completion marker. The runner retains the evidence ZIP before stopping.

## Original Arduventure power-off

Configure the native DSI worker with the current standby-latch-enabled Part.
Admit the normalized Flash SHA `0922e46d70edc11d285fd3d4023a18f061d4d95fd8e7a1729e00702cc3dba063`
for `st7123`. Provide the original Arduventure 1.0.0 upload BIN.

```sh
python3 tests/firmware/tab5_st7123/run_power.py \
  --base-url "$DEVICE_API" --token-file "$CONTROL_TOKEN_FILE" \
  --firmware "$ARDUVENTURE_BIN" --output "$POWER_EVIDENCE_DIR"
```

The runner includes short-tap and off-icon hold controls, the original power-off
frame, the live and ZIP latch receipt, quiet UART, and a normal title frame
after explicit Device Service reset.
[Native co-sim evidence](../../../docs/evidence/2026-11-17-tab5-power-latch/README.md)
