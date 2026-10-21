# 外设仿真架构

设备仿真被拆成四层：

1. **设备档案**
   `devices/catalog.source.json` 声明真实的 SoC、屏幕、按键和传感器能力。
2. **外设契约**
   `platform/peripherals/catalog.json` 把能力映射到具体芯片、总线、地址、
   QOM 路径、注入接口和仿真状态。
3. **QEMU/虚拟后端**
   为 I2C、GPIO、PMIC、RTC、音频、摄像头等提供协议模型；高带宽数据通过
   QOM、共享内存或 GDB 邮箱注入。
4. **UIFlow2 测试**
   `tests/uiflow2/` 使用官方 UIFlow2 API 读取外设、注入输入并验证屏幕/串口/
   API 返回行为。

5. **设备中心清单**
   `platform/tools/peripheral_inventory.py` 将设备硬件需求、具体组件、芯片、
   总线、地址、QOM 路径、注入方式、数据面和 blocker 展开成机器可读清单，
   后续设备中心可直接消费，不再自行猜测模拟器支持范围。

## 状态语义

- `simulated`：初始化、状态注入、读取回放和 API 闭环均已通过。
- `partial`：芯片能被识别，或只有部分寄存器和数据通路可用。
- `planned`：仅登记硬件能力，尚无可用模型。
- `not-applicable`：不属于 ESP32 仿真范围。

`reference-ready` 只代表显示和输入闭环；外设状态必须以本目录状态为准。

设备级外设状态是模型状态与板级后端验证的交集。芯片模型在另一块主控上
通过，不代表它在新的 SoC、I2C 控制器、I2S/DMA、GPIO 映射或 Linux 驱动下
已经可用。`peripheral_status=simulated` 必须同时满足：

- 器件有真实寄存器/协议模型；
- 数据经过 SoC 控制器和 DMA/FIFO/端点；
- 当前设备有 UIFlow2 API 或原生驱动闭环证据；
- 宿主注入和抓取接口可重复执行。

只要任一组件仍为 `partial`/`planned`，设备就必须在
`peripheral_blockers` 中逐项列出模型和具体后端缺口，CI 会检查两侧是否完全
对应。

对于尚未完成的现有设备，`completion_policy.incomplete_device_allowlist`
必须给出原因和复查日期；新设备若还存在任何非显示外设缺口，CI 会直接失败。
这样可以防止后续新增设备只做外壳、显示和触摸就进入设备中心。

## 新增设备

新增设备必须先补 `platform/peripherals/catalog.json`。CI 会检查：

- 设备是否存在于外设清单；
- 每个 `hardware.sensors` 是否至少有一个组件覆盖；
- 每个控制类型是否有对应输入模型；
- 组件引用的模型是否存在；
- 模型状态是否合法。

因此后续设备不会只凭一张设备外壳和显示屏就进入 `reference-ready`。

目录校验读取 `devices/catalog.source.json` 的完整硬件档案，而不是生成后的
展示目录。当前 14 台设备共有 155 个唯一硬件需求，CI 同时检查需求和组件
是否一一覆盖。生成后的展示目录若缺少 `hardware.sensors/controls`，不会再
造成“零需求、假通过”。
反向检查同样生效：板级实现中的每个非显示组件都必须能在设备硬件档案中
找到对应需求，防止“模型已经接了但设备中心清单漏项”的单向通过。
`runtime-coverage.json` 还要求每个 `simulated` 模型至少绑定一个带运行时
证据的矩阵用例，或绑定 external probe 及其 evidence 文件；仅有模型名称
和静态 PASS 不再足够。

`case_models` 进一步记录每个用例实际覆盖的芯片模型。校验器会把该映射和
设备组件求交集，要求每台设备上的每个 `simulated` 组件至少有一个在**同一
设备后端**运行的用例。这样同名芯片在别的 SoC、I2C 总线、DMA 或引脚映射上
通过，也不会让新设备自动继承完成状态。

新增模型使用 [`model-template.json`](../platform/peripherals/model-template.json)。
`simulated` 模型缺少 `data_plane`、`injection` 或 `tested_devices` 会直接
失败；`partial`/`planned` 模型缺少 `blocker` 也会失败。

## 当前后端能力边界

| 后端 | 已可用 | 未提供 |
| --- | --- | --- |
| QEMU ESP32-S3/C6/LX6 | GPIO、I2C、I2S/GDMA、PDM、RMT、LCD_CAM、SPI、SD、TWAI、UART peer、USB Host | 尚未建模的具体芯片需要逐项补寄存器/数据面 |
| `esp-emu` native P4 | UART 下载、GDB、framebuffer/touch 固件邮箱、ESP-Hosted、通用 I2C 寄存器设备 | I2S/PCM、MIPI DSI/CSI 控制器、USB Host、可写 I2C 器件/QOM、PCIe |
| ARM64 Linux | BCM2837 机器、M5Stack DT overlay、ST7789v3 DRM、GPIO/I2C、TCA8418 input、ES8389 I2C/BCM2835 I2S FIFO/DREQ DMA、播放与麦克风 PCM、IP2315 充放电状态、寄存器驱动的 IMX219 + Unicam CSI1 V4L2 帧、GL852G MTT 兼容 FS/LS 路由、SR9900A/r8152 以太网帧回环、GPIO IR 收发、LVGL fb1 非黑首帧 | AW8737A 模拟电气链路 |

Tab5 当前已完成显示、触摸可视化、C6 Hosted、静态 I2C 寄存器探测、
PI4IOE 充电/放电状态到 `Power.isCharging()` 的闭环和 SIT3088 RS-485
（UART1 G20/G21、方向 G34）主机对端。它仍缺少
ES8388/ES7210 音频数据面、SC2356 MIPI-CSI、P4 USB Host、SDIO 存储和
真实 ST7123 触摸寄存器路径，不能标记为全外设闭环。

后端必须补齐的控制器、DMA、端点、热注入和验收条件见
[`p4-peripheral-backend-requirements.md`](p4-peripheral-backend-requirements.md)。

## 高带宽外设

摄像头、麦克风、扬声器和 USB 不适合只用寄存器模型表达。推荐接口：

- Camera：QOM frame source 或共享 framebuffer 邮箱；
- Audio：PCM ring buffer，输入/输出分别注入和抓取；
- USB Host：QEMU USB device 或虚拟端点；
- SD：虚拟块设备镜像。

这些接口必须保持为芯片/控制器之后的数据面，不能在 Python 测试代码里直接
伪造返回值，否则无法发现驱动和板级接线问题。

## 当前数据面实现

- **Camera**：CoreS3/StackChan 的 GC0308 SCCB + ESP32-S3 LCD_CAM + GDMA RX
  描述符已闭环。模型在 `IN_LINK.START` 的同一寄存器事务中通过 GDMA
  peripheral callback 启动采集，解决“驱动等 VSYNC、模型等 DMA”的启动死锁；
  后续半缓冲通过循环描述符和 `IN_SUC_EOF` 连续交付。`camera.snapshot()`
  返回 `320x240 / 153600 bytes` 并经 `M5.Display.show()` 显示，宿主也可通过
  `M5SW_CAMERA_FRAME` 注入原始 RGB565 帧。
  CardputerZero 的 IMX219 进一步保存 Linux 驱动写入的 mode-select、lane、
  crop/output window、frame/line length、曝光、模拟/数字增益、方向和测试图案
  寄存器；Unicam 每帧按这些寄存器生成 RG10 数据，而不是固定图案。
- **I2C 传感器/电源**：BMI270、BMM150、AXP2101、M5PM1、BQ27220、AW32001、
  PCF8563、RX8130、INA226、INA3221、LTR553、LM75、SHT40、ST25R3916 等均有
  总线级模型和 QOM 注入。RX8130/PCF8563 用例通过 `machine.I2C` 直接读写
  BCD 时间寄存器并检查走时；`machine.RTC` 只修改 SoC 系统时钟，不作为外部
  RTC 证据。
- **M5PM1**：电源源/配置、GPIO、ADC/温度、PWM、NeoPixel RAM、IRQ 状态与
  屏蔽、唤醒源、看门狗、定时器和 RTC RAM 均按寄存器语义工作，支持输入和
  模拟量 QOM 注入。
- **AXP192**：Core2 legacy 选择路径验证了芯片 ID、状态、电池/VBUS/APS
  ADC、充放电电流及 GPIO/IRQ 寄存器文件。
- **GPIO/扩展 IO**：按键、触摸、PI4IOE 的输入/输出/上拉/中断状态，AW9523
  的输入/输出/方向/中断状态，以及 M5IOE1 的 GPIO、ADC、PWM、IRQ 和
  NeoPixel RAM 均通过真实 I2C/GPIO 路径读取。
- **串行执行器**：StackChan 的 SCS 舵机通过真实 UART1 字节流解析
  `PING/READ/WRITE/SYNC_WRITE` 帧，位置、扭矩和遥测状态由舵机模型回包。
- **音频**：ES8311、ES7210、AW88298、AW8737A 和 PDM 麦克风通过
  ESP32-S3 I2S 与循环 GDMA 工作；宿主文件可抓取扬声器 PCM，也可向麦克风
  RX 描述符注入 PCM。Core2 v1.1 使用独立的 ESP32 classic I2S 控制器模型，
  直接消费 IDF `lldesc_t` 描述符链，NS4168 与 SPM1423 已分别完成 TX/RX
  数据面。CardputerZero 的 ES8389 使用 I2C 身份/状态寄存器、BCM2835 I2S
  FIFO 和 DREQ DMA；播放与麦克风 WAV 均能逐字节验证。CardputerZero 的
  IP2315 QOM 电源路径状态通过 BQ27220 有符号电流寄存器影响 Linux
  `power_supply`；PaperMono 的 IP2315 在 I2C `0x75` 提供充电使能和
  `REG_CHG_STAT(0xC7)`，由 `Power.isCharging()` 读取。
- **SPI 存储**：Cardputer-ADV 与 PaperColor 的 microSD 走 GP-SPI SD
  command/data 协议，并使用原始块镜像作为后端。
- **CAN/RS485**：StamPLC 的 TWAI 控制器连接 QEMU CAN-bus 虚拟节点；
  StamPLC PWR485 使用 UART2、Tab5 SIT3088 使用 UART1，两者均通过
  字节级虚拟对端完成双向 TX/RX。
- **蜂鸣器**：StamPLC 的 G44 由 M5Unified 生成为 I2S 1-bit ΔΣ 流，宿主
  从真实 I2S TX DMA 描述符抓取比特流；Nesso N1 的 GPIO11 走 ESP32-C6
  I2S TX、AHB GDMA OUT EOF 中断和同一类 PCM 抓取路径。
- **RGB LED**：StackChan 的 M5IOE1 RGB RAM 和 PaperColor 的 ESP32-S3 RMT
  WS2812/GRB 波形都已闭环；RMT 抓取结果可在宿主按真实 T0H/T1H 解码。
- **ESP32-C6 RMT**：TX/RX 通道、APB FIFO、硬件符号内存和完成中断已建模；
  NanoC6 与 Nesso N1 的 `hardware.IR.tx()` 可抓取并解码 NEC 帧。
- **USB Host**：CoreS3 M-Bus SPI 上的 MAX3421E 模型实现寄存器/FIFO、
  USB Chapter 9 枚举、配置和 HID report descriptor，以及中断 IN 鼠标报告；
  QOM 可注入 x/y/buttons。
  CardputerZero 的 GL852G 提供 MTT 兼容路径：下游模型保留真实 FS/LS 速度，
  上游 HCD 使用 HS 端口并通过 hub 转发。SR9900A Full-Speed 以太网帧回环和
  Low-Speed USB HID 枚举/输入均已通过。

## 仍需高带宽数据面的器件

Tab5 的 SC2356、ES8388、ES7210、P4 USB Host、SDIO 与 ST7123 仍缺少当前
原生后端的控制器/端点。它们必须继续实现端点、帧数据面或总线级模型，并
加入对应系统下的自动测试。

CardputerZero 的 BCM2835 SPI 已支持 DMAEN 32-bit FIFO 和 write-only 面板
背压处理，并可旁路重建 ST7789v3 RGB565 像素流；官方 factory UI 可完成
fbdev、输入、资源和 LVGL 初始化，并通过 fb1 验证 320x170 非黑首帧：
54400/54400 像素非黑、127 种 RGB565 颜色，启动后帧哈希发生变化。
