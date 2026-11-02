# M5Stick

- SKU：`K016`
- 分组：`ESP32 LX6`
- 外壳：`竖条棒状`
- 运行时：`candidate`
- 外设仿真：`partial`
- UIFlow2：`不支持`，m5ui：`不支持`
- UIFlow2 固件：不适用

## 硬件档案

| 项目 | 值 |
| --- | --- |
| SoC | ESP32-WROOM32 |
| 架构 | xtensa-lx6 |
| Flash | 4 MB |
| PSRAM | 0 B |
| 机身尺寸 | 48.2 × 25.5 × 13.7 mm |
| 重量 | 14 g |
| 显示 | 64×128 oled，1.3"，SH1107，无触摸 |
| 控制 | A, PWR |
| 外设 | imu:mpu9250, ir, buzzer, led-output:gpio19, battery:ip5306, charger:ip5306 |

## 模拟状态

candidate。

- 验证：`native-factory-boot-oled-probe-blocked` (2026-11-02)
- 本页只保留设备档案、验证状态和当前边界；逐项能力、运行流水与不可继承边界见 [项目当前状态](../../../docs/project-status.md)、[验证证据台账](../../../docs/validation-ledger.md) 和 [项目 Backlog](../../../docs/project-backlog.md)。
- 复现入口与 evidence 路径见 [代码与验证入口地图](../../../docs/code-map.md)。

## 未完成的板级数据面

- 工厂固件的 I2C 传输未在 classic I2C 控制器模型上完成（legacy ESP-IDF FIFO 数据写入路径未到达模型），因此原厂 MPU9250 探测输出 0xFF，工厂固件的按键/九轴数据面未通过；MPU9250 模型数据面只由 generic MicroPython fixture 取证。AK8963 磁力计、DMP、SH1107 最终 UI 帧、黑/灰修订区分、蜂鸣器/IR/LED、Grove Unit 与物理声学/光学/电气行为未验证。

## 文件

- `device.json`：设备中心与页面使用的完整档案
- `firmware.json`：UIFlow2 固件定位与缓存约定
- `index.html`：打开对应模拟页面
- `web/`：仅设备专属运行时使用
