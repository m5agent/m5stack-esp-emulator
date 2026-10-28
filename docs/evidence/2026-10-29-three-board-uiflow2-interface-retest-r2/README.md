# 2026-10-29：StopWatch / StickS3 / Core2 UIFlow2 接口再次复测

## 范围

本轮在 StopWatch、StickS3 和 Core2 的当前原厂 UIFlow2 `v2.5.3`
镜像上，重新执行可用接口、板级外设、M5UI 方法矩阵和已选 stock SDK
candidate lane。三台使用相互隔离的本地 Device Service 并发执行，用户的
`8787` 服务和既有评审服务均未占用、停止或重启。

全部结果是 **virtual-device validation**。物理硬件、RF、声学、光学、
电气测量和物理 PSRAM/cache timing 均为 `NOT RUN`。

| 设备 | 原厂基础镜像 SHA256 |
| --- | --- |
| StopWatch | `99d6482befe094de47bf68ce43618d3868bd62fb1fc72f0b55c0d0c2ea4e7f8d` |
| StickS3 | `c08196024019273ccadee9b4b3da303567f7ab206fa14edd1af283f04f6e98d8` |
| Core2 | `b228c0e2d877e77a8a352e917ed84f4da8ea92d15b25e28f431a2999620fe3c4` |

统一 QEMU SHA256：

`9bf74439ddbe7225a64eb437290043729fb032525756adb834565ec412f8c197`

## 系统与共享基线

| 检查 | StopWatch | StickS3 | Core2 |
| --- | ---: | ---: | ---: |
| System runtime | `50 PASS + 1 STATE_PASS` | `50 PASS + 1 STATE_PASS` | `50 PASS + 1 STATE_PASS` |
| Shared corrections | `7/7` | `7/7` | `7/7` |
| Board display baseline | `468x468 PASS` | `135x240 PASS` | `320x240 PASS` |

每个 baseline session 都取得独立 evidence ZIP，停止后确认 runtime PID
gone、历史保留且 companion 清理完成。

## 通信与协议

| 组 | StopWatch | StickS3 | Core2 |
| --- | ---: | ---: | ---: |
| Sockets | `23/23` | `23/23` | `23/23` |
| EasySocket | `57 + 1 N/A` | `57 + 1 N/A` | `57 + 1 N/A` |
| MQTT | `42/42` | `42/42` | `42/42` |
| Network | `14/14` | `14/14` | `14/14` |
| EzData | `17/17` | `17/17` | `17/17` |
| ESP-NOW | `12 PASS + 5 STATE_PASS + 1 CONFIGURED_UNVERIFIED` | 同左 | 同左 |
| Native ESP-NOW | `21 PASS + 21 STATE_PASS + 3 CONFIGURED_UNVERIFIED` | 同左 | 同左 |
| Audio player | `15/15` | `15/15` | `NOT_EXPORTED` |
| Audio recorder | `12/12` | `12/12` | `NOT_EXPORTED` |

ESP-NOW 仅为 opt-in 同 guest controller TX/RX DMA loopback。外部 peer、
PMK 加密 payload、跨设备 fabric、丢包/重试、RF 和 timing 均未验证。

## Stock 失败与 candidate lane

三台 stock 固件继续稳定复现同一组 SDK 缺陷：

| 组 | Stock 结果 | 失败点 |
| --- | ---: | --- |
| HTTP / requests2 | `15 PASS + 1 FAIL` | `requests2.urlencode` |
| Modbus TCP async | `42 PASS + 8 ERROR` | 八个 async 方法访问不存在的 `Loop.sock_recv` |
| TLS | `3 STATE_PASS + 2 ERROR` | 固件证书 epoch 过期 |
| Core2 `m5ble-server` | `21 PASS + 1 ERROR` | `Server.get_client(0)` 对 `set` 做下标访问 |

同一 stock firmware 上的 hash-pinned source/candidate lane：

| Candidate | 三设备结果 |
| --- | --- |
| requests2 `40d1a98d…` | 三台各 `2/2 PASS` |
| Modbus async `86125ad2…` | 三台各 `50/50 PASS` |
| TLS candidate firmware | StopWatch `5/5`、StickS3 `5/5`、Core2 `5/5` |
| M5UI native marshalling | StopWatch/Core2 各 `4/4 STATE_PASS + 2/2 FRAME_PASS` |
| Core2 `m5ble` stacked `0021 + 0025` | `22/22 PASS` |

Core2 TLS base candidate SHA256 分别为 StopWatch
`edcd9a392f1ff5e5741c8331ae41ea18b915ae50b2ff54c173110c65c532e6a6`、
StickS3 `2e8386057fab9d384489651a544e30ce4edaf86586e1f4ce7f588469439af6aa`、
Core2 `204def8c601c29b7fa4af83b767c3fd8ced9c6b12815a709c450fb5b80a2e2c6`。
Core2 m5ble candidate SHA256 为
`d82c1aec593de997d2d63f6bc409f6786a3b90e8b4b793c722cb9c61b8c82703`。

这些是 candidate lane，不能表述为原厂冻结固件已经修复。

StopWatch 与 StickS3 的首次 TLS candidate 尝试在并发峰值下未到达 guest
marker；隔离重跑分别以 session `0ba63059…` 和 `9d2bce74…` 得到
`5/5 PASS`。首次运行作为启动时序 control 保留，不记成 TLS 功能失败。

## M5UI 全量方法矩阵

StopWatch 和 Core2 各执行 28 个文档 widget 类、505 个 widget 方法，
另执行 `m5ui.init/deinit` 两个 lifecycle 结果：

| 状态 | 数量 |
| --- | ---: |
| `STATE_PASS` | `409` |
| `PENDING_FRAME_OR_INPUT` | `80` |
| `PENDING_FRAME_OBJECT_REMOVAL` | `3` |
| `DOCUMENTATION_MISMATCH` | `11` |
| `EXPECTED_UNSUPPORTED` | `1` |
| `FAIL` | `3` |

两台的 29 个批次均到达 READY、全部结果已观察，最终 frame 分别为
StopWatch `466x466`、Core2 `320x240`。stock 三失败仍是：

- `M5Canvas.draw_triangle`；
- `M5Image.set_scale(1.5)`；
- `M5Spinbox.set_step(5)`。

StopWatch candidate frame SHA256：
`195231931ebca534a6b1377a84f6057f570236efc290e5c3e552fe60880ae91b`。

Core2 candidate frame SHA256：
`5a074d2987258112f79cecc800578df7325e6f35c32ceace859b828c8f942403`。

0074 的 Core2 panel DMA 修复在本轮重新执行后仍得到 triangle/image
`2/2 FRAME_PASS`，画面无此前条带。StickS3 当前 stock 镜像不导出
`m5ui`。

## BLE

- StopWatch/StickS3 stock `ble-nus` 和 `m5ble-server` 仍在真实 GATT
  前被 internal-controller 模型阻塞；Core2 的 native-HCI 结果不转移给它们。
- Core2 使用 `core2-native-hci` 和 matching ELF
  `5bec056bb775bcc94bc020e4fa411def097ea17b108dcd597d9cdab3c347db49`
  独立重跑 `ble-nus` 为 `8/8 PASS`，peer 实际完成连接、GATT discovery、
  CCCD 订阅、写入 `M5_CORE2_UNIFIED` 和精确通知
  `ACK:M5_CORE2_UNIFIED`。
- 首轮并发 M5UI 时 `deinit` 在 GATT/ACK 完成后 `7 PASS + 1 TIMED_OUT`；
  该失败保留。协议 probe 在显式断连后等待 2 秒，让自动重广告和 BLE task
  收口，随后 stock 与 candidate 各两轮均通过。该 settle 只描述测试时序。
- `ble-client`/`m5ble-client` 当前 peripheral-role 准入不覆盖这三台，
  因此记为 `NOT_RUN/NOT_ADMITTED`，不当作固件失败或 PASS。

## 板级接口

三台通用硬件 probe 均为：

`115 CALL_OK + 66 API_ASSERTION_PASS + 1 OBSERVED (M5.Mic.record.pcm)`

Mic 的原始 PCM 另行由 recorder 数据面 oracle 验证，`OBSERVED` 不被当成
单独功能 PASS。

| 设备 | 本轮重跑板级组 |
| --- | --- |
| StopWatch | peripherals、M5IOE1、M5PM1、vibration |
| StickS3 | peripherals、BMI270/按键/PWR、IR TX、IR RX |
| Core2 | peripherals、INA3221 power monitor、MPU6886 IMU、AXP192、Mic、Speaker/audio |

M5PM1 使用官方 `m5pm1.py` fixture；首次缺少 fixture 的 ImportError
保留为 harness control。Core2 AXP192 显式使用
`M5SW_CORE2_PMIC=axp192`，不是默认 AXP2101 路径。首次 AXP192 尝试在
marker 触发 touch 早于 guest 输入就绪时停住；最终隔离重跑在 QOM 动作后
等待 1 秒再注入 touch，完成 `5/5` host actions 与最终画面。

## 未关闭项

- StopWatch/StickS3 stock internal-controller GATT；
- BLE pairing/security、RF、天线、共存和 controller bit-exact；
- 外部或加密 ESP-NOW、跨设备 fabric 和丢包/重试；
- 三个 stock SDK 缺陷和 Core2 `Server.get_client` 仅由 candidate lane 修复；
- Core2 legacy UIFlow `RUNTIME-03` normal-WDT 启动和应用帧；
- 物理硬件同路径、物理 PSRAM/cache timing、声学和电气验证。

## 复现入口

```bash
PYTHONPATH=platform/tools:.work/py312 python3.12 \
  tests/uiflow2/api_sweep/run_guest.py \
  --api <isolated-device-service> --device <device> \
  --source tests/uiflow2/api_sweep/probe_system_runtime.py \
  --done-marker SYSTEM_RUNTIME_DONE --out-dir /tmp/m5-system

PYTHONPATH=platform/tools:.work/py312 python3.12 \
  tests/uiflow2/api_sweep/run_protocols.py \
  --execute --api <isolated-device-service> --device <device> \
  --group <group> --token-file <private-token-file> \
  --out-dir /tmp/m5-protocol

PYTHONPATH=platform/tools:.work/py312 python3.12 \
  tests/uiflow2/api_sweep/run_m5ui_matrix.py \
  --api <isolated-device-service> --device <device> \
  --token-file <private-token-file> --out-dir /tmp/m5-m5ui
```

`run_m5ui_matrix.py` 为每类控件创建独立可见 session，并逐个保存
READY、方法结果、frame/evidence、session 和 cleanup；StickS3 当前
stock 镜像不导出 `m5ui`，因此不进入该矩阵。

原始串口、frame、PCM、pcap、ZIP 和完整程序只保留在 ignored `.work/`。
本页和[机器摘要](summary.json)只保留计数、哈希、失败分类和复现边界。
