# StickS3 peripheral probe

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
- accelerometer/gyroscope values: PARTIAL, still zero after QOM injection.
