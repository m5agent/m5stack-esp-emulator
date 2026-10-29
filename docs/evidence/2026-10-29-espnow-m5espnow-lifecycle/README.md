# 2026-10-29：M5ESPNow wrapper peer lifecycle

## 范围

使用 stock UIFlow2 `m5espnow.M5ESPNow` wrapper 验证 external encrypted
peer 生命周期：

- `set_pmk_encrypt` + `set_add_peer(..., encrypt=True)`；
- `peer_count=[1,1]` 且 `get_peer_list(1)` 包含目标 peer；
- bidirectional PRE barrier 后 `set_delete_peer(1)`；
- peer table 回到 `[0,0]`，`get_peer_list(1) == []`；
- wrapper 的 delete 后 `send_data` 保持 no-op，不抛异常；
- 重新 `set_add_peer` 后 peer list/count 恢复；
- post-resume encrypted payload 双向交付。

全部结果为 **virtual-device validation**。M5ESPNow 以 string LMK/PMK 和
peer-id API 封装原生 ESP-NOW；QEMU bridge key 仍来自 external fixture，
因此本轮不证明 guest key-state 写入 bridge。

| 项目 | SHA256 |
| --- | --- |
| QEMU runtime | `be7c376550829427b0fc72ada75f9d06e2246feaa64b2c222904d5a17a3c4076` |
| `tests/uiflow2/api_sweep/run_espnow_pair.py` | `6cf511cd66e5f2a1580ee87c8ec63f50952428d22e8b428e427048859a294fd9` |

## 结果

| 设备对 | 设备 | firmware SHA256 | bridge TX/RX | lifecycle | evidence SHA256 |
| --- | --- | --- | ---: | --- | --- |
| StopWatch↔StickS3 | StopWatch | `f1cd663551e9733903a97dcf59a5ead9aa577c299978dd7fef7a33f1d05605b6` | 15/15 | PASS | `415ecadfd593d6a592c13d61ac88c44ef013276b80be7b502f37a8ad864ff1cd` |
| StopWatch↔StickS3 | StickS3 | `6ab4ffda8912de24c7f274a7d085e81baa510359af2c25609efa99c3370d9748` | 15/15 | PASS | `e1ba6c52f1c5cdaf9124e488b6576f1b53639ca0031b700a7851bddeca1036ec` |
| Core2↔StopWatch | Core2 | `5473429682d2177b43f6906bb80b9e566f9d79f9aa1baa35fe30e68eef4ce981` | 21/32 | PASS | `c28fcbdc1aac710cbbb640484d9036b793693bd7141c0cce40b3a94ee3896387` |
| Core2↔StopWatch | StopWatch | `4013d31632cecd446591f038606e7ba2b896a5bf97db2659a8ad90c4e487b325` | 33/21 | PASS | `0ecfd18a96a33640b087450af3f1a226af4ad2fcffbfb53cc6beea9fec900bbd` |

四个 session 均满足：

- `initial_count=[1,1]` 且 registration PASS；
- `pre_synced=true`；
- delete 后 `deleted_count=[0,0]`、`deleted_peer_list_empty=true`；
- `send_after_delete_noop=true`；
- re-add 后 `readded_count=[1,1]`、`peer_list_restored=true`；
- `post_resumed=true`；
- terminal `stopped`、runtime PID gone、history retained、`purge=0`。

## 未关闭

- guest key-state 写入 QEMU bridge 和 key rotation；
- multi-peer/乱序 replay window、loss/retry；
- channel/rate、bit-exact controller；
- RF、antenna、AP coexistence、电气、timing 和 physical hardware。

`RUNTIME-06` 仍为 `PARTIAL`。本轮关闭的是 stock M5ESPNow wrapper 的
add/delete/re-add 生命周期和恢复传输。

## 复现入口

```bash
export M5_CORE2_RADIO_QEMU="$PWD/.work/M5StopWatch-QEMU/build/qemu/build/qemu-system-xtensa"
PYTHONPATH=.work/py python3 platform/tools/serve.py 8811 \
  --bind 127.0.0.1 \
  --state-dir /tmp/m5-espnow-m5-wrapper-state \
  --api-token-file /tmp/m5-espnow-token

PYTHONPATH=.work/py python3 tests/uiflow2/api_sweep/run_espnow_pair.py \
  --api http://127.0.0.1:8811 \
  --token-file /tmp/m5-espnow-token \
  --scenario lifecycle-m5espnow \
  --left-device core2 --right-device stopwatch \
  --out-dir /tmp/m5-espnow-m5-wrapper
```
