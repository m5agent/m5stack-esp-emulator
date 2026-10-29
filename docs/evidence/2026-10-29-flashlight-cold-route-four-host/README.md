# FlashLight cold-route four-host retest

Date: `2026-10-29`

Validation category: **virtual-device validation**

This record closes `UNIT-HOST-37` for the original UIFlow2 FlashLight
constructor and its cold low baseline. It covers CoreS3, AtomS3R, StickS3 and
StopWatch in one fixed runtime, using the original `FlashLightUnit` source
path. Dynamic S1 modes, PWM/OEN/IOMUX breadth, photometry, electrical and
physical-hardware behavior remain separate.

## Runtime and firmware

- QEMU SHA256:
  `e318b2b748d6e982cd2e592a1b991ec930a8e9501cf02a0c19925022a656b373`
- CoreS3 firmware:
  `0ede40601c1e37b7ba32c87a3ca55e4da7a448f6cf52957f005763bc7c7c78e8`
- AtomS3R firmware:
  `0c70da2a56102dc812f380ac24fcb0a75bd3cb0c70e5380d97c11baeca935323`
- StickS3 firmware:
  `93a547011be37a2b5f062ad7a56da108a95600119d360481adef10c634ed8d76`
- StopWatch firmware:
  `869f8a192cbc0392c8905cf69cfa7244482e97221cce977a04e9dc191f46ff21`

## Guest path

`tests/units/run_flashlight_route_probe.py` creates one visible QEMU session
per host with `program_mode=uiflow-live`, attaches U152 with
`initial={"flash-mode": true}`, and runs three replacement programs in the
same PID:

1. original `FlashLightUnit((white, yellow))` constructor with no prior high
   edge;
2. original `flash(BRIGHTNESS_100, TIME_220MS, False)`;
3. original `flash(0, TIME_220MS, True)`.

For every host, the first state was trusted `ready-low` with
`output-known=true`, route/pad synchronization and zero decoded programs.
After the original API call, the model observed one rising edge and decoded
`100% / 220ms`; after the off run it returned to trusted `ready-low`.
All three executions used the same guest PID and no reboot banner appeared.

## Mounted Web consumer

`platform/tests/test_flashlight_unit_web.mjs` now accepts
`M5_FLASHLIGHT_REAL_STATE` and replays the actual initial/active/off QOM
properties through the mounted Unit panel. CoreS3 produced:

```text
real-state-replay=ACTUAL-QOM-SNAPSHOT
```

This verifies the mounted model consumer against actual same-session controller
state. It is a state-snapshot replay, not a live browser polling session; that
live refresh remains `NOT RUN`.

## Evidence hashes

| Host | Pins white/yellow | Evidence ZIP SHA256 |
| --- | --- | --- |
| CoreS3 | `1/2` | `23b10c5f0d29fe24dfb209bb66705d752a255f2ed8ac08ccab7f47ee495d63a7` |
| AtomS3R | `1/2` | `3e30a3003d7d362d438191596b79a00117ee63792acc3f99a3d9a4277bffd757` |
| StickS3 | `10/9` | `ca96473cbe07a718d9f389e8d690cf08deec24036b4add32e46bed0e39e669a7` |
| StopWatch | `11/10` | `5f7ec5b1484e3fbd85b69a99c7e7376ccfcb6535af155e59b4eea545c46b32e9` |

Web replay output SHA256:
`117340a1d0167f0d805fe824c5e1c4982107dfd7cea473b24474192a74c28cfa`.

Final repository regression: platform `1559 tests OK, 10 skipped`;
runtime coverage, peripheral catalog, QEMU profiles and generated project
snapshot checks PASS. The mounted Web test passes both its baseline synthetic
fixture lane and the actual-QOM snapshot replay.

## Boundaries

- Flash percentage is a relative digital code, not photometric output.
- The model does not prove the exact fast pulse encoding is bit-exact on silicon.
- Dynamic S1 changes, EN PWM, full OEN/IOMUX, optical, thermal, current,
  electrical and physical hardware are `NOT RUN`.
- Live mounted Web polling against an active session is `NOT RUN`; the verified
  path replays actual QOM snapshots through the real mounted consumer.
