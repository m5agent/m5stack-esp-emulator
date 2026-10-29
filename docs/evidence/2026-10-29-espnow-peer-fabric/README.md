# 2026-10-29：ESP-NOW 三 guest shared-LMK fabric

## 范围

`0081-esp32-espnow-peer-fabric.patch` 在 `0080` 的 stock guest controller
key-state 上增加一个 opt-in 三 guest fabric。StopWatch、StickS3 和 Core2
分别连接同一个 IPv4 loopback UDP broker，每个 guest 注册另外两个 encrypted
peer，并各自发送、接收另外两端的 action-frame payload。

全部结果为 **virtual-device validation**。host 不合成 guest payload、CCMP
tag 或 receive callback；TX 来自 guest controller DMA，bridge 在控制器边界
执行 CCMP/MIC，RX 再进入 peer guest 的正常 DMA。

## 身份与 replay 设计

- 每个 controller 在加密前把自己的 synthetic `M5SW_ESPNOW_PEER_PUBLIC_MAC`
  写入 transmitter/address3，broker 不在 MIC 计算后改写这两个受 AAD 保护
  的字段；
- broker 按真实 UDP source、receiver MAC 和显式 roles 路由，只向目标 guest
  提供 source peer；
- RX replay window 按 authenticated source-peer MAC 分片，共 8 个 slot，
  每 slot 为 64 frame bitmap；
- 先验证 CCMP/MIC，再查 source-peer replay state；失败帧不会推进 window；
- 该 lane 的 key scope 是 **shared LMK**，不证明每个 peer 使用不同 LMK。

| 项目 | SHA256 |
| --- | --- |
| QEMU runtime | `de8d5b07a31861bf3aae0731ad21da772753cb1bd1388f5b678bdcf23a0ef9b1` |
| `0081` patch | `b86d3561d503139a4ae8dbda6c4699534b478113ff681784012e562d4d8cf7ca` |
| fabric runner | `74429e26440c7bbce6c2ad47ef99b03939c1ab62db5daf21da9350dc07e24d97` |

## 正控

| role | 设备 | firmware SHA256 | TX/RX | key ready | replay drop | peer payload matches |
| --- | --- | --- | ---: | ---: | ---: | --- |
| A | StopWatch | `c55e9154…` | 844/854 | 2 | 0 | B `206`, C `220` |
| B | StickS3 | `e61b31f0…` | 828/862 | 2 | 0 | A `210`, C `220` |
| C | Core2 | `4e168954…` | 880/352 | 2 | 0 | A `55`, B `55` |

三个 guest 的 `peer_count` 均为 `[2,2]`，并分别收到另外两个 peer 的正确
payload。broker 观察到全部 `A→B/A→C/B→A/B→C/C→A/C→B` 路径，错误为
`0`。三个 session 均 terminal `stopped`、runtime PID gone、history
retained。

## Replay 负控

broker 在三方完成 PRE 后复制一帧真实 forwarded frame。StickS3 的 action
frame source 为 StopWatch，其 per-source window 恰好记录一次
`replay_drops=1`；StopWatch 与 Core2 均为 `0`。三方正常 payload 仍为
PASS，没有把重复帧交付给 guest callback。runner 只有在目标 B 精确为 `1`
且 A/C 精确为 `0` 时才将负控标记 PASS。

该负控也验证 replay state 不会被第三个 peer 的 PN 推进或清除。原始 broker
转发计数保存在机器摘要中。

## 失败控制

首轮实现先在 guest CCMP 后改写 transmitter/address3，broker 再改一次地址，
导致 AAD 不一致并让全部 MIC 验证失败。该实现被拒绝；最终设计把 public MAC
注入放到加密前，并在 RX 保留 broker 提供的 source peer。

早期 readiness 使用单独的两阶段 barrier，Core2 尚未 ready 时另外两 guest
已结束交换。最终 runner 把 `READY` 和持续 payload 交换放在同一个 24 秒
循环中，positive 与 replay 负控都以该版本重跑。失败轮只作为本地 ignored
控制保留，没有提交 raw serial 或 MAC 日志。

## 清理与边界

正控与 replay 负控各三个 session，全部使用 `purge=0` 停止并保留 history。
本地 Device Service 回归 `123/123 PASS`；ESP-NOW 契约测试 `7/7 PASS`。

`RUNTIME-06` 仍为 `PARTIAL`。本轮关闭三 guest shared-LMK fabric、
per-source replay window 和 fabric replay 负控；以下仍未覆盖：

- per-peer LMK key routing；
- PN wrap；
- loss/retry；
- channel/rate；
- bit-exact controller；
- RF/antenna、电气时序和物理硬件。

## 复现入口

```bash
export M5_CORE2_RADIO_QEMU="$PWD/.work/M5StopWatch-QEMU/build/qemu/build/qemu-system-xtensa"
PYTHONPATH=.work/py python3 platform/tools/serve.py 8811 \
  --bind 127.0.0.1 \
  --state-dir /tmp/m5-espnow-fabric-state \
  --api-token-file /tmp/m5-espnow-fabric-state/api-token

PYTHONPATH=.work/py python3 tests/uiflow2/api_sweep/run_espnow_pair.py \
  --api http://127.0.0.1:8811 \
  --token-file /tmp/m5-espnow-fabric-state/api-token \
  --scenario fabric \
  --left-device stopwatch \
  --right-device sticks3 \
  --third-device core2 \
  --out-dir /tmp/m5-espnow-fabric
```

replay 负控将 `--scenario fabric` 改为 `--scenario fabric-replay`，并使用
新的输出目录。
