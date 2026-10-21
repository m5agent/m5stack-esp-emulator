# Arduino Nesso N1 buzzer probe

Diagnostic probe for the documented GPIO11 buzzer through the official
UIFlow2 `Speaker` API.

The probe checks that M5Unified reports an active tone and captures the
firmware-generated 1-bit delta-sigma stream from the real ESP32-C6 I2S TX and
GDMA descriptor path. Successful output must contain non-zero PCM samples; an
API-only `Speaker.isRunning()` result is not sufficient.
