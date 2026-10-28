# 2026-10-28：Core2 UIFlow2 触控条与电源键回调

## 范围

在独立 Device Service 中，以 stock UIFlow2 `v2.5.3` Core2 镜像
`b228c0e2d877e77a8a352e917ed84f4da8ea92d15b25e28f431a2999620fe3c4`
验证 `BtnA`、`BtnB`、`BtnC` 和 `BtnPWR` 的
`setCallback.WAS_HOLD`、真实 host input、guest 状态与
`removeCallback`。

最终 QEMU runtime SHA256：

`03d74d53ff8187c4f0a3b22d34c4e898bdd93b61cfc98432dbbeecd1beb12419`

全部结果是 **virtual-device validation**；物理触控压力、PMIC 电气行为和
真机为 `NOT RUN`。

## 结果

| 输入 | 对接路径 | guest 坐标 | 回调 | remove 后新事件 | firmware SHA256 |
| --- | --- | --- | --- | ---: | --- |
| `key:a` | FT5x06 左侧触控条 | `(53,260)` | `[2]` PASS | 0 | `2870ad6dd2d3035ba72b01e85f0f5cd3849cf9bf27b02cfa02bf8e8e17c78773` |
| `key:b` | FT5x06 中间触控条 | `(160,260)` | `[2]` PASS | 0 | `3f695a26b0664222a605f150d749aabe3dfa1e14075898b36db0e51838ac1ffd` |
| `key:c` | FT5x06 右侧触控条 | `(266,260)` | `[2]` PASS | 0 | `d5164dad38a37f2670beb998a84dc39812c99bc1375ae9f73be9ebde94e7130e` |
| `key:p` | AXP2101 `IRQ_STATUS1(0x49)` | n/a | `[2]` PASS | 0 | `0d64d250e742407e7591fe3fde26537ac140a532819c144808ad81382ed70725` |

四个独立可见 session：

- `BtnA`：`acf00a9a021b422cbf146bd9028beeb6`
- `BtnB`：`c9d6d6d63ae543d59220309a575bca9b`
- `BtnC`：`b7e83b010d684ea98d43030291506d46`
- `BtnPWR`：`48db772a52334eeb8a80711b2db233a3`

每例只允许一次目标回调；A/B/C 同时观察到 pressed、holding 和 released
状态，`removeCallback` 后不再调度新事件。`BtnPWR` 是 AXP2101 事件型
输入，不伪造连续 GPIO level。

## 根因与修复

Core2 的 A/B/C 不属于通用 ESP32 GPIO 按键，而是 FT5x06 下方触控条。
`0063-core2-touch-buttons.patch` 在 panel controller 内把三个键同步为
FT5x06 触点。

首版 `0063` 对 `touch_buttons` 的所有键码都提前 `break`，因此也吞掉了
同一切换块后面的 `Q_KEY_CODE_P -> m5sw_pwr_button()` 路径。修复只在
`A/B/C` 时进入触控条分支并 `break`；`P` 继续落到 AXP2101 电源键事件路径。

## 回归

- `test_core2_touch_buttons_patch.py` 重放 patch，并检查 P 电源键路径仍位于
  触控条分支之后可到达。
- A/B/C/PWR 在最终 runtime 上全部以同一模式重新执行。
- 所有 session 都先请求 evidence ZIP，再以 `purge=0` 停止；QEMU PID 消失、
  历史与最后帧保留。

原始 serial、frame、ZIP 和 host action 保存在 ignored `.work/`，本页只保留
可复现摘要和哈希。
