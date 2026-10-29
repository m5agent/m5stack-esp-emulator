# Original AtomS3 (C123) peripheral probe

Use this source only with the original AtomS3 firmware and the `m5atoms3`
machine, not AtomS3R. The probe reads `M5.Imu.getAccel()` and `getGyro()` through
the firmware's MPU6886 driver, reports GPIO41 BtnA down/up with a guest counter,
and redraws the changed sample/button areas on the 128 x 128 display.

The original firmware's default `hardware.RGB()` returns `None`. The separate
`RGB(io=35, n=1, type="WS2812")` call exercises the schematic's GPIO35 path via
the official WS2812/RMT driver. It emits RGB `0x204060` at brightness 100; inspect
the captured RMT bytes independently of the serial announcement. This is not a
claim that the default AtomS3 RGB API or physical LED optics are supported.

Compose `boot.py` and `main.py` into a dedicated Device Service session. Inject
two different accel/gyro vectors into `/machine/mpu6886`, retain QOM readback,
serial and frames, then press and release A in the same session. Request the
evidence archive before stopping with `purge=0`. RGB and IMU errors are printed
as errors, never substituted with host-generated sensor values.

API references: official UIFlow2 `hardware/imu`, `hardware/button`,
`hardware/display`, and `hardware/rgb.py` at source commit
`64c3ce1346ceb4d404c1c3d74e66fed7eadb4d90`. The C123 v1.0 schematic names
WS2812 U3 `SK_DIN` GPIO35 and BtnA GPIO41. Execution status remains NOT RUN
until a matching session receipt is recorded.
