# Tab5

- SKU：`C145 / K145`
- 分组：`ESP32-P4`
- 外壳：`平板终端`
- 运行时：`reference-ready`
- 外设仿真：`partial`
- UIFlow2：`支持`，m5ui：`支持`
- UIFlow2 固件：v2.5.3 / `1897200000000002379`

## 硬件档案

| 项目 | 值 |
| --- | --- |
| SoC | ESP32-P4NRW32 |
| 架构 | riscv32 |
| Flash | 16 MB |
| PSRAM | 32 MB |
| 机身尺寸 | 128 × 80 × 12 mm |
| 重量 | 120.9 g |
| 显示 | 1280×720 ips，5"，ST7121 / ST7123，触摸 |
| 控制 | Touch, Reset/Boot |
| 外设 | wireless:esp32c6-mini, camera:sc2356, imu:bmi270, rtc:rx8130ce, power-monitor:ina226, io-expander:pi4ioe5v6408, audio:es8388, microphone:es7210, speaker:es8388, usb-host:usb-host-p4-dwc, rs485, storage:sd, charger:ip2326 |

## 模拟状态

reference-ready：真实固件、画面和输入已打通。

- 验证：`display-touch-rs485-pass-peripherals-partial` (2026-10-22)
- 本页只保留设备档案、验证状态和当前边界；逐项能力、运行流水与不可继承边界见 [项目当前状态](../../../docs/project-status.md)、[验证证据台账](../../../docs/validation-ledger.md) 和 [项目 Backlog](../../../docs/project-backlog.md)。
- 复现入口与 evidence 路径见 [代码与验证入口地图](../../../docs/code-map.md)。

## 未完成的板级数据面

- SC2356 MIPI CSI-2 controller/frame path is absent from esp-emu 0.50.0
- ES8388/ES7210 I2S register and PCM endpoints are absent from esp-emu 0.50.0
- ESP32-P4 USB Host controller and endpoint attachment are absent
- ST7123 touch is currently a firmware GDB mailbox, not an I2C chip model
- Tab5 SDIO storage is not wired to a host block backend
- Tab5 PI4IOE CHG_STAT/CHG_EN and Power.isCharging() decode pass for charging and discharging, but IP2326 analog current/termination behavior and hot state injection remain partial; BMI270 identity, dynamic sensor values, GPIO side effects and interrupts also remain partial

## 文件

- `device.json`：设备中心与页面使用的完整档案
- `firmware.json`：UIFlow2 固件定位与缓存约定
- `index.html`：打开对应模拟页面
- `web/`：仅设备专属运行时使用

### 当前可用的部分

- 官方 UIFlow2 镜像可启动，真实 M5GFX 绘制路径输出 1280×720 帧；
- 触摸、RS-485、C6 ESP-Hosted 和静态 I2C 寄存器探测可用；
- 可通过真实 `esptool write-flash` 分块写入 16 MiB 虚拟 Flash，逐字节校验后从同一镜像启动。

2026-10-22 定向复测结果：

```text
FLASH PASS
BOOT PASS
TAB5_UI_DRAWN PASS
```

该复测只覆盖“虚拟烧录、启动和测试 UI 标记”，不覆盖下表未完成的动态外设。

### 虚拟烧录边界

Tab5 不是“完全不能用”，但也还不是可以无条件审查任意生产镜像的烧录器：

- 当前验证使用与仿真 ELF 匹配的 UIFlow2 镜像；
- 为避免 `esp-emu 0.50.0` P4 下载模式的高位地址回卷限制，仿真分区布局把
  `factory/sys/vfs/storage` 放在 8 MiB 以下；
- 任意生产固件在烧录前仍需确认 Flash 布局、ROM/eFuse、镜像长度和分区地址是否兼容。

完整待办和恢复条件见
[`docs/tab5-deferred-backlog.md`](../../../docs/tab5-deferred-backlog.md)。
