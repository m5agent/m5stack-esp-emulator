# 2026-10-29：ESP-NOW external CCMP 64-frame replay window

## 范围

`0079-esp32-espnow-external-ccmp-window.patch` 将单 external peer 的严格
monotonic PN guard 升级为 64-frame authenticated replay window：

- 新 PN 向前推进 last PN，并移位 bitmap；
- window 内未见过的 older PN 接受一次；
- duplicate、超过 window 的 old PN 在 MIC 成功后仍丢弃；
- MIC 失败不推进任何 replay state。

全部结果为 **virtual-device validation**。该 window 仍是单 peer；RF、
timing、PN wrap/key rotation 和多 peer window 为 `NOT RUN`。

| 项目 | SHA256 |
| --- | --- |
| QEMU runtime | `ef88746915960fe26a275cccfefcbb506cbc0f7d322747faad81a4a0916661cd` |
| `0079-esp32-espnow-external-ccmp-window.patch` | `c4f40a614412db0b0c642f448820bb1acb8cf9bbe980df4e20e15d5c74556e0c` |
| `tests/uiflow2/api_sweep/run_espnow_pair.py` | `264f475e9c1d1725fde16112025219e8933e5fb7678b361e9f131692f1211708` |

## 真实乱序控制

`ReorderProxy` 在两个方向都已通信后，暂存一帧 left→right datagram，
等下一帧到达后先发送第二帧，再发送 held first frame，形成 PN `2 → 1`。

| 项目 | 值 |
| --- | --- |
| left→right forwarded | `58` |
| right→left forwarded | `58` |
| reordered | `true` |
| held frame released | `true` |
| proxy errors | `0` |
| receiver replay drops | `0` |

| 设备 | firmware SHA256 | TX/RX | peer payload | 结果 | evidence SHA256 |
| --- | --- | ---: | ---: | --- | --- |
| StopWatch | `b6baab9fa89d706a1e97da9302306c19f6f3f45abf171fa3c4dcab5e35dddb08` | 58/58 | 57 | PASS | `13a67280e38ff825021750f7647810b7ff8bb3e89994d2bdfbe3548e130564e3` |
| StickS3 | `a36fdff4efaee90b1b9bc1eed265b660d7e009b2fd391552a0d8205ed508ee6c` | 58/58 | 58 | PASS | `f62ecc6a259d67d2d0b6207875b5c94f7d506bb9aca93dd875b1c91d01d0026f` |

## 负控与回归

| 场景 | 结果 |
| --- | --- |
| duplicate replay | StickS3 RX `59`、replay drop `1`、guest payload 不重复 |
| Core2↔StopWatch encrypted | Core2 `14`、StopWatch `44` source/payload matches |

六个 session 均 terminal `stopped`、runtime PID gone、history retained，
并沿用 `purge=0`。

## 未关闭

- multi-peer replay windows；
- PN wrap、key rotation；
- guest key-state 写入 QEMU bridge；
- loss/retry、channel/rate、bit-exact controller；
- RF、antenna、AP coexistence、电气、timing 和 physical hardware。

`RUNTIME-06` 仍为 `PARTIAL`。本轮关闭单 peer bounded reordering，不放宽
duplicate replay。

## 复现入口

```bash
export M5_CORE2_RADIO_QEMU="$PWD/.work/M5StopWatch-QEMU/build/qemu/build/qemu-system-xtensa"
PYTHONPATH=.work/py python3 platform/tools/serve.py 8811 \
  --bind 127.0.0.1 \
  --state-dir /tmp/m5-espnow-window-state \
  --api-token-file /tmp/m5-espnow-token

PYTHONPATH=.work/py python3 tests/uiflow2/api_sweep/run_espnow_pair.py \
  --api http://127.0.0.1:8811 \
  --token-file /tmp/m5-espnow-token \
  --scenario reorder \
  --left-device stopwatch --right-device sticks3 \
  --out-dir /tmp/m5-espnow-window
```
