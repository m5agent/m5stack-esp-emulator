# M5Stack Firmware Simulation Platform

[简体中文](README.md) · English

[![CI](https://github.com/m5agent/m5stack-esp-emulator/actions/workflows/ci.yml/badge.svg)](https://github.com/m5agent/m5stack-esp-emulator/actions/workflows/ci.yml)

Run M5Stack firmware in a browser or a local service. Inspect the display, use buttons and touch input,
exercise supported peripherals, and retain reproducible execution evidence.
The platform uses C/QEMU and independent device backends. UIFlow2 has the broadest validated coverage;
Arduino, ESP-IDF and MicroPython images are also supported when their compatibility requirements are met.

**[Try online](https://m5agent.github.io/m5stack-esp-emulator/)** · [Capabilities and limits](docs/project-status.md) · [Documentation](docs/README.md) · [Report an issue](https://github.com/m5agent/m5stack-esp-emulator/issues)

![CoreS3 firmware and interaction in the browser workbench](docs/images/browser-workbench.png)

*Captured from an actual browser run for this documentation update; see [image provenance and reproduction](docs/images/README.md). The deployed site can differ from main. See the [Pages guide](docs/pages-deployment.md) for deployment and version details.*

## Choose a runtime

| Mode | Use it for | Requirements and scope |
| --- | --- | --- |
| Browser WASM | Open a page and run a reference example or a compatible full-flash image | Only admitted devices and configurations; no Device Service required |
| Local Device Service | Virtual flashing, serial/display/input access, peripheral and network tests, automated evidence | Matching runtime assets, ROMs and firmware; sessions are managed through `/api/v1` |
| 3D model preview | Explore device and Unit enclosures, ports and interactions | A visible model does not imply a firmware execution backend |

Browser displays and state come from guest firmware and simulated controllers. The 3D shell presents
those results and supplies input. Consult the [generated project snapshot](docs/project-snapshot.md)
for backends, peripheral status and open work, and the [validation ledger](docs/validation-ledger.md)
for exact test conditions.

![Current Atom and Stick model previews, without firmware execution](docs/images/device-models.png)

*Visual catalog examples. Firmware execution must be validated separately for each device.*

## Try it online

1. Open the [website](https://m5agent.github.io/m5stack-esp-emulator/) in desktop Chromium.
2. Select a device marked “浏览器运行” (runs in browser) and its reference firmware. Start it and wait for the application display or ready marker.
3. Use the device's buttons, touch surface or supported inputs, inspect serial output and the display, then stop the instance.

The first run downloads WASM, ROMs and firmware. Some devices have a slow cold start. HTTPS,
Service Workers and shared memory are required. ROMs and firmware are downloaded and verified
in the visitor's browser; they are not bundled with the site. Local `.bin` files and firmware URLs
must still match the selected device's chip, board configuration and partition layout.
See [browser requirements and firmware scope](docs/pages-deployment.md).

## Run locally

Python 3.12+ is recommended:

```bash
git clone https://github.com/m5agent/m5stack-esp-emulator.git
cd m5stack-esp-emulator
./start.sh
```

Open <http://127.0.0.1:8787/platform/web/>. Also available: [sessions](http://127.0.0.1:8787/platform/web/sessions.html),
[firmware import](http://127.0.0.1:8787/platform/web/firmware.html) and [OpenAPI](http://127.0.0.1:8787/api/v1/openapi.yaml).
Use `PORT=8890 ./start.sh` to choose another port.

A fresh clone can serve the catalog and API pages. It does not contain the local runtime assets
needed to create native virtual devices. Follow [deployment and runtime setup](docs/deployment.md)
to build or configure backends matching the current source and host architecture, then create a
session through the workbench or [Device Service API](docs/device-service-api.md).
`running` only means the control channel has started. Confirm application readiness using
`ready_marker`, serial output and actual frames.

## Scope and limitations

- Compatibility depends on the device, profile, controller coverage, Flash/PSRAM, partition layout
  and security configuration. Successful import is not successful execution; a passing example
  does not imply support for arbitrary firmware. See [firmware admission](docs/firmware-manifest.md).
- Browser, native-service and physical-hardware validation are separate. Tab5 and CardputerZero
  have independent backends and usable subsets; they do not inherit ESP32 browser results.
  C6, P4 and Linux ARM64 are also separate targets from Xtensa WASM.
- Virtual-device results do not establish physical RF, power, acoustic, optical, mechanical
  or electrical equivalence.
- The service currently assumes a trusted host. Network policies and static checks do not
  replace production isolation for untrusted firmware.
- Firmware differences, startup time, input latency and Worker cleanup have known limitations.
  See [current status](docs/project-status.md) and the [runtime gap register](docs/runtime-model-gap-register.md).

## Development and contributions

Issues and pull requests are welcome. Include the device, runtime/profile, firmware SHA256,
reproduction steps and relevant serial/display evidence. Remove credentials, device identifiers
and private addresses. Check redistribution rights before sharing firmware binaries;
this source repository does not accept firmware or ROM images.

Read [AGENTS.md](AGENTS.md) and the local instructions for the directory you change.
Choose checks using the [test guide](tests/README.md). Common offline checks are:

```bash
PYTHONPATH=platform/tools python3 -m unittest discover -s platform/tests -p 'test_*.py'
python3 platform/tools/runtime_coverage.py --check
python3 platform/tools/peripheral_catalog.py --check
python3 platform/tools/qemu_profiles.py --check
python3 platform/tools/project_snapshot.py --check
```

| Looking for | Start here |
| --- | --- |
| Architecture and onboarding | [Engineering handoff](docs/engineering-handoff.md) · [Code map](docs/code-map.md) |
| Tasks and workstreams | [Backlog](docs/project-backlog.md) · [Workstream index](docs/workstreams.md) |
| Device and peripheral integration | [Device catalog](devices/README.md) · [Peripheral contracts](docs/peripheral-simulation-architecture.md) |
| Agent integration and same-guest Run | [Source-to-Unit session guide](docs/unit-agent-api.md) |
| Validation history and firmware differences | [Validation ledger](docs/validation-ledger.md) · [Firmware matrix](docs/user-firmware-simulation-matrix.md) |

Most detailed engineering documents are currently in Chinese. This README provides the English entry point.

## License and acknowledgements

Original code and documentation are licensed under the [MIT License](LICENSE). QEMU, WASM,
third-party code and model assets retain their own licenses. Review [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md)
before redistribution.
Thanks to [M5StopWatch-QEMU](https://github.com/zqqf16/M5StopWatch-QEMU),
[Espressif QEMU](https://github.com/espressif/qemu), [esp-emulator](https://github.com/espressif/esp-emulator),
[UIFlow MicroPython](https://github.com/m5stack/uiflow-micropython),
[M5GFX](https://github.com/m5stack/M5GFX), [M5Unified](https://github.com/m5stack/M5Unified)
and the [device model project](https://github.com/yuyun2000/m5stack-models) for their foundations and references.
