# CoreS3 peripheral probe

Exercises the official UIFlow2 APIs for:

- `Imu.getType()`, `Imu.getAccel()`, `Imu.getGyro()`, `Imu.getMag()`
- `Power.getBatteryLevel()`, `Power.getBatteryVoltage()`, `Power.isCharging()`
- `BtnPWR.wasPressed()` and touch input

The QEMU runner changes BMI270 QOM properties during runtime and injects a
power-key event plus a touch.

Observed result:

- touch and PWR: PASS;
- AXP2101 battery/charging telemetry: PASS;
- PCF8563 RTC: PASS;
- BMI270 values: PARTIAL;
- BMM150 magnetometer: FAIL, returns an untrusted all-zero vector.
