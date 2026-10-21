# Cardputer-ADV BMI270 probe

Exercises the board BMI270 at I2C `0x69` through the official UIFlow2
`Imu.getAccel()` and `Imu.getGyro()` APIs. QEMU injects physical values into
the BMI270 sample registers before firmware boot.
