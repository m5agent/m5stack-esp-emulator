# Core2 native HCI backend design

日期：`2026-10-24`

本文定义 `CORE2-01` 的目标结构、当前 GDB 诊断桥的失效边界，以及可执行的
QEMU 内部实现路线。当前能力结论仍以
[项目当前状态](project-status.md) 为准，未完成项只在
[项目 Backlog](project-backlog.md) 跟踪。

## 结论先行

现有 `API_vhci_host_send_packet → GDB Python → Bumble` 路径可以作为调试夹具，
但不能作为稳定产品后端。同 commit 的 Device Service repeated lease 目前
`1/2`：失败时 C2H callback 在 H2C sender context 返回 `2559356`，随后 GDB
进入 target-running，guest `InstrFetchProhibited` 并重启。

`CORE2-01` 应采用 QEMU 进程内的 HCI relay，并满足：

- H2C 来自 guest 真实 `API_vhci_host_send_packet` 数据面；
- C2H 由 QEMU/异步主循环在确定的 vCPU 安全点提交；
- host socket/chardev worker 不直接修改 vCPU 寄存器或调用 guest callback；
- 每个 packet 有 queued/submitted/completed 状态和失败分类；
- 同一 stock 固件、同一 ELF、同一 Bumble peer 通过 repeated lease；
- 不使用 GDB Python callback、固定 HCI 脚本事件或 Python 伪造寄存器。

## 为什么 GDB 桥不稳定

当前 bridge 在 QEMU gdbstub 内做三件不同层次的事情：

1. 从 ELF 固定 `API_vhci_host_send_packet`、`vhci_env_p` 和 idle 地址；
2. 在 H2C breakpoint 中用 `gdb.execute("return")` 合成 controller 调用返回；
3. 在 Python 中调用 firmware `notify_host_recv` 或 `notify_host_send_available`。

第 1 项已经稳定并有测试；第 2、3 项依赖具体 vCPU thread、Xtensa register
window 和 gdbstub 的 stop/continue 状态。实验表明：

- 从 H2C sender context 调用 host callback 会间歇返回错误 status；
- 固定切到 CPU0 可提高成功数，但在另一 CPU 的 sender callback 会破坏上下文；
- 只在 CPU1 idle 注入时 guest 不响应；
- 改用常驻 CPU0 idle 会改善部分测试，但统一测试仍出现崩溃或延迟；
- 单 CPU `-smp 1` 不能启动该 Core2 镜像；
- `set scheduler-locking on` 会触发 Espressif GDB 内部断言。

因此继续调整 callback 调用的时序不能证明生产稳定性。

## 可复用结构

公开 `0x504B0304/bes-qemu @ e57911d5` 的 Bluetooth bridge 提供了结构参考：

- `qemu/bridges/bluetooth/miband_hci_bridge.c`：host H4/socket transport、
  RX packet parser、TX backpressure；
- `qemu/bridges/bluetooth/miband_hci_backend.c`：backend 选择；
- `qemu/soc/best1503/controllers/bt/miband_bt.c`：controller model；
- worker 读取 external HCI，主循环用 `async_run_on_cpu` 把提交放到 vCPU
  安全点，不在 fd callback 中操作 guest CPU。

该实现面向 BES SoC 和其 BT mailbox，不能直接复制到 classic ESP32；可复用
的是“host transport worker + QEMU device queue + vCPU-safe commit”边界。

## 目标数据面

```text
guest NimBLE
  -> API_vhci_host_send_packet
  -> ESP32 VHCI shared-memory/register path
  -> QEMU esp32-native-hci device
       -> H4 parser / queue
       -> Bumble HCI socket
  <- Bumble C2H
  <- QEMU main-loop worker + async vCPU commit
  <- ESP32 VHCI controller-to-host interrupt/queue
  <- firmware notify_host_recv
  -> guest NimBLE
```

关键要求是让最后的 C2H 交给 guest 自己的 VHCI controller-to-host 路径执行；
QEMU 不应从任意 host 线程直接调用 `notify_host_recv`。

## 实施阶段

### HCI-0：静态边界与测试夹具

- 固化 `vhci_env_p` 结构偏移、H2C buffer、C2H callback、controller
  interrupt 和 send-available 的权威来源；
- 对同一 ELF 记录符号、section、反汇编和 runtime register trace；
- 增加 packet state machine 和 queue overflow/peer disconnect 单测；
- 不改变现有 GDB diagnostic runner。

验收：结构字段、queue 状态和错误分类有单测；没有 guest PASS 声明。

### HCI-1：QEMU chardev/socket transport

状态：`transport-only PASS`。补丁与证据：

- `patches/qemu-core2-native-hci/0001-esp32-native-hci-transport.patch`
- `tests/uiflow2/core2_native_hci/evidence-2026-10-24-transport-pass.json`

已实现：

- 新增 QEMU 设备或 `hw/misc` 模块，提供 `chardev`-backed H4 transport；
- worker 只做 socket read/write、H4 packetization 和 bounded queue；
- 通过 QOM 暴露 counters、last error、peer connected、RX/TX packet counts；
- QEMU shutdown 必须关闭 fd、worker 和 timer，无残留线程/进程。

验收结果：targeted `m5core2` paused-QEMU test 覆盖分片 event/ACL、
`32` packet queue 上限、overflow drop、peer open/close、counters 和 clean
shutdown。该 PASS 只覆盖 host transport，不覆盖 guest VHCI。

### HCI-2：H2C guest→QEMU

- 在 classic ESP32 VHCI 数据面捕获完整 H2C packet；
- 不执行 GDB `return`，不调用 host callback；
- 将 packet 入队到 transport 并保留 guest-visible accepted/completed 状态；
- 按真实 ID 记录 H2C opcode/ACL header，不记录敏感载荷。

验收：stock firmware Reset、LE init、advertising enable 命令按 H4 完整到达
Bumble。

### HCI-3：C2H QEMU→guest

- Bumble event/ACL 由 QEMU 主循环接收；
- 用 `async_run_on_cpu` 或设备 IRQ 在安全点提交；
- 由 firmware 自己的 VHCI controller-to-host 路径调用 `notify_host_recv`；
- 保持 packet order、flow control 和 send-available 语义；
- 失败时显式中止 lease，不丢包后继续伪装成功。

验收：external Bumble scan/connect/NUS subscribe/write/notify；guest ACK
回读。

### HCI-4：稳定性门禁

- 同一固件 SHA、ELF SHA、QEMU build 和 profile 连续至少 `5/5`；
- 每个 lease 都通过 Device Service `/api/v1`；
- 同时检查 board/frame/QOM/audio/WiFi/DNS/public HTTP/BLE；
- 失败必须分类为 queue、transport、vCPU commit、guest reset 或 peer；
- 再做长稳、coexistence 和真机同路径。

## 工作量

在已有 Core2 QEMU、HCI packet fixture 和 Bumble peer 的前提下：

- HCI-0 到 HCI-2 的 host transport、queue 和 H2C 抓取：约 `4–7` 天；
- HCI-3 的 C2H 安全提交和 ESP32 VHCI controller-to-host 对齐：约
  `4–8` 天；
- HCI-4 的 repeated lease、故障注入和长稳：约 `3–5` 天；
- 若必须实现 bit-exact controller/baseband、PHY 与 coex，另计
  `4–8` 周，不能包含在前 2–3 周内。

若 classic ESP32 VHCI shared-memory 的 controller-to-host queue 无法从现有
firmware/ELF 和 QEMU 状态建立可验证语义，HCI-3 会升级为架构 blocker，
届时停止 GDB hack，不以更多 retry 掩盖。

## 明确不接受

- 修改固件为 HCI-UART offload 后冒充 stock internal-controller；
- 在 Python/GDB 中伪造 C2H event 或写死 guest marker；
- 把 WiFi/公网 PASS 拼接成 BLE PASS；
- 自动 retry 后只报告成功次数；
- 把 QEMU virtual HCI 描述为 RF、controller 固件或真机等价。
