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
| `HCI-2` H2C | `PASS` | `env-pointer-address` poller；`test_guest_h2c.py`；`0003` API-boundary hook | 首个 `01030c00` 与完整 H2C 命令流均不依赖 GDB |
| `HCI-3a` C2H callback | `DIAGNOSTIC PASS` | `c2h-allocator-address`、注册 callback 调用、send-available 和 QOM counters | Reset Complete 已交付 guest 的 `notify_host_recv`，callback status 为 0，guest 随后发出 Read Local Version；连续 `5/5`。这只证明窄路径 ABI，不是可扩展产品后端 |
| `HCI-3b` HLI event | `PASS` | `0002-esp32-native-hci-hli-event.patch`、`test_hli_event.py` | guest 池分配真实 Reset Complete，经 HLI event 13 和 `ble_transport_to_hs_evt_impl` 交付；`01030c00 → 01011000` 连续 `5/5` |
| `HCI-3b` full transaction | `PASS` | `0003-esp32-native-hci-api-transaction.patch`、`0004-xtensa-ccount-tb-yield.patch`、`run_full.py --hli-c2h` | 无 GDB 完成 scan/connect/NUS discovery/subscribe/write/notify 和 Bumble ACK；合法 loader 为 15-byte probe / 17-byte ATT PDU，连续 `5/5` |
| `HCI-4` stability | `PASS` | `run_service_5x.py`、`evidence-2026-10-24-hci4-service-5x.json` | 规范 profile `core2-native-hci` 通过五个独立 `/api/v1` lease；每轮同时验证 frame、QOM、WiFi/公网、外部 NUS GATT、pcap 和 evidence ZIP，且 `gdb_bridge=false` |
| `CORE2-02` extended run | `PASS` | `0005-esp32-native-hci-guest-call-sregs.patch`、`evidence-2026-10-24-hci4-halted-gate-5x.json`、`evidence-2026-10-24-hci4-hold60-3x.json`、`evidence-2026-10-24-hci4-hold120-2x.json`、`evidence-2026-10-24-hci4-active-ble-hold120-2x.json` | caller-saved sregs 与 halted/idle gate 后，两批 `5×10s`、3 个 `60s`、2 个 `120s` 和 2 个 active-BLE `120s` hold 已通过，每轮 HLI health 零错误 |
| `CORE2-02` same-guest reconnect | `PASS` | `run_service_5x.py --ble-reconnect-cycles 20`、`0006-esp32-native-hci-observability.patch`、`evidence-2026-10-24-hci4-reconnect10-3x.json`、`evidence-2026-10-24-hci4-reconnect20-3x.json` | 修正 Bumble 对无响应 `0x0c35` 的非法 Command Status 后，先完成 3 个 lease 各 10 轮，再扩到各 20 轮；二十轮结果每 lease HLI 577/577、events 397、ACLs 180 清空，连接/L2CAP/GATT 池回到 `3/9/3` |
| `CORE2-02` 30-cycle extension | `PASS` | `run_service_5x.py --ble-reconnect-cycles 30 --attempts 3`、`evidence-2026-10-24-hci4-reconnect30-3x.json` | 3 个独立 lease 各 30 轮；每 lease HLI `857/857`、events 587、ACLs 270、HLI errors/queue/panic 为 0，连接池回到 `3/9/3` |

`HCI-3a` 已证明 callback ABI、guest buffer、window/return 和
send-available 的窄路径；`HCI-3b` 则改用 guest-visible HLI IRQ/queue，
并以 API-boundary H2C 隔离 firmware internal controller。旧 21-byte probe
生成 24-byte ATT PDU，超过默认 MTU 23，导致 L2CAP 拒绝；改用 15-byte
probe 后完整外部 NUS GATT 连续 `5/5`。`HCI-4` 随后让 Device Service
使用同一路径并通过五轮 independent lease；bit-exact controller 与物理
cache/PSRAM 仍是独立边界。`CORE2-02` 随后修复 nested guest-call 上下文：
恢复 caller-saved Xtensa 特殊寄存器，并只在 halted/idle vCPU 注入 HLI
allocator/callback；两次独立 5×10 秒 hold 运行合计 `10/10`，随后
3 个 60 秒 hold 运行 `3/3`，2 个 120 秒 hold 运行 `2/2`。随后 3 个
独立 lease 先各自通过十轮、后又各自通过二十轮 GATT reconnect；首次十轮运行还暴露并修复了
Device Service 将 HCI peer 等待硬截断为 30 秒的 session 误杀；历史
`ack 12` 已定位到外部
Bumble 对无响应 `0x0c35` 的非法回复。

## 结论先行

现有 `API_vhci_host_send_packet → GDB Python → Bumble` 路径只保留为
legacy/diagnostic profile，不作为稳定产品后端。同 commit 的 Device Service
repeated lease 为 `1/2`：失败时 C2H callback 在 H2C sender context 返回
`2559356`，随后 GDB 进入 target-running，guest
`InstrFetchProhibited` 并重启。新调用使用 `core2-native-hci`。

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

状态：`PASS`（由 `HCI-3b` 扩展验证完整 sequence）。已从真实 stock
Core2 VHCI shared memory 捕获首个 H4 command `01030c00`（HCI Reset），
不启动 GDB，QOM `h2c-packets=1`，dummy peer 收到相同 4 bytes。证据：
`tests/uiflow2/core2_native_hci/evidence-2026-10-24-guest-h2c.json`。

- 在 classic ESP32 VHCI 数据面捕获完整 H2C packet；
- 不执行 GDB `return`，不调用 host callback；
- 将 packet 入队到 transport 并保留 guest-visible accepted/completed 状态；
- 按真实 ID 记录 H2C opcode/ACL header，不记录敏感载荷。

验收：stock firmware Reset、LE init、advertising enable 命令按 H4 完整到达
Bumble。Reset、完整 init 和 NUS GATT 均已在 `HCI-3b` 中通过。

### HCI-3：C2H QEMU→guest

状态：`HCI-3a DIAGNOSTIC PASS / HCI-3b PASS / HCI-4 PASS`。

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
交付机制；后续门禁改用 HLI queue/IRQ，而不是扩展该回调注入路径。

#### 已排除的假设

本地实验把 C2H 从 chardev callback 送进 CPU0，并尝试直接调用 guest
`vhci_send`。`cpu_exec_step_atomic` 能让该函数返回，但 guest 随后报告
`HCI wait for ack returned 19` 和 `OSError: ETIMEDOUT`。这说明
`vhci_send` 不是简单的 `(H4 buffer, length)` 注入入口；它依赖 controller
内部事件/队列结构。该实验没有固化为源码提交，不应继续猜 `a2/a3/a4/a5`
参数或靠 retry 让它“偶尔返回值”。

#### HCI-3b 根因与通过证据

`run_full.py --hli-c2h` 现在使用 `0003` 的 API-boundary H2C hook、HLI
event/ACL 投递和 `0004` 的 CCOUNT TB-yield。trace 覆盖：

1. `ble_hs_hci_evt_acl_process`；
2. `ble_l2cap_rx` 和 ATT channel 分支；
3. `ble_att_svr_rx_write(_no_rsp)` 与 attribute lookup；
4. `mp_bluetooth_gatts_on_write`、Python notify 和 Bumble notification。

旧失败不是 controller ACK 或 H2C ownership：21-byte 测试载荷形成
24-byte ATT PDU，而 guest 使用默认 MTU 23，最终包在
`ble_l2cap_rx` 的 MTU 检查处被丢弃。trace 中
`l2cap-chan-found=9`、`mtu-reject=1`、`rxfn=8`、`att-rx=8`。

把默认 probe 改为 15-byte `M5_CORE2_PROBE` 后：

- ATT PDU 为 17 bytes；
- `l2cap-mtu-reject=0`、`l2cap-rxfn=9`、`att-rx=9`；
- `att-write-no-rsp=1`、`python-gatts-on-write=1`；
- Python notify 路径命中，Bumble 收到 `ACK:M5_CORE2_PROBE`；
- 同固件、ELF、QEMU build 连续 `5/5` PASS。

证据：
`tests/uiflow2/core2_native_hci/evidence-2026-10-24-hli-api-gatt-5x.json`。
post-pass peer teardown 仍可能产生 H2C `EIO`，runner 将其记录在
`post_sequence_teardown`，不参与已完成的 GATT transaction 判定。

历史 safe-point audit 与 controller-entry audit 仍然有效：

- 任意 CPU0 safe point 注入 callback 会造成 `LoadProhibited`；
- nested `r_eif_send → vhci_send` 会触发
  `Cache disabled but cached memory region accessed`。

因此正式路径继续使用 guest HLI IRQ/queue，而不从 QEMU device callback
同步调用 guest 内部函数。

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
该 partial 结果后来由 `0003`/`0004` patch 和合法 ATT 载荷闭环。
失败 evidence
`evidence-2026-10-24-hci3b-hli-api-notification-fail.json` 保留为
“24-byte PDU 超过默认 MTU”的负向证据，不再代表当前 `HCI-3b` 状态。

#### HLI queue delivery spike

最新诊断没有直接在任意 safe point 调用 host callback，而是写入固件自己的
`BTDM_CTRL_HLI` 队列路径：

```text
QEMU H4 C2H callback
  -> g_rw_schd_queue item
  -> guest btdm_queue_item_t -> hli_queue_t
  -> meta queue
  -> INTSET bit 29 / level-3 software IRQ
  -> hli_c_handler -> queue_isr_handler
  -> btdm_controller_task callback
```

对匹配的 stock UIFlow2 v2.5.3 镜像已确认：

- `CONFIG_BTDM_CTRL_HLI=1`；
- NimBLE 固定在 core 1，BT controller 固定在 core 0；
- `g_rw_schd_queue=0x3ffcb890`，`s_meta_queue_ptr=0x3ffc1158`；
- HLI software interrupt 为 29；
- `hli_queue_t` 的 element size、begin/end/bufend、downstream、flags 和
  inline buffer 偏移与 QEMU 写入布局一致。

实验向队列写入一个 8-byte controller work item，向 4-byte meta queue 写入
queue handle，再置 `INTSET[29]`。以 event 13 和 `ets_printf` 为 callback
时，guest 串口出现 `Fatal error in queue_signal: s_meta_queue full`，QOM
`hli-errors=0`，HLI/meta queue depth 都回到 0。这说明 guest HLI ISR 和
controller task 确实消费了 QEMU 投递项，验证了后续 C2H 的设备/IRQ 交付
seam。

最初的 event-13 marker 只证明 queue/IRQ seam，不能作为 HCI PASS。随后保留
的 `0002` patch 增加了真实 event buffer 路径：

- allocation 使用 guest `ble_transport_alloc_evt(0)`，buffer 最终由 NimBLE
  池归还；
- event bytes 写入时不包含 H4 type byte；
- event 13 的 controller work item 调用
  `ble_transport_to_hs_evt_impl`，不是打印 callback；
- HLI queue 使用真实 `hli_queue_t` 状态，修复了 `hli-consumed` 比较错误；
- VHCI length 的非最终写入单独计为 `h2c-incomplete-writes`，不再误报
  malformed packet。

`test_hli_event.py` 用真实 Bumble Reset Complete 驱动 stock guest。
`5/5` 次均观察到 `01030c00` 后 guest 发出 `01011000`，同时
`hli-posts=1`、`hli-consumed=1`、`hli-event-buffers=1`、
`hli-errors=0`、HLI/meta queue depth 归零。

证据：
`tests/uiflow2/core2_native_hci/evidence-2026-10-24-hli-event-5x.json`。
这关闭了“真实 controller event 能否从 HLI 安全进入 host”的阻塞。保留的
`0003` patch 进一步通过 `ble_transport_alloc_acl_from_ll`、
`os_mbuf_append` 和 `ble_transport_to_hs_acl_impl` 投递 ACL，并在
`API_vhci_host_send_packet` 边界隔离 firmware internal controller。

`HCI-3b` 的最终 5/5 约束：

- 使用合法默认 MTU 内的 probe，当前为 15-byte payload / 17-byte ATT PDU；
- `hli-c2h-events=39`、`hli-c2h-acls=9`、HLI/meta queue 清空；
- `l2cap-mtu-reject=0`，ATT write、Python handler 和 notify 路径命中；
- Bumble 收到 notification 并返回 `BLE_BUMBLE_PASS`；
- post-pass peer teardown 的 `EIO` 单独分类，不参与 transaction 门禁；
- 连续 `5/5`。

后续 `HCI-4` 已按这里的 no-GDB、HLI/API-boundary 路径通过；不再继续调
固定 sleep、CPU pinning、寄存器补丁或 nested guest RPC。

### HCI-4：五 lease 功能门禁

状态：`PASS`。证据：
`tests/uiflow2/core2_native_hci/evidence-2026-10-24-hci4-service-5x.json`。

- 同一固件 SHA、ELF SHA、QEMU build 和 profile 连续至少 `5/5`；
- 每个 lease 都通过 Device Service `/api/v1`；
- 每轮同时检查 320×240 frame、27 节点 QOM、WiFi DHCP/HTTP、公网
  DNS/HTTP、外部 NUS GATT、pcap 和 evidence ZIP；
- `gdb_bridge=false`，五个独立 lease/QEMU 进程，不使用自动 retry 掩盖失败；
- frame SHA256 五轮一致：`5bfcdf8f...db8408b`；
- 局限：仅 trusted-host，不是恶意固件沙箱；pcap 在 evidence ZIP 中保留，
  live `/network` 在停止前可显示 `CAPTURING`；
- 当前 H2C/HLI/trace hook 的指令偏移按已验证的 UIFlow2 v2.5.3 build
  固定；`elf_artifact_id` 必须是同一固件构建产出的匹配 ELF。其他 Core2
  build 仍为 `NOT RUN`，不能只凭“SoC 相同”复用该 profile；
- 该 PASS 只覆盖五个独立功能 lease；带 hold 的延长运行另见
  `CORE2-02`。仍不能据此声明长稳、coexistence、物理 cache/PSRAM 或真机。

重跑命令：

```bash
python3 tests/uiflow2/core2_native_hci/run_service_5x.py \
  --base-url http://127.0.0.1:8787 \
  --image /path/to/unified-core2.bin \
  --elf /path/to/matching/micropython.elf \
  --qemu .work/M5StopWatch-QEMU/build/qemu/build/qemu-system-xtensa \
  --attempts 5 \
  --hold-seconds 10 \
  --out-dir /tmp/m5-core2-native-hci-service-5x
```

`core2-native-vhci` 仍可显式用于历史对照，但文档和自动化不得把它描述为
稳定生产路径。

### CORE2-02：extended-run 修复与门禁

新增的 `--hold-seconds` 会让每个 lease 保留运行态并持续轮询 session，
用于把“启动后立刻截图”与“持续运行”区分开。历史失败记录包括：

- 一次 10 次请求、每轮 hold 10 秒的运行在 attempt 4 前 3 次 PASS，第 4 次
  在 READY 前出现 `InstrFetchProhibited`、`PC=0`；
- 另一轮单次 hold 1 秒的失败已经通过 READY、WiFi/公网和 BLE 连接，随后
  首轮 panic 为 `IllegalInstruction`，PC `0x40266960`，符号化为
  `semphr_give_wrapper`
  (`components/bt/controller/esp32/bt.c:677`)；重启后进入
  `InstrFetchProhibited`、`PC=0`、`EXCCAUSE=0x14` 的循环；
- Bumble peer 可以走到 connect，随后在 GATT discovery 或 notification
  阶段超时；这说明失败发生在 BLE 生命周期边界，而不是 WiFi/DNS/HTTP
  之前；
- 失败发生在 `hold_seconds` 生效之前的 READY/session 状态检查，不能把
  它解释为“等待时间过长”；
- runner 现在在失败时保留 serial/peer/pcap 以及 partial evidence，并在
  汇总 JSON 写入 aggregate `FAIL`；不得通过增加 retry 或删除 hold 检查
  把结果变绿。

证据：
`tests/uiflow2/core2_native_hci/evidence-2026-10-24-extended-run-fail.json`。

修复分两步：

1. `0005` 在每次 nested guest call 前后恢复
   `LBEG/LEND/LCOUNT/SAR/BR/LITBASE/SCOMPARE1/ACCLO/ACCHI/M0-M3/
   THREADPTR/ATOMCTL/CPENABLE`；
2. HLI 的 allocator/callback guest-call 只在目标 vCPU 已进入
   halted/idle 时执行；非 halted 状态由虚拟 timer 延后，避免从
   cache-disabled 的 WiFi/controller 中间上下文进入 guest 代码。

仅恢复 sregs 的中间构建通过 `4/5`，第 5 轮仍在 WiFi `vListInsert`
出现 Cache error。加入 halted/idle gate 后，同一固件/ELF/QEMU build
连续两批独立 `5×10s` hold 运行均通过，合计 `10/10`；每轮
`hli-posts=hli-consumed=47`、`hli-c2h-events=38`、
`hli-c2h-acls=9`、`hli-errors=0`、HLI/meta queue 深度为 0，frame
SHA256 一致。证据：
`tests/uiflow2/core2_native_hci/evidence-2026-10-24-hci4-halted-gate-5x.json`。
60 秒 hold 证据：
`tests/uiflow2/core2_native_hci/evidence-2026-10-24-hci4-hold60-3x.json`。
120 秒 hold 证据：
`tests/uiflow2/core2_native_hci/evidence-2026-10-24-hci4-hold120-2x.json`。
Active-BLE 120 秒 hold 证据：
`tests/uiflow2/core2_native_hci/evidence-2026-10-24-hci4-active-ble-hold120-2x.json`。

60 秒运行中 BLE peer 正常关闭后设备保持 running，QOM 的 write error
仅在 `peer-closed>0` 时允许，其他 HLI errors 仍必须为 0。
120 秒运行中，BLE GATT 事务完成后 peer 会正常关闭；guest 继续发送 HCI
command 时可填满 32-packet TX queue。runner 只在
`peer-closed>0` 且 `tx-queue-depth>0` 时接受 `QUEUE_FULL` 尾态；HLI
errors、HLI/meta queue depth 和非 peer-close 的 queue-full 仍然是 FAIL。
进一步通过 `network.ble_linger_seconds=180` 让 GATT peer 在 hold 期间保持
连接：两轮 120 秒结束时均为 `peer-closed=0`、`tx-queue-depth=0`、
`last-error=0`，证明 active WiFi + 公网 + BLE GATT 共存持续两分钟。
active hold 只覆盖一条连接不断开；它不能证明 disconnect 后还能建立第二条连接。

#### 同一 guest 的 disconnect/reconnect 边界

`run_service_5x.py --ble-reconnect-cycles 20` 会要求同一个外部 peer 完成二十轮
完整的 scan/connect/NUS subscribe/write/notify/disconnect。执行顺序是：

- 先仅保留第一轮，确认 disconnect 本身不会让 NimBLE reset；
- 再开启后续 cycle，确认每次都能重新收到 advertisement；
- 检查每轮是否完成 NUS write/notify，并确认 HLI、TX/RX 和连接池健康。

历史失败表现为 first-cycle disconnect 后连续
`NimBLE: HCI process ack returned 12` 和 HCI reset。对照与 H2C/C2H trace
最终确认：

- guest disconnect 事件正常经 HLI 交付；
- connection、L2CAP 和 GATT pool 没有泄漏；
- 外部 Bumble compatibility 层错误地为无响应的
  `HCI_Host_Number_of_Completed_Packets (0x0c35)` 返回 Command Status；
- 下一条 `LE Set Advertising Data (0x2008)` 把这个 stale ACK 当自己的
  acknowledgement，`ble_hs_hci_process_ack` 因 opcode mismatch 返回
  `BLE_HS_ECONTROLLER (12)`，随后 NimBLE reset。

修正后，stock Core2 固件在 3 个独立 `/api/v1` lease 中都完成二十轮
NUS GATT；每轮 frame/QOM、WiFi、公网、pcap、evidence 和 HLI health PASS。
每轮 guest RX 与 notification 均成立，`trace-hs-sched-reset=0`、
`trace-gap-adv-start=20`、HLI posts/consumed 为 `577/577`，events 397、
ACLs 180；三个 lease
都回到 conn/L2CAP/GATT `3/9/3` 的空闲池基线。

- 十轮成功证据：
  `tests/uiflow2/core2_native_hci/evidence-2026-10-24-hci4-reconnect10-3x.json`
- 二十轮成功证据：
  `tests/uiflow2/core2_native_hci/evidence-2026-10-24-hci4-reconnect20-3x.json`
- 首次十轮运行的 service timeout 失败：
  `tests/uiflow2/core2_native_hci/evidence-2026-10-24-hci4-reconnect10-timeout-fail.json`
- 较早的五轮成功证据：
  `tests/uiflow2/core2_native_hci/evidence-2026-10-24-hci4-reconnect5-3x.json`
- 双轮成功证据：
  `tests/uiflow2/core2_native_hci/evidence-2026-10-24-hci4-reconnect2-3x.json`
- 历史失败与根因：
  `tests/uiflow2/core2_native_hci/evidence-2026-10-24-reconnect2-fail.json`

二十轮和三十轮 reconnect 关闭的是同 guest 连接生命周期门禁，不表示物理
cache/PSRAM、bit-exact controller、多小时 coexistence 或真机已经等价。
后续长稳仍需验证超过三十轮的连接与更长 hold。当前 reconnect 上限为
`30`，service runner 的 hold 上限为 `120s`；下一轮必须先扩大这两个执行
上限和等待预算。

## 剩余工作量

下面是当前阶段之后的重新估算，不包含已经完成的 HCI-1、HCI-2、
HCI-3a、HLI event/ACL、`HCI-3b` 完整外部 NUS GATT 和 `HCI-4`
Device Service repeated lease；`CORE2-02` 的短时 extended-run 和二十轮
reconnect 门禁已 PASS：

- 若必须实现 bit-exact controller/baseband、PHY 与 coex，另计 `4–8` 周；
- 物理 cache/PSRAM 等价性、超过三十轮连接、长期 coexistence/soak 和真机
  路径需要独立
  计划，不能由当前 `5×10s` / `3×60s` / `2×120s` 重复门禁推导；当前
  PASS 覆盖 halt-gated guest 注入、最多两分钟的独立 lease 生命周期和
  active BLE 共存、二十轮和三十轮 reconnect；不覆盖超过三十轮连接或多小时
  soak。

若 classic ESP32 VHCI shared-memory 的 controller-to-host queue 无法从现有
firmware/ELF 和 QEMU 状态建立可验证语义，`HCI-4` 会升级为架构 blocker，
届时保留显式诊断模式，不以 retry 或 GDB hack 掩盖。

## 明确不接受

- 修改固件为 HCI-UART offload 后冒充 stock internal-controller；
- 在 Python/GDB 中伪造 C2H event 或写死 guest marker；
- 把 WiFi/公网 PASS 拼接成 BLE PASS；
- 自动 retry 后只报告成功次数；
- 把 QEMU virtual HCI 描述为 RF、controller 固件或真机等价。
