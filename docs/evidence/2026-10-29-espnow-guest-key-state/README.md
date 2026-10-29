# 2026-10-29：ESP-NOW stock guest controller key-state

## 范围

`0080-esp32-espnow-guest-key-state.patch` 把 classic ESP32 与 ESP32-S3
WiFi crypto key-store MMIO 接入 external ESP-NOW bridge。本轮验证 stock
UIFlow2 `espnow.ESPNow` 的 `set_pmk`、`add_peer`、`del_peer`、
`mod_peer` 和 `send/recvinto` 路径，runtime-env 不提供 PMK/LMK。

全部结果为 **virtual-device validation**。没有合成 Python payload、
controller key 或 callback；payload 仍从 guest TX DMA 发出，经 bridge
真实 AES-CCMP/MIC 后进入 peer guest 的正常 RX DMA。

## Controller 入口

反汇编匹配的 `libespnow.a`、`libnet80211.a` 和 `libpp.a` 后确认：

- `mt_set_lmk` 调用 `ic_set_key`，最终进入
  `hal_crypto_set_key_entry` / `hal_crypto_enable`；
- classic ESP32 key store 为 `0x3ff74400`，S3 为 `0x60034400`；
- 每个 entry stride 为 40 bytes，key data 从 entry `+8` 开始；
- 固件首选 extended slot `24`，有效位为 `0x01000000`；
- 模型只在 valid bit 已置位且 16-byte LMK 全部写入后启用 key。

slot clear、replacement 和 QEMU cleanup 同时清 active key 与 replay
state。trace 只输出 slot、mask 和 state，不输出 key bytes。

| 项目 | SHA256 |
| --- | --- |
| QEMU runtime | `d2f25608dce3d4b4ff8951b1b89a778d52a57286bfb460f7959ddec696e48796` |
| `0080` patch | `c827a3e6e76f591b319379342e099a5cd4ffd086029fb514cb99c61a72e2babc` |
| pair runner | `23791688c70ca6c1c7c3ac171d021bb8c1c9b82d38ecad2602d92da6ae06472a` |

## 正控

| 设备对 | 设备 | firmware SHA256 | TX/RX | guest key ready | peer payload matches | 结果 |
| --- | --- | --- | ---: | ---: | ---: | --- |
| StopWatch↔StickS3 | StopWatch | `b6baab9f…` | 58/58 | 1 | 57 | PASS |
| StopWatch↔StickS3 | StickS3 | `a36fdff4…` | 58/58 | 1 | 58 | PASS |
| Core2↔StopWatch | Core2 | `b39ced5d…` | 44/37 | 1 | 15 | PASS |
| Core2↔StopWatch | StopWatch | `bb9999e9…` | 47/44 | 1 | 44 | PASS |

两侧 `created.json` 都只有 bridge ports 和 trace flag，没有
`M5SW_ESPNOW_PEER_PMK` / `M5SW_ESPNOW_PEER_LMK`。

## 负控与轮换

不同 guest LMK 的两个设备对均为 `EXPECTED_DROP`：两端
`rx_packets=0`，MIC failure 在 RX DMA 前发生。trace 中 S3 两侧各记录
39–40 次 validation failure；classic/StopWatch 混合 pair 记录 7/40 次。

key rotation 使用相同流程：初始共享 LMK 完成 PRE 双向通信，
`del_peer` 清 key，re-add 后 `mod_peer` 切换到新共享 LMK，再完成
post-resume 双向通信。

| 设备对 | pre-sync | delete/re-add/modify | post-resume | guest key ready | 结果 |
| --- | --- | --- | --- | ---: | --- |
| StopWatch↔StickS3 | true | PASS | true | 4 + 4 | PASS |
| Core2↔StopWatch | true | PASS | true | 4 + 4 | PASS |

## 清理与边界

六个设备对、十二个 session 全部 terminal `stopped`，runtime PID gone，
history retained，并沿用例 `purge=0`。本轮没有把虚拟 controller 结果外推
为 RF、antenna、channel/rate、电气时序或真机测量。

`RUNTIME-06` 仍为 `PARTIAL`：multi-peer key routing/每 peer replay
window、3+ peer fabric、PN wrap、loss/retry、channel/rate、
bit-exact controller 和 physical hardware 仍 `NOT RUN`。

## 复现入口

```bash
export M5_CORE2_RADIO_QEMU="$PWD/.work/M5StopWatch-QEMU/build/qemu/build/qemu-system-xtensa"
PYTHONPATH=.work/py python3 platform/tools/serve.py 8811 \
  --bind 127.0.0.1 \
  --state-dir /tmp/m5-espnow-guest-key-state \
  --api-token-file /tmp/m5-espnow-token

PYTHONPATH=.work/py python3 tests/uiflow2/api_sweep/run_espnow_pair.py \
  --api http://127.0.0.1:8811 \
  --token-file /tmp/m5-espnow-token \
  --scenario guest-key \
  --left-device stopwatch \
  --right-device sticks3 \
  --out-dir /tmp/m5-espnow-guest-key
```

`guest-key-wrong-lmk` 和 `guest-key-rotation` 使用相同入口。
