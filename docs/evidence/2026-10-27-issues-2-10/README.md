# 2026-10-27 GitHub issues #2–#10 顺序复测

本次复测基于主线 `8a0d99a03e3205564011bb123e0ee981587bebe7` 上的干净
QEMU 源码栈重新冷构建，并只通过可见 Device Service `/api/v1` session
执行。结果是 `virtual-device validation`；物理硬件验证为 `NOT RUN`。

## 运行时

- 14 个固定 patch、109 个 source 文件；
- `qemu-system-xtensa` SHA256：
  `9aca9a8db5143ad133510795cd228ed8ac23c388ea197267d7b2b4750e58eb82`；
- source receipt SHA256：
  `1219a45d8ad495509e01088f87af5fe7e41719bb4661e6e60afc42fdce035b26`；
- 最后一个控制器 patch：
  `patches/qemu-m5stack-peripherals/0048-unit-servos8-joystick2-nfc.patch`，
  SHA256 `bda0038c4239fb2d21c8d17f30bc2107cfb977f8d8a9e5a6ed3fc58aa304f7fe`。

每个功能 session 都在停止前请求 evidence ZIP，随后以 `purge=0` 停止并保留
历史。`summary.json` 保存可公开的固件、runtime、串口标记、QOM/数据面值、
帧和 evidence ZIP 哈希；原始 ZIP 不随源码分支提交。

完整平台套件为 `1241` 项 `PASS`、`1 skipped`；runtime coverage、peripheral
catalog、QEMU profiles、project snapshot、Unit runtime/ADC/controller 定向
测试、四个 Unit Node 契约以及 bootstrap source receipt 检查均通过。`0048`
对最终冷构建源码执行 reverse apply 也通过。完整 UIFlow2 外设矩阵在本轮
`NOT RUN`。

## 结果

| Issue | 复测结论 | 关键证据 |
| --- | --- | --- |
| [#2](https://github.com/m5agent/m5stack-esp-emulator/issues/2) | 仍为 `OPEN`；四个 Core2 app 的共同路径仍出现 WDT/reset，未到 `ISSUE2_DONE`，帧仍为 302-byte 纯黑 | session `ae3d913d352248a7b03419082736a349`，firmware `2b1cb7d5…`，frame/evidence SHA 见 JSON |
| [#3](https://github.com/m5agent/m5stack-esp-emulator/issues/3) | 仍为 `OPEN`；`core2-openmac` 下仍出现 WDT/reset，未到 `ISSUE3_DONE`，帧仍为 302-byte 纯黑 | session `2d59cedb0bc746d79bacaec64832d47a`，firmware `591dfd5e…`，network proof `PARTIAL` |
| [#4](https://github.com/m5agent/m5stack-esp-emulator/issues/4) | 已由合入主线的前置修复解决：ENV III 返回 `23.5 C / 47.0 % / 1002.5 hPa`，QOM 记录 22 次事务、46 read bytes、15 written bytes | session `87104dffe4854012b54136318c916409` |
| [#5](https://github.com/m5agent/m5stack-esp-emulator/issues/5) | 已修复：Hat2-Bus scan 为 `[54]`，Servos8Hat 角度 90、power 1 | session `afde8580679649f4956a990f1a387f1f` |
| [#6](https://github.com/m5agent/m5stack-esp-emulator/issues/6) | 已修复：Port A scan `[64]`、Port B scan `[37]`，8Servos mode 3、angle 90 | session `97e3ec05059547bb90092a18f0bf8332` |
| [#7](https://github.com/m5agent/m5stack-esp-emulator/issues/7) | 已修复：scan `[99, 100]`，A `(0,0)`，B `(1200,-800)`、button `True` | session `aeddd9b4f67345909174da28769b3f8a` |
| [#8](https://github.com/m5agent/m5stack-esp-emulator/issues/8) | 已修复：scan `[80]`，`NFCUnit` 构造和 `detect()` 成功，UID `DEADBEEF` | session `a4f65ddd7ade49c2ba464e4382ebd142` |
| [#9](https://github.com/m5agent/m5stack-esp-emulator/issues/9) | 已修复：Cardputer-ADV app-bound synthetic ADC calibration 写入 session eFuse；无 calibration/fatal error，UI 达到 running/nonblank | session `087fc3390f5949ceb83de0551d7f8b14` |
| [#10](https://github.com/m5agent/m5stack-esp-emulator/issues/10) | 启动阻塞已修复：同一 `Canvas`/`MatrixKeyboard`/GPIO0/`Speaker`/IMU setup 路径完成并有 `ALL SETUP OK` 绿帧 | session `099513ad37cf495eb0a6d921ae21ceb3` |

## Issue #4–#8 的精确 guest 程序

程序通过 Device Service program execution 在已经运行的同一 guest UART
REPL 中执行；源码哈希和结果都记录在 `summary.json`。

```python
# #4: source sha256 f9fd8eaa6dfb09b251fcc5fcd58a1cf61b43686af101d3bc7a3787c1df333d4a
bus = I2C(0, scl=Pin(10), sda=Pin(9), freq=100000)
env = ENVUnit(i2c=bus, type=3)
print(env.read_temperature(), env.read_humidity(), env.read_pressure())
```

```python
# #5: source sha256 4c7694cddfca505d4081c8a7d3fbe282422f4c58cc1723e62a65fea156a26b85
i2c0 = I2C(0, scl=Pin(0), sda=Pin(8), freq=100000)
servo = Servos8Hat(i2c0, 0x36)
servo.power_on()
servo.write_servo_angle(1, 90)
print(i2c0.scan(), servo.read_servo_angle(1), servo.get_power_state())
```

```python
# #6: source sha256 fd160bae63b176a7784aef29d7a4b95cdb77d8b9763a9d1fed69610debcb9b0b
enc_i2c = I2C(0, scl=Pin(1), sda=Pin(2), freq=100000)
srv_i2c = I2C(1, scl=Pin(8), sda=Pin(9), freq=100000)
servos = Servos8Unit(srv_i2c, 0x25)
servos.set_mode(3, 0)
servos.set_servo_angle(90, 0)
print(enc_i2c.scan(), srv_i2c.scan(), servos.get_servo_angle(0))
```

```python
# #7: source sha256 68b452117b96858287aedc95bb4faa821a27afd35dbc9653ee1472dac2b1da3f
i2c0 = I2C(0, scl=Pin(1), sda=Pin(2), freq=100000)
a = Joystick2Unit(i2c0, 0x63)
b = Joystick2Unit(i2c0, 0x64)
print(i2c0.scan(), a.get_axis_position(), b.get_axis_position(), b.get_button_status())
```

```python
# #8: source sha256 eb6a51958763d8336e954dfe168d640bb960e7deac164a6d391606c296ed585d
i2c0 = I2C(0, scl=Pin(1), sda=Pin(2), freq=400000)
nfc = NFCUnit(i2c0)
card = nfc.detect()
print(i2c0.scan(), card.uid_str if card else "none")
```

## 修复范围

- `0048-unit-servos8-joystick2-nfc.patch` 增加 StickS3
  `servo8-hat@0x36`、CoreS3 `8servos@0x25`、Joystick2 `0x63`/`0x64`
  和 ST25R3916 NFC `0x50` 的 guest 可见 I2C 路径；
- Cardputer-ADV 只对匹配参考应用 segment 的 UIFlow2 镜像应用 17 个白名单
  ADC calibration/version eFuse 字段，并在 evidence 中写入
  `units/adc-calibration.json`；
- `#4` 在当前主线已经由既有 ENV III 模型解决，本轮没有重复修改其控制器。

## 验证边界

- 物理硬件：`NOT RUN`；
- 舵机机械运动、电流和电源切换：`NOT RUN`；
- Joystick2 机械行程、中心/方向标定：`NOT RUN`；
- NFC RF、天线、范围和真实卡片：`NOT RUN`；
- Cardputer ADC 精度、电池电气特性和生产校准：`NOT RUN`；
- `#10` 验证的是原 issue 中完整 setup 路径及首个成功画面，不是逐帧 Tetris
  游戏逻辑；原始 Tetris 完整源码不在可取得的归档中；
- `#2`/#3 未解决，因此保持 open，不把相关 WDT/黑帧转记为通过。

详细值、哈希和每个 issue 的停止状态见 [summary.json](summary.json)。
