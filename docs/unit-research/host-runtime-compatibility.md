# Unit runtime 跨主机兼容性审计

审计日期：2026-10-26。本页保存初始源码、官方接线与独立无 Unit boot control
的边界。初审没有扩大 host 白名单；后来的主机本地验证与显式开发准入分别
登记在 runtime profile 和状态页，不在本页复制一份当前许可名单。
一个 Unit 的基线不能向其他主机或其他 Unit 继承 PASS。
当前能力与待办仍以 `project-status.md`、`project-backlog.md` 为准。

## 已存在的复用边界

本页基础源码审计与三台无 Unit boot control 的历史冻结 runtime SHA 为
`1880891da692de06612aa0a10b2026c0209875f4641e837df29dc818bb3ac81d`。
`unit-runtime-source-replay-20261026.json` 保留 public base、全部补丁与 106 个
源文件的精确 hash。以下符号均可在 `0033-unit-runtime-core-and-routing.patch`
及其配套 source replay 中核对：

- `hw/xtensa/esp32s3.c` 在 board 初始化后统一调用 `m5_unit_runtime_init(true)`；
  九种 M5 S3 machine 共用入口，不是 CoreS3 独有的 C 分支。
- `m5_unit_runtime.c:m5_unit_i2c_route` 根据 guest GPIO matrix 的 SDA/SCL
  选择独立 Unit bus；未匹配时回到 board bus。内部器件与外部同地址器件必须用
  本机 scan/read 证明隔离，不能因有统一入口而推断已隔离成功。
- `m5_unit_gpio.c` 通过 GPIO 输入/IRQ、SENS、LEDC、RMTMEM/IRQ 和 UART FIFO
  连接 Unit。S3 理想 SAR 映射覆盖 ADC1 GPIO1..10、ADC2 GPIO11..20。
- `UnitRegistry.attachments()` 仍要求每个 Unit profile 明确包含目标 host；
  初始审计时 profiles 只列 CoreS3，gen9 首批后来验证了三主机各三个组合。
  已确认物理口不等于运行时准入。

三主机后续六类 I2C sensor 采用同样的硬件总线分离：外部 controller 0
使用各自 Grove GPIO，内部 controller 1 使用实际系统 GPIO。AtomS3R 必须
使用 47/0，不能以 QEMU 的旧 soft-I2C fallback 47/48 代替。显式开发准入
仅允许开始测试，必须另有 exact 外部 scan、内部 BMI before/after/loop、
原 sensor 负控/采样、实际产品 POST 与输入后新鲜 guest 读回。

## 其余八种 S3 主机

下表 GPIO 顺序刻意使用 **yellow / white**。普通 UIFlow GPIO `port` tuple
为 `(white, yellow)`；I2C 则明确 SDA=yellow、SCL=white。ADC 栏描述芯片能力
和当前 C 映射可达性，不代表该主机 ADC 已运行通过。

| 主机 | 已确认主口 yellow / white | white 的 ADC | 板内资源与扩展前检查 |
| --- | --- | --- | --- |
| StickS3 | CUSTOM 9 / 10 | ADC1 ch9；C 映射存在 | 系统 I2C=47/48，按键=11/12，内置 IR=46/42，与主 Grove 不重叠。外部与内置 IR/RGB 仍共享 RMT 分配器，必须验证独立 channel。43/44 是 Hat2 bus 信号，console 测试应声明未装 HAT。 |
| StopWatch | PORT.A 10 / 11 | **ADC2 ch0**；C 映射存在 | 系统 I2C=47/48，按键=2/1，与 Grove 分离。UART0 43/44 经 M5IOE1 扩展口 USB/UART mux，官方默认 UART；不能把切到 USB 后的空 serial 当 guest 未运行。Grove 5V 由 M5PM1 管理，当前 Unit 数据面没有证明断电副作用。 |
| AtomS3R | CUSTOM 2 / 1 | ADC1 ch0；C 映射存在 | 官方 SYS_SDA=47、SYS_SCL=0；当前 board 的 soft-I2C fallback 仍初始化 47/48，不能用 fallback 的存在替代 guest 实际 pin route 证明。USER=41，IR=45，显示 MOSI=21/SCK=15/CS=14，与 Grove 分离。 |
| Cardputer-Adv | CUSTOM 2 / 1 | ADC1 ch0；C 映射存在 | 内部 I2C=8/9（键盘/IMU/codec），与 Grove 分离。**43 是 audio LRCK，44 是 IR TX**，通用 UART0 43/44 probe 会重配板内引脚；须先选定可观测且无冲突的日志方案。显示、键盘及 SD 必须同时保留功能。 |
| StamPLC | PORT.A 2 / 1 | ADC1 ch0；C 映射存在 | 内部 I2C=13/15，PWR-485=TX0/RX39/DIR46，板载 UART2 不能被外部 RS485 probe 抢占；外部可评估 UART1。**43 是 CAN RX，44 是 buzzer**，不能原样复用通用 console pin。PORT.C 5/4 虽有官方映射，当前登记为附件/配置相关，不能擅自作为现有主口开放。 |
| StackChan | PORT.A 2 / 1 | ADC1 ch0；C 映射存在 | 内部 I2C=12/11，servo=UART1 TX6/RX7，IR=TX5/RX10，与 Grove 引脚分离。**当前 servo peer 挂 UART1 TX callback，未按 GPIO matrix 过滤**，外部 UART1 RS485 不能直接继承 CoreS3 结果。优先独立 UART2，或先修 board peer 路由并回归内置 servo。PORT.B/C 维持附件配置门槛。 |
| PaperColor | PORT.A 4 / 5 | ADC1 ch4；C 映射存在 | 内部 I2C=3/2，Grove 分离；官方 Grove power direction 由 M5PM1 控制。**43=EINK_DC，44=EINK_CS，45=audio power**；现有不同探针分别使用 43/44 和 44/45 日志，均不能作为无冲突物理接线依据。需先落实 console 方案，并证明 e-paper 与电源 API 未受重配影响。内置 RGB/IR 与外部 RMT 还需同时验证。 |
| PaperMono | **未确认外部 Grove** | 未分配 | 当前官方 PinMap 只列板内总线与扩展芯片；不能从 S3 通用 GPIO 或视觉模型反推一个 Grove。先取得准确 connector/schematic/revision，才允许研究外部路由。系统 I2C=47/48，SD 占 8..13，其他大量引脚用于 e-paper、PDM、LoRa、按键及中断，不能随意借用。 |

上述板内接线于本次审计重新读取官方产品 PinMap。原始网页含完整产品内容，
未作为运行证据加入正向结果。它们与 `host-ports.json` 主 Grove pin 一致；
AtomS3R 的 SYS_SCL=0 与当前 soft fallback=48 的差异需要后续本机路由检查。

## 不能直接复制 CoreS3 probe 的部分

| 主机 | Flash / VFS offset / VFS size | 目标 framebuffer |
| --- | --- | --- |
| CoreS3、StackChan | 16 MiB / `0xAA0000` / `0x4C0000` | 320×240 |
| StickS3 | 8 MiB / `0x651000` / `0x1AE000` | 135×240 |
| AtomS3R | 8 MiB / `0x641000` / `0x1BE000` | 128×128 |
| Cardputer-Adv | 8 MiB / `0x651000` / `0x1AE000` | 240×135 |
| StamPLC | 8 MiB / `0x641000` / `0x1BE000` | 240×135 |
| StopWatch | 16 MiB / `0x820000` / `0x7DF000` | native frame 466×466；guest canvas 468×468，rotation 0，圆形可视区域 |
| PaperColor | 16 MiB / `0x820000` / `0x7DF000` | 400×600，e-paper settle |
| PaperMono | 16 MiB / `0x820000` / `0x7DF000` | 480×800，e-paper settle；无外口准入 |

显示/Flash 参数来自 `tests/uiflow2/device_matrix.json`，VFS 数值由本次对实际
reference bytes 调用 first-party `firmware_analysis.parse_partition_table`
重新读取。当前 StickS3/Cardputer-Adv 的 VFS 已为 `0x651000/0x1AE000`，旧矩阵
仍写 `0x641000/0x1BE000`；不能静默沿用。上传其他固件必须重新核对 partition，
并拒绝不合法、重叠或不唯一的 VFS。现有 IO probe 固定
`setRotation(1)`、320×240 绘图区和 UART0 43/44，runner 的 `--device` 仅
接受 CoreS3。扩展需要显示布局/rotation、serial transport、端口选择和设备
matrix 参数化，而不是只往 profiles 的 hosts 数组加名字。LittleFS 仍须以
正确 geometry 打包、remount 并逐字验证 guest 文件。

ADC 有独立阻断：当前 `esp32s3-adc-calibration.json` 精确绑定 CoreS3 V2.5.3
application segment bytes。Service 对不匹配 app 只记录 `not-applied` 并保留
raw ADC，不能复用 CoreS3 的 `read_uv()` oracle 宣称其他主机通过。每种 firmware
需核实 IDF/MicroPython 校准路径，建立对应的精确 fixture 绑定；StopWatch 要
明确使用 `adc_unit=2`。不能改 guest driver 返回值或关闭校准来凑相同结果。

## 每个主机的最小设备本地验证

下面是准入门槛，不是已执行结果，也不替代最终逐 Unit 的 device-local case。
所有功能验证都经可见 `/api/v1` session，保存 firmware/runtime SHA、串口、
frame、QOM、输入、控制器计数、停止前 ZIP，以及 `purge=0` history。

1. 从本机 reference firmware 制作只做 M5 初始化/显示/日志的 control，保留
   板内输入和一个板内 I2C 读值。确认日志没有重配显示、audio、CAN 或 servo
   信号，且准备图像的 partition/VFS/字节校验通过。
2. 首个连接组合覆盖 Button（GPIO/IRQ）、Relay（输出）、ENV III（外部 I2C
   与内部 bus 隔离）；明确选用的 I2C controller，并在外部读后再次读取板内
   设备。相同地址不得泄漏到错误 bus。
3. 运行 Angle/Light 的 white ADC raw 与 digital 两路；只有 fixture 匹配后
   才加入精确 `read_uv()`。StopWatch 单独跑 ADC2 的负向 channel 选择检查。
4. 运行 Fan/Buzzer 的真实 LEDC duty/frequency 和停止；运行 RGB/Key 的完整
   RMT chain、short-frame 拒绝，以及内置 RMT 资源不被重配的本机检查。
5. RS485 binary FIFO 双向/容量拒绝必须选择无 board peer 争用的 UART；
   StackChan 还要证明内置 servo 保持独立。IR 保留原 wrapper、独立 native TX
   与 callback GC 缺口的分层结论，不把 CoreS3 workaround 自动推广到别的固件。
6. 最后逐个迁移全部目标 Unit case，冻结 host/runtime/firmware 后检查浏览器
   live state、对应视觉部件、同一 session evidence 与 retained history。
   完成哪个 host+Unit，就只开放该组合；其他组合继续 fail closed。

## 历史无 Unit boot control 与 gen9 九组合验证

AtomS3R、StickS3、StopWatch 的三个独立可见 session 已在历史冻结 `1880891d…`
上通过无外部 Unit boot control，直接 PID executable SHA、启动前后及循环内
BMI270 `CHIP_ID=0x24`、非空 framebuffer、停止前 ZIP 和 `purge=0` history 均
保留于 [boot summary](https://github.com/m5agent/m5stack-esp-emulator/blob/a37342f61c05964c060719a6e35c2d568c828e84/docs/evidence/2026-10-26-unit-host-boot-controls/summary.json)。
StopWatch 同一运行报告 guest canvas 468×468、rotation 0，native frame 466×466；
这两个维度现在分开断言，未修改 C framebuffer 或裁剪模型。失败的 QMP-ready
和几何断言尝试也保留，不能只保留成功结果。

`tests/units/run_host_cases.py` 随后在 generation 9、runtime
`a8fe15dbe7299c5be4b52eeac68a6d0012578950d267287630760bf8bec7d047`
完成这三台主机各自的 Button、Relay、ENV III：**9/9 严格功能 PASS，0 失败、
0 重试**。使用明确内外 I2C controller、板内 BMI270 再读、真实 GPIO/IRQ/output
与外部 ENV 两组物理输入；每个组合分别绑定 host 和 Web 的直接 PID/hash、同一
session/firmware/generation、实际 DOM 与 HTTP 输入、停止前 ZIP 及保留 history。
证据见 [host9 archive](https://github.com/m5agent/m5stack-esp-emulator/blob/a37342f61c05964c060719a6e35c2d568c828e84/docs/evidence/2026-10-26-unit-host-web-gen9-a8fe/README.md)。

逐行光标布局已由本次九张 native frame 验证，历史 boot frame 不改写。九组合
功能 PASS 与浏览器构图分列：三台 ENV 的浏览器截图存在全局 sticky header 遮住
session card 标题/顶边，framing 为 **PARTIAL**；输入、控制器字段与 serial 可读，
native frame 不受影响，不宣称完整视觉验收，也不重拍覆盖原证据。

执行前冻结包含明确的 25 个命名源文件，遗漏直接打包 helper
`run_control_cases.py`、`run_sensor_cases.py`；其后只能做 archive-time hash 和历史
冻结 helper 连续性核对，不能倒填为执行前冻结。其他 24 Units/host、ADC 和物理
行为仍不在九组合范围内。不得把 gen9 与历史 `1880891d…` boot control 拼成同次执行。

## 非 S3 主机的具体边界

| 主机 | 当前源码可复用部分 | 扩展阻断 |
| --- | --- | --- |
| Core2 / ESP32 | `m5core2_board_init()` 已调用 `m5_unit_runtime_init(false)` 和 classic SENS；classic GPIO/I2C routing、理想 ADC 与 LEDC hooks 已存在。主口 yellow32/white33=ADC1 ch5；内部 I2C=21/22。 | 没有 Core2 Unit profile/device-local acceptance。RGB、Key、IR、RS485 在 realize 明确拒绝 classic path；S3 RMT signal/channel/memory 和 UART 选择器不能直接套用。其他基础 Unit 也须本机验证。日志用 UART0 TX1/RX3；S3 fixture 不适用。Port B white36 只能输入，不能任 SCL/TX/output；Port B/C 当前仍为附件相关口。 |
| NanoC6、Nesso N1 / ESP32-C6 | repo 有各自板级 GPIO、I2C、LEDC/RMT、UART/HCI 的历史实现与测试。官方主口分别 yellow2/white1、yellow5/white4；芯片 ADC 分别为 ADC1 ch1/ch4。 | 当前 Unit source bootstrap/0033 针对 Xtensa 构建，未给 C6 binary 连接 `M5_UNIT_CONFIG`、Unit QOM、C6 GPIO-matrix bus routing、SAR/LEDC observer 或 FIFO peer。`s3=false` 是 classic ESP32，并非 C6。必须给 C6 各寄存器/IRQ/signal map 接入和本机案例；C6 板载组件 PASS 不等于外部 Unit PASS。 |
| Tab5 / ESP32-P4 | 官方 PORT.A yellow53/white54；P4 white54 是 ADC2 ch5。当前 esp-emu P4 部分板内路径可用。 | 外部 Unit 不是 Xtensa QEMU lane，runtime init 不会自动执行；S3 pins<49 限制与 ADC/RMT/register map 都不适用。闭源 backend 目前没有本任务可用的动态 I2C Unit、controller IRQ/GPIO/ADC/LEDC/RMT/UART endpoints 和统一 QOM/ZIP Unit contract。必须先取得真实 controller-level bridge，不能用 Python fake sensor/callback。现有板内 preload 不满足动态 Unit 数据面。 |
| CardputerZero / Linux ARM64 | 另有 BCM2837 Linux board backend、板内 I2C/USB/audio/IR 等测试。 | 不受 `/api/v1` 管理，host-ports 未确认外部 Grove；旧产品 URL 的 404 不等于无硬件。先核实外部 connector、GPIO chip/line、Linux I2C/SPI/UART device node 与 pinmux；再建立独立 Device Service adapter、Unit生命周期/输入/证据接口。现有 BCM 板内测试不是 UIFlow/S3 Unit runtime。 |

## 来源

- 接线与电源：[StickS3](https://docs.m5stack.com/en/core/StickS3)、
  [StopWatch](https://docs.m5stack.com/en/core/StopWatch)、
  [AtomS3R](https://docs.m5stack.com/en/core/AtomS3R)、
  [Cardputer-Adv](https://docs.m5stack.com/en/core/Cardputer-ADV)、
  [StamPLC](https://docs.m5stack.com/en/core/StamPLC)、
  [StackChan](https://docs.m5stack.com/en/StackChan)、
  [PaperColor](https://docs.m5stack.com/en/core/PaperColor)、
  [PaperMono](https://docs.m5stack.com/en/core/PaperMono)，本次均重新读取 PinMap。
- 芯片 ADC pin map：[ESP32-S3](https://github.com/espressif/esp-idf/blob/v5.5.5/components/soc/esp32s3/include/soc/adc_channel.h)、
  [ESP32](https://github.com/espressif/esp-idf/blob/v5.5.5/components/soc/esp32/include/soc/adc_channel.h)、
  [ESP32-C6](https://github.com/espressif/esp-idf/blob/v5.5.5/components/soc/esp32c6/include/soc/adc_channel.h)、
  [ESP32-P4](https://github.com/espressif/esp-idf/blob/v5.5.5/components/soc/esp32p4/include/soc/adc_channel.h)，本次重新读取固定 tag 原文件。
- 仓库权威输入：`platform/units/host-ports.json`、`runtime-profiles.json`、
  `platform/tools/unit_runtime.py`、`platform/tools/device_service.py`、
  `tests/uiflow2/device_matrix.json`、`platform/peripherals/catalog.json`。
- C 路径：`0033-unit-runtime-core-and-routing.patch`、`0034-unit-i2c-sensors.patch`、
  `0035-unit-i2c-controls.patch` 与 source replay；C6 对照见
  `0025-esp32c6-wifi-mac.patch` 和其 README，不把缺少当前 C6 source checkout
  解释为板级 C6 控制器完全不存在。
