# M5StickT2

- SKU：`K016-T2`
- 分组：`ESP32 LX6`
- 外壳：`竖条棒状`
- 运行时：`candidate`
- 外设仿真：`partial`
- UIFlow2：`不支持`，m5ui：`不支持`
- UIFlow2 固件：不适用

## 硬件档案

| 项目 | 值 |
| --- | --- |
| SoC | ESP32-PICO-D4 |
| 架构 | xtensa-lx6 |
| Flash | 4 MB |
| PSRAM | 0 B |
| 机身尺寸 | 官方未确认 |
| 重量 | 官方未确认 |
| 显示 | 135×240 ips，1.14"，ST7789，无触摸 |
| 控制 | A, B, PWR, Rotary Encoder |
| 外设 | thermal:lepton, imu:mpu6886, rtc:bm8563, microphone:spm1423, battery:axp192, charger:axp192 |

## 模拟状态

candidate。

- 验证：`native-boot-thermal-vospi-panel-probe-pass` (2026-11-02)
- 本页只保留设备档案、验证状态和当前边界；逐项能力、运行流水与不可继承边界见 [项目当前状态](../../../docs/project-status.md)、[验证证据台账](../../../docs/validation-ledger.md) 和 [项目 Backlog](../../../docs/project-backlog.md)。
- 复现入口与 evidence 路径见 [代码与验证入口地图](../../../docs/code-map.md)。

## 未完成的板级数据面

- Thermal virtual-device data plane passed with the committed bare-metal probe: Lepton CCI commands/PID-free register path, deterministic VoSPI frames matching the host fixture oracle, ST7789 panel screenshot and encoder QOM injection. The official M5Burner StickT2 User Demo (SHA-256 bb33ffd4…) reaches its app boot marker under deterministic icount but its thermal/UI path is not reached and cannot be probe-injected; physical LWIR optics/thermal measurement, Grove Units, PDM microphone, encoder hardware and full factory UI remain open.

## 文件

- `device.json`：设备中心与页面使用的完整档案
- `firmware.json`：UIFlow2 固件定位与缓存约定
- `index.html`：打开对应模拟页面
- `web/`：仅设备专属运行时使用
