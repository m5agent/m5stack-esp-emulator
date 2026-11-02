# Unit 第八批 12 款虚拟设备证据

日期：`2026-11-03`。范围：把 batch8 全部 12 款 Unit（`pahub-v21`/`gps-v11`/
`gps-sma`/`lcd`/`mini-can`/`oled`/`mini-oled`/`glass2`/`nbiot-cn`/
`lora-e220-920`/`lorawan-us915`/`mic`）的数据面通过**独立 Device Service**的
可见 `/api/v1` 会话记录为**虚拟设备**证据。显示光学/GNSS RF/蜂窝 RF/LoRaWAN
RF/CAN 电气/声学语义全部 `NOT RUN`。

本页是验证证据，不定义当前能力；当前能力以
[项目当前状态](../../project-status.md) 为准，工作队列以
[项目 Backlog](../../project-backlog.md) 为准。所有结果只覆盖表内记录的主机、
固件 SHA、QEMU 二进制 SHA 和检查项，不转授未列组合。

## 关键点：单一 QEMU 构建 + 0152 证据修复

12 款都在 canonical 32 层链（`0146` batch8 A + `0148` batch8 B）上；本批只需
**一个** QEMU 构建，`0152` 是本轮证据发现的模型修复。

| 项 | 值 |
| --- | --- |
| QEMU 源码状态 | canonical `75f1d24` + canonical 链 32 层（…→0146→0148→0149→0150→0151）+ **0152（本轮证据修复）** |
| QEMU 树 | `.work/native-lock-source/qemu`（`rm -rf build` 后重新 `configure`） |
| 运行时二进制 SHA-256（签名部署副本） | `bed1fea8…`（每条 report 的 `runtime_binary_sha256` 一致） |
| 参考固件 | cores3 `platform/.cache/firmware/cores3/uiflow2.bin`，SHA-256 `1324f12d…` |
| Device Service | 独立 `127.0.0.1:8801`、独立 state/token、`M5_SERVICE_FLASH_MODE=host-image`；用户 `8787` 与另一 `8799` 服务均未触碰 |

**端口选择说明**：任务预期的 `8799` 被另一并行任务的服务占用（`unit-batch7-service`），
因此本批使用独立 `8801` + 独立 state/token；不停止、不修改 `8799` 与 `8787`。

## 证据修复（本轮发现）

`0153-unit-batch8-evidence-lcd-read.patch`，base 为 canonical 链到 `0151` 的树：

| 根因 | 影响 | 修复 |
| --- | --- | --- |
| `0146` Unit LCD 在写事务 `I2C_FINISH` 时清空 `lcd_cmd_buf`，而冻结驱动把 READ_ID/READ_BUFCOUNT 作为「写命令 + 独立读事务」两步 | 读阶段取不到命令，返回 0x00，guest `LCDUnit` init 抛 `OSError("LCD Unit init failed")` | 读事务回退使用 last-command 日志（`lcd_last`），READ_ID 正常返回 |

显示三款另有**地址口径差异**：冻结参考固件里的 `OLEDUnit`/`MiniOLEDUnit` 默认
`0x3C`（页面地址），而 batch8 模型沿用公共驱动默认 `0x3D`；证据用驱动的显式
`address=0x3D` 参数通过（`oled`/`mini-oled`）。`glass2` 冻结驱动默认 `0x3C` 与
模型一致，直接默认地址通过。`lcd` 也用显式 `address=0x3D`。这些差异在 report
的 `observations`/`blocker` 中记录，不声称 0x3C/0x3D 冲突已解决。

## 结论

12 款各建 1 个可见 session，均在 guest 内运行参考固件自带的**原始冻结 UIFlow2
驱动**（`mic` 无 Unit 驱动，只能 `machine.ADC`/`machine.Pin`），经真实 SoC
I2C/UART/GPIO 控制器读写，没有 host 端直写驱动返回值：

| Unit | 主机/端口 | 原始驱动类 | 结果 |
| --- | --- | --- | --- |
| `pahub-v21` | cores3 port-a | `PAHUBUnit` (0x70) | PASS |
| `gps-v11` | cores3 port-a（官方 PORT.C） | `GPSUnit`（AT6668 NMEA） | PASS（baud 页面值 unresolved） |
| `gps-sma` | cores3 port-a（官方 PORT.C） | `GPSUnit`（同 AT6668 路径） | PASS（baud 页面值 unresolved） |
| `lcd` | cores3 port-a | `LCDUnit`（显式 0x3D，0152 修复） | PASS |
| `mini-can` | cores3 port-a（官方 PORT.C） | `CANUnit`（m5can/TWAI） | **BLOCKED**（Unit runtime 无 CAN attachment lane） |
| `oled` | cores3 port-a | `OLEDUnit`（M5.addDisplay，显式 0x3D） | PASS |
| `mini-oled` | cores3 port-a | `MiniOLEDUnit`（M5.addDisplay，显式 0x3D） | PASS |
| `glass2` | cores3 port-a | `Glass2Unit`（M5.addDisplay，默认 0x3C） | PASS |
| `nbiot-cn` | cores3 port-a（官方 PORT.C） | `NBIOTUnit`（SIM7020 AT） | PASS（仅字节层） |
| `lora-e220-920` | cores3 port-a（官方 PORT.C） | `LoRaE220JPUnit`（0xC0/C1 + send） | PASS（仅字节层） |
| `lorawan-us915` | cores3 port-a（官方 PORT.C） | `LoRaWANUnit`（ASR650x 驱动/STM32WLE5 产品） | **BLOCKED**（AT 字节未到达 Unit UART lane） |
| `mic` | cores3 port-a（官方 PORT.B） | `machine.ADC` + `machine.Pin`（无 Unit 驱动） | PASS（driver-gap，仅 ADC/comparator fixture） |

**端口替换说明**：`gps-v11`/`gps-sma`/`nbiot-cn`/`lora-e220-920`/`lorawan-us915`/
`mini-can` 官方在 PORT.C、`mic` 官方在 PORT.B，当前 host-port 注册表只准入
`cores3/PORT.A`，因此这些 session 使用 cores3 PORT.A 的 GPIO 2/1 作为 harness
接线；guest 的 SoC 控制器路径真实执行，**官方连接器物理接线未被验证**。每条
report 的 `official_port`/`runtime_port_substitution` 记录替换。

关键 controller-backed 观测（完整值见 `summary.json` 与 `report-<unit>.json`）：

- `pahub-v21`：guest 读 mask 0 → select 3 → 8 → select 5 → 40 → release 3 → 32；
  QOM channel-mask=0x20、channel-writes≥3、dip-address=0x70、i2c-address=0x70。
- `gps-v11`/`gps-sma`：guest 解出 `2242.10772N`/`11348.64472E`、时间
  `10:44:23`（UTC+8）、日期 `01/11/22`、卫星 14、海拔 52.1、航向 90.5、
  速度 18.52 kph；QOM `nmea-lines` fixture、`injected-lines`、`baud`=9600
  fixture。**冻结驱动硬编码 9600、页面写 115200：guest 无法暴露实际波特率，
  页面值 unresolved/NOT validated，只记录 9600 fixture。**
- `lcd`：guest `LCDUnit(i2c, address=0x3D)` init 通过（0152 修复 READ_ID 读事务），
  `fillScreen`/`fillRect` 后 QOM commands>0、pixels>0、framebuffer-crc 变化。
- `oled`/`mini-oled`/`glass2`：M5.addDisplay 组合成功，guest 清屏 + 矩形后 QOM
  commands/data-bytes/pixels/framebuffer-crc 变化；controller 分别为
  sh1107/ssd1315/ssd1309。**显示光学/亮度/寿命 NOT RUN。**
- `nbiot-cn`：guest `NBIOTUnit` 构造成功；QOM tx-hex =
  `AT`/`AT+CRESET`/`AT+CFUN=1`/`AT+CGSN` 字节流，frames-sent≥1。
  **SIM7020C AT/URC/入网顺序 unresolved；CN 频段/RF/SIM/TLS/MQTT NOT RUN。**
- `lora-e220-920`：guest `setup()` 0xC0 等长回显通过、`send()` 写入
  `>HB` 目标头；QOM tx-hex 含 `c0…` 配置帧与 `432107` 发送头，config-hex
  为 8 字节配置镜像。**920 RF/天线/距离/Telec NOT RUN；433 证据不转授。**
- `lorawan-us915`：**BLOCKED** —— 冻结 `unit/lorawan.py` 继承 ASR650x 驱动而
  产品是 STM32WLE5/RAK3172；guest 构造与 get_DevAddr/DevEui/AppEui 调用完成但
  **没有 AT 字节到达 Unit UART lane**（tx-hex 空），字节层无法断言，不冒充 PASS。
- `mini-can`：**BLOCKED** —— session 创建被拒绝（`QEMU Unit model/state contract
  is incomplete`）：Unit runtime 没有 CAN attachment/frame lane（catalog
  rx-frames/tx-frames 契约与 batch7 CAN client 属性不匹配）；不伪造 CAN 帧。
- `mic`：guest `machine.ADC` 读到 raw 33832（1600mV fixture）、比较器 `Pin`=1；
  QOM analog-mv=1600、digital-level=true、adc-samples≥1。`read_uv()` 因 QEMU S3
  ADC 校准 eFuse 未烧录而不可用（显式边界）。**无 public Unit MIC 驱动（driver
  gap）；声学/阈值/SNR/频率响应 NOT RUN。**

每个会话在停止前取得 evidence ZIP，停止使用 `purge=0` 并回读保留 history。

## 复现

```bash
# 1) QEMU：canonical 32 层链到 0151 + 0152
rm -rf .work/native-lock-source/qemu/build
cd .work/native-lock-source/qemu && ./configure ... && ninja -j10 qemu-system-xtensa
cp build/qemu-system-xtensa ../../M5StopWatch-QEMU/build/qemu/build/
xattr -c ../../M5StopWatch-QEMU/build/qemu/build/qemu-system-xtensa
codesign --force --sign - ../../M5StopWatch-QEMU/build/qemu/build/qemu-system-xtensa
# 2) 独立 Device Service（8801，独立 state/token，host-image；不碰 8787/8799）
M5_SERVICE_FLASH_MODE=host-image \
M5_QEMU_XTENSA="$PWD/.work/M5StopWatch-QEMU/build/qemu/build/qemu-system-xtensa" \
M5_QEMU_XTENSA_ROM_DIR="$PWD/.work/M5StopWatch-QEMU/build/qemu/pc-bios" \
  PYTHONPATH=platform/tools python3.12 platform/tools/serve.py 8801 \
  --bind 127.0.0.1 --state-dir .work/unit-batch8-service-8801 \
  --api-token "$(cat .work/unit-batch8-service-8801.token)"
# 3) 每款一个可见 session
export M5_SERVICE_API_TOKEN="$(cat .work/unit-batch8-service-8801.token)"
PYTHONPATH=platform/tools python3.12 tests/units/run_batch8_cases.py \
  --api-url http://127.0.0.1:8801 --case lcd --out-dir .work/unit-batch8-evidence
```

`mini-can`/`lorawan-us915` 预期 `BLOCKED`；其余 10 款预期 `PASS`。原始
ZIP/帧/串口日志留在本地忽略的 `.work`，仓库只提交摘要、哈希与复现命令。

## 未覆盖与边界

- 全部物理语义：显示光学/透明区、GNSS RF/天线、蜂窝 RF/网络/SIM、LoRa RF/Telec、
  LoRaWAN/US915 Join/FCC、CAN 电气/仲裁/终端、声学——均 `NOT RUN`；
- 显示地址 0x3C/0x3D 三款互斥与冻结驱动/页面/模型地址差异未解决，用显式地址
  取得证据并记录；
- GPS 页面 115200 vs 冻结驱动 9600 未实测钉（guest 无法暴露 baud）；
- `mini-can`/`lorawan-us915` 维持 planned，不转授 10 款 PASS；
- 本结果只覆盖 cores3 + 记录固件 SHA + 记录 QEMU 二进制 SHA，不转授其他主机/固件。
