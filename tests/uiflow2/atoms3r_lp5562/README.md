# AtomS3R LP5562 RGB probe

Exercises the LP5562 I2C RGB controller at address `0x30` on AtomS3R. The test
enables the chip, writes independent R/G/B PWM registers and verifies the
readback through the real I2C bus.
