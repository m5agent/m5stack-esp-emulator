# Unit hard-reset output boundary

Date: `2026-10-29`

Validation category: **virtual-device validation**

This record closes `UNIT-HOST-36` for the shared GPIO hard-reset lifecycle and
the Relay/Relay2 derived-output state that depended on it. It is not an
electrical, contact, coil, load or physical-hardware result.

## Implementation

Patch `0087-unit-hard-reset-output-boundary.patch` adds a reset-observer API to
the legacy GPIO model. Patch SHA256 is
`d269d35e83411f2c7170e36a76948531f7a2e6d43611f1adf916ab903aa4f7db`.
`esp32_gpio_reset_hold()` now:

1. clears controller registers and establishes the post-reset output routes;
2. notifies reset observers with the actual post-reset pad level;
3. publishes any changed effective line through the existing output listeners
   and transition-IRQ path.

Relay and Relay2 register reset observers. A reset rebases
`previous_output` from the post-reset pad and clears the applicable transition
counters. The observer runs before the normal output notification, so a
high-to-reset-low boundary is not counted as a new transition. The same helper
also handles a Unit-local reset independent of GPIO reset ordering.

This is generic reset propagation, but only peripherals that opt into the reset
observer receive peripheral-specific semantics. It does not automatically
reset unrelated Unit state, FlashLight qualification, relay contacts or other
analog/electrical behavior.

## A/B guest result

Both runs used the same AtomS3R UIFlow2 guest image and the same 10 gpio-1/2
assignment. The guest drove both Relay2 inputs high, requested
`POST /api/v1/sessions/{id}/reset`, then held the pads low and drove gpio-1,
followed by gpio-2, high again.

- firmware SHA256:
  `ab4dd742a342f85037c3c0cb2c67c037bf5eef7cf429bee131d2227d4a404e3d`
- pre-fix QEMU SHA256:
  `9aca9a8db5143ad133510795cd228ed8ac23c388ea197267d7b2b4750e58eb82`
- fixed QEMU SHA256:
  `e318b2b748d6e982cd2e592a1b991ec930a8e9501cf02a0c19925022a656b373`

The fixed source was rebuilt from QEMU
`40edccac415693c5130f91c01d84176ae6008566` with the 38-patch source receipt;
`bootstrap-unit-runtime.py --check` reported `source_status=verified` and 119
patched source files. Bootstrap-local `0003`–`0006` forward ports isolate the
existing `0065/0066/0069/0070` behavior from their historical Core2 diagnostic
prerequisites; those original diagnostic patches remain unchanged.

| Runtime/model | Immediately after reset | Second boot |
| --- | --- | --- |
| pre-fix Relay2 | pads low, counters still `1/1` | FAIL: reset boundary was counted as stale state |
| fixed Relay2 | pads low, counters `0/0` | gpio-1 `1/0`, then gpio-2 `1/1`; PASS |
| pre-fix Relay | counter still `2`, then `3` after the warm-boot low write | FAIL: counter crossed reset and lost its reset boundary |
| fixed Relay | counter `0` at reset; the released input's later low write creates the first warm-boot transition | gpio-2 remains stable while gpio-1 is high, then increments by one when gpio-2 goes high; PASS |

The pre-fix Relay2 evidence ZIP SHA256 is
`cc259eff53bc2ee9132c4aae46503719cd1a0e386c34b66fa085a585f45406c7`.
The fixed Relay2 evidence ZIP SHA256 is
`67acff27951363b7fe27fe185a6cf78e0f06ce0057ac84868a335c7c8ea428b0`.
The pre-fix single-Relay evidence ZIP SHA256 is
`91b176229d55bf9e30e34695b7f7363f0507222c5ae5b87a661db0c76d91cd31`;
the fixed single-Relay evidence ZIP SHA256 is
`6ac5a02268a8c9b6230ff784debb57aecd08cc7e4fad518143206c054b9203f3`.

All sessions were requested with evidence before `purge=0` stop. The retained
evidence contains serial, QOM snapshot, Unit contract/state, current frame,
session manifest and process cleanup state.

Final repository regression: platform `1558 tests OK, 10 skipped`; runtime
coverage, peripheral catalog, QEMU profiles and generated project snapshot
checks PASS; the `0087` reverse-apply check and source receipt verification
also PASS.

## Reproduction

```bash
python3 scripts/bootstrap-unit-runtime.py \
  --source-dir .work/unit-host36-reset-source/qemu \
  --work-dir .work/unit-runtime-build

python3 tests/units/run_relay_reset_probe.py \
  --out-dir /tmp/m5-relay-reset \
  --device atoms3r \
  --unit 2relay \
  --base /path/to/atoms3r/uiflow2.bin \
  --qemu /path/to/qemu-system-xtensa \
  --execute
```

Use `--unit relay` for the single Relay path. Offline preparation is the
default; `--execute` requires a clean local Device Service on port `8787`.

## Boundaries

- This validates the same controller and Unit implementation path through a
  real UIFlow2 guest, but only one host/model combination is recorded for this
  issue closure.
- Transition counters are digital listener observations, not mechanical relay
  transitions, pulse widths or electrical contact state.
- Preview reset remains disabled. The result does not change relay/contact/load
  safety, physical hardware, RF or analog behavior.
