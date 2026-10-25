# Test index and evidence rules

Last reviewed: `2026-10-25`

This directory contains runnable regression fixtures and committed evidence.
It is not the authoritative description of current product capability:

- current device, profile, model-gap and task counts:
  [`docs/project-snapshot.md`](../docs/project-snapshot.md);
- current capabilities, risks and validation boundaries:
  [`docs/project-status.md`](../docs/project-status.md);
- unfinished work and acceptance criteria:
  [`docs/project-backlog.md`](../docs/project-backlog.md);
- chronological evidence:
  [`docs/validation-ledger.md`](../docs/validation-ledger.md);
- implementation and test routing:
  [`docs/code-map.md`](../docs/code-map.md).

Many case-level `README.md` files describe the runner and boundary at the time
that case was added. Read the current status pages before treating a case page
as today's complete-device capability.

## Test lanes

| Lane | Entry | Scope | Evidence boundary |
| --- | --- | --- | --- |
| Platform contracts | [`platform/tests/`](../platform/tests/) | API, catalog, manifest, storage, worker and documentation contracts | implementation support, not guest execution |
| UIFlow2 and device runtime | [`uiflow2/README.md`](uiflow2/README.md) | flash, boot, frame, input, peripherals, unified board/WiFi/BLE and Core2 radio | one case is scoped to its device, firmware, profile and evidence |
| Network and worker | [`network/README.md`](network/README.md) | Linux namespaces, DNS/TLS, bounded address/CIDR/domain-set egress, pcap, reconnect, worker control/runtime planes and restart continuity | diagnostic or transport evidence unless the fixture explicitly starts a matching guest |
| Firmware review | [`firmware/README.md`](firmware/README.md) | FirmwareManifest, static review, filesystems, SD/NVS fixtures, public-firmware matrix, security and model gaps | intake/static/runtime/security results stay separate |
| CardputerZero | [`cardputer_zero/README.md`](cardputer_zero/README.md) | Linux ARM64 boot, display, input and peripheral data planes | not an ESP32/UIFlow2 result |

Support directories such as `tests/uiflow2/lib/`,
`tests/uiflow2/_stackchan_probe/`, `tests/uiflow2/core2_wifi_probe/`,
`tests/uiflow2/rtc_api_probe/` and `tests/uiflow2/sticks3_public_network/`
contain shared probes or generated inputs. A support directory without its own
README is not a separately supported test entry.

## How evidence is named

- `evidence-YYYY-MM-DD-<topic>.json` is an immutable observation for that run.
- Evidence normally binds device, runtime/profile, firmware or artifact SHA,
  session identity, assertions, logs and cleanup.
- A later PASS does not erase an earlier FAIL or diagnostic checkpoint.
- A refreshed public firmware must be re-run even when the firmware ID and
  version ID did not change; the bytes can change behind the metadata.

Do not infer a current PASS from a README sentence alone. Open the referenced
JSON and confirm status, scope, hashes and checks.

## Normal commands

Run the fastest contract suite first:

```bash
PYTHONPATH=platform/tools python3 -m unittest discover \
  -s platform/tests -p 'test_*.py'
python3 platform/tools/runtime_coverage.py --check
python3 platform/tools/peripheral_catalog.py --check
python3 platform/tools/qemu_profiles.py --check
python3 platform/tools/project_snapshot.py --check
```

Agent-triggered functional firmware tests must use Device Service `/api/v1` so
the session is visible and retained. Direct QEMU runners in this directory are
for repository regression development and evidence reproduction.
