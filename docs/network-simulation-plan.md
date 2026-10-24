# 网络模拟方案

日期：`2026-10-25`

本文定义网络数据面、隔离模式、测试要求和安全边界。当前 PASS 计数、具体
固件结果和未完成 Task 分别由
[自动项目快照](project-snapshot.md)、[项目当前状态](project-status.md)和
[项目 Backlog](project-backlog.md)维护。

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
| Controlled DNS/TLS | Linux network + mount namespace、测试 CA、A/AAAA resolver、Host allowlist | 允许/拒绝决策、证书路径、同一 UIFlow2 test-build guest 的 AAAA/HTTP/denied-port 和 pcap 一致 | 任意公网服务、原厂固件默认 IPv6 能力或证书固定 |
| Exact dual-stack egress | nftables + per-session IPv4/IPv6 veth/NAT | 精确 IPv4/IPv6 地址、协议和端口的允许/拒绝及清理 | CIDR、domain-set 或完整恶意固件沙箱 |
| Firmware SoftAP | `runtime=network`、AP 密码和 loopback `hostfwd` | 固件自建 provisioning portal | 手机、captive portal OS 或真实 roaming |
| Multi-device lab fabric | private namespace 内的 QEMU socket L2 switch | 两台 guest 的 DHCP、私有 TCP 和双侧 pcap | TAP primitive、RF、WPA2/WPA3 或生产 worker |
| CardputerZero Ethernet | 独立 Linux ARM64 后端 | SR9900A/r8152 Ethernet frame 数据面 | WiFi 或 ESP32/UIFlow2 网络 |

S3/C6 的 QEMU 模型覆盖 guest 可见的 MAC、DMA descriptor、interrupt 和
user-net frame path，不是完整 PHY、速率、安全或天线模型。Core2 OpenMAC 和
HCI boundary 也是功能级模型；PHY-ready 日志不等于应用联网。

## 已实现的机制

详细 result 和 evidence 只在当前状态、快照和验证台账维护。稳定实现包括：

- S3/C6 单 guest board + WiFi + HCI-UART BLE profile；
- Core2 OpenMAC WiFi、公网 DNS/HTTP 和 `core2-native-hci` controller
  boundary；
- `core2-native-vhci` GDB 诊断路径，仅作为兼容和历史对照；
- controlled DNS、exact A/AAAA records、测试 CA、DNS/TLS allowlist、
  Host 决策和 pcap 摘要；
- nftables exact IPv4/IPv6 egress、双栈 veth/NAT、IPv6 neighbor
  discovery control、fail-closed 和清理；
- 专用 UIFlow2 StickS3 测试构建在同一 guest 中完成 IPv6 TCP/HTTP 和 pcap
  绑定；原厂 UIFlow2 尚未创建 IPv6 link-local；
- 错误密码、radio/AP 丢失、DHCP renewal 和同 guest 重连负向/恢复探针；
- private namespace 内两台 QEMU guest 的 socket L2 fabric；
- Device Service 的 pcap、network evidence 和 `network-fault` API；
- durable worker queue、HTTPS/mTLS、TLS/token `SIGHUP` rotation、
  active-request drain、bounded credential overlap 和 generation-pointer
  credential migration；
- 两个 veth 连接 network namespace 中的 Bearer+HMAC worker control plane，
  以及 worker namespace 内独立 Device Service 执行真实 StickS3 QEMU、
  artifact/firmware、evidence、terminal result 和 cleanup；
- 本地 QEMU/QMP control-plane restart re-attach。

cleanup probe 会读取 sandbox 实际生成的 `isolation.json`，只有
`cleanup_completed`、QEMU reap、DNS/HTTP close 均成立时才把清理记为 PASS；
Linux arm64 private namespace 已用同一 UIFlow2 test-build guest 完成
controlled AAAA、allowed IPv6 HTTP、denied-port、pcap、namespace cleanup
和 QEMU reap。

当前仍未完成的网络产品化项只列在
[项目 Backlog](project-backlog.md)，重点是 `NET-04` 跨主机 worker/QEMU
executor、companion/evidence continuity 和 CIDR/domain-set。
`NET-05` 与 `NET-06` 均已完成当前 accepted virtual-device scope。

## Required test matrix

| Capability | Minimum assertion |
| --- | --- |
| Scan/associate | guest 看见目标 SSID，并记录预期安全模式或明确仅使用开放测试 AP |
| DHCP | guest 获得 address、gateway 和 DNS |
| DNS | 允许/拒绝查询到达受控 resolver，并有 pcap 或结构化 query log |
| TCP/UDP | guest 与 namespace 内 peer 完成请求/响应或 datagram |
| Wrong credential | 认证失败、重试、无 DHCP/HTTP 和明确失败 marker 同时成立 |
| Radio/AP recovery | radio 移除后 scan 为空，恢复后重新 DHCP，前后请求和 pcap 对齐 |
| DHCP renewal | 不重启 guest 观察到 lease renewal，且地址/HTTP 连续性成立 |
| Multi-device | 两台 guest 只能通过预期 lab fabric 通信 |
| Core egress | 允许/拒绝 IP+protocol+port 可重复，不能被 user-net 旁路 |
| Worker transport | 认证、TLS/mTLS、rotation、drain、replay 防护和 fail-closed 有同次证据 |
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
- [Exact dual-stack egress](../tests/network/egress_allowlist/README.md)
- [DHCP renewal](../tests/network/idf_dhcp_renewal/README.md)
- [Wrong password](../tests/network/wrong_password/README.md)
- [Radio/AP reconnect](../tests/network/reconnect_probe/README.md)
- [Two-guest lab fabric](../tests/network/lab_fabric/README.md)
- [Worker TLS/mTLS and rotation](../tests/network/worker_tls/README.md)
- [Worker durable queue](../tests/network/worker_queue/README.md)
- [Worker cross-network-namespace control and QEMU execution](../tests/network/worker_cross_netns/README.md)
- [Worker QEMU/QMP reattach](../tests/network/worker_reattach/README.md)
- [Core2 native-HCI backend](core2-native-hci-backend.md)
- [Unified runtime contract](unified-device-runtime.md)
