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
连续转动模式和仅指定速度的运动曲线尚未模拟，网页分别提示此限制，不能用其
动作时间判断真实舵机速度。模型俯仰显示范围为 0–90°；越界时保留
原始位置并给出提示。该位置模型不代表物理惯性、负载、碰撞或机械性能。

重复发送相同的扭矩值不应重新计时；新的目标、时间或速度命令仍从当前反馈
位置重新开始。官方 SCSCL 从 PWM 切回位置模式时，会分两次写回最小/最大
角度限位；模拟器允许这个临时中间态，但在区间无效时禁止运动。两项行为由
`0096` 控制器回归覆盖，实际固件和浏览器结果单独记在验证台账。

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


S3 软件 I²C 桥在硬控制器接管后，还需要随 GPIO RESET 清除协议与接管状态。
`0097` 恢复下次启动时 M5GFX 的实际 GPIO 探测，只结束桥自身事务、释放其自身
SDA 低电平，不重置端点寄存器或 NVS，也不覆盖独立输入源。复位的实际位置
边界应在 CPU 暂停时前后读回，再分开检查 BSP 初始化发出的真实 UART 命令；
SDK 的整数角度往返可能发出 1 tick 的位置调整，不能把它当成控制器丢位置。
