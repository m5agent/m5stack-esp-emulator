# Batch-10 a/b 类 18 款登记与最小模型状态（2026-11-03）

本页记录 batch-10 收口登记的落地结果，承接
[`2026-11-03-batch10-protocols.md`](2026-11-03-batch10-protocols.md) 与
`2026-11-03-batch10-catalog-draft.json`。catalog/profile 从 **142→160**，
184 个 unit 产品至此全部有登记或明确边界结论。全部 18 款保持 **planned**、
hosts 空；本批**不做 guest/Device Service 证据**，只有 6 款建了模型的
Unit 做了离线 QOM smoke。

## 实现 vs 仅登记

| Unit | 状态 | 实现/边界 |
| --- | --- | --- |
| `dcssr` U140 | 建模型（planned） | 复用 `CONTROL_ACSSR` I2C 0x50：0x00 relay/0x10 RGB/0xFE fw/0x20 addr；Modbus/RS485 模式与 SSR 电气/隔离/寿命/热 NOT RUN |
| `puzzle` U193 | 建模型（planned） | 复用 hex/neohex RMT 捕获，64×WS2812E；无 public Unit 驱动，WS2812E vs WS2812C 时序/光学/级联方向 unresolved |
| `dof6` U228 | 建模型（planned） | 仅 BMI270 0x68 子集（accel/gyro/temp/whoami，复用 0145 `US_BMI270`）；init blob/量程/motion NOT RUN |
| `dof9` U229 | 建模型（planned） | 仅 BMI270 0x68 子集；**BMM350 0x14 无驱动/寄存器表，未建模**；磁力/heading NOT RUN |
| `dof10` U230 | 建模型（planned） | 仅 BMI270 0x68 子集；**BMM350 0x14/SPA06 0x76 未建模，不用 BMP280 替代 SPA06**；气压/高度 NOT RUN |
| `asr` U194 | 建模型（planned） | UART 115200 fixture responder + AA55 `<id>` 55AA 字节层解析（command-id）；语音/AEC/麦克风/扬声器 NOT RUN |
| `ina226-1a` U200-1A | **仅登记** | 无 Unit driver/寄存器表、TI datasheet 未钉；只写 planned 契约+blocker，不建模型 |
| `roller485` / `roller485-lite` U182 | **仅登记** | RS485/I2C 0x64 电机；内部固件/协议外部文档；不建模型 |
| `rollercan-lite` U188-Lite | **仅登记** | CAN/I2C 0x64 电机；内部固件/帧表外部；不建模型 |
| `byteswitch` U191 / `bytebutton` U192 | **仅登记** | I2C 0x46/0x47、8 开关/按键+9 RGB；协议表不可读；不建模型 |
| `step16` U198 / `timerpwr` U189 / `mq` U199 | **仅登记** | I2C 0x48/0x56/0x11；内部寄存器/调度/加热表不可读；不建模型 |
| `8servos2-chain` U223 / `cat1-cn` U204 / `chainbus` U212 | **仅登记** | UART Chain/ML307R/ChainBus；协议/AT 表外部；不建模型 |

## QEMU 0152

`0152-unit-batch10ab.patch`（base canonical 32 层 through 0151；0120 起第 33
层；0153+ 下一号）：

- `m5_unit_i2c_controls.c`：`dcssr` 加入 controls 支持列表并别名
  `CONTROL_ACSSR`（0x50，寄存器语义同 U139）；
- `m5_unit_gpio.c`：`puzzle` 加入 GPIO 支持列表和 LED RMT 分支
  （`leds=64`）；`asr` 加入 UART 支持/S3-only/TX 捕获/responder/realize
  分支，并新增 `command-id`（AA55 `<id>` 55AA 解析）；
- `m5_unit_i2c_sensors.c`：`dof6`/`dof9`/`dof10` 加入 sensors 支持列表，
  只 attach BMI270 0x68 子集（accel/gyro/temp/whoami）；BMM350/SPA06 未建模。
- `ina226-1a` 和 11 款 b 类**没有** QEMU 代码（只登记契约）。

离线 QOM smoke（S3 `m5cores3`，无 guest firmware）：6/6 attach 成功——
`dcssr` relay-level/led-rgb/fw-version/i2c-address=0x50；
`puzzle` 64 灯数组/led-frames/incomplete-frames；`dof6/dof9/dof10`
accel/gyro/temp/whoami=0x24；`asr` responses-hex/tx-hex/frames-sent/
frames-injected/command-id。该 smoke **不是** functional PASS，不产生 guest
证据；`ina226-1a` 与 b 类无模型、无 smoke。

## 计数与边界

- catalog/profile **142→160**（18 条 planned，hosts 空，无
  `virtual_device_evidence`）。
- visual audit 18 条 + marker `all-160-products`。
- 地址/冲突：dcssr 0x50；ina226-1a 0x41 与 ina226-10a 冲突；
  byteswitch 0x46；bytebutton 0x47；step16 0x48；timerpwr 0x56；mq 0x11；
  roller485/rollercan-lite 0x64；dof6 BMI270 0x68 与 mini-imu 系冲突，
  dof9/dof10 BMM350 0x14 未建模，dof10 SPA06 0x76 与 env 系冲突；
  puzzle PORT.B 单线；asr/cat1-cn/chainbus/8servos2-chain 共用 UART。
- 光学/电机/SSR 电气/隔离/传感精度/RF/蜂窝/语音/气体/电池/热等语义全部
  NOT RUN；不能把本页 QOM smoke 当 PASS。

## 验证

- `0152-unit-batch10ab.patch`：`git apply --check` + reverse OK。
- 离线 QOM smoke 6/6。
- 全量测试 + 四 check 结果见 commit 报告。
