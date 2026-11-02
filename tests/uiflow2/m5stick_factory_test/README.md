# m5stick factory-test firmware

The M5Stick (K016) has no public UIFlow1/UIFlow2 build. Its only official
executable image is the FactoryTest binary embedded in the official Windows
EasyLoader installer:

- installer: `EasyLoader_M5Stick_FactoryTest.exe`
  - bytes `9463808`, SHA-256 `99c640b0ed51bd9670f544164f5542cb9c0303f1b6f84a4ee91e33e6c82e69f4`
- flash segment extracted from installer offset `0x527b41`, `0x571e0` bytes,
  written at flash `0x1000` (`7435e808…`)
- normalized 4 MiB image SHA-256
  `84228dfb6f0dd9b84b63c33f93a53545d8d43658893f432e3eaf4313923bffca`

```bash
python3 tests/uiflow2/m5stick_factory_test/extract_image.py
PYTHONPATH=platform/tools python3 tests/uiflow2/run_device_matrix.py \
  --device m5stick --flash-transport direct --out-dir /tmp/m5stick-matrix
```

The matrix case runs the image in deterministic icount mode and PASSes when the
native serial marker `mpu9250 addr:` appears. That marker means the factory
app reached its MPU probe and reported `0xFF`; it does not claim the factory
firmware's button/IMU data plane or a final OLED UI frame.
