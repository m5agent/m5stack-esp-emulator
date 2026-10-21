# PaperColor power, RTC and keys

Exercises the PaperColor M5PM1 power path, RX8130 RTC over I2C, user key and
power key through the official UIFlow2 API. The matrix runner injects QOM
power values and QMP key events, then verifies serial markers and the
e-paper frame.
