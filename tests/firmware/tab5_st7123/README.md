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
(0,1279), (719,0), and (310,608). It verifies the exact coordinates and released
status on the same guest's UART and retains the evidence ZIP before stopping.
This probe covers the controller, GPIO interrupt and guest read path.
