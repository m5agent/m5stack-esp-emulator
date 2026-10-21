# Core2 MPU6886 probe

Uses the official UIFlow2 `Imu` API and QOM-injected MPU6886 accel/gyro values.
The guest accesses the chip through the ESP32 I2C0 controller and the
M5Unified MPU6886 driver.
