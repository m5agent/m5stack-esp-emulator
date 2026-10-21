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

## 状态语义

- `simulated`：初始化、状态注入、读取回放和 API 闭环均已通过。
- `partial`：芯片能被识别，或只有部分寄存器和数据通路可用。
- `planned`：仅登记硬件能力，尚无可用模型。
- `not-applicable`：不属于 ESP32 仿真范围。

`reference-ready` 只代表显示和输入闭环；外设状态必须以本目录状态为准。

## 新增设备

新增设备必须先补 `platform/peripherals/catalog.json`。CI 会检查：

- 设备是否存在于外设清单；
- 每个 `hardware.sensors` 是否至少有一个组件覆盖；
- 每个控制类型是否有对应输入模型；
- 组件引用的模型是否存在；
- 模型状态是否合法。

因此后续设备不会只凭一张设备外壳和显示屏就进入 `reference-ready`。

## 高带宽外设

摄像头、麦克风、扬声器和 USB 不适合只用寄存器模型表达。推荐接口：

- Camera：QOM frame source 或共享 framebuffer 邮箱；
- Audio：PCM ring buffer，输入/输出分别注入和抓取；
- USB Host：QEMU USB device 或虚拟端点；
- SD：虚拟块设备镜像。

这些接口必须保持为芯片/控制器之后的数据面，不能在 Python 测试代码里直接
伪造返回值，否则无法发现驱动和板级接线问题。

## 当前数据面实现

- **Camera**：CoreS3 的 GC0308 SCCB + ESP32-S3 LCD_CAM + GDMA RX 描述符已
  闭环。模型以半缓冲连续事件生成 RGB565 帧，支持 `camera.snapshot()` 和
  `M5.Display.show()`；宿主可通过 `M5SW_CAMERA_FRAME` 注入原始 RGB565 帧。
- **I2C 传感器/电源**：BMI270、BMM150、AXP2101、M5PM1、BQ27220、AW32001、
  PCF8563、RX8130、INA226、INA3221、LTR553、LM75、SHT40、ST25R3916 等均有
  总线级模型和 QOM 注入。
- **GPIO/扩展 IO**：按键、触摸、PI4IOE 的输入/输出/上拉/中断状态，AW9523
  的输入/输出/方向/中断状态，以及 M5IOE1 的 GPIO、ADC、PWM、IRQ 和
  NeoPixel RAM 均通过真实 I2C/GPIO 路径读取。
- **串行执行器**：StackChan 的 SCS 舵机通过真实 UART1 字节流解析
  `PING/READ/WRITE/SYNC_WRITE` 帧，位置、扭矩和遥测状态由舵机模型回包。
- **音频**：ES8311、ES7210、AW88298、AW8737A 和 PDM 麦克风通过
  ESP32-S3 I2S 与循环 GDMA 工作；宿主文件可抓取扬声器 PCM，也可向麦克风
  RX 描述符注入 PCM。Core2 v1.1 使用独立的 ESP32 classic I2S 控制器模型，
  直接消费 IDF `lldesc_t` 描述符链，NS4168 与 SPM1423 已分别完成 TX/RX
  数据面。
- **SPI 存储**：Cardputer-ADV 与 PaperColor 的 microSD 走 GP-SPI SD
  command/data 协议，并使用原始块镜像作为后端。
- **CAN/RS485**：StamPLC 的 TWAI 控制器连接 QEMU CAN-bus 虚拟节点；
  PWR485 使用 UART2 字节级虚拟对端。两者均通过官方 UIFlow2 驱动完成双向
  TX/RX。
- **蜂鸣器**：StamPLC 的 G44 由 M5Unified 生成为 I2S 1-bit ΔΣ 流，宿主
  从真实 I2S TX DMA 描述符抓取比特流。
- **RGB LED**：StackChan 的 M5IOE1 RGB RAM 和 PaperColor 的 ESP32-S3 RMT
  WS2812/GRB 波形都已闭环；RMT 抓取结果可在宿主按真实 T0H/T1H 解码。

## 仍需高带宽数据面的器件

USB Host、Tab5 摄像头/音频、核心传感器的一些剩余寄存器语义和现场总线
仍不能仅以“芯片可识别”标记为完成。它们必须继续实现端点、帧数据面或
总线级模型，并加入 UIFlow2 API 闭环测试。
