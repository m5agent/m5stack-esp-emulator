# 2026-10-28：ESP-NOW loopback 与三设备 UIFlow2 接口收尾复测

## 范围

本轮在 StopWatch、StickS3 和 Core2 当前 M5Burner UIFlow2 `v2.5.3`
上重新执行运行态、协议、音频 wrapper 和设备组接口。所有结果都是
**virtual-device validation**；物理硬件、RF、声学、光学和电气测量均为
`NOT RUN`。

最终 QEMU SHA256：

`c3c3140322513de6f3ef724513e2f1272764e6af8a8fdd7c7bfd4448dc17f534`

该 binary 在上一轮 `20266732…` 基础上加入
`0067-esp32-espnow-controlled-peer-loopback.patch`。补丁 SHA256：

`d269334ac039e78a75cc3054c4f6e853865cb16f7489a242c40ddf095a57163b`

所有可见 session 都通过 `/api/v1` 或项目矩阵 runner 执行；每个 network
session 在停止前取得 evidence ZIP，停止使用 `purge=0`，并确认 QEMU PID
消失。原始 serial、frame、PCM、pcap、ZIP 和完整 program 留在 ignored
`.work/`。

## 最终 runtime 三设备回归

| 检查 | StopWatch | StickS3 | Core2 |
| --- | ---: | ---: | ---: |
| System runtime | `50 PASS + 1 STATE_PASS` | `50 PASS + 1 STATE_PASS` | `50 PASS + 1 STATE_PASS` |
| Shared corrections | `7/7` | `7/7` | `7/7` |
| Device group | `6/6` | `5/5` | `6/6` |
| Audio recorder wrapper | `12/12` | `12/12` | `NOT_EXPORTED` |

17 个设备组 case 全部首轮 PASS、`retry_used=false`。设备组检查数为
StopWatch `31`、StickS3 `15`、Core2 `24`。

最终 runtime 的通信复测：

| 组 | StopWatch | StickS3 | Core2 |
| --- | ---: | ---: | ---: |
| Sockets | `23/23` | `23/23` | `23/23` |
| MQTT | `42/42` | `42/42` | `42/42` |
| Network | `14/14` | `14/14` | `14/14` |
| EzData owned fixture | `17/17` | `17/17` | `17/17` |
| requests2 candidate source | `2/2` | `2/2` | `2/2` |
| Modbus async candidate source | `50/50` | `50/50` | `50/50` |

## ESP-NOW controller loopback

新的 `0067` 是默认关闭的 `M5SW_ESPNOW_LOOPBACK=1` 测试夹具。guest 使用
原厂 `espnow`/`m5espnow` 栈写入正常 TX DMA 的 802.11 management action
frame；模型在 controller 层交换 peer/source 地址，再通过正常 RX DMA
送回同一 guest。broadcast 使用固定的 locally-administered fixture peer
`02:00:00:00:00:42`。

最终 runtime 三台结果：

| 设备 | `m5espnow` | native ESP-NOW 三组 API |
| --- | --- | --- |
| StopWatch | `12 PASS + 5 STATE_PASS + 1 CONFIGURED_UNVERIFIED` | `21 PASS + 21 STATE_PASS + 3 CONFIGURED_UNVERIFIED` |
| StickS3 | 同左 | 同左 |
| Core2 | 同左 | 同左 |

`m5espnow` 的 `send_data`、`broadcast_data`、`recv_data` 和
`set_irq_callback` 均为 PASS；native `espnow.ESPNow`、`ESPNowBase` 和
`m5espnow.M5ESPNow` 的 `send`、`recvinto`、`irq` 均为 PASS。该结果是
同一 guest 的受控 virtual peer loopback：

- 不证明外部 ESP-NOW peer、跨设备互操作或真实 RF；
- 不证明 PMK 加密 payload、retry/loss、channel/rate、timing 或电气行为；
- 不以 Python host fixture 伪造 payload 或 callback。

## 音频 wrapper

`audio.Player.play_tone(..., sync=True)` 的 stock 实现会在返回后仍短暂保持
`RUNNING(1)`，约 1.5–2 秒后状态回调进入 `FINISHED(4)`。最小 probe 连续
轮询确认不是永久阻塞。旧测试在函数返回瞬间断言，存在采样竞态；probe 已
改为最多 3 秒的有界等待。

最终 runtime：

| 设备 | Audio player | Audio recorder |
| --- | ---: | ---: |
| StopWatch | `15/15` | `12/12` |
| StickS3 | `15/15` | `12/12` |
| Core2 | `audio` module not exported | `audio` module not exported |

该修正只改变测试采样边界；raw PCM/频谱和物理声学结论仍由既有音频证据与
设备组 data-plane oracle 负责。

## Stock 固件边界

STOP / preimage 仍保留，不由候选结果覆盖：

- HTTP stock 三台均为 `15 PASS + 1 FAIL`，失败点为
  `requests2.urlencode` 保留字符/UTF-8；
- Modbus stock 三台均为 `42 PASS + 8 ERROR`，失败点为 8 个 async 方法调用
  不存在的 `Loop.sock_recv`；
- TLS stock 三台均为 `2 ERROR + 3 STATE_PASS`，过期判定来自
  `0010-mbedtls-epoch` 所修正的 epoch 路径。

最终 runtime 上重新执行 hash-pinned 候选：

- `requests2` 候选源码三台 `2/2`；
- Modbus async 候选源码三台 `50/50`；
- TLS candidate firmware 三台 `5/5`；StopWatch/Core2 使用 `dupterm`，
  StickS3 的 native-REPL unified image 使用 `native` bootstrap。

## 未关闭问题

- Core2 legacy UIFlow `RUNTIME-03`：normal-WDT reset、display completion、
  setup/REPL 和非空应用帧仍未闭环；
- ESP-NOW 外部 peer、加密 PMK、跨设备 fabric 和 RF/timing (`RUNTIME-06`)；
- Core2 全部 28 类 M5UI 文档方法矩阵仍为 `REVIEW`；
- 任何物理硬件、射频、声学、光学或电气验证均为 `NOT RUN`。

## 复现入口

```bash
PYTHONPATH=platform/tools:.work/py python3 \
  tests/uiflow2/api_sweep/run_guest.py \
  --api http://127.0.0.1:8788 --device stopwatch \
  --source tests/uiflow2/api_sweep/probe_system_runtime.py \
  --done-marker SYSTEM_RUNTIME_DONE --out-dir /tmp/m5-system

PYTHONPATH=platform/tools:.work/py python3 \
  tests/uiflow2/api_sweep/run_protocols.py \
  --execute --api http://127.0.0.1:8788 \
  --device stopwatch --device sticks3 --device core2 \
  --group espnow \
  --runtime-env-json .work/uiflow2-retest-20261028-b/espnow-loopback.json \
  --out-dir /tmp/m5-espnow

PYTHONPATH=.work/py python3 \
  tests/uiflow2/run_peripheral_matrix.py \
  --device stopwatch --out-dir /tmp/m5-stopwatch-group
```
