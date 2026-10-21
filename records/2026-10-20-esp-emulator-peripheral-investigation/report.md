# esp-emulator 外设模拟与纯软件测试评估

## 背景

用户希望评估能否用 `espressif/esp-emulator` 模拟 M5Stack 外设，从而把硬件测试尽可能转为纯软件测试。

## 上游事实

- 项目是 Espressif 的 Beta 级 ESP32 系列仿真器，支持 C3/C5/C6/H2/P4/S3/S31。
- 公开仓库主要提供预编译 release、安装脚本、文档和测试应用，没有仿真器源码。
- 当前 release 为 `0.49.0`，更新频繁；仓库规模约 275 stars、20 forks，仍处于快速演进阶段。
- 已支持 CPU、Wi-Fi、BLE、Thread、Ethernet、Flash/NVS、加密、GDB、trace、网络 NAT 等。
- 已支持的片上外设包括 UART、USB Serial/JTAG、GPIO、定时器、SPI Flash、GDMA、GP-SPI、RMT、LEDC、PCNT、MCPWM、I2C（内置 EEPROM）和 watchdogs。

## 实际验证

环境：macOS Apple Silicon，`esp-emu 0.49.0`，`espressif/idf:v5.5.5`。

官方 smoke 测试应用都从 ROM 经二级 bootloader 跑到 `app_main`：

| 芯片 | 结果 |
| --- | --- |
| ESP32-C3 | `passed=32 failed=0` |
| ESP32-P4 | `passed=36 failed=0` |
| ESP32-S3 | `passed=34 failed=0` |

这些测试覆盖了系统信息、Flash/NVS、FreeRTOS、GPIO、SPI、I2C EEPROM、RMT、LEDC、PCNT、加密、Wi-Fi/Ethernet DHCP、reset reason 等。

此外构造了一个最小 UART1 外部设备实验：

- C3 固件向 UART1 发送 `PING\n`；
- 宿主机 Python 进程通过 `--uart1-tcp` 接收；
- 宿主机回传 `PONG\n`；
- 固件在 UART0 输出 `UART_PEER_OK`。

结果通过，说明“外部串口设备用脚本模拟”是当前可用的能力。

## 关键限制

### 1. SPI/I2C/GPIO 外部设备桥未实现

上游 issue #5 明确请求：

- 任意 UART 的 TCP bridge；
- GPIO 事件 bridge；
- SPI/I2C transaction bridge；
- I2S PCM bridge。

维护者已回复保持 issue open、正在讨论 peripheral emulation，但没有实现或时间表。没有这些 bridge，不能可靠模拟：

- SPI 显示器和 LCD 初始化；
- I2C 触摸、PMIC、IMU、RTC、传感器；
- 按键和外部中断；
- 音频 codec；
- 需要 CS/DC/RESET 等 sideband GPIO 的设备。

固件即使在模拟器中启动，遇到常见的 `i2c_master_probe()` 失败或 LCD 读 ID 失败仍可能 abort，后续网络和业务代码根本不会执行。

### 2. 不是板级仿真

CLI 只有 `--chip`，没有 M5Stack 板级 profile。Flash/PSRAM/console 可配置，但外设接线、电源树和 board revision 仍需要应用层自己的测试替身。

### 3. UART bridge 不是时序仿真

UART1 TCP 能传字节，但 UART TX/RX 当前接近瞬时完成，RXFIFO timeout 没有按真实波特率触发（上游 issue #20）。因此：

- 简单命令/响应协议可以测试；
- Modbus RTU、RS485、依赖字符间隔或帧尾超时的协议不能当作真实时序验收。

### 4. 显示、相机和音频没有完整产品结果

浏览器版本可以看 GPIO/寄存器/内存和终端，但不是 LCD 像素输出。LCD_CAM、MIPI DSI、I2S、ADC、USB Host 和 camera 也没有通用外部设备桥。

### 5. 源码风险

公开 repo 带 Apache-2.0 LICENSE，但没有 `src/`。上游 issue #10 表示源码发布尚未决定。当前不能假设可以自行 fork 或添加私有外设模型。

## 对现有测试体系的建议

### 第一层：纯软件仿真，马上可做

适合放进 CI 或 Agent 任务中心：

- merged.bin + ELF 启动；
- bootloader/partition/flash/NVS；
- FreeRTOS 任务、队列、定时器；
- Wi-Fi/Ethernet、DHCP、DNS、HTTP/MQTT；
- BLE/Thread/ESP-Hosted（按上游能力）；
- UART1 虚拟传感器/串口设备；
- OTA 启动和异常 reset 路径；
- 业务层的“无屏幕”逻辑。

### 第二层：把固件改造成可测试

对 M5Stack 真实产品增加：

- `hal` 接口；
- “sim” build 或 `CONFIG_APP_TEST_DOUBLE`；
- I2C/SPI/GPIO device mock；
- 将显示/触摸/PMIC 初始化与业务逻辑解耦；
- host-side unit tests 和 structured test markers。

这能覆盖大部分业务逻辑，但不能证明真实外设电气/时序行为。

### 第三层：等待上游增强仿真器

最值得推动的是 issue #5 的四类 bridge。若 Espressif 实现或开源，才能进一步做：

- SPI display framebuffer viewer；
- I2C register-file devices；
- GPIO buttons/INT；
- I2S codec。

### 第四层：真机验收保留

以下场景仍必须在 Device Test Center 或实机完成：

- 屏幕/触摸/相机/音频；
- PMIC、电池和 12V/5V 电源；
- USB Host/Device 实体行为；
- RF/天线/功耗；
- 传感器精度和环境响应；
- 产线治具、烧录、重启和掉电恢复。

## 结论

esp-emulator **可以作为强大的第二测试 oracle 和 CI 前置层**，但不能把当前 M5Stack 全部测试直接改成纯软件。最合理的路线是：先把启动、网络、协议、UART 和业务逻辑前移到仿真，再推动上游 SPI/I2C/GPIO bridge；最终显示、电源、相机等仍保留真机验收。

## 风险与回滚

本调查没有修改上游仓库，也没有接入生产测试流程；只下载 release 到本地目录并运行 smoke/样例。后续接入时应把仿真结果与真机证据分栏记录，禁止把 smoke PASS 直接写成产品行为 PASS。
