# 2026-10-29：StopWatch / StickS3 / Core2 UIFlow2 全接口复测

## 范围

本轮在 StopWatch、StickS3 和 Core2 的当前原厂 UIFlow2 `v2.5.3`
镜像上，并发执行能覆盖的系统运行时、通信协议、M5UI、音频、ESP-NOW、
BLE 和已选板级外设接口。全部结果都是
**virtual-device validation**；物理硬件、RF、声学、光学和电气测量均为
`NOT RUN`。

统一 QEMU SHA256：

`fccfa931c032f8cae6b90e97ba5f98b1770fbf6856446c4db5f7950241e1fe90`

| 设备 | 原厂基础镜像 SHA256 |
| --- | --- |
| StopWatch | `99d6482befe094de47bf68ce43618d3868bd62fb1fc72f0b55c0d0c2ea4e7f8d` |
| StickS3 | `c08196024019273ccadee9b4b3da303567f7ab206fa14edd1af283f04f6e98d8` |
| Core2 | `b228c0e2d877e77a8a352e917ed84f4da8ea92d15b25e28f431a2999620fe3c4` |

三台使用相互隔离的 Device Service 并发执行。所有可见 session 都通过
`/api/v1` 创建，停止前取得 evidence ZIP，并以 `purge=0` 保留历史；
runtime PID、Flash 释放和 companion 清理均通过。原始串口、frame、PCM、
pcap、ZIP 和完整程序只保留在 ignored `.work/`。

## 系统与协议

| 检查 | StopWatch | StickS3 | Core2 |
| --- | ---: | ---: | ---: |
| System runtime | `50 PASS + 1 STATE_PASS` | `50 PASS + 1 STATE_PASS` | `50 PASS + 1 STATE_PASS` |
| Shared corrections | `7/7` | `7/7` | `7/7` |
| Sockets | `23/23` | `23/23` | `23/23` |
| MQTT | `42/42` | `42/42` | `42/42` |
| Network | `14/14` | `14/14` | `14/14` |
| EzData owned fixture | `17/17` | `17/17` | `17/17` |
| EasySocket | `57 PASS + 1 N/A` | `57 PASS + 1 N/A` | `57 PASS + 1 N/A` |

`STATE_PASS` 是 Core2 当前 UART duplicate-terminal 所有权边界，不是固件
失败；FAT/LittleFS、`select.poll`、TCP readiness、熵和标准蓝牙 UUID
等其余系统项均由 guest 数据面 oracle 判定。

## Stock 固件失败负控

三台冻结 stock 固件稳定复现同一组 SDK 缺陷：

| 组 | Stock 结果 | 失败点 |
| --- | ---: | --- |
| HTTP / requests2 | `15 PASS + 1 FAIL` | `requests2.urlencode` 未正确转义保留字符和 UTF-8 |
| Modbus TCP async | `42 PASS + 8 ERROR` | 八个 async 方法调用不存在的 `Loop.sock_recv` |
| TLS | `3 STATE_PASS + 2 ERROR` | 证书 epoch 过期 |

同一 runtime 上的 hash-pinned 候选路径：

- requests2 候选源码三台 `2/2 PASS`；
- Modbus async 候选源码三台 `50/50 PASS`；
- TLS candidate firmware 三台各 `5/5 PASS`，基础候选 SHA256 分别为
  StopWatch `edcd9a39…`、StickS3 `2e838605…`、Core2 `204def8c…`。

这些结果是 candidate lane，不能表述为原厂冻结固件已经修复。

## M5UI 全量方法矩阵

StopWatch 和 Core2 均执行了文档列出的 `28` 个 M5UI 类、合计 `505`
个方法。两台分类完全相同：

| 状态 | 数量 |
| --- | ---: |
| `STATE_PASS` | `407` |
| `PENDING_FRAME_OR_INPUT` | `80` |
| `PENDING_FRAME_OBJECT_REMOVAL` | `3` |
| `DOCUMENTATION_MISMATCH` | `11` |
| `EXPECTED_UNSUPPORTED` | `1` |
| `FAIL` | `3` |

共同 stock 失败为：

- `M5Canvas.draw_triangle`：native descriptor 顶点未正确回写；
- `M5Image.set_scale(1.5)`：float-to-int 转换异常；
- `M5Spinbox.set_step(5)`：integer step 被错误放大为 `50`。

两台各 `28/28` 批次到达 READY，最终 frame 尺寸分别为 StopWatch
`466x466`、Core2 `320x240`，且全部 `28/28` 为非黑帧。非黑帧只证明
显示数据面存在，不替代逐 widget 视觉 oracle。

hash-pinned M5UI candidate source 结果：

- StopWatch：四个状态 oracle `4/4 PASS`，triangle 与 image scale 两个
  frame oracle `2/2 FRAME_PASS`；
- Core2：四个状态 oracle `4/4 PASS`，但 triangle/image 两个 frame
  oracle 仍失败。最终 revision 在 `rotation=1`、`SCREEN_LOAD DONE`
  后取帧；画面仍出现横向条带和错误位置，说明候选源码语义修复有效，
  但 Core2 的 M5UI 全屏刷新/panel window 路径仍未闭环。

StickS3 当前 stock 镜像不导出 `m5ui`，因此该矩阵为 `NOT_EXPORTED`，
不能从 StopWatch/Core2 继承。

## 音频、ESP-NOW 与外设组

| 检查 | StopWatch | StickS3 | Core2 |
| --- | ---: | ---: | --- |
| `audio` player | `15/15` | `15/15` | `NOT_EXPORTED` |
| `audio` recorder | `12/12` | `12/12`（隔离重跑） | `NOT_EXPORTED` |
| `M5.Speaker` device group | 不适用 | 不适用 | PASS |
| `M5.Mic` device group | 不适用 | 不适用 | PASS |
| `espnow` | `12 PASS + 5 STATE_PASS + 1 CONFIGURED_UNVERIFIED` | 同左 | 同左 |
| `espnow-native` | `21 PASS + 21 STATE_PASS + 3 CONFIGURED_UNVERIFIED` | 同左 | 同左 |

StopWatch 的 peripherals、vibration、M5IOE1、M5PM1，Core2 的
peripherals、power monitor、IMU、AXP192，以及 StickS3 的 peripherals、
IMU、A/B/PWR 和 IR TX/RX 组均完成 guest marker、QOM/units 或 host action
核对。StickS3 NEC 解码值为 `0x56/0xA3`。全部 session 的串口/frame
证据和 cleanup 通过。

ESP-NOW 仍是 opt-in 的同 guest controller TX/RX DMA loopback。外部 peer、
PMK 加密 payload、跨设备 fabric、RF、loss/retry 和 timing 均未验证。

## Stock BLE 边界

修复测试端的完整设备身份表后，三台再次并发执行最小 `ble-nus` 路径：

- StopWatch 外部 central 使用 `M5-STOPWATCH-UNIFIED` 扫描，未找到可连接
  advertisement，guest 最终报 `actual NUS peer write absent`；
- StickS3 使用 `M5-STICKS3-UNIFIED`，结果相同；
- Core2 的 `core2-unified` profile 在
  `UNIFIED_CORE2_IO_CONFIG_READY` 前超时。

三台 runtime、BLE peer 和 companion 都已停止并保留失败证据。该结果只说明
stock internal-controller GATT 路径仍为 `BLOCKED_MODEL`；显式 HCI
test-firmware 的既有结果不能替代 stock 结果。

## 本轮测试工具修正

M5UI runner 现在从设备清单读取 `api_size` 和 `ui_rotation`，不再对
Core2 硬编码 `320x240/rotation=0`；慢速 Core2 program 的请求和 marker
预算统一为可配置、最高 120 秒；correction probe 增加 rotation 和
`SCREEN_LOAD BEGIN/DONE` 标记。

BLE protocol runner 现在使用与 Device Service 一致的 StopWatch、StickS3、
Core2、CoreS3 和 Cardputer-ADV 广告名/payload 映射。Core2 model blocker
也不再误写成 ESP32-S3。新增契约测试同时检查 identity 对齐、四个 BLE
group 的源码可编译和 blocker 设备文案。

## 回归检查

- 平台套件：`1406` 项，`OK`，`1` 项既有 skip；
- `runtime_coverage`、`peripheral_catalog`、`qemu_profiles` 和
  `project_snapshot` 均 PASS；
- `compileall`、变更文件 scoped Ruff `E9/F` 和 `git diff --check` PASS；
- 本轮没有新增要关闭的 GitHub issue 或 PR；仅关闭已由本提交修复的
  runner 缺陷。

## 未关闭项

- Core2 M5UI candidate source 的 frame routing/window oracle；
- Core2 legacy UIFlow `RUNTIME-03` normal-WDT 启动与应用帧；
- stock BLE internal-controller GATT、显式 HCI 跨固件兼容和真实 RF；
- 外部/加密 ESP-NOW、RF/timing 与跨设备 fabric；
- 全部同固件 SHA 物理硬件验证。

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
  --group <group> --out-dir /tmp/m5-protocol

PYTHONPATH=.work/py312 python3.12 \
  tests/uiflow2/api_sweep/run_m5ui_documented.py \
  --api <isolated-device-service> --device <device> \
  --uiflow-root <pinned-uiflow-checkout> --out-dir /tmp/m5-m5ui
```

原始执行资产不进入 Git；本页和
[机器摘要](summary.json)只保留可公开的计数、哈希、失败分类和复现边界。
