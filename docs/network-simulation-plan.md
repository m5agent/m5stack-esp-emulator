# 网络模拟方案

日期：`2026-10-25`

本文定义网络数据面、隔离模式、测试要求和安全边界。当前 PASS 计数、具体
固件结果和未完成 Task 分别由
[自动项目快照](project-snapshot.md)、[项目当前状态](project-status.md)和
[项目 Backlog](project-backlog.md)维护。

第一次进入项目时先读[工程交接总览](engineering-handoff.md)，再按本页理解
网络数据面和证据边界。

## 产品路径

完整设备验收使用一个 Device Service lease、一个 QEMU guest 和一份 evidence：

```text
Device Service lease
        |
        +-- one QEMU process
              +-- SoC + flash + RAM/PSRAM
              +-- board display/input/audio/sensors
              +-- WiFi MAC/DMA + QEMU NIC
              +-- BLE HCI-UART or controller-boundary path
              +-- serial + frame + QOM + pcap + peer evidence
```

`runtime=network` 是诊断和 provisioning lane，不能与另一条板级结果拼接成
单 guest PASS。

## 网络模式

| 模式 | 入口 | 能证明什么 | 不能证明什么 |
| --- | --- | --- | --- |
| User-mode lab | QEMU user net + 实例内 HTTP/BLE peer | scan、association、DHCP、DNS、TCP/UDP 和重连逻辑 | 宿主/公网隔离，真实 RF |
| Controlled DNS/TLS | Linux network + mount namespace、测试 CA、A/AAAA/CNAME resolver、Host allowlist | 允许/拒绝决策、证书路径、同一 UIFlow2 test-build guest 的 AAAA/HTTP/denied-port 和 pcap 一致；同 guest CNAME→A→HTTP/denied-name/denied-port/cleanup | 任意公网服务、原厂固件默认 IPv6 能力或证书固定 |
| Bounded dual-stack egress | nftables + per-session IPv4/IPv6 veth/NAT | 有界 IPv4/IPv6 地址或 CIDR、协议和端口的允许/拒绝及清理 | 任意宽泛网段、未绑定域名或完整恶意固件沙箱 |
| Firmware SoftAP | `runtime=network`、AP 密码和 loopback `hostfwd` | 固件自建 provisioning portal | 手机、captive portal OS 或真实 roaming |
| Multi-device lab fabric | private namespace 内的 QEMU socket L2 switch | 两台 guest 的 DHCP、私有 TCP 和双侧 pcap | TAP primitive、RF、WPA2/WPA3 或生产 worker |
| Cross-container worker | 两个独立 Docker 容器 + user-defined bridge；routable unicast discovery seed | central queue/directory 跨容器控制，worker 容器内 runtime Device Service 执行真实 QEMU 并返回 evidence；跨子网 worker 通过 signed seed 发现 control URL | 物理跨主机、无 reachable seed 的任意 NAT traversal、迁移或 companion continuity |
| CardputerZero Ethernet | 独立 Linux ARM64 后端 | SR9900A/r8152 Ethernet frame 数据面 | WiFi 或 ESP32/UIFlow2 网络 |

S3/C6 的 QEMU 模型覆盖 guest 可见的 MAC、DMA descriptor、interrupt 和
user-net frame path，不是完整 PHY、速率、安全或天线模型。Core2 OpenMAC 和
HCI boundary 也是功能级模型；PHY-ready 日志不等于应用联网。

## 已实现的机制

详细 result 和 evidence 只在当前状态、快照和验证台账维护。稳定实现包括：

- S3/C6 单 guest board + WiFi + HCI-UART BLE profile；
- 任意 ESP32-S3 backend 的 `runtime=qemu-wifi/profile=generic-observe`
  board+WiFi 最小观察路径，用于非 UIFlow、headless 和 network-first
  固件；它不要求 HCI/BLE 或 UIFlow marker，并支持 Open 与 WPA2-PSK；
- S3 WPA2-PSK RSN、M1-M4、PTK/GTK、成对密钥 CCMP RX、正确/错误密码、
  session-derived eFuse/NIC MAC 绑定和 unicast DHCP delivery；
- Core2 OpenMAC WiFi、公网 DNS/HTTP 和 `core2-native-hci` controller
  boundary；
- Core2 `0008` 在 CPU0 idle 时预分配真实 guest HCI event/ACL 对象，避免
  ACL FIFO head 把 Command Status/LE Meta 延迟到 NimBLE `2s` ACK 预算之外；
  两批双实例 `4×120s` 为 `8/8 PASS`，两批三实例 `3×120s` 为
  `6/6 PASS`；extended BLE peer scan 预算随 session readiness 有界扩展。
  四实例首批先 `1 PASS / 3 FAIL`，暴露 HLI health/prealloc failure 和
  NimBLE `ble_hs_hci_process_ack` panic；`0009` 将真实 guest event/ACL
  备用池扩到 `8/4` 后，两批四实例各 `4/4 PASS`。两批五实例 30 秒错峰
  各 `5/5 PASS`；旧 `shift=auto` 零错峰实现先 `5/5 PASS`、独立确认批
  `3/5 FAIL`。默认固定 `icount shift=5` 并前置测试 BLE server 后，两批
  zero-stagger 五实例均 `5/5 PASS`；随后两批六实例又均 `6/6 PASS`，
  合计 `12/12`；八实例先以旧 sweep 下限得到纯吞吐阈值失败，校准
  `hold/12` 后两批均 `8/8 PASS`，合计 `16/16`，达到服务单设备容量上限。
  结论仍不外推到大于八实例、physical controller/RF 或真机；
- `core2-native-vhci` GDB 诊断路径，仅作为兼容和历史对照；
- controlled DNS、exact A/AAAA records、domain suffix 的 label-boundary
  匹配、最多 8 跳 exact-name CNAME chain、测试 CA、DNS/TLS allowlist、
  Host 决策和 pcap 摘要；
- domain suffix 必须显式绑定受控 resolver answer，且 answer 必须落在
  `allowed_endpoints` 的地址/CIDR 内；域名不直接授权外部解析出的任意地址；
- CNAME alias 和 terminal 都必须受 policy 覆盖；A/AAAA response 返回
  chain+terminal record，CNAME query 返回 chain；cycle、uncontrolled
  terminal、越权 alias、与 exact A/AAAA 或 domain-suffix answer 冲突和
  超过 8 跳均 fail-closed；
- 三个独立 `qemu-wifi/uiflow2-sticks3-wifi` Device Service lease 已让同一
  stock UIFlow2 guest 跟随 CNAME terminal A，完成 allowed HTTP、denied
  name、denied port、pcap、namespace cleanup 和 QEMU reap；
- nftables IPv4/IPv6 地址或 CIDR egress、双栈 veth/NAT、IPv6 neighbor
  discovery control、fail-closed 和清理；IPv4 最宽 `/16`、IPv6 最宽
  `/48`，并拒绝 special-use、IPv4-mapped 和 QEMU SLiRP synthetic CIDR；
- 专用 UIFlow2 StickS3 测试构建在同一 guest 中完成 IPv6 TCP/HTTP 和 pcap
  绑定；原厂 UIFlow2 尚未创建 IPv6 link-local；
- 错误密码、radio/AP 丢失、DHCP renewal 和同 guest 重连负向/恢复探针；
- private namespace 内两台 QEMU guest 的 socket L2 fabric；
- Device Service 的 pcap、network evidence 和 `network-fault` API；
- durable worker queue、HTTPS/mTLS、TLS/token `SIGHUP` rotation、
  active-request drain、bounded credential overlap 和 generation-pointer
  credential migration；
- HMAC-authenticated IPv4 multicast control-plane discovery；worker 验证
  active-token 签名后自动注册，错误/旧 token reject，token rotation 后
  新 worker 可重新发现；beacon 不含 token；
- 对无法接收 multicast 的跨子网/NAT worker，独立 unicast discovery seed
  返回同一 HMAC-signed beacon；worker 通过
  `--discover-control-seed-url` 验证签名后使用其中的 control URL。
  privileged Linux fixture 用两个独立 subnet、IPv4 forwarding 和
  masquerade 连续 `3/3 PASS`，同时证明 multicast 不跨 router、错误/旧
  token reject、rotation、NAT 源地址和 cleanup；
- job claim 后，worker 对 transient control-plane network/429/5xx 做有界
  heartbeat/result retry；central service 以同一 state dir 重启后，worker
  自动重注册、继续 heartbeat 并提交原 lease 的 evidence，runtime QEMU
  session 不被重启。claim 本身没有稳定 dedup token 前不自动盲重试；
- worker→control blackhole 会受剩余 reconnect budget 约束。真实 Linux
  namespace fixture 在 local runtime session 与 child process 已创建后
  drop control traffic，worker fence、DELETE runtime、reap process、拒绝
  stale result；5 秒 lease expiry 后 job re-queue，网络恢复后第二个 worker
  以新 attempt 完成 PASS，连续 `3/3`。同一 runner 另有真实 worker-local
  Device Service + StickS3 QEMU lane：首轮 QEMU PID 被 reap，attempt 2
  启动新 QEMU 并完成 PASS，亦为 `3/3`。worker-local `qemu-unified` lane
  又在三次独立运行中等待同 session 的 HTTP request、BLE PASS 和非空 pcap
  后断网，验证 HTTP/BLE companion 进入 terminated、BLE PID 回收、pcap
  summary 完成以及 fresh retry 重新取得 unified evidence；QEMU 内
  guest/controller 内部状态与 worker 未拥有的外部 side effect 仍开放；
- 已获得具体 runtime session ID 后，worker 对 runtime status/evidence/stop
  做有界 transient retry；runtime Device Service 同 state 重启后按
  PID start-time、QMP ownership 和 running 状态重新接管同一 QEMU；
  trusted-host unified session 还会从持久请求重建 HTTP fixture，并在
  PID/start-time/command SHA256 校验后 adopt 存活 BLE peer，完成重启后的
  GATT cycle 2 和 guest HTTP recheck；
  session create 使用持久化 idempotency key；worker 以 job+lease 派生稳定
  key，响应丢失后重试仍返回同一 session，不同请求返回 409；
- 两个 veth 连接 network namespace 中的 Bearer+HMAC worker control plane，
  以及 worker namespace 内独立 Device Service 执行真实 StickS3 QEMU、
  artifact/firmware、evidence、terminal result 和 cleanup；
- 三个独立双容器复现中，central 容器和 worker 容器通过 user-defined Docker
  bridge 通信；worker 容器内 runtime 创建真实 QEMU session，绑定
  source/normalized firmware、QEMU 和 evidence hash，并清理 QEMU、容器和
  bridge；
- 本地 QEMU/QMP control-plane restart re-attach。

cleanup probe 会读取 sandbox 实际生成的 `isolation.json`，只有
`cleanup_completed`、QEMU reap、DNS/HTTP close 均成立时才把清理记为 PASS；
Linux arm64 private namespace 已用同一 UIFlow2 test-build guest 完成
controlled AAAA、allowed IPv6 HTTP、denied-port、pcap、namespace cleanup
和 QEMU reap。

当前仍未完成的网络产品化项只列在
[项目 Backlog](project-backlog.md)，重点是 `NET-04` 物理跨主机 worker/QEMU
executor、namespace-managed/Tab5/cross-host companion continuity、连续
external evidence 流、没有 reachable seed 时的任意 NAT traversal 和不可信
固件 disposable VM。
`NET-05` 与 `NET-06` 均已完成当前 accepted virtual-device scope。

## Required test matrix

| Capability | Minimum assertion |
| --- | --- |
| Scan/associate | guest 看见目标 SSID，并记录预期安全模式或明确仅使用开放测试 AP |
| DHCP | guest 获得 address、gateway 和 DNS |
| DNS | 允许/拒绝查询到达受控 resolver，并有 pcap 或结构化 query log |
| TCP/UDP | guest 与 namespace 内 peer 完成请求/响应或 datagram |
| Wrong credential | 认证失败、重试、无 DHCP/HTTP 和明确失败 marker 同时成立 |
| WPA2-PSK | 正确密码完成 RSN、M1-M4、CCMP RX、DHCP/DNS/TCP；错误密码在 M2 MIC 拒绝且无 DHCP |
| Radio/AP recovery | radio 移除后 scan 为空，恢复后重新 DHCP，前后请求和 pcap 对齐 |
| DHCP renewal | 不重启 guest 观察到 lease renewal，且地址/HTTP 连续性成立 |
| Multi-device | 两台 guest 只能通过预期 lab fabric 通信 |
| Core egress | 允许/拒绝 IP 或 CIDR+protocol+port 可重复，不能被 user-net 旁路 |
| Domain/CNAME | suffix 只在 DNS label boundary 匹配；exact/longest suffix 顺序稳定；CNAME chain 有界、无 cycle、alias/terminal 受 policy 覆盖；同一 guest 使用 terminal address 完成 TCP/HTTP，未允许名称/端口被拒绝 |
| Worker transport | 认证、TLS/mTLS、rotation、drain、replay 防护、network-partition runtime fence 和 fail-closed 有同次证据 |
| Evidence | 只保存允许的网络元数据和 payload hash，artifact 可复现 |

## Security boundary

待审固件和 QEMU 都必须视为不可信输入：

- 每个任务使用 disposable VM/namespace 和独立虚拟 Flash；
- 阻断 workstation LAN、宿主目录、凭据、云 metadata 和控制面；
- 只保留 pcap 元数据、DNS/DHCP/flow 摘要和 payload hash；
- 设置 CPU、RAM、磁盘、运行时长和并发上限；
- 任务结束后回收进程、网络和临时盘；
- namespace 或 policy 创建失败时拒绝启动，不能回退到无隔离网络。

当前的 trusted-host namespace、user-net 和 loopback `hostfwd` 不是恶意固件
沙箱。生产审查仍需要 disposable VM/copy-on-write isolation、对象存储、
审计和跨主机调度。

## 证据要求

一次网络 PASS 至少要保存：

1. firmware/ELF/QEMU SHA、device、runtime/profile；
2. guest 侧 scan/association/DHCP/DNS/TCP/UDP marker；
3. host side peer/controller/gateway 决策日志；
4. pcap 或结构化 packet 摘要；
5. namespace、nftables、veth/NAT 和进程清理结果；
6. 失败时的 bounded error 和首个失败点。

`runtime=network` 证据不能声明 framebuffer、input、QOM 或完整设备 PASS。

## Evidence entries

- [Controlled DNS/TLS](../tests/network/tls_allowlist/README.md)
- [Controlled DNS CNAME chain](../tests/network/dns_cname_chain/README.md)
- [Firmware guest CNAME lifecycle](../tests/network/cname_guest_lifecycle/README.md)
- [Exact dual-stack egress](../tests/network/egress_allowlist/README.md)
- [DHCP renewal](../tests/network/idf_dhcp_renewal/README.md)
- [Wrong password](../tests/network/wrong_password/README.md)
- [Radio/AP reconnect](../tests/network/reconnect_probe/README.md)
- [Two-guest lab fabric](../tests/network/lab_fabric/README.md)
- [Worker TLS/mTLS and rotation](../tests/network/worker_tls/README.md)
- [Worker durable queue](../tests/network/worker_queue/README.md)
- [Authenticated worker discovery](../tests/network/worker_discovery/README.md)
- [Authenticated unicast discovery across NAT](../tests/network/worker_discovery_seed/README.md)
- [Worker network-partition side-effect fencing](../tests/network/worker_partition_fencing/README.md)
- [Worker control-plane restart continuity](../tests/network/worker_control_restart/README.md)
- [Worker runtime-service restart continuity](../tests/network/worker_runtime_restart/README.md)
- [Idempotent session creation](../tests/network/session_idempotency/README.md)
- [Worker cross-network-namespace control and QEMU execution](../tests/network/worker_cross_netns/README.md)
- [Worker QEMU across Docker containers](../tests/network/worker_cross_container/README.md)
- [Worker QEMU/QMP reattach](../tests/network/worker_reattach/README.md)
- [Core2 native-HCI backend](core2-native-hci-backend.md)
- [Unified runtime contract](unified-device-runtime.md)
