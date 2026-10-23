# 代码与验证入口地图

日期：`2026-10-24`

本文说明代码从哪里进入、运行时如何组织、证据由哪条测试产生，以及修改时应
同时更新哪些文档。当前能力结论只看
[项目当前状态](project-status.md)，未完成事项只看
[项目 Backlog](project-backlog.md)。完整文档分类和新鲜度规则见
[文档导航](README.md)。

## 单一事实源

| 问题 | 权威入口 |
| --- | --- |
| 文档应从哪里读、哪些是历史页 | [文档导航与新鲜度规则](README.md) |
| 现在到底支持什么 | `devices/catalog.source.json`、`platform/peripherals/catalog.json`、最新测试与 [项目当前状态](project-status.md) |
| 还有什么没做 | [项目 Backlog](project-backlog.md) |
| Device Service 如何调用 | [Device Service API](device-service-api.md) 与 [OpenAPI](device-service.openapi.yaml) |
| 单 lease 设备验收标准 | [统一设备运行时契约](unified-device-runtime.md) |
| 固件如何规范化和拒绝 | [固件清单与 WebBurner 导入](firmware-manifest.md) |
| 网络如何隔离和取证 | [网络模拟方案](network-simulation-plan.md)、[网络诊断 lane](network-lane.md) |
| Core2 如何进入 QEMU 内部 HCI relay | [Core2 native HCI backend](core2-native-hci-backend.md) |
| 代码入口和证据目录 | 本文 |

旧的启动排障、渲染分析和计划文档保留为历史证据，不应覆盖上述当前状态。

## 代码目录

| 目录 | 职责 | 是否产品入口 |
| --- | --- | --- |
| `platform/tools/` | Device Service、固件导入/审查、网络策略、存储、QEMU profile 和目录生成 | 是 |
| `platform/tests/` | 平台单元/契约测试；`test_docs_consistency.py` 防止文档和 API 漂移 | 是 |
| `platform/peripherals/` | 芯片模型登记、运行时 coverage、设备/模型模板和完成门禁 | 是 |
| `platform/qemu/` | QEMU machine、runtime profile、资产和 blocker 注册表 | 是 |
| `patches/` | 可重放的 QEMU/板级补丁源；必须从匹配 worktree 生成和反向验证 | 是 |
| `tests/uiflow2/` | 外设、UI、统一运行时、Core2 无线和证据包 | 是 |
| `tests/network/` | namespace、DNS、TLS、错误密码、radio/AP 重连和 Core2 网络夹具 | 是 |
| `tests/firmware/` | FirmwareManifest、静态审查和文件系统清单证据 | 是 |
| `devices/` | 源设备清单、生成后的设备档案、固件来源和说明 | 是 |
| `platform/web/` | 设备目录、Live session、输入和 3D 外壳 | 是 |
| `platform/runtime/wasm/` | 固定版本的第三方 `esp-emu` 运行时资产 | 仅 Tab5/诊断后端 |
| `records/` | 仓内历史调查快照；不代表当前状态 | 否，历史证据 |
| `.work/` | 本地 QEMU、ROM、工具链、固件和缓存，不提交 | 否，运行时资产 |

代码和文档发生冲突时，优先级是：本次实测 evidence 与同 commit 生成物 >
源 catalog/profile/API 契约 > `project-status.md` > 专题说明 > 历史文档。

## 平台工具完整清单

下表中的 `platform/tools/*.py` 都由文档测试检查，新增顶层工具时
`platform/tests/test_docs_consistency.py` 会要求同步本页。

| 路径 | 职责 | 主要调用方 |
| --- | --- | --- |
| `platform/tools/serve.py` | HTTP/静态页面入口和 `/api/v1` 路由 | `./start.sh`、浏览器、Agent |
| `platform/tools/device_service.py` | lease、会话、运行时、证据和生命周期主编排 | `serve.py`、测试、固件矩阵 |
| `platform/tools/storage_policy.py` | 历史、Flash 和缓存保留/回收策略 | Device Service |
| `platform/tools/xtensa_elf_symbols.py` | 从 ELF32 LE Xtensa 符号表严格解析 Core2 native-VHCI 固定地址 | Device Service、Core2 runners |
| `platform/tools/fetch_firmware.py` | 查询、校验、下载和缓存公开 M5Burner 固件 | 本地准备、固件矩阵 |
| `platform/tools/firmware_manifest.py` | merged/segmented/ZIP/WebBurner 导入和 manifest | CLI、Device Service |
| `platform/tools/firmware_analysis.py` | ESP image、分区、应用描述和静态镜像分析 | manifest、矩阵 |
| `platform/tools/firmware_filesystems.py` | LittleFS 与 FAT12/16/32 只读清单、哈希和 SPDX | manifest |
| `platform/tools/firmware_static_review.py` | 脱敏 URL/凭据/高熵审查、SBOM 摘要 | manifest |
| `platform/tools/user_firmware_matrix.py` | 热门公开固件经 Device Service 的批量仿真 | 回归操作员 |
| `platform/tools/network_policy.py` | isolation/egress/DNS/TLS/pcap 策略校验 | Device Service |
| `platform/tools/network_egress.py` | 精确 IPv4 IP/协议/端口、veth/NAT 和清理 | Device Service、隔离测试 |
| `platform/tools/network_sandbox.py` | Linux private net/mount namespace 与 controlled DNS | 隔离 runner、worker |
| `platform/tools/network_lane.py` | `esp-emu` 网络诊断与 SoftAP provisioning lane | CLI、Device Service |
| `platform/tools/pcap_summary.py` | pcap flow/DNS/DHCP/ARP 和 payload hash 摘要 | Device Service、测试 |
| `platform/tools/ble_probe.py` | 外部 BLE peer、scan/connect/GATT 验证 | unified/BLE runners |
| `platform/tools/hci_stream.py` | H4 HCI command/event/ACL 分包工具 | BLE runners、测试 |
| `platform/tools/qemu_network_preflight.py` | 检查 QEMU user-net/网络后端能力 | 部署和测试 |
| `platform/tools/qemu_profiles.py` | 检查/查询 machine、profile、runtime 和资产 | CI、设备中心 |
| `platform/tools/peripheral_catalog.py` | 检查设备硬件需求、模型、blocker 和覆盖 | CI |
| `platform/tools/peripheral_inventory.py` | 生成设备中心可消费的外设/控制清单 | `serve.py`、设备页 |
| `platform/tools/runtime_coverage.py` | 检查 simulated 模型到设备级运行证据的映射 | CI |
| `platform/tools/runtime_interfaces.py` | 从 evidence/case 生成 QOM、输入和文件接口 | 设备中心 |
| `platform/tools/generate_catalog.py` | 从源 catalog 生成设备 JSON/README | 发布与 CI |
| `platform/tools/export_bundle.py` | 导出可移植设备/运行时资产包 | 部署 |

## 测试入口归属

| 入口 | 负责范围 | 何时运行 |
| --- | --- | --- |
| `platform/tests/` | API、catalog、manifest、network、文档和工具契约 | 每次代码改动 |
| `tests/uiflow2/run_device_matrix.py` | 设备首帧、输入、烧录和板型 smoke | 设备/固件 profile 改动 |
| `tests/uiflow2/run_profile_ui_test.py` | 单 profile UI 回归开发 | 显示/输入改动 |
| `tests/uiflow2/run_peripheral_matrix.py` | 控制器/总线/驱动/API 外设数据面 | 外设改动、里程碑全矩阵 |
| `tests/uiflow2/unified_*/` | 单 guest board + WiFi + BLE 设备切片 | unified profile 或共享 radio 改动 |
| `tests/network/` | namespace、DNS/TLS、精确 egress、DHCP renewal 和 radio/AP 重连 | 网络策略/运行时改动 |
| `tests/firmware/evidence-*.json` | 固件导入、静态 review、LittleFS/FAT 证据 | manifest/filesystem 改动 |
| `tests/cardputer_zero/` | 独立 Linux ARM64 后端 | CardputerZero 改动 |

`run_profile_ui_test.py`、`run_peripheral_matrix.py` 和直接 QEMU 启动是仓库
回归开发入口；Agent 触发的普通固件功能测试必须走 Device Service，避免产生
不可观察、不可保留的临时结果。

## 当前代码组织债务

2026-10-24 的静态盘点显示：

| 位置 | 规模/现象 | 处理原则 |
| --- | --- | --- |
| `platform/tools/device_service.py` | 约 6840 行，覆盖 7 类生命周期职责 | 按 `SVC-03` 拆存储、runtime adapter、evidence 和 history；拆分前先锁 API/evidence 契约 |
| `platform/tests/test_device_service.py` | 约 3660 行 | 跟随后续 service 模块拆分，不先做无语义的测试改名 |
| `tests/uiflow2/run_peripheral_matrix.py` | 约 2900 行 | case registry、输入注入和断言可拆；每个设备 probe 仍保留设备本地证据 |
| `tests/uiflow2/unified_*/` | 12 个 profile 有相似 board/WiFi/BLE 外壳 | 先抽无设备语义的 transport/evidence helper；不要用一个万能 probe 吞掉设备差异 |

这些是维护成本，不是当前功能失败。没有 API 契约测试和同路径 evidence
保护时，不做跨文件大重构。

## 运行链路

### Device Service

```text
HTTP / browser
  -> platform/tools/serve.py
  -> platform/tools/device_service.py
       -> device/session catalog
       -> FirmwareStore
       -> DeviceSession / NetworkDeviceSession / Tab5DeviceSession
       -> QEMU or esp-emu process
       -> serial / framebuffer / QMP / QOM / network evidence
       -> retained session directory and evidence ZIP
```

关键模块：

| 路径 | 职责 |
| --- | --- |
| `platform/tools/serve.py` | HTTP 服务、静态页面和 `/api/v1` 路由入口 |
| `platform/tools/device_service.py` | lease、固件存储、会话生命周期、QEMU/esp-emu 编排、证据包 |
| `platform/tools/storage_policy.py` | 会话历史、Flash 保留与缓存 GC |
| `platform/tools/qemu_profiles.py` | QEMU profile、machine、runtime 和资产检查 |
| `platform/web/` | 设备目录、会话观察和浏览器设备外壳 |

`device_service.py` 仍是主要编排热区。修改时应先锁定对外 API 和会话状态机，
用平台单元测试保护，再拆内部模块；不要把尚未验证的控制器逻辑移到 Python
设备服务层。

### 固件输入

```text
M5Burner / WebBurner / ESP-IDF / merged / segmented
  -> firmware_manifest.py
  -> normalized flash + manifest.json
  -> POST /api/v1/firmware (kind=manifest)
  -> capability/security preflight
  -> session
```

| 路径 | 职责 |
| --- | --- |
| `platform/tools/fetch_firmware.py` | 公开 M5Burner 固件查询、校验、下载与缓存 |
| `platform/tools/firmware_analysis.py` | ESP image、分区、应用描述和静态镜像分析 |
| `platform/tools/firmware_filesystems.py` | LittleFS 挂载与 FAT12/16/32 只读解析、文件哈希、敏感路径脱敏和 SPDX 提取 |
| `platform/tools/firmware_manifest.py` | ZIP/目录导入、sparse 补齐、manifest 和 capability mismatch |
| `platform/tools/firmware_static_review.py` | URL/凭据/高熵脱敏审查与 SBOM 摘要 |
| `platform/tools/firmware_manifest.schema.json` | 版本化 manifest schema |
| `platform/tools/user_firmware_matrix.py` | 通过 Device Service 批量运行热门公开固件 |
| `platform/tools/generate_catalog.py` | 从 `catalog.source.json` 生成目录、设备 JSON 和 README |

### 网络与 BLE

| 路径 | 职责 |
| --- | --- |
| `platform/tools/network_policy.py` | `isolation`、`egress`、controlled DNS 和 pcap 策略 |
| `platform/tools/network_egress.py` | exact IPv4 IP/协议/端口、nftables、per-session veth/NAT 和清理 |
| `platform/tools/network_sandbox.py` | Linux net/mount namespace、controlled DNS、lab-only 无路由、allowlist nft 执行和 fail-closed 启动 |
| `platform/tools/network_lane.py` | `esp-emu` 诊断/Provisioning 网络 lane |
| `platform/tools/pcap_summary.py` | flow、DNS、DHCP message/transaction/renewal、ARP、egress scope 和 payload hash |
| `platform/tools/ble_probe.py` | 外部 BLE peer / GATT 验证 |
| `platform/tools/hci_stream.py` | H4 command/event/ACL 分包 |
| `platform/tools/runtime_interfaces.py` | 对外汇总设备、外设和运行时可注入接口 |
| `tests/uiflow2/core2_native_vhci/` | stock Core2 VHCI→Bumble GATT runner |
| `tests/uiflow2/core2_radio_probe/native_vhci_bridge.py` | QEMU GDB H2C/C2H bridge；符号地址来自固定环境变量，GDB 仍负责暂停、callback 注入和 synthetic return |
| `tests/network/tls_allowlist/` | 测试 CA、namespace-local HTTPS gateway、Host 允许/拒绝和 pcap 断言 |
| `tests/network/idf_dhcp_renewal/` | ESP-IDF `netifapi_dhcp_renew()`、Device Service 和 pcap renewal 断言 |
| `tests/network/` | 隔离、错误密码、radio/AP 丢失重连和 Core2 网络夹具 |

QEMU 主路径必须在同一个 guest 内同时具备板级外设、网络和 HCI/BT 数据面。
`runtime=network` 只用于诊断，不能和另一条 QEMU 板级结果拼成整机 PASS。

### 运行时优先级

| 层级 | 入口 | 用途 | 结论边界 |
| --- | --- | --- | --- |
| 产品验收 | `runtime=qemu-unified` + `*-unified` profile | 单 lease、单 guest 的 board/WiFi/BLE/evidence | 当前 S3/C6/Core2 的主路径 |
| 兼容无线 | `qemu-wifi`、`qemu-ble` | 旧 profile 和单选无线诊断 | `qemu-ble` 不应作为新调用默认值 |
| 网络诊断 | `runtime=network` / `network_lane.py` | WiFi/BLE blocker、SoftAP、DNS/TCP/UDP/HCI | 没有同 guest 板级结论 |
| Tab5 例外 | `esp-emulator-native` | P4 rom/ELF、显示、触摸和 ESP-Hosted | `partial`，不是完整 P4 外设模型 |
| 历史实验 | 无服务入口的临时 QEMU worktree、旧 evidence | 根因调查 | 不能写成当前产品能力 |

### 设备契约与 QEMU

| 路径 | 职责 |
| --- | --- |
| `devices/catalog.source.json` | 14 台设备的源清单 |
| `devices/catalog.json` | 生成后的展示/API 清单 |
| `platform/peripherals/catalog.json` | 芯片模型、总线、地址、QOM、注入和数据面 |
| `platform/peripherals/runtime-coverage.json` | 模型到设备级测试证据的映射 |
| `platform/qemu/profiles.json` | machine 与 runtime profile |
| `patches/` | 可提交的 QEMU/板级补丁源 |
| `.work/` | 本机不可提交的 QEMU、ROM、工具链和运行时缓存 |

修改设备或外设后，至少同步源清单、生成目录、外设契约、runtime coverage、
profile、设备级测试和文档；生成目录不得手改成与源清单和校验器不同的状态。

## 验证入口

| 层级 | 命令或入口 | 能证明什么 |
| --- | --- | --- |
| 平台单元/契约 | `platform/tests/` | 解析、目录一致性、API、manifest、网络策略和文档契约 |
| 外设矩阵 | `tests/uiflow2/run_peripheral_matrix.py` | 控制器/总线/驱动/API 的数据面 |
| 单设备统一运行时 | `tests/uiflow2/unified_*` | 单 QEMU guest 的板级、WiFi 和 HCI BLE |
| Core2 stock VHCI BLE | `tests/uiflow2/core2_native_vhci/run_test.py --symbol-source pinned` | ELF 固定符号下，内置-controller 固件边界的外部 NUS GATT 5/5；`gdb` 仅保留作符号查询对照 |
| Core2 unified native VHCI | `qemu-unified/profile=core2-native-vhci`；`tests/uiflow2/unified_core2/run_test.py --ble-transport native-vhci` | Device Service/独立 runner 的同 guest board+WiFi+公网+native-VHCI BLE，符号来自匹配 ELF |
| GDMA external memory + full matrix | `tests/uiflow2/evidence-2026-10-24-gdma-external-memory-matrix.json` | AES/GDMA 外部内存修复后 67/67、274/274，全部首轮无重试 |
| Firmware redacted review | `tests/firmware/evidence-2026-10-23-static-review.json` | URL/访问凭据脱敏、高熵块指纹、SBOM 和真实公开固件 round-trip |
| Filesystem inventory | `tests/firmware/evidence-2026-10-24-filesystem-inventory.json` | StickS3 `sys`/`vfs` LittleFS 文件、大小、哈希和分区摘要 |
| FAT inventory | `tests/firmware/evidence-2026-10-24-fat-inventory.json` | 合成 FAT12/16/32、LFN、循环链、多簇哈希、敏感路径、erased partition 与真实 PaperColor FAT12 样本 |
| 网络隔离 | `tests/network/linux_isolation/` | Linux private namespace、无外部路由、pcap |
| 错误密码/radio 重连 | `network_lane.py`、`tests/network/reconnect_probe/` | 负向认证、radio/AP 移除、scan `1→0→1`、重新 DHCP 和前后 HTTP |
| DNS + TLS/Host allowlist | `tests/network/tls_allowlist/`、QEMU patch `0027` | Linux namespace 下允许域名 A/拒绝 NXDOMAIN、TLS CA、允许 200/拒绝 403 和 pcap PASS |
| Exact IPv4 egress | `tests/network/egress_allowlist/` | nftables 默认 drop、允许/拒绝端口与 IP、`1.1.1.1:80` veth/NAT、namespace/NAT 清理 |
| DHCP renewal | `tests/network/idf_dhcp_renewal/` | guest 调用 renew API；pcap 区分初次 DORA 与后续 REQUEST/ACK，lease/地址/HTTP 联合 PASS |
| 热门用户固件 | `platform/tools/user_firmware_matrix.py` | 公开固件的启动、首帧、输入和串口结果 |
| 公共 API | `/api/v1` Device Service | 可观察、可保留的 session/evidence |

设备级 PASS 至少要有固件 hash、runtime/profile、输入、串口、frame 和对应
数据面证据。进程启动、版本匹配或单条日志不能单独作为应用 PASS。

## 证据优先级

1. 同一固件路径的物理硬件验证。
2. 同一固件路径的 validated virtual-device 验证。
3. 模型/协议单测和静态分析，只作为实现支撑，不单独发布固件结论。

任何虚拟结果都要标记为 virtual-device validation；RF、功耗、声学、光学、
机械和电气结论不能由当前 QEMU/esp-emu 路径替代。

## 文档维护规则

- 当前能力变更：更新 `README.md`、`docs/project-status.md` 和对应专题页。
- 计划或缺口变更：只更新 `docs/project-backlog.md` 或专项 backlog。
- API 变更：同步 `docs/device-service-api.md`、OpenAPI 和 tests。
- 设备/外设变更：同步源清单、生成目录、契约、coverage 和矩阵文档。
- 验证结果：写回测试 evidence 或 `agent-work-logs`，不要只留在会话里。
- 新文档：先登记到 [文档导航](README.md)，并标明它是当前事实、契约、
  专题说明还是历史证据。
- 被推翻的当前结论：在所有当前入口删除旧陈述，在历史页保留原日期并写明
  取代关系；不要只在新页面加一句更正而留下互相矛盾的主入口。
