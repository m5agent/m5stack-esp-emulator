# m5stick model fixture

`m5stick` (K016) has no official UIFlow1/UIFlow2 firmware, so this fixture runs
the generic classic-ESP32 UIFlow2 **Atom Lite** image only as a transport for a
device-model probe on the `m5stick` QEMU machine. It is not the M5Stick factory
firmware and does not claim UIFlow2 support for this board.

What it exercises through real guest controllers:

- shared G21/G22 I2C bus scan (`0x48` QEMU tmp105 convenience device, `0x68`
  MPU9250, `0x75` IP5306);
- MPU9250 `WHO_AM_I` (`0x71`) and the big-endian accel frame, plus a live
  `qom-set /machine/mpu9250 accel-x 2.0` fixture read back as raw `8192`;
- IP5306 register reads (`SYS_CTL0` reset `0xbe`, `READ4` `0xff` = no cell);
- GPIO35 custom button: `qmp input-send-event` drives the panel input handler
  and the guest reports both the pressed (`0`) and released (`1`) states.

The factory-firmware lane is separate: `m5stick_factory_test/extract_image.py`
builds the pinned EasyLoader image, and the device matrix `firmware` case only
asserts the native serial marker `mpu9250 addr:` before the firmware stalls.
