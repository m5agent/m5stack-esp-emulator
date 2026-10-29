# StackChan Arduino 浏览器兼容性

浏览器执行上传的 ESP32-S3 完整 Flash，通过同一 guest 的 UART1 SCS 数据面
取得舵机实际位置，再映射到模型的左右和抬头关节。屏幕变化、目标位置变化和
实际舵机运动是三个独立观察，网页不会从触摸或目标位置生成机械动作。

## 已复现的 Dance 行为

对照固定官方 [StackChan-BSP e2f3b02d 的 Dance 示例](https://github.com/m5stack/StackChan-BSP/blob/e2f3b02dbe7f28e26a02adc72bef3aa2c545e4a0/examples/Servo/Dance/Dance.ino)：
顶部触摸触发 Dance，屏幕和目标值变化，但初始化后 torque 为 0，实际位置
保持不变。此结果只绑定该示例和 BSP 版本，不推定其它上传固件有相同问题。

在这一版本的示例 `setup()` 中，`M5StackChan.begin()` 后显式添加：

```cpp
M5StackChan.Motion.setAutoTorqueReleaseEnabled(false);
M5StackChan.Motion.setTorqueEnabled(true);
```

这是明确改变示例扭矩策略的对照版本。其余舞步、顶部 Si12T 触发与延时保留；
运动必须有同一 guest 的 `present_position` 和模型关节读回证据。屏幕触摸
FT6336U 与顶部 Si12T 是不同输入，点击屏幕不会替代顶部触摸。

## 网页状态

设备下方显示控制器读回的未供电、UART 未接通、舵机未使能或已使能状态。
UART1 内部接线为 TX6/RX7；错误接线不应操作舵机或得到有效返回。
连续转动模式的机械运动尚未模拟，模型俯仰显示范围为 0–90°；越界时保留
原始位置并给出提示。该位置模型不代表物理惯性、负载、碰撞或机械性能。

## NVS 与复位

16 MiB S3 Flash 使用的 ISSI 模型需要 3 字节 QIOR mode/dummy phase，
2/4/8 MiB Winbond/GigaDevice 使用 5 字节。旧 S3 桥接固定使用 5 字节，
会让 ISSI 读取偏移两个字节，出现配置写入成功但读回失败。修复按实际
Flash 模型配置相位，且不改变共享控制器上 CS1 PSRAM 的时序。

RESET 通过同一实例的 QMP `system_reset`，保留该实例的 Flash。停止会话后
重新创建、页面重载和跨次运行的 Flash 持久化仍是独立能力，不能从一次
同实例复位验证推导已经支持。准确新旧 runtime、固件及验证结果见验证台账。

独立 NVS 复现源码位于 `tests/firmware/stackchan_arduino_nvs/`，不链接
StackChan-BSP，也不替换 IDF 返回值。使用固定 PlatformIO 6.1.18：

```sh
pio run -d tests/firmware/stackchan_arduino_nvs
python3 tests/firmware/stackchan_arduino_nvs/merge.py \
  --boot-app0 "$PLATFORMIO_CORE_DIR/packages/framework-arduinoespressif32/tools/partitions/boot_app0.bin" \
  --output /tmp/stackchan-nvs-16mb.bin
```

`PLATFORMIO_CORE_DIR` 指向该构建实际使用的 PlatformIO core 目录。上传完整
16 MiB 镜像后，首次应出现 `readback rc=0 value=6885417`，同实例 RESET 后
应出现 `persisted_after_reset rc=0 value=6885417`，且无需再次写入。构建时间
等元数据可能改变镜像 SHA；每次运行必须记录实际 SHA，不能继承旧镜像结果。
