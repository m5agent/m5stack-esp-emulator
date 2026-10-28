# 2026-10-29：Core2 legacy pre-boot phase profile

## 结论

当前公开 `UIFlow_Core2 v1.15.4` 镜像在 WDT-off 的 80 秒虚拟时间窗口中
仍然持续工作。新增的官方 phase profile 把同一运行的 UART 时间轴、
50 ms PC 采样、SSI transaction 和 cache/cross-core 计数绑定到一起：

- MicroPython banner 完成于 `2.7724 s`；
- `BOARD NAME` 于 `54.9924 s`；
- `APIKEY` 于 `54.9971 s`；
- legacy `boot.py` start/done 于 `77.8622/78.3712 s`。

同一镜像 normal-WDT 仍在 `7.2536 s` stage-0、`17.2536 s` stage-1 reset，
TG1 在 reset 前持续 feed，`0` 次 timeout。因此当前阻断仍是正常的
pre-boot 工作超过 stage-1 deadline，而不是永久 deadlock。

PC 采样共 `1,599` 个 50 ms 样本。CPU0 约 `31.0%` 位于
`0x4026306e` idle/waiti 形态，约 `60.4%` 位于
`0x40087980..8e` 的 BIN-bound Flash/cache handoff 簇。CPU1 主要位于
中断分发和 SSI 驱动地址簇；没有 matching ELF/MAP，因此不把这些地址
命名成未经证明的函数。

## SSI 与调度边界

80 秒状态点：

| Counter | Value |
| --- | ---: |
| SSI transactions | `103,058` |
| SSI RX bytes | `3,181,984` |
| 最后一次 SSI command | `0xBB` |
| 最后一次 SSI payload | `64` bytes |
| DPORT cache-sync calls | `215,836` |
| Changed pages | `5,911` |
| Cross-core writes | `428,205` |

sampled SSI stream 中大量 transaction 为 read-class command，接收长度
通常为 64 bytes。当前结果把下一问题缩小到：

1. guest 为什么在启动期执行约十万次小块 Flash read；
2. 为什么每次 read completion 到下一次 host controller command 之间存在
   明显虚拟时间间隔；
3. 该间隔来自 guest 指令路径、SPI interrupt delivery，还是缺少更大的
   controller/DMA transaction。

三组“立即切核”负控均已执行并丢弃：

| Control | QEMU SHA256 | 结果 |
| --- | --- | --- |
| 所有 high-priority memw/retw 立即退出 TB | `7203bfe1…` | 30 秒墙钟只到约 `2.35 s` 虚拟时间，连 MicroPython banner 都未到 |
| 仅 CPU1 handler 立即退出一次 | `bd94be5d…` | TG1 虽继续 feed，但 stage-0 后仍未见 BOARD/APIKEY |
| cross-core 写时退出当前 TB | `dc4ad087…` | 虚拟时间推进进一步变慢 |
| SPI `TRANS_DONE` 时退出当前 TB | `fb9c482a…` | 虚拟时间推进变慢，未改善启动预算 |

这些修改没有进入主线，也不能作为产品修复。

## 工具修复

`run_pause_sweep.py` 新增显式：

- `--pc-sample-ns`：设置并记录 PC sampling interval；
- `--uart-trace`：打开 UART TX virtual timestamp；
- `phase_profile`：保存 PC 热点、sample window、sampled SSI read/read64 计数。

此前 runner 虽会解析 UART TX 行，但正式调用没有启用
`M5SW_UART_TRACE`，且即使外部设置 PC sampling，evidence 仍写成
`NOT RUN`。该 instrumentation 缺口已修复并加入合同测试。

## 身份

| 项目 | 值 |
| --- | --- |
| Validation | `virtual-device validation` |
| Physical hardware | `NOT RUN` |
| Firmware normalized SHA256 | `4d2d648bd8707a1789d540366015a1b90dc816b66a04163048626ea29e333ed4` |
| QEMU SHA256 | `fccfa931c032f8cae6b90e97ba5f98b1770fbf6856446c4db5f7950241e1fe90` |
| Runtime | `qemu-wifi`, `icount shift=5` |
| WDT-off QEMU stderr SHA256 | `8e12e54a4a4e74cef831720c9ee305f549a6547321e3891ed9a1939fc84de780` |
| WDT-off serial SHA256 | `923380826ceb9be6107e6437dcb690be6a67bdccaade80164ab6537b7f458d0d` |

## 复现

```bash
PYTHONPATH=.work/py python3 \
  tests/firmware/core2_handoff_trace/run_pause_sweep.py \
  --image .work/runtime03-original-vfs-probe/image.bin \
  --expected-image-sha256 4d2d648bd8707a1789d540366015a1b90dc816b66a04163048626ea29e333ed4 \
  --pause-seconds 80 --disable-wdt --runtime qemu-wifi \
  --icount-shift 5 --pc-sample-ns 50000000 --uart-trace \
  --timeout-seconds 300 \
  --out-dir /tmp/core2-preboot-phase-profile
```

## 边界

- 只证明当前固件、当前 QEMU 和 WDT-off 诊断控制下的虚拟设备时间轴；
- PC sampling 会改变宿主调度，不能单独当作 normal-WDT 产品结果；
- 没有 matching ELF/MAP，地址只描述 BIN 控制流，不是函数符号；
- 没有证明物理 Flash、cache、PSRAM、RF、电气或真机时序；
- `RUNTIME-03` 仍为 `OPEN`。
