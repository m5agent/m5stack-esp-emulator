# Platform

Last reviewed: `2026-10-26`

一页理解代码阅读顺序、成熟度和下一步，见
[`docs/engineering-handoff.md`](../docs/engineering-handoff.md)。

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
| `qemu-esp32s3` | 当前 ESP32-S3 设备集合（数量见自动快照） | 产品主路径：板级外设、WiFi MAC/DMA、UART HCI BLE |
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
- 两个 veth 连接 network namespace 的 worker-local StickS3 QEMU 执行：
  central control service 负责 claim/heartbeat/result，worker namespace 内
  独立 Device Service 负责 artifact/firmware、QEMU、serial/frame/QOM
  evidence 和 cleanup；
- 三个独立 Docker 容器对中，central 与 worker-local runtime/QEMU 通过
  user-defined bridge 完成真实 job/evidence、三工件哈希和 QEMU/container/
  bridge cleanup；仍共享 one Docker daemon，不是物理跨主机；
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
- Linux private net/mount namespace、controlled DNS A/AAAA/CNAME、
  fail-closed isolation、TLS/Host allowlist fixture 和 SoftAP `hostfwd`
  诊断。

当前边界：

- `core2-native-hci` 是规范产品路径，`core2-native-vhci` 只保留为显式
  GDB 诊断/兼容路径。当前虚拟设备门禁覆盖 board、WiFi/公网、外部 GATT、
  reconnect、active-BLE hold、PSRAM、frame/QOM、pcap、evidence、active-stop
  和当前服务容量内的并发；精确轮次、哈希、资源数值和失败 control 只查
  [验证证据台账](../docs/validation-ledger.md)与
  [Core2 native-HCI 专题](../docs/core2-native-hci-backend.md)。
- `m5core2` 提供 QOM 8 MiB PSRAM 和 DRAM1 32 KiB MMU 页；普通 heap 仍是
  4 MiB，upper bank 通过 MMU remap 验证。虚拟容量不证明物理 PSRAM/cache
  timing、持续吞吐或电气行为。
- bit-exact Espressif BT controller/baseband、大于当前服务容量、active-stop
  之外的 teardown 和真机仍未完成。bounded-TCG host-memory 结论只覆盖已测试
  的长稳 workload。
- Core2 legacy UIFlow 的 shared I2C、equal-deadline timer 和 TIMG WDT-mask
  已分别修复；同一固件仍有 normal-WDT `TG0WDT_SYS_RESET`/reset PC `0`。
  QIO bulk-read 和关闭 WDT 只是诊断，下一步必须在 SSI/m25p80 数据面内实现
  高效转发并解释 cross-core/DPORT 交接。
- Tab5 通过 `esp-emu` 单独接入，外设状态明确为 `partial`。
- CardputerZero 不由 `/api/v1` 管理。
- trusted-host 网络 namespace 不是恶意固件沙箱。本地 worker identity、
  heartbeat、drain/resume 和重启租约分类，以及远程 worker 注册目录已实现；
  durable job queue 已支持幂等提交、claim/lease、expiry retry 和 worker
  失联回收；本地 QEMU/QMP 控制面已完成 ownership 校验后的 reattach。
  同主机 HTTP executor、worker-local QEMU、worker HMAC、可验证
  HTTPS/mTLS、真实 QEMU 和 unified StickS3 job over mTLS、SIGHUP rotation
  + activity drain + bounded credential overlap、evidence ZIP/SHA256 回报，
  以及 generation-pointer 同主机双 worker 自动迁移和 secret-free receipts
  已实现；trusted-host unified HTTP/BLE companion continuity 也已完成。
  active-token multicast discovery 覆盖同一广播域；跨子网/NAT worker 可从
  HMAC-authenticated unicast discovery seed 获取同一 beacon，两个独立子网、
  IPv4 forwarding、masquerade、rotation 和 cleanup 已在 privileged Linux
  Docker fixture 中重复通过。物理跨主机 QEMU executor/reattach、
  namespace-managed/Tab5/cross-host companion、连续 evidence 流、生产
  secret manager/多机调度和 VM 隔离仍未完成。
- controlled DNS 与 TLS/Host allowlist 已在 Linux private namespace 下
  PASS，QEMU patch `0027` 闭合 AES/GDMA 外部内存读取；`egress=allowlist`
  已在同一隔离路径验证有界 IPv4/IPv6 地址或 CIDR/协议/端口、双栈
  veth/NAT、IPv6 neighbor control 和清理。controlled resolver 支持
  exact A/AAAA、显式绑定 domain suffix 与最多 8 跳 CNAME chain；每个
  alias/terminal/answer 必须受 policy 和 allowed endpoint 约束。CNAME
  resolver fixture 与三个独立 Device Service lease 均 PASS；后三者由同一
  stock UIFlow2 guest 跟随 CNAME terminal A、完成 allowed HTTP、拒绝未
  允许名称/端口，并保留 DNS/HTTP/pcap/cleanup。上述内容仍不等于任意公网
  域名解析、guest IPv6 默认能力或恶意固件沙箱。
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
| `tools/worker_agent.py` | HTTP-only worker executor、control/runtime API 双端点、按剩余预算限时的 reconnect、network/409 lease fence、token/TLS `SIGHUP` reload、atomic generation-pointer auto reload/receipts、generation、claim、heartbeat、session 执行、evidence 和 result |
| `tools/transport_security.py` | TLS 1.2+ server/client context、服务端证书校验、可选 client CA、mTLS 客户端证书 |
| `tools/firmware_manifest.py` | ZIP/目录/WebBurner/M5Burner/flasher_args 导入与脱敏 eFuse 安全摘要 |
| `tools/firmware_static_review.py` | 脱敏 URL/凭据/高熵审查和 SPDX/CycloneDX SBOM 摘要 |
| `tools/firmware_analysis.py` | ESP image、分区、应用描述和静态分析 |
| `tools/firmware_filesystems.py` | LittleFS、只读 FAT12/16/32 和 ESP-IDF SPIFFS 文件清单、LUT/对象页校验、哈希、敏感路径脱敏和 SPDX 提取 |
| `tools/fetch_firmware.py` | 公开 M5Burner 固件查询、下载和缓存 |
| `tools/user_firmware_matrix.py` | 热门用户固件仿真矩阵 |
| `tools/sd_image.py` | 确定性 FAT32+MBR / FAT16 superfloppy SD fixture 生成器 |
| `tools/nvs_image.py` | 确定性 NVSv2 namespace/string fixture 生成器 |
| `tools/network_policy.py` | isolation、egress、controlled DNS、Host allowlist 和 pcap 策略 |
| `tools/network_egress.py` | nftables 精确 IP/端口规则、veth/NAT gateway、能力检查和清理 |
| `tools/worker_discovery.py` | HMAC multicast beacon 与 unicast seed beacon 的签名、TTL、来源和 URL 校验 |
| `tools/worker_discovery_seed.py` | 为无法接收 multicast 的 worker 提供 signed unicast discovery beacon |
| `tools/network_fabric.py` | private namespace、双 guest QEMU socket L2 switch、DHCP reservation 和 TAP/bridge primitive |
| `tools/network_sandbox.py` | Linux private net/mount namespace、controlled DNS 与 fail-closed runner |
| `tools/network_lane.py` | esp-emu 网络/Provisioning 诊断 lane |
| `tools/pcap_summary.py` | pcap 元数据和 payload hash 摘要 |
| `tools/ble_probe.py` | 外部 BLE controller/peer 与 GATT 验证；支持同一 peer process 多轮 disconnect/reconnect |
| `tools/storage_policy.py` | 历史、Flash 和缓存回收策略 |
| `tools/project_snapshot.py` | 从 catalog、profile、peripheral、firmware evidence、Backlog 和全量 Markdown 清单生成并校验项目快照；区分权威页与委派文档 |
| `../tests/network/tls_allowlist/` | 测试 CA、HTTPS Host allowlist、200/403、pcap 断言和 AES/GDMA 回归证据 |
| `../tests/network/dns_cname_chain/` | Controlled resolver 的 bounded CNAME chain、A/AAAA/CNAME encoding、NXDOMAIN 和非法图拒绝 |
| `../tests/network/cname_guest_lifecycle/` | 同 guest CNAME→terminal A→HTTP、denied name/port、pcap、namespace cleanup 和三次独立 lease 复现 |
| `../tests/network/egress_allowlist/` | 精确 IP/端口、拒绝端口/拒绝 IP、veth/NAT 和清理验证 |
| `../tests/network/worker_discovery_seed/` | 两个独立子网、NAT、unicast seed、错误/旧 token、rotation 和清理验证 |
| `../tests/network/worker_partition_fencing/` | worker→control 断网、bounded heartbeat failure、OS process/真实 QEMU PID reap、lease expiry/requeue 和 retry 完成 |
| `../tests/network/idf_dhcp_renewal/` | ESP-IDF 主动 renew、DORA/renew transaction、lease 与 HTTP 联合验证 |
| `../tests/network/lab_fabric/` | 两台 StickS3 QEMU guest 的 DHCP、guest TCP、双侧 pcap、宿主隔离和 host TAP/bridge primitive |
| `../tests/network/worker_lifecycle/` | 真实 StickS3 QEMU lease 的 heartbeat、drain/resume、进程组清理和下一代 abandoned lease 分类 |
| `../tests/network/worker_cross_container/` | 两个独立 Docker 容器、user-defined bridge、central queue/directory、worker-local runtime/QEMU、terminal evidence 和 container/network cleanup |
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

平台测试中的 `test_docs_consistency.py` 是兼容入口；实际契约按领域位于
`test_docs_index_contract.py`、`test_docs_current_state_contract.py`、
`test_docs_core2_runtime_contract.py`、`test_docs_firmware_security_contract.py`
和 `test_docs_network_worker_contract.py`。它们共同检查关键文档、相对链接、
API 版本、生成计数和旧状态回流；退役说法由
`platform/tests/fixtures/stale_doc_claims.json` 结构化维护。
