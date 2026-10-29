# Dial device-local original-driver probe

This probe uses the exact official Dial UIFlow2 image and the original
`M5.Display`, `M5.Touch`, `M5.BtnA`, `hardware.Rotary`/RotaryIRQ and
`unit.RTC8563Unit` drivers. The RTC instance uses the documented internal
SDA11/SCL12 bus at address 0x51; `machine.RTC()` alone would measure the
SoC clock rather than establish external BM8563 transactions.

Compose with a fresh `probe_config.NONCE` and run through an owned Device
Service session. Match `M5EMU_DIAL` nonce/sequence events with that session's
firmware hash, frame, input and QOM state. Inject touch, `key:a` press/release,
and `/machine/encoder` `detents` both positive and negative; compare
`delivered-detents` and `gpio-edges` to the original guest Rotary count. Set
`/machine/pcf8563` `unix-time` and compare all seven RTC fields read by the
original driver. Save a frame after each input class and request evidence
before stopping with `purge=0`.

RFID WS1850S, buzzer and power/sleep are not covered. Source/API validation
and C algorithm controls do not grant a device functional or hardware PASS.

Official source evidence:

- [Dial](https://docs.m5stack.com/en/core/M5Dial)
- [Rotary wrapper](https://github.com/m5stack/uiflow-micropython/blob/64c3ce1346ceb4d404c1c3d74e66fed7eadb4d90/m5stack/libs/hardware/rotary.py)
- [RTC8563 driver](https://github.com/m5stack/uiflow-micropython/blob/64c3ce1346ceb4d404c1c3d74e66fed7eadb4d90/m5stack/libs/unit/rtc8563.py)
