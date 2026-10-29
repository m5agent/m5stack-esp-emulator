# 2026-10-29：ESP-NOW per-peer LMK routing

## 范围

`0082-esp32-espnow-per-peer-key-routing.patch` 使用 stock controller key
entry 的 peer MAC 选择对应 guest LMK，使同一个三 guest fabric 中，每个
方向可以绑定独立 pairwise LMK。该结果关闭 `RUNTIME-06` 的 per-peer LMK
TX/RX routing 里程碑，并保留 shared-LMK 和 direct guest-key 回归。

全部结果为 **virtual-device validation**。host 不合成 key slot、payload、
MIC 或 callback；peer table 与 LMK 仍由 stock `espnow.ESPNow` 写入
classic ESP32/ESP32-S3 controller。

## Controller key entry

匹配 UIFlow2 ELF 的 stock `wDev_Insert_KeyEntry` 把 6-byte peer address
复制到 descriptor bytes `3..8`。`hal_crypto_set_key_entry` 再把它写成
controller key entry 的前 6 bytes：

- key entry stride：`40` bytes；
- peer MAC：entry offset `0..5`；
- LMK：entry offset `8..23`；
- valid bits：control offset `0x14`；
- `hal_crypto_set_key_entry`：ESP32-S3 `0x42182fc0`，classic ESP32
  `0x402e2178`。

模型只在 valid bit、前 8-byte metadata 和 16-byte LMK 全部写入后，才把
slot 视为 ready。fabric TX 按 receiver peer 查 key，RX 按 authenticated
frame 的 transmitter peer 查 key。每个 guest key slot 保存独立 TX PN；
replay window 仍按 source-peer MAC 分片。

| 项目 | SHA256 |
| --- | --- |
| QEMU runtime | `9c36bb527f441b65acc16aff09728ae66e98ea19957a42fbc8bc087d52c9e5e0` |
| `0082` patch | `5405d62fe3e4b6fff9cd1b41129b32d296a56b8a288e927ac19e1770acb88a6c` |
| fabric runner | `642522e681f23a8fc2c8c6ccf41c1802ebc029b59ecdac39c72e6f049cef44f0` |

## Shared-LMK 回归

最终 QEMU 上三端 `peer_count=[2,2]`，各端收到另外两个 peer 的 payload，
所有 `replay_drops=0`。该回归证明新增 metadata 条件和 peer lookup 没有
破坏 `0081` shared-LMK fabric。

| role | 设备 | TX/RX | key ready | payload matches |
| --- | --- | ---: | ---: | --- |
| A | StopWatch | 844/864 | 2 | B `205`, C `225` |
| B | StickS3 | 828/872 | 2 | A `210`, C `225` |
| C | Core2 | 900/362 | 2 | A `56`, B `56` |

## Pairwise-LMK 正控

A-B、A-C、B-C 分别使用三个不同的 16-byte LMK。三端 stock key store 都把
两个 peer 写入 extended slots `23`、`24`，每端 `guest_key_ready=2`。
全部六个 directed payload 路径仍 PASS，说明 TX/RX 都选到了方向对应的
peer key，而不是复用某一个全局 LMK。

| role | 设备 | TX/RX | key ready | payload matches |
| --- | --- | ---: | ---: | --- |
| A | StopWatch | 848/878 | 2 | B `213`, C `225` |
| B | StickS3 | 856/874 | 2 | A `211`, C `225` |
| C | Core2 | 900/370 | 2 | A `56`, B `56` |

## Cross-wire 负控

负控只把 role B 对 role A 的 LMK 改成 B-C 的 LMK；broker 仍正常转发全部
六个 directed path，三个 guest 也都注册两个 peer。预期 A↔B 双向 MIC
失败，A↔C 与 B↔C 保持：

| receiver | A | B | C |
| --- | ---: | ---: | ---: |
| A | — | `0` | `226` |
| B | `0` | — | `226` |
| C | `45` | `46` | — |

A/B 的 `source_matches` 对错误 peer 也为 `0`，正确 peer 为非零。
StopWatch/StickS3 trace 分别记录 `470/472` 次 peer-key/CCMP failure，Core2
为 `0`。runner 只有在 expected link matrix 与 source/payload matrix 同时
一致时才标记负控 PASS。

## 回归与清理

- direct `guest-key` StopWatch↔StickS3：双方 TX/RX `57/58` 与 `58/57`，
  `guest_key_ready=1`，PASS；
- shared-LMK、pairwise 正控、cross-wire 负控和 direct regression 共
  `11` 个 session；
- 全部 terminal `stopped`、runtime PID gone、history retained，并沿用例
  `purge=0`；
- ESP-NOW controller/patch contracts：`47/47 PASS`；
- QEMU build PASS；patch forward/current-source/reverse PASS。

## 未覆盖

`RUNTIME-06` 仍为 `PARTIAL`：

- PN wrap；
- loss/retry；
- channel/rate；
- bit-exact controller；
- RF/antenna、电气时序和 physical hardware。

## 复现入口

```bash
export M5_CORE2_RADIO_QEMU="$PWD/.work/M5StopWatch-QEMU/build/qemu/build/qemu-system-xtensa"
PYTHONPATH=.work/py python3 platform/tools/serve.py 8811 \
  --bind 127.0.0.1 \
  --state-dir /tmp/m5-espnow-per-peer-state \
  --api-token-file /tmp/m5-espnow-token

PYTHONPATH=.work/py python3 tests/uiflow2/api_sweep/run_espnow_pair.py \
  --api http://127.0.0.1:8811 \
  --token-file /tmp/m5-espnow-token \
  --scenario fabric-per-peer-key \
  --left-device stopwatch \
  --right-device sticks3 \
  --third-device core2 \
  --out-dir /tmp/m5-espnow-per-peer
```

cross-wire 负控将 `--scenario` 改为
`fabric-per-peer-key-negative`，并使用新的输出目录。
