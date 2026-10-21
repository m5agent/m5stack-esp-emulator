# Peripheral simulation catalog

`catalog.json` is the contract between device profiles, QEMU board models,
UIFlow2 API tests and future Device Center scheduling.

Every non-display capability declared in `devices/catalog.json` must map to at
least one component in the device's peripheral manifest. A new device cannot
pass CI until all of its sensors and controls are registered.
The inverse is also enforced: every modeled component must be represented by
the device's hardware inventory, so a peripheral cannot exist only in the QEMU
board implementation while remaining absent from the Device Center manifest.
`runtime-coverage.json` maps every `simulated` model to at least one matrix
case with runtime evidence or to a concrete external test and evidence file.
The mapped case's QEMU machine or external `device` must also appear in that
model's `tested_devices`, preventing coverage from an unrelated board.
Every device also has a `device_case_groups` entry whose cases must run on that
device and whose model list covers all simulated components on the board. A
model tested only on another controller cannot silently make a new board
peripheral-complete.
Every matrix and external case must also appear in `case_models`, listing the
exact simulated chip models exercised by that case. CI intersects these lists
with each device's components and rejects a board when any simulated component
has no device-local case. Inheriting `simulated` from another board is not
sufficient.
Every matrix or external case must be assigned to exactly one device group, so
adding a test without wiring it into device scheduling also fails validation.

Every device manifest must also carry at least one official documentation or
schematic evidence URL. Every `simulated` model must declare a concrete
`data_plane` (register/protocol path followed by the controller and DMA/buffer
endpoint), at least one injection/source interface, and at least one
`tested_devices` entry where the UIFlow2 path was actually exercised.

The catalog validator also compares device-level component status with the
selected backend. A chip model that works on one SoC is not automatically valid
on another. If a device uses a model that is still `partial`/`planned`, or the
board wiring has not been exercised on that backend, the component must say so
and the device must list the same model in `peripheral_blockers`.

Validation reads `devices/catalog.source.json`, not the generated display
catalog, so the real `hardware.sensors` and `hardware.controls` arrays are
checked. The current 14-device source contains 155 unique hardware
requirements; every requirement must be covered by a registered component.

Display, framebuffer and touch do not satisfy this contract by themselves. A
new board profile must enumerate every non-display sensor, actuator, storage,
radio, fieldbus or power-path component. The UIFlow2 peripheral runner also
rejects a case with no runtime evidence source, so a new manifest cannot become
`simulated` through a static PASS declaration.

## Status

- `simulated`: protocol behavior, data injection and readback are implemented;
- `partial`: chip identity or a subset of behavior is implemented;
- `planned`: registered but still missing a usable model;
- `not-applicable`: platform is outside the ESP32 simulator scope.

`simulated` is a model-level claim. A device still needs its own board-level
test before its component can be marked `simulated`; reusing a chip driver on a
different SoC, bus, DMA controller or pin mapping is not sufficient.

Validate:

```bash
python3 platform/tools/peripheral_catalog.py --check
python3 platform/tools/peripheral_catalog.py --json
python3 platform/tools/runtime_coverage.py --check
```

Generate the Device Center-facing inventory. It includes backend identity,
every hardware requirement, the matched component, chip model, bus/address,
QOM path, injection mechanism, data plane and blocker:

```bash
python3 platform/tools/peripheral_inventory.py
python3 platform/tools/peripheral_inventory.py --device tab5 --json
python3 platform/tools/peripheral_inventory.py --require-complete
```

Generate the runtime interface map. It extracts concrete QOM properties, QMP
input controls, PCM/RMT files, block devices, framebuffer captures and external
probe entry points from the evidence matrix:

```bash
python3 platform/tools/runtime_interfaces.py
python3 platform/tools/runtime_interfaces.py --model bmi270
```

The same data is served by `/api/peripheral-interfaces` and
`/api/peripheral-interfaces/<model>` for Device Center integration.

## New device checklist

1. Add the device to `devices/catalog.source.json`.
2. Add a matching entry to `platform/peripherals/catalog.json`.
3. Register every IMU, touch controller, PMIC, expander, RTC, audio codec,
   camera, sensor, actuator, fieldbus and storage device.
4. Include chip part number, bus, I2C address or GPIO, QOM path, injection
   mechanism and a component-level status.
5. Add official documentation/schematic evidence for every non-obvious part.
6. Add a QEMU board model or reuse an existing board/peripheral model.
7. Define the data plane for camera, audio, IR, RF, storage and USB.
8. Add a UIFlow2 API probe under `tests/uiflow2/`.
9. Add the device to `run_peripheral_matrix.py`.
10. Add every simulated model to `runtime-coverage.json`.
11. Add each new case to `case_models` with the exact models it exercises.
12. Add a `device_case_groups` entry containing the matrix/external cases that
    run on the new device and cover every simulated component.
13. Run the normal display/input matrix and peripheral matrix.

Use [`device-template.json`](device-template.json) as the manifest skeleton.
Use [`model-template.json`](model-template.json) for a new chip model.

New manifests start as `peripheral_status: "planned"` with explicit blockers.
Only remove a blocker and change the matching component to `simulated` after
the complete injection -> controller/bus/DMA -> UIFlow2 API -> display/serial
evidence path passes on that exact device backend.

CI also enforces the completion policy. Every device with an unfinished
component must be listed in `completion_policy.incomplete_device_allowlist`
with a concrete reason and future review date. A newly registered device is
therefore rejected unless all of its non-display peripherals are complete.
Remove an exemption as soon as the device becomes complete.

The current Tab5 backend work is specified in
[`docs/p4-peripheral-backend-requirements.md`](../../docs/p4-peripheral-backend-requirements.md).
