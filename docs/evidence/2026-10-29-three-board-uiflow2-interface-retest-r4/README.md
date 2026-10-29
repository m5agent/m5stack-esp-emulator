# 2026-10-29：StopWatch / StickS3 / Core2 UIFlow2 接口复测 r4

## 范围

在源码 `0769ae7c0136f81aa34d85a58588c67fd879fc19` 和当前
QEMU `dd4b1b34a4003a6fe84263974efade9d8d85e584fcd7397bc0f13b2d77337435`
上再次并发复测 StopWatch、StickS3 和 Core2 的 stock UIFlow2 `v2.5.3`
接口。三台使用独立 Device Service、state、token 和输出目录；所有功能
执行都通过可见 `/api/v1` session，停止时使用 `purge=0`。

全部结果均为 **virtual-device validation**。物理硬件、RF、天线、
BLE 安全、声学、光学、电气测量和物理 PSRAM/cache timing 均为
`NOT RUN`。

| 设备 | 原厂基础镜像 SHA256 |
| --- | --- |
| StopWatch | `99d6482befe094de47bf68ce43618d3868bd62fb1fc72f0b55c0d0c2ea4e7f8d` |
| StickS3 | `c08196024019273ccadee9b4b3da303567f7ab206fa14edd1af283f04f6e98d8` |
| Core2 | `b228c0e2d877e77a8a352e917ed84f4da8ea92d15b25e28f431a2999620fe3c4` |

## 结论

没有发现由当前 QEMU 引入的稳定接口回归。三台的 system/shared/board
基线、通信、音频、ESP-NOW、通用 hardware matrix 和设备本地 case 均保持
通过；StopWatch/Core2 M5UI 继续得到 507 个可观察结果且零漏测。

Core2 network 在本次三设备首轮冷启动并发中直接得到 `14/14 PASS`，
优于 r3 首轮的 `13/14`；不再出现 re-activate 后立即 scan 的瞬时控制问题。

stock 固件既有缺陷与 r3 完全相同：

- `requests2.urlencode`；
- 八个 Modbus TCP async 方法访问不存在的 `Loop.sock_recv`；
- stock TLS 证书 epoch 已过期；
- StopWatch/Core2 的 `M5Canvas.draw_triangle`、
  `M5Image.set_scale(float)` 和 `M5Spinbox.set_step(int)`；
- Core2 `m5ble.Server.get_client(0)` 对 `set` 下标。

以上均为 **stock UIFlow2 SDK/固件** 结果。相同基础镜像上加载
hash-pinned source candidate 后，协议与 M5UI 修正均重新通过，因此本轮没有
把 SDK 缺陷误归因为模拟器控制面或 QEMU 数据面回归。

## 基线与通用协议

| 检查 | StopWatch | StickS3 | Core2 |
| --- | ---: | ---: | ---: |
| System runtime | `50 PASS + 1 STATE_PASS` | 同左 | 同左 |
| Shared corrections | `7/7` | `7/7` | `7/7` |
| Board display | `468x468 PASS` | `135x240 PASS` | `320x240 PASS` |
| Sockets | `23/23` | `23/23` | `23/23` |
| EasySocket | `57 PASS + 1 N/A` | 同左 | 同左 |
| MQTT | `42/42` | `42/42` | `42/42` |
| Network | `14/14` | `14/14` | `14/14` |
| EzData | `17/17` | `17/17` | `17/17` |
| ESP-NOW | `12 PASS + 5 STATE_PASS + 1 CONFIGURED_UNVERIFIED` | 同左 | 同左 |
| Native ESP-NOW | `21 PASS + 21 STATE_PASS + 3 CONFIGURED_UNVERIFIED` | 同左 | 同左 |
| Audio player | `15/15` | `15/15` | `NOT_EXPORTED` |
| Audio recorder | `12/12` | `12/12` | `NOT_EXPORTED` |

ESP-NOW 仍是 opt-in 的同 guest controller TX/RX DMA loopback。外部独立
peer、PMK/LMK 加密 payload、跨设备 fabric、丢包/重试、RF 和 timing
仍为 `RUNTIME-06` 开放项。

## Stock 缺陷与 candidate

| 组 | Stock | Hash-pinned candidate |
| --- | ---: | ---: |
| HTTP / requests2 | `15 PASS + 1 FAIL` | 三台各 `2/2 PASS` |
| Modbus TCP async | `42 PASS + 8 ERROR` | 三台各 `50/50 PASS` |
| TLS | `3 STATE_PASS + 2 ERROR` | 三台各 `5/5 PASS` |
| Core2 `m5ble-server` | `21 PASS + 1 ERROR` | `22/22 PASS` |
| StopWatch/Core2 M5UI corrections | 三个已知 FAIL | 各 `4/4 STATE_PASS + 2/2 FRAME_PASS` |

TLS candidate composed firmware SHA256：

- StopWatch：`0b49d9aadbee22038bbe0c22f8f0ce3d4db3283d8f781c41cb9562540d3a1519`
- StickS3：`56eab792673221bcfb4b8669d0749347793ef38a3b353f364274d5cca4269981`
- Core2：`f6c5e99d200a78ebb2a3a4974ae176c58df60a9fdec1560038ee5ab3373da6b9`

M5UI candidate source 来自
`3a86d8f611b3639cca755a933e01a5a829771ef1`，patch SHA256
`a05eda779d819a7e50210da457a267be6be87ecdebb82e968fc370335ff77da7`；
实际三文件 preimage 全部匹配，source override 不改变 stock 固件身份。

## M5UI

StopWatch 和 Core2 各执行 28 个文档 widget 类、505 个 widget 方法和
`m5ui.init/deinit`，共 29 个独立 READY session、507 个可观察结果。

| 状态 | 数量 |
| --- | ---: |
| `STATE_PASS` | 409 |
| `PENDING_FRAME_OR_INPUT` | 80 |
| `PENDING_FRAME_OBJECT_REMOVAL` | 3 |
| `DOCUMENTATION_MISMATCH` | 11 |
| `EXPECTED_UNSUPPORTED` | 1 |
| `FAIL` | 3 |

Stock 三失败保持为 Canvas triangle、Image float scale 和 Spinbox integer
step。candidate 的四个状态及两个 frame oracle 全部通过；frame SHA256 分别
保持 `19523193…` 和 `5a074d29…`。StickS3 当前 stock 镜像不导出 `m5ui`。

## BLE 与板级接口

- StopWatch/StickS3 stock `ble-nus` 与 `m5ble-server` 继续为
  `BLOCKED_MODEL`；client 组为 `NOT_RUN / BLOCKED_FIXTURE`。
- Core2 stock `ble-nus` 使用 `core2-native-hci` 和 matching ELF，为
  `8/8 PASS`。
- Core2 stock `m5ble-server` 保持 `21 PASS + 1 ERROR`；candidate 为
  `22/22 PASS`。
- 三台通用 hardware matrix 各
  `115 CALL_OK + 66 API_ASSERTION_PASS + 1 OBSERVED`。
- StopWatch 完成 peripherals、M5IOE1、M5PM1、vibration；
  StickS3 完成 peripherals、IR TX/RX；Core2 完成 peripherals、
  INA3221、IMU、AXP192、Mic、Speaker/audio。

## 测试控制

- Core2 网络 runtime 必须显式设置 `M5_CORE2_RADIO_QEMU`。缺少时统一
  WiFi profile 返回 `503 qemu_wifi_backend_unavailable`；修正环境后，
  所有网络 group 首次并发执行通过。
- StopWatch TLS candidate 使用 `native` bootstrap 时，应用已启动但
  UART REPL 被占用；改回默认 `dupterm` 后 `5/5 PASS`。
- StickS3 TLS candidate 使用默认 `dupterm` 时 boot.py 报
  `ESP_ERR_INVALID_STATE`；改回 `native` 后 `5/5 PASS`。
- 候选 M5UI 必须先以 `program_transport=uart-repl` 创建 base session；
  缺少该声明时拒绝后续 `/program` 是预期准入行为。

这些控制均保留在 ignored `.work/`，不写成模拟器稳定回归。

## 回归与清理

- 三台报告实际加载的 runtime 均为 `dd4b1b34…`，没有混入其他 QEMU；
- 三个主 Device Service 与五个短生命 candidate 服务均已停止；
- 所有 QEMU、BLE peer 和 runner 进程均清理；
- 原始串口、frame、PCM、pcap、ZIP、Flash 和完整日志只保留在
  ignored `.work/`；
- 机器摘要见 [summary.json](summary.json)。

## 未关闭项

- stock HTTP/requests2、Modbus async、TLS epoch、Core2
  `Server.get_client` 和 M5UI 三缺陷；
- StopWatch/StickS3 stock internal-controller GATT；
- BLE pairing/security、RF、天线、共存和 controller bit-exact；
- 外部或加密 ESP-NOW、跨设备 fabric 和丢包/重试；
- Core2 legacy UIFlow `RUNTIME-03` normal-WDT 启动及应用帧；
- 物理硬件同路径、声学、光学、电气和物理 PSRAM/cache timing。
