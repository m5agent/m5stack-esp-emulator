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
| Core2 stock BLE | 不重建 HCI-UART，在 stock 固件的 `esp_vhci_host_*` 边界接 Bumble；外部 NUS GATT 5/5，同 guest board+WiFi+公网+BLE GATT 3/3 | 依赖 GDB bridge，不是 bit-exact BT baseband/controller |
| Device Service | `qemu-unified/profile=core2-native-vhci` 单 lease 返回 frame、QOM、pcap、bridge 和 peer evidence | 仅证明该 runtime/profile 和对应固件 SHA |
| 公网 | StickS3、Nesso N1 和 Core2 在对应同 guest 路径完成 IPv4 DNS/HTTP | 只证明一次可达的 IPv4 HTTP；不证明任意云服务、TLS 固定或长期稳定 |
| 负向认证 | 错误密码要求认证失败、重试、无 DHCP、无 HTTP 和失败 marker 同时成立 | 当前实际 AP 类型有限 |
| 断线和恢复 | guest `WLAN.disconnect()` 叠加 QMP `wifi0` link down/up 后重新 DHCP，并通过 `/after` HTTP | 不是物理 AP/radio 消失，也不是 DHCP renewal |
| Linux 隔离 | StickS3 QEMU guest 位于 private network namespace；无外部路由，namespace 创建失败时 fail-closed | 单设备、受控 fixture；不是恶意固件 VM |
| DNS/TLS allowlist | private mount namespace 注入临时 `resolv.conf`；允许域名 A，拒绝和 UIFlow/NTP 后台域名 NXDOMAIN；测试 CA TLS 允许 200、拒绝 403；pcap 一致 | 仍不是任意目标 IP/端口 egress policy |
| QEMU 外部内存 | patch `0027` 修复 ESP32-S3 AES/GDMA 访问外部内存，TLS 可进入证书解析和 HTTPS 路径 | 修复后最新全矩阵 `67/67`、`274/274`，全部首轮无重试 |
| Tab5 | C6 `network_adapter` 以 ESP-Hosted 启动 | P4 UIFlow2/ESP-IDF 的 association/DHCP/DNS/TCP 仍 `NOT RUN` |
| CardputerZero | 独立 SR9900A Ethernet frame 回环 | 不是 WiFi，也不是 ESP32/UIFlow2 产品路径 |

主要证据：

- [controlled DNS + TLS Host allowlist](../tests/network/tls_allowlist/evidence-2026-10-24-controlled-dns-pass.json)
- [Linux private namespace guest](../tests/network/linux_isolation/evidence-2026-10-23-linux.json)
- [Core2 native-VHCI Device Service lease](../tests/uiflow2/unified_core2/evidence-2026-10-23-native-vhci-service.json)
- [GDMA 外部内存修复和全矩阵](../tests/uiflow2/evidence-2026-10-24-gdma-external-memory-matrix.json)

## 尚未证明

- 通用 destination IP/端口级 egress allowlist；
- DHCP renewal、真实 AP 消失/恢复和 lease 变化；
- WPA2/WPA3、hidden SSID、roaming、channel/rate/security 行为；
- 两台设备通过唯一预期 lab fabric 通信；
- namespace、pcap retention 和 evidence upload 的正式 CI/worker 生命周期；
- 任意 S3/C6 固件或任意公网服务的稳定联网；
- Tab5 P4↔C6 ESP-Hosted 端到端网络；
- Core2 无 GDB 的 VHCI 后端、bit-exact BT controller/baseband、
  RF/coexistence/throughput/soak；
- 基于一次网络观测判定固件安全。

QEMU S3/C6 模型覆盖 guest 可见的 MAC、DMA descriptor、interrupt 和
QEMU user-net frame path，不是完整 PHY、速率、安全或天线模型。Core2
OpenMAC 和 BT boundary 同样是功能级模型；PHY-ready 日志不等于应用联网。

## Device coverage

| Device class | Current network path | Status |
| --- | --- | --- |
| 9 台 ESP32-S3 | QEMU S3 WiFi MAC/DMA + board model + UART1/2 H4 BLE | Unified Device Service lease PASS |
| NanoC6、Nesso N1 | QEMU C6 WiFi MAC/DMA + board model + UART1 H4 BLE | Unified Device Service lease PASS |
| Core2 | OpenMAC WiFi；HCI-offload 或 stock native-VHCI BLE | `core2-unified` 和 `core2-native-vhci` PASS；生产边界开放 |
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
| Link recovery | link down/up 后重新 DHCP，前后请求和 pcap 对齐 |
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
| N1 可控 DNS/TLS/负向/重连/pcap | MOSTLY DONE | 补 destination IP/port policy 和 DHCP renewal |
| N2 S3/C6 单 guest board+radio | DONE | 新 profile 必须带设备级 evidence |
| N3 Tab5 P4↔C6 end-to-end | `NOT RUN` | association、DHCP、DNS、TCP 同一 P4 guest |
| N4 Linux CI、egress、双设备 fabric | IN PROGRESS | CI 可重复，namespace fail-closed，两 guest 隔离 |
| N5 Core2 production BLE/PHY | PARTIAL | 非 GDB backend、controller semantics、coexistence soak |
| N6 单实例产品契约 | S3/C6/Core2 slices PASS | 扩大固件覆盖并补真机同路径 |

下一项最小交付是 `NET-01`：在现有 namespace controlled DNS/TLS 基础上加入
目标 IP+端口 allow/deny，并由同一次 guest 产生 pcap 和协议证据。随后补
`NET-02` 的 renewal/真实 AP 恢复和 `NET-03` 的双设备 fabric。
