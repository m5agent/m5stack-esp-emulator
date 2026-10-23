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
| Core2 unified | OpenMAC WiFi、DHCP、受控 HTTP、公网 DNS/HTTP、UART1 HCI-offload BLE 和板级外设同一 guest；确定性 TCG/icount 10/10 首轮 | 环境门控；物理 cache/PSRAM、RF 和 long soak 未验 |
| Core2 stock BLE | 不重建 HCI-UART，在 stock 固件的 `esp_vhci_host_*` 边界接 Bumble；VHCI 地址由 ELF 固定；外部 NUS GATT 5/5，同 guest board+WiFi+公网+BLE GATT 3/3 | GDB 仍控制暂停/注入/return；不是 bit-exact BT baseband/controller |
| Core2 QEMU native-HCI | `HCI-1` transport PASS；无 GDB 捕获首个 H2C `01030c00`；`HCI-3a` 交付 Reset Complete 后 guest 发出下一条命令，targeted `5/5` | `HCI-3b` 完整 HCI/GATT 与 `HCI-4` repeated lease 仍开放，不能作为整机 BLE PASS |
| Device Service | `qemu-unified/profile=core2-native-vhci` 单 lease 返回 frame、QOM、pcap、bridge 和 peer evidence | 仅证明该 runtime/profile 和对应固件 SHA |
| 公网 | StickS3、Nesso N1 和 Core2 在对应同 guest 路径完成 IPv4 DNS/HTTP | 只证明一次可达的 IPv4 HTTP；不证明任意云服务、TLS 固定或长期稳定 |
| 负向认证 | 错误密码要求认证失败、重试、无 DHCP、无 HTTP 和失败 marker 同时成立 | 当前实际 AP 类型有限 |
| AP/radio 丢失与恢复 | `radio-enabled=false` 后 scan `1→0`、恢复后 `0→1`；同一 guest 重新 DHCP 并通过 `/after` HTTP，pcap 含两次 DORA | 虚拟 WiFi 模型状态，不是物理 RF；不是 DHCP renewal |
| DHCP renewal | ESP-IDF guest 调用 `netifapi_dhcp_renew()`；pcap 同事务包含初次 DORA 后的 `REQUEST/ACK`，lease 86400、地址保持、随后 HTTP 200 | 仿真 lease renewal，不是物理 AP/RF |
| Linux 隔离 | StickS3 QEMU guest 位于 private network namespace；无外部路由，namespace 创建失败时 fail-closed | 单设备、受控 fixture；不是恶意固件 VM |
| Linux CI | GitHub Ubuntu runner 执行完整平台测试和 nftables exact IPv4 veth/NAT fixture | 验证策略引擎、清理和 CI 稳定性；没有 QEMU guest |
| DNS/TLS allowlist | private mount namespace 注入临时 `resolv.conf`；允许域名 A，拒绝和 UIFlow/NTP 后台域名 NXDOMAIN；测试 CA TLS 允许 200、拒绝 403；pcap 一致 | Host/DNS 决策与网络 destination policy 分开记录 |
| 精确 IPv4 egress | nftables input/output 默认 drop；exact IP+protocol+port；同 IP 其他端口和同端口其他 IP 均超时；`1.1.1.1:80` 经 veth/NAT 200/301；namespace/NAT 清理 | 外部 IPv6、CIDR 和域名不作为隐式端点 |
| QEMU 外部内存 | patch `0027` 修复 ESP32-S3 AES/GDMA 访问外部内存，TLS 可进入证书解析和 HTTPS 路径 | 修复后最新全矩阵 `67/67`、`274/274`，全部首轮无重试 |
| Tab5 | C6 `network_adapter` 以 ESP-Hosted 启动 | P4 UIFlow2/ESP-IDF 的 association/DHCP/DNS/TCP 仍 `NOT RUN` |
| CardputerZero | 独立 SR9900A Ethernet frame 回环 | 不是 WiFi，也不是 ESP32/UIFlow2 产品路径 |

主要证据：

- [controlled DNS + TLS Host allowlist](../tests/network/tls_allowlist/evidence-2026-10-24-controlled-dns-pass.json)
- [Linux private namespace guest](../tests/network/linux_isolation/evidence-2026-10-23-linux.json)
- [GitHub Actions namespace/egress PASS](../tests/network/egress_allowlist/evidence-2026-10-24-github-actions-pass.json)
- [Core2 native-VHCI Device Service lease](../tests/uiflow2/unified_core2/evidence-2026-10-23-native-vhci-service.json)
- [精确 IPv4 IP/端口和 NAT 证据](../tests/network/egress_allowlist/evidence-2026-10-24-ip-port-pass.json)
- [TLS guest under nftables policy](../tests/network/tls_allowlist/evidence-2026-10-24-ip-port-nftables-pass.json)
- [GDMA 外部内存修复和全矩阵](../tests/uiflow2/evidence-2026-10-24-gdma-external-memory-matrix.json)
- [StickS3 radio/AP 丢失与同 guest 恢复](../tests/network/reconnect_probe/evidence-2026-10-24-radio-loss-pass.json)

## 尚未证明

- 物理 RF 消失/恢复、信道/速率变化或重新分配不同 lease；
- WPA2/WPA3、hidden SSID、roaming、channel/rate/security 行为；
- 两台设备通过唯一预期 lab fabric 通信；
- namespace、pcap retention 和 evidence upload 的正式 CI/worker 生命周期；
- 任意 S3/C6 固件或任意公网服务的稳定联网；
- 外部 IPv6、CIDR 或域名到多个 IP 的 egress policy；
- Tab5 P4↔C6 ESP-Hosted 端到端网络；
- Core2 重复 Device Service lease 稳定性、无 GDB 暂停/注入/return 的 VHCI
  后端、bit-exact BT controller/baseband、RF/coexistence/throughput/soak；
- 基于一次网络观测判定固件安全。

QEMU S3/C6 模型覆盖 guest 可见的 MAC、DMA descriptor、interrupt 和
QEMU user-net frame path，不是完整 PHY、速率、安全或天线模型。Core2
OpenMAC 和 BT boundary 同样是功能级模型；PHY-ready 日志不等于应用联网。

## Device coverage

| Device class | Current network path | Status |
| --- | --- | --- |
| 9 台 ESP32-S3 | QEMU S3 WiFi MAC/DMA + board model + UART1/2 H4 BLE | Unified Device Service lease PASS |
| NanoC6、Nesso N1 | QEMU C6 WiFi MAC/DMA + board model + UART1 H4 BLE | Unified Device Service lease PASS |
| Core2 | OpenMAC WiFi；HCI-offload 或 stock native-VHCI BLE | `core2-unified` 和 `core2-native-vhci` PASS；VHCI 符号已固定；GDB 控制面与重复 lease 门禁开放 |
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

后续在独立 namespace/bridge 内连接两台 guest。必须证明设备仅通过预期 fabric
通信，不能访问工作站 LAN、宿主服务、云元数据或控制面。

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
| N4b 双设备 fabric | OPEN | 两台 guest 只能通过预期 fabric 通信，宿主 LAN/控制面不可达 |
| N5 Core2 production BLE/PHY | PARTIAL | ELF 固定符号已完成；剩余 GDB 控制面、重复 lease、controller semantics、coexistence soak |
| N6 单实例产品契约 | S3/C6/Core2 slices PASS | 扩大固件覆盖并补真机同路径 |

虚拟 radio/AP 丢失恢复已完成，下一步是 `NET-03` 双设备 fabric。精确 IPv4
endpoint policy 已由 nftables 在隔离 namespace 内执行，外部 IPv4 通过
per-session veth/NAT；策略或依赖不可用时 fail-closed。
