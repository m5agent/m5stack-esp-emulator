# PaperMono GPIO PWM buzzer

Drives the documented BB_PWM buzzer on GPIO42 through the official
`Speaker.tone()` API. The ESP32-S3 LEDC controller records the channel duty in
QOM so the matrix runner can prove that firmware output reached the hardware
PWM peripheral rather than only updating a Python status flag.
