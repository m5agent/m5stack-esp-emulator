# PaperDIY

- SKU：`K159-B`
- 分组：`ESP32-S3`
- 外壳：`电子纸`
- 运行时：`boot-capable`
- 外设仿真：`partial`
- UIFlow2：`支持`，m5ui：`不支持`
- UIFlow2 固件：v2.5.4 / `2110563172188712962`

## 硬件档案

| 项目 | 值 |
| --- | --- |
| SoC | ESP32-S3-WROOM-1-N16R8 |
| 架构 | xtensa-lx7 |
| Flash | 16 MB |
| PSRAM | 8 MB |
| 机身尺寸 | 68.2 × 120 × 6.3 mm |
| 重量 | 43.1 g |
| 显示 | 540×960 e-paper，4.7"，ET047TC1，无触摸 |
| 控制 | A, B, PWR |
| 外设 | battery:m5pm1, charger:m5pm1, storage:sd |

## 模拟状态

boot-capable：对应 QEMU 后端可启动固件并查看串口，板级显示/外设仍在收口。

- 验证：`native-et047tc1-buttons-pass` (2026-11-09)
- 本页只保留设备档案、验证状态和当前边界；逐项能力、运行流水与不可继承边界见 [项目当前状态](../../../docs/project-status.md)、[验证证据台账](../../../docs/validation-ledger.md) 和 [项目 Backlog](../../../docs/project-backlog.md)。
- 复现入口与 evidence 路径见 [代码与验证入口地图](../../../docs/code-map.md)。

## 未完成的板级数据面

- Factory display reaches PM1 power-enable and reads 4000 mV; independent charging, IRQ and wake-source injection were not exercised.
- The factory PM1 shutdown command exits the guest; independent power-key, standby and restart behavior were not validated.
- The factory demo reaches the empty-slot SPI path; a mounted image, card-detect transitions and sector transfers were not validated.

## 文件

- `device.json`：设备中心与页面使用的完整档案
- `firmware.json`：UIFlow2 固件定位与缓存约定
- `index.html`：打开对应模拟页面
- `web/`：仅设备专属运行时使用
