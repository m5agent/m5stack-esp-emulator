# CoreS3 camera probe

Uses the official UIFlow2 `camera` module with `RGB565` and `QVGA`. The test
requires:

- GC0308 SCCB identity at I2C address `0x21`;
- ESP32-S3 LCD_CAM capture and DMA;
- a synthetic or captured frame returned by `camera.snapshot()`.

The QEMU board currently exposes the GC0308 identity. Full frame capture is
only reported as PASS if `camera.snapshot()` returns a 320x240 RGB565 image
and the result can be shown on the CoreS3 display.
