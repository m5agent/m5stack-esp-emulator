# 2026-10-29：Core2 legacy status/CAS 关联诊断

## 结论

新增 `0075-esp32-legacy-status-cas-correlation.patch`，把 legacy
UIFlow Core2 的 `RDSR(0x05)` 返回值、前序 `0xBB/64` 读、cache
计数变化、IRQ 状态，以及 `s32c1i` 的
PC/caller/lock/old-owner/holder-PC 聚合绑定到同一个显式 freeze。

本轮否定了“Flash WIP/busy 位让启动长期等待”的假设：

- 20 秒 WDT-off 对照共 12,093 次 `RDSR`；
- status `0x00` 有 4,278 次，`0x02` 有 7,815 次；
- 所有读数 bit0（WIP/BUSY）均为 `0`，`0x02` 只表示 WEL；
- 11,904 次 status read 紧跟 `0xBB/64`，但两者之间的 guest
  gap 合计 17.0741 秒，占该 20 秒窗口的 85.37%；
- status 调用全部位于 PS intlevel 0 且
  `interrupt_request=0`，不是被屏蔽中断卡住。

同窗口还观察到 6,288,123 次 `s32c1i`，其中 5,737,336 次是
当前 CPU 等待另一个 CPU 持有锁的真实跨核竞争。主要热点是
`0x3ffbf2cc`：5,482,913 次 CAS，253,241 次成功。没有发生
sparse table overflow，常态 old-owner 只出现
`0xB33FFFFF`（free）、`0x0000ABAB` 和 `0x0000CDCD`。

这不是一个已证明的 Xtensa `s32c1i` 语义错误。高竞争调用点集中在
`0x40094a5a` / `0x40095b2e`，持有者常处于
`0x400958xx-0x400961xx`、`0x40096dxx` 和
`0x40097axx-0x40097bxx` 的调度/list 代码形貌。当前缺少匹配的
legacy ELF/MAP，因此不把这些 BIN-bound 地址猜成精确函数名。

## WDT 对照

两次运行使用同一 firmware、最终 QEMU 和 runtime；唯一差异是
默认关闭的 `M5SW_XTENA_CONTENDED_CAS_YIELD=1`。

| 控制 | stage-0 | stage-1 | first reset | TG1 feeds | TG1 timeouts |
| --- | ---: | ---: | ---: | ---: | ---: |
| normal WDT | `7.248411234 s` | `17.248411265 s` | `17.248490561 s` | `14,996` | `0` |
| failed-CAS slice yield | `7.248929759 s` | `17.248929760 s` | `17.248930720 s` | `14,998` | `0` |

两者都分类为
`BOOTLOADER_TG0_STAGE1_RESET_WITH_TG1_LIVE`。TG1 最大 feed
间隔分别为 `3.926687 ms` 和 `3.926684 ms`，最后 feed 距 reset
分别为 `0.891968 ms` 和 `0.816736 ms`。失败 CAS 上主动退出
TCG slice 没有改变约 17.249 秒的正常 WDT 边界，因此该开关只保留
为负向控制，不是产品修复。

serial 仍只有 MicroPython banner、没有 REPL prompt；frame SHA256
仍为 `57580743a08a3f4ebdf57240cbcc997002ef63b7234531f946127f1495973f43`
的 302-byte black frame，不能记为应用启动成功。

## RDSR 与 cache 关联

| 指标 | 值 |
| --- | ---: |
| `RDSR` 总数 | `12,093` |
| status `0x00` | `4,278` |
| status `0x02` | `7,815` |
| bit0 WIP/BUSY | `0` |
| 前序 `0xBB/64` | `11,904` |
| status gap 总时间 | `17.074056543 s` / `20 s` |
| 最大 status gap | `1.923178656 s` |

两个 status read 之间 cache counters 的变化如下：

| Counter | 非零区间 | 总 delta | 单区间最大 |
| --- | ---: | ---: | ---: |
| cache sync calls | `11,954` | `55,316` | `120` |
| cache sync pages | `3` | `5,655` | `4,708` |
| cache state updates | `11,954` | `55,350` | `154` |
| cache invalidate calls | `3` | `84` | `70` |
| illegal reads | `0` | `0` | `0` |

cache sync/state update 在大多数 status 区间继续发生，但没有
illegal read，且 Flash status 的 busy 位始终为零。当前证据不能把
等待归给 m25p80 的 WIP 或 stateful SSI 返回值。

## CAS 与锁竞争

| 指标 | 值 |
| --- | ---: |
| `s32c1i` 总数 | `6,288,123` |
| CAS 成功 | `537,482` |
| CAS 返回 old 非 free | `5,750,641` |
| 真实跨核竞争 | `5,737,336` |
| `0x3ffbf2cc` CAS | `5,482,913` |
| `0x3ffbf2cc` 成功 | `253,241` |

最高调用点：

| CPU / caller A0 | CAS site | Lock | Failed CAS |
| --- | --- | --- | ---: |
| CPU0 `0x8009655c` | `0x40095b2e` | `0x3ffbf2cc` | `3,254,878` |
| CPU0 `0x80095833` | `0x40094a5a` | `0x3ffbf2cc` | `1,010,213` |
| CPU1 `0x80095833` | `0x40094a5a` | `0x3ffbf2cc` | `767,177` |
| CPU0 `0x80094e8d` | `0x40095b2e` | `0x3ffb7a58` | `442,274` |

最高 holder-PC 桶为 `0x40096100`、`0x40095b00`、`0x40097a00`
和 `0x40095900`。这些是 256-byte BIN-bound 桶，不是函数符号。
连续 PC 采样同时把 CPU0/Core1 的热点落在
`0x4009a146`（memcmp 形貌）及上述两个 `s32c1i` 循环，和 CAS
表相互印证。

## 身份与边界

| 项目 | 值 |
| --- | --- |
| Firmware | `UIFlow_Core2 v1.15.4` |
| Public source SHA256 | `18d77e28adfacf7e719a167bd0c3450b78357d13cb1d2f2a8b7bccc2248a909a` |
| Normalized flash SHA256 | `4d2d648bd8707a1789d540366015a1b90dc816b66a04163048626ea29e333ed4` |
| QEMU SHA256 | `d60e6fb0e24e025ff19a521b34debbb9c16d9e5e427d35c8d22596ad98de42fa` |
| `0075` patch SHA256 | `7be9f75c6d65250c80f30b4580569d7c7bc804d087f688f917f396104e35ca35` |
| 20 秒 WDT-off evidence SHA256 | `27c2c16d3989df90a9994b8dd0436e07adec91e9a396ac559f2e6360c9b579b3` |
| 20 秒 WDT-off stderr SHA256 | `0085ea92647b53dc391b0215835fe2cc4f8bb38859297be8dd54467144019a26` |
| Normal-WDT evidence SHA256 | `4320b4d5329cfa248f466e94c378ee003f0f327aebcf0ccc5e2d8017a8a90c2b` |
| Failed-CAS-yield evidence SHA256 | `6fc1e18856f4ac4943b4ae533c5a66b0e261c2deb200b18e1ceab8e142ca6734` |
| Hardware validation | `NOT RUN` |

全部为 virtual-device validation。没有 matching legacy ELF/MAP，
不把 PC 或 caller A0 冒充符号；也不声称物理 cache/PSRAM timing、
RF、电气、实时性能或真机行为。

`RUNTIME-03` 保持 `OPEN`。下一项工作应从调度/list 热点、tick/IRQ
频率和 `0x3ffbf2cc` 锁的持有区间继续缩小，而不是回转去修改
Flash status 返回值或关闭 WDT。

## 复现

```bash
PYTHONPATH=platform/tools:.work/py312 .work/py312/bin/python \
  tests/firmware/core2_handoff_trace/run_pause_sweep.py \
  --image .work/runtime03-original-vfs-probe/image.bin \
  --qemu .work/M5StopWatch-QEMU/build/qemu/build/qemu-system-xtensa \
  --pause-seconds 20 --disable-wdt --runtime qemu-wifi \
  --expected-image-sha256 4d2d648bd8707a1789d540366015a1b90dc816b66a04163048626ea29e333ed4 \
  --pc-sample-ns 5000000 --service-port 8911 \
  --out-dir /tmp/m5-core2-status-cas
```
