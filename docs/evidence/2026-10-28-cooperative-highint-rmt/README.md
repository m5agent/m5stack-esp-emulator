# 2026-10-28：Core2 高优先级 IRQ 协作调度、经典 RMT 与三设备回归

## 范围

本页把两类结果分开记录：

- Core2 legacy `UIFlow_Core2 v1.15.4` 的 Xtensa high-priority IRQ / DPORT
  handoff 与经典 ESP32 RMT 诊断；
- StopWatch、StickS3、Core2 当前 UIFlow2 `v2.5.3` 在最终 runtime 上的并发
  接口与设备级回归。

全部结果是 **virtual-device validation**。物理硬件、RF、电气、声学和光学测量
均为 `NOT RUN`。

最终 QEMU 为 `2026673273b5bced2c2696ac4850a48f5ea47d8e9c80d6ceb2cf15f68c36d29f`。
legacy 固件 normalized Flash SHA256 为
`152127c808b9212e3a5b55dd9e0a2d24e71b902e225452b67db381c76caba1cc`。

## Xtensa high-priority IRQ 协作调度

经典 ESP32 的 DPORT flash/cache handoff 用 peer CPU 的 level-4 中断和共享 SRAM
start/end flags 协调。单线程 TCG 的大 icount slice 可以让发送端在接收端观察
上一组 flags 前清标志并开始下一轮，形成 CPU0 等 `start`、CPU1 等 `end` 的
调度诱导死锁。

`0065-xtensa-high-priority-irq-cooperative-yield.patch` 记录每个 CPU 当前是否
处于 level-4/5 handler，并只在两个协议顺序点让出 TCG slice：

- handler 用 `memw` 发布 start flag 后；
- sender 经 `retw` 返回 end 路径时。

level-5 handler 返回 level-4 时保留 active；离开 level 4 的 `rfi/rfe` 和
CPU reset 才清除。guest 指令、virtual time 与 interrupt level 均未修改；
状态机只在 TCG icount 启用时工作，非 icount accelerator 不会被强制让出，
WDT、中断和协议 flag 也没有绕过。五轮独立首启动在
`5.000000002-5.000000031 s` 到达相同 early-state 边界，`5/5 PASS`；两核 PC
不再固定停在旧 deadlock 地址。

该修复关闭 scheduler-induced handoff deadlock，不关闭 legacy firmware 的
watchdog、display completion 或应用启动。

## 经典 ESP32 RMT

`0066-esp32-classic-rmt-legacy.patch` 替换此前未实现的
`0x3ff56000..0x3ff56fff` legacy RMT region，提供：

- 8 个 channel、RMT 寄存器与 2 KiB RMTMEM；
- `conf0.mem_size` 读回、memory-mode TX start；
- TX threshold refill、per-channel `TX_END` 和 INTMATRIX source 47；
- 有界 symbol capture，默认关闭。

修复前，legacy Neopixel 初始化把 `conf0.mem_size` 读成 0，随后报
`RMT translator buffer create fail` 和 `OSError: Error initializing Neopixel
interface`。修复后，同一固件越过该异常并打印
`BOARD NAME: M5STACK-CORE2` / `APIKEY`；debug trace 观察到四次 channel 7 TX，
每次 49 symbols。最终 runtime 的 68 秒 WDT-off 状态点也再次到达 APIKEY。

只证明 legacy IDF RMT 初始化/内存 TX 数据面，不证明 GPIO waveform、LED 光学、
电气时序或 RMT 全生命周期。

## Legacy late frame

最终 runtime 在 `68.000000000 s` exact-time 状态点为：

- CPU0 `0x40087984`，CPU1 `0x40095b31`；
- Serial 552 bytes，已到 `APIKEY`；
- 320x240 PNG 为 302 bytes，`0 nonblack pixels`，SHA256
  `57580743a08a3f4ebdf57240cbcc997002ef63b7234531f946127f1495973f43`。

截图在 exact-time register/state snapshot 后短暂恢复 QEMU、立即执行 QMP
`screendump`；它不是与 CPU state 原子一致的硬件采样。结果证明该时刻仍是
黑帧，不能把 RMT 初始化通过写成 legacy 应用 PASS。normal-WDT 的首 reset、
display completion、setup/REPL 和非空应用帧仍为 `OPEN`。

最终 runtime 的 normal-WDT 20 秒 control 仍在
`7.249439902 s` 进入 TG0 stage-0 timeout，在
`17.249439902 s` 进入 stage-1 timeout，并于
`17.249530334 s` 首次重启；串口明确报告 `TG0WDT_SYS_RESET` 与两核
`PC=0x0`。因此 `0065/0066` 修复的是两个独立、可重放的模型缺口，不是
watchdog/应用启动的完整修复。

## 三设备 UIFlow2 并发回归

三台使用同一个最终 QEMU 和独立可见 Device Service session；所有 raw
firmware、serial、frame 与 evidence ZIP 留在 ignored `.work/`。

| 检查 | StopWatch | StickS3 | Core2 |
| --- | ---: | ---: | ---: |
| System runtime | `50 PASS + 1 STATE_PASS` | `50 PASS + 1 STATE_PASS` | `50 PASS + 1 STATE_PASS` |
| Shared corrections | `7/7` | `7/7` | `7/7` |
| Device group | `6/6` | `5/5` | `6/6` |

17 个设备组 case 全部首轮 PASS、`retry_used=false`：

- StopWatch：peripherals、vibration、audio、mic、M5IOE1、M5PM1；
- StickS3：peripherals、audio、mic、IR TX、IR RX；
- Core2：peripherals、audio、mic、power monitor、IMU、AXP192。

Shared corrections 覆盖 BLE 16/32-bit UUID decode 和 Modbus RTU
request/response/error bytes。System runtime 的 `STATE_PASS` 是各板的显式
`os.dupterm` 边界；Core2 的 native-UART0 路径在该探针中报告 supported，
但本页不把短探针扩展成完整 console reattach。

## 回归检查

- `test_xtensa_high_priority_irq_cooperative.py`：`2/2 PASS`，包含实际 C
  round-trip；
- `test_esp32_classic_rmt_patch.py`：`3/3 PASS`；
- `test_core2_handoff_state_sweep.py`：`2/2 PASS`；
- `0065`、`0066` 在 retained QEMU tree 的 reverse apply check 均 PASS；
- `git diff --check` PASS。

复现入口：

```bash
PYTHONPATH=platform/tools .work/issue-review-venv/bin/python \
  -m unittest discover -s platform/tests \
  -p 'test_xtensa_high_priority_irq_cooperative.py'

PYTHONPATH=platform/tools .work/issue-review-venv/bin/python \
  -m unittest discover -s platform/tests \
  -p 'test_esp32_classic_rmt_patch.py'

PYTHONPATH=.work/py python3 tests/uiflow2/run_peripheral_matrix.py \
  --device core2 --out-dir /tmp/m5-core2-device-group
```

机器可读摘要见 [`summary.json`](summary.json)。
