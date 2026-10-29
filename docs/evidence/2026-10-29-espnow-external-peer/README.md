# 2026-10-29：ESP-NOW 两个独立 guest 的明文 action-frame 交换

## 范围

本轮验证 `RUNTIME-06` 的外部 peer 基线：两个独立 Device Service session
分别运行 StopWatch、StickS3 或 Core2 的原厂 UIFlow2 `v2.5.3` guest，
通过显式配对的 IPv4 loopback UDP 端口交换 ESP-NOW management action frame。

全部结果为 **virtual-device validation**。物理硬件、RF、天线、channel/rate、
电气时序、AP 共存和 timing 均为 `NOT RUN`。

| 项目 | SHA256 |
| --- | --- |
| QEMU runtime | `df0e20f176494a9de8e32361dbc865688c5e72791207793d0bdb0b5a947b616a` |
| `0076-esp32-external-espnow-peer-bridge.patch` | `de39dd922d15bc2ad3827a13293d86dc2a2f0dafcfe2036783730dfab8037c62` |
| `tests/uiflow2/api_sweep/run_espnow_pair.py` | `a5bfcb7a7a1a88a64c3464a1ac7437a0b78080b887b0d86e5305918faedd780a` |

## 实现边界

`0076` 默认关闭；只有两个独立 controller 同时配置成对的
`M5SW_ESPNOW_PEER_LOCAL_PORT` / `M5SW_ESPNOW_PEER_REMOTE_PORT` 时才启用。
该 lane：

- 只转发 802.11 management action frame；
- 发送端仍从 guest 经正常 controller TX DMA 写帧；
- 接收端仍把 peer frame 注入目标 controller 的正常 RX DMA；
- 在 controller 边界绑定当前 session 的 station MAC 和 RX filter；
- 拒绝缺失/相同端口、非法端口及与 `0067` 同 guest loopback 混用；
- 不构造 Python payload、不直接调用 guest callback。

两轮测试使用固定受控 peer `02:00:00:00:00:43`。每侧发送自己的
`PAIR_PLAINTEXT:A/B`，只接受对方的 role payload；接收窗口为 12 秒，
避免 Core2 较慢的 UIFlow2 网络初始化被 4 秒窗口误判为失败。
`encrypt=False`，因此本轮只覆盖未加密 ESP-NOW。

## 结果

### StopWatch ↔ StickS3

| 设备 | session | firmware SHA256 | TX trace | RX trace | 收到对方 payload | source/payload match | evidence SHA256 |
| --- | --- | --- | ---: | ---: | ---: | ---: | --- |
| StopWatch | `15408c03af30478999ef27385c9b0ee4` | `69ab9a2fad35401209d36e60e23270a604f4defb5228e8d64c05bb118beac36c` | 58 | 58 | 57 | 57/57 | `df23a410354e0399cf52ade816ac749dd9b45d02c43cd6d763486cb63bb99a51` |
| StickS3 | `d700433e22884fa198e73f9bf9e4871b` | `05544f977fdb375c185f94e6161920561ef9e07666fb5354bd259ee6b1be3e3b` | 58 | 58 | 58 | 58/58 | `5dd98062bec54bb0013cf8fe49621a8698fc0110b3b4e527d150d4a11aaf7a21` |

### Core2 ↔ StopWatch

| 设备 | session | firmware SHA256 | TX trace | RX trace | 收到对方 payload | source/payload match | evidence SHA256 |
| --- | --- | --- | ---: | ---: | ---: | ---: | --- |
| Core2 | `cdeae8a415704d54b8be88f5108b0786` | `a5323bf37e7ba92f622b65eea759d2dd9a6c5144385b6db166a5886e0218aabb` | 44 | 32 | 14 | 14/14 | `810bdf60b2a1b307b37adf832c185504ab03d8d98604aa7f3e04bdf7cbc47cfe` |
| StopWatch | `a8b60a0d4cbb49d0b4d2cbe9ce0351f0` | `4b0838fe8fda88a85124558df1add2d37738b8c157c352bea83c720776924f21` | 48 | 44 | 44 | 44/44 | `107e685f5b28faac0ed15021d3fc2555c6d632e41ad9d6f91788c8ab9e1cfb77` |

两轮共四个独立 session 均为 terminal `stopped`，`runtime_pid_gone=true`，
停止使用 `purge=0`，停止前取得 serial/frame/evidence ZIP；历史保留且没有
残留 QEMU/runner。原始 ZIP、serial、frame 和完整 stderr 只保存在 ignored
`.work/`。机器摘要见 [summary.json](summary.json)。

## 未关闭

- PMK/LMK、CCMP、错误 key 和加密 payload；
- peer add/update/delete、replay、loss/retry 和更完整生命周期；
- 多于两个 peer 的 fabric、channel/rate、bit-exact controller；
- RF、天线、AP 共存、电气和 timing；
- 物理硬件同路径验证。

因此 `RUNTIME-06` 仍为 `PARTIAL`：本次只关闭“两个独立 guest 的未加密
action-frame 交换”，不能把 loopback、external plaintext 或同 SoC 结果扩展成
加密、RF 或真机 PASS。

## 复现入口

```bash
export M5_CORE2_RADIO_QEMU="$PWD/.work/M5StopWatch-QEMU/build/qemu/build/qemu-system-xtensa"
PYTHONPATH=.work/py python3 platform/tools/serve.py 8810 \
  --bind 127.0.0.1 \
  --state-dir /tmp/m5-espnow-state \
  --api-token-file /tmp/m5-espnow-token

PYTHONPATH=.work/py python3 tests/uiflow2/api_sweep/run_espnow_pair.py \
  --api http://127.0.0.1:8810 \
  --token-file /tmp/m5-espnow-token \
  --scenario plaintext \
  --left-device stopwatch --right-device sticks3 \
  --out-dir /tmp/m5-espnow-stopwatch-sticks3

PYTHONPATH=.work/py python3 tests/uiflow2/api_sweep/run_espnow_pair.py \
  --api http://127.0.0.1:8810 \
  --token-file /tmp/m5-espnow-token \
  --scenario plaintext \
  --left-device core2 --right-device stopwatch \
  --out-dir /tmp/m5-espnow-core2-stopwatch
```
