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
| 网络隔离 | private net/mount namespace、fail-closed、controlled DNS、TLS/Host allowlist、200/403 与 pcap 联合 PASS | [`controlled-dns-pass.json`](../tests/network/tls_allowlist/evidence-2026-10-24-controlled-dns-pass.json) |
| IP/端口 egress | nftables 默认 drop；允许/拒绝端口、允许/拒绝 IP、`1.1.1.1:80` veth/NAT、namespace/NAT 清理 PASS；TLS guest 在同一策略下 PASS | [`ip-port-pass.json`](../tests/network/egress_allowlist/evidence-2026-10-24-ip-port-pass.json) |
| Linux CI | Ubuntu runner 执行当时的 `236` 项平台测试和 fail-closed namespace/egress fixture；允许端点、拒绝目标、veth/NAT 与清理 PASS。该数字是历史证据，当前套件规模见项目当前状态 | [`github-actions-pass.json`](../tests/network/egress_allowlist/evidence-2026-10-24-github-actions-pass.json) |
| AP/radio loss | StickS3 guest 先 DHCP/HTTP；QOM `radio-enabled=false` 后扫描为 0，恢复后扫描为 1，同一 guest 再 DHCP 并完成 `/after` HTTP；pcap 含两组 DORA | [`radio-loss-pass.json`](../tests/network/reconnect_probe/evidence-2026-10-24-radio-loss-pass.json) |
| DHCP renewal | ESP-IDF guest 调用 `netifapi_dhcp_renew()`；pcap 出现初次 DORA 后的 `REQUEST/ACK`，地址保持并通过 HTTP | [`renewal-pass.json`](../tests/network/idf_dhcp_renewal/evidence-2026-10-24-renewal-pass.json) |
| 双设备 lab fabric | private namespace 内两台 StickS3 完成 DHCP；A→B TCP `19123` 请求/响应成功，两侧 pcap 均有双向 payload hash；宿主、公网、metadata、默认路由不可达，namespace 已清理 | [`two-guest-pass.json`](../tests/network/lab_fabric/evidence-2026-10-24-two-guest-pass.json) |
| 本地 worker lifecycle | 真实 StickS3 `qemu-wifi` lease：heartbeat、active lease、drain、活动会话保留、resume；强杀服务进程组后 generation 递增，旧 lease 标为 abandoned，会话恢复为 interrupted failed | [`worker-lifecycle-pass.json`](../tests/network/worker_lifecycle/evidence-2026-10-24-pass.json) |
| 共享 WiFi + 全矩阵 | patch `0028` 后 S3/C6/Core2 `67/67` case、`274/274` check，全部 `attempts=1`、`retry_used=false`；Cardputer-ADV 键盘 settle 已加固 | [`dual-guest-fabric-matrix.json`](../tests/uiflow2/evidence-2026-10-24-dual-guest-fabric-matrix.json) |
| 共享 QEMU | ESP32-S3 AES/GDMA 外部内存读取修复；当轮全矩阵 `67/67`、`274/274`，全部首轮无重试 | [`gdma-external-memory-matrix.json`](../tests/uiflow2/evidence-2026-10-24-gdma-external-memory-matrix.json) |
| 固件文件系统 | LittleFS 与只读 FAT12/16/32 文件清单、SHA256、LFN、敏感路径脱敏与 SPDX 提取 | [`fat-inventory.json`](../tests/firmware/evidence-2026-10-24-fat-inventory.json) |
| SPIFFS 文件清单 | 8 个声明配置的自包含多索引样本 PASS；LUT 与 page header 不一致、随机损坏输入均 `INVALID`；ESP-IDF `spiffsgen.py` canonical 镜像和 60000-byte 多索引文件 PASS | [`spiffs-inventory.json`](../tests/firmware/evidence-2026-10-24-spiffs-inventory.json) |
| 固件上传 | 可恢复 chunk artifact upload 的连续 offset、per-chunk/final SHA256、失败回滚、原子 metadata、abort 和 staging GC | [`streaming-artifact-upload.json`](../tests/firmware/evidence-2026-10-24-streaming-artifact-upload.json) |
| WebBurner | 浏览器流式 SHA256、4 MiB 多 chunk、进度/重试/取消、刷新恢复和 package → FirmwareManifest import；9.44 MiB 三 chunk 探针 PASS | [`webburner-ui.json`](../tests/firmware/evidence-2026-10-24-webburner-ui.json) |
| 固件安全配置 | 解析脱敏 `espefuse summary --format json`，区分镜像、sdkconfig、分区 flag 与 eFuse 证据；安全启动/Flash Encryption preflight 按预期拒绝 | [`efuse-security.json`](../tests/firmware/evidence-2026-10-24-efuse-security.json) |
| Core2 稳定性 | 确定性 TCG/icount 下独立启动 `10/10` 首轮 PASS；同 guest board+WiFi+公网+native-VHCI BLE `3/3` | [`native-vhci-pinned.json`](../tests/uiflow2/unified_core2/evidence-2026-10-24-native-vhci-pinned.json) |
| Core2 Device Service | `qemu-unified/profile=core2-native-vhci` 单 lease 返回 frame、QOM、pcap、bridge 和 peer evidence | [`native-vhci-service.json`](../tests/uiflow2/unified_core2/evidence-2026-10-23-native-vhci-service.json) |
| Core2 repeated lease | 同一 GDB 诊断桥 repeated lease 仅 `1/2`，证明该路径不能作为稳定后端 | [`native-vhci-service-stability.json`](../tests/uiflow2/unified_core2/evidence-2026-10-24-native-vhci-service-stability.json) |
| Core2 native-HCI `HCI-1` | QEMU H4 chardev framing、32 packet bounded queue、overflow、peer、clean shutdown 和 QOM counters PASS | [`transport-pass.json`](../tests/uiflow2/core2_native_hci/evidence-2026-10-24-transport-pass.json) |
| Core2 native-HCI `HCI-2` | 不启动 GDB，从真实 VHCI shared memory 捕获 stock HCI Reset `01030c00`；完整命令序列等待 C2H | [`guest-h2c.json`](../tests/uiflow2/core2_native_hci/evidence-2026-10-24-guest-h2c.json) |
| Core2 native-HCI `HCI-3a` | 诊断性单包 C2H：callback status 0，Reset Complete 后 guest 发出下一条 H2C，targeted `5/5`。后续审计不支持把它扩展成产品后端 | [`c2h-delivery.json`](../tests/uiflow2/core2_native_hci/evidence-2026-10-24-c2h-delivery.json) |
| Core2 native-HCI `HCI-3b` | Bumble peer 已发现/连接并完成首个 ATT request/response；第二个 ATT request 后 guest `ack returned 12` 并 Reset，完整 sequence FAIL | [`hci3b-diagnostic.json`](../tests/uiflow2/core2_native_hci/evidence-2026-10-24-hci3b-diagnostic.json) |
| Core2 native-HCI API boundary | GDB return 语义审计确认 pre-entry API hook 不旋转 Xtensa window；实验性 QEMU API hook 完成广播、连接、NUS discovery 和订阅，但 final write/notify transaction 仍超时，实验未保留 | [`hci3b-api-boundary-audit.json`](../tests/uiflow2/core2_native_hci/evidence-2026-10-24-hci3b-api-boundary-audit.json) |
| Core2 HLI queue | 实验写入 firmware `g_rw_schd_queue`/meta queue 并置 `INTSET[29]`；guest ISR/controller task 消费 event-13 marker，QOM 无错误、队列清空。该结果只证明交付 seam，不是 HCI/GATT PASS，实验未保留 | [`hci3b-hli-queue-diagnostic.json`](../tests/uiflow2/core2_native_hci/evidence-2026-10-24-hci3b-hli-queue-diagnostic.json) |
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
