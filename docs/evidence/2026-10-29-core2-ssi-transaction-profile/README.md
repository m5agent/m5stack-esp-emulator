# 2026-10-29：Core2 legacy SSI transaction profile

## 结论

新增默认关闭的 controller 级 SSI transaction profile。它不依赖
`M5SW_ESP32_HANDOFF_TRACE_SAMPLE=1024` 的抽样事件，而是在冻结点输出：

- 完整 16-bit command 计数；
- RX payload length `0..255` 与 `256+` bucket；
- completion 后到下一 command 的 virtual-time gap bucket；
- gap count、总时长、最大值和最后一次 transaction-end 时间。

同一 public `UIFlow_Core2 v1.15.4` SHA 的两轮 WDT-off 控制得到稳定请求
序列：约 `49.5k` 个 `0x05` RDSR、约 `49.6k` 个 `0xBB` Dual-I/O Fast
Read，以及相近数量的 1-byte / 64-byte RX transaction。command、
RX-length 和 gap 三个直方图的总数分别严格等于 transaction 数或
`transaction-1`。

在关闭 PC sampling 的控制中，相邻 transaction 的 virtual-time gap 合计
`79.699109375 s`，占 80 秒窗口的约 `99.6%`。这说明当前瓶颈不是日志抽样
漏掉的单次超大 controller 传输，也不是约十万次 transaction 都隐藏在
controller C 数据面内；主要工作发生在 guest 两次 SPI command 之间。
normal-WDT 仍在 `17.253695649 s` reset，instrumentation 没有改变
`RUNTIME-03` 边界。

## 请求分布

关闭 PC sampling 的 WDT-off 80 秒控制：

| Command | Count | 说明 |
| --- | ---: | --- |
| `0x05` | `49,489` | RDSR / status read |
| `0xBB` | `49,586` | Dual I/O Fast Read |
| `0x00` | `5,135` | no-command controller transaction |
| 其它 | `92` | `0x01`、`0x02`、`0x06`、`0x20`、`0x35`、`0x9f`、`0xab` |
| 合计 | `104,302` | 与冻结 transaction counter 相等 |

RX length：

| RX bytes | Count |
| ---: | ---: |
| `0` | `1,653` |
| `1` | `53,054` |
| `64` | `49,586` |
| 其它 | `9` |
| 合计 | `104,302` |

`0x05` 与 64-byte read 数量接近，RX-length `1` 与 `64` 的数量也接近；
当前结果证明控制器边界确实收到约五万组独立 status/64-byte command。
由于尚未输出 command-length 联合键，仍不把“每次 0xBB 后恰好一次
0x05”写成严格配对结论。

## Completion 到下一 command

关闭 PC sampling：

| Gap | Count |
| --- | ---: |
| `0 ns` | `0` |
| `1..1,000 ns` | `0` |
| `1,001..10,000 ns` | `50,581` |
| `10,001..100,000 ns` | `3,936` |
| `100,001..1,000,000 ns` | `23,800` |
| `1,000,001..10,000,000 ns` | `25,819` |
| `10,000,001..100,000,000 ns` | `94` |
| `100,000,001..1,000,000,000 ns` | `69` |
| `>1,000,000,000 ns` | `2` |

gap count `104,301`、总和 `79,699,109,375 ns`、最大
`2,693,165,726 ns`。PC sampling 开启的同 SHA 控制为
`104,974` transactions、`79,694,773,694 ns` gap 总量和
`2,678,539,837 ns` 最大值，分布形状一致；因此采样只带来轻微扰动。

## Normal WDT 回归

同一 `fbc2850c…` QEMU 和 `4d2d648b…` 固件的正常 WDT 控制：

- TG0 stage-0：`7.253601472 s`；
- TG0 stage-1 timeout：`17.253601473 s`；
- 首次 reset：`17.253695649 s`；
- TG1 reset 前 feed：`14,998`；
- TG1 最大 feed interval：`3.926687 ms`；
- TG1 timeout：`0`；
- classification：`BOOTLOADER_TG0_STAGE1_RESET_WITH_TG1_LIVE`。

这些值与 instrumentation 前的 `7.2536 s / 17.2536 s` 基本重合。
`RUNTIME-03` 仍为 `OPEN`。

## 改动

`0071-esp32-ssi-transaction-profile.patch`：

- 在现有 `Esp32HandoffMetrics` 增加 command、RX-length 和 gap 聚合；
- 每笔 transaction 开始时统计上一笔 end→本次 start 的 gap；
- 继续使用现有 metrics reset 生命周期；
- 只在显式 pause/freeze dump 时输出非零 histogram；
- 不调用 scheduler accelerator、不扩大 timeout、不关闭 WDT、不改变
  SSI transaction 数据。

`run_pause_sweep.py` 现在从冻结 trace 输出
`ssi_command_histogram`、`ssi_rx_length_histogram` 和
`ssi_gap_histogram`，并验证 command/length 总数等于 transaction 数、
gap 总数等于 `transaction-1`。

## 身份

| 项目 | 值 |
| --- | --- |
| QEMU SHA256 | `fbc2850c924d535d6c3a2c5dedf5772fec403da6e36ccecf20d811de1cf81fbe` |
| 0071 patch SHA256 | `3c53c5a74128891988d73addfed710c865f094b188a30be47f661beca72afc6c` |
| Firmware | `UIFlow_Core2 v1.15.4` |
| Firmware SHA256 | `4d2d648bd8707a1789d540366015a1b90dc816b66a04163048626ea29e333ed4` |
| Runtime | `qemu-wifi`, `icount shift=5` |
| Hardware validation | `NOT RUN` |

## 边界与下一步

- 当前 profile 是 virtual-device controller 事件观测，不是物理 Flash、
  cache、总线、功耗或实时性能测量；
- 尚未取得 matching legacy source/ELF/MAP，不能把 guest command cadence
  直接归因到具体函数；
- 下一步需要输出 command-length 联合键和按 command 的 gap 统计，确认
  每个 64-byte read 后的 status 轮询来源与等待类型；
- 随后定位 guest 在两次 command 之间执行的 driver/IRQ 路径，以及
  normal-WDT 前为什么需要约 55 秒才能到 BOARD/APIKEY；
- WDT-off、扩大 timeout、accelerator override 和 retry 都不是产品修复。
