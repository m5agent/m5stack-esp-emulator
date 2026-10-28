# 2026-10-28：最新 runtime 三设备 UIFlow2 接口复测

## 范围

本轮在 StopWatch、StickS3 和 Core2 的 M5Burner UIFlow2 `v2.5.3`
参考固件上复测系统运行时、共享候选、设备组、通信协议和 TLS 候选固件。
三台设备之间并发，单台设备内按会话串行，所有功能执行均通过独立
Device Service `/api/v1`。

全部结果为 **virtual-device validation**；物理硬件、RF、声学、光学和
电气测量为 `NOT RUN`。

QEMU SHA256：

`78555183d53318fc25bc8413300e928d35bbbc1305f9d9648e97a73d34ce63b1`

该 binary 包含本轮
[`0069-esp32-timg-wdt-feed-unprotected.patch`](../../../patches/qemu-m5stack-peripherals/0069-esp32-timg-wdt-feed-unprotected.patch)。

| 设备 | Base firmware SHA256 |
| --- | --- |
| StopWatch | `99d6482befe094de47bf68ce43618d3868bd62fb1fc72f0b55c0d0c2ea4e7f8d` |
| StickS3 | `c08196024019273ccadee9b4b3da303567f7ab206fa14edd1af283f04f6e98d8` |
| Core2 | `b228c0e2d877e77a8a352e917ed84f4da8ea92d15b25e28f431a2999620fe3c4` |

## 通过项

| 检查 | StopWatch | StickS3 | Core2 |
| --- | ---: | ---: | ---: |
| System runtime | `50 PASS + 1 STATE_PASS` | 同左 | 同左 |
| Shared corrections | `7/7` | `7/7` | `7/7` |
| Device group | `6/6` | `5/5` | `6/6` |
| Sockets | `23/23` | `23/23` | `23/23` |
| EasySocket | `57 + 1 N/A` | 同左 | 同左 |
| MQTT | `42/42` | `42/42` | `42/42` |
| Network | `14/14` | `14/14` | `14/14` |
| EzData owned fixture | `17/17` | `17/17` | `17/17` |
| ESP-NOW loopback | `12 PASS + 5 STATE_PASS + 1 configured` | 同左 | 同左 |
| Native ESP-NOW loopback | `21 PASS + 21 STATE_PASS + 3 configured` | 同左 | 同左 |
| Audio player | `15/15` | `15/15` | `NOT_EXPORTED` |
| Audio recorder | `12/12` | `12/12` | `NOT_EXPORTED` |

17 个设备组用例全部首轮 PASS，`retry_used=false`。Core2 六个用例覆盖
外设、audio、mic、power monitor、IMU 和 AXP192；`core2-imu` 另行首跑
`3/3`。三台最终帧都有非黑成功 marker，未用状态返回代替画面 oracle。

关键 system/shared session：

| 设备 | System runtime | Shared corrections |
| --- | --- | --- |
| StopWatch | `afc42ce342634d319cc5eb1e02f85b04` | `a02e70747dfb4f9893810ae3e83ef2f8` |
| StickS3 | `023227cd64164c939e2078fe9c1a5953` | `3fdd42929fef4301a189cfe225c32eac` |
| Core2 | `1a359fe661544421bf393461accff439` | `5c777000170f42ee924b8e7cff64977c` |

所有会话均先取得 evidence ZIP，再以 `purge=0` 停止；报告确认 QEMU PID
消失、history 保留且 companion cleanup 完成。

## Stock 固件边界与候选修复

三台参考固件仍复现相同 stock 缺陷，不能把候选结果写成原厂镜像已修复：

| 接口组 | Stock | 失败点 | 同 runtime 候选 |
| --- | ---: | --- | ---: |
| HTTP | `15 PASS + 1 FAIL` | `requests2.urlencode` | `2/2` |
| Modbus TCP | `42 PASS + 8 ERROR` | 8 个 async 方法缺少 `Loop.sock_recv` | `50/50` |
| TLS | `3 STATE_PASS + 2 ERROR` | mbedTLS certificate epoch | `5/5` |

`requests2` 候选源码 SHA256 为
`40d1a98d2413b379e14c1732b329004feb8b6675655ae2548931ef2dd16ba052`；
Modbus async 候选源码 SHA256 为
`86125ad2cff3929849709a6670750847835f8e8fa3f9d0c493d37fe0042ed37a`。

TLS candidate firmware 在最新 runtime 重跑：

| 设备 | Candidate base SHA256 | Session | 结果 |
| --- | --- | --- | ---: |
| StopWatch | `edcd9a392f1ff5e5741c8331ae41ea18b915ae50b2ff54c173110c65c532e6a6` | `e8476e19ff70470f898f69ea09638205` | `5/5` |
| StickS3 | `2e8386057fab9d384489651a544e30ce4edaf86586e1f4ce7f588469439af6aa` | `e2a38d616a5e4509b9c7ba87928dc393` | `5/5` |
| Core2 | `204def8c601c29b7fa4af83b767c3fd8ced9c6b12815a709c450fb5b80a2e2c6` | `775bab855201444a9f442d2bda37cf16` | `5/5` |

这些候选均为 hash-pinned source 或增量 application 镜像，不替换设备矩阵
默认参考固件。

## Device Service 与并发

- Device Service API sweep：`81` operations、`95` cases、
  `13` positive + `70` boundary，全部 PASS；
- 完整平台套件：`1366` 项完成，`OK`，`1` 项既有 skip；
- 设备间并发使用独立 service/state/token，设备内串行，避免同一服务
  per-device capacity 竞争；
- Core2 virtual WiFi 服务必须显式设置 `M5_CORE2_RADIO_QEMU`。首次遗漏
  该部署环境返回 503，属于 infrastructure control；按
  [部署文档](../../deployment.md)配置后同一候选固件 `5/5` PASS，
  不计入固件或模拟器功能失败；
- 本轮的 `network.http_fixture=false`、READY→RUNNING 等待和 RMT trusted
  local fixture 修复已由上一提交落地，本轮没有新增 runner 回归。

## 未覆盖项

- Core2 legacy UIFlow `RUNTIME-03`：normal-WDT reset、原厂 startup UI、
  setup/REPL 和完整 application frame；
- 外部或加密 ESP-NOW peer、跨设备 fabric、RF 和 timing；
- 使用显式 HCI test firmware 的 BLE NUS/client 组，以及未准入的
  Modbus RTU/PPP Unit 组合；
- Core2 二十八类 M5UI 完整文档方法矩阵；
- 所有物理显示、触控、声学、光学、RF 和电气验证。

## 复现入口

```bash
PYTHONPATH=platform/tools .work/issue-review-venv/bin/python3.12 \
  tests/uiflow2/api_sweep/run_protocols.py \
  --execute --api http://127.0.0.1:<isolated-port>/api/v1 \
  --token-file <private-token-file> --device sticks3 --group sockets \
  --out-dir <new-output-dir>

PYTHONPATH=platform/tools .work/issue-review-venv/bin/python3.12 \
  tests/uiflow2/api_sweep/run_protocols.py \
  --execute --api http://127.0.0.1:<isolated-core2-port>/api/v1 \
  --token-file <private-core2-token-file> --device core2 --group tls \
  --base-image core2=<pinned-tls-candidate-full-flash.bin> \
  --expected-base-sha256 core2=204def8c601c29b7fa4af83b767c3fd8ced9c6b12815a709c450fb5b80a2e2c6 \
  --out-dir <new-output-dir>
```

Core2 service 启动前设置：

```bash
export M5_CORE2_RADIO_QEMU="$PWD/.work/M5StopWatch-QEMU/build/qemu/build/qemu-system-xtensa"
```

不要复用输出目录；原始 serial、frame、pcap、PCM、候选镜像、证书和
evidence ZIP 留在 ignored `.work/`。
