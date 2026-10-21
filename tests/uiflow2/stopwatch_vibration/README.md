# StopWatch vibration probe

Uses the official UIFlow2 `Power.setVibration()` API. M5Unified drives M5IOE1
PWM1, which controls the G9 vibration motor. QEMU reads back the PWM1 duty and
enable bits through the real M5IOE1 I2C register model.
