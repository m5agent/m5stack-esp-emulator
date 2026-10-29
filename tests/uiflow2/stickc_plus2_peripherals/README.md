# StickC Plus2 peripheral probe

Use the exact official StickC Plus2 firmware through a dedicated Device Service
session. Compose `boot.py`, `main.py`, and `tests/uiflow2/lib/rtc_probe.py` as
`rtc_probe.py`. Keep the firmware's native UART0 console.

The probe reports the board ID and 135×240 display, writes and reads the real
PCF8563/BM8563 calendar registers on I2C1 SDA21/SCL22 at `0x51`, and requires
clock advancement after a guest delay. It then continuously calls `M5.update()`
and reports A/B/PWR transitions and the original MPU6886 accel/gyro API values.
Inject two distinct physical MPU6886 fixtures through `/machine/mpu6886` and
exercise each button with separate key-down/key-up requests in this same VM.

Collect serial, frames, QOM reads and the evidence ZIP before stopping with
`purge=0`. This probe establishes only its recorded virtual-device paths; it
does not establish battery ADC, microphone, buzzer, IR, sleep/wake, electrical
behavior or physical-hardware equivalence. Acceptance belongs to the current
status and validation ledger, not the existence of this probe.
