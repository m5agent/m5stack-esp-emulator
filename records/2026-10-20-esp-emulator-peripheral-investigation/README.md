# 基础设施 esp-emulator 外设模拟能力调查

- 日期：`2026-10-20`
- 结果：`PASS`（完成上游、版本、实际运行与 UART 外设桥验证）；`PARTIAL`（M5Stack 全产品外设纯软件测试尚不具备条件）
- 工作类型：`infra_baseline`
- 问题来源：用户询问是否可以在 `espressif/esp-emulator` 上模拟外设，并把测试全部转为纯软件
- 源码/工具版本：`espressif/esp-emulator @ 017d587`，`esp-emu 0.49.0`
- 环境：macOS Apple Silicon、Docker `espressif/idf:v5.5.5`、Playwright 无关

## 结论

**适合做一部分纯软件测试，但不能直接把 M5Stack 全部硬件测试替换掉。**

当前版本可以可靠覆盖 ESP32-C3/S3/P4 的固件启动、FreeRTOS、内存/Flash/NVS、Wi-Fi/Ethernet、BLE、加密、UART、基础 GPIO/SPI/I2C 控制器与网络协议测试。实测 C3 `32/32`、P4 `36/36`、S3 `34/34` smoke 通过。

外设层面目前只有有限的“外部设备”入口：

- `--uart1-tcp` 可以把 UART1 接到宿主机 Python/C 进程，已用 `PING/PONG` 实测通过；
- I2C 控制器带一个内置 `0x50` EEPROM 测试从机；
- RMT 可以做 TX→RX loopback；
- 没有通用的 SPI/I2C/GPIO 外部设备桥，也没有 M5Stack 板级 profile。

因此 SPI 屏幕、I2C 触摸/PMIC/IMU/RTC、按钮线、I2S 音频、ADC、相机、USB Host、LCD/DSI 和电源轨这些真实产品外设，目前不能通过 esp-emu 直接复现。上游 issue #5 正在讨论并保持 open，但没有实现或 ETA；仿真器源码也未发布（issue #10）。

## 建议

采用分层策略：

1. **现在可落地**：把固件启动、网络、协议、OTA、UART 外设和业务逻辑测试接入 CI/任务中心。
2. **补测试性**：在固件中增加 HAL/测试替身，先做 PC 端单元测试，不依赖真实外设。
3. **等待/推动上游**：跟踪 issue #5，争取 SPI/I2C/GPIO/I2S 外部设备桥和源码发布。
4. **保留真机**：显示、触摸、音频、相机、电源和整机交互仍由 Device Test Center 做最终验收。

## 关键证据

- `evidence/upstream-findings.md`
- `evidence/smoke-summary.txt`
- `evidence/smoke-esp32c3.log`
- `evidence/smoke-esp32p4.log`
- `evidence/smoke-esp32s3.log`
- `evidence/uart-peer-emulator.log`
- `evidence/uart-peer-host.log`
- `code/uart-peer/`

## 文件

- `report.md`：完整调查与接入建议
- `run.json`：结构化结果
- `evidence/`：上游问题记录、smoke 日志、UART 虚拟外设证据
- `code/uart-peer/`：可重建的最小 UART 外部设备样例

## 未覆盖项

没有接入 M5Stack 的真实屏幕/触摸/PMIC/相机固件；这些外设模型当前不存在。没有对 BLE、Thread、ESP-Hosted 做本机端到端复测，只核对了上游文档和发布说明。
