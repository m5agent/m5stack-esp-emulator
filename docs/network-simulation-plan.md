# 网络模拟方案

日期：`2026-10-24`

本文定义网络架构、当前验证边界和后续验收顺序。当前设备能力以
[项目当前状态](project-status.md) 为准，未完成事项只在
[项目 Backlog](project-backlog.md) 维护，代码和证据入口见
[代码与验证入口地图](code-map.md)。

## 产品路径

正式验收使用一个 Device Service lease、一个 QEMU guest 和一份 evidence：

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

`esp-emu runtime=network` 是诊断和 provisioning lane，不是整机验收后端。
它不能与其他 guest 的板级结果拼接成“单实例 PASS”。

## 当前已验证

| 范围 | 当前结果 | 证据边界 |
| --- | --- | --- |
| S3/C6 unified | 11 个设备 profile 在单 guest 中完成板级、WiFi scan/association/DHCP/HTTP 和外部 HCI-UART BLE GATT | 固定开放 AP；不是完整 PHY/RF，也不覆盖 WPA2/WPA3 |
| Core2 unified | OpenMAC WiFi、DHCP、受控 HTTP、公网 DNS/HTTP、UART1 HCI-offload BLE 和板级外设同一 guest；确定性 TCG/icount 10/10 首轮 | 环境门控；物理 cache/PSRAM 和 RF 未验；native-HCI 短时 extended-run 已 PASS |
| Core2 stock BLE（legacy） | 不重建 HCI-UART，在 GDB 中介的 `esp_vhci_host_*` 边界接 Bumble；外部 NUS GATT 5/5，同 guest board+WiFi+公网+GATT 3/3 | 仅用于诊断/兼容；repeated lease `1/2`，不是 bit-exact BT baseband/controller |
| Core2 QEMU native-HCI | `HCI-1` 至 `HCI-4` PASS；`0005` halt-gated guest call 后两批 `5×10s` 为 `10/10`，3 个 `60s` 为 `3/3`，2 个 `120s` 为 `2/2`；active-BLE 120 秒 hold，以及 3 个各 20、30、60、120 轮的 GATT lease 均 PASS | `core2-native-hci` 无 GDB bridge，同包验证 frame/QOM/WiFi/公网/GATT/pcap 与 HLI health；reconnect blocker 已定位到 Bumble 对无响应 `0x0c35` 的非法 Command Status 并修正；120 轮每 lease HLI `3377/3377`；bit-exact controller、超过一百二十轮、多小时 soak 和物理 cache/PSRAM 仍开放 |
| Device Service | `qemu-unified/profile=core2-native-hci` 五 lease PASS | 每轮均绑定同一固件/ELF/QEMU SHA 和完整 evidence ZIP |
| 公网 | StickS3、Nesso N1 和 Core2 在对应同 guest 路径完成 IPv4 DNS/HTTP | 只证明一次可达的 IPv4 HTTP；不证明任意云服务、TLS 固定或长期稳定 |
| 负向认证 | 错误密码要求认证失败、重试、无 DHCP、无 HTTP 和失败 marker 同时成立 | 当前实际 AP 类型有限 |
| AP/radio 丢失与恢复 | `radio-enabled=false` 后 scan `1→0`、恢复后 `0→1`；同一 guest 重新 DHCP 并通过 `/after` HTTP，pcap 含两次 DORA | 虚拟 WiFi 模型状态，不是物理 RF；不是 DHCP renewal |
| DHCP renewal | ESP-IDF guest 调用 `netifapi_dhcp_renew()`；pcap 同事务包含初次 DORA 后的 `REQUEST/ACK`，lease 86400、地址保持、随后 HTTP 200 | 仿真 lease renewal，不是物理 AP/RF |
| Linux 隔离 | StickS3 QEMU guest 位于 private network namespace；无外部路由，namespace 创建失败时 fail-closed | 单设备、受控 fixture；不是恶意固件 VM |
| Linux CI | GitHub Ubuntu runner 执行完整平台测试和 nftables exact IPv4 veth/NAT fixture | 验证策略引擎、清理和 CI 稳定性；没有 QEMU guest |
| 双设备 lab fabric | private namespace 内的 QEMU socket L2 switch 连接两台 StickS3，并按 MAC 绑定连接槽位；两端 DORA、A→B TCP `19123`、双侧 pcap 双向 payload hash、宿主/公网/metadata/默认路由阻断和清理全部 PASS | 两台真实 QEMU guest、各自的 NIC/协议栈；不是 TAP 数据面、RF、WPA2/WPA3、worker 或恶意固件沙箱 |
| DNS/TLS allowlist | private mount namespace 注入临时 `resolv.conf`；允许域名 A，拒绝和 UIFlow/NTP 后台域名 NXDOMAIN；测试 CA TLS 允许 200、拒绝 403；pcap 一致 | Host/DNS 决策与网络 destination policy 分开记录 |
| 精确 IPv4 egress | nftables input/output 默认 drop；exact IP+protocol+port；同 IP 其他端口和同端口其他 IP 均超时；`1.1.1.1:80` 经 veth/NAT 200/301；namespace/NAT 清理 | 外部 IPv6、CIDR 和域名不作为隐式端点 |
| QEMU 外部内存 | patch `0027` 修复 ESP32-S3 AES/GDMA 访问外部内存，TLS 可进入证书解析和 HTTPS 路径 | 当轮全矩阵 `67/67`、`274/274`，全部首轮无重试 |
| 共享 WLAN 生命周期 | patch `0028` 修复显式 NIC MAC、association/DHCP ingress 和积压队列 flush；双 guest socket fabric 已完成 DHCP/TCP/双侧 pcap | patch `0028` 后最新全矩阵 `67/67`、`274/274`，全部首轮无重试 |
| Tab5 | C6 `network_adapter` 以 ESP-Hosted 启动 | P4 UIFlow2/ESP-IDF 的 association/DHCP/DNS/TCP 仍 `NOT RUN` |
| CardputerZero | 独立 SR9900A Ethernet frame 回环 | 不是 WiFi，也不是 ESP32/UIFlow2 产品路径 |

主要证据：

- [controlled DNS + TLS Host allowlist](../tests/network/tls_allowlist/evidence-2026-10-24-controlled-dns-pass.json)
- [Linux private namespace guest](../tests/network/linux_isolation/evidence-2026-10-23-linux.json)
- [GitHub Actions namespace/egress PASS](../tests/network/egress_allowlist/evidence-2026-10-24-github-actions-pass.json)
- [Core2 native-HCI Device Service five-lease evidence](../tests/uiflow2/core2_native_hci/evidence-2026-10-24-hci4-service-5x.json)
- [Core2 halt-gated extended-run evidence](../tests/uiflow2/core2_native_hci/evidence-2026-10-24-hci4-halted-gate-5x.json)
- [Core2 60-second hold evidence](../tests/uiflow2/core2_native_hci/evidence-2026-10-24-hci4-hold60-3x.json)
- [Core2 120-second hold evidence](../tests/uiflow2/core2_native_hci/evidence-2026-10-24-hci4-hold120-2x.json)
- [Core2 ten-cycle reconnect evidence](../tests/uiflow2/core2_native_hci/evidence-2026-10-24-hci4-reconnect10-3x.json)
- [Core2 twenty-cycle reconnect evidence](../tests/uiflow2/core2_native_hci/evidence-2026-10-24-hci4-reconnect20-3x.json)
- [Core2 thirty-cycle reconnect evidence](../tests/uiflow2/core2_native_hci/evidence-2026-10-24-hci4-reconnect30-3x.json)
- [Core2 sixty-cycle reconnect evidence](../tests/uiflow2/core2_native_hci/evidence-2026-10-24-hci4-reconnect60-3x.json)
- [Core2 one-hundred-twenty-cycle reconnect evidence](../tests/uiflow2/core2_native_hci/evidence-2026-10-24-hci4-reconnect120-3x.json)
- [Core2 ten-cycle service timeout failure](../tests/uiflow2/core2_native_hci/evidence-2026-10-24-hci4-reconnect10-timeout-fail.json)
- [Worker HTTPS/mTLS transport](../tests/network/worker_tls/evidence-2026-10-24-tls-mtls-pass.json)
- [Worker real QEMU job over mTLS](../tests/network/worker_tls/evidence-2026-10-24-tls-mtls-qemu-job-pass.json)
- [Worker unified StickS3 job over mTLS](../tests/network/worker_tls/evidence-2026-10-24-tls-mtls-unified-job-pass.json)
- [Worker TLS/token rotation and post-rotation QEMU job](../tests/network/worker_tls/evidence-2026-10-24-security-rotation-job-pass.json)
- [Worker rotation with active-request drain](../tests/network/worker_tls/evidence-2026-10-24-security-rotation-drain-job-pass.json)
- [Worker rotation with bounded overlap and final cutover](../tests/network/worker_tls/evidence-2026-10-24-security-rotation-overlap-job-pass.json)
- [Two-worker generation-pointer credential migration](../tests/network/worker_tls/evidence-2026-10-24-fleet-credential-migration-pass.json)
- [Core2 WiFi-only deterministic repeat](../tests/network/core2_openmac_wifi/evidence-2026-10-24-deterministic-5x.json)
- [Core2 legacy native-VHCI diagnostic lease](../tests/uiflow2/unified_core2/evidence-2026-10-23-native-vhci-service.json)
- [精确 IPv4 IP/端口和 NAT 证据](../tests/network/egress_allowlist/evidence-2026-10-24-ip-port-pass.json)
- [TLS guest under nftables policy](../tests/network/tls_allowlist/evidence-2026-10-24-ip-port-nftables-pass.json)
- [GDMA 外部内存修复和全矩阵](../tests/uiflow2/evidence-2026-10-24-gdma-external-memory-matrix.json)
- [双 guest WLAN patch 和最新全矩阵](../tests/uiflow2/evidence-2026-10-24-dual-guest-fabric-matrix.json)
- [ESP-IDF 错误密码拒绝、重试和 no-DHCP/no-HTTP 证据](../tests/network/wrong_password/evidence-2026-10-24-wrong-password-pass.json)
- [ESP-IDF DNS/UDP 双向载荷证据](../tests/network/idf_dns_udp/evidence-2026-10-24-dns-udp-pass.json)
- [StickS3 radio/AP 丢失与同 guest 恢复](../tests/network/reconnect_probe/evidence-2026-10-24-radio-loss-pass.json)
- [StickS3 自动化 radio down/up、双 DHCP、前后 HTTP 与 pcap](../tests/network/reconnect_probe/evidence-2026-10-24-radio-loss-recovery-pass.json)
- [双设备 private QEMU lab fabric](../tests/network/lab_fabric/evidence-2026-10-24-two-guest-pass.json)

## 尚未证明

- 物理 RF 消失/恢复、信道/速率变化或重新分配不同 lease；
- WPA2/WPA3、hidden SSID、roaming、channel/rate/security 行为；
- namespace、pcap retention 和 evidence upload 的跨主机 executor、
  跨主机 QEMU job、worker 主机自动发现/跨主机迁移、
  companion/evidence continuity、跨主机 reattach 和生产调度；本地
  heartbeat/drain、HTTPS/mTLS、`SIGHUP` A/B rotation + activity drain +
  bounded credential overlap、generation-pointer 双 worker 自动迁移、authenticated
  同主机 HTTP executor、QEMU/QMP restart reattach、远程注册目录和 durable
  queue/lease supervisor 已具备，GitHub-hosted policy/egress CI 已单独
  通过；
- 任意 S3/C6 固件或任意公网服务的稳定联网；
- 外部 IPv6、CIDR 或域名到多个 IP 的 egress policy；
- Tab5 P4↔C6 ESP-Hosted 端到端网络；
- Core2 bit-exact BT controller/baseband、物理 cache/PSRAM、
  RF/coexistence/throughput、超过一百二十轮和多小时 soak；two-minute
  halt-gated extended-run 与 20、30、60、120 轮 reconnect 已通过，但参数上限
  `120` 不能推导超过一百二十轮的证据；
- 基于一次网络观测判定固件安全。

QEMU S3/C6 模型覆盖 guest 可见的 MAC、DMA descriptor、interrupt 和
QEMU user-net frame path，不是完整 PHY、速率、安全或天线模型。Core2
OpenMAC 和 BT boundary 同样是功能级模型；PHY-ready 日志不等于应用联网。

## Device coverage

| Device class | Current network path | Status |
| --- | --- | --- |
| 9 台 ESP32-S3 | QEMU S3 WiFi MAC/DMA + board model + UART1/2 H4 BLE | Unified Device Service lease PASS |
| NanoC6、Nesso N1 | QEMU C6 WiFi MAC/DMA + board model + UART1 H4 BLE | Unified Device Service lease PASS |
| Core2 | OpenMAC WiFi；HCI-offload、legacy VHCI 或 canonical native-HCI | `core2-native-hci` 五 lease、hold 和 20/30/60/120 轮 reconnect PASS 且无 GDB；`core2-native-vhci` 仅诊断 |
| Tab5 | C6 ESP-Hosted transport | Transport starts; end-to-end network `NOT RUN` |
| CardputerZero | Linux SR9900A Ethernet | Separate backend; not WiFi |

“模拟设备可联网”只能按设备、profile、固件 SHA 和本次 evidence 判断，
不能从同一 SoC 的另一台设备继承 PASS。

## 网络模式

### Isolated user-mode lab

QEMU `user` networking 加本实例内的受控 HTTP/BLE peer。默认用于固件功能
测试、DNS/TCP/UDP、重连和 provisioning。用户态 NAT 本身不是恶意固件沙箱。

### Controlled DNS and TLS

Linux worker 使用 private network + mount namespace。命名空间内没有外部路由；
QEMU 子树看到 127.0.0.1 resolver；HTTPS 网关使用临时 CA 和 Host allowlist。
允许/拒绝、DNS、TLS 和 pcap 必须由同一次 guest 运行产生。

### Firmware SoftAP

固件自建 AP 时，`runtime=network` 可加入该 AP，并用最多 8 条 loopback-only
`hostfwd` 访问 provisioning portal。该路径覆盖 portal 请求，不模拟手机、
真实 roaming 或 captive-portal 操作系统行为。

### Multi-device lab fabric

已通过的双设备路径在 private Linux network namespace 内运行一个 QEMU socket
L2 switch，两台 StickS3 分别连接到这个 switch。namespace 没有默认路由，
input/output 默认 drop；DHCP 使用固定 MAC/IP reservation，switch 只转发给
另一台已登记 guest。

`network_fabric.py` 另有 namespace bridge + 两个 TAP + 原生命令 DHCP 的 host
primitive，用于在没有 QEMU 的 CI 中检查 namespace、nftables、DHCP readiness
和清理。两条路径都有独立证据，不能把 primitive 说成 QEMU 数据面，也不能把
本次虚拟 lab 说成生产 worker、恶意固件沙箱或工作站 LAN 隔离保证。

## Required test matrix

| Capability | Minimum assertion |
| --- | --- |
| Scan/associate | 固件看见目标 SSID 并使用预期安全模式 |
| DHCP | guest 获得 address、gateway 和 DNS |
| DNS | 允许/拒绝查询到达受控 resolver 并有 pcap |
| TCP/UDP | guest 与 namespace 内 peer 完成请求/响应或 datagram |
| Wrong credential | 认证失败、重试、无 DHCP/HTTP、明确失败 marker |
| Radio/AP recovery | radio 移除后 scan 为空，恢复后重新 DHCP，前后请求和 pcap 对齐 |
| DHCP renewal | 不重启 guest 观察到 lease renewal |
| Real AP loss | 移除实际虚拟 radio/AP 后恢复，而不是只调用 guest disconnect |
| Multi-device | 两台 guest 只能通过预期 lab fabric 通信 |
| Core egress | 允许/拒绝目标 IP+port 可重复，不能被 user-net 旁路 |
| Evidence | pcap 只保存元数据和 payload hash，evidence 可复现 |

## Security boundary

待审固件和 QEMU 都应视为不可信输入：

- 每个任务使用 disposable VM/namespace 和独立虚拟 Flash；
- 阻断工作站 LAN、宿主目录、凭据、云元数据和控制面；
- 只保留 pcap 元数据、DNS/DHCP/flow 摘要和 payload hash；
- 设置 CPU、RAM、磁盘、运行时长和并发上限；
- 任务结束后回收进程、网络和临时盘；
- “没有看到异常流量”不等于安全。

## 交付顺序

| Phase | Status | Next acceptance |
| --- | --- | --- |
| N0 单设备 WiFi/DHCP/HTTP | DONE | 保留回归 |
| N1 可控 DNS/TLS/IP-port/DHCP-renew/负向/重连/pcap | DONE | 保留回归 |
| N2 S3/C6 单 guest board+radio | DONE | 新 profile 必须带设备级 evidence |
| N3 Tab5 P4↔C6 end-to-end | `NOT RUN` | association、DHCP、DNS、TCP 同一 P4 guest |
| N4a Linux policy CI | DONE | GitHub-hosted namespace/nft/egress fixture 保持 fail-closed 并可重复 |
| N4b 双设备 fabric | DONE (virtual) | 两台 StickS3 的 DHCP、guest TCP、双侧 pcap、宿主隔离与清理已通过；下一步接入 worker |
| N4c durable queue/lease supervisor | DONE (contract/API) | 幂等 submit、capability claim、lease、expiry retry、cancel/result、worker stale/stop/generation 回收；authenticated 同主机 HTTP executor 已运行真实 QEMU job；真实 loopback HTTPS/mTLS、signed worker 生命周期、真实 QEMU job、unified StickS3 job over mTLS、SIGHUP TLS/token rotation、activity drain、bounded credential overlap 和 final cutover 后 QEMU job PASS；双 worker 再通过 generation pointer 自动迁移并写出 receipt，无需 worker SIGHUP；跨主机 QEMU job、worker 主机自动发现、companion/evidence continuity 仍开放 |
| N5 Core2 production BLE/PHY | PARTIAL | `HCI-4`、active hold 和 3 个独立 lease × 20/30/60/120 轮 reconnect 已通过；继续补超过一百二十轮与多小时 soak，之后处理 bit-exact controller/baseband、物理 cache/PSRAM、coexistence 和真机 |
| N6 单实例产品契约 | S3/C6/Core2 slices PASS | 扩大固件覆盖并补真机同路径 |

虚拟 radio/AP 丢失恢复和双设备 private lab fabric 已完成，远程 worker
注册目录、durable job queue、authenticated 同主机 HTTP executor 和本地
QEMU/QMP restart reattach 也已具备，SIGHUP TLS/token rotation 已在同主机
loopback 验证，活动请求会在 reload 前完成，previous token/CA 也提供有界
重叠与 final cutover。双 worker generation-pointer 迁移和 secret-free
receipts 也已通过；下一步是 `NET-04` 的 worker 主机自动发现、跨主机
executor、跨主机 QEMU job、
companion/evidence continuity、跨主机 reattach 与生产多机调度，再单列
`NET-05` 外部 IPv6。精确 IPv4
endpoint policy 已由 nftables 在隔离 namespace 内执行，外部 IPv4 通过
per-session veth/NAT；策略或依赖不可用时 fail-closed。
