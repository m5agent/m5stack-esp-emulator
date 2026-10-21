# CoreS3 camera probe

Uses the official UIFlow2 `camera` module with `RGB565` and `QVGA`. The test
requires:

- GC0308 SCCB identity at I2C address `0x21`;
- ESP32-S3 LCD_CAM capture and DMA;
- a synthetic or captured frame returned by `camera.snapshot()`.

The QEMU board currently exposes the GC0308 identity. Full frame capture is
only reported as PASS if `camera.snapshot()` returns a 320x240 RGB565 image
and the result can be shown on the display. The probe also emits
`CORES3_CAMERA_PASS 320x240 153600 bytes`; the peripheral matrix requires that
UART marker, so a non-crashing firmware that still returns `None` cannot pass.

The LCD_CAM model raises independent VSYNC while DMA is idle and arms capture
on the GDMA `IN_LINK.START` write. This matches the esp32-camera startup order
(wait for VSYNC, then program the DMA link) and avoids a model/driver deadlock.
