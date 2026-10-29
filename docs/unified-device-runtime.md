# Unified Device Runtime Contract

Date: `2026-10-26`

This document defines the acceptance contract for a complete virtual device.
It does not track current counts, per-device PASS results or unfinished work.
Use the [automated project snapshot](project-snapshot.md),
[project current status](project-status.md),
[validation ledger](validation-ledger.md) and
[project backlog](project-backlog.md) for those facts.

## Decision

The product contract is one Device Service lease, one guest instance, one
firmware image and one evidence bundle:

```text
Device Service /api/v1
        |
        +-- one guest process
              +-- SoC + flash + RAM/PSRAM
              +-- board display / input / audio / camera / sensors
              +-- WiFi MAC/DMA and QEMU NIC
              +-- BLE controller/HCI path
              +-- serial + frame + input + QOM
              +-- network + peer + runtime-health evidence
```

A session assembled by joining output from unrelated guests, or by injecting
Python-level fake values after bypassing the controller, is not a unified
device PASS.

## Required invariants

Every `runtime=qemu-unified` profile must satisfy all of the following:

1. The requested firmware, device, chip architecture, flash layout and runtime
   profile are compatible.
2. One QEMU process owns the board model and executes the firmware from reset.
3. Board peripherals use their real bus/controller path, including GPIO, I2C,
   SPI, I2S, DMA/FIFO and interrupts where applicable.
4. WiFi association, DHCP and the required HTTP/DNS transaction originate from
   the same guest that drives the board.
5. BLE scan/connect/GATT traffic crosses the documented controller/HCI boundary
   of that same guest; an unrelated peer-only test is insufficient.
6. Display/input evidence is bound to the same lease. Headless devices use an
   explicit serial/peripheral contract instead of pretending to have a frame.
7. Evidence includes firmware SHA, runtime/profile, session identity, serial
   markers, frame/QOM/input data where applicable, network/peer data and
   failure-safe logs.
8. A failed data path returns `PARTIAL`, `FAIL`, `REVIEW` or
   `runtime_model_gap`; it must not be hidden by retry or by copying a PASS from
   another device.
9. A declared BLE reconnect workload receives a readiness budget derived from
   its cycle count and delay. A fixed application-start timeout must not be
   reported as a controller failure when the peer workload is still advancing.

## Evidence layers

| Layer | Required output | PASS meaning |
| --- | --- | --- |
| Intake | artifact SHA, chip/board/profile, partition and capability check | image is a valid candidate for this path |
| Boot | bounded serial transcript and application-ready marker | firmware reached the expected runtime stage |
| Board | frame/input/QOM/PCM/bus or endpoint evidence | the requested board data path executed |
| Network | DHCP/DNS/TCP/UDP plus pcap or structured network evidence | the same guest completed the declared network exchange |
| BLE | HCI counters plus scan/connect/GATT peer transcript | the same guest completed the declared controller exchange |
| Stability | health counters, queue depths, reset/panic scan and duration | no failure was observed for the declared window |
| Bundle | manifest, hashes and retained session | another operator can audit the result |

The evidence bundle must preserve the first failure. A later successful retry
does not erase an earlier panic, timeout, dropped packet or environment error.

## Status semantics

| Status | Meaning |
| --- | --- |
| `PASS` | Every required assertion for this exact firmware/path/window passed |
| `PARTIAL` | A useful subset passed, but an application or data-plane gate did not |
| `FAIL` | A compatible, modeled path produced reproducible fatal firmware behavior |
| `REVIEW` | Security or policy evidence is insufficient for an automated decision |
| `runtime_model_gap` | The simulator lacks a capability required by the firmware |
| `INFRA_ERROR` | The service, host runtime, storage or test fixture failed |
| `NOT RUN` | The required test or physical validation did not execute |

`runtime_model_gap`, `INFRA_ERROR` and `NOT RUN` are not firmware defects.
`PASS` is scoped to the artifact hash, device, profile, inputs and observation
window; it is not inherited by a sibling board or another firmware SHA.

## Runtime routing

| Request | Runtime/profile | Result boundary |
| --- | --- | --- |
| Complete virtual-device functional test | `runtime=qemu-unified` and a registered unified profile | one lease/guest evidence bundle |
| Network or provisioning diagnosis | `runtime=network` | diagnostic network evidence only |
| Legacy radio-only or compatibility test | `qemu-wifi`, `qemu-ble` or a documented legacy profile | no complete-device claim |
| Tab5 P4/C6 path | `esp-emulator-native` | explicitly bounded by Tab5 peripheral status |
| CardputerZero | separate Linux ARM64 backend | not an ESP32/UIFlow2 result |

`qemu-ble` remains an accepted compatibility alias; new board/radio acceptance
uses `qemu-unified`. Core2 new work uses `profile=core2-native-hci`.
`core2-native-vhci` remains diagnostic because its GDB-mediated control plane is
not a stable production executor.

Core2 unified profiles default to a 180-second session readiness budget. The
external unified BLE peer waits ten seconds after subscription before writing
the NUS characteristic so a slower guest can finish processing CCCD state
before exercising its TX path. That settle interval is a service scheduling
boundary, not RF timing or a hardware measurement.

## Integration rule

Do not launch one emulator behind another, copy a prebuilt emulator into a QEMU
session, or merge evidence from separate process runs into one device PASS.
Reuse protocol behavior by implementing the required radio/controller model in
the selected guest runtime.

Network fixtures, BLE peers, DNS/TLS gateways and packet capture tools may be
separate host processes. Their traffic must still target the guest and lease
being evaluated, and their logs must be included in the same evidence bundle.

## Boundaries

- The S3 NIC model covers guest-visible MAC/DMA, interrupts and user-net
  frames. The validated `qemu-wifi/generic-observe` route additionally covers
  WPA2-PSK RSN/M1-M4 and pairwise CCMP RX. It does not cover WPA3, group-key
  multicast, RF, antenna or channel/rate behavior. The C6 path remains
  Open-auth unless a profile explicitly states otherwise.
- Core2 OpenMAC and native-HCI have functional data-plane evidence, not a
  bit-exact Espressif BT controller/baseband or physical cache/PSRAM timing.
- Tab5 uses the closed-source P4 backend as a documented exception; missing
  CSI, I2S/PCM, USB Host, SDIO, dynamic I2C and controller-level touch remain
  explicit blockers.
- `runtime=network` user-net and loopback `hostfwd` are not an
  untrusted-firmware sandbox.
- Simulation cannot replace hardware measurements for RF, power, acoustics,
  optics, mechanics or electrical behavior.

## Acceptance and change control

A unified profile is accepted only after a real Device Service lease exercises
the same firmware path and the evidence bundle is retained. Current profiles,
counts and blockers are generated into
[project-snapshot.md](project-snapshot.md), while the narrative conclusion and
open work remain in [project-status.md](project-status.md) and
[project-backlog.md](project-backlog.md).

Any API, profile, evidence-field or runtime-routing change must update the
implementation, OpenAPI, contract tests, automated snapshot and affected
validation evidence in one reviewable change.
