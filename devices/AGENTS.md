# Device catalog and onboarding

The [root guidance](../AGENTS.md) applies. `catalog.source.json` is the editable
device source. `catalog.json`, per-device JSON and the generated device README
sections come from `platform/tools/generate_catalog.py`; do not hand-edit those
outputs to make a validator pass. See [the device index](README.md).

## Onboard a functioning device

1. Record the exact model/revision, chip, memory, display, controls, sensors and
   official documentation/schematic in `catalog.source.json`. A similar casing
   or SDK family is not proof of identical wiring or controller support.
2. Register the backend/profile in `platform/qemu/profiles.json` or document the
   independent backend. Do not alias a different SoC to an existing ESP32 model.
3. Follow the [peripheral contract](../platform/peripherals/README.md): enumerate
   every non-display capability, component status, bus/address/GPIO, data plane,
   injection/source interface and blocker. Use its device/model templates.
4. Add a device-local original-driver probe and runtime case mapping for every
   simulated component. Include `case_models`, `tested_devices` and the device
   case group; coverage from another board does not complete this board.
5. Regenerate catalog outputs, update profiles and run affected cases before
   changing status. `partial`/`planned` remain explicit with concrete blockers
   and a dated incomplete-device allowlist entry.

Use `qom_steps`, settle intervals and serial readiness markers for runtime
transitions. Do not encode host-side fake values or report a sensor/actuator as
simulated solely because its model or register identity exists.

## Execution and visual inventory

Native service support, browser admission and a visual model are separate
registries. Model shells come from the pinned model import under
`platform/web/vendor/`; adding one does not create a backend or admit firmware.
Browser support additionally requires the profile/runtime intersection and
that device's actual browser input/frame/output/cleanup evidence. Tab5 and
CardputerZero retain independent backend boundaries.

Firmware compatibility must name chip/profile, Flash/PSRAM, partition/image
layout and eFuse/security/controller requirements. A public download URL is
not redistribution permission. Keep firmware and ROM artifacts out of Git.

## Generate and check

From the repository root:

```sh
python3 platform/tools/generate_catalog.py
python3 platform/tools/qemu_profiles.py --check
python3 platform/tools/peripheral_catalog.py --check
python3 platform/tools/runtime_coverage.py --check
```

The catalog tool generates device outputs; `profiles.json` and the peripheral
registries are maintained sources checked by their validators. Do not hide a
mismatch by changing a test expectation. Update the current status/backlog and
regenerate the project snapshot after the final inventory/document edits. Put
exact run counts and SHA-bound results in the ledger/evidence, not in this guide.
