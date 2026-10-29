# 2026-10-29：ESP-NOW loss/retry、channel/rate 与 60 秒 soak

## 范围

`0084-esp32-espnow-loss-channel-rate.patch` 在两个独立 controller 的
action-frame bridge 上增加 8-byte、带版本号的 channel/rate envelope。guest
payload、CCMP、replay window、key routing 和 RX DMA 仍走原有路径；新增元数据
只描述虚拟 bridge link。全部结果为 **virtual-device validation**。

第一次同信道测试把 `add_peer(channel=6)` 用在仍连接 channel 1 AP 的 stock
driver 上，guest 自身记录 `Peer channel is not equal to the home channel` 并
拒绝发送。该失败保留为测试前提负控；最终探针会完成 Wi-Fi 基线、断开并从目标
home channel 重新激活 STA，再进入 ESP-NOW。

## Bridge 语义

- envelope 固定包含 magic、version、channel、rate 和保留字节；
- RX 在 action-frame/CCMP/DMA 处理前拒绝截断、错误 magic/version、
  超大 frame、异 channel 和不支持的 rate；
- channel 只接受 1–14，TX rate 只接受
  `1/2/6/9/11/12/18/24/36/48/54 Mbps`；
- 被交付 frame 进入 controller RX metadata 时携带 envelope 的
  channel/rate；该 envelope 是受信测试 fixture、位于 CCMP 外，不是
  authenticated security field；
- channel/rate runtime env 只能与 explicit external peer bridge 组合；
- 不建立 RF propagation、天线、速率自适应、bit-exact timing 或物理控制器
  PASS。

| 项目 | SHA256 |
| --- | --- |
| QEMU runtime | `54e7a7f7cd0ff6f5a1d6343c06563388f49c2b0abbca4cafb850876e57ed1254` |
| `0084` patch | `91ef766541a9802336d5a3efaefc38fd28f5d7ea55107e605e2ec37fdf2594fc` |
| runner | `f0416d4d2acc396a49a830d507530145af07111563cc8e0184623c4d2c535ef2` |

## 主路径

loss/retry 使用真实 UDP fault proxy，在双向流量建立后丢弃 StopWatch→StickS3
的前两帧。proxy 记录 `2` drop、`56/58` forwarded，应用层重试后两端 payload
PASS；各端发送 `58` 次、`tx_errors=0`。

同 channel 正控在两端连接后切换到 channel 6，stock `get_peer`/delivery
均为 channel 6；双向 frame 与 controller RX metadata 都是
`channel=6/rate=11`。

异 channel 负控保持 A=1、B=6。所有真实 controller frame 均离开 guest，
bridge 两端各记录 `40` 次 channel mismatch，正常 RX DMA delivery 为 `0`，
guest payload 为 `EXPECTED_DROP`。

混合 rate lane 在 channel 6 上让 StopWatch 以 11 Mbps、StickS3 以 24 Mbps
发送。两端 payload PASS；A 收到的 metadata 为 24 Mbps，B 收到 11 Mbps，
证明发送端与接收端 rate 元数据没有被静态值覆盖。

| 场景 | 结果 | 关键计数 |
| --- | --- | --- |
| loss/retry | PASS | proxy drop `2`；A/B payload matches `57/56` |
| channel 6 ↔ 6 | PASS | 两端 TX/RX `58/58`；channel drop `0` |
| channel 1 ↔ 6 | PASS negative | 两端 channel drop `40/40`；RX packet `0/0` |
| rate 11 ↔ 24 Mbps | PASS | 两端 59 TX；互见对端 rate metadata |
| 60-second soak | PASS | A TX/RX `528/527`；B `527/528`；payload `526/527` |

60 秒 soak 的 duplicate payload、unexpected source 和 TX error 均为 `0`。
所有最终 session 使用 `purge=0`、terminal `stopped`、runtime PID gone，
history retained。

## 回归

最终 QEMU 上重新执行：

- direct encrypted guest-key pair：PASS；
- replay proxy：目标端 `replay_drops=1`，PASS；
- reorder proxy：两端 `replay_drops=0`，PASS；
- shared-LMK / pairwise-LMK 三 guest fabric：PASS；
- B/A cross-wire 负控：只有 A↔B payload 归零，PASS；
- PN exhaustion + new-LMK rekey：两端各 65 次 exhaustion，post payload
  `166/164`，PASS。

`0084` patch forward/current-source/reverse check PASS；平台全量为
`1526 OK + 1 skipped`，runtime coverage、peripheral catalog、QEMU profiles、
project snapshot、compileall 与 Node contracts 均 PASS。CI 在本里程碑提交
后执行。

## 未覆盖

- bit-exact controller/baseband；
- RF propagation、天线、channel 测量和速率自适应；
- 电气时序；
- physical hardware validation。

## 复现入口

```bash
export M5_CORE2_RADIO_QEMU="$PWD/.work/M5StopWatch-QEMU/build/qemu/build/qemu-system-xtensa"
PYTHONPATH=.work/py python3 platform/tools/serve.py 8811 \
  --bind 127.0.0.1 \
  --state-dir /tmp/m5-espnow-loss-state \
  --api-token-file /tmp/m5-espnow-token
```

主场景：

```bash
PYTHONPATH=.work/py python3 tests/uiflow2/api_sweep/run_espnow_pair.py \
  --api http://127.0.0.1:8811 \
  --token-file /tmp/m5-espnow-token \
  --scenario loss-retry \
  --left-device stopwatch \
  --right-device sticks3 \
  --out-dir /tmp/m5-espnow-loss-retry
```

将 `--scenario` 改为 `channel-match`、`channel-mismatch`、`rate-mixed` 或
`soak --soak-seconds 60`，并使用新的输出目录。
