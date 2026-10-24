<!-- GENERATED FILE: run `python3 platform/tools/project_snapshot.py --write` -->

# 项目快照（自动生成）

来源日期：`2026-10-24`；最新 evidence 日期：`2026-10-24`。

本页只汇总机器可读源和已提交 evidence，避免在多个文档手写同一组动态事实。实现结论、风险说明和验证层级仍以[项目当前状态](project-status.md)、[验证证据台账](validation-ledger.md)和 [项目 Backlog](project-backlog.md) 为准。

## 设备与后端

- 设备登记：`14` 台；Device Service 可创建：`13` 台。
- 设备分组：`esp32-c6` 2，`esp32-lx6` 1，`esp32-p4` 1，`esp32-s3` 9，`linux-arm64` 1。
- 外设状态：`partial` 1，`simulated` 13。

| 设备 | SoC | 后端 | 外设 | 最近验证 | 当前边界 |
| --- | --- | --- | --- | --- | --- |
| StopWatch (`stopwatch`) | ESP32-S3R8 | `qemu-esp32s3` | `simulated` | `2026-10-23` / `display-touch-peripherals-wifi-ble-pass` | 无登记 blocker |
| AtomS3R (`atoms3r`) | ESP32-S3-PICO-1-N8R8 | `qemu-esp32s3` | `simulated` | `2026-10-23` / `display-input-peripherals-wifi-ble-pass` | 无登记 blocker |
| CoreS3 (`cores3`) | ESP32-S3 | `qemu-esp32s3` | `simulated` | `2026-10-23` / `display-touch-peripherals-wifi-ble-pass` | UIFlow startup-menu palette PNG/tRNS assets render striped artifacts; ordinary RGB PNG and opaque drawing paths are correct |
| StickS3 (`sticks3`) | ESP32-S3-PICO-1-N8R8 | `qemu-esp32s3` | `simulated` | `2026-10-23` / `display-input-peripherals-wifi-ble-pass` | 无登记 blocker |
| Cardputer-ADV (`cardputer-adv`) | ESP32-S3FN8 | `qemu-esp32s3` | `simulated` | `2026-10-23` / `display-keyboard-peripherals-wifi-ble-pass` | 无登记 blocker |
| StackChan (`stackchan`) | ESP32-S3 | `qemu-esp32s3` | `simulated` | `2026-10-23` / `display-input-peripherals-wifi-ble-pass` | 无登记 blocker |
| StamPLC (`stamplc`) | ESP32-S3FN8 | `qemu-esp32s3` | `simulated` | `2026-10-23` / `display-input-peripherals-wifi-ble-pass` | 无登记 blocker |
| PaperColor (`papercolor`) | ESP32-S3R8 | `qemu-esp32s3` | `simulated` | `2026-10-23` / `display-input-peripherals-wifi-ble-pass` | 无登记 blocker |
| PaperMono (`papermono`) | ESP32-S3R8 | `qemu-esp32s3` | `simulated` | `2026-10-23` / `display-touch-peripherals-wifi-ble-pass` | 无登记 blocker |
| NanoC6 (`nanoc6`) | ESP32-C6FH4 | `qemu-esp32c6` | `simulated` | `2026-10-24` / `board-peripherals-wifi-ble-pass` | Zigbee/802.15.4 controller data plane is not modeled (RUNTIME-02) |
| Arduino Nesso N1 (`nesso-n1`) | ESP32-C6 | `qemu-esp32c6` | `simulated` | `2026-10-24` / `display-touch-peripherals-wifi-ble-pass` | Meshtastic remains PARTIAL after an independent post-application instruction access fault (RUNTIME-01 flash/PMP defect is fixed) |
| CardputerZero (`cardputer-zero`) | RP3A0 (BCM2837) | `external-linux-arm64` | `simulated` | `2026-10-22` / `linux-display-input-i2c-audio-power-usb-camera-partial` | not an ESP32 firmware target |
| Core2 (`core2`) | ESP32-D0WDQ6-V3 | `qemu-esp32lx6` | `simulated` | `2026-10-24` / `display-input-peripherals-wifi-ble-pass` | physical cache/PSRAM timing equivalence remains NOT RUN; bit-exact ESP32 BT baseband/controller remains NOT RUN; more than one hundred twenty reconnect cycles and an artifact-bound two-hour coexistence/soak remain NOT RUN |
| Tab5 (`tab5`) | ESP32-P4NRW32 | `esp-emulator-native` | `partial` | `2026-10-22` / `display-touch-rs485-pass-peripherals-partial` | SC2356 MIPI CSI-2 controller/frame path missing from esp-emu 0.50.0; ES8388/ES7210 I2S register and PCM endpoints missing from esp-emu 0.50.0; ESP32-P4 USB Host controller and endpoint attachment missing; Tab5 ST7123 touch is currently a firmware GDB mailbox rather than an I2C chip model; Tab5 SDIO storage is not wired to a host block backend; Tab5 INA226 register preload reaches Power as 8000 mV/1248 mA/87%, direct machine.I2C write/read reaches RX8130 registers, and PI4IOE CHG_STAT/CHG_EN reach Power.isCharging() in both charging and discharging scenarios, but RTC progression, dynamic I2C/time injection and IP2326 analog current/termination behavior remain partial; BMI270 identity also remains partial |

## 通用固件审查

公开样本快照覆盖 `7` 台设备、`21` 个固件：`10` PASS、`11` PARTIAL、`0` FAIL。PARTIAL 不自动等于固件缺陷；`runtime_model_gap` 必须保留模型边界。

## 运行时模型缺口

| ID | 状态 | 缺口 |
| --- | --- | --- |
| `RUNTIME-01` | `FIXED` | C6 软件复位后 chip-id 错误 |
| `RUNTIME-02` | `OPEN` | C6 Zigbee/802.15.4 运行时未建模 |
| `RUNTIME-03` | `OPEN` | Core2 legacy I2C controller/board-bus routing 未闭环 |
| `RUNTIME-04` | `OPEN` | Core2 for AWS ATECC608 未建模 |

## Backlog Task 板

| Task | 当前状态 | 下一项最小交付 |
| --- | --- | --- |
| `NET-04` | 进行中 | 自动主机发现/跨主机 worker 迁移、跨主机 QEMU executor/reattach、companion/evidence continuity、生产调度 |
| `CORE2-02` | 进行中 | 3 个独立 lease 各 20/30/60/120 轮、`5×10s`、`3×60s`、`2×120s`、active-BLE `600s` 和一次未绑定资产的 `7200s` 行为诊断已通过；新的 artifact-bound `7200s` soak 正在运行，reconnect 上限为 `1–120`，hold 上限为 `7200s`。完成后再做超过一百二十轮、coexistence 和 teardown |
| `FW-01` | 进行中 | 运行时权限、完整源码级许可扫描与法律审批 |
| `FW-02` | 进行中 | 真机 secure boot、Flash Encryption、eFuse 和生产 key 流程 |
| `FW-03` | 进行中 | 已有 7 台设备、21 个公开非基线样本；扩到更多设备与 firmware family |
| `RUNTIME-02` | 进行中（backend blocked） | esp-emu `--thread-sim` 已观察到双向 802.15.4 帧，但 commissioning/join 未完成；补 MAC ACK/commissioning 语义或取得公开固件匹配 ELF |
| `RUNTIME-03` | 进行中 | 对齐 Core2 legacy I2C controller port、SCL/SDA pin 与板级 bus；确认 `disable_timer_interrupt()` 的 BM8563 RTC 路径 |
| `RUNTIME-04` | 进行中 | 为 Core2 for AWS 提供 ATECC608 测试 slot/config fixture |
| `SVC-01` | 进行中 | companion/evidence continuity、worker 主机自动发现与跨主机 reattach |
| `SVC-02` | 待做 | warm pool、队列、配额、对象存储和审计 |
| `SVC-03` | 待做 | 拆分 `device_service.py` 的存储、runtime、evidence 和 session 状态机 |
| `HW-01` | 待做 | 代表设备同固件 SHA 的真机测试计划 |
| `TAB5-01` | 决策 | 重建或扩展 P4 backend |
| `UI-01` | 待做 | 逐设备高保真外壳、hitbox 和截图阈值 |
| `CZ-01` | 待做 | CardputerZero 系统、驱动和长期回归 |

## 文档与测试

- 平台测试：`336` 项。
- Docs 新鲜度登记：`32` 行。
- 代码边界和大型模块的维护建议由[代码与验证入口地图](code-map.md)维护。

## 维护入口

- 当前能力、风险和真机边界：[项目当前状态](project-status.md)。
- 未完成 Task、依赖和验收：[项目 Backlog](project-backlog.md)。
- 带日期的验证结果和 evidence：[验证证据台账](validation-ledger.md)。
- 代码、测试和证据路径：[代码与验证入口地图](code-map.md)。
- 文档职责和新鲜度：[文档导航](README.md)。
