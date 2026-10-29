# 2026-10-29：ESP-NOW external peer add/delete/modify lifecycle

## 范围

在 `0076`/`0077`/`0078` 的 independent-guest external encrypted bridge 上，
使用 stock UIFlow2 `espnow.ESPNow` 原生接口验证：

- 初始 encrypted `add_peer` 和 `peer_count() == (1, 1)`；
- pre-sync 后 `del_peer()` 使 count 回到 `(0, 0)`；
- 删除后 `get_peer()` 与 `send()` 返回 `OSError`；
- 重新 `add_peer()`、`mod_peer()` 后 count 恢复 `(1, 1)`；
- 双方重新完成 encrypted payload exchange。

全部结果为 **virtual-device validation**。该场景验证 guest API 和正常
controller TX/RX DMA 生命周期，不证明 guest key-state 已被 QEMU bridge
读取，也不证明 key rotation、多 peer、RF 或物理硬件。

| 项目 | SHA256 |
| --- | --- |
| QEMU runtime | `be7c376550829427b0fc72ada75f9d06e2246feaa64b2c222904d5a17a3c4076` |
| `tests/uiflow2/api_sweep/run_espnow_pair.py` | `7d1c4a9122cbb51316ccc91aecc3241449ec49b304cee62d3c0026ed4c4c23e4` |

## 官方接口依据

- `espnow.ESPNow.add_peer(mac, lmk, channel, ifidx, encrypt)`：注册 peer；
- `del_peer(mac)`：注销 peer；
- `get_peer(mac)`：读取 `(mac, lmk, channel, ifidx, encrypt)`；
- `peer_count()`：返回 `(peer_num, encrypt_num)`；
- `mod_peer(...)`：修改已注册 peer 参数；
- 删除后 `send()` 的 `ESP_ERR_ESPNOW_NOT_FOUND` 负控。

## 结果

| 设备对 | 设备 | firmware SHA256 | bridge TX/RX | lifecycle | evidence SHA256 |
| --- | --- | --- | ---: | --- | --- |
| StopWatch↔StickS3 | StopWatch | `7a4be3675173a324ba6ae375ab4d279dbdec8bd7c36a465fd63eacf8a553c2d2` | 16/16 | PASS | `08304edd96e4b1ee47fe8e4d62552be76ce65c161ce886880c28526b958e668f` |
| StopWatch↔StickS3 | StickS3 | `93535fae7014051095b6c7a579fc57ea40470c692260c0104c6c02a26156f900` | 16/16 | PASS | `b8bf59fd11a46d8226901aa831c113acfd6d819234fb61e53318aa81bfb234a2` |
| Core2↔StopWatch | Core2 | `c7383713513462e13e53843f9a23265d749cb15647f4829c09284ba058b5194e` | 51/35 | PASS | `08059bd81f0f9906615436c0c8b9ea7a1adeb7d6f3e8d31752a5bd3621d20b39` |
| Core2↔StopWatch | StopWatch | `d982afde8fcf864f85fed805c9c514fbca2758bd0970c7338e9735cf9ddc9f1b` | 39/51 | PASS | `fbc44a4a11d38e2d386dca9a3acf12a78c88b1896db7d9a69c25724419263f5d` |

四个 session 的 `initial_count` 与 `readded_count` 均为 `[1, 1]`，
`deleted_count` 为 `[0, 0]`；`get_peer_not_found`、`send_rejected`、
`modified`、`pre_synced`、`post_resumed` 全部为 `true`。所有 session
terminal `stopped`、runtime PID 消失、history 保留并使用 `purge=0`。

## 首轮控制

Core2↔StopWatch 首轮得到一个有价值的 runner 竞态：StopWatch 收到 Core2
PRE 后立即删除 peer，而较慢的 Core2 尚未收到回向 PRE，导致 Core2
`pre_synced=false`。delete/re-add/modify 本身两边均已 PASS。runner 随后
改为收到 PRE 后继续发送 1.5 秒再删除；S3 pair 与 Core2 pair 均重跑 PASS。
失败 control 仅保存在 ignored `.work/`。

## 未关闭

- guest key-state 写入 QEMU bridge、key rotation；
- 多 peer/乱序 replay window、loss/retry；
- channel/rate、bit-exact controller；
- RF、antenna、AP coexistence、电气、timing 和 physical hardware。

`RUNTIME-06` 仍为 `PARTIAL`。本轮关闭的是 stock guest peer
add/delete/modify 生命周期和删除后发送拒绝。

## 复现入口

```bash
export M5_CORE2_RADIO_QEMU="$PWD/.work/M5StopWatch-QEMU/build/qemu/build/qemu-system-xtensa"
PYTHONPATH=.work/py python3 platform/tools/serve.py 8811 \
  --bind 127.0.0.1 \
  --state-dir /tmp/m5-espnow-lifecycle-state \
  --api-token-file /tmp/m5-espnow-token

PYTHONPATH=.work/py python3 tests/uiflow2/api_sweep/run_espnow_pair.py \
  --api http://127.0.0.1:8811 \
  --token-file /tmp/m5-espnow-token \
  --scenario lifecycle \
  --left-device core2 --right-device stopwatch \
  --out-dir /tmp/m5-espnow-lifecycle
```
