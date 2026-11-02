# AtomS3R-CAM

- SKU：`C126-CAM`
- 分组：`ESP32-S3`
- 外壳：`微型方块`
- 运行时：`candidate`
- 外设仿真：`partial`
- UIFlow2：`支持`，m5ui：`不支持`
- UIFlow2 固件：v2.5.4 / `1897200000000003117`

## 硬件档案

| 项目 | 值 |
| --- | --- |
| SoC | ESP32-S3-PICO-1-N8R8 |
| 架构 | xtensa-lx7 |
| Flash | 8 MB |
| PSRAM | 8 MB |
| 机身尺寸 | 24 × 24 × 14 mm |
| 重量 | 官方未确认 |
| 显示 | 128×128 ips，0.85"，GC9107，无触摸 |
| 控制 | USER |
| 外设 | imu:bmi270, magnetometer:bmm150, camera:gc0308, ir |

## 模拟状态

candidate。

- 验证：`native-boot-display-camera-frame-pass` (2026-11-02)
- 本页只保留设备档案、验证状态和当前边界；逐项能力、运行流水与不可继承边界见 [项目当前状态](../../../docs/project-status.md)、[验证证据台账](../../../docs/validation-ledger.md) 和 [项目 Backlog](../../../docs/project-backlog.md)。
- 复现入口与 evidence 路径见 [代码与验证入口地图](../../../docs/code-map.md)。

## 未完成的板级数据面

- Camera SCCB/DVP virtual-device path passed for the default QVGA frame only. Non-QVGA framesize geometry does not follow GC0308 window/subsample registers, multi-frame streaming is not tested, and IR GPIO47, Grove Units, USB CDC and physical optics/electrics remain open.

## 文件

- `device.json`：设备中心与页面使用的完整档案
- `firmware.json`：UIFlow2 固件定位与缓存约定
- `index.html`：打开对应模拟页面
- `web/`：仅设备专属运行时使用
