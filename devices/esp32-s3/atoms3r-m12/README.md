# AtomS3R-M12

- SKU：`C126-M12`
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
| 机身尺寸 | 官方未确认 |
| 重量 | 官方未确认 |
| 显示 | 128×128 ips，0.85"，GC9107，无触摸 |
| 控制 | USER |
| 外设 | imu:bmi270, magnetometer:bmm150, camera:ov3660, ir |

## 模拟状态

candidate。

- 验证：`native-boot-display-camera-geometry-stream-pass` (2026-11-02)
- 本页只保留设备档案、验证状态和当前边界；逐项能力、运行流水与不可继承边界见 [项目当前状态](../../../docs/project-status.md)、[验证证据台账](../../../docs/validation-ledger.md) 和 [项目 Backlog](../../../docs/project-backlog.md)。
- 复现入口与 evidence 路径见 [代码与验证入口地图](../../../docs/code-map.md)。

## 未完成的板级数据面

- Camera virtual-device path passed on the shared official UIFlow2 image (M5Burner entry declares AtomS3R-CAM and AtomS3R-M12 support): OV3660 detected at 0x3c, QQVGA/QVGA/VGA/HD frames match the reconstructed DVP waveform and five QQVGA streamed frames are distinct. There is no M12-specific UIFlow2 entry; the community MJPEG/UVC demo frame path, physical optics/electrics, IR GPIO47, Grove Units and USB CDC remain open.

## 文件

- `device.json`：设备中心与页面使用的完整档案
- `firmware.json`：UIFlow2 固件定位与缓存约定
- `index.html`：打开对应模拟页面
- `web/`：仅设备专属运行时使用
