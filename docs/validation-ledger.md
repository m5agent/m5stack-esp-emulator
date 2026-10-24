# 验证证据台账

日期：`2026-10-24`

本文只记录带日期的验证结果和证据入口。它用于回答“这项结论是什么时候、
用什么路径验证的”，不定义当前能力，也不定义待办。当前能力以
[项目当前状态](project-status.md) 为准，未完成工作以
[项目 Backlog](project-backlog.md) 为准。

所有未明确标为 hardware validation 的结果都是 virtual-device validation。
一次 PASS 只覆盖对应 commit、固件 SHA、runtime/profile、设备和检查项；
不能把同 SoC 的另一台设备、另一个安全模式或物理 RF 行为自动视为通过。

## 2026-10-24

| 工作流 | 结果 | 证据 |
| --- | --- | --- |
| 代码与文档基线 | 动态测试/矩阵计数集中到 `project-status.md`；README、文档导航和工作流台账改为链接；设备 catalog 与 QEMU profile 增加日期/状态交叉校验，并修正 AtomS3R、PaperMono 旧元数据；平台套件 `297/297 PASS` | [`test_qemu_profiles.py`](../platform/tests/test_qemu_profiles.py)、[`test_docs_consistency.py`](../platform/tests/test_docs_consistency.py) |
| 网络隔离 | private net/mount namespace、fail-closed、controlled DNS、TLS/Host allowlist、200/403 与 pcap 联合 PASS | [`controlled-dns-pass.json`](../tests/network/tls_allowlist/evidence-2026-10-24-controlled-dns-pass.json) |
| 错误密码 P0 | ESP32-S3 ESP-IDF guest 使用错误凭据后发生 6 次 auth/reject；无 DHCP、无 HTTP 进度；固件输出 `HTTP_TPUT_RESULT: FAILED (no IP in 20s)`，SoftAP 记录 wrong-password warning；`7/7` 负向检查同次 PASS | [`wrong-password-pass.json`](../tests/network/wrong_password/evidence-2026-10-24-wrong-password-pass.json) |
| DNS/UDP 数据面 | ESP32-S3 guest 完成 DHCP 和 DNS 解析，host peer 收到固定 UDP 载荷，guest 收到带前缀的同载荷回包；5/5 检查 PASS | [`dns-udp-pass.json`](../tests/network/idf_dns_udp/evidence-2026-10-24-dns-udp-pass.json) |
| FirmwareManifest 公共样本 | 公开 StickS3 Weather `2108939572843147265` 的 merged 与 WebBurner 三 segment 输入均规范化到同一 `8 MiB` artifact SHA256；camera-on-StickS3 返回结构化 `unsupported_capability`；Manifest 19 项、定向 service/security 6 项 PASS | [`public-manifest-web-conformance.json`](../tests/firmware/evidence-2026-10-24-public-manifest-web-conformance.json) |
| IP/端口 egress | nftables 默认 drop；允许/拒绝端口、允许/拒绝 IP、`1.1.1.1:80` veth/NAT、namespace/NAT 清理 PASS；TLS guest 在同一策略下 PASS | [`ip-port-pass.json`](../tests/network/egress_allowlist/evidence-2026-10-24-ip-port-pass.json) |
| Linux CI | Ubuntu runner 执行当时的 `236` 项平台测试和 fail-closed namespace/egress fixture；允许端点、拒绝目标、veth/NAT 与清理 PASS。该数字是历史证据，当前套件规模见项目当前状态 | [`github-actions-pass.json`](../tests/network/egress_allowlist/evidence-2026-10-24-github-actions-pass.json) |
| AP/radio loss | StickS3 guest 先 DHCP/HTTP；QOM `radio-enabled=false` 后扫描为 0，恢复后扫描为 1，同一 guest 再 DHCP 并完成 `/after` HTTP；pcap 含两组 DORA | [`radio-loss-pass.json`](../tests/network/reconnect_probe/evidence-2026-10-24-radio-loss-pass.json) |
| AP/radio loss 自动化回归 | 同一 `qemu-wifi` session 中 radio QOM `false→true`，扫描 `1→0→1`，两次 DHCP、前后 HTTP 200；pcap 含 2 组 DORA/OFFER/REQUEST/ACK 和两条受控 HTTP 流；16/16 checks PASS | [`radio-loss-recovery-pass.json`](../tests/network/reconnect_probe/evidence-2026-10-24-radio-loss-recovery-pass.json) |
| DHCP renewal | ESP-IDF guest 调用 `netifapi_dhcp_renew()`；pcap 出现初次 DORA 后的 `REQUEST/ACK`，地址保持并通过 HTTP | [`renewal-pass.json`](../tests/network/idf_dhcp_renewal/evidence-2026-10-24-renewal-pass.json) |
| 双设备 lab fabric | private namespace 内两台 StickS3 完成 DHCP；A→B TCP `19123` 请求/响应成功，两侧 pcap 均有双向 payload hash；宿主、公网、metadata、默认路由不可达，namespace 已清理 | [`two-guest-pass.json`](../tests/network/lab_fabric/evidence-2026-10-24-two-guest-pass.json) |
| 本地 worker lifecycle | 真实 StickS3 `qemu-wifi` lease：heartbeat、active lease、drain、活动会话保留、resume；强杀服务进程组后 generation 递增，旧 lease 标为 abandoned，会话恢复为 interrupted failed | [`worker-lifecycle-pass.json`](../tests/network/worker_lifecycle/evidence-2026-10-24-pass.json) |
| 远程 worker 注册目录 | 持久 identity/generation、stale 判定、live-instance 冲突、heartbeat/drain/stop、capability/结果上限、原子 `0600` 状态文件；HTTP 契约与 Bearer token 路径 PASS。该结果只证明目录 API，不证明 worker supervisor、调度或活动 QEMU 接管 | [`test_worker_directory.py`](../platform/tests/test_worker_directory.py)、[`test_device_service.py`](../platform/tests/test_device_service.py) |
| 远程 durable job queue | 幂等 submit/replay、capability matching、FIFO claim、identity-bound lease heartbeat、expiry retry、terminal result/cancel、worker stale/stop/generation 回收、持久重启恢复和 HTTP `/api/v1/jobs` 契约 PASS | [`queue-pass.json`](../tests/network/worker_queue/evidence-2026-10-24-queue-pass.json)、[`test_worker_queue.py`](../platform/tests/test_worker_queue.py)、[`test_device_service.py`](../platform/tests/test_device_service.py) |
| HTTP-only worker executor | 独立进程持久 generation、注册 worker、claim job、worker/job heartbeat、创建真实 StickS3 QEMU session、等待 running、下载 evidence ZIP/SHA256、`purge=0` 停止并提交 completed/PASS；live `1/1` PASS | [`executor-pass.json`](../tests/network/worker_executor/evidence-2026-10-24-executor-pass.json)、[`test_worker_agent.py`](../platform/tests/test_worker_agent.py) |
| Worker HMAC authentication | worker ID/instance/generation 派生 key；claim/heartbeat/result 需要 timestamp、nonce、body signature；unsigned claim `401`、body identity mismatch 与 replay 拒绝；启用 token 的真实 StickS3 job 仍 completed/PASS，live `1/1` PASS | [`executor-auth-pass.json`](../tests/network/worker_executor/evidence-2026-10-24-executor-auth-pass.json)、[`test_worker_auth.py`](../platform/tests/test_worker_auth.py) |
| 本地 QEMU restart re-attach | 单元/契约覆盖 PID start-time、session QMP ownership、`query-status=running`、缺失 identity 与 stale start-time 拒绝；真实服务 SIGKILL 仅杀服务、保留 QEMU，同状态目录重启后接管同一 PID、generation 2 lease，停止时清理 QEMU，live `1/1` PASS | [`reattach-pass.json`](../tests/network/worker_reattach/evidence-2026-10-24-reattach-pass.json)、[`test_device_service.py`](../platform/tests/test_device_service.py) |
| 共享 WiFi + 全矩阵 | patch `0028` 后 S3/C6/Core2 `67/67` case、`274/274` check，全部 `attempts=1`、`retry_used=false`；Cardputer-ADV 键盘 settle 已加固 | [`dual-guest-fabric-matrix.json`](../tests/uiflow2/evidence-2026-10-24-dual-guest-fabric-matrix.json) |
| 共享 QEMU | ESP32-S3 AES/GDMA 外部内存读取修复；当轮全矩阵 `67/67`、`274/274`，全部首轮无重试 | [`gdma-external-memory-matrix.json`](../tests/uiflow2/evidence-2026-10-24-gdma-external-memory-matrix.json) |
| 固件文件系统 | LittleFS 与只读 FAT12/16/32 文件清单、SHA256、LFN、敏感路径脱敏与 SPDX 提取 | [`fat-inventory.json`](../tests/firmware/evidence-2026-10-24-fat-inventory.json) |
| SPIFFS 文件清单 | 8 个声明配置的自包含多索引样本 PASS；LUT 与 page header 不一致、随机损坏输入均 `INVALID`；ESP-IDF `spiffsgen.py` canonical 镜像和 60000-byte 多索引文件 PASS | [`spiffs-inventory.json`](../tests/firmware/evidence-2026-10-24-spiffs-inventory.json) |
| 固件上传 | 可恢复 chunk artifact upload 的连续 offset、per-chunk/final SHA256、失败回滚、原子 metadata、abort 和 staging GC | [`streaming-artifact-upload.json`](../tests/firmware/evidence-2026-10-24-streaming-artifact-upload.json) |
| WebBurner | 浏览器流式 SHA256、4 MiB 多 chunk、进度/重试/取消、刷新恢复和 package → FirmwareManifest import；9.44 MiB 三 chunk 探针 PASS | [`webburner-ui.json`](../tests/firmware/evidence-2026-10-24-webburner-ui.json) |
| 固件安全配置 | 解析脱敏 `espefuse summary --format json`，区分镜像、sdkconfig、分区 flag 与 eFuse 证据；安全启动/Flash Encryption preflight 按预期拒绝 | [`efuse-security.json`](../tests/firmware/evidence-2026-10-24-efuse-security.json) |
| 固件许可策略 | provenance、文件系统 SPDX、SBOM 声明汇总；allowlist PASS、denylist REJECTED、无 allowlist/无声明/unknown 保持 REVIEW_REQUIRED；策略不是完整源码扫描或法律意见 | [`license-policy.json`](../tests/firmware/evidence-2026-10-24-license-policy.json) |
| Core2 稳定性 | 确定性 TCG/icount 下独立启动 `10/10` 首轮 PASS；同 guest board+WiFi+公网+native-VHCI BLE `3/3` | [`native-vhci-pinned.json`](../tests/uiflow2/unified_core2/evidence-2026-10-24-native-vhci-pinned.json) |
| Core2 Device Service | `qemu-unified/profile=core2-native-vhci` 单 lease 返回 frame、QOM、pcap、bridge 和 peer evidence | [`native-vhci-service.json`](../tests/uiflow2/unified_core2/evidence-2026-10-23-native-vhci-service.json) |
| Core2 repeated lease | 同一 GDB 诊断桥 repeated lease 仅 `1/2`，证明该路径不能作为稳定后端 | [`native-vhci-service-stability.json`](../tests/uiflow2/unified_core2/evidence-2026-10-24-native-vhci-service-stability.json) |
| Core2 native-HCI `HCI-1` | QEMU H4 chardev framing、32 packet bounded queue、overflow、peer、clean shutdown 和 QOM counters PASS | [`transport-pass.json`](../tests/uiflow2/core2_native_hci/evidence-2026-10-24-transport-pass.json) |
| Core2 native-HCI `HCI-2` | 不启动 GDB，从真实 VHCI shared memory 捕获 stock HCI Reset `01030c00`；完整命令序列等待 C2H | [`guest-h2c.json`](../tests/uiflow2/core2_native_hci/evidence-2026-10-24-guest-h2c.json) |
| Core2 native-HCI `HCI-3a` | 诊断性单包 C2H：callback status 0，Reset Complete 后 guest 发出下一条 H2C，targeted `5/5`。后续审计不支持把它扩展成产品后端 | [`c2h-delivery.json`](../tests/uiflow2/core2_native_hci/evidence-2026-10-24-c2h-delivery.json) |
| Core2 native-HCI internal-controller relay | 历史变体：Bumble peer 已发现/连接并完成首个 ATT request/response；第二个 ATT request 后 guest `ack returned 12` 并 Reset。该路径不是最终 API-boundary/HLI 方案 | [`hci3b-diagnostic.json`](../tests/uiflow2/core2_native_hci/evidence-2026-10-24-hci3b-diagnostic.json) |
| Core2 native-HCI API boundary | GDB return 语义审计确认 pre-entry API hook 不旋转 Xtensa window；实验性 QEMU API hook 完成广播、连接、NUS discovery 和订阅，但 final write/notify transaction 仍超时，实验未保留 | [`hci3b-api-boundary-audit.json`](../tests/uiflow2/core2_native_hci/evidence-2026-10-24-hci3b-api-boundary-audit.json) |
| Core2 native-HCI MTU negative case | 历史 `2/2` 使用 21-byte probe，形成 24-byte ATT PDU，超过 guest 默认 MTU 23；协议栈 trace 显示 `chan-found=9`、`mtu-reject=1`、`rxfn=8`，在 ATT dispatch 前拒绝，后续已用 17-byte PDU 闭环 | [`notification-fail.json`](../tests/uiflow2/core2_native_hci/evidence-2026-10-24-hci3b-hli-api-notification-fail.json)、[`oversize-att-mtu.json`](../tests/uiflow2/core2_native_hci/evidence-2026-10-24-oversize-att-mtu.json) |
| Core2 native-HCI `HCI-3b` full GATT | 同固件/ELF/QEMU build 使用 15-byte probe / 17-byte ATT PDU，HLI/API-boundary H2C 完成 discovery、subscription、write、Python handler、notify 和 Bumble ACK，连续 `5/5`；旧失败由 24-byte ATT PDU 超过默认 MTU 23 解释 | [`hli-api-gatt-5x.json`](../tests/uiflow2/core2_native_hci/evidence-2026-10-24-hli-api-gatt-5x.json) |
| Core2 native-HCI `HCI-4` | 规范 profile `core2-native-hci` 通过五个独立 `/api/v1` lease/QEMU 进程；每轮 frame、27 节点 QOM、WiFi DHCP/HTTP、公网 DNS/HTTP、外部 NUS GATT、pcap 和 evidence ZIP 均 PASS，`gdb_bridge=false` | [`hci4-service-5x.json`](../tests/uiflow2/core2_native_hci/evidence-2026-10-24-hci4-service-5x.json) |
| Core2 extended-run regression（历史失败） | `HCI-4 5/5` 后，带 hold 的独立运行在 READY/联网/BLE 连接后出现 panic。另一轮在 attempt 4 出现 `PC=0`；单轮失败首轮为 `IllegalInstruction` at `0x40266960` (`semphr_give_wrapper`)，随后 `InstrFetchProhibited` reboot loop。runner 已保留 partial evidence 并输出 aggregate FAIL；由下一行 halt-gated 修复证据取代 | [`extended-run-fail.json`](../tests/uiflow2/core2_native_hci/evidence-2026-10-24-extended-run-fail.json) |
| Core2 extended-run halt-gated fix | `0005` 恢复 caller-saved Xtensa sregs，并把 HLI guest allocator/callback 注入限制在 halted/idle vCPU。中间 sregs-only build `4/5`；halt gate 后两批独立 `5×10s` hold 合计 `10/10`。每轮 frame、QOM、WiFi/公网、NUS GATT、pcap 和 evidence PASS，`hli-posts=hli-consumed=47`、events=38、ACLs=9、`hli-errors=0`、HLI/meta queue 深度为 0 | [`hci4-halted-gate-5x.json`](../tests/uiflow2/core2_native_hci/evidence-2026-10-24-hci4-halted-gate-5x.json) |
| Core2 60-second hold | 3 个独立 QEMU lease 在 WiFi/公网/GATT/pcap/evidence 后保持 60 秒；全部 `3/3` PASS。设备在 BLE peer 正常关闭后继续 running；每轮 48 posts/48 consumed、39 events、9 ACLs、`hli-errors=0`，仅允许与 `peer-closed=1` 同时出现的 write-error 尾态 | [`hci4-hold60-3x.json`](../tests/uiflow2/core2_native_hci/evidence-2026-10-24-hci4-hold60-3x.json) |
| Core2 120-second hold | 2 个独立 stock Core2 lease 在 frame、34 节点 QOM、WiFi、公网 DNS/HTTP、NUS GATT、pcap、evidence 后各保持 120 秒；全部 `2/2` PASS。每轮 48 posts/48 consumed、39 events、9 ACLs、`hli-errors=0`、HLI/meta queue 为空；GATT peer 关闭后 `tx-queue-depth=32` 与 `last-error=2` 作为显式尾态分类 | [`hci4-hold120-2x.json`](../tests/uiflow2/core2_native_hci/evidence-2026-10-24-hci4-hold120-2x.json) |
| Core2 active-BLE 120-second hold | `ble_linger_seconds=180` 让 GATT peer 贯穿整个 hold；2 个独立 lease `2/2` PASS，frame/QOM、WiFi、公网、GATT、pcap 和 evidence 全通过。每轮 47/47 HLI posts/consumed、38 events、9 ACLs、`hli-errors=0`、HLI/meta queue 和 TX queue 为空，`peer-closed=0`、`last-error=0` | [`hci4-active-ble-hold120-2x.json`](../tests/uiflow2/core2_native_hci/evidence-2026-10-24-hci4-active-ble-hold120-2x.json) |
| Core2 same-guest reconnect boundary（历史失败） | `network.ble_reconnect_cycles=2` 时第一轮 scan/connect/NUS/write/notify/disconnect 成功，第二轮 advertisement 超时。重广告路径出现连续 `NimBLE: HCI process ack returned 12` 和 HCI reset；真正的 no-readvertise 对照无 reset。后续定位为 Bumble 对 `HCI_Host_Number_of_Completed_Packets (0x0c35)` 返回非法 Command Status，由下一命令消费成 stale ACK | [`reconnect2-fail.json`](../tests/uiflow2/core2_native_hci/evidence-2026-10-24-reconnect2-fail.json) |
| Core2 same-guest reconnect fix | 修正 Bumble compatibility 层，使 `0x0c35` 不再产生任何 HCI response。stock Core2 固件在 3 个独立 `/api/v1` lease 中均完成两轮 scan/connect/NUS GATT/disconnect；每轮 frame/QOM、WiFi、公网、pcap、evidence 与 HLI health PASS，第二轮有 guest RX 和 notification；`trace-hs-sched-reset=0`、`trace-gap-adv-start=2`、HLI 73/73 清空 | [`hci4-reconnect2-3x.json`](../tests/uiflow2/core2_native_hci/evidence-2026-10-24-hci4-reconnect2-3x.json) |
| Core2 five-cycle same-guest reconnect | 同一固件/QEMU build 在 3 个独立 lease 中各自完成 5 轮 scan/connect/NUS GATT/disconnect。每轮 frame/QOM、WiFi、公网、pcap、evidence 和 HLI health PASS；HLI `157/157`、events 112、ACLs 45，HLI errors 和队列深度为 0，connection/L2CAP/GATT 池回到 `3/9/3` 空闲基线，`trace-hs-sched-reset=0`、`trace-gap-adv-start=5` | [`hci4-reconnect5-3x.json`](../tests/uiflow2/core2_native_hci/evidence-2026-10-24-hci4-reconnect5-3x.json) |
| Core2 WiFi deterministic repeat | runner 之前文档声称使用 `tcg,thread=single` + `icount`，但代码漏传，导致 idle `WAITI` Cache error。修正后 WiFi-only scan/association/DHCP/HTTP 独立运行 `5/5` PASS | [`deterministic-5x.json`](../tests/network/core2_openmac_wifi/evidence-2026-10-24-deterministic-5x.json) |
| Core2 HLI queue | 实验写入 firmware `g_rw_schd_queue`/meta queue 并置 `INTSET[29]`；guest ISR/controller task 消费 event-13 marker，QOM 无错误、队列清空。该结果只证明交付 seam，不是 HCI/GATT PASS，实验未保留 | [`hci3b-hli-queue-diagnostic.json`](../tests/uiflow2/core2_native_hci/evidence-2026-10-24-hci3b-hli-queue-diagnostic.json) |
| Core2 HLI event | 保留的 QEMU patch 通过 guest `ble_transport_alloc_evt(0)` 分配真实 Reset Complete，经 event 13 和 `ble_transport_to_hs_evt_impl` 交付；`01030c00` 后 guest 发出 `01011000`，连续 `5/5`，HLI/meta queue 清空且无 malformed/dropped packet | [`hli-event-5x.json`](../tests/uiflow2/core2_native_hci/evidence-2026-10-24-hli-event-5x.json) |
| Core2 callback 路线审计 | safe-point callback 仍崩溃；nested `r_eif_send → vhci_send` 触发 cache-disabled 异常。两个实验均回退，patch reverse-check PASS | [`safe-point-audit.json`](../tests/uiflow2/core2_native_hci/evidence-2026-10-24-hci3b-safe-point-audit.json)、[`controller-entry-audit.json`](../tests/uiflow2/core2_native_hci/evidence-2026-10-24-hci3b-controller-entry-audit.json) |

## 2026-10-23

| 工作流 | 结果 | 证据 |
| --- | --- | --- |
| 单机网络隔离 | StickS3 QEMU guest 在 Linux private network namespace 内运行，外部路由缺失时按预期阻断 | [`linux.json`](../tests/network/linux_isolation/evidence-2026-10-23-linux.json) |
| TLS blocker | 当轮 TLS 阻塞点定位到 ESP32-S3 AES/GDMA 外部内存读取，作为后续 patch `0027` 的负向证据保留 | [`blocked.json`](../tests/network/tls_allowlist/evidence-2026-10-23-blocked.json) |
| TLS/Host allowlist | 测试 CA、允许 Host 200、拒绝 Host 403、请求决策和 pcap PASS | [`pass.json`](../tests/network/tls_allowlist/evidence-2026-10-23-pass.json) |
| 零重试矩阵 | 无自动重试的外设矩阵基线 | [`zero-retry-matrix.json`](../tests/uiflow2/evidence-2026-10-23-zero-retry-matrix.json) |
| 固件静态审查 | 公开固件 round-trip、URL/凭据脱敏、高熵块指纹和 SBOM | [`static-review.json`](../tests/firmware/evidence-2026-10-23-static-review.json) |

## 阅读规则

1. 先读 [项目当前状态](project-status.md)，确认该结论是否仍是当前能力。
2. 再读本页确认证据日期和当时边界。
3. 最后打开 evidence JSON，核对固件 SHA、runtime/profile、设备、检查项和
   `PASS`/`PARTIAL`/`FAIL` 字段。
4. 新证据按日期和主题追加，不改写旧失败；若结论被推翻，在当前状态页更新，
   在历史页说明取代关系。
