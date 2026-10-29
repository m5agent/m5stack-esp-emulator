# 2026-10-29：ESP-NOW external CCMP PN anti-replay

## 范围

`0078-esp32-espnow-external-ccmp-replay.patch` 为单个 encrypted external
ESP-NOW peer 增加 monotonic CCMP PN guard。只有通过 MIC 验证的帧才可推进
receiver PN；PN 等于或小于 last accepted PN 的 authenticated frame 在正常
RX DMA 前丢弃。

全部结果为 **virtual-device validation**。物理 hardware、RF、antenna、
channel/rate、electrical、timing、multi-peer replay window 和 key rotation
均为 `NOT RUN`。

| 项目 | SHA256 |
| --- | --- |
| QEMU runtime | `be7c376550829427b0fc72ada75f9d06e2246feaa64b2c222904d5a17a3c4076` |
| `0078-esp32-espnow-external-ccmp-replay.patch` | `b30c56272dba2fd6e4000ee8b12f82a08e57ccadf8bc8e0d0d42488b5baa1adc` |
| `tests/uiflow2/api_sweep/run_espnow_pair.py` | `9778e0d8a10e05e839c6f6aff542077ff8c7da5bb5e943aab71d427240992ac9` |

## 实现边界

- receiver state 只保存 `last_rx_pn` 和有效位，session realize/cleanup 与
  wrapped key state 一起重置。
- unauthenticated frame 在 replay 检查之前失败，不能推进 PN 或毒化窗口。
- authenticated equal/older PN 在 `espnow_peer_wrap_rx_envelope` 和
  `Esp32_sendFrame` 之前 `continue`，不进入 guest DMA。
- replay fixture 是一个 UDP proxy：先正常转发两个方向的真实 action frame，
  等双向都已通信后，仅把一帧 left→right datagram 再发送一次。
- 这是单调单 peer guard，不是允许多 peer/乱序的 production replay window；
  PN wrap 需要尚未建模的 key rotation。

## 结果

### StopWatch → StickS3 replay

| 设备 | firmware SHA256 | TX | RX | replay drop | peer payload | 结果 | evidence SHA256 |
| --- | --- | ---: | ---: | ---: | ---: | --- | --- |
| StopWatch | `b6baab9fa89d706a1e97da9302306c19f6f3f45abf171fa3c4dcab5e35dddb08` | 58 | 58 | 0 | 57 | PASS | `dee94595b90c021d4dbbf7dda4b0fba64da680ee2a0e095b59ff3dbfb6a3fac0` |
| StickS3 | `a36fdff4efaee90b1b9bc1eed265b660d7e009b2fd391552a0d8205ed508ee6c` | 58 | 59 | 1 | 58 | PASS | `95531c92ec99703cccff1d31e3af167179439e851c710f26644908b97bb42e6c` |

UDP replay proxy 两个方向均转发 `58` 帧，`replay_sent=true`，无 proxy error。
StickS3 的额外 RX frame 对应 controller 输出的
`[espnow-peer] RX drop: CCMP PN replay`，没有进入 guest callback。

### 回归

| 场景 | 设备对 | TX/RX | peer payload | 结果 |
| --- | --- | --- | ---: | --- |
| wrong-LMK | StopWatch↔StickS3 | `40/40`, `40/40` | `0/0` | EXPECTED_DROP |
| encrypted | Core2↔StopWatch | `44/31`, `48/44` | `15/44` | PASS |

六个独立 session 全部 terminal `stopped`、`runtime_pid_gone=true`、
history 保留且停止使用 `purge=0`。

## 未关闭

- 多 peer、乱序和固定 replay window；
- PN wrap 与 key rotation；
- guest `set_pmk`/`add_peer` key-state 传播与 peer lifecycle；
- loss/retry、channel/rate、bit-exact controller；
- RF、antenna、AP coexistence、电气、timing 和 physical hardware。

因此 `RUNTIME-06` 仍为 `PARTIAL`：本轮只关闭单 peer monotonic replay
fixture，不能外推 production replay window 或物理 controller。

## 复现入口

```bash
export M5_CORE2_RADIO_QEMU="$PWD/.work/M5StopWatch-QEMU/build/qemu/build/qemu-system-xtensa"
PYTHONPATH=.work/py python3 platform/tools/serve.py 8811 \
  --bind 127.0.0.1 \
  --state-dir /tmp/m5-espnow-replay-state \
  --api-token-file /tmp/m5-espnow-token

PYTHONPATH=.work/py python3 tests/uiflow2/api_sweep/run_espnow_pair.py \
  --api http://127.0.0.1:8811 \
  --token-file /tmp/m5-espnow-token \
  --scenario replay \
  --left-device stopwatch --right-device sticks3 \
  --out-dir /tmp/m5-espnow-replay
```
