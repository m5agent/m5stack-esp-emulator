# 项目当前状态

日期：`2026-10-24`

本文是项目能力的当前快照。代码、生成目录和自动化测试是权威来源；专题文档
负责解释实现和边界，[项目 Backlog](project-backlog.md) 只记录尚未完成的
工作，[代码与验证入口地图](code-map.md) 说明实现和证据位置。
需要按工作流查看交付状态、代码面和下一 Task ID 时，先看
[工作流总台账](workstreams.md)。

## 总览

- 本轮事实快照以 `2026-10-24` 当前代码、生成物和证据 JSON 为准。本地
  平台套件共 `264` 项，`264` 项通过、`0` 项环境相关测试跳过；
  `runtime_coverage`、`peripheral_catalog` 和 `qemu_profiles` 校验通过。
- WebBurner 浏览器 SHA256/upload client Node 测试 `2/2 PASS`；真实页面对
  `9.44 MiB`、`3` chunk 的 WebBurner ZIP 完成上传、manifest 导入和刷新恢复。
- 已登记 `14` 台设备：9 台 ESP32-S3、2 台 ESP32-C6、Core2、Tab5 和
  CardputerZero。
- Device Service 可创建 `13` 台设备：12 台 QEMU ESP32 加 Tab5。CardputerZero
  是独立 Linux ARM64 后端，当前不由 `/api/v1` 管理。
- `13` 台设备的登记外设已达到 `simulated`；Tab5 仍为 `partial`。
- S3/C6 已形成 `11` 条设备级 QEMU WiFi 验证路径；Core2 在
  `M5_CORE2_RADIO_QEMU` 环境门控下提供第 `12` 条 unified profile。规范
  runtime 为 `qemu-unified`，`qemu-ble` 仅为兼容别名。
- 最新完整 UIFlow2 外设矩阵在 `2026-10-24 06:47 +08:00` 完成：
  `67/67` 用例、`274/274` 检查 PASS，包含全部 6 个 Core2 case；每个
  case 都是 `attempts=1`、`retry_used=false`。Core2 使用
  `tcg,thread=single` + deterministic `icount`，RTC 从 boot epoch 起按
  QEMU 虚拟时钟推进。该轮包含双 guest WiFi patch `0028`；第一轮暴露
  Cardputer-ADV 键盘 6 秒启动窗口竞争，补齐 10 秒等待和 2 秒输入后等待
  后，定向用例和最终全矩阵均通过。
- 当前窄校验：runtime coverage、peripheral catalog 和 QEMU profiles
  均 `PASS`。
- 本地 Device Service worker 已持久化稳定身份、generation、heartbeat、
  active lease、drain/resume 和 abandoned-lease 分类；状态目录由独占锁
  防止双进程接管。生产远程注册和活动 QEMU 进程 re-attach 仍未实现。
- 双设备网络实验已在 private Linux namespace 内用 QEMU socket L2 switch
  实跑两台 StickS3：两端均完成 DHCP，A 通过 guest TCP 访问 B，双侧 pcap
  都包含双向请求/响应，switch 按配置 MAC 绑定连接槽位；宿主控制面、
  公网 IPv4、metadata 和默认路由不可达。
- 以上全部是虚拟设备证据，物理硬件验证仍为 `NOT RUN`。

## 能力成熟度

这张表回答“现在到底是什么程度”，避免把协议单测、虚拟整机和服务化混成
一个 PASS。

| 能力面 | 虚拟设备验证 | 本地服务化 | 真机 | 当前结论 |
| --- | --- | --- | --- | --- |
| 板级外设与 UI | 13 台设备达到登记外设的 `simulated`；Tab5 为 `partial` | 13 台可通过 Device Service 创建 | `NOT RUN` | 可做功能回归，不等于物理外设通过 |
| S3/C6/Core2 单实例无线 | 12 个 unified profile；S3/C6 整机路径 PASS，Core2 为环境门控且 GDB/native-HCI 生产化未闭环 | `qemu-unified` 可返回 frame/QOM/network/evidence | `NOT RUN` | 已能验证应用网络与 BLE 数据面，不是完整 RF/PHY |
| 网络隔离与取证 | namespace、DNS/TLS allowlist、exact IPv4 egress、pcap、断线重连、DHCP renewal、双 guest DHCP/TCP/双侧 pcap PASS | 双设备夹具和本地 worker lifecycle control 已通过；远程 worker、活动进程 re-attach 和 IPv6 未完成 | `NOT RUN` | 适合受控审查和回归，尚不是多租户恶意固件 VM |
| 通用固件审查 | 导入、capability/security preflight、静态审查、LittleFS/FAT、WebBurner 浏览器流式上传/刷新恢复 PASS | 本地 WebBurner 可上传并生成 manifest；生产 key 流程未完成 | `NOT RUN` | 浏览器入口已闭环，生产安全和跨厂商覆盖未完成 |
| 服务生命周期 | 停止/失败历史可恢复、容量与 GC 可用；worker heartbeat/drain/resume、租约和重启分类可用 | 活动进程不能跨重启接管，无远程注册、warm pool/多机调度 | 不适用 | 本地 worker 控制面，不是完整云端服务 |

## 最近里程碑

| 日期 | 工作流 | 已交付结果 | 证据入口 |
| --- | --- | --- | --- |
| 2026-10-24 | 网络隔离 | private net/mount namespace、fail-closed、controlled DNS、TLS/Host allowlist、200/403 与 pcap 联合 PASS | [`controlled-dns-pass.json`](../tests/network/tls_allowlist/evidence-2026-10-24-controlled-dns-pass.json) |
| 2026-10-24 | IP/端口 egress | nftables input/output 默认 drop；允许/拒绝端口、允许/拒绝 IP、`1.1.1.1:80` veth/NAT、namespace/NAT 清理 PASS；TLS guest 在同一策略下 PASS | [`ip-port-pass.json`](../tests/network/egress_allowlist/evidence-2026-10-24-ip-port-pass.json) |
| 2026-10-24 | Linux CI | 该证据产生时 GitHub Ubuntu runner 执行 `236` 项平台测试和 fail-closed namespace/egress fixture；允许端点 200、拒绝端口/IP、veth/NAT 与清理全部 PASS。该数字属于历史证据，当前套件规模见上方本轮快照 | [`github-actions-pass.json`](../tests/network/egress_allowlist/evidence-2026-10-24-github-actions-pass.json) |
| 2026-10-24 | AP/radio loss | StickS3 guest 先 DHCP/HTTP；QOM `radio-enabled=false` 后扫描为 0，恢复后扫描为 1，同一 guest 再 DHCP 并完成 `/after` HTTP；pcap 含两组 DORA | [`radio-loss-pass.json`](../tests/network/reconnect_probe/evidence-2026-10-24-radio-loss-pass.json) |
| 2026-10-24 | DHCP renewal | ESP-IDF guest 调用 `netifapi_dhcp_renew()`；pcap 同事务出现初次 DORA 后再接 `REQUEST/ACK`，renewal request/ack 各 1，地址保持并通过 HTTP | [`renewal-pass.json`](../tests/network/idf_dhcp_renewal/evidence-2026-10-24-renewal-pass.json) |
| 2026-10-24 | 双设备 lab fabric | private namespace 内两台 StickS3 完成 DHCP；A→B TCP `19123` 请求/响应成功，两侧 pcap 均有双向 payload hash；宿主、公网、metadata、默认路由不可达，namespace 已清理 | [`two-guest-pass.json`](../tests/network/lab_fabric/evidence-2026-10-24-two-guest-pass.json) |
| 2026-10-24 | 本地 worker lifecycle | 真实 StickS3 `qemu-wifi` lease：心跳、active lease、drain 阻断新租约、活动会话和 pcap 继续、停止后 drained、resume；强杀服务进程组后下一 generation 将旧 lease 标为 abandoned，会话恢复为 interrupted failed | [`worker-lifecycle-pass.json`](../tests/network/worker_lifecycle/evidence-2026-10-24-pass.json) |
| 2026-10-24 | 共享 WiFi + 全矩阵 | patch `0028` 的双 guest WLAN 生命周期进入同一 QEMU build；Cardputer-ADV 键盘 settle 加固后，S3/C6/Core2 `67/67` case、`274/274` check 首轮 PASS，全部 `attempts=1`、`retry_used=false` | [`dual-guest-fabric-matrix.json`](../tests/uiflow2/evidence-2026-10-24-dual-guest-fabric-matrix.json) |
| 2026-10-24 | 共享 QEMU | ESP32-S3 AES/GDMA 外部内存读取修复；当轮全矩阵 `67/67` case、`274/274` check，全部首轮无重试 | [`gdma-external-memory-matrix.json`](../tests/uiflow2/evidence-2026-10-24-gdma-external-memory-matrix.json) |
| 2026-10-24 | 固件审查 | FirmwareManifest 增加 LittleFS 与只读 FAT12/16/32 文件清单、SHA256、LFN、敏感路径脱敏与 SPDX 提取 | [`fat-inventory.json`](../tests/firmware/evidence-2026-10-24-fat-inventory.json) |
| 2026-10-24 | 固件上传 | 可恢复 chunk artifact upload 增加连续 offset、per-chunk/final SHA256、写入失败回滚、原子 metadata、abort 和废弃 staging GC | [`streaming-artifact-upload.json`](../tests/firmware/evidence-2026-10-24-streaming-artifact-upload.json) |
| 2026-10-24 | WebBurner | 浏览器完成流式 SHA256、4 MiB 多 chunk、进度/重试/取消、刷新恢复和 package → FirmwareManifest import；9.44 MiB 三 chunk 探针 PASS | [`webburner-ui.json`](../tests/firmware/evidence-2026-10-24-webburner-ui.json) |
| 2026-10-24 | 固件安全配置 | FirmwareManifest 解析脱敏 `espefuse summary --format json`，区分镜像、sdkconfig、分区 flag 与 eFuse 证据；原始 key/value 不落输出；启用安全启动/加密仍被 capability preflight 拒绝 | [`efuse-security.json`](../tests/firmware/evidence-2026-10-24-efuse-security.json) |
| 2026-10-24 | Core2 | 确定性启动与零重试门禁合入；stock native-VHCI BLE、同 guest board+WiFi+公网+BLE GATT、Device Service 单 lease 证据已归档 | [`native-vhci-service.json`](../tests/uiflow2/unified_core2/evidence-2026-10-23-native-vhci-service.json) |
| 2026-10-24 | Core2 VHCI 符号 | 从匹配 Xtensa ELF 解析 `API_vhci_host_send_packet`、`vhci_env_p`、`esp_cpu_wait_for_intr` 固定地址；standalone BLE `5/5`、同 guest unified `3/3`；GDB 不再负责符号查询，仍负责暂停、callback 注入和 synthetic return | [`native-vhci-pinned.json`](../tests/uiflow2/unified_core2/evidence-2026-10-24-native-vhci-pinned.json) |
| 2026-10-24 | Core2 native HCI `HCI-1` | QEMU `esp32-native-hci` 完成 H4 chardev framing、32 packet bounded queue、overflow/peer/clean shutdown 和 QOM counters，targeted transport test PASS | [`transport-pass.json`](../tests/uiflow2/core2_native_hci/evidence-2026-10-24-transport-pass.json) |
| 2026-10-24 | Core2 native HCI `HCI-2` | 不启动 GDB，从真实 VHCI shared memory 捕获 stock HCI Reset `01030c00`，QOM 与 dummy peer 均记录同一 packet；完整命令序列仍等待 C2H | [`guest-h2c.json`](../tests/uiflow2/core2_native_hci/evidence-2026-10-24-guest-h2c.json) |
| 2026-10-24 | Core2 native HCI `HCI-3a` | 从 ELF 解析 `vhci_env_p` 和 guest `malloc`，按 Xtensa callback ABI 交付 Reset Complete；callback status 为 0，guest 继续发出 Read Local Version，targeted `5/5` | [`c2h-delivery.json`](../tests/uiflow2/core2_native_hci/evidence-2026-10-24-c2h-delivery.json) |
| 2026-10-24 | Core2 native HCI `HCI-3b` | 无 GDB 的 Bumble peer 已发现/连接并完成首个 ATT request/response；第二个 ATT request 后 guest 报 `HCI process ack returned 12` 并发送 HCI Reset，服务发现超时。H4 解析和 callback status 不是故障点，完整 sequence 仍为 `FAIL` | [`hci3b-diagnostic.json`](../tests/uiflow2/core2_native_hci/evidence-2026-10-24-hci3b-diagnostic.json) |
| 2026-10-24 | Core2 callback 路线审计 | 保存/恢复常用 Xtensa caller-saved 特殊寄存器并在任意 CPU0 safe point 注入，仍触发 ack 12 和 `LoadProhibited`；直接 nested 调用真实 `r_eif_send → vhci_send` 触发 `Cache disabled but cached memory region accessed`。两个实验均未保留，补丁 reverse-check 为 `PASS` | [`safe-point-audit.json`](../tests/uiflow2/core2_native_hci/evidence-2026-10-24-hci3b-safe-point-audit.json)、[`controller-entry-audit.json`](../tests/uiflow2/core2_native_hci/evidence-2026-10-24-hci3b-controller-entry-audit.json) |

## P0 收口

| 工作 | 已闭合 | 仍开放 |
| --- | --- | --- |
| 网络观测与隔离 | 单 guest WiFi/DHCP/HTTP、pcap、错误密码、radio/AP 丢失恢复；controlled DNS、TLS/Host allowlist；nftables exact IPv4 egress、veth/NAT；DHCP renewal request/ACK；双 guest DHCP/TCP/双侧 pcap/宿主隔离；本地 worker heartbeat/drain/restart classification；GitHub Actions Linux policy CI PASS | 远程 QEMU worker、活动进程 re-attach、外部 IPv6 |
| Core2 | 确定性 TCG/icount 10/10 首轮、unified WiFi、公网 DNS/HTTP、HCI-offload GATT、stock VHCI BLE 5/5、同 guest native-VHCI 3/3、ELF 固定 VHCI 符号；`HCI-1` PASS、`HCI-2` 首包 PARTIAL、`HCI-3a` 单包 C2H callback `5/5` | 同 commit GDB 诊断桥 repeated lease 仅 `1/2`；无 GDB `run_full.py` 已到广播/连接和首个 ATT 交互，但第二个 ATT request 后 guest `ack returned 12` 并 Reset；任意 safe-point callback 与 nested `r_eif_send` 均已证伪并回退。下一步是实现 C2H device/IRQ queue 或 in-process controller transaction，随后 `HCI-4` Device Service `5/5`、bit-exact controller、物理 cache/PSRAM、RF/coexistence/soak |
| 通用固件 | FirmwareManifest、WebBurner/M5Burner/ESP-IDF 导入、浏览器 chunk 上传/刷新恢复、可回滚 artifact backend、sdkconfig/分区 flag/eFuse summary 分层、capability mismatch、脱敏 URL/凭据/高熵审查、SPDX/CycloneDX SBOM、LittleFS 与 FAT12/16/32 文件清单/哈希/敏感路径/SPDX 提取 | SPIFFS 解包、运行时权限、许可策略、真机 key/eFuse 流程、跨厂商回归 |

## 工程工作流总表

| 工作流 | 当前状态 | 主要代码 | 已验证内容 | 下一道边界 |
| --- | --- | --- | --- | --- |
| 设备与板级契约 | 已完成 | `devices/`、`platform/peripherals/`、`platform/qemu/` | 14 台设备登记；13 台达到登记外设的模拟数据面；catalog、coverage、profile 校验通过 | 新设备逐项登记；视觉保真另列 |
| QEMU/S3/C6 外设 | 当前全矩阵通过 | `patches/`、`tests/uiflow2/` | QEMU patch `0028` 后最新 67/67、274/274，全部首轮无重试；11 条 S3/C6 unified 设备路径；Core2 targeted/native/UI 路径通过 | 新共享控制器变更后重新跑受影响矩阵/全矩阵 |
| Core2 LX6 | 功能路径完成；native-HCI 单包 C2H 已通过，完整 sequence 已有序失败取证 | `patches/qemu-core2-*`、`tests/uiflow2/core2_*` | 10/10 确定性首轮启动、WiFi/公网、HCI-offload、stock VHCI 5/5、同 guest 3/3、ELF 固定符号、Device Service 单 lease PASS；`HCI-1` PASS、`HCI-2` 首包 PARTIAL、`HCI-3a` `5/5`；`HCI-3b` diagnostic FAIL 固定在第二个 ATT request，safe-point/nested-entry 实验已回退 | 实现 guest-visible controller-to-host IRQ/queue 或 in-process controller transaction；随后 `HCI-4` Device Service `5/5`；bit-exact BT、物理 cache/PSRAM 与 soak 另列 |
| Device Service | 本地 v1 + worker lifecycle controller 可用，生产服务化未完成 | `platform/tools/device_service.py`、`serve.py`、`worker_registry.py`、`storage_policy.py`、`platform/web/firmware.*` | lease、worker heartbeat/drain/resume、独占状态目录、generation/abandoned lease、WebBurner/firmware package import、direct/resumable chunk 上传、烧录、frame/serial/input/QOM/audio/network/evidence、存储回收、API 1.14.0 | 远程 worker 注册/调度、活动 QEMU 进程 re-attach、warm pool、多机、VM 隔离和编排模块拆分 |
| FirmwareManifest | v1 + 静态审查 + eFuse 安全摘要 + LittleFS/FAT 清单 + WebBurner browser intake | `firmware_manifest.py`、`firmware_analysis.py`、`firmware_filesystems.py`、`firmware_static_review.py`、`device_service.py`、`platform/web/firmware.*` | merged/segmented/ZIP、WebBurner/M5Burner/flasher_args、8 MiB API chunk、4 MiB browser chunk、browser SHA256/progress/retry/cancel/refresh、failed-append rollback、staging GC、capability mismatch、SBOM、LittleFS/FAT | SPIFFS、运行时权限、许可策略、真机 key/eFuse、跨厂商回归 |
| 网络隔离与取证 | Linux 单机、双 guest lab fabric、本地 worker lifecycle 与 GitHub Actions policy 路径闭环，远程 worker 开放 | `worker_registry.py`、`network_fabric.py`、`network_egress.py`、`network_policy.py`、`network_sandbox.py`、`pcap_summary.py`、reconnect probe | namespace/controlled DNS/TLS、nftables exact IPv4 egress、veth/NAT、DHCP DORA+renew lifecycle、pcap、错误密码、radio/AP 丢失恢复、双 guest DHCP/TCP/双侧 pcap、本地 worker heartbeat/drain/restart classification 和清理 PASS；GitHub Actions Linux job PASS | 远程 QEMU worker、活动进程 re-attach、外部 IPv6 |
| 浏览器与目录 | 可用 | `platform/web/`、`generate_catalog.py`、`peripheral_inventory.py` | 设备目录、会话观察、外设/运行时接口 | warm pool 的前端状态与视觉保真 |
| 物理硬件验证 | `NOT RUN` | Device Test Center 路径 | 当前仅有 virtual-device validation | 代表设备使用同固件 SHA 和同测试计划做实机证据 |

这张表是工作流级摘要，设备级细节在下文矩阵；真正未完成事项只在
[项目 Backlog](project-backlog.md) 维护。

## 现在可以做什么

### 虚拟设备与 Device Service

- 通过 `/api/v1` 租用、烧录、启动、停止和恢复 13 台设备的历史会话。
- `GET /api/v1/worker` 查看本地 worker heartbeat/lease；`POST /worker/drain`
  停止接纳新会话，`POST /worker/resume` 恢复接纳。
- 使用完整 merged 镜像或 bootloader/partition/app/filesystem 分段镜像。
- 采集串口、framebuffer、输入结果、QOM、设备状态、音频 PCM、网络和
  BLE peer evidence。
- 使用 `runtime=qemu-unified` 在单个 QEMU guest 中同时运行板级外设、
  WiFi 和 HCI-offload BLE。
- QEMU radio session 默认通过 `filter-dump` 保留 pcap，并生成 flow、
  DNS、DHCP、ARP、egress scope 和 payload hash 摘要。
- 可通过 `POST /sessions/{id}/network-fault` 对 `wifi0` 执行
  `target=link`，或用 `target=radio` 关闭/恢复 WiFi 模型的
  `radio-enabled` QOM 状态；StickS3 reconnect probe 已验证 scan
  `1→0→1`、两次 DHCP、前后 HTTP 和 pcap。
- `qemu-ble` 保留为兼容别名；新调用应使用 `qemu-unified`。
- 对固件自建 SoftAP 的 provisioning 流程，使用 `runtime=network`、
  `firmware_ap_password` 和 loopback-only `hostfwd` 诊断门户。

### 网络与 BLE

- S3/C6 QEMU 驱动经过真实 guest MMIO、DMA、IRQ、QEMU NIC 和 SLiRP。
- 已验证 scan、association、DHCP、DNS、受控 HTTP；StickS3 和 Nesso N1
  还在同一 guest 中完成 `example.com` 的 IPv4 公网 HTTP。
- 双设备夹具使用 private network namespace 内的 QEMU socket L2 switch；
  两台 StickS3 使用真实 NIC/DHCP/TCP 栈，A 访问 B 的 `19123` 服务并收到
  请求应答。QEMU host 侧另有独立 TAP/bridge primitive，但它不是这次双 guest
  PASS 的运行路径。
- BLE 使用 UIFlow2 HCI-UART 测试构建，经 QEMU UART 到 Bumble controller，
  由外部 Bumble peer 完成 scan/connect/NUS/GATT write/notify。
- Core2 的 Device Service unified profile 仍使用 OpenMAC WiFi 加
  UART1 HCI-offload BLE。另有一个 standalone stock UIFlow2 路径：不重建
  HCI-UART 固件，在 QEMU 的 native ESP32 VHCI host API 边界把 H2C/C2H
  交给 Bumble controller；外部 peer 已完成 scan/connect/NUS subscribe/write
  和 guest notify 回读。独立 BLE runner 连续 5/5 PASS；扩展后的
  `unified_core2` runner 又在同一 guest 中合并 display/touch、音频、
  QOM、WiFi/DHCP、公网 DNS/HTTP 和 native-VHCI BLE，连续 3/3 PASS。
  GDB 不再通过 `parse_and_eval` 查询 VHCI 符号；Device Service 和独立
  runner 都从匹配 ELF 解析固定地址并作为环境变量传入。该路径现已作为
  `runtime=qemu-unified`、
  `profile=core2-native-vhci` 暴露到 Device Service：一个 lease 同时返回
  board/WiFi/公网/frame/QOM/BLE PASS，并从 evidence ZIP 提供 bridge、
  peer、pcap 和 manifest。GDB 仍用于 guest 暂停、callback 注入和
  synthetic return，重复 lease 稳定性尚未形成门禁；也没有执行 bit-exact
  Espressif BT baseband/controller 固件。
  `CORE2-01` 的替代路径已固化为
  [QEMU 内部 native HCI backend](core2-native-hci-backend.md)：host
  transport worker、bounded queue、vCPU-safe C2H commit 和 `5/5` lease
  门禁；在此之前不再把 GDB 桥单次 PASS 写成稳定能力。
  QEMU native-HCI 当前按四个门禁推进：

  | 阶段 | 状态 | 当前边界 |
  | --- | --- | --- |
  | `HCI-1` transport | `PASS` | 分片 ACL、32 packet bounded queue、overflow、peer close、counters 和 clean shutdown |
  | `HCI-2` H2C | `PARTIAL` | 不启动 GDB，已捕获真实 stock HCI Reset `01030c00`；后续 H2C 依赖 controller response |
  | `HCI-3a` C2H callback | `PASS` | 真实 Bumble Reset Complete 经 firmware `notify_host_recv` 交付，callback status 0；send-available 后 guest 从 HCI Reset 推进到 Read Local Version，targeted `5/5` |
  | `HCI-3b` complete sequence | `OPEN` / diagnostic `FAIL` | Bumble 能到广播/连接和首个 ATT request/response；第二个 ATT request 后 ack 12 并 Reset。任意 safe-point callback 与 nested `r_eif_send` 均已证伪并回退，必须改走 device/IRQ queue 或 in-process controller |
  | `HCI-4` stability | `OPEN` | 尚无以 Device Service `/api/v1` 连续 `5/5`、无 GDB callback/synthetic return 的完整 GATT 门禁 |
- 错误密码负向测试要求认证失败、重试、无 DHCP、无 HTTP 和失败 marker
  全部成立；StickS3 link-fault/reconnect 路径同时要求恢复后 DHCP 和
  `/after` HTTP。
- Linux arm64 已用同一 QEMU 源码重建 `qemu-system-xtensa`，在 private
  network namespace 内实跑 StickS3 guest：namespace 内 HTTP PASS、公网
  DNS 查询无响应、pcap 中无 global/slirp-redirect 目标。
- `esp-emu` 的 `user` 网络没有 pcap；pcap 只由 QEMU radio runtime 提供。

网络模型不是完整 RF/PHY。WPA2/WPA3、天线、距离、干扰、功耗和稳定性结论
必须来自真机或后续更完整的无线模型。

### 通用固件

- 输入支持 UIFlow1/UIFlow2、ESP-IDF、Arduino、MicroPython 和兼容的
  merged/segmented flash。
- Device Service 会检查镜像格式、芯片、Flash 大小、地址重叠和基础分区。
- 已提供版本化 FirmwareManifest、WebBurner/M5Burner/`flasher_args.json`
  导入、规范化完整 Flash、provenance/security 记录和结构化 capability
  mismatch；真实公开固件样本已 round-trip。
- `/platform/web/firmware.html` 可直接上传 merged `.bin` 或 WebBurner/
  M5Burner/ESP-IDF 包；浏览器流式计算 SHA256，按 4 MiB chunk 上传，支持
  进度、瞬态重试、取消和刷新恢复，完成后调用同一 Manifest importer。
- 已提供公开社区固件抓取、热门固件批量仿真、结构分析、脱敏静态审查和
  SPDX/CycloneDX SBOM 摘要。manifest 不保存 URL query、凭据或编码载荷明文。
- 任意固件仍受板型、PSRAM、eFuse/安全启动、Flash 加密、分区和控制器覆盖
  约束；不支持时必须以结构化能力缺口返回，不能伪装成固件失败或 PASS。

## 设备矩阵

| 设备 | SoC / 后端 | 当前能力 | 网络状态 | 主要剩余缺口 |
| --- | --- | --- | --- | --- |
| StopWatch | ESP32-S3 / QEMU | 466×466 显示、触摸、电源、IMU、音频、振动和外设矩阵通过 | `qemu-unified` PASS | 高保真外观、真机与 RF 未验 |
| StickS3 | ESP32-S3 / QEMU | 显示、按键、电源、IMU、音频、IR 和外设矩阵通过 | `qemu-unified` PASS；同 guest 公网 DNS/HTTP PASS | 真机与 RF 未验 |
| CoreS3 | ESP32-S3 / QEMU | 显示、触摸、电源、IMU、音频、摄像头和 USB Host 数据面通过 | `qemu-unified` PASS | 启动菜单透明/调色板图像仍有模拟条纹 |
| AtomS3R | ESP32-S3 / QEMU | 显示、按键、IMU、磁力计、RGB、IR 通过 | `qemu-unified` PASS | 高保真外观与真机 |
| Cardputer-ADV | ESP32-S3 / QEMU | 显示、键盘、IMU、音频、SD、NFC、CC1101、IR 通过 | `qemu-unified` PASS | 高保真外观与真机 |
| PaperColor | ESP32-S3 / QEMU | Spectra 6、按键、电源、SHT4X、音频、SD、RGB、IR 通过 | `qemu-unified` PASS | 刷新时序与真机光学表现 |
| PaperMono | ESP32-S3 / QEMU | 灰度屏、触摸、电源、IMU、RTC、音频、NFC、LoRa、RGB 通过 | `qemu-unified` PASS | 刷新手感与真机显示表现 |
| StackChan | ESP32-S3 / QEMU | 显示、触摸、摄像头、环境/运动传感器、音频、NFC、IR、双舵机通过 | `qemu-unified` PASS | 机械运动、声学和相机光学 |
| StamPLC | ESP32-S3 / QEMU | 显示、按键、继电器/输入、CAN、RS-485、温度、蜂鸣器通过 | `qemu-unified` PASS | 工业电气特性和真机 |
| NanoC6 | ESP32-C6 / QEMU | 无屏控制台、GPIO、RGB、按键、IR、WiFi、BLE 通过 | `qemu-unified` PASS；独立公网探针 PASS | 原生 BT controller 与 C6 WiFi PHY |
| Nesso N1 | ESP32-C6 / QEMU | 显示、触摸、扩展 IO、电源、IMU、LoRa、IR、蜂鸣器、WiFi、BLE 通过 | `qemu-unified` PASS；同 guest 公网 DNS/HTTP PASS | stock `hardware.RGB()` 未验、原生 BT controller |
| Core2 | ESP32 LX6 / QEMU | 显示、触摸、PMIC、IMU、RTC、扬声器、麦克风、WiFi、公网 DNS/HTTP、HCI-offload BLE、stock native-VHCI BLE GATT、ELF 固定 VHCI 符号 | `core2-unified` 与 `core2-native-vhci` Device Service 单 lease PASS；native-VHCI BLE 5/5；同 guest 3/3 | 移除 GDB 暂停/注入/return 控制面、重复 lease 稳定门禁、bit-exact BT controller、物理 cache/PSRAM 等价性 |
| Tab5 | ESP32-P4 / esp-emu | 烧录、启动、1280×720、触摸、RS-485、C6 ESP-Hosted、静态 I2C | P4↔C6 end-to-end unified network `NOT RUN` | I2S/PCM、CSI、USB Host、SDIO、动态 I2C、ST7123 controller |
| CardputerZero | BCM2837 / Linux ARM64 | 官方镜像、显示、键盘、I2C、双向 PCM、USB Hub、摄像头、SR9900A 帧回环 | Ethernet 路径，不是 WiFi | 完整系统回归、生产级 USB/时序和真机验证 |

逐项测试依据：

- [QEMU 设备适配矩阵](qemu-device-adaptation-matrix.md)
- [UIFlow2 外设测试矩阵](uiflow2-peripheral-test-matrix.md)
- [代码与验证入口地图](code-map.md)
- Core2 10-run evidence:
  [`tests/uiflow2/unified_core2/evidence-2026-10-23-icount-public.json`](../tests/uiflow2/unified_core2/evidence-2026-10-23-icount-public.json)
- Core2 native-VHCI GATT evidence:
  [`tests/uiflow2/core2_native_vhci/evidence-2026-10-23-vhci.json`](../tests/uiflow2/core2_native_vhci/evidence-2026-10-23-vhci.json)
- Core2 same-guest unified native-VHCI evidence:
  [`tests/uiflow2/unified_core2/evidence-2026-10-23-native-vhci.json`](../tests/uiflow2/unified_core2/evidence-2026-10-23-native-vhci.json)
- Core2 pinned-symbol standalone native-VHCI evidence:
  [`tests/uiflow2/core2_native_vhci/evidence-2026-10-24-symbol-pinned.json`](../tests/uiflow2/core2_native_vhci/evidence-2026-10-24-symbol-pinned.json)
- Core2 pinned-symbol same-guest unified evidence:
  [`tests/uiflow2/unified_core2/evidence-2026-10-24-native-vhci-pinned.json`](../tests/uiflow2/unified_core2/evidence-2026-10-24-native-vhci-pinned.json)
- Core2 repeated Device Service stability failure:
  [`tests/uiflow2/unified_core2/evidence-2026-10-24-native-vhci-service-stability.json`](../tests/uiflow2/unified_core2/evidence-2026-10-24-native-vhci-service-stability.json)
- Core2 Device Service native-VHCI evidence:
  [`tests/uiflow2/unified_core2/evidence-2026-10-23-native-vhci-service.json`](../tests/uiflow2/unified_core2/evidence-2026-10-23-native-vhci-service.json)
- GDMA external-memory fix + patch 0027 full-matrix evidence:
  [`tests/uiflow2/evidence-2026-10-24-gdma-external-memory-matrix.json`](../tests/uiflow2/evidence-2026-10-24-gdma-external-memory-matrix.json)
- Dual-guest WiFi patch + latest full matrix evidence:
  [`tests/uiflow2/evidence-2026-10-24-dual-guest-fabric-matrix.json`](../tests/uiflow2/evidence-2026-10-24-dual-guest-fabric-matrix.json)
- TLS/Host allowlist pass evidence:
  [`tests/network/tls_allowlist/evidence-2026-10-23-pass.json`](../tests/network/tls_allowlist/evidence-2026-10-23-pass.json)
- Linux namespace TLS/Host allowlist evidence:
  [`tests/network/tls_allowlist/evidence-2026-10-24-linux-namespace-pass.json`](../tests/network/tls_allowlist/evidence-2026-10-24-linux-namespace-pass.json)
- Controlled DNS + TLS/Host allowlist evidence:
  [`tests/network/tls_allowlist/evidence-2026-10-24-controlled-dns-pass.json`](../tests/network/tls_allowlist/evidence-2026-10-24-controlled-dns-pass.json)
- Exact IP/port, public NAT and cleanup evidence:
  [`tests/network/egress_allowlist/evidence-2026-10-24-ip-port-pass.json`](../tests/network/egress_allowlist/evidence-2026-10-24-ip-port-pass.json)
- GitHub Actions Linux namespace/egress evidence:
  [`tests/network/egress_allowlist/evidence-2026-10-24-github-actions-pass.json`](../tests/network/egress_allowlist/evidence-2026-10-24-github-actions-pass.json)
- Two-guest private QEMU lab fabric:
  [`tests/network/lab_fabric/evidence-2026-10-24-two-guest-pass.json`](../tests/network/lab_fabric/evidence-2026-10-24-two-guest-pass.json)
- Local worker drain/restart lifecycle:
  [`tests/network/worker_lifecycle/evidence-2026-10-24-pass.json`](../tests/network/worker_lifecycle/evidence-2026-10-24-pass.json)
- StickS3 TLS under nftables IP/port policy:
  [`tests/network/tls_allowlist/evidence-2026-10-24-ip-port-nftables-pass.json`](../tests/network/tls_allowlist/evidence-2026-10-24-ip-port-nftables-pass.json)
- DHCP renewal through Device Service:
  [`tests/network/idf_dhcp_renewal/evidence-2026-10-24-renewal-pass.json`](../tests/network/idf_dhcp_renewal/evidence-2026-10-24-renewal-pass.json)
- Virtual WiFi radio/AP loss and same-guest recovery:
  [`tests/network/reconnect_probe/evidence-2026-10-24-radio-loss-pass.json`](../tests/network/reconnect_probe/evidence-2026-10-24-radio-loss-pass.json)
- Firmware redacted static review evidence:
  [`tests/firmware/evidence-2026-10-23-static-review.json`](../tests/firmware/evidence-2026-10-23-static-review.json)
- LittleFS inventory evidence:
  [`tests/firmware/evidence-2026-10-24-filesystem-inventory.json`](../tests/firmware/evidence-2026-10-24-filesystem-inventory.json)
- FAT12/16/32 inventory and real-sample evidence:
  [`tests/firmware/evidence-2026-10-24-fat-inventory.json`](../tests/firmware/evidence-2026-10-24-fat-inventory.json)
- Resumable artifact upload, rollback and staging GC:
  [`tests/firmware/evidence-2026-10-24-streaming-artifact-upload.json`](../tests/firmware/evidence-2026-10-24-streaming-artifact-upload.json)
- WebBurner browser upload, refresh recovery and cancel:
  [`tests/firmware/evidence-2026-10-24-webburner-ui.json`](../tests/firmware/evidence-2026-10-24-webburner-ui.json)
- Linux guest-in-namespace evidence:
  [`tests/network/linux_isolation/evidence-2026-10-23-linux.json`](../tests/network/linux_isolation/evidence-2026-10-23-linux.json)
- [网络模拟方案](network-simulation-plan.md)
- [网络诊断 lane](network-lane.md)
- [统一设备运行时契约](unified-device-runtime.md)
- [Device Service API](device-service-api.md)

## 当前风险

1. **仿真边界**：QEMU/esp-emu PASS 不等于 RF、功耗、声学、光学或机械真机
   PASS。
2. **Core2 调度与 BT 等价性**：确定性 TCG/icount 已消除当前虚拟启动 WDT
   复现；native-VHCI 已在同一 guest 与 WiFi/公网/board 合并 3/3，并进入
   Device Service。VHCI 符号已经固定，但 GDB 仍控制暂停、callback 注入
   和 synthetic return。QEMU 内部 relay 已完成 transport、首个 H2C 和
   单包 C2H callback；完整 sequence 的失败证据也排除了任意 safe-point
   回调与 nested guest RPC。下一步必须建立 guest-visible controller
   IRQ/queue 或 in-process controller transaction。该路径不是无调试器的
   生产模型，也不等于 bit-exact Espressif BT controller 或物理
   cache/PSRAM 时序。
3. **Tab5 闭源后端**：`esp-emu 0.50.0` 缺少若干动态设备与控制面，Tab5 仍是
   `partial`。
4. **网络隔离**：Linux namespace runner 和 guest-inside-namespace 整机路径
   已 PASS；trusted-host 和 Linux private namespace 下的 TLS/Host allowlist
   也已完成测试 CA、HTTPS 握手、200/403 和 pcap 联合验证。nftables 精确
   IPv4 IP/协议/端口、veth/NAT 和清理已 PASS；两台 guest 的 DHCP、TCP、
   双侧 pcap 与宿主隔离也已 PASS。它仍不等同于恶意固件沙箱、生产 worker
   或 RF；本地 worker heartbeat/drain 已实现，活动进程 re-attach、远程调度、
   VM 隔离和外部 IPv6 仍待实现。
5. **通用固件兼容性**：SoC 相同不代表板级、分区、安全配置和控制器全部
   兼容。
6. **视觉保真**：除 StopWatch 外，设备外壳仍主要是近似模型。

## 文档职责

- `README.md`：入口、当前摘要、快速开始和文档导航。
- `workstreams.md`：按工作流汇总当前交付、代码/证据入口和未完成 Task ID。
- 本文：当前能力与设备状态。
- `docs/project-backlog.md`：只列未完成事项、优先级和依赖。
- `docs/code-map.md`：代码入口、验证命令、证据目录和文档维护规则。
- `docs/unified-device-runtime.md`：单 lease/单 guest 的运行时契约。
- `docs/network-*.md`：网络数据面、测试夹具和边界。
- [固件清单与 WebBurner 导入](firmware-manifest.md)：manifest、导入和
  capability mismatch。
- `docs/*-backlog.md`：专项长期缺口。
