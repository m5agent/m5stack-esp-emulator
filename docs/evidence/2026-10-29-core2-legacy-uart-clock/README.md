# 2026-10-29：Core2 legacy UART 与虚拟时钟对齐

## 范围

本页继续跟踪 `RUNTIME-03`。目标是把 legacy Core2 的 MicroPython 串口输出、
TIMG watchdog 和 SSI/DPORT handoff 放到同一条 QEMU 虚拟时间轴上，判断
normal-WDT reset 是否来自 display completion、watchdog register 或 boot
生命周期中的一个局部错误。

全部结果为 **virtual-device validation**；物理硬件和电气时序为 `NOT RUN`。

## 诊断修复

新增
[`0070-esp32-uart-tx-virtual-clock.patch`](../../../patches/qemu-m5stack-peripherals/0070-esp32-uart-tx-virtual-clock.patch)，
在既有默认关闭的 `M5SW_UART_TRACE` 每字节输出中加入
`qemu_clock_get_ns(QEMU_CLOCK_VIRTUAL)` 时间戳。UART 数据路径、guest 指令、
watchdog 和 accelerator 均未改变。

新 QEMU SHA256：

`f0eb5f6c26f82ce99d6dad4006fcd0748991ba1a8d1ce780092d57d01d8e798e`

补丁 SHA256：

`43e7771613dd4a1dbcb66056961ed8c6bfa496d6128b019b4113e5e9e989ea40`

`run_pause_sweep.py` 同步增加 `[uart-tx] now=...` 行重组和 512 行上限，
使 evidence JSON 直接保留串口行首/行尾虚拟时间，而不再只依赖另一个
serial 文件。

## 正常启动时间线

公开 UIFlow_Core2 v1.15.4 的 normalized Flash SHA256：

`4d2d648bd8707a1789d540366015a1b90dc816b66a04163048626ea29e333ed4`

在 `runtime=qemu-wifi`、`icount shift=5`、WDT-off 诊断控制和 80 秒
exact-time sampling 下：

| 串口行 | 虚拟时间 |
| --- | ---: |
| MicroPython banner 完成 | `2.772445 s` |
| `BOARD NAME: M5STACK-CORE2` | `54.995475 s` |
| `APIKEY` | `55.001658 s` |
| `CORE2_LEGACY_ORIGINAL_BOOT_START` | `77.109223 s` |
| `CORE2_LEGACY_ORIGINAL_BOOT_DONE` | `77.615129 s` |

80 秒状态点两核仍在运行：

- CPU0 `0x4008798e`、CPU1 `0x40095b31`；
- SSI 累计 `104,061` transactions、`3,219,821` RX bytes；
- DPORT cache-sync `218,396`、changed pages `5,911`；
- cross-core writes `432,918`；
- frame 未捕获，不能从该状态点声明 visual PASS。

这说明正常 boot 在 board/APIKEY 之前并非永久 deadlock；它在持续执行
Flash/cache handoff 和 guest 工作，只是远晚于 normal-WDT 的 stage-1
deadline。具体数字只属于本 fixture/runtime，不外推到物理 Core2 启动时间。

## WDT 对照

同 QEMU 的 normal-WDT `shift=5` baseline 仍在：

- stage-0 timeout `7.2529 s`；
- stage-1 timeout `17.2529 s`；
- first reset `17.2529 s`。

显式 `shift=2` 诊断一轮在更长墙钟窗口内仍完成 reset：

- stage-0 timeout `5.5609 s`；
- stage-1 timeout `15.5609 s`；
- first reset `15.5609 s`；
- serial 仍没有 BOARD NAME/APIKEY，TG1 持续 feed，`0` 次 TG1 timeout。

因此降低 icount shift 只改变 host/virtual 执行速率，不消除该启动期
WDT 门禁。不能将 accelerator override 当作 `RUNTIME-03` 修复。

## 当前判断

`0069` 已排除 protected WDTFEED 被模型丢弃。新的时间线把剩余问题收敛为：

1. legacy guest 在 boot script 之前消耗的执行/等待预算远大于 bootloader
   stage-1 watchdog 窗口；
2. 这段时间有真实 SSI/cache/DPORT 活动，不是单纯 CPU idle；
3. display completion 不是当前 first failure；原厂 startup UI 尚未开始；
4. 必须找到能改变 guest/controller 工作量的模型缺陷或取得匹配源码，
   不能通过延长 WDT、关闭 WDT、缩 VFS、替换 startup UI 或 accelerator
   覆盖来声称修复。

## 复现

```bash
M5SW_UART_TRACE=1 PYTHONPATH=platform/tools \
  .work/issue-review-venv/bin/python3.12 \
  tests/firmware/core2_handoff_trace/run_pause_sweep.py \
  --image .work/runtime03-original-vfs-probe/image.bin \
  --expected-image-sha256 4d2d648bd8707a1789d540366015a1b90dc816b66a04163048626ea29e333ed4 \
  --qemu .work/M5StopWatch-QEMU/build/qemu/build/qemu-system-xtensa \
  --runtime qemu-wifi --icount-shift 5 --pause-seconds 80 \
  --timeout-seconds 360 --disable-wdt --out-dir <new-output-dir>
```

不要复用输出目录；原始串口、frame、ZIP 和完整 trace 留在 ignored
`.work/`。
