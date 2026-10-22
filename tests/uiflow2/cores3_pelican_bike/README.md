# CoreS3 pelican bicycle animation

Runs a full-screen 320 x 240 M5GFX Canvas animation from CoreS3's official
UIFlow2 firmware in QEMU. The scene exercises text, rectangles, rounded
rectangles, lines, circles, ellipses, triangles, reusable off-screen Canvas,
single `push()` presentation, FT6336 touch detail and BMI270 accel/gyro.

CoreS3's panel uses `offset_rotation=3`; rotation `1` is the landscape
320 x 240 orientation. Using rotation `0` leaves the logical drawing width at
240 pixels and clips the right side of the frame.

Controls:

- drag across the road to select speed 0-4;
- hold the pelican to play a deterministic PCM bell through CoreS3 `Speaker`:
  1000 Hz for 50 ms, 10 ms silence, then 800 Hz for 60 ms;
- tap the dark button in the upper-right corner to pause or resume.

BMI270 X tilt shifts the rider and bicycle, Y tilt adds vertical motion, and
gyro Z strengthens the scarf and speed-line effect. The bottom status strip
shows the filtered `Imu.getAccel()/getGyro()` values.

Run the interaction scenario:

```bash
M5SW_I2S_DMA_IRQ=1 \
M5SW_I2S_PCM_FILE=/tmp/m5-cores3-pelican/speaker.pcm \
PYTHONPATH=.work/py python3 tests/uiflow2/run_profile_ui_test.py \
  --base platform/.cache/firmware/cores3/uiflow2.bin \
  --machine m5cores3 \
  --files-dir tests/uiflow2/cores3_pelican_bike \
  --vfs-offset 0xAA0000 --vfs-size 0x4C0000 --flash-size 0x1000000 \
  --expected-size 320x240 \
  --qom-set /machine/bmi270 accel-x 0.65 \
  --qom-set /machine/bmi270 accel-y -0.25 \
  --qom-set /machine/bmi270 accel-z 0.75 \
  --qom-set /machine/bmi270 gyro-z 35 \
  --input drag:45,220,285,220 \
  --input longpress:170,130,0.9 \
  --input touch:280,25 \
  --capture-frames 18 --capture-interval 0.1 --capture-each-input \
  --out-dir /tmp/m5-cores3-pelican
```

Validate the captured CoreS3 I2S output:

```bash
python3 tests/uiflow2/check_pcm.py \
  /tmp/m5-cores3-pelican/speaker.pcm \
  --min-nonzero 1000 --min-peak-to-peak 1000
```

The corrected 48 kHz capture produced `32768` bytes / `16384` samples,
`5277` nonzero samples and peak-to-peak `4476`. The first 50 ms contains about
99 sign transitions (1000 Hz); the remaining active region contains about 97
(800 Hz plus the short gap).

The runner defaults to the rebuilt QEMU at
`.work/M5StopWatch-QEMU/build/qemu/build/qemu-system-xtensa`. Do not use the
older `bin/Darwin-arm64/qemu-system-xtensa`: it predates the ESP32-S3 I2C FIFO
and repeated-start fixes, so CoreS3's BMI270 remains at zero after soft reset.

The animation is a simulator demonstration. It does not replace validation on
physical CoreS3 hardware. The PCM proves the firmware-driven I2S digital path;
it does not prove physical speaker sound pressure or the final acoustic timbre.
