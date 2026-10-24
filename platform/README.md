# Platform

Last reviewed: `2026-10-25`

共享基础设施，不含具体产品档案。当前能力以
[`docs/project-status.md`](../docs/project-status.md) 为准，代码和证据入口见
[`docs/code-map.md`](../docs/code-map.md)，按工作流查看交付和待办见
[`docs/workstreams.md`](../docs/workstreams.md)，带日期的验证记录见
[`docs/validation-ledger.md`](../docs/validation-ledger.md)，已知固件运行时
模型差异见
[`docs/runtime-model-gap-register.md`](../docs/runtime-model-gap-register.md)。

```text
platform/
├── qemu/                 # QEMU machine/profile 注册表
├── peripherals/          # 外设契约、runtime coverage 和模板
├── runtime/wasm/         # esp-emu WASM 运行时
├── schema/               # device.json schema
├── tests/                # API、catalog、manifest、network、文档契约测试
├── tools/                # Device Service、固件、网络、生成器和证据工具
└── web/                  # 设备目录、会话观察和浏览器设备外壳
```

## 运行时分层

| 后端 | 覆盖 | 定位 |
| --- | --- | --- |
| `qemu-esp32s3` | 9 台 ESP32-S3 设备 | 产品主路径：板级外设、WiFi MAC/DMA、UART HCI BLE |
| `qemu-esp32c6` | NanoC6、Nesso N1 | 产品主路径：C6 板级模型、WiFi MAC/DMA、UART HCI BLE |
| `qemu-esp32lx6` | Core2 | 产品主路径：LX6 板级、OpenMAC WiFi、HCI-offload 与 no-GDB `core2-native-hci` |
| `esp-emu 0.50.0` | Tab5 | P4 专用例外：烧录、启动、framebuffer、touch mailbox、RS-485、静态 I2C |
| Linux ARM64 QEMU | CardputerZero | 独立 Linux 后端，不是 ESP32/UIFlow2 路径 |
| `esp-emu runtime=network` | 诊断/Provisioning | 网络和 SoftAP 排障 lane，不提供整机板级 PASS |

QEMU S3/C6 和 Core2 的单个 `qemu-unified` lease 可以同时提供板级外设、WiFi、
受控 HTTP、BLE peer 和 evidence。它们仍是功能级虚拟设备，不是完整 PHY/RF、
安全模式、功耗或物理时序模型。

## Device Service

`platform/tools/device_service.py` 提供按 lease 创建独立虚拟设备的本地服务；
`platform/tools/serve.py` 暴露 HTTP 和 `/api/v1`：

- 内容寻址 firmware/artifact 和版本化 FirmwareManifest；
- 可恢复 chunk artifact upload，含连续 offset/hash、失败回滚和 staging GC；
- `/platform/web/firmware.html` WebBurner：浏览器 SHA256、chunk 进度重试、
  取消、刷新恢复和 package → manifest import；
- merged/segmented/ZIP 导入与 capability mismatch；
- QEMU 与 Tab5 session 生命周期、TTL、容量和存储回收；
- 本地 worker 的稳定 ID、generation、heartbeat、独占状态目录、
  active/abandoned lease、drain/resume 和 recent-result 记录；
- 远程 worker 的持久 job queue、幂等提交、capability 匹配、claim、lease
  heartbeat、worker 失联回收、超时重试和 terminal result；
- 独立 HTTP worker executor：持久 generation、中央 claim/result、
  worker/job heartbeat，并可用独立 runtime API 执行真实 session、
  evidence ZIP/SHA256 下载和 stop；
- worker-only mutation 的 HMAC 请求签名、时间戳、nonce replay cache 和
  path/body identity binding；
- HTTPS TLS 1.2+、服务端证书校验、可选 client CA 强制 mTLS，以及
  `worker_agent.py` 的自定义 CA/客户端证书；
- token-file 与 `SIGHUP` A/B rotation：先 drain 活动请求，再更新服务端
  证书、client CA、worker 客户证书/key 和 master token；previous
  token/client-CA 提供有界重叠，移除 previous 并再次 `SIGHUP` 后旧凭据
  失效；drain 超时保留旧配置；
- 本地 QEMU 的 PID start-time、QMP socket ownership 和
  `query-status=running` 三重校验后 re-attach；仅恢复 QEMU/QMP 控制面；
- 串口、framebuffer、输入、QOM、reset、link/radio `network-fault` 和
  evidence ZIP；
- `runtime=qemu-unified` 的 S3/C6/Core2 单 guest 板级 + 网络 + BLE；
- Core2 `profile=core2-native-hci` 的 stock firmware QEMU native-HCI →
  HLI → Bumble 路径；
- legacy `profile=core2-native-vhci` 的 GDB 诊断/兼容路径；
- QEMU pcap、flow/DNS/DHCP/ARP 和 payload-hash 摘要；
- Linux private net/mount namespace、controlled DNS、fail-closed isolation、
  TLS/Host allowlist fixture 和 SoftAP `hostfwd` 诊断。

当前边界：

- `core2-native-hci` 已完成 `HCI-1` 至 `HCI-4`。五个独立
  `/api/v1` lease 同时通过 frame/QOM、WiFi/公网、外部 NUS GATT、pcap 和
  evidence ZIP，且 `gdb_bridge=false`。`0005` 恢复 guest-call sregs 并把
  HLI 注入限制在 halted/idle vCPU 后，两批 `5×10s` hold 运行 `10/10`
  PASS，3 个 `60s` hold `3/3`，2 个 `120s` hold `2/2`，每轮 HLI
  health 为零错误；另有 2 个 active-BLE `600s` hold `2/2`。同一 guest
  reconnect 已在 3 个独立 lease 中分别完成
  20、30、60、120 轮，每轮均有 guest RX/notification；一百二十轮每 lease HLI
  `3377/3377`、events `2297`、ACLs `1080`。根因是 Bumble 为无响应
  `0x0c35` 错误返回 Command Status，留下 stale ACK。旧
  `core2-native-vhci` 仍使用
  服务托管的 GDB bridge，且 repeated lease 只有 `1/2`，因此只保留为
  显式诊断/兼容路径。Device Service/Bumble/runner 已接受 `1–121` 轮并有
  `122` 轮拒绝测试；一百二十轮门禁全部 `3/3 PASS`，无错误或 panic。bit-exact
  Espressif BT baseband/controller、物理 cache/PSRAM、121 轮运行、最终两小时
  限容 soak 和真机仍未完成。
- Tab5 通过 `esp-emu` 单独接入，外设状态明确为 `partial`。
- CardputerZero 不由 `/api/v1` 管理。
- trusted-host 网络 namespace 不是恶意固件沙箱。本地 worker identity、
  heartbeat、drain/resume 和重启租约分类，以及远程 worker 注册目录已实现；
  durable job queue 已支持幂等提交、claim/lease、expiry retry 和 worker
  失联回收；本地 QEMU/QMP 控制面已完成 ownership 校验后的 reattach。
  同主机 HTTP executor、worker HMAC、可验证 HTTPS/mTLS、真实 QEMU 和
  unified StickS3 job over mTLS、SIGHUP rotation + activity drain +
  bounded credential overlap、evidence ZIP/SHA256 回报，以及
  generation-pointer 同主机双 worker 自动迁移和 secret-free receipts 已实现；
  自动发现 worker 主机、跨主机 QEMU executor/reattach、
  companion/BLE/evidence continuity、生产 secret manager/多机调度和 VM
  隔离仍未完成。
- controlled DNS 与 TLS/Host allowlist 已在 Linux private namespace 下
  PASS，QEMU patch `0027` 闭合 AES/GDMA 外部内存读取；`egress=allowlist`
  已在同一隔离路径验证 exact IPv4/IPv6 IP/协议/端口、双栈 veth/NAT、
  IPv6 neighbor control 和清理，上述内容也不等于 CIDR、域名、IPv6 DNS
  或恶意固件沙箱。
- 双设备 lab fabric 同样是 virtual-device 证据：private namespace 内两台
  StickS3 通过 QEMU socket L2 switch 完成 DHCP、A→B TCP 和双侧 pcap，宿主
  与公网不可达。TAP/bridge + DHCP helper 是 CI 单独检查的 host primitive，
  不是本次 QEMU PASS 的数据路径，也不是生产 worker。
- C6 `LP_SW_HPSYS` 后的 chip-id 错误已定位为 16 MiB Flash legacy 写擦
  地址宽度和 reset PMP 状态问题并修复；Zigbee/802.15.4 controller 仍未
  建模。`esp-emu --thread-sim` 已观察到源码构建 switch/light 的双向
  802.15.4 帧，但 commissioning/join 未完成；相关固件只能按新 evidence
  分层记录，不能通过宿主假值或重试改成 PASS。

完整契约见
[`docs/device-service-api.md`](../docs/device-service-api.md) 和
[`docs/device-service.openapi.yaml`](../docs/device-service.openapi.yaml)。
服务演进路线见
[`docs/simulator-service-architecture.md`](../docs/simulator-service-architecture.md)。

## 主要工具入口

| 路径 | 职责 |
| --- | --- |
| `tools/device_service.py` | session、lease、runtime 编排、证据和状态机 |
| `tools/worker_registry.py` | 单 worker 的持久化 heartbeat、generation、lease、drain/resume 和重启失败分类 |
| `tools/worker_directory.py` | 远程 worker identity/generation 注册、stale/drain/stop、capability 与有界结果目录 |
| `tools/worker_queue.py` | 持久 job queue、idempotency、capability 匹配、lease/heartbeat、超时重试和 supervisor 回收 |
| `tools/worker_auth.py` | 严格 token-file、worker key 派生、HMAC 请求签名、时间戳、nonce replay cache 和 identity binding |
| `tools/worker_agent.py` | HTTP-only worker executor、control/runtime API 双端点、token/TLS `SIGHUP` reload、atomic generation-pointer auto reload/receipts、generation、claim、heartbeat、session 执行、evidence 和 result |
| `tools/transport_security.py` | TLS 1.2+ server/client context、服务端证书校验、可选 client CA、mTLS 客户端证书 |
| `tools/firmware_manifest.py` | ZIP/目录/WebBurner/M5Burner/flasher_args 导入与脱敏 eFuse 安全摘要 |
| `tools/firmware_static_review.py` | 脱敏 URL/凭据/高熵审查和 SPDX/CycloneDX SBOM 摘要 |
| `tools/firmware_analysis.py` | ESP image、分区、应用描述和静态分析 |
| `tools/firmware_filesystems.py` | LittleFS、只读 FAT12/16/32 和 ESP-IDF SPIFFS 文件清单、LUT/对象页校验、哈希、敏感路径脱敏和 SPDX 提取 |
| `tools/fetch_firmware.py` | 公开 M5Burner 固件查询、下载和缓存 |
| `tools/user_firmware_matrix.py` | 热门用户固件仿真矩阵 |
| `tools/network_policy.py` | isolation、egress、controlled DNS、Host allowlist 和 pcap 策略 |
| `tools/network_egress.py` | nftables 精确 IP/端口规则、veth/NAT gateway、能力检查和清理 |
| `tools/network_fabric.py` | private namespace、双 guest QEMU socket L2 switch、DHCP reservation 和 TAP/bridge primitive |
| `tools/network_sandbox.py` | Linux private net/mount namespace、controlled DNS 与 fail-closed runner |
| `tools/network_lane.py` | esp-emu 网络/Provisioning 诊断 lane |
| `tools/pcap_summary.py` | pcap 元数据和 payload hash 摘要 |
| `tools/ble_probe.py` | 外部 BLE controller/peer 与 GATT 验证；支持同一 peer process 多轮 disconnect/reconnect |
| `tools/storage_policy.py` | 历史、Flash 和缓存回收策略 |
| `tools/project_snapshot.py` | 从 catalog、profile、peripheral、firmware evidence 和 Backlog 生成并校验项目快照 |
| `../tests/network/tls_allowlist/` | 测试 CA、HTTPS Host allowlist、200/403、pcap 断言和 AES/GDMA 回归证据 |
| `../tests/network/egress_allowlist/` | 精确 IP/端口、拒绝端口/拒绝 IP、veth/NAT 和清理验证 |
| `../tests/network/idf_dhcp_renewal/` | ESP-IDF 主动 renew、DORA/renew transaction、lease 与 HTTP 联合验证 |
| `../tests/network/lab_fabric/` | 两台 StickS3 QEMU guest 的 DHCP、guest TCP、双侧 pcap、宿主隔离和 host TAP/bridge primitive |
| `../tests/network/worker_lifecycle/` | 真实 StickS3 QEMU lease 的 heartbeat、drain/resume、进程组清理和下一代 abandoned lease 分类 |
| `../tests/network/worker_tls/` | 真实 HTTPS/mTLS 进程、证书/客户端证书拒绝/通过、Bearer + worker HMAC、SIGHUP rotation + active-request drain + bounded overlap/final cutover、真实 QEMU job 和 unified StickS3 job over mTLS |

## 目录服务 API

`serve.py` 除 `/api/v1` 外还暴露：

```text
GET /api/peripherals
GET /api/peripherals/<device>
GET /api/peripheral-interfaces
GET /api/peripheral-interfaces/<model>
```

内容来自 peripheral contract 和 inventory，可取得硬件需求、组件芯片、总线、
地址、QOM、数据面、evidence、blocker、完成状态和设备的 `runtime_cases`。

## 显示协议

`m5emu-shared-v1`：

1. 固件启动时输出 `M5EMU:SHARED=0x........`；
2. 共享结构头部提供 magic、宽高、framebuffer 地址和 frame sequence；
3. worker 通过 `read_memory` 分块读取 framebuffer；
4. 设备页按 RGB565 解码到 canvas。

没有该协议的固件仍可运行并显示 UART，但设备页会明确显示板级 framebuffer
尚未适配。QEMU unified 路径优先使用 QEMU framebuffer，不依赖该协议。

## 验证

```bash
PYTHONPATH=platform/tools python3 -m unittest discover \
  -s platform/tests -p 'test_*.py'
python3 platform/tools/runtime_coverage.py --check
python3 platform/tools/peripheral_catalog.py --check
python3 platform/tools/qemu_profiles.py --check
python3 platform/tools/project_snapshot.py --check
```

平台测试中的 `test_docs_consistency.py` 还负责检查关键文档、相对链接、API
版本和设备计数，防止旧状态重新写回当前入口。
