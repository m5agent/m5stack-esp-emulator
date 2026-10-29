# 2026-10-29：StopWatch / StickS3 / Core2 UIFlow2 接口复测（最新 QEMU）

## 范围

在源码 `66af02cc6061bded00659ee13632f5e3a9a397dc` 和当前 QEMU
`05a43941c087642f274a4521c495edde88269ec1f99187742b509cc98ac49d59`
上，并发复测 StopWatch、StickS3 和 Core2 的 stock UIFlow2 `v2.5.3`
接口。三台使用相互隔离的 Device Service、state、token 和输出目录；
每台设备内部串行创建可见 session。

全部结果均为 **virtual-device validation**。物理硬件、RF、声学、光学、
电气测量和物理 PSRAM/cache timing 均为 `NOT RUN`。

| 设备 | 原厂基础镜像 SHA256 |
| --- | --- |
| StopWatch | `99d6482befe094de47bf68ce43618d3868bd62fb1fc72f0b55c0d0c2ea4e7f8d` |
| StickS3 | `c08196024019273ccadee9b4b3da303567f7ab206fa14edd1af283f04f6e98d8` |
| Core2 | `b228c0e2d877e77a8a352e917ed84f4da8ea92d15b25e28f431a2999620fe3c4` |

## 结论

没有发现由本次 QEMU 更新引入的稳定接口回归。三台 board/system/shared
基线、可执行通信和板级组继续通过；StopWatch/Core2 M5UI 507 项仍无漏测。
stock 固件的既有 SDK 缺陷稳定保留，相同 stock base 上加载 hash-pinned
candidate 后全部通过。

本轮没有需要修改模拟器源码的新功能缺陷。发现的两类失败均已用控制实验
分类：

- Core2 三设备首轮并发时，`WLAN.active(False) -> active(True) -> scan`
  一次未看到 fixture AP；隔离重跑和随后 `4/4` 三设备并发重复均为
  `14/14 PASS`，保留为 transient concurrency control；
- StickS3 TLS candidate 首轮将 native UART-REPL 镜像误用 dupterm
  bootstrap，使用 `--uart-repl-bootstrap native` 后 `5/5 PASS`，属于
  harness control。

## 基线与通用协议

| 检查 | StopWatch | StickS3 | Core2 |
| --- | ---: | ---: | ---: |
| System runtime | `50 PASS + 1 STATE_PASS` | 同左 | 同左 |
| Shared corrections | `7/7` | `7/7` | `7/7` |
| Board display | `468x468 PASS` | `135x240 PASS` | `320x240 PASS` |
| Sockets | `23/23` | `23/23` | `23/23` |
| EasySocket | `57 PASS + 1 N/A` | 同左 | 同左 |
| MQTT | `42/42` | `42/42` | `42/42` |
| Network | `14/14` | `14/14` | `14/14`（隔离/重复控制） |
| EzData | `17/17` | `17/17` | `17/17` |
| ESP-NOW | `12 PASS + 5 STATE_PASS + 1 CONFIGURED_UNVERIFIED` | 同左 | 同左 |
| Native ESP-NOW | `21 PASS + 21 STATE_PASS + 3 CONFIGURED_UNVERIFIED` | 同左 | 同左 |
| Audio player | `15/15` | `15/15` | `NOT_EXPORTED` |
| Audio recorder | `12/12` | `12/12` | `NOT_EXPORTED` |

ESP-NOW 仍是 opt-in 的同 guest controller TX/RX DMA loopback。外部 peer、
PMK 加密 payload、跨设备 fabric、丢包/重试、RF 和 timing 未验证。

## Stock 缺陷与 candidate

| 组 | Stock 结果 | 失败点 | Candidate |
| --- | ---: | --- | ---: |
| HTTP / requests2 | `15 PASS + 1 FAIL` | `requests2.urlencode` | 三台各 `2/2` |
| Modbus TCP async | `42 PASS + 8 ERROR` | 八个 async 方法访问不存在的 `Loop.sock_recv` | 三台各 `50/50` |
| TLS | `3 STATE_PASS + 2 ERROR` | 固件证书 epoch 已过期 | 三台各 `5/5` |
| Core2 `m5ble-server` | `21 PASS + 1 ERROR` | `Server.get_client(0)` 对 `set` 下标 | 叠加 `0021+0025` 后 `22/22` |

Candidate source SHA256：

- requests2：`40d1a98d2413b379e14c1732b329004feb8b6675655ae2548931ef2dd16ba052`
- Modbus async：`86125ad2cff3929849709a6670750847835f8e8fa3f9d0c493d37fe0042ed37a`
- Core2 M5BLE：`d82c1aec593de997d2d63f6bc409f6786a3b90e8b4b793c722cb9c61b8c82703`

TLS candidate 的 composed firmware SHA256 分别为 StopWatch
`d66ba3c6…`、StickS3 `87bf48f9…`、Core2 `6a071716…`。这些是
candidate lane，不能表述为默认 stock 镜像已经修复。

## M5UI

StopWatch 和 Core2 各执行 28 个文档 widget 类、505 个 widget 方法和
`m5ui.init/deinit`，共 29 个独立 READY session、507 个可观察结果、零漏测。

| 状态 | 数量 |
| --- | ---: |
| `STATE_PASS` | 409 |
| `PENDING_FRAME_OR_INPUT` | 80 |
| `PENDING_FRAME_OBJECT_REMOVAL` | 3 |
| `DOCUMENTATION_MISMATCH` | 11 |
| `EXPECTED_UNSUPPORTED` | 1 |
| `FAIL` | 3 |

Stock 三失败仍为：

- `M5Canvas.draw_triangle`；
- `M5Image.set_scale(1.5)`；
- `M5Spinbox.set_step(5)`。

StopWatch/Core2 candidate 均为 `4/4 STATE_PASS + 2/2 FRAME_PASS`。
Frame SHA256 分别保持 `19523193…` 和 `5a074d29…`，与此前 QEMU
证据一致。StickS3 当前 stock 镜像不导出 `m5ui`。

## BLE 与板级接口

- StopWatch/StickS3 stock `ble-nus` 和 `m5ble-server` 继续为
  `BLOCKED_MODEL`；client 组为 `NOT_RUN / BLOCKED_FIXTURE`。
- Core2 `core2-native-hci` + matching ELF
  `5bec056bb775bcc94bc020e4fa411def097ea17b108dcd597d9cdab3c347db49`
  的 stock `ble-nus` 为 `8/8 PASS`。
- Core2 stock `m5ble-server` 为 `21 PASS + 1 ERROR`，candidate
  `22/22 PASS`。
- 三台通用 hardware matrix 各
  `115 CALL_OK + 66 API_ASSERTION_PASS + 1 OBSERVED`。
- StopWatch 重跑 peripherals、M5IOE1、M5PM1、vibration；
  StickS3 重跑 peripherals、IR TX/RX；Core2 重跑 peripherals、
  INA3221、IMU、AXP192、Mic、Speaker/audio。

所有设备本地 case 都取得 evidence ZIP、frame 和 host action 记录，
`purge=0` 停止后 runtime PID、Flash 和 companion 清理通过。

## 回归与清理

- 平台测试：`1432` 项 `OK`，`1` 项既有 skip；
- `runtime_coverage`、`peripheral_catalog`、`qemu_profiles`、
  `project_snapshot` 和 `git diff --check` PASS；
- 三台 QEMU 在全部报告中均为 `05a43941…`，没有混入其他 runtime；
- 三个隔离 Device Service 和所有 QEMU/BLE peer 已停止，无残留进程；
- 原始串口、frame、PCM、pcap、ZIP 和完整日志只保留在 ignored `.work/`。

## 未关闭项

- StopWatch/StickS3 stock internal-controller GATT；
- stock requests2、Modbus async、TLS epoch、Core2 `get_client` 和
  M5UI 三缺陷（仅 candidate lane 修复）；
- BLE pairing/security、RF、天线、共存和 controller bit-exact；
- 外部或加密 ESP-NOW、跨设备 fabric 和丢包/重试；
- Core2 legacy UIFlow `RUNTIME-03` normal-WDT 启动与应用帧；
- 物理硬件同路径、声学、光学、电气和物理 PSRAM/cache timing。

机器摘要见 [summary.json](summary.json)。
