# Core2 native HCI backend design

日期：`2026-10-24`

本文定义 `CORE2-01` 的目标结构、当前 GDB 诊断桥的失效边界，以及可执行的
QEMU 内部实现路线。当前能力结论仍以
[项目当前状态](project-status.md) 为准，未完成项只在
[项目 Backlog](project-backlog.md) 跟踪。

## 当前阶段快照

| 阶段 | 状态 | 已提交产物 | 结论 |
| --- | --- | --- | --- |
| `HCI-1` host transport | `PASS` | `patches/qemu-core2-native-hci/0001-esp32-native-hci-transport.patch` | H4 framing、bounded queue、overflow、peer lifecycle、QOM counters 和 clean shutdown 已通过 targeted test |
| `HCI-2` H2C | `PARTIAL` | 同一补丁的 `env-pointer-address` poller；`test_guest_h2c.py` | 不启动 GDB 已捕获真实 stock HCI Reset `01030c00`；完整命令序列需要 C2H 才能继续 |
| `HCI-3a` C2H callback | `DIAGNOSTIC PASS` | `c2h-allocator-address`、注册 callback 调用、send-available 和 QOM counters | Reset Complete 已交付 guest 的 `notify_host_recv`，callback status 为 0，guest 随后发出 Read Local Version；连续 `5/5`。这只证明窄路径 ABI，不是可扩展产品后端 |
| `HCI-3b` complete sequence | `OPEN` / diagnostic `FAIL` | `run_full.py`、`evidence-2026-10-24-hci3b-diagnostic.json` | 可发现、连接并完成首个 ATT request/response；第二个 ATT request 后 guest 报 `HCI process ack returned 12` 并 Reset，不能作为 PASS |
| `HCI-4` stability | `OPEN` | 无门禁 | 还没有无 GDB 的 Device Service 连续 `5/5` 完整 GATT 证据 |

`HCI-3a` 已证明 callback ABI、guest buffer、window/return 和
send-available 的窄路径；但 `HCI-3b` 的后续审计证明：在任意 safe point
直接注入 callback、以及 nested 调用真实 `r_eif_send → vhci_send`，都不是
有效的 controller-to-host 交付上下文。下一实现必须提供 guest-visible
IRQ/queue 或 in-process controller transaction。只有完整 sequence 稳定后
才可进入 `HCI-4`。不能把单次 connect/首包 callback 写成“原生蓝牙后端已完成”。

## 结论先行

现有 `API_vhci_host_send_packet → GDB Python → Bumble` 路径可以作为调试夹具，
但不能作为稳定产品后端。同 commit 的 Device Service repeated lease 目前
`1/2`：失败时 C2H callback 在 H2C sender context 返回 `2559356`，随后 GDB
进入 target-running，guest `InstrFetchProhibited` 并重启。

`CORE2-01` 应采用 QEMU 进程内的 HCI relay，并满足：

- H2C 来自 guest 真实 `API_vhci_host_send_packet` 数据面；
- C2H 先进入 QEMU controller-to-host 数据/状态队列，再向 guest 发出与真实
  controller 等价的 IRQ；
- guest firmware ISR 自己消费队列、调用 `notify_host_recv` 并更新
  VHCI flow-control/ACK 状态；
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

状态：`PARTIAL`（首个 packet PASS，完整 sequence 未完成）。已从真实 stock
Core2 VHCI shared memory 捕获首个 H4 command `01030c00`（HCI Reset），
不启动 GDB，QOM `h2c-packets=1`，dummy peer 收到相同 4 bytes。证据：
`tests/uiflow2/core2_native_hci/evidence-2026-10-24-guest-h2c.json`。

- 在 classic ESP32 VHCI 数据面捕获完整 H2C packet；
- 不执行 GDB `return`，不调用 host callback；
- 将 packet 入队到 transport 并保留 guest-visible accepted/completed 状态；
- 按真实 ID 记录 H2C opcode/ACL header，不记录敏感载荷。

验收：stock firmware Reset、LE init、advertising enable 命令按 H4 完整到达
Bumble。Reset 已通过；`HCI-3a` 现在能交付第一个 C2H 响应并推进一条后续
命令，但完整 Bumble sequence 仍归入 `HCI-3b`。

### HCI-3：C2H QEMU→guest

状态：`HCI-3a DIAGNOSTIC PASS / HCI-3b OPEN`。

- Bumble event/ACL 由 QEMU 主循环接收；
- 用 `async_run_on_cpu` 或设备 IRQ 在安全点提交；
- 由 firmware 自己的 VHCI controller-to-host 路径调用 `notify_host_recv`；
- 保持 packet order、flow control 和 send-available 语义；
- 失败时显式中止 lease，不丢包后继续伪装成功。

验收：external Bumble scan/connect/NUS subscribe/write/notify；guest ACK
回读。

#### HCI-3a 诊断路径已通过

- 从 `vhci_env_p + 0x4e4` 动态读取注册 callback table；
- 用真实 guest `malloc` 分配 C2H scratch，避免覆盖 BT RAM；
- 按 Xtensa `call8` ABI 使用 caller `a10/a11` 传参数，返回地址放在 `a8`；
- 在 CPU safe point 运行 `notify_host_recv`，恢复 PC、PS、window base/start、
  physical registers 和 icount；
- callback 返回后调用 send-available；
- dummy controller 返回 Reset Complete 后，guest 从 `01030c00` 推进到
  `01011000`。

证据：
`tests/uiflow2/core2_native_hci/evidence-2026-10-24-c2h-delivery.json`；
同一固件/QEMU 的 targeted run 连续 `5/5` PASS：
`tests/uiflow2/core2_native_hci/evidence-2026-10-24-c2h-delivery-5x.json`。

这仍不等于完整 BLE：探索性 Bumble 运行出现过完整初始化、广播和连接，
但后续 ATT 请求不能稳定完成，因此不把 scan/connect/GATT 作为门禁结果。
后续审计也证明该 callback 注入方式不适合作为正式 controller-to-host
交付机制，不能据此进入 `HCI-4`。

#### 已排除的假设

本地实验把 C2H 从 chardev callback 送进 CPU0，并尝试直接调用 guest
`vhci_send`。`cpu_exec_step_atomic` 能让该函数返回，但 guest 随后报告
`HCI wait for ack returned 19` 和 `OSError: ETIMEDOUT`。这说明
`vhci_send` 不是简单的 `(H4 buffer, length)` 注入入口；它依赖 controller
内部事件/队列结构。该实验没有固化为源码提交，不应继续猜 `a2/a3/a4/a5`
参数或靠 retry 让它“偶尔返回值”。

#### HCI-3b 下一项

`run_full.py` 已建立真实 Bumble controller/peer 的完整门禁。当前实测：

1. controller、广播、scan、connect 和第一个 ATT request/response PASS；
2. 第二个 ATT request 已到达 QEMU，但 guest 随后
   `HCI process ack returned 12`，发送 HCI Reset，Bumble ATT discovery
   timeout；
3. callback 每次返回 status 0，H4 parser 没有 RX 错位；
4. 临时诊断确认 `malformed-packets` 是 VHCI length 字段的非最终写入，
   不是 C2H/H4 数据损坏；
5. 仅固定 CPU0 idle、任意 CPU0 safe point、扩大无丢弃队列三种实验均未解决，
   已从运行时恢复。

后续 safe-point audit 又保存/恢复了 `SAR`、`LITBASE`、循环寄存器、
`M0-M3`、`THREADPTR`、`ATOMCTL` 等 common caller-saved 特殊寄存器，再在
任意 CPU0 safe point 注入 callback；guest 仍在 BLE 初始化阶段两次
`ack returned 12`，随后 `LoadProhibited` 崩溃。该实验也已回退。

controller-entry audit 进一步确认 `r_eif_send → vhci_send` 是 firmware
真实 C2H 路径，负责调用 registered receive callback 并更新 VHCI flow。
但把该入口当作 nested guest RPC 调用会触发
`Cache disabled but cached memory region accessed`，callback 不能正常返回。
因此 controller 交付必须是设备/IRQ 事件，或由 in-process controller
执行；不能再从 QEMU device callback 同步“远程调用” guest 内部函数。

已证伪并回退的路线：

| 路线 | 结果 | 证据 |
| --- | --- | --- |
| 固定 CPU0 idle / 任意 CPU0 safe point 直接调用 callback | BLE 初始化 ack 12；补寄存器后在 `LoadProhibited` 崩溃 | `evidence-2026-10-24-hci3b-safe-point-audit.json` |
| nested 调用真实 `r_eif_send → vhci_send` | `Cache disabled but cached memory region accessed`，callback 未正常返回 | `evidence-2026-10-24-hci3b-controller-entry-audit.json` |
| 扩大 RX 队列、移除 drop | 仍停在第二个 ATT request，不能修复 transaction | `evidence-2026-10-24-hci3b-diagnostic.json` |

两次审计实验均未保留；QEMU 补丁 reverse-check 为 `PASS`。

#### API boundary 审计

后续对照 GDB 5/5 路径与 native-HCI 失败路径，确认两者在 H2C 边界上并不同：

- GDB 桥在 `API_vhci_host_send_packet` 入口截获真实参数并直接返回，固件内部
  controller 不参与 HCI transaction；
- native-HCI 仅监听 VHCI shared-memory 长度写入，固件内部 controller 与
  Bumble 同时推进状态，第二个 ATT request 后发生 ACK 12/Reset；
- 在 Xtensa `entry` 指令之前，`WINDOW_BASE` 仍在 caller；GDB `return`
  把 PC 放回 wrapper call site 而不旋转窗口。QEMU hook 旋转窗口会造成
  cache-disabled panic。

实验性 QEMU CPU hook 使用正确的 pre-entry 返回语义后，完成了广播、连接、
NUS service discovery 和 CCCD subscription，H2C parser error/drop 均为 0，
外部 peer 也发出了 NUS write；但最后一个 guest write/notify callback 事务
未完成。改变 nested callback step budget 只移动失败点，没有闭环。

证据：
`tests/uiflow2/core2_native_hci/evidence-2026-10-24-hci3b-api-boundary-audit.json`。
实验代码未保留，`HCI-3b` 仍为 `FAIL`，不能把这次 partial 结果写成蓝牙后端完成。

下一步应实现与真实 controller-to-host 通知/事务等价的生命周期，而不是继续
调整固定 sleep、CPU pinning、寄存器补丁或 nested guest RPC：

- 在 `API_vhci_host_send_packet` 边界建立显式 transaction，避免内部 controller
  和外部 controller 同时拥有同一 packet；
- 增加 guest 可见的 controller-to-host queue/status 寄存器并 raise IRQ；
- 在 H2C send 与对应 C2H response 之间保持可验证的 transaction；
- 让 guest firmware 自己的 ISR/worker 在有效 cache 和 task 上下文中消费；
- 明确 FreeRTOS task wake/ACK 与 vCPU resume 的关系；
- 每一步都要求 Bumble ATT/GATT 前进，失败不 retry。

完整 sequence 通过后再接 NUS subscribe/write/notify，并进入 `HCI-4`
repeated lease。

### HCI-4：稳定性门禁

- 同一固件 SHA、ELF SHA、QEMU build 和 profile 连续至少 `5/5`；
- 每个 lease 都通过 Device Service `/api/v1`；
- 同时检查 board/frame/QOM/audio/WiFi/DNS/public HTTP/BLE；
- 失败必须分类为 queue、transport、vCPU commit、guest reset 或 peer；
- 再做长稳、coexistence 和真机同路径。

## 剩余工作量

下面是当前阶段之后的重新估算，不包含已经完成的 HCI-1、HCI-2 和
HCI-3a 窄路径：

- `HCI-3b` C2H queue/status/IRQ 语义审计和 spike：约 `1–2` 天；如果固件
  和 ELF 能给出可验证字段，再进入实现；
- `HCI-3b` guest-visible queue/IRQ 或 in-process controller transaction：
  约 `3–6` 天；
- `HCI-4` repeated lease、故障注入和长稳：约 `2–4` 天；
- 若必须实现 bit-exact controller/baseband、PHY 与 coex，另计 `4–8` 周，
  不能包含在 HCI-3b/HCI-4 的估算内。

若 classic ESP32 VHCI shared-memory 的 controller-to-host queue 无法从现有
firmware/ELF 和 QEMU 状态建立可验证语义，HCI-3b 会升级为架构 blocker，
届时停止 GDB hack，不以更多 retry 掩盖。

## 明确不接受

- 修改固件为 HCI-UART offload 后冒充 stock internal-controller；
- 在 Python/GDB 中伪造 C2H event 或写死 guest marker；
- 把 WiFi/公网 PASS 拼接成 BLE PASS；
- 自动 retry 后只报告成功次数；
- 把 QEMU virtual HCI 描述为 RF、controller 固件或真机等价。
