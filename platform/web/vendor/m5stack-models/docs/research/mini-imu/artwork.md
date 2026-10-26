# U095 Mini IMU artwork

This model includes three newly drawn raster labels from exact U095 official photographs. They contain newly drawn text and shapes, without photographic pixels or cropped labels:

| Asset | Physical placement | Source |
| --- | --- | --- |
| `reference-redraw-front.png` | 18 × 4 mm, front recessed label, centered (0, 7.1, 3.8) mm | `imu_08.webp`, corroborated by `imu_09.webp` |
| `reference-redraw-axes.png` | 6 × 6 mm, front axis circle, centered (0, 0, 4) mm | `imu_08.webp`, corroborated by `imu_09.webp` |
| `reference-redraw-back.png` | 16.4 × 4.5 mm, rear recessed pinout label, centered (0, 7.1, −3.8) mm | `imu_02.webp` |

Official source base: `https://static-cdn.m5stack.com/resource/docs/products/unit/imu/`. `artwork.json` records exact URLs, source hashes, final PNG hashes and registration.

Front text is **IMU / MPU6886**. The circular label shows red X right, olive Y up and blue Z at the origin. The rear label shows **PORT.A / I2C** and, in rear-view left-to-right order, **SCL / SDA / 5V / GND** with white/yellow/red/black blocks. No extra address, component stamp, button, status label or variant is invented.

Colours, letterforms and physical label size/position are reconstructed from photographs and native recesses; these PNGs are not original production print files. All three use `artworkKind: 'reference-redraw'`. The projection follows existing shell surfaces and leaves holes intact; `artwork:false` disables all three without changing the physical geometry or component state. No separate known sticker face remains omitted in the checked U095 product photos. M5Stack designs and marks retain their respective rights.
