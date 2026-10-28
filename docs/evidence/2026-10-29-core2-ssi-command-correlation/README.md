# 2026-10-29：Core2 legacy SSI command correlation

## 结论

新增 `0072-esp32-ssi-command-correlation.patch`，在 `0071` 的独立
command、RX-length、gap 聚合之上增加：

- command-length 联合键；
- completion→next-command gap 的按 command 汇总；
- command transition（前一 command → 当前 command）；
- 每个稀疏表的有界 overflow 计数。

同一 public `UIFlow_Core2 v1.15.4` SHA 的 80 秒 WDT-off 控制得到
`105,346` transactions。`0xBB/64 -> 0x05/1` 为 `49,582` 次，
`0x05/1 -> 0xBB/64` 为 `49,600` 次，形成稳定的
“64-byte Fast Read → status read → 下一次 Fast Read”循环。

`0x05` 前的相邻 command gap 合计 `65,670,563,678 ns`，占全部 gap 的
`82.398%`，平均 `1.3115489 ms`；`0xBB` 前仅 `152,263,360 ns`
（`0.191%`），平均约 `3.05 us`。因此当前预算主要落在 64-byte read
之后、下一次 status read 之前的 guest 工作区，而不是 controller 收到
status command 后的单次数据操作。

`RUNTIME-03` 仍为 `OPEN`；下一步需要在这段 gap 内取得 guest PC/驱动
路径，或取得 matching legacy source/ELF/MAP。

## 联合分布

主要 command-length：

| Command / RX bytes | Count |
| --- | ---: |
| `0x05 / 1` | `50,071` |
| `0xBB / 64` | `49,882` |
| `0x00 / 0` | `1,561` |
| `0x00 / 1` | `3,567` |
| 其它 | `265` |
| 合计 | `105,346` |

联合表总计 `105,346`，overflow `0`。

## Command transition

主要转移：

| Transition | Count |
| --- | ---: |
| `0xBB -> 0x05` | `49,582` |
| `0x05 -> 0xBB` | `49,600` |
| `0x00 -> 0x00` | `5,113` |
| `0xBB -> 0xBB` | `282` |
| `0x05 -> 0x05` | `212` |
| 其它 | `556` |
| 合计 | `105,345` |

transition 总数等于 `transactions - 1`，overflow `0`。

## Gap attribution

| 当前 command | Gap count | Total gap | Share | Average |
| --- | ---: | ---: | ---: | ---: |
| `0x05` | `50,071` | `65,670,563,678 ns` | `82.398%` | `1.3115489 ms` |
| `0x00` | `5,133` | `13,849,241,407 ns` | `17.377%` | `2.698079 ms` |
| `0xBB` | `49,882` | `152,263,360 ns` | `0.191%` | `3.05 us` |
| 其它 | `259` | `28,533,432 ns` | `0.036%` | 约 `110 us` |

全部 gap：`105,345`、总时长 `79,699,282,877 ns`、最大
`2,687,751,164 ns`。按 command 汇总总数与全局 gap 数相等，overflow `0`。

## Normal WDT

同一 `4aa418e6…` QEMU 的 normal-WDT 控制：

- stage-0 timeout：`7.249439872 s`；
- stage-1 timeout：`17.249439902 s`；
- 首次 reset：`17.249440926 s`；
- TG1 reset 前 feed：`14,999`；
- TG1 最大 feed interval：`3.926688 ms`；
- TG1 timeout：`0`；
- classification：`BOOTLOADER_TG0_STAGE1_RESET_WITH_TG1_LIVE`。

新联合 instrumentation 没有改变 `RUNTIME-03` 的 reset 边界。

## 身份

| 项目 | 值 |
| --- | --- |
| QEMU SHA256 | `4aa418e6cba1a6d7104906ff88991c62c85e02661fa6ba4e256743f13b6753ba` |
| 0072 patch SHA256 | `107cc478b2a4157d391d6d3331a141683ee61ed37d06ba81244afb92324fa024` |
| Firmware | `UIFlow_Core2 v1.15.4` |
| Firmware SHA256 | `4d2d648bd8707a1789d540366015a1b90dc816b66a04163048626ea29e333ed4` |
| Runtime | `qemu-wifi`, `icount shift=5` |
| Hardware validation | `NOT RUN` |

## 边界与下一步

- 当前仍是 virtual-device controller instrumentation；
- `0x05` 的 RDSR、`0xBB/64` 的 Fast Read 和交替顺序已确认；
- 仍未把 1.31 ms gap 绑定到具体 guest driver/IRQ 函数；
- 下一步在这些 gap 内做低频 PC 聚类或加入 transaction-bound PC 采样，
  并尝试取得 matching source/ELF/MAP；
- WDT-off、扩大 timeout、accelerator override 和 retry 都不是产品修复。
