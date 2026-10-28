# 2026-10-29：Core2 M5UI panel DMA 双写修复

## 结论

Core2 M5UI candidate 全屏刷新条带/坐标错误的根因不在 M5UI 源码、MADCTL
或 rotation，而在 classic ESP32 SPI panel 模型对同一笔 DMA flush 的二次
消费：

1. guest 写 `DMA_LINK` 时，模型已经按 descriptor 把完整像素写进 panel；
2. 随后 `SPI_CMD` 事务又走 CPU data-register 路径，把 64-byte 寄存器内容
   及其重复 tail 再写一次；
3. 一个 `320x10` 的 RGB565 strip 应消费 `6,400` bytes，修复前实际写成
   `12,736` bytes（`12,736 = 2 * 6,400 - 64`），导致尾部像素反复覆盖并
   形成条带。

`0074-esp32-spi-panel-dma-dedup.patch` 在当前 command 已消费 panel DMA 时，
暂时跳过 CMD 路径的 CPU-register replay，并在 transaction 结束后清状态；
同时增加 opt-in `M5SW_PANEL_RAMWR_TRACE`，对 RAMWR window 期望字节数和
实际写入数逐笔核对。

同一 hash-pinned M5UI candidate 的最终结果：

| 检查 | 修复前 | 修复后 |
| --- | ---: | ---: |
| M5Canvas triangle state | `STATE_PASS` | `STATE_PASS` |
| M5Image set_scale state | `STATE_PASS` | `STATE_PASS` |
| Spinbox integer/decimal state | `2/2 STATE_PASS` | `2/2 STATE_PASS` |
| triangle frame oracle | `FAIL` | `FRAME_PASS` |
| image scale frame oracle | `FAIL` | `FRAME_PASS` |
| RAMWR byte-count mismatch | `49/54` | `0/54` |

最终帧 SHA256 为
`5a074d2987258112f79cecc800578df7325e6f35c32ceace859b828c8f942403`，
画面包含标题、cyan triangle、四色缩放图与 Spinbox，不再有条带。

## RAMWR 证据

hash-pinned candidate 的 flush 包含：

- `48` 个 `320x10` strip，每笔 expected `6,400` bytes；
- `5` 个 `320x240` 全屏 clear，每笔 expected `153,600` bytes；
- `1` 个 `20x60` image window，expected `2,400` bytes。

修复前，48 个 strip 全部写成 `12,736` bytes，20x60 window 写成
`4,736` bytes；只有不使用 DMA 的 5 个全屏 clear 为 exact。修复后 54 个
window 全部 `written == expected`。

## 被否决的控制

- 把 Core2 panel 的 `apply-madctl` 从 `false` 改为 `true` 后，同一 candidate
  仍得到相同条带帧，不能解释问题；
- 将 M5UI rotation 从 `1` 改为 `0` 后，文字方向改变，但条带仍存在；
- 在 READY 后等待额外时间重新取帧，frame hash 与 RUN 完成时完全相同。

因此问题被绑定到 panel DMA/CMD 双消费，而不是旋转语义或 capture timing。

## 当前 QEMU 的三设备 smoke

同一 QEMU `9bf74439…` 上并发重跑 StopWatch、StickS3、Core2 的
system runtime 与 shared corrections：

| 设备 | System | Shared | Evidence ZIP SHA256（system / shared） |
| --- | ---: | ---: | --- |
| StopWatch | `50 PASS + 1 STATE_PASS` | `7/7 PASS` | `59e4f5c3…` / `72b4a612…` |
| StickS3 | `50 PASS + 1 STATE_PASS` | `7/7 PASS` | `fb8cd5a7…` / `531bbf0a…` |
| Core2 | `50 PASS + 1 STATE_PASS` | `7/7 PASS` | `74a1e4d8…` / `a9062703…` |

StopWatch/StickS3 使用 ESP32-S3 panel 路径，不经过本次 classic ESP32 DMA
去重；该 smoke 只证明当前同 binary 的通用 runtime/shared 接口无回归。

## 身份

| 项目 | 值 |
| --- | --- |
| Base UIFlow2 SHA256 | `2a91964f4ef1b4823adc4b7b13fa08ddb2166ead3b96c74fe2088a71c4e3ea2a` |
| Candidate composed firmware SHA256 | `cd9bbacd97884708d2264baf87fa541519000fe674c58867f8371e1adfd785d9` |
| Candidate source SHA256 | `68da5e2ef246ff503ef8001d5c03a2f2bcd392e934de5e42c9bcd9e8a5571895` |
| QEMU SHA256 | `9bf74439ddbe7225a64eb437290043729fb032525756adb834565ec412f8c197` |
| 0074 patch SHA256 | `cda59c76952e2f0c9d094e546b998d01636810daeabbfad5f96d07d16d47ad9b` |
| Final frame SHA256 | `5a074d2987258112f79cecc800578df7325e6f35c32ceace859b828c8f942403` |
| Evidence ZIP SHA256 | `82a1d59ba0fa3f55f37f87ff7c70258abafe915b5cde3662ed79f61cc70a8eae` |
| Hardware validation | `NOT RUN` |

全部为 virtual-device validation。该结果关闭当前 Core2 candidate M5UI
frame oracle 的模型缺陷；不证明物理 ILI9342 panel、DMA/SPI 时序、电气或
真机视觉等价。

## 复现

候选与 UI runner：

```bash
tests/uiflow2/api_sweep/run_ui_live.py \
  --api <isolated-device-service> \
  --session-id <running-uart-repl-session> \
  --device core2 \
  --lane corrections \
  --candidate-dir <hash-pinned-candidate> \
  --out-dir /tmp/core2-m5ui-corrections
```

RAMWR 核对：

```bash
M5SW_PANEL_RAMWR_TRACE=1 <device-service>
```

原始 frame、serial、evidence ZIP 和完整 trace 只保留在 ignored `.work/`；
本页与[机器摘要](summary.json)保存公开计数、哈希和边界。
