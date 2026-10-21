# Peripheral simulation catalog

`catalog.json` is the contract between device profiles, QEMU board models,
UIFlow2 API tests and future Device Center scheduling.

Every non-display capability declared in `devices/catalog.json` must map to at
least one component in the device's peripheral manifest. A new device cannot
pass CI until all of its sensors and controls are registered.

Every device manifest must also carry at least one official documentation or
schematic evidence URL. A high-bandwidth model cannot claim `simulated` unless
it declares a concrete `data_plane` (framebuffer, PCM ring buffer, packet
mailbox, virtual block device or USB endpoint).

## Status

- `simulated`: protocol behavior, data injection and readback are implemented;
- `partial`: chip identity or a subset of behavior is implemented;
- `planned`: registered but still missing a usable model;
- `not-applicable`: platform is outside the ESP32 simulator scope.

Validate:

```bash
python3 platform/tools/peripheral_catalog.py --check
python3 platform/tools/peripheral_catalog.py --json
```

## New device checklist

1. Add the device to `devices/catalog.source.json`.
2. Add a matching entry to `platform/peripherals/catalog.json`.
3. Register every IMU, touch controller, PMIC, expander, RTC, audio codec,
   camera, sensor, actuator, fieldbus and storage device.
4. Include chip part number, bus, I2C address or GPIO, QOM path and injection
   mechanism.
5. Add official documentation/schematic evidence for every non-obvious part.
6. Add a QEMU board model or reuse an existing board/peripheral model.
7. Define the data plane for camera, audio, IR, RF, storage and USB.
8. Add a UIFlow2 API probe under `tests/uiflow2/`.
9. Add the device to `run_peripheral_matrix.py`.
10. Run the normal display/input matrix and peripheral matrix.

Use [`device-template.json`](device-template.json) as the manifest skeleton.
