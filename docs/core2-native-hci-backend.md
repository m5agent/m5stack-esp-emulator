# Core2 native HCI backend design

日期：`2026-10-26`

本文定义 `CORE2-01` 的目标结构、当前 GDB 诊断桥的失效边界，以及可执行的
QEMU 内部实现路线。当前能力结论仍以
[项目当前状态](project-status.md) 为准，未完成项只在
[项目 Backlog](project-backlog.md) 跟踪。

> 本页同时保留设计、根因和按时间累积的验证记录。下文中的轮次、哈希和
> `PASS/FAIL` 是当时 evidence 的事实，不代表整个平台今天的全局状态；当前
> 能力与剩余边界只看状态页，精确运行结果只看验证台账。

## 当前阶段快照

| 阶段 | 状态 | 已提交产物 | 结论 |
| --- | --- | --- | --- |
| `HCI-1` host transport | `PASS` | `patches/qemu-core2-native-hci/0001-esp32-native-hci-transport.patch` | H4 framing、bounded queue、overflow、peer lifecycle、QOM counters 和 clean shutdown 已通过 targeted test |
| `HCI-2` H2C | `PASS` | `env-pointer-address` poller；`test_guest_h2c.py`；`0003` API-boundary hook | 首个 `01030c00` 与完整 H2C 命令流均不依赖 GDB |
| `HCI-3a` C2H callback | `DIAGNOSTIC PASS` | `c2h-allocator-address`、注册 callback 调用、send-available 和 QOM counters | Reset Complete 已交付 guest 的 `notify_host_recv`，callback status 为 0，guest 随后发出 Read Local Version；连续 `5/5`。这只证明窄路径 ABI，不是可扩展产品后端 |
| `HCI-3b` HLI event | `PASS` | `0002-esp32-native-hci-hli-event.patch`、`test_hli_event.py` | guest 池分配真实 Reset Complete，经 HLI event 13 和 `ble_transport_to_hs_evt_impl` 交付；`01030c00 → 01011000` 连续 `5/5` |
| `HCI-3b` full transaction | `PASS` | `0003-esp32-native-hci-api-transaction.patch`、`0004-xtensa-ccount-tb-yield.patch`、`run_full.py --hli-c2h` | 无 GDB 完成 scan/connect/NUS discovery/subscribe/write/notify 和 Bumble ACK；合法 loader 为 15-byte probe / 17-byte ATT PDU，连续 `5/5` |
| `HCI-4` stability | `PASS` | `run_service_5x.py`、`evidence-2026-10-24-hci4-service-5x.json` | 规范 profile `core2-native-hci` 通过五个独立 `/api/v1` lease；每轮同时验证 frame、QOM、WiFi/公网、外部 NUS GATT、pcap 和 evidence ZIP，且 `gdb_bridge=false` |
| `CORE2-02` extended run | `PASS` | `0005-esp32-native-hci-guest-call-sregs.patch`、hold 60/120s evidence、`evidence-2026-10-24-hci4-active-ble-hold600-2x.json` | caller-saved sregs 与 halted/idle gate 后，两批 `5×10s`、3 个 `60s`、2 个 `120s` 和 2 个 active-BLE `600s` hold 已通过；600s hold 的 peer 全程连接，HLI `45/45` 且队列/错误为 0 |
| `CORE2-02` 7200s diagnostic | `DIAGNOSTIC PASS` | `evidence-2026-10-24-hci4-active-ble-hold7200-diagnostic.json` | WiFi/公网/active BLE GATT/frame/pcap 保持 7200 秒，HLI `45/45` 且错误/队列/peer-close 为 0；QEMU 在 run 中被临时重编，旧 runner 未冻结启动哈希，因此不关闭 artifact-bound 门禁 |
| `CORE2-02` artifact-bound 7200s | `FUNCTIONAL PASS / RSS REVIEW` | `evidence-2026-10-24-hci4-active-ble-hold7200-artifact-bound-1x.json` | 首 lease 前绑定 firmware/ELF/QEMU 哈希，运行期无资产漂移；WiFi/公网/GATT/frame/pcap/HLI health 和 session 清理 PASS。QEMU host RSS 从 `744160 KiB` 增至 `1202176 KiB`，后续归因到未限容 TCG translation buffer；该证据仍不写“RSS bounded”。后续 runner 已增加 runner/service/accelerator/tool 文件哈希绑定 |
| Core2 host TCG memory bound | `VALIDATED / 120s` | `evidence-2026-10-24-hci4-tb128-hold120-1x.json`；`qemu_accel.py` | 原先未限定 TCG translation buffer，默认最多保留 `1 GiB`；`vmmap` 显示增长落在 `VM_ALLOCATE`。改为 `tb-size=128` 后 120 秒功能全 PASS，RSS delta `-16 KiB`、phys-footprint delta `-17408 KiB` |
| `CORE2-02` final bounded 7200s | `PASS` | `run_service_5x.py --hold-seconds 7200 --attempts 1`；`evidence-2026-10-25-hci4-active-ble-hold7200-tb128-artifact-bound-1x.json` | firmware/ELF/QEMU 与 runner/service/accelerator/limits 工具哈希在首 lease 前冻结，运行期无漂移；`bounded_tcg_cache`、frame/QOM、WiFi/公网、active-BLE GATT、pcap、HLI health 和 cleanup 全 PASS。240 个资源采样中 RSS `323536→252992 KiB`、phys footprint `250880→188416 KiB`，未出现旧两小时的单调增长 |
| Core2 runtime memory | `PASS` | `qemu_runtime_memory()`、`0030-core2-eight-mib-psram.patch`、Device Service QOM | CLI `-m 0` 解析为 QOM-effective `8 MiB` / `has_psram=true`；普通 DRAM1 heap 仍是架构允许的 `4 MiB` 直接映射窗口。物理 PSRAM/cache timing 仍为 `NOT RUN` |
| Core2 upper-PSRAM MMU bank switch | `3/3 PASS` | `tests/firmware/core2_psram_himem/run_test.py --attempts 3`；`evidence-2026-10-25-core2-himem-bank-switch-3x.json` | 三个独立 lease 都通过 `esp_himem` 将两个不同 32 KiB 物理块映射到同一虚拟窗口并反向校验；`physical_himem_bytes=4,456,448`、reserve `262,144 B`、QOM `8,388,608 B`、无 mismatch/failure marker |
| Core2 guest PSRAM sustained stress | `3/3 PASS` | `run_service_5x.py --require-psram --hold-seconds 120 --attempts 3`；`evidence-2026-10-25-core2-psram-sustained-8m-3x120.json`；pcap summary | 3 个独立 artifact-bound lease 均观察到 `4,194,304 B` 普通 DRAM1 heap，guest 分配 `1,048,576 B` bytearray，分别完成 35/35/35 次全缓冲校验，累计 `105 MiB`；每轮受控 HTTP、公网 recheck、active BLE、frame/QOM、NUS GATT、pcap、evidence 与 cleanup PASS。QOM device capacity 另由 `8 MiB` 和 upper-bank probe 覆盖；物理 timing 不在结论内 |
| Core2 guest PSRAM 600-second stress | `1/1 PASS` | `run_service_5x.py --require-psram --hold-seconds 600 --attempts 1`；`evidence-2026-10-25-core2-psram-sustained-1x600.json`；pcap summary | 单 lease 600 秒完成 179 次 `1 MiB` 全缓冲校验（约 `179 MiB`）、51 次受控 HTTP、18 次公网 recheck；active BLE/HLI、bounded TCG、frame/QOM、912-packet pcap、evidence 和 cleanup PASS。20 个 RSS 采样 `327472→327824 KiB`，不声明物理 PSRAM/cache timing |
| `CORE2-02` same-guest reconnect | `PASS` | `run_service_5x.py --ble-reconnect-cycles 20`、`0006-esp32-native-hci-observability.patch`、`evidence-2026-10-24-hci4-reconnect10-3x.json`、`evidence-2026-10-24-hci4-reconnect20-3x.json` | 修正 Bumble 对无响应 `0x0c35` 的非法 Command Status 后，先完成 3 个 lease 各 10 轮，再扩到各 20 轮；二十轮结果每 lease HLI 577/577、events 397、ACLs 180 清空，连接/L2CAP/GATT 池回到 `3/9/3` |
| `CORE2-02` 30-cycle extension | `PASS` | `run_service_5x.py --ble-reconnect-cycles 30 --attempts 3`、`evidence-2026-10-24-hci4-reconnect30-3x.json` | 3 个独立 lease 各 30 轮；每 lease HLI `857/857`、events 587、ACLs 270、HLI errors/queue/panic 为 0，连接池回到 `3/9/3` |
| `CORE2-02` 60-cycle extension | `PASS` | `run_service_5x.py --ble-reconnect-cycles 60 --attempts 3`、`evidence-2026-10-24-hci4-reconnect60-3x.json` | 3 个独立 lease 各 60 轮；每 lease HLI `1697/1697`、events `1157`、ACLs `540`、HLI errors/queue/panic 为 0，连接池回到 `3/9/3` |
| `CORE2-02` 120-cycle extension | `PASS` | `run_service_5x.py --ble-reconnect-cycles 120 --attempts 3`、`evidence-2026-10-24-hci4-reconnect120-3x.json` | 3 个独立 lease 各 120 轮；每 lease HLI `3377/3377`、events `2297`、ACLs `1080`、HLI errors/queue/dropped/panic 为 0，连接池回到 `3/9/3` |
| `CORE2-02` 121-cycle readiness budget | `FIXED` | `evidence-2026-10-25-hci4-reconnect121-readiness-timeout-1x.json`、`ble_runtime_limits.py` | 首次运行完成 29 轮并开始第 30 轮后，被固定 `180s` readiness 预算误杀；guest 无 panic。runner 和 Device Service 改为共享 workload-aware 预算，`121` 轮/`2s` 延迟为 `1028s` |
| `CORE2-02` reconnect accelerator sampling | `FIXED` | `evidence-2026-10-25-hci4-reconnect121-accelerator-sampling-fail-1x.json`、`run_service_5x.py` | 功能 `121/121` PASS，但 reconnect-only 路径没有 hold loop，QEMU accelerator 未被采样，形成 `bounded_tcg_cache` 假失败；runner 现于 session first running 时直接采样 |
| `CORE2-02` 121-cycle three-lease gate | `3/3 PASS` | `evidence-2026-10-25-hci4-reconnect121-3x.json` | 3 个独立 artifact-bound lease 均为 `121/121 PASS`，且 firmware/ELF/QEMU/工具哈希一致；每 lease `tb-size=128`、WiFi/公网、NUS GATT、frame/QOM、pcap、evidence 与 cleanup PASS。每 lease HLI `3405/3405`、events 2316、ACLs 1089，队列、错误、dropped、peer-close 和 panic 均为 0 |
| `CORE2-02` active-stop/recovery | `3/3 PASS` | `run_service_teardown.py --attempts 3`；`evidence-2026-10-25-core2-active-stop-recovery-3x.json` | 三个 session 均在 BLE peer linger 窗口内删除；每次为 `stopped`/无错误，HTTP/BLE companion terminate，BLE/QEMU PID 回收，worker lease 归零，随后新 session 再完成 frame/QOM、DHCP/DNS/HTTP、外部 NUS GATT、pcap 和 evidence。该门禁关闭 active-stop cleanup；不等于 throughput、controller 或物理 cache/PSRAM |
| `CORE2-02` post-reset stop/recovery | `3/3 PASS` | `run_service_teardown.py --stop-mode after-reset --attempts 3`；`evidence-2026-10-29-core2-post-reset-stop-recovery-3x.json` | 三个 ready session 先冻结 frame/QOM/network/GATT/pcap evidence，再执行 guest `system_reset`；同一 QEMU PID 在 reboot-in-flight 窗口保持 running，随后 stop 达 `stopped`/无错误，HTTP/BLE companion terminate、两 PID 回收、worker lease 归零，下一次 lease 仍完成 ready/network/GATT/frame/QOM。扩展 teardown 模式，不改变 controller/物理边界 |
| `CORE2-02` staggered concurrent leases | `2/2 PASS` | `run_service_5x.py --attempts 2 --concurrency 2 --stagger-seconds 30 --hold-seconds 120 --require-psram`；`evidence-2026-10-25-core2-concurrent-2x120-stagger30.json` | 两个 `qemu-unified/core2-native-hci` session 最大同时数为 2；共享同一固件/ELF/QEMU，分别使用 QEMU `guestfwd` HTTP endpoint。两轮均完成 Wi-Fi、公网 DNS/HTTP、external NUS GATT、30+ 次 `1 MiB` PSRAM sweep、frame/QOM、pcap、bounded TCG、evidence 和 cleanup；frame/QOM 一致，HLI `45/45`，无 panic |
| `CORE2-02` simultaneous cold-start history | `HISTORICAL / SUPERSEDED` | `evidence-2026-10-25-core2-concurrent-2x120-simultaneous-timeout30-pass.json`、`evidence-2026-10-25-core2-concurrent-4x120-hli-errors-fail.json`、`evidence-2026-10-25-core2-concurrent-4x120-simultaneous-pass.json`、`evidence-2026-10-25-core2-concurrent-4x120-simultaneous-confirm-fail.json`；`0007` | GATT timeout `30s` 后首对 `2/2 PASS`；旧扩展运行 `3/4` 且 `hli-errors=3`。`0007` 清除无效 HLI 调度并使首批 `4/4 PASS`，但同实现复核仍在 `ble_hs_hci_process_ack` 收到过晚 Command Status 后 panic。`0008` 随后关闭双实例路径；四实例后来独立复测再次暴露 2-packet reserve 不足，由后续 `0009` 扩大备用池解决 |
| `CORE2-02` simultaneous cold-start preallocation | `PASS` | `evidence-2026-10-25-core2-concurrent-4x120-prealloc-pass-a.json`、`evidence-2026-10-25-core2-concurrent-4x120-prealloc-confirm-pass-b.json`、`evidence-2026-10-25-core2-hli-preallocation-latency.json`；`0008-esp32-native-hci-preallocate-hli-objects.patch` | 两批独立无错峰 `4×120s` 合计 `8/8 PASS`。CPU0 idle 时预分配 2 个真实 guest event buffer 和 2 个 ACL mbuf；繁忙时 QEMU 直接填充 guest 对象，不嵌套 guest call。每轮 36 events/9 ACLs 全部 fast path、HLI `45/45`、errors/reset/panic 为 0；trace Command Status 接收→HLI 从约 `3.660s` 降到 `0.328s`，低于 NimBLE `2s` ACK 预算。只覆盖两实例、指定 firmware/ELF/QEMU |
| `CORE2-02` three-instance no-stagger gate | `6/6 PASS` | `evidence-2026-10-25-core2-concurrent-3x120-pass-a.json`、`evidence-2026-10-25-core2-concurrent-3x120-confirm-pass-b.json`；失败对照 `...peer-timeout-fail.json`、`...scan120-threshold-fail.json` | 两批独立三实例 `3×120s` 均为 `3/3 PASS`。三个 QEMU、BLE peer 和 per-session HTTP fixture 同时运行；每 lease HLI `45/45`、events 36、ACLs 9、errors/reset/panic 为 0，完成 WiFi/公网/GATT/frame/QOM/pcap/evidence 和 29–30 次 `1 MiB` PSRAM 全缓冲校验。历史运行先暴露固定 `40s` peer scan 预算过短，再暴露并发下 sweep 下限 `30` 过紧；最终按最高服务并发 8 的争用校准为 `hold/12`，仍要求连续序列、heartbeat、HTTP 和公网 recheck |
| `CORE2-02` four-instance initial failure | `FAIL 1/4` | `evidence-2026-10-25-core2-concurrent-4x120-prealloc-4way-fail.json` | 最大并发 session 数为 `4`，确实同时启动四个 QEMU。attempt 2 完成可见 WiFi/公网/GATT/PSRAM/frame/QOM/pcap，但 `hli-errors=1`、`hli-prealloc-failures=2`；attempt 3/4 在 READY 前反复 `LoadProhibited @ 0x402630cc`。Bumble peer 实际逐条返回 Command Complete，排除了“没有 controller 响应”；符号指向 `ble_hs_hci_process_ack()` 的 ACK opcode 读取 (`ble_hs_hci.c:495`)，reboot 后的 `PC=0` 是次生故障 |
| `CORE2-02` four-instance expanded reserve | `8/8 PASS` | `evidence-2026-10-25-core2-concurrent-4x120-prealloc8x4-pass-a.json`、`evidence-2026-10-25-core2-concurrent-4x120-prealloc8x4-confirm-pass-b.json`；`0009-esp32-native-hci-expand-hli-preallocation.patch` | 两批独立四实例 `4×120s` 均 `4/4 PASS`。`0008` 的 2 个 event buffer 会被四条并发 guest 启动命令序列耗尽，CPU0 尚未再次 idle 时后续 Bumble ACK 无法注入 HLI；`0009` 将真实 guest reserve 扩为 8 event/4 ACL。每 lease 完成 WiFi/公网/GATT/PSRAM/frame/QOM/pcap/evidence，HLI `45/45`、36 events/9 ACLs、errors/reset/panic 为 0，结束时 spare depth `8/4`。首批一个 lease 有 2 次 transient refill failure，后补满且不产生 HCI error |
| `CORE2-02` five-instance staggered | `10/10 PASS` | `evidence-2026-10-25-core2-concurrent-5x120-stagger30-pass-a.json`、`evidence-2026-10-25-core2-concurrent-5x120-stagger30-confirm-pass-b.json` | 两批独立 `5×120s` 均使用 30 秒 startup stagger 并通过 `5/5`。最大并发 session 数为 5；每个 lease 完成 WiFi/公网/NUS GATT/PSRAM/frame/QOM/pcap/evidence，HLI `45/45`、36 events/9 ACLs、errors/reset/panic 为 0。runner 并发上限与服务默认单设备容量一致，当前为 8 |
| `CORE2-02` five-instance simultaneous cold start | `10/10 PASS with fixed icount` | `evidence-2026-10-25-core2-concurrent-5x120-fixed-icount-blefirst-pass-a.json`、`evidence-2026-10-25-core2-concurrent-5x120-fixed-icount-blefirst-pass-b.json`；历史失败 `evidence-2026-10-25-core2-concurrent-5x120-no-stagger-pass-1.json`、`evidence-2026-10-25-core2-concurrent-5x120-no-stagger-fail-1.json` | 旧 `shift=auto` 实现下，一批零错峰 `5×120s` 为 `5/5 PASS`，独立确认批为 `3/5 FAIL`，因此错峰稳态不能继承给同时冷启动。trace 显示 guest 在 PSRAM 初始化窗口关闭中断时 HLI 已入队；`shift=auto` 又会随宿主争用拉伸虚拟时间，使 delivery 越过 NimBLE ACK 预算。默认改为固定 `shift=5`，并让测试 BLE server 在 WiFi 和长 PSRAM 压力前启动后，两批独立零错峰 `5×120s` 均 `5/5 PASS`，合计 `10/10`。每个 lease 完成 WiFi DHCP/HTTP、公网 DNS/HTTP、NUS GATT、frame、31 节点 QOM、pcap、evidence 和 14–15 次 1 MiB PSRAM 全缓冲校验；HLI `45/45`、36 events/9 ACLs，errors/reset/panic/dropped/queue depth 均为 0 |
| `CORE2-02` six-instance simultaneous cold start | `12/12 PASS with fixed icount` | `evidence-2026-10-25-core2-concurrent-6x120-fixed-icount-pass-a.json`、`evidence-2026-10-25-core2-concurrent-6x120-fixed-icount-pass-b.json` | 两批独立零错峰 `6×120s` 均 `6/6 PASS`，合计 `12/12`，最大真实并发 6。每个 lease 完成 WiFi DHCP/HTTP、公网 DNS/HTTP、NUS GATT、frame、31 节点 QOM、pcap、evidence 和 12–13 次 1 MiB PSRAM 全缓冲校验；HLI `45/45`、36 events/9 ACLs、reset/panic/dropped/queue depth 均为 0。batch B 的 attempt 6 记录一次可恢复 `hli-prealloc-failures=1`，随后仍完成全部 36/9 fast-path packet 和 45/45 HLI 投递，该 transient 保留为诊断 |
| `CORE2-02` eight-instance simultaneous cold start | `16/16 PASS after calibration` | `evidence-2026-10-25-core2-concurrent-8x120-threshold-fail.json`、`evidence-2026-10-25-core2-concurrent-8x120-fixed-icount-pass-a.json`、`evidence-2026-10-25-core2-concurrent-8x120-fixed-icount-pass-b.json` | 旧 `hold/10` 下限下首批 `4/8 FAIL`，但 HCI/网络/GATT/frame/QOM/pcap 全部 PASS、panic 为 0；失败 lease 均完成 11 次连续 sweep。该 evidence 保留为阈值校准控制。按最高服务并发 8 校准为 `hold/12` 后，两批独立 `8×120s` 均 `8/8 PASS`，合计 `16/16`，达到当前服务单设备容量。每 lease 完成 11–12 次 PSRAM 全缓冲校验；两批各保留一次可恢复 prealloc transient |
| `CORE2-02` eight-instance tool-hash rebind | `16/16 PASS` | `evidence-2026-10-26-core2-concurrent-8x120-network-hardening-pass-a.json`、`evidence-2026-10-26-core2-concurrent-8x120-network-hardening-pass-b.json` | HTTP Host/DNS exact-answer hardening 更新 `device_service.py` 与 `network_policy.py` 后，用当前工具 hash 重跑两批独立零错峰 `8×120s`。每批 `8/8 PASS`，最大真实并发 8；每 lease 完成 frame/31 节点 QOM、WiFi DHCP/HTTP、公网 DNS/HTTP、外部 NUS GATT、pcap、11–12 次 1 MiB PSRAM 全缓冲读回、bounded TCG、evidence 和 cleanup，HLI errors/reset/panic/dropped 为 0。manifest-identity rebind 的旧 A/B 证据保留。该重绑维持当前服务容量门禁，不证明大于八实例、持续吞吐、物理 PSRAM/cache、bit-exact controller/RF 或真机 |
| `CORE2-02` five-instance ACK observability | `HISTORICAL FAIL / RETAINED` | `evidence-2026-10-25-core2-concurrent-5x20-ack-observability.json`、`evidence-2026-10-25-core2-ack-observability-default-1x.json`、`evidence-2026-10-25-core2-ack-observability-summary.json`、trace/serial/peer logs；`0010-esp32-native-hci-ack-observability.patch` | 旧 `shift=auto` 诊断批次保留了 `3/5 PASS` 的零错峰失败。第一条 Reset response 已从 Bumble 返回，但 response→HLI 时间戳差为 `4.506306s`（host trace time，不是 guest 虚拟时钟）；guest 连续重发三次 Reset，恢复后旧 Reset Complete 与新 `0x1001` response 交错，`ble_hs_hci_process_ack` 以 error 12 调度 reset，后续 `0x402630cc` panic 是次生结果。第一条事件进入 ACK 检查时 `ack=NULL`、semaphore count `0`，排除了初始 stale ACK pointer/semaphore-state 假设。`0010` 只增加 opt-in 观测，不改变默认运行路径；历史失败不会删除 |

`HCI-3a` 已证明 callback ABI、guest buffer、window/return 和
send-available 的窄路径；`HCI-3b` 则改用 guest-visible HLI IRQ/queue，
并以 API-boundary H2C 隔离 firmware internal controller。旧 21-byte probe
生成 24-byte ATT PDU，超过默认 MTU 23，导致 L2CAP 拒绝；改用 15-byte
probe 后完整外部 NUS GATT 连续 `5/5`。`HCI-4` 随后让 Device Service
使用同一路径并通过五轮 independent lease；bit-exact controller 与物理
cache/PSRAM 仍是独立边界。`CORE2-02` 随后修复 nested guest-call 上下文：
恢复 caller-saved Xtensa 特殊寄存器，并只在 halted/idle vCPU 注入 HLI
allocator/callback；两次独立 5×10 秒 hold 运行合计 `10/10`，随后
3 个 60 秒 hold 运行 `3/3`，2 个 120 秒 hold 运行 `2/2`，2 个
active-BLE 600 秒 hold 运行 `2/2`。随后 3 个
独立 lease 先各自通过十轮、后又各自通过 20/30/60/120 轮 GATT reconnect；首次十轮运行还暴露并修复了
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

artifact-bound `7200s` active-BLE run 的功能门禁已经完成。首 lease 前冻结
firmware、ELF 和 QEMU 哈希，运行期资产无漂移；frame/pcap、WiFi/公网、外部
GATT、HLI health 和停止后清理均通过。QEMU host RSS 从 `744160 KiB` 上升到
`1202176 KiB`，因此本轮只关闭功能长稳门禁，内存增长趋势仍为 `REVIEW`。
禁止把功能 PASS 写成内存占用受限或物理内存等价。

进一步复核把 RSS 增长定位到 QEMU TCG translation buffer，而不是 guest
PSRAM：默认 `tb-size` 最多预留 `1 GiB`，macOS `vmmap` 的增长主要落在
`VM_ALLOCATE`。统一 Core2 accelerator helper 现使用
`tcg,thread=single,tb-size=128`；120 秒 active-BLE 功能复测为 `PASS`，
RSS `323600→323584 KiB`、phys footprint `214016→196608 KiB`，同时
HLI `45/45` 且错误和队列为 0。最终 artifact-bound 两小时复测随后也 PASS：
240 个资源采样中 RSS `323536→252992 KiB`、phys footprint
`250880→188416 KiB`，峰值分别为 `323808 KiB` 和 `256000 KiB`，没有形成
旧运行的持续增长曲线。“增长对象是 TCG translation buffer”已经由 `vmmap`
证据确认。runner 已将
`bounded_tcg_cache` 作为必需功能检查，accelerator 不是预期值时整轮 FAIL。

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

#### Concurrent CPU0 delivery latency

无错峰双实例运行暴露出一个独立于 `hli-errors` 的问题。QEMU packet trace
显示 Bumble 已在约 `4.6ms` 内返回 `LE Read Remote Features` 的
Command Status 和 LE Meta，但 ACL FIFO head 需要 guest allocator/mbuf
guest call，而目标 CPU0 正执行 cache-sensitive controller code；HLI
投递被推迟到约 `3.660s`，超过 NimBLE `BLE_HCI_CMD_TIMEOUT_MS=2000`，
随后进入 reset/错误 ACK 路径。

`0008` 使用真实 guest 对象预分配解决调用延迟，而不是放宽 guest ACK 判断：

- CPU0 idle 时调用真实 `ble_transport_alloc_evt(0)` 和
  `ble_transport_alloc_acl_from_ll()`，各保留 2 个 spare guest object；
- 收到 event/ACL 时，QEMU 直接把 Bumble payload 写入预分配对象；
- ACL mbuf 按匹配 ESP-IDF v5.5.4 的 32-bit `os_mbuf` 布局写入
  `om_data`、`om_len` 和 packet header `omp_len`；
- 仍然使用真实 `ble_transport_to_hs_evt_impl` /
  `ble_transport_to_hs_acl_impl` callback 和真实 HLI queue/IRQ；
- 如果没有 spare object，fallback 仍是原来的 halted/idle guest-call
  路径，不能绕过 guest 数据面。

最终 trace 中同一 Command Status 的接收→HLI 延迟为约 `0.328s`；两批
独立无错峰 `4×120s` 共 `8/8 PASS`，每轮 36 events/9 ACLs 全部走
fast path。证据：
`evidence-2026-10-25-core2-hli-preallocation-latency.json`。

三实例门禁进一步把 harness 生命周期与 guest 数据面拆开。旧 Device
Service 给扩展 BLE peer 固定 `40s` 扫描窗口，而三个 QEMU 同时冷启动时
guest 到 BLE 初始化约需 `55s`；peer 先退出，随后 socket 关闭才造成
`api-h2c-errors` 和 NimBLE HCI timeout。失败证据保留为
`evidence-2026-10-25-core2-concurrent-3x120-peer-timeout-fail.json`。
`ble_runtime_limits.py` 现按 session readiness 计算
`min(120s, max(40s, ready_timeout - 10s))`，并与 GATT operation timeout
分离。第二轮三实例已全部通过 guest/network/GATT，但两个 lease 在 120 秒
内完成 29 次而不是旧硬阈值 30 次 sweep；该校准失败保留为
`evidence-2026-10-25-core2-concurrent-3x120-scan120-threshold-fail.json`。
当时 final sweep 下限按 `hold/5` 设为 24；后续固定 `shift=5` 的五/六实例
曾校准为 `hold/10`。八实例 control 证明最高服务并发下部分完整 workload
完成 11 次连续 sweep，因此当前 floor 为 `hold/12`（120 秒下限 10），仍要求
连续序列、heartbeat、HTTP 和公网 recheck。两批独立三实例 evidence 均为 `3/3 PASS`。其中一个 lease
记录一次启动期 prealloc allocation failure，但最终恢复 `2/2` spare depth，
36/9 packet 全部走 fast path 且 HLI `45/45`；该 transient counter 保留为
诊断，不解释成最终对象缺失。

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
Active-BLE 600 秒 hold 证据：
`tests/uiflow2/core2_native_hci/evidence-2026-10-24-hci4-active-ble-hold600-2x.json`。
Active-BLE 7200 秒诊断保持证据：
`tests/uiflow2/core2_native_hci/evidence-2026-10-24-hci4-active-ble-hold7200-diagnostic.json`。

60 秒运行中 BLE peer 正常关闭后设备保持 running，QOM 的 write error
仅在 `peer-closed>0` 时允许，其他 HLI errors 仍必须为 0。
120 秒运行中，BLE GATT 事务完成后 peer 会正常关闭；guest 继续发送 HCI
command 时可填满 32-packet TX queue。runner 只在
`peer-closed>0` 且 `tx-queue-depth>0` 时接受 `QUEUE_FULL` 尾态；HLI
errors、HLI/meta queue depth 和非 peer-close 的 queue-full 仍然是 FAIL。
进一步通过 `network.ble_linger_seconds=660` 让 GATT peer 在 hold 期间保持
连接：两轮 600 秒结束时均为 `peer-closed=0`、`tx-queue-depth=0`、
`last-error=0`，HLI 为 `45/45`，证明 active WiFi + 公网 + BLE GATT
共存持续十分钟。
active hold 只覆盖一条连接不断开；它不能证明 disconnect 后还能建立第二条连接。

#### 同一 guest 的 disconnect/reconnect 边界

`run_service_5x.py --ble-reconnect-cycles 120` 会要求同一个外部 peer 完成
120 轮完整的 scan/connect/NUS subscribe/write/notify/disconnect。执行顺序是：

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

修正后，stock Core2 固件在 3 个独立 `/api/v1` lease 中分别完成 20、30、
60、120 轮 NUS GATT；每轮 frame/QOM、WiFi、公网、pcap、evidence 和 HLI
health PASS。120 轮每轮 guest RX 与 notification 均成立，
`trace-hs-sched-reset=0`、`trace-gap-adv-start=120`，HLI posts/consumed
为 `3377/3377`，events `2297`、ACLs `1080`；三个 lease 都回到
conn/L2CAP/GATT `3/9/3` 的空闲池基线。

- 十轮成功证据：
  `tests/uiflow2/core2_native_hci/evidence-2026-10-24-hci4-reconnect10-3x.json`
- 二十轮成功证据：
  `tests/uiflow2/core2_native_hci/evidence-2026-10-24-hci4-reconnect20-3x.json`
- 三十轮成功证据：
  `tests/uiflow2/core2_native_hci/evidence-2026-10-24-hci4-reconnect30-3x.json`
- 六十轮成功证据：
  `tests/uiflow2/core2_native_hci/evidence-2026-10-24-hci4-reconnect60-3x.json`
- 一百二十轮成功证据：
  `tests/uiflow2/core2_native_hci/evidence-2026-10-24-hci4-reconnect120-3x.json`
- 首次十轮运行的 service timeout 失败：
  `tests/uiflow2/core2_native_hci/evidence-2026-10-24-hci4-reconnect10-timeout-fail.json`
- 较早的五轮成功证据：
  `tests/uiflow2/core2_native_hci/evidence-2026-10-24-hci4-reconnect5-3x.json`
- 双轮成功证据：
  `tests/uiflow2/core2_native_hci/evidence-2026-10-24-hci4-reconnect2-3x.json`
- 历史失败与根因：
  `tests/uiflow2/core2_native_hci/evidence-2026-10-24-reconnect2-fail.json`

20、30、60 和 120 轮 reconnect 关闭的是同 guest 连接生命周期门禁，不表示物理
cache/PSRAM、bit-exact controller、两小时 coexistence 或真机已经等价。
另一次不带资产绑定的 7200 秒行为保持保留为 `DIAGNOSTIC_PASS`。使用
hash-freeze runner 的重跑已完成 `7200s` 功能门禁：

- 首 lease 前冻结 firmware、ELF 和 QEMU，运行期 `input_asset_drift={}`；
- frame `3710` bytes、QOM `34` 节点、WiFi、公网 DNS/HTTP、外部 NUS GATT、
  pcap 和 evidence ZIP 均 PASS；
- HLI `45/45`、events `36`、ACLs `9`，errors、HLI/meta/TX queue、
  dropped 和 peer-close 均为 `0`，无 panic；
- QEMU host RSS 曾从 `744160 KiB` 增至 `1202176 KiB`（`+458016 KiB`）；
  后续 `vmmap` 已归因到未限容 TCG translation buffer，最终
  `tb-size=128` artifact-bound 两小时复测为 PASS。

证据：
`tests/uiflow2/core2_native_hci/evidence-2026-10-25-hci4-active-ble-hold7200-tb128-artifact-bound-1x.json`。
当前 reconnect 参数范围扩到 `121`，`122` 会被拒绝；`120` 已有三个独立
lease PASS。`121` 的第一次运行在应用、WiFi、公网和 29 个完整 cycle 后，
于第 30 轮开始时被固定 `180s` readiness 预算误杀；第二次运行完成
`121/121`，却因 reconnect-only 路径未进入 hold loop 而漏采 QEMU
accelerator，形成 `bounded_tcg_cache` 假失败。两个 harness 问题修复后，
第三个 artifact-bound lease PASS；随后再补两个独立 lease，`3 × 121`
最终为 `3/3 PASS`，三轮 firmware/ELF/QEMU/工具哈希一致。hold 上限为
`7200s`；600 秒 active-BLE gate 已通过。

## 剩余工作量

下面是当前阶段之后的重新估算，不包含已经完成的 HCI-1、HCI-2、
HCI-3a、HLI event/ACL、`HCI-3b` 完整外部 NUS GATT 和 `HCI-4`
Device Service repeated lease；`CORE2-02` 的短时 extended-run 和 20、30、
60、120 轮 reconnect 门禁已 PASS：

- 若必须实现 bit-exact controller/baseband、PHY 与 coex，另计 `4–8` 周；
- 物理板载 `8 MiB` PSRAM、cache/PSRAM 等价性和真机
  路径需要独立
  计划，不能由当前 `5×10s` / `3×60s` / `2×120s` 重复门禁推导；当前
  PASS 覆盖 halt-gated guest 注入、artifact-bound 两小时 active-BLE
  WiFi/公网/GATT 功能保持、限容 host-memory 和 20、30、60、120 轮
  reconnect；三 lease 121 轮已完成 `3/3`，active-stop/recovery 也已
  `3/3 PASS`：在 peer 仍处于 linger 时结束 session，companion、PID 和
  worker lease 全部清理，并连续启动新 session。guest 还已在 `3×120s`
  中完成累计 105 次 `1 MiB` 虚拟 PSRAM 全缓冲校验和周期联网。两个
  `core2-native-hci` lease 在 30 秒启动错峰后，已同时保持 120 秒并各自
  完成 BLE、WiFi、公网、PSRAM 和 evidence；并发稳态不再列为完全未执行。
  无错峰双实例路径也已完成两批独立 `4×120s`，合计 `8/8 PASS`：`0007`
  禁止在未观察到有效 guest HLI 队列时安排投递；`0008` 在 idle 时预分配
  真实 guest event buffer/ACL mbuf，使 CPU0 繁忙时无需嵌套 guest call
  也能把 controller event 和 ACL 放进 firmware HLI queue。trace 中
  Command Status 的接收→HLI 延迟由约 `3.660s` 降至 `0.328s`。剩余并发项
  已继续推进到两批独立三实例 `3×120s`，合计 `6/6 PASS`；三个 QEMU、
  peer、HTTP fixture、WiFi/公网/GATT、PSRAM、frame/QOM/pcap/evidence
  同时成立。四实例首批 `4×120s` 随后实际执行并 FAIL：一个 lease 出现
  HLI health/prealloc failure，两个在 READY 前于 NimBLE
  `ble_hs_hci_process_ack()` 读取 ACK opcode 时 `LoadProhibited`，前序已有
  HCI ACK timeout/reset。Bumble peer 的 H4 日志显示 Command Complete 已返回，
  因而根因收敛到 `0008` 两 packet reserve 在四条并发启动 burst 中耗尽。
  `0009` 将 reserve 扩到 8 event/4 ACL 后，两批独立四实例各 `4/4 PASS`，
  合计 `8/8`。五实例 30 秒错峰两批各 `5/5`，合计 `10/10`。旧
  `shift=auto` 实现的零错峰冷启动一批 `5/5`、独立确认批 `3/5`；
  `0010` trace 证明失败从 HLI response readiness/delivery ordering 开始：
  首条 Reset Complete 在 Bumble 已返回，但 response→HLI 时间戳差为
  `4.506306s`（host trace time，不是 guest 虚拟时钟），期间 CPU0 又在
  PSRAM 初始化时关闭中断，旧 response 在 guest 前进后才被投递。当前
  `qemu_accel.py` 默认固定 `shift=5`，统一 probe 把 BLE server 放到 WiFi
  和长 PSRAM 压力前；两批独立零错峰 `5×120s` 随后均为 `5/5 PASS`
  （合计 `10/10`），输入资产和工具哈希一致；随后两批六实例又均
  `6/6 PASS`（合计 `12/12`）。八实例先用旧 threshold 得到 `4/8`
  纯吞吐校准失败，改用 `hold/12` 后两批均 `8/8 PASS`（合计 `16/16`）。
  之后仍需大于八实例、持续
  吞吐、其他 teardown、物理 `8 MiB` 与 cache/PSRAM 等价性；固定虚拟时钟
  不代表实时速度或真机时序。

若 classic ESP32 VHCI shared-memory 的 controller-to-host queue 无法从现有
firmware/ELF 和 QEMU 状态建立可验证语义，`HCI-4` 会升级为架构 blocker，
届时保留显式诊断模式，不以 retry 或 GDB hack 掩盖。

## 明确不接受

- 修改固件为 HCI-UART offload 后冒充 stock internal-controller；
- 在 Python/GDB 中伪造 C2H event 或写死 guest marker；
- 把 WiFi/公网 PASS 拼接成 BLE PASS；
- 自动 retry 后只报告成功次数；
- 把 QEMU virtual HCI 描述为 RF、controller 固件或真机等价。
