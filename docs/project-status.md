# 项目当前状态

日期：`2026-10-25`

本文是项目能力的当前快照。代码、生成目录和自动化测试是权威来源；专题文档
负责解释实现和边界，[项目 Backlog](project-backlog.md) 只记录尚未完成的
工作，[代码与验证入口地图](code-map.md) 说明实现和证据位置。
需要按工作流查看交付状态、代码面和下一 Task ID 时，先看
[工作流总台账](workstreams.md)。

需要一页快速了解代码阅读顺序、成熟度和下一步，先看
[工程交接总览](engineering-handoff.md)。本页继续作为详细能力结论的权威入口；
逐次运行轮次、PASS/FAIL 和 evidence 只追加到
[验证证据台账](validation-ledger.md)，不在这里重复维护历史流水。

## 一页交接

当前项目已经不是“只能跑 reference 固件”的早期阶段：设备 Service、单 guest
unified runtime、受控网络、BLE peer、固件 Manifest/WebBurner、worker queue、
HTTPS/mTLS 和多种重启恢复路径都已有可执行实现。现阶段的主线是补齐生产
生命周期边界，而不是重写主运行链路。

- **最近已闭合**：authenticated multicast discovery（`658b2d4`）、
  HMAC-authenticated unicast seed discovery 跨两个独立 subnet/NAT
  （`3/3 PASS`）、worker→control network blackhole 下的 bounded heartbeat、
  runtime DELETE、process reap、lease expiry/requeue 和 retry（`3/3 PASS`）、central
  control-plane 重启后原 lease/evidence 收敛（`f85b8c9`）、runtime Device
  Service 重启后同 PID/QMP reattach（`cd3adc7`）、`POST /sessions`
  并发/重启幂等（`0e3a913`），以及 trusted-host unified HTTP/BLE
  companion continuity（当前实现与 evidence 见下文）。网络策略还闭合了
  有界 IPv4/IPv6 CIDR、显式绑定 controlled domain suffix 与有界 CNAME
  chain；Linux namespace policy fixture 通过，CNAME resolver 数据面也已
  通过。同一 guest 的三独立 lease 又完成 CNAME→terminal A→HTTP 200，
  拒绝域名与拒绝端口同时 PASS，并保留 DNS/HTTP/pcap/cleanup 证据。
  三个独立 Docker 容器对也完成了 central 跨 bridge 控制、worker-local
  runtime/QEMU、terminal evidence 和容器/网络清理。
- **当前已闭合的 companion 门禁**：trusted-host unified StickS3 在 runtime
  service SIGKILL 后保持同一 QEMU PID；HTTP fixture 从持久 generation-1
  请求重建为 generation-2，BLE peer 在 PID/start-time/command-SHA 全部匹配后
  adopt，并完成重启后的第二轮 GATT 和 guest HTTP recheck。相同 lease 的
  evidence ZIP 同时包含两代 HTTP、BLE continuity、serial、network/pcap 和
  cleanup。
- **下一 P0**：`NET-04` 的真实跨主机 executor/reattach、跨主机 idempotency、
  无 reachable seed 时的任意 NAT traversal、QEMU 内 guest/device-controller side-effect
  fencing 和生产调度；namespace-managed/Tab5/cross-host
  companion recovery；`FW-01/02/03` 的运行态 ACL/许可、真机
  security/key 流程和更多固件族；`RUNTIME-02/03/04` 的 C6 Zigbee、Core2
  legacy I2C 与 ATECC608；以及 `HW-01` 同固件 SHA 真机验证。
- **不再误列为待办**：Manifest、WebBurner chunk upload、SHA-bound
  UI/headless/network-first expectation、SD/NVS fixture、有界 IPv4/IPv6
  地址/CIDR、显式绑定 domain suffix、有界 CNAME resolver 与同 guest
  CNAME→HTTP 生命周期、S3 WPA2-PSK pair key、worker
  TLS/mTLS/rotation/drain、cross-container worker-local QEMU、同主机
  QEMU/QMP reattach、trusted-host unified companion continuity、
  cross-subnet/NAT unicast seed discovery 和 Core2
  `3×121` reconnect 均已有实现与 evidence；它们剩余的是更窄的边界，不是
  “尚未开发”。
- **当前仍然失真的旧说法**：把 WebBurner、FAT/SPIFFS、DHCP renewal、
  TLS allowlist、worker rotation、Core2 native-HCI、121-round reconnect 或
  session idempotency、或“没有 multicast 就无法跨子网发现”写成 TODO，
  均属于过期信息；动态数量以自动快照为
  准，能力结论以本页为准。

设备本地 README、测试 case README 和早期设计页保留当时语境，不应单独用来
判断今天是否支持某项能力。测试总入口见 [`tests/README.md`](../tests/README.md)，
补丁总入口见 [`patches/README.md`](../patches/README.md)。

## 总览

- 本轮事实快照以 `2026-10-25` 当前代码、生成物和证据 JSON 为准。平台
  套件总数、设备/后端/外设/样本数量统一从
  [自动项目快照](project-snapshot.md)读取；本轮
  `runtime_coverage`、`peripheral_catalog`、`qemu_profiles` 和项目快照
  校验通过。
- 设备、Backlog Task 和固件样本的动态计数已改由
  [`project_snapshot.py`](../platform/tools/project_snapshot.py)从 catalog、
  profile、evidence 和 Backlog 生成到
  [自动项目快照](project-snapshot.md)；README、工作流页、统一运行时契约和
  网络方案不再复制逐轮 PASS 计数。
- 当前状态页不再复制会随提交变化的测试、设备和 profile 数量；README、
  文档导航、工作流台账和本页统一链接自动快照。设备 catalog 与 QEMU
  profile 的验证日期/状态仍有交叉校验。
- WebBurner 浏览器 SHA256/upload client Node 测试 `2/2 PASS`；真实页面对
  `9.44 MiB`、`3` chunk 的 WebBurner ZIP 完成上传、manifest 导入和刷新恢复。
  WebBurner 现在还可在导入前声明 required/optional capabilities；API 与
  client 对别名、去重、64 项上限和非法输入做同一契约检查，StickS3 声明
  `camera` 会在 manifest 阶段结构化拒绝，而不是生成空能力声明。
  包内 `sdkconfig` 的 WiFi/Bluetooth/PSRAM 高置信构建开关另记为
  `capabilities.detected`；目标 profile 缺失时只产生 warning，不会把编译
  开关误升级为“应用实际使用外设”的硬拒绝。没有 sdkconfig 时，
  白名单镜像 token 会写入独立的 `capabilities.observed`，以低置信度
  review warning 标出 declared/observed 偏差；WebBurner 分开展示
  `SDKConfig capabilities`、`Image observations`、`Image scan` 和 warning
  code。观察结果不替代运行态证据。
- WebBurner `parts[]` 的可选 `size`、SHA-256、SHA-1、MD5 或等价
  `integrity` 声明会在规范化前流式复算。size/digest mismatch、非法
  digest、冲突重复声明和未知 integrity 字段均结构化拒绝；成功 segment
  只记录 `status=verified`、算法集合和是否包含弱摘要，不复制源包，也不
  把摘要校验写成发布者认证或签名验证。
- Device Service 新增 session-isolated NVS partition fixture：服务解析
  固件分区表，要求 fixture 大小严格等于 NVS 分区，只修改 session Flash
  副本，并同时记录 base/effective Flash SHA。`nvs_image.py` 可确定性生成
  NVS namespace/string 数据，编码与 ESP-IDF NVS generator 逐字节一致。
  公开 OpenAI Voice Assistant BIN 的 NVS 分区为全 `FF`；注入合成
  `config` 数据后，guest 在 Open 与 WPA2-PSK 两种 AP 下都完成关联、DHCP，
  解析 `api.openai.com` 并发起 TCP/443。WPA2 对照完成 M1-M4 和成对密钥
  CCMP RX；错误密码在 M2 MIC 被拒绝、deauthenticate 后重试且无 DHCP。
- 设备登记、Device Service 可创建数量、外设完成度和 unified profile
  数量统一见 [自动项目快照](project-snapshot.md)。CardputerZero 是独立
  Linux ARM64 后端，当前不由 `/api/v1` 管理；规范 runtime 为
  `qemu-unified`，`qemu-ble` 仅为兼容别名。
- 最新完整 UIFlow2 外设矩阵在 `2026-10-24 06:47 +08:00` 完成：
  `67/67` 用例、`274/274` 检查 PASS，包含全部 6 个 Core2 case；每个
  case 都是 `attempts=1`、`retry_used=false`。Core2 使用
  `tcg,thread=single,tb-size=128` + deterministic `icount`，RTC 从 boot epoch 起按
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
  `query-status=running` 全部匹配后 re-attach。trusted-host unified session
  还会持久化 companion ownership：HTTP fixture 按 generation 重建并加载
  历史请求，BLE peer 仅在 PID/start-time/完整 command SHA256 匹配时 adopt；
  namespace-managed、Tab5 和 cross-host companion 仍不支持。启用 API token 时，
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
  旧 token 随即失效。同主机双 worker 还通过不可变 generation 目录和单个
  原子 pointer 自动迁移：worker 在下一请求读取一致的 token/CA/client
  key 集合，并写出 secret-free receipt；无需逐个发送 worker `SIGHUP`。
  Device Service 还可广播 active-token HMAC 签名的 IPv4 multicast beacon，
  真实 `worker_agent.py --discover-control` 已在不硬编码 control URL 的
  情况下发现并注册；错误/旧 token 被拒绝，SIGHUP rotation 后新 token
  可重新发现。无法接收 multicast 的跨子网/NAT worker 可从独立
  `worker_discovery_seed.py` 取同一 signed beacon；两个 subnet、IPv4
  forwarding、masquerade、错误/旧 token、rotation 和 cleanup 已在
  privileged Linux Docker fixture 中连续 `3/3 PASS`。独立
  control/runtime 服务 fixture 还证明 central 同 state
  重启 2.2 秒后，worker 重新注册并以原 identity/generation 和 lease
  提交 evidence PASS；runtime Device Service 同 state 重启后也会按
  PID start-time、QMP ownership 和 running 状态重新接管原 QEMU。无
  reachable seed 的任意 NAT traversal、跨主机 QEMU job/continuity、生产 secret manager 和多机
  scheduler 仍未实现。
- restart reattach 已用真实 StickS3 QEMU 做 live `1/1`：只 SIGKILL 服务
  进程时 QEMU 保持运行，第二代服务在同状态目录中接管同一 PID、重建
  worker lease，并通过 stop 清理 QEMU 进程。unified companion fixture
  进一步在重启后验证 HTTP generation-1→2、同 BLE peer GATT cycle 2、
  guest HTTP recheck、原 job/lease PASS 和 QEMU/companion 清理。
- 双设备网络实验已在 private Linux namespace 内用 QEMU socket L2 switch
  实跑两台 StickS3：两端均完成 DHCP，A 通过 guest TCP 访问 B，双侧 pcap
  都包含双向请求/响应，switch 按配置 MAC 绑定连接槽位；宿主控制面、
  公网 IPv4、metadata 和默认路由不可达。
- `NET-05` 的 exact IPv6 egress 已接入同一 fail-closed nftables 路径：
  `inet` 表同时生成 IPv4/IPv6 精确目的地址/协议/端口规则，IPv6 veth
  使用独立 ULA /126、default route、neighbor solicitation/advertisement
  控制例外和 masquerade。Linux worker→upstream 夹具连续 `2/2 PASS`，
  上游观察到的是 worker veth 源地址，内层 NAT table、inner/worker/upstream
  namespaces 均已清理；同一 source commit 的 GitHub Actions
  `network-namespace-policy` job 再次 PASS。该结果只覆盖虚拟网络策略，
  不是固件 guest 或公网 IPv6 可用性。controlled resolver 现已支持 exact
  A/AAAA records，且 Device Service 对 IPv6 endpoint 预检
  `require_ipv6`。专用 UIFlow2 StickS3 测试构建已在同一 guest 中完成
  IPv6 TCP 和 HTTP，pcap 记录 `fec0::2:18095` 双向流；原厂 UIFlow2 未启用
  IPv6 link-local，属于固件配置边界。Linux arm64 private namespace 中的
  同一 guest 现已完成 controlled AAAA、IPv6 HTTP、denied-port、pcap、
  namespace cleanup 和 QEMU reap。网络策略现已接受有界 IPv4 `/16+`、
  IPv6 `/48+` CIDR，并支持 controlled DNS domain suffix 与最多 8 跳的
  CNAME chain；每个 suffix/alias 必须受 policy 覆盖，terminal answer
  必须落在允许 endpoint 地址/CIDR 内。Host 匹配只在 DNS label boundary
  生效，域名和 CNAME 都不会授权外部 resolver 返回的任意地址。
- Core2 `HCI-4` 已通过：规范的
  `runtime=qemu-unified/profile=core2-native-hci` 在五个独立
  Device Service lease 中同时验证 320×240 frame、27 节点 QOM、WiFi
  DHCP/HTTP、公网 DNS/HTTP、外部 NUS GATT、pcap 和 evidence ZIP；
  `gdb_bridge=false`，五次 frame SHA256 一致。旧 `core2-native-vhci`
  保留为显式 GDB 诊断/兼容 profile。
- Core2 unified guest 的 PSRAM 稳定性路径已通过：QOM PSRAM device 为
  `8 MiB`，普通 DRAM1 heap 保持 4 MiB 直接映射窗口；3 个独立 artifact-bound
  lease 各运行 120 秒，都从该 4 MiB heap 分配 `1 MiB`
  bytearray，并在 4096-byte 块地址标记/数据模式上完成 35、35、35 次
  全缓冲读回校验，累计 `105 MiB`。每轮同时执行 10 次受控 HTTP recheck、
  3–4 次公网 DNS/HTTP recheck，并保持 active BLE、frame/QOM、pcap、evidence
  和 cleanup PASS；pcap 分别包含 222、205、211 个包，识别到 DHCP DORA、
  `example.com` DNS 和持续 TCP。另一次单 lease 600 秒 soak 又完成 179 次
  `1 MiB` 校验、51 次受控 HTTP 和 18 次公网 recheck；pcap 为 912 包/208
  flows。每轮外部堆空闲量下降 `2,228,232 B`，因此
  不只证明“QOM 里有 PSRAM 节点”。另 3 个独立 `esp_himem` lease 通过
  DRAM1 MMU 在同一个虚拟窗口切换不同 upper-bank 物理块，QOM 8 MiB 和
  reserved MMU 256 KiB 均成立并读回 PASS。物理 cache/PSRAM 时序和真机
  验证仍 `NOT RUN`。
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
  `3` 个独立 `/api/v1` lease 中分别完成 20、30、60、120 轮
  scan/connect/NUS GATT/disconnect，四个门禁均为 `3/3 PASS`。120 轮
  每 lease HLI `3377/3377`、events `2297`、ACLs `1080`，HLI errors、
  HLI/meta/TX queue、dropped 和 panic 均为 0，connection/L2CAP/GATT 池回到
  `3/9/3`，三次 frame SHA256 一致。
- Core2 的 hash-freeze runner 已完成 artifact-bound `7200s` active-BLE
  WiFi/公网/GATT 功能保持：首 lease 前冻结 firmware、ELF、QEMU，运行期
  `input_asset_drift={}`；session 全程 running，frame、pcap、BLE peer 和
  HLI health 正常，结束时 HLI `45/45`、events `36`、ACLs `9`，
  errors/queue/dropped/peer-close 均为 0，无 panic，清理成功。该轮功能
  结果为 `PASS`。同一次运行采样 QEMU host RSS 从 `744160 KiB` 增至
  `1202176 KiB`（`+458016 KiB`）；后续用 macOS `vmmap` 把增长定位到
  QEMU TCG translation buffer `VM_ALLOCATE`，而不是 guest PSRAM；默认
  `tb-size` 最多可预留 `1 GiB`。
- 统一 Core2 accelerator 已改为
  `tcg,thread=single,tb-size=128`。同一固件的 120 秒 active-BLE 功能复测
  全 PASS，RSS `323600→323584 KiB`、phys footprint
  `214016→196608 KiB`，HLI `45/45`。最终 artifact-bound `7200s` 复测也已
  PASS：1/1 lease、`bounded_tcg_cache`、frame/QOM、WiFi/公网、active-BLE
  GATT、pcap、HLI `45/45`、active peer 和 cleanup 全部成立；240 个资源采样
  的 RSS 为 `323536→252992 KiB`，phys footprint 为
  `250880→188416 KiB`，启动资产和工具哈希无漂移。
- Core2 native-controller 虽然传入 CLI `-m 0`，`m5core2` machine 现在
  解析为 QOM `8 MiB` memory 和 `has_psram=true`；普通 ESP32 DRAM1 heap
  仍只有 4 MiB 直接映射窗口。新的 `0030-core2-eight-mib-psram.patch`
  模型化 128 个 32 KiB DRAM1 MMU 页；3 个独立 `esp_himem` lease 在同一
  虚拟窗口中交替映射不同 upper-bank 物理块并读回，`3/3 PASS`。物理 cache/
  PSRAM 时序和物理 8 MiB 性能仍为 `NOT RUN`。
- 首次 10 轮运行暴露了 Device Service 的独立等待缺陷：peer 已完成 5 轮并
  开始第 6 轮且 guest 未 panic，但 `_wait_hci_probe_result()` 把
  `ready_timeout_seconds` 硬截断为 30 秒，导致 session 被误判失败并终止
  QEMU。修复后等待使用 session ready timeout，并增加超过 30 秒仍可完成的
  回归测试；失败证据和修复后 PASS 证据分别保留。
- Device Service、Bumble peer 和 runner 当前共享 `1–121` 参数范围，`122`
  会被契约测试拒绝。`120` 已完成 `3/3 PASS`。第一次 `121` 轮运行在应用
  READY、WiFi 和公网已通过后完成 `29` 轮并开始第 `30` 轮，但被固定的
  `180s` readiness 预算误判超时；guest 没有 panic，peer 也没有 GATT
  timeout。runner 与 Device Service 已改为共享按 workload 计算的预算
  `min(7200, 60 + cycles × (6 + delay))s`，`121` 轮、`2s` 间隔对应
  `1028s`。修复 accelerator 采样后，3 个独立 artifact-bound lease 均完成
  `121/121`，WiFi/公网、NUS GATT、frame/QOM、pcap、evidence 和 bounded
  TCG 全部 PASS；`3/3` 复现门禁已经关闭。
- Core2 active-stop/recovery 已在 3 个连续 session 中 PASS：每个 session
  都在 BLE peer 仍处于 linger 窗口、HTTP companion 仍运行时发出 DELETE；
  final state 为 `stopped` 且无错误，HTTP/BLE companion 进入 `terminated`，
  BLE/QEMU PID 均回收，worker active lease 归零。下一次 session 继续完成
  frame/QOM、WiFi DHCP、公网 DNS/HTTP、外部 NUS GATT、pcap 和 evidence。
  该门禁关闭 active-stop cleanup，不覆盖 throughput、其他停止时序或物理
  cache/PSRAM。
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
  B；移除 previous 文件后旧 CA/token 被拒绝。该轮本身只覆盖手工 staged
  migration；另一次双 worker generation-pointer 运行已覆盖自动迁移和
  receipts，但不覆盖跨主机或真机。
- Worker 路径已在两个独立 Linux network namespace 中完成两层验证。第一层
  用真实 Device Service、`WorkerAgent`、Bearer + worker HMAC 和 veth
  验证 control plane，明确不启动 QEMU。第二层在 worker namespace 启动独立
  Device Service，上传并规范化 StickS3 固件、创建真实 QEMU session、取得
  frame/QOM/serial evidence，再由 central service 完成 claim、heartbeat 和
  terminal result；18 项检查全部 PASS，source/normalized firmware 与 QEMU
  SHA256 均绑定，token 不落日志，QEMU 和两个 namespace 均回收。该证据是
  `virtual-device validation`，只证明同一主机上的 server/worker namespace
  隔离；unicast seed 已另证跨两个 routed/masqueraded subnet，但真正跨主机
  QEMU executor/reattach、无 reachable seed 的 NAT traversal、
  namespace-managed/Tab5/cross-host companion continuity 和生产多机调度
  仍未完成。同一 multicast
  domain 的 authenticated discovery 和同主机 central control-plane restart
  continuity 已由独立 live fixture 覆盖。
- `WorkerAgent` 已把控制面与执行面拆成两个可配置的 `/api/v1` 端点：
  中央服务负责 claim/heartbeat/result，可选的 worker-local runtime service
  负责创建、等待、采集 evidence 和停止 QEMU session。单元契约验证所有
  session 请求只发往 runtime plane，控制面不创建 session，并且 runtime 未
  通过 `/api/health` 时 worker 在每次 register/claim 前 fail-closed。worker 还可通过
  `--advertise-endpoint` 把无凭据的 HTTP(S) 可达端点登记到中央目录；
  `--discover-control` 可从 active-token HMAC multicast beacon 自动获得
  control URL，`--discover-control-seed-url` 可从可路由 unicast seed 获得
  同一 signed URL。Linux fixture 的 worker-local QEMU 模式已经 PASS，
  证明控制请求不落到执行面的 session API、执行面独立拥有 QEMU/evidence 和
  cleanup。central control-plane restart fixture 进一步证明 transient
  network retry、重新注册、原 lease/evidence 收敛。runtime-service restart
  fixture 则证明已知 session 的 status/evidence/stop retry、同 PID/QMP
  reattach 和原 job evidence PASS；unified 模式还在同一 lease 中完成 HTTP
  fixture generation-2 重建、BLE peer adoption、第二轮 GATT 和 guest HTTP
  recheck。它不证明物理跨主机网络、跨主机进程迁移或跨主机 idempotency
  存储。
- Job ownership 现已同时由队列和 worker 执行面 fencing：lease 过期、worker
  stale/stop 或 generation 变化导致 re-claim 时，新 claim 获得不同
  `lease_id`，旧 lease 的 heartbeat/result 返回 `409 job_lease_mismatch`；
  `WorkerAgent` 在 heartbeat 所有权冲突或 transient recovery 用尽后，打断
  readiness/evidence wait，停止自己能访问的 worker-local runtime session，
  写本地 `lease_fenced=true` FAIL，并拒绝上报 stale result。control request
  timeout 现受剩余 reconnect budget 限制，真实 blackhole 不会拖到完整 60
  秒 socket timeout。两个 namespace 中的 OS-process side effect 已连续
  `3/3` 证明 runtime DELETE、process reap、lease expiry/requeue 和 retry；
  worker-local Device Service + StickS3 QEMU lane 也连续 `3/3`：首轮真实
  QEMU PID 被 reap，attempt 2 启动新 QEMU 并完成 PASS。QEMU 内
  guest/device-controller side effect、worker 未拥有的外部网络 side effect
  和物理跨主机执行仍为 `NOT RUN`。

## 能力成熟度

这张表回答“现在到底是什么程度”，避免把协议单测、虚拟整机和服务化混成
一个 PASS。

| 能力面 | 虚拟设备验证 | 本地服务化 | 真机 | 当前结论 |
| --- | --- | --- | --- | --- |
| 板级外设与 UI | 设备外设完成度见自动快照；除 Tab5 为 `partial` 外，已登记设备达到其声明范围 | 已启用设备可通过 Device Service 创建 | `NOT RUN` | 可做功能回归，不等于物理外设通过 |
| S3/C6/Core2 单实例无线 | unified profile 与 radio 路径数量见自动快照；S3/C6 整机路径 PASS；S3 `generic-observe` 完成 Open/WPA2-PSK 正确密码 DHCP/DNS/TCP443 和错误密码 M2 拒绝；Core2 `core2-native-hci` 的 HCI/重连/7200s/active-stop 门禁均 PASS，QOM PSRAM device 为 8 MiB，普通 4 MiB heap 持续压力与 upper 4 MiB `esp_himem` MMU bank switch 均完成独立复现 | `qemu-unified` 可返回 frame/QOM/network/evidence；Core2 不启动 GDB bridge；QOM 8 MiB、upper-bank `3/3`、121 轮 readiness 与 accelerator-sampling 均已验证 | `NOT RUN` | 已能验证 WPA2-PSK 成对密钥、同 guest 长重连、限容 host-memory、8 MiB PSRAM 模型和上下 bank 数据路径；后续只剩物理 PSRAM/cache timing/性能、RF/PHY、bit-exact BT controller 和真机 |
| 网络隔离与取证 | namespace、DNS/TLS allowlist、exact A/AAAA resolver、显式绑定 domain suffix 和 bounded CNAME chain、同 guest CNAME→terminal A→HTTP + denied-name/port、有界 IPv4/IPv6 地址或 CIDR egress、pcap、断线重连、DHCP renewal、双 guest DHCP/TCP/双侧 pcap、专用 UIFlow2 测试构建的同 guest IPv6 TCP/HTTP、Linux namespace 内同 guest controlled AAAA + IPv6 HTTP + denied-port + cleanup PASS；真实 server/worker namespace 与三个独立 Docker 容器对的 Bearer+HMAC control plane、worker-local StickS3 QEMU execution、terminal evidence、QEMU reap、container/bridge cleanup、active-token multicast discovery、unicast-seed discovery across routed/masqueraded subnets、worker network-partition process + real QEMU PID fence、central control-plane restart、runtime-service restart continuity 和 trusted-host unified HTTP/BLE companion continuity PASS | 双设备夹具、本地 worker lifecycle、QEMU/QMP restart re-attach、远程目录、durable lease supervisor、同主机 HTTP executor 和 worker HMAC 已通过契约/真实 job 测试；worker 控制面/本地 runtime 双端点已经由单测、双 namespace 和独立 Docker 容器对验证；真实 HTTPS/mTLS、客户端证书、QEMU job、unified StickS3 job over mTLS、SIGHUP TLS/token rotation、active-request drain、previous token/CA 有界重叠和无 worker-SIGHUP 的双 worker generation-pointer 自动迁移 PASS；worker 可在同一 multicast domain 或 reachable unicast seed 发现 control URL，错误/旧 token reject；central/runtime 重启后同 worker/lease/session/evidence 可收敛；物理跨主机 QEMU job、QEMU 内 guest/device-controller 和 worker 未拥有的外部 side-effect fencing、无 reachable seed 的任意 NAT traversal 和 namespace-managed/Tab5/cross-host companion continuity 未完成 | `NOT RUN` | 传输、认证、同主机 QEMU/unified job、worker namespace/container-local QEMU、可审计批量迁移、multicast/unicast bootstrap、worker network-partition OS/QEMU PID fence、central/runtime restart continuity、trusted-host companion continuity、有界地址/CIDR、domain suffix、CNAME resolver 与 guest 生命周期已具备，尚不是多租户恶意固件 VM、任意公网域名解析器或物理跨主机调度器 |
| 通用固件审查 | 导入、capability/security preflight、required/optional 重叠拒绝、unsupported optional warning、security evidence 双向冲突 warning、WebBurner 分段 size/SHA-256/SHA-1/MD5 复算、静态审查、LittleFS/FAT/SPIFFS、文件级 `permission_policy`、包内源码 SPDX header、WebBurner 浏览器流式上传/刷新恢复与 capability 来源展示、session-isolated SD/NVS fixture、sdkconfig detected 与 image-signature observed capability、SHA-bound UI/headless/network-first review expectation PASS；7 台设备 21 个公开非基线样本的历史哈希绑定结果为 10 PASS / 11 PARTIAL；矩阵（含 resume）每轮强制刷新公开 BIN，结果键绑定 device/firmware/SHA/SD/NVS/expectation；当前 CDN 四样本用 SD fixture 得到 `3 PASS / 1 PARTIAL / 0 FAIL`。OpenAI 公开 BIN 的 network-first 模式在合成 NVS 下完成 DHCP、`api.openai.com` DNS、TCP/443 和 pcap；Open、正确 WPA2 与错误 WPA2 三组共用同一固件 SHA | 本地 WebBurner 可上传并生成 manifest；生产 key 流程未完成 | `NOT RUN` | Matrix PASS 分别覆盖 frame/input 或显式 runtime/network expectation；OpenAI 后续仍需真实 key/Realtime/音频和云端业务验证。摘要复算不证明发布者签名或来源真实性。运行态 ACL/权限、完整许可和 `RUNTIME-02/03/04` 仍未完成 |
| 服务生命周期 | 停止/失败历史可恢复；本地 worker heartbeat/drain/resume；PID+start-time+QMP 校验后的 QEMU/QMP re-attach；trusted-host HTTP fixture generation recovery 与 BLE peer adopt；durable queue、HMAC-authenticated HTTP executor、409 与 network blackhole 后的 lease fence/worker-local runtime stop、OS process 与真实 QEMU PID reap、HTTPS/mTLS、`SIGHUP` TLS/token 轮换、active-request drain、previous token/CA 有界重叠与 final cutover、双 worker generation-pointer 自动迁移与回执、multicast/unicast-seed discovery、central control-plane/runtime-service restart continuity、session-create idempotency、worker lease 与失联回收；控制面与本地 runtime API 双端点分离 | 无真实跨主机 QEMU executor、无 reachable seed 的任意 NAT traversal、namespace-managed/Tab5/cross-host companion recovery、跨主机 idempotency、QEMU 内 guest/device-controller 和 worker 未拥有的外部 side-effect fencing、warm pool、生产多机调度 | 不适用 | 已有 durable queue、同主机 authenticated executor、409/network ownership fencing、TLS/mTLS、drained overlap rotation、可审计批量迁移、local control-plane reattach、trusted-host companion reattach、远程 lease、multicast/unicast bootstrap、central/runtime restart continuity、session-create idempotency 和控制/执行面分离基础，不是完整云端服务 |

## 验证证据

带日期的里程碑、当时检查项和证据链接统一维护在
[验证证据台账](validation-ledger.md)。本页只保留“这些证据加在一起，今天
能得出什么当前结论”，不复制逐条流水。代码路径和复现命令见
[代码与验证入口地图](code-map.md)。

## P0 收口

| 工作 | 已闭合 | 仍开放 |
| --- | --- | --- |
| 网络观测与隔离 | 单 guest WiFi/DHCP/HTTP、pcap、WPA2-PSK 正确/错误密码、radio/AP 丢失恢复；controlled DNS A/AAAA、label-boundary domain suffix、bounded CNAME chain 与同 guest CNAME→HTTP、denied-name/port、TLS/Host allowlist；nftables 有界 IPv4/IPv6 地址/CIDR egress、双栈 veth/NAT、IPv6 neighbor control 和清理；专用 UIFlow2 测试构建的同 guest IPv6 TCP/HTTP 与 Linux namespace 内 controlled AAAA、IPv6 HTTP、denied-port、pcap、cleanup；DHCP renewal request/ACK；双 guest DHCP/TCP/双侧 pcap/宿主隔离；跨 server/worker namespace 与三个独立 Docker 容器对的 Bearer+HMAC worker control plane；worker-local StickS3 QEMU、artifact/firmware、evidence、terminal result、QEMU reap、namespace/container/bridge cleanup；本地 worker lifecycle、QEMU/QMP reattach、trusted-host unified HTTP/BLE companion continuity、远程目录、durable queue/lease supervisor、同主机 HTTP executor、HMAC worker auth、active-token multicast discovery、unicast-seed discovery across two routed/masqueraded subnets `3/3`、central/runtime restart continuity、session-create idempotency、HTTPS/mTLS、真实 QEMU job、unified StickS3 job over mTLS、`SIGHUP` TLS/token 轮换、活动请求 drain、previous token/CA 有界重叠与 final cutover、双 worker generation-pointer 自动迁移与回执、控制/本地 runtime API 分离；GitHub Actions Linux policy CI PASS | WPA3、group-key multicast、物理跨主机 QEMU executor/reattach、无 reachable seed 的任意 NAT traversal、namespace-managed/Tab5/cross-host companion continuity、跨主机 idempotency、生产多机调度、任意公网域名解析器 |
| Core2 | 确定性 TCG/icount 10/10 首轮、unified WiFi、公网 DNS/HTTP、HCI、QOM 8 MiB PSRAM、upper-bank MMU remap、121 轮重连、7200s、active-stop 和持续压力均已通过；3 个独立 `esp_himem` lease 在同一个虚拟窗口切换不同 upper physical block，3 个 120 秒 unified lease 在普通 4 MiB heap 各完成 35 次校验；旧未限容 RSS 增长已归因到 TCG buffer | bit-exact controller/baseband、物理板载 `8 MiB` PSRAM/cache timing/性能、长时并发/吞吐、其他 teardown 模式和真机 |
| 通用固件 | FirmwareManifest、WebBurner/M5Burner/ESP-IDF 导入、浏览器 chunk 上传/刷新恢复、WebBurner 分段 size/SHA-256/SHA-1/MD5 完整性、required/optional capability 声明与重叠拒绝、optional mismatch warning、sdkconfig radio/PSRAM detected capability、image-signature observed capability、公开 CDN 每次强制刷新、可回滚 artifact backend、security evidence 双向冲突 warning、capability mismatch、脱敏 URL/凭据/高熵审查、SPDX/CycloneDX SBOM、LittleFS/FAT12/16/32/SPIFFS 文件清单/哈希/敏感路径/SPDX 提取、文件级权限来源、包内源码 SPDX header 和声明级许可 allowlist/denylist；Device Service 支持 session-isolated SD 和分区校验 NVS fixture，矩阵结果键可绑定 fixture、expectation 与 firmware SHA；UI、headless-serial 和 network-first expectation 已可用；7 台设备 21 个公开非基线样本的历史哈希绑定结果为 10 PASS / 11 PARTIAL；当前 CDN 四样本 `3 PASS / 1 PARTIAL / 0 FAIL`；OpenAI NVS、WPA2 正确/错误密码和 network-first pcap 路径绑定同一 BIN SHA；`RUNTIME-01` Flash/PMP 与 `RUNTIME-05` S3 WPA2 已通过虚拟设备验证 | OpenAI 无 UI/云服务完整流程、真实 key/Realtime/音频、书籍内容流程、运行态 ACL/权限、完整许可、法律审批、真机 key/eFuse、更多设备/firmware family；WPA3/group multicast；`RUNTIME-02` Zigbee、`RUNTIME-03` Core2 legacy I2C 和 `RUNTIME-04` ATECC608 仍 `OPEN` |

## 工作流入口

按工作流查看交付状态、代码/证据入口和未完成 Task ID，见
[工作流总台账](workstreams.md)。设备级细节在下文矩阵；真正未完成事项只在
[项目 Backlog](project-backlog.md) 维护。

## 现在可以做什么

### 虚拟设备与 Device Service

- 通过 `/api/v1` 租用、烧录、启动、停止和恢复已启用设备的历史会话；
  当前设备数量见 [自动项目快照](project-snapshot.md)。
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
  Active-BLE 600 秒 hold 证据：
  [`hci4-active-ble-hold600-2x.json`](../tests/uiflow2/core2_native_hci/evidence-2026-10-24-hci4-active-ble-hold600-2x.json)。
  Active-BLE 7200 秒诊断保持证据：
  [`hci4-active-ble-hold7200-diagnostic.json`](../tests/uiflow2/core2_native_hci/evidence-2026-10-24-hci4-active-ble-hold7200-diagnostic.json)。
  Artifact-bound 7200 秒功能保持证据：
  [`hci4-active-ble-hold7200-artifact-bound-1x.json`](../tests/uiflow2/core2_native_hci/evidence-2026-10-24-hci4-active-ble-hold7200-artifact-bound-1x.json)。
  `tb-size=128` 最终两小时证据：
  [`hci4-active-ble-hold7200-tb128-artifact-bound-1x.json`](../tests/uiflow2/core2_native_hci/evidence-2026-10-25-hci4-active-ble-hold7200-tb128-artifact-bound-1x.json)。
  十轮重连证据：
  [`hci4-reconnect10-3x.json`](../tests/uiflow2/core2_native_hci/evidence-2026-10-24-hci4-reconnect10-3x.json)。
  二十轮重连证据：
  [`hci4-reconnect20-3x.json`](../tests/uiflow2/core2_native_hci/evidence-2026-10-24-hci4-reconnect20-3x.json)。
  三十轮重连证据：
  [`hci4-reconnect30-3x.json`](../tests/uiflow2/core2_native_hci/evidence-2026-10-24-hci4-reconnect30-3x.json)。
  六十轮重连证据：
  [`hci4-reconnect60-3x.json`](../tests/uiflow2/core2_native_hci/evidence-2026-10-24-hci4-reconnect60-3x.json)。
  一百二十轮重连证据：
  [`hci4-reconnect120-3x.json`](../tests/uiflow2/core2_native_hci/evidence-2026-10-24-hci4-reconnect120-3x.json)。
  121 轮首次运行的 readiness 预算失败证据：
  [`hci4-reconnect121-readiness-timeout-1x.json`](../tests/uiflow2/core2_native_hci/evidence-2026-10-25-hci4-reconnect121-readiness-timeout-1x.json)。
  reconnect-only accelerator 采样失败证据：
  [`hci4-reconnect121-accelerator-sampling-fail-1x.json`](../tests/uiflow2/core2_native_hci/evidence-2026-10-25-hci4-reconnect121-accelerator-sampling-fail-1x.json)。
  单 lease 121 轮 PASS 证据：
  [`hci4-reconnect121-1x.json`](../tests/uiflow2/core2_native_hci/evidence-2026-10-25-hci4-reconnect121-1x.json)。
  三 lease 121 轮 PASS 聚合证据：
  [`hci4-reconnect121-3x.json`](../tests/uiflow2/core2_native_hci/evidence-2026-10-25-hci4-reconnect121-3x.json)。
  十轮首次运行的 service timeout 失败证据：
  [`hci4-reconnect10-timeout-fail.json`](../tests/uiflow2/core2_native_hci/evidence-2026-10-24-hci4-reconnect10-timeout-fail.json)。
- 错误密码负向测试要求认证失败、重试、无 DHCP、无 HTTP 和失败 marker
  全部成立；StickS3 link-fault/reconnect 路径同时要求恢复后 DHCP 和
  `/after` HTTP。
- Controlled DNS 的 CNAME resolver fixture 已通过两跳 chain、exact 与
  domain-suffix terminal、A/AAAA response 中 chain+terminal record、独立
  CNAME query、NXDOMAIN、循环、uncontrolled terminal、越权 alias 和 9 跳
  拒绝检查：
  [`controlled CNAME evidence`](../tests/network/dns_cname_chain/evidence-2026-10-25-controlled-cname-chain.json)。
  `cname_guest_lifecycle` 又在三个独立 `/api/v1` lease 中完成同 guest
  CNAME→terminal A→HTTP 200、denied-name、denied-port、pcap 与 cleanup：
  [`CNAME guest evidence`](../tests/network/cname_guest_lifecycle/evidence-2026-10-25-cname-guest-lifecycle-3x.json)。
  两次 pre-guest 启动失败保留为诊断，不归因于固件。
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
  真实 QEMU job；跨主机和真机未验。
- 双 worker 自动凭证迁移：
  [`fleet-credential-migration-pass.json`](../tests/network/worker_tls/evidence-2026-10-24-fleet-credential-migration-pass.json)；
  两个 worker 先加载 `A+B` server-trust bridge，服务端进入 A/B overlap 后，
  只原子替换 credential generation pointer；两个 worker 在下一请求自动
  切到 B，并写出相同 fingerprint 的 secret-free receipt，worker `SIGHUP`
  未使用；最后移除 previous 后旧身份被拒绝。
- Linux arm64 已用同一 QEMU 源码重建 `qemu-system-xtensa`，在 private
  network namespace 内实跑 StickS3 guest：namespace 内 HTTP PASS、公网
  DNS 查询无响应、pcap 中无 global/slirp-redirect 目标。
- `esp-emu` 的 `user` 网络没有 pcap；pcap 只由 QEMU radio runtime 提供。

网络模型不是完整 RF/PHY。S3 已验证的是 WPA2-PSK RSN、M1-M4、成对密钥
CCMP RX 和单播 DHCP 数据路径；WPA3、group-key multicast、天线、距离、
干扰、速率、功耗和稳定性结论必须来自后续模型或真机。

### 通用固件

- 输入支持 UIFlow1/UIFlow2、ESP-IDF、Arduino、MicroPython 和兼容的
  merged/segmented flash。
- Device Service 会检查镜像格式、芯片、Flash 大小、地址重叠和基础分区。
- 已提供版本化 FirmwareManifest、WebBurner/M5Burner/`flasher_args.json`
  导入、规范化完整 Flash、provenance/security 记录和结构化 capability
  mismatch；WebBurner 分段可选 size/SHA-256/SHA-1/MD5 会在导入前复算，
  mismatch 直接拒绝；没有 sdkconfig 时还会从规范化 Flash 记录低置信度 WiFi/BLE/
  camera/display/touch/audio/SD 等镜像签名，并区分 required 未观察、
  observed 未声明和 observed 设备不支持。真实公开固件样本已 round-trip。
- `/platform/web/firmware.html` 可直接上传 merged `.bin` 或 WebBurner/
  M5Burner/ESP-IDF 包；浏览器流式计算 SHA256，按 4 MiB chunk 上传，支持
  进度、瞬态重试、取消和刷新恢复，完成后调用同一 Manifest importer。
- 已提供公开社区固件抓取、热门固件批量仿真、结构分析、脱敏静态审查和
  SPDX/CycloneDX SBOM 摘要。manifest 不保存 URL query、凭据或编码载荷明文。
- 包内源码支持有界 `SPDX-License-Identifier` header 扫描。源文件 SHA256、
  脱敏路径和声明进入 `source_license_scan`，并参与许可 allowlist/denylist；
  该扫描不覆盖生成代码、包外 vendor 依赖或法律意见。
- LittleFS/FAT/SPIFFS 的每个文件现在都有 `permission_policy`。FAT 原生
  read-only/hidden/system/archive 属性会单独记录；LittleFS/SPIFFS 明确标记
  没有 Unix mode。三者都没有把镜像属性升级为运行态 ACL 或权限强制 PASS：
  [`filesystem-permission-policy.json`](../tests/firmware/evidence-2026-10-24-filesystem-permission-policy.json)。
- 跨厂商运行时样本已形成 `6` 台 S3/C6 设备、`18` 个热门公开固件快照
  （`8` 个官方、`10` 个社区）：全部完成静态镜像/分区分析和 Device Service
  执行，`10 PASS`、`8 PARTIAL`。该历史快照最初把 C6 Zigbee radio 未建模和
  C6 `LP_SW_HPSYS` 软件复位后 chip id 错误归为两个
  `runtime_model_gap`，保留原始 serial/error 证据而不误报固件 FAIL：
  [`cross-vendor-runtime-model-gaps.json`](../tests/firmware/evidence-2026-10-24-cross-vendor-runtime-model-gaps.json)。
- Core2 新增 `3` 个 MOST_DOWNLOADED 官方固件，运行窗口为 `90s`。
  `UIFlow_Core2` 与 `Core2FactoryTest` 可以完成 AXP 地址/chip-id 探测，但
  随后的 address-`0x51` 事务在 legacy controller 路径上无 ACK，并在产生新
  PMIC `0x34` 事务前返回 I2C 错误；冻结 BM8563 qstr 和调用栈指向 RTC
  candidate。`Core2_For_AWS` 因 ATECC608 安全元件未建模而 abort。三者均无
  应用帧，归类为 `PARTIAL/runtime_model_gap`，不是固件 FAIL：
  [`core2-public-firmware-model-gaps.json`](../tests/firmware/evidence-2026-10-24-core2-public-firmware-model-gaps.json)。
  同一次扩展还修正了 matrix HTTP `/wait` 使用默认 90 秒超时导致长启动窗口
  被误杀的缺陷。
- `RUNTIME-01` 已关闭：16 MiB C6 的全局 4-byte 地址模式误解析了 legacy
  `0x02/0x20` 三字节写擦地址，core dump 写入覆盖 offset 0 的 bootloader；
  同时修复 C6 复位后遗留 PMP range 的问题。该固件经 Device Service 重跑后
  不再出现 `Invalid chip id`，`runtime_model_gaps=[]`，Nesso 官方外设组
  `5/5`、NanoC6 板级探针均通过：
  [`c6-soft-reset-flash-addressing.json`](../tests/firmware/evidence-2026-10-24-c6-soft-reset-flash-addressing.json)。
  该样本随后仍有独立的 Instruction access fault，因此完整功能仍是
  `PARTIAL`。`RUNTIME-02` Zigbee/802.15.4 仍为 `OPEN`；`esp-emu`
  `--thread-sim` 已观察到源码构建 switch/light 的双向 802.15.4 帧，但没有
  完成 commissioning/join。缺口、
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
| NanoC6 | ESP32-C6 / QEMU | 无屏控制台、GPIO、RGB、按键、IR、WiFi、BLE 通过 | `qemu-unified` PASS；独立公网探针 PASS；Zigbee `thread-sim` 仅有双向帧，join 未通过 | 原生 BT controller、C6 WiFi PHY；Zigbee/802.15.4 `RUNTIME-02` commissioning 未建模 |
| Nesso N1 | ESP32-C6 / QEMU | 显示、触摸、扩展 IO、电源、IMU、LoRa、IR、蜂鸣器、WiFi、BLE 通过 | `qemu-unified` PASS；同 guest 公网 DNS/HTTP PASS | stock `hardware.RGB()` 未验、原生 BT controller；`RUNTIME-01` Flash/PMP 修复已关闭，Meshtastic 独立应用异常待归因 |
| Core2 | ESP32 LX6 / QEMU | 显示、触摸、PMIC、IMU、RTC、音频、WiFi、公网 DNS/HTTP、HCI-offload、stock VHCI、QEMU native-HCI 外部 GATT、同 guest 多轮重连、8 MiB PSRAM QOM/upper-bank MMU、持续压力/周期联网和 active-stop/recovery | `HCI-4` 五 lease、upper-bank `3/3`、heap `3×120s`/600s、3 个 121 轮 lease、最终 `tb-size=128` `7200s` 和 active-stop/recovery `3/3` 均 PASS；旧 `core2-native-vhci` 仅诊断/兼容 | bit-exact BT controller/baseband、物理 PSRAM/cache timing、长时并发/吞吐、其他 teardown 模式、真机同路径 |
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
   extended-run 故障；artifact-bound 两小时 active-BLE 功能保持也已 PASS，
   但仍不覆盖 bit-exact controller/baseband、物理 cache/PSRAM 和真机同路径；
   同 guest 20、30、60、120 轮 GATT 均已有 3 个独立 lease 的 PASS
   evidence。第一次 `121` 轮运行完成 `29` 轮并开始第 `30` 轮后，被固定
   `180s` readiness 预算误杀；guest 无 panic，peer 无 GATT timeout。现在
   runner 与 Device Service 使用同一 workload-aware 预算。第二次复跑又
   暴露 accelerator 仅由 hold loop 采样的 evidence bug；修复后单个
   artifact-bound lease 完成 `121/121`，HLI `3405/3405`、events `2316`、
   ACLs `1089`，队列、错误、dropped 和 panic 均为 0。随后另 2 个独立
   lease 以同固件/ELF/QEMU/工具哈希完成 `121/121`，`3/3` 门禁关闭。
   第一个 10 轮
   attempt 的失败已确认是 service 30 秒硬上限，不是 guest/controller；
   修复后的失败和 PASS evidence 均保留。旧
   `core2-native-vhci` 的
   `1/2` 只说明 GDB 诊断桥不稳定；`core2-native-hci` 的 hook 偏移仍绑定
   已验证 UIFlow2 v2.5.3 build。
   旧 `7200s` 行为保持保留为 `DIAGNOSTIC_PASS`。最终 `tb-size=128`
   artifact-bound 两小时复测已完成：启动资产/工具无漂移，`bounded_tcg_cache`、
   frame/QOM、WiFi、公网、GATT、pcap、HLI health、active peer 和清理全部
   PASS；240 个资源采样的 RSS `323536→252992 KiB`、phys footprint
   `250880→188416 KiB`。旧的未限容增长已定位到 TCG translation buffer，
   当前 workload 的 host-memory 风险关闭；这不等于物理 cache/PSRAM 等价。
   unified guest 已在普通 4 MiB DRAM1 heap 上完成 `3×120s` 与 600 秒持续
   校验，upper 4 MiB 另由 `esp_himem` MMU remap `3/3` 覆盖；两者合计关闭
   “只有 QOM 可见、没有持续 guest 数据面”的功能缺口，但不覆盖物理
   PSRAM/cache 时序或真机。
3. **Tab5 闭源后端**：`esp-emu 0.50.0` 缺少若干动态设备与控制面，Tab5 仍是
   `partial`。
4. **网络隔离**：Linux namespace runner 和 guest-inside-namespace 整机路径
   已 PASS；trusted-host 和 Linux private namespace 下的 TLS/Host allowlist
   也已完成测试 CA、HTTPS 握手、200/403 和 pcap 联合验证。nftables 精确
   IPv4/IPv6 地址/协议/端口、双栈 veth/NAT、IPv6 neighbor control 和清理
   已 PASS；两台 guest 的 DHCP、TCP、双侧 pcap 与宿主隔离也已 PASS。它仍
   不等同于恶意固件沙箱、生产 worker 或 RF；本地 worker lifecycle、
   QEMU/QMP reattach、远程注册目录、durable job queue、同主机独立 HTTP
   executor、HTTPS/mTLS、真实 QEMU job、unified StickS3 job over mTLS
  两个 namespace 与三个独立 Docker 容器对中的 worker-local QEMU
  execution 也已实现。同一
   multicast domain 中的 active-token discovery 和 central control-plane
   restart、runtime-service restart 后的同 lease/session/evidence continuity
  也已 PASS；不能接收 multicast 的跨子网 worker 还可从 reachable unicast
  seed 获取同一 signed control URL，两个 routed/masqueraded subnet
  fixture 为 `3/3 PASS`。trusted-host unified HTTP/BLE companion 在 service restart
   后还会重建 HTTP fixture、adopt 存活 BLE peer 并完成重启后的第二轮 GATT
  与 guest HTTP 请求。物理跨主机 QEMU executor/reattach、无 reachable seed
  的任意 NAT traversal 与跨主机迁移、namespace-managed/Tab5/cross-host companion continuity、
   连续外部 evidence 流、生产 secret manager/多机调度和 VM 隔离仍待
   实现。网络策略现已覆盖有界 CIDR、显式绑定 domain suffix、bounded
   CNAME chain 与同 guest CNAME→HTTP 生命周期，但 terminal answer 仍受
   endpoint 限制，不能代替任意公网解析或恶意固件沙箱。
   专用 UIFlow2 测试构建已在同一
   Linux namespace guest 内完成 controlled AAAA、IPv6 HTTP、denied-port、
   pcap 和 cleanup；原厂固件仍默认未启用 IPv6 link-local。
5. **通用固件兼容性**：SoC 相同不代表板级、分区、安全配置和控制器全部
   兼容。当前 C6 的软件复位 chip-id 错误已定位为 Flash 地址宽度与 PMP
   复位模型缺陷并修复；Zigbee/802.15.4 仍未建模。修复后的 Meshtastic
   样本仍有独立 Instruction access fault，必须继续区分固件缺陷和新的
   模型偏差，不能用重试伪装 PASS。OpenAI 样本的黑屏已拆分：公开 BIN 的
   NVS 为空；注入合成配置后，Open 和 WPA2-PSK 正确密码都能进入 DHCP、
   DNS 和 TCP/443，错误密码则在 M2 MIC 被拒绝且无 DHCP。后续固件审查仍
   必须显式声明用户数据、网络认证和安全前置条件，不能仅凭首帧或单条
   “retry”日志判断固件失败。
6. **视觉保真**：除 StopWatch 外，设备外壳仍主要是近似模型。

## 文档职责

- `README.md`：入口、当前摘要、快速开始和文档导航。
- `project-snapshot.md`：从机器可读源自动生成的设备、样本、缺口和 Task 板。
- `workstreams.md`：按工作流汇总稳定代码入口、权威状态页和未完成 Task ID。
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
