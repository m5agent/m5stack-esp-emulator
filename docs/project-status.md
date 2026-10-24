# 项目当前状态

日期：`2026-10-24`

本文是项目能力的当前快照。代码、生成目录和自动化测试是权威来源；专题文档
负责解释实现和边界，[项目 Backlog](project-backlog.md) 只记录尚未完成的
工作，[代码与验证入口地图](code-map.md) 说明实现和证据位置。
需要按工作流查看交付状态、代码面和下一 Task ID 时，先看
[工作流总台账](workstreams.md)。

## 总览

- 本轮事实快照以 `2026-10-24` 当前代码、生成物和证据 JSON 为准。本地
  平台套件共 `317` 项，`317` 项通过、`0` 项环境相关测试跳过；
  `runtime_coverage`、`peripheral_catalog` 和 `qemu_profiles` 校验通过。
- 本轮文档对账把会随提交变化的测试与矩阵计数集中到本页；README、文档
  导航和工作流台账改为链接。设备 catalog 与 QEMU profile 的验证日期/状态
  已增加交叉校验，AtomS3R 和 PaperMono 的旧 profile 元数据已修正。
- WebBurner 浏览器 SHA256/upload client Node 测试 `2/2 PASS`；真实页面对
  `9.44 MiB`、`3` chunk 的 WebBurner ZIP 完成上传、manifest 导入和刷新恢复。
- 已登记 `14` 台设备：9 台 ESP32-S3、2 台 ESP32-C6、Core2、Tab5 和
  CardputerZero。
- Device Service 可创建 `13` 台设备：12 台 QEMU ESP32 加 Tab5。CardputerZero
  是独立 Linux ARM64 后端，当前不由 `/api/v1` 管理。
- `13` 台设备的登记外设已达到 `simulated`；Tab5 仍为 `partial`。
- S3/C6 已形成 `11` 条设备级 QEMU WiFi 验证路径；Core2 在
  `M5_CORE2_RADIO_QEMU` 环境门控下增加第 `12` 条设备级路径，并细分为
  `core2-unified`、`core2-native-hci` 和 legacy `core2-native-vhci`；
  当前共 `14` 个 unified profile。规范 runtime 为 `qemu-unified`，
  `qemu-ble` 仅为兼容别名。
- 最新完整 UIFlow2 外设矩阵在 `2026-10-24 06:47 +08:00` 完成：
  `67/67` 用例、`274/274` 检查 PASS，包含全部 6 个 Core2 case；每个
  case 都是 `attempts=1`、`retry_used=false`。Core2 使用
  `tcg,thread=single` + deterministic `icount`，RTC 从 boot epoch 起按
  QEMU 虚拟时钟推进。该轮包含 QEMU patch `0028` 的双 guest WiFi
  生命周期；第一轮暴露
  Cardputer-ADV 键盘 6 秒启动窗口竞争，补齐 10 秒等待和 2 秒输入后等待
  后，定向用例和最终全矩阵均通过。
- 当前窄校验：runtime coverage、peripheral catalog 和 QEMU profiles
  均 `PASS`。
- 本地 Device Service worker 已持久化稳定身份、generation、heartbeat、
  active lease、drain/resume 和 abandoned-lease 分类；状态目录由独占锁
  防止双进程接管。另有远程 worker 注册目录，按 identity/generation 防止
  活实例冲突，记录 heartbeat/drain/stop、capability 和有界结果元数据。
  持久 job queue 已支持幂等提交、capability matching、claim/lease、
  heartbeat、超时重试、worker 失联回收和 terminal result；队列不执行
  自身 job。独立 `worker_agent.py` 已能通过公开 API claim job、创建真实
  QEMU session、下载 evidence ZIP/SHA256、停止 session 并提交结果。正在
  运行的本地 QEMU 可在 PID start-time、QMP socket ownership 和
  `query-status=running` 全部匹配后 re-attach；仅恢复 QEMU/QMP 控制面，
  不恢复 companion HTTP/BLE helper 或 evidence 流。启用 API token 时，
  worker-only mutation 使用 worker/generation 派生 HMAC、时间戳和 nonce
  replay cache。服务端可用 PEM 证书/私钥启用 TLS 1.2+，配置 client CA 后
  强制 mTLS；worker client 可加载自定义 CA 与客户端证书。真实 loopback
  进程中已验证 TLS 1.3、服务端证书校验、无客户端证书拒绝、有证书通过、
  Bearer + worker HMAC 保持和明文回退拒绝。服务端与 worker 还通过
  `SIGHUP` 原子切换服务端证书、client CA、worker 客户证书/key 和 master
  token；旧 TLS 身份与旧 token 均被拒绝，新凭据随后完成真实 QEMU job。
  reload 前会停止接纳新请求并等待已进入处理器的请求完成，默认 drain
  timeout 为 30 秒；超时则保留旧配置并恢复接纳。真实 fixture 中一个旧
  token 在途 artifact 上传在轮换期间先返回 `201`，随后才提交新配置。
  `--api-token-previous-file` 和 `--tls-client-ca-previous` 还提供有界
  重叠窗口：第一阶段旧/新 token 均通过 Bearer/HMAC，旧/新客户端 CA 均被
  接受；worker 切到新身份后删除 previous 文件并再次 `SIGHUP`，旧 CA 和
  旧 token 随即失效。自动化客户端批量迁移、跨主机 QEMU job、跨主机
  continuity、生产 secret manager 和多机 scheduler 仍未实现。
- restart reattach 已用真实 StickS3 QEMU 做 live `1/1`：只 SIGKILL 服务
  进程时 QEMU 保持运行，第二代服务在同状态目录中接管同一 PID、重建
  worker lease，并通过 stop 清理 QEMU 进程。
- 双设备网络实验已在 private Linux namespace 内用 QEMU socket L2 switch
  实跑两台 StickS3：两端均完成 DHCP，A 通过 guest TCP 访问 B，双侧 pcap
  都包含双向请求/响应，switch 按配置 MAC 绑定连接槽位；宿主控制面、
  公网 IPv4、metadata 和默认路由不可达。
- Core2 `HCI-4` 已通过：规范的
  `runtime=qemu-unified/profile=core2-native-hci` 在五个独立
  Device Service lease 中同时验证 320×240 frame、27 节点 QOM、WiFi
  DHCP/HTTP、公网 DNS/HTTP、外部 NUS GATT、pcap 和 evidence ZIP；
  `gdb_bridge=false`，五次 frame SHA256 一致。旧 `core2-native-vhci`
  保留为显式 GDB 诊断/兼容 profile。
- Core2 repeated-start/two-minute extended-run 已从 `FAIL` 修到 `PASS`：先恢复 nested guest
  call 前后的 caller-saved Xtensa 特殊寄存器，再把 HLI
  allocator/callback 注入限制在 halted/idle vCPU。中间 sregs-only 构建
  仍为 `4/5`，加入 halt gate 后两批独立 `5×10s` hold 运行合计
  `10/10`；随后 3 个独立 `60s` hold 也 `3/3`，并覆盖 BLE peer 正常
  关闭后的尾态；2 个独立 `120s` hold 进一步 `2/2`，同时覆盖 frame/QOM、
  WiFi、公网 DNS/HTTP、外部 NUS GATT、pcap 和 HLI health。每轮
  `hli-errors=0`、HLI/meta queue 深度为 0。此前
  `semphr_give_wrapper`、`PC=0` 和 `Cache error` 失败证据继续保留。
- Core2 同一 guest 的多轮 BLE 连接（same-guest reconnect）已从 `FAIL`
  修正为 `PASS`。根因不在固件 NimBLE 或 QEMU HLI：外部 Bumble
  compatibility 层错误地为无响应的
  `HCI_Host_Number_of_Completed_Packets (0x0c35)` 发送 Command Status；
  下一条 `LE Set Advertising Data (0x2008)` 消费 stale ACK，导致
  `BLE_HS_ECONTROLLER (12)` 和 reset loop。移除非法响应后，stock 固件在
  3 个独立 `/api/v1` lease 中各自完成 10 轮
  scan/connect/NUS GATT/disconnect；每轮 guest RX、notification、pcap
  和 evidence 全部 PASS。每个 lease 的 HLI 为 `297/297`、events `207`、
  ACLs `90`，HLI errors 和队列深度为 0，connection/L2CAP/GATT 池均回到
  `3/9/3` 空闲基线，`trace-hs-sched-reset=0`。
- 随后将 Device Service、Bumble peer 和 runner 的 `1–10` 硬上限统一扩展到
  `1–30`，并用同一 ELF/QEMU SHA 与重新构建的 unified Core2 镜像运行
  `3` 个独立 lease、每个 `20` 轮 same-guest reconnect。全部 `3/3` PASS；
  每个 lease 的 HLI 为 `577/577`、events `397`、ACLs `180`、HLI errors 和
  队列深度为 0，连接/L2CAP/GATT 池均回到 `3/9/3`，无 panic。该结果关闭
  “超过十轮”缺口，但仍只是 virtual-device 20 轮，不等于多小时 soak。
- 首次 10 轮运行暴露了 Device Service 的独立等待缺陷：peer 已完成 5 轮并
  开始第 6 轮且 guest 未 panic，但 `_wait_hci_probe_result()` 把
  `ready_timeout_seconds` 硬截断为 30 秒，导致 session 被误判失败并终止
  QEMU。修复后等待使用 session ready timeout，并增加超过 30 秒仍可完成的
  回归测试；失败证据和修复后 PASS 证据分别保留。
- 以上全部是虚拟设备证据，物理硬件验证仍为 `NOT RUN`。
- Worker transport 安全证据单独归类为 `transport-security validation`，
  不是跨主机网络拓扑验证。当前 HTTPS/mTLS 运行覆盖同主机 loopback 上的
  真实 TLS 进程、完整 StickS3 flash mTLS 上传、durable job、真实 QEMU
  session、evidence SHA256 和 terminal PASS；另一次
  `qemu-unified/profile=uiflow2-sticks3-unified` job 还从同一 evidence ZIP
  验证 board/WiFi/BLE serial markers、network evidence、pcap 和 PNG frame。
  轮换运行在 A/B 两套临时 PKI 之间原子替换服务端证书、client CA、worker
  客户证书/key 和 master token，验证旧 CA 身份和旧 token 失败，再由新
  凭据完成 signed job。增强运行还持有一个未完成的旧 token artifact 上传，
  确认服务先 drain、请求返回 `201`、之后才 reload。最终运行在 A/B 重叠
  阶段同时接受旧/新 client CA 和 token，再由手工 staged 的 worker 切到
  B；移除 previous 文件后旧 CA/token 被拒绝。该结果不覆盖自动化客户端
  批量迁移、跨主机或真机。

## 能力成熟度

这张表回答“现在到底是什么程度”，避免把协议单测、虚拟整机和服务化混成
一个 PASS。

| 能力面 | 虚拟设备验证 | 本地服务化 | 真机 | 当前结论 |
| --- | --- | --- | --- | --- |
| 板级外设与 UI | 13 台设备达到登记外设的 `simulated`；Tab5 为 `partial` | 13 台可通过 Device Service 创建 | `NOT RUN` | 可做功能回归，不等于物理外设通过 |
| S3/C6/Core2 单实例无线 | 14 个 unified profile、12 条设备级 radio 路径；S3/C6 整机路径 PASS；Core2 `core2-native-hci` 的 `HCI-4`、两批 `5×10s`、3 个 `60s`、2 个 `120s`、2 个 active-BLE `120s` hold 和 3 个各 20 轮的 same-guest GATT lease 均 PASS | `qemu-unified` 可返回 frame/QOM/network/evidence；Core2 不启动 GDB bridge | `NOT RUN` | 已能验证首轮、持续 active BLE 和同 guest 二十轮重连数据面；仍不是完整 RF/PHY、bit-exact BT controller、多小时 soak 或超过二十轮连接 |
| 网络隔离与取证 | namespace、DNS/TLS allowlist、exact IPv4 egress、pcap、断线重连、DHCP renewal、双 guest DHCP/TCP/双侧 pcap PASS | 双设备夹具、本地 worker lifecycle、QEMU/QMP restart re-attach、远程目录、durable lease supervisor、同主机 HTTP executor 和 worker HMAC 已通过契约/真实 job 测试；真实 HTTPS/mTLS、客户端证书、QEMU job、unified StickS3 job over mTLS、SIGHUP TLS/token rotation、active-request drain 和 previous token/CA 有界重叠后 final cutover PASS；自动化客户端批量迁移、跨主机 QEMU job、companion continuity 和 IPv6 未完成 | `NOT RUN` | 传输、认证和同主机 QEMU/unified job 基础已具备，尚不是多租户恶意固件 VM |
| 通用固件审查 | 导入、capability/security preflight、静态审查、LittleFS/FAT/SPIFFS、WebBurner 浏览器流式上传/刷新恢复 PASS；6 台设备 18 个公开非基线样本为 10 PASS / 8 PARTIAL，2 个 runtime model gap 已结构化分类 | 本地 WebBurner 可上传并生成 manifest；生产 key 流程未完成 | `NOT RUN` | 浏览器入口已闭环；C6 软件复位与 Zigbee 两个模型缺口仍 `OPEN`；FW-03 仍需更多设备/firmware family，生产安全未完成 |
| 服务生命周期 | 停止/失败历史可恢复；本地 worker heartbeat/drain/resume；PID+start-time+QMP 校验后的 QEMU/QMP re-attach；durable queue、HMAC-authenticated HTTP executor、HTTPS/mTLS、`SIGHUP` TLS/token 轮换、active-request drain、previous token/CA 有界重叠与 final cutover、worker lease 与失联回收 | 无跨主机 QEMU executor、自动化客户端批量迁移、companion/BLE/evidence 连续接管、warm pool、生产多机调度 | 不适用 | 已有 durable queue、同主机 authenticated executor、TLS/mTLS、drained overlap rotation、local control-plane reattach 和远程 lease 基础，不是完整云端服务 |

## 验证证据

带日期的里程碑、当时检查项和证据链接统一维护在
[验证证据台账](validation-ledger.md)。本页只保留“这些证据加在一起，今天
能得出什么当前结论”，不复制逐条流水。代码路径和复现命令见
[代码与验证入口地图](code-map.md)。

## P0 收口

| 工作 | 已闭合 | 仍开放 |
| --- | --- | --- |
| 网络观测与隔离 | 单 guest WiFi/DHCP/HTTP、pcap、错误密码、radio/AP 丢失恢复；controlled DNS、TLS/Host allowlist；nftables exact IPv4 egress、veth/NAT；DHCP renewal request/ACK；双 guest DHCP/TCP/双侧 pcap/宿主隔离；本地 worker lifecycle、QEMU/QMP reattach、远程目录、durable queue/lease supervisor、同主机 HTTP executor、HMAC worker auth、HTTPS/mTLS、真实 QEMU job、unified StickS3 job over mTLS、`SIGHUP` TLS/token 轮换、活动请求 drain、previous token/CA 有界重叠与 final cutover；GitHub Actions Linux policy CI PASS | 自动化客户端批量迁移、跨主机 QEMU executor/reattach、companion/evidence continuity、生产多机调度、外部 IPv6 |
| Core2 | 确定性 TCG/icount 10/10 首轮、unified WiFi、公网 DNS/HTTP、HCI-offload、stock VHCI、native-HCI `HCI-1` 至 `HCI-4` PASS；两批 `5×10s` `10/10`、3 个 `60s` `3/3`、2 个 `120s` `2/2`；另 2 个 `120s` active-BLE hold `2/2`；3 个独立 lease 各 20 轮的 same-guest GATT `3/3` | `HCI-4`、two-minute virtual extended-run、十轮与二十轮 reconnect 已通过。reconnect 根因是 Bumble 为 HCI Host Completed Packets 返回非法 Command Status；Bumble compatibility 层已修正。Device Service/Bumble peer/runner 的统一 API 上限已扩到 `30`。旧 GDB 路径 `1/2` 只作诊断。剩余是超过二十轮、多小时 soak、bit-exact controller/baseband、物理 cache/PSRAM、coexistence 和真机 |
| 通用固件 | FirmwareManifest、WebBurner/M5Burner/ESP-IDF 导入、浏览器 chunk 上传/刷新恢复、可回滚 artifact backend、sdkconfig/分区 flag/eFuse summary 分层、capability mismatch、脱敏 URL/凭据/高熵审查、SPDX/CycloneDX SBOM、LittleFS/FAT12/16/32/SPIFFS 文件清单/哈希/敏感路径/SPDX 提取、声明级许可 allowlist/denylist；6 台设备 18 个公开非基线样本 10 PASS / 8 PARTIAL，模型缺口与固件故障分开 | 运行时权限、完整源码级许可扫描/法律审批、真机 key/eFuse 流程、更多设备/firmware family 回归；`RUNTIME-01` C6 软件复位和 `RUNTIME-02` Zigbee/802.15.4 仍 `OPEN` |

## 工作流入口

按工作流查看交付状态、代码/证据入口和未完成 Task ID，见
[工作流总台账](workstreams.md)。设备级细节在下文矩阵；真正未完成事项只在
[项目 Backlog](project-backlog.md) 维护。

## 现在可以做什么

### 虚拟设备与 Device Service

- 通过 `/api/v1` 租用、烧录、启动、停止和恢复 13 台设备的历史会话。
- `GET /api/v1/worker` 查看本地 worker heartbeat/lease；`POST /worker/drain`
  停止接纳新会话，`POST /worker/resume` 恢复接纳。
- `GET/POST /api/v1/workers` 管理远程 worker 注册目录；后续
  `/workers/{id}/heartbeat|drain|stop|results` 记录身份绑定的状态和结果
  元数据。该目录不执行任务，也不证明远程 QEMU 已受管。
- `/api/v1/jobs` 提供幂等 job 提交、capability matching、worker claim、
  lease heartbeat、超时重试、cancel 和 terminal result；worker 失联、
  stopped 或 generation 改变时由 supervisor 回收仍 active 的 job。
  该队列不启动 worker，也不接管其活动 QEMU。
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
  UART1 HCI-offload BLE。另有 stock UIFlow2 路径：不重建
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
  peer、pcap 和 manifest。该 profile 的 GDB 仍用于 guest 暂停、
  callback 注入和 synthetic return；同 commit repeated lease 只有 `1/2`，
  因此只保留为显式诊断/兼容路径。新调用应使用 `core2-native-hci`。
  `CORE2-01` 的替代路径已固化为
  [QEMU 内部 native HCI backend](core2-native-hci-backend.md)：host
  transport worker、bounded queue、vCPU-safe HLI C2H commit 和 Git-tracked
  `5/5` lease 门禁均已通过。
  QEMU native-HCI 当前按五个门禁记录：

  | 阶段 | 状态 | 当前边界 |
  | --- | --- | --- |
  | `HCI-1` transport | `PASS` | 分片 ACL、32 packet bounded queue、overflow、peer close、counters 和 clean shutdown |
  | `HCI-2` H2C | `PASS` | 不启动 GDB，真实 stock HCI Reset `01030c00` 和完整 H2C 命令流均已通过 |
  | `HCI-3a` C2H callback | `DIAGNOSTIC PASS` | 真实 Bumble Reset Complete 经 firmware `notify_host_recv` 交付，callback status 0；send-available 后 guest 从 HCI Reset 推进到 Read Local Version，targeted `5/5`。后续审计不支持把它当作产品后端 |
  | `HCI-3b` HLI event | `PASS` | guest `ble_transport_alloc_evt(0)` + event 13 + `ble_transport_to_hs_evt_impl`；真实 Reset Complete 后 `01030c00 → 01011000`，连续 `5/5`，队列清空且无 malformed/dropped |
  | `HCI-3b` complete sequence | `PASS` | `0003` API-boundary H2C + HLI event/ACL，`0004` CCOUNT TB-yield；15-byte probe / 17-byte ATT PDU 完成外部 NUS GATT、Python write/notify 和 Bumble ACK，连续 `5/5` |
  | `HCI-4` stability | `PASS` | `core2-native-hci` 通过五个独立 `/api/v1` lease；每轮同时验证 frame、27 节点 QOM、WiFi/公网、外部 NUS GATT、pcap 和 evidence ZIP，`gdb_bridge=false` |
  | `CORE2-02` extended run | `PASS` | `0005` halt-gated guest call；两批 `5×10s` 为 `10/10`，3 个 `60s` 为 `3/3`，2 个 `120s` 为 `2/2`；每轮 HLI errors/queue depth 为零 |

  `HCI-4` 证据：
  [`hci4-service-5x.json`](../tests/uiflow2/core2_native_hci/evidence-2026-10-24-hci4-service-5x.json)。
  延长运行失败证据：
  [`extended-run-fail.json`](../tests/uiflow2/core2_native_hci/evidence-2026-10-24-extended-run-fail.json)。
  修复后门禁证据：
  [`hci4-halted-gate-5x.json`](../tests/uiflow2/core2_native_hci/evidence-2026-10-24-hci4-halted-gate-5x.json)。
  60 秒 hold 证据：
  [`hci4-hold60-3x.json`](../tests/uiflow2/core2_native_hci/evidence-2026-10-24-hci4-hold60-3x.json)。
  120 秒 hold 证据：
  [`hci4-hold120-2x.json`](../tests/uiflow2/core2_native_hci/evidence-2026-10-24-hci4-hold120-2x.json)。
  Active-BLE 120 秒 hold 证据：
  [`hci4-active-ble-hold120-2x.json`](../tests/uiflow2/core2_native_hci/evidence-2026-10-24-hci4-active-ble-hold120-2x.json)。
  十轮重连证据：
  [`hci4-reconnect10-3x.json`](../tests/uiflow2/core2_native_hci/evidence-2026-10-24-hci4-reconnect10-3x.json)。
  二十轮重连证据：
  [`hci4-reconnect20-3x.json`](../tests/uiflow2/core2_native_hci/evidence-2026-10-24-hci4-reconnect20-3x.json)。
  十轮首次运行的 service timeout 失败证据：
  [`hci4-reconnect10-timeout-fail.json`](../tests/uiflow2/core2_native_hci/evidence-2026-10-24-hci4-reconnect10-timeout-fail.json)。
- 错误密码负向测试要求认证失败、重试、无 DHCP、无 HTTP 和失败 marker
  全部成立；StickS3 link-fault/reconnect 路径同时要求恢复后 DHCP 和
  `/after` HTTP。
- Worker HTTPS/mTLS 真实进程证据：
  [`tls-mtls-pass.json`](../tests/network/worker_tls/evidence-2026-10-24-tls-mtls-pass.json)；
  覆盖 TLS 1.3、服务端证书校验、客户端证书拒绝/通过、Bearer/HMAC 保持、
  unsigned claim `401` 和 worker agent 签名请求生命周期。
- 真实 QEMU job over mTLS：
  [`tls-mtls-qemu-job-pass.json`](../tests/network/worker_tls/evidence-2026-10-24-tls-mtls-qemu-job-pass.json)；
  mTLS 上传完整 StickS3 flash、compose firmware、durable job、真实 QEMU
  session、evidence ZIP/SHA256 和 terminal `completed/PASS` 均成立。
- unified StickS3 job over mTLS：
  [`tls-mtls-unified-job-pass.json`](../tests/network/worker_tls/evidence-2026-10-24-tls-mtls-unified-job-pass.json)；
  board/WiFi/BLE serial markers、network evidence、pcap 和 PNG frame 均从
  同一次 mTLS worker job 的 evidence ZIP 验证。
- SIGHUP TLS/token 轮换与轮换后 QEMU job：
  [`security-rotation-job-pass.json`](../tests/network/worker_tls/evidence-2026-10-24-security-rotation-job-pass.json)；
  A/B PKI 与 master token 原子替换，旧 TLS 身份和旧 token 被拒绝，
  `worker credentials reloaded` 后 signed job 为 `completed/PASS`、
  `attempts=1` 且 evidence SHA256 一致。
- SIGHUP rotation 的活动请求 drain：
  [`security-rotation-drain-job-pass.json`](../tests/network/worker_tls/evidence-2026-10-24-security-rotation-drain-job-pass.json)；
  旧 token 的未完成 artifact upload 在 `SIGHUP` 后先完成并返回 `201`，
  服务随后 reload，再由新凭据完成真实 QEMU job；该 drain 里程碑本身不覆盖
  credential overlap，重叠由下一项验证；跨主机和真机未验。
- SIGHUP rotation 的 bounded overlap 与 final cutover：
  [`security-rotation-overlap-job-pass.json`](../tests/network/worker_tls/evidence-2026-10-24-security-rotation-overlap-job-pass.json)；
  重叠阶段旧/新 client CA 和 token 均有效，worker 切到新身份后移除
  previous 文件并再次 `SIGHUP`，旧 CA/token 最终拒绝，再由新凭据完成
  真实 QEMU job；自动化客户端批量迁移、跨主机和真机未验。
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
- 跨厂商运行时样本已形成 `6` 台 S3/C6 设备、`18` 个热门公开固件快照
  （`8` 个官方、`10` 个社区）：全部完成静态镜像/分区分析和 Device Service
  执行，`10 PASS`、`8 PARTIAL`。两类稳定模型缺口（C6 Zigbee radio 未建模、
  C6 `LP_SW_HPSYS` 软件复位后 chip id 错误）现归为
  `runtime_model_gap`，保留原始 serial/error 证据，不再误报固件 FAIL：
  [`cross-vendor-runtime-model-gaps.json`](../tests/firmware/evidence-2026-10-24-cross-vendor-runtime-model-gaps.json)。
- 上述两个 `runtime_model_gap` 仍为 `OPEN`，“分类正确”不等于“模型已修”。
  `RUNTIME-01` 需要从 C6 ROM/eFuse/复位域语义定位 chip-id 来源；
  `RUNTIME-02` 需要决定 802.15.4/Zigbee controller 是否可维护地建模。缺口、
  已知边界和关闭条件统一维护在
  [运行时模型缺口登记](runtime-model-gap-register.md)。
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
| NanoC6 | ESP32-C6 / QEMU | 无屏控制台、GPIO、RGB、按键、IR、WiFi、BLE 通过 | `qemu-unified` PASS；独立公网探针 PASS | 原生 BT controller、C6 WiFi PHY；Zigbee/802.15.4 `RUNTIME-02` 未建模 |
| Nesso N1 | ESP32-C6 / QEMU | 显示、触摸、扩展 IO、电源、IMU、LoRa、IR、蜂鸣器、WiFi、BLE 通过 | `qemu-unified` PASS；同 guest 公网 DNS/HTTP PASS | stock `hardware.RGB()` 未验、原生 BT controller；`LP_SW_HPSYS` 后 chip-id `RUNTIME-01` |
| Core2 | ESP32 LX6 / QEMU | 显示、触摸、PMIC、IMU、RTC、音频、WiFi、公网 DNS/HTTP、HCI-offload、stock VHCI、QEMU native-HCI 外部 GATT 和同 guest 多轮重连 | `HCI-4` 五 lease、`5×10s` `10/10`、`60s` `3/3`、`120s` `2/2`、active-BLE `120s` `2/2` 与 3 个各 20 轮的 GATT lease 均 PASS；旧 `core2-native-vhci` 仅诊断/兼容 | 超过二十轮、多小时 soak、bit-exact BT controller/baseband、物理 cache/PSRAM、coexistence、真机同路径 |
| Tab5 | ESP32-P4 / esp-emu | 烧录、启动、1280×720、触摸、RS-485、C6 ESP-Hosted、静态 I2C | P4↔C6 end-to-end unified network `NOT RUN` | I2S/PCM、CSI、USB Host、SDIO、动态 I2C、ST7123 controller |
| CardputerZero | BCM2837 / Linux ARM64 | 官方镜像、显示、键盘、I2C、双向 PCM、USB Hub、摄像头、SR9900A 帧回环 | Ethernet 路径，不是 WiFi | 完整系统回归、生产级 USB/时序和真机验证 |

逐项测试依据：

- [QEMU 设备适配矩阵](qemu-device-adaptation-matrix.md)
- [UIFlow2 外设测试矩阵](uiflow2-peripheral-test-matrix.md)
- [验证证据台账](validation-ledger.md)
- [代码与验证入口地图](code-map.md)
- [网络模拟方案](network-simulation-plan.md)
- [网络诊断 lane](network-lane.md)
- [统一设备运行时契约](unified-device-runtime.md)
- [Device Service API](device-service-api.md)

## 当前风险

1. **仿真边界**：QEMU/esp-emu PASS 不等于 RF、功耗、声学、光学或机械真机
   PASS。
2. **Core2 调度、BT 等价性与长稳**：确定性 TCG/icount 已消除当前虚拟启动
   WDT 复现，`HCI-4` 的五个独立 lease 证明功能路径可运行。随后出现的
   READY/联网/BLE 后 panic 已定位到两个 QEMU 注入边界：nested guest call
   未完整恢复 caller-saved sregs，以及在非 halted/cache-safe 上下文执行
   HLI allocator/callback。修复后两批独立 `5×10s` hold 运行 `10/10`，
   3 个 `60s` hold 也 `3/3`，2 个 `120s` hold 为 `2/2`，且 HLI
   health 为零错误。该结果关闭当前 repeated-start/two-minute virtual
   extended-run 故障，但不覆盖 bit-exact controller/baseband、物理
   cache/PSRAM、多小时 coexistence/soak、超过二十轮连接和真机同路径；
   同 guest 二十轮 GATT 已有 3 个独立 lease 的 PASS evidence。第一个 10 轮
   attempt 的失败已确认是 service 30 秒硬上限，不是 guest/controller；
   修复后的失败和 PASS evidence 均保留。旧
   `core2-native-vhci` 的
   `1/2` 只说明 GDB 诊断桥不稳定；`core2-native-hci` 的 hook 偏移仍绑定
   已验证 UIFlow2 v2.5.3 build。
3. **Tab5 闭源后端**：`esp-emu 0.50.0` 缺少若干动态设备与控制面，Tab5 仍是
   `partial`。
4. **网络隔离**：Linux namespace runner 和 guest-inside-namespace 整机路径
   已 PASS；trusted-host 和 Linux private namespace 下的 TLS/Host allowlist
   也已完成测试 CA、HTTPS 握手、200/403 和 pcap 联合验证。nftables 精确
   IPv4 IP/协议/端口、veth/NAT 和清理已 PASS；两台 guest 的 DHCP、TCP、
   双侧 pcap 与宿主隔离也已 PASS。它仍不等同于恶意固件沙箱、生产 worker
  或 RF；本地 worker lifecycle、QEMU/QMP reattach、远程注册目录、durable
  job queue、同主机独立 HTTP executor、HTTPS/mTLS、真实 QEMU job 和
  unified StickS3 job over mTLS 已实现。跨主机
  QEMU executor/reattach、自动化客户端批量迁移、
  companion/evidence continuity、生产 secret manager/多机调度、VM 隔离和
  外部 IPv6 仍待实现。
5. **通用固件兼容性**：SoC 相同不代表板级、分区、安全配置和控制器全部
   兼容。当前 C6 已有两个真实缺口：软件复位后 ROM 读到错误 chip id，以及
   Zigbee/802.15.4 未建模。两者保持 `PARTIAL/runtime_model_gap`，直到有
   真实 QEMU controller/reset 证据关闭；不能通过宿主假值或重试伪装 PASS。
6. **视觉保真**：除 StopWatch 外，设备外壳仍主要是近似模型。

## 文档职责

- `README.md`：入口、当前摘要、快速开始和文档导航。
- `workstreams.md`：按工作流汇总当前交付、代码/证据入口和未完成 Task ID。
- 本文：当前能力与设备状态。
- `docs/project-backlog.md`：只列未完成事项、优先级和依赖。
- `docs/validation-ledger.md`：按日期保存里程碑、检查项和 evidence。
- `docs/code-map.md`：代码入口、验证命令、证据目录和文档维护规则。
- `docs/unified-device-runtime.md`：单 lease/单 guest 的运行时契约。
- `docs/network-*.md`：网络数据面、测试夹具和边界。
- [固件清单与 WebBurner 导入](firmware-manifest.md)：manifest、导入和
  capability mismatch。
- [运行时模型缺口登记](runtime-model-gap-register.md)：已知模拟器能力缺口、
  证据、边界和关闭条件。
- `docs/*-backlog.md`：专项长期缺口。
