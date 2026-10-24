# StickS3 peripheral probe

Last reviewed: `2026-10-24`

Exercises the official UIFlow2 APIs for:

- `Imu.getType()`, `Imu.getAccel()`, `Imu.getGyro()`
- `Power.getBatteryLevel()`, `Power.getBatteryVoltage()`, `Power.isCharging()`
- `BtnA.wasPressed()`, `BtnB.wasPressed()`, `BtnPWR.wasPressed()`

The QEMU runner injects `A`, `B`, and `P` key events and changes the BMI270
QOM properties while the firmware is running.

Observed result:

- A/B/P buttons: PASS;
- battery percentage, voltage and charging state: PASS;
- BMI270 identity and enabled state: PASS;
- accelerometer values `0.250/-0.500/0.750` and gyroscope values
  `10/-20/30`: PASS through the UIFlow2 `Imu` API after QOM injection.
