# Tab5 GT911 GPIO IRQ and I²C fixture

This ESP-IDF v5.5.4 probe reads the GT911 over HP I²C controller 1 after a
GPIO23 interrupt. It reports the raw single-contact coordinates and clears
the controller's status to acknowledge each report. Its display pipeline is
unused. Use the [native Device Service GT911 profile](../../../docs/device-service-api.md#create-a-reference-uiflow2-device).

```sh
idf.py -C tests/firmware/tab5_gt911 -B "$BUILD_DIR" set-target esp32p4
idf.py -C tests/firmware/tab5_gt911 -B "$BUILD_DIR" build
cd "$BUILD_DIR"
python -m esptool --chip esp32p4 merge_bin -o merged.bin @flash_args
```

Upload the merged firmware through the native Device Service and wait for
`GT911_PROBE_WAIT`. A drag from (120,200) to (620,1000) should report these
ordered unique positions on the same session serial stream:

```text
(120,200) (220,360) (320,520) (420,680) (520,840) (620,1000)
```

The listener should then receive a release report and acknowledge its status.
Repeated samples are valid while a contact is held. This fixture verifies
the controller data plane. Use a separate original application UI check for
application semantics.
