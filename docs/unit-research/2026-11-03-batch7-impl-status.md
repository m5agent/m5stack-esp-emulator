# Unit 第七批剩余 7 款实现状态（0145）

日期：`2026-11-03`。范围：batch7 研究中剩余 7 款 Unit 的 QEMU 数据面/planned
契约实现状态。本页是**实现依据**，不是 guest/Device Service 证据；所有条目
保持 `planned`，profil 无 host，离线 QOM smoke 只验证模型注册/属性/fixture，
不运行参考固件、不宣称功能 PASS。研究依据见
[批次 7 协议研究](2026-11-02-batch7-protocols.md)。

补丁：`patches/qemu-m5stack-peripherals/0145-unit-batch7b.patch`
（`patch_sha256 = eb1ef3e9dfa02951b7bec975b6243302169c39cd828b25244a200e3738916cf2`），
位于 canonical 链 0144 之后（0120 起第 26 层）。catalog/profile 111→118。

| Unit | SKU | 实现状态 | 数据面/契约 | 边界 |
| --- | --- | --- | --- | --- |
| `hex` | A045 | 已实现（复用） | 37-LED RMT 捕获（alias `neohex`）：`led-rgb`/`led-frames`/`incomplete-frames` | public 源无 `unit/hex.py`（driver-gap）；SK6812 vs WS2812C 时序/字节序 unresolved；PORT.B 冲突；光学/功率/级联 NOT RUN |
| `mini-pdm` | U089 | **DEFER 未实现** | 仅 planned 契约（pcm-frame/sample-rate/frames/clock-hz），无 QEMU Unit 模型 | 无 public Unit PDM 驱动；SPM1423 PDM RX 是板级 I2S 路径，Unit attachment 无法绑定；不伪造 PCM fixture；声学 NOT RUN |
| `catm` | U128 | 已实现（fixture responder） | UART TX 捕获 + idle 响应注入：`tx-hex`/`frames-sent`/`frames-injected`/`responses-hex` | 不做 AT 解码；SIM7080G AT 固件/URC 顺序 unresolved；蜂窝 RF/网络/SIM/认证/TLS/MQTT NOT RUN |
| `catm-gnss` | U137 | 已实现（fixture responder） | 同 catm | AT+CGNSINF/GNSS 字段解析未建模；蜂窝+GNSS 不能并发（页面 FAQ）、COG 不是行进方向；GNSS RF/定位 NOT RUN |
| `lorawan-cn470` | U184-CN470 | 已实现（fixture responder） | 同 catm | **产品 STM32WLE5/RAK3172 vs 冻结驱动 ASR650x 错配 unresolved**；OTAA/ABP/Join/CN470 RF/占空比/认证 NOT RUN |
| `can` | U085 | 已实现（最小 CANBus 绑定） | cores3 `m5-canbus` 的 `CanBusClient`：`frames-observed`/`last-frame-hex`；QOM `inject-hex` 注入一帧 → `injected-frames` | 帧方向/过滤/位定时、外部收发器/隔离/终端/总线仲裁 NOT modeled；PORT.C 与 UART Unit 复用 pins；CAN attachment 语义有限 |
| `mini-imu-pro` | U171 | 已实现（最小复合模型） | BMI270 0x68：接受 CMD 0x7E init burst，`whoami=0x24`，accel/gyro/temperature fixture；BMP280 0x76 pressure；BMM150 简化 0x04–0x09 16-bit aux 窗口（raw=uT*16） | 完整 init blob 执行/aux 事务/量程配置未建模；0x68 与 mini-imu、0x76 与 env/bps/env-ii/env-iv 冲突；运动/磁力/姿态物理 NOT RUN |

## 离线 QOM smoke

在 S3 `m5cores3`、无 guest 固件下 attach 6 个已实现模型（hex、catm、
catm-gnss、lorawan-cn470、can、mini-imu-pro；mini-pdm DEFER）并验证：

- hex：37 灯 `led-rgb`、`led-frames`/`incomplete-frames` 属性注册；
- 三个 UART 单元：`responses-hex`/`tx-hex`/`frames-sent`/`frames-injected`
  注册，initial fixture 可读；
- can/mini-can：`inject-hex` 注入 `123#deadbeef` 后 `injected-frames=1`、
  `frames-observed=1`（`M5SW_CAN_ECHO=1` 下 peer 回环）、
  `last-frame-hex=123#deadbeef`；
- mini-imu-pro：双从机 attach（`bmi270`/`bmp280` child 路径）、fixtures
  （accel/mag/temperature/pressure）、`whoami=0x24`。

smoke **不覆盖** guest I2C/UART/CAN 字节语义、LED 时序、AT 解码、CAN
位定时/仲裁或 IMU 物理；这些仍需参考固件 guest/Device Service 证据。

## 未覆盖/后续

- 7 款全部 `planned`、profile hosts 空；catalog runtime status `planned`。
- 证据任务需要为每款建可见 session、先 ZIP 后 `purge=0`、记录 QOM/serial/
  帧哈希；通过后才升 profile。
- 已知 unresolved：hex 驱动-gap/SK6812、mini-pdm 无 Unit 驱动、
  catm/catm-gnss/lorawan AT/URC、CAN attachment/电气、mini-imu-pro aux/量程。
- 本批未修改真实硬件语义；RF/蜂窝/光学/声学/运动/电气全部 `NOT RUN`。
