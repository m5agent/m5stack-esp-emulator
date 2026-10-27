# Arduino Nesso N1 BMI270 probe

Exercises the board BMI270 at I2C `0x68` through the official UIFlow2
`Imu.getAccel()` and `Imu.getGyro()` APIs. The QEMU model injects physical
accelerometer and gyroscope values through the chip-native sample registers;
the test does not replace or monkey-patch the UIFlow2 API.
