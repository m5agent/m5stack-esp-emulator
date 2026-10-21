# CardputerZero

- SKU：`C154`
- 分组：`Linux ARM64`
- 外壳：`掌上键盘机`
- 运行时：`backend-required`
- 外设仿真：`simulated`
- UIFlow2：`不支持`，m5ui：`不支持`
- UIFlow2 固件：不适用

## 硬件档案

| 项目 | 值 |
| --- | --- |
| SoC | RP3A0 (BCM2837) |
| 架构 | arm64 |
| Flash | 未确认 |
| PSRAM | 未确认 |
| 机身尺寸 | 84 × 54 × 23.1 mm |
| 重量 | 官方未确认 |
| 显示 | 320×170 lcd，1.9"，ST7789v3，无触摸 |
| 控制 | 46-key keyboard |
| 外设 | camera:imx219, imu:bmi270, magnetometer:bmm150, rtc:rx8130ce, audio:es8389, microphone:es8389, speaker:aw8737a, battery:bq27220, charger:ip2315, io-expander:m5ioe1, ethernet:ethernet-sr9900a, usb-host:usb-hub-gl852g, ir, storage:sd |

## 模拟状态

backend-required：UIFlow2 不适用，独立架构后端按外设状态单独验收。

- 验证：`linux-display-input-i2c-audio-power-usb-camera-pass` (2026-10-22)
- 详情：官方 CardputerZero ARM64 镜像以 512 MiB RAM 启动；ST7789v3 的 DRM/fb1 路径输出 320x170 RGB565 帧，QMP TCA8418 事件经 BCM GPIO27 中断进入 Linux input。TCA8418、M5IOE1、BMI270、BMM150、RX8130、BQ27220 和 ES8389 均绑定到 Linux 驱动；ES8389 I2C ID/状态、ALSA 播放 PCM、麦克风 PCM 逐字节回放和 AW8737A GPIO24 使能通过；IP2315 QOM 电源路径注入使 BQ27220/Linux status 从 Charging 切换为 Discharging；GL852G MTT 兼容路径同时完成 SR9900A Full-Speed 以太网帧回环和 Low-Speed HID 枚举/输入，r8152 创建 eth0；QMP GPIO13 波形经 Linux LIRC 收到 mode2 数据，GPIO12 NEC 发送边沿可抓取；IMX219 寄存器驱动 Unicam CSI1 完成 640x480 RG10 V4L2 实帧与 V4L2 控制项验证；官方 factory_test 的 LVGL 320x170 首帧通过 fb1 验证，54400/54400 个像素非黑、127 种 RGB565 颜色，画面哈希在 UI 启动后发生变化。

Raspberry Pi CM0/Linux, not an Espressif/UIFlow2 firmware target



## 文件

- `device.json`：设备中心与页面使用的完整档案
- `firmware.json`：UIFlow2 固件定位与缓存约定
- `index.html`：打开对应模拟页面
- `web/`：仅设备专属运行时使用
