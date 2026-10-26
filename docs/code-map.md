# 代码与验证入口地图

日期：`2026-10-27`

本文说明代码从哪里进入、运行时如何组织、证据由哪条测试产生，以及修改时应
同时更新哪些文档。当前能力结论只看
[项目当前状态](project-status.md)，未完成事项只看
[项目 Backlog](project-backlog.md)。完整文档分类和新鲜度规则见
[文档导航](README.md)。

## 单一事实源

| 问题 | 权威入口 |
| --- | --- |
| 一页了解代码阅读顺序、成熟度和下一步 | [工程交接总览](engineering-handoff.md) |
| 文档应从哪里读、哪些是历史页 | [文档导航与新鲜度规则](README.md) |
| 当前设备、样本、缺口、Task 和测试规模快照 | [自动项目快照](project-snapshot.md) |
| 现在到底支持什么 | `devices/catalog.source.json`、`platform/peripherals/catalog.json`、最新测试与 [项目当前状态](project-status.md) |
| 还有什么没做 | [项目 Backlog](project-backlog.md) |
| Device Service 如何调用 | [Device Service API](device-service-api.md) 与 [OpenAPI](device-service.openapi.yaml) |
| 外部 Agent 如何提交 Python、配置 Unit 和取证 | [UIFlow 源码到 Unit 会话](unit-agent-api.md) |
| 单 lease 设备验收标准 | [统一设备运行时契约](unified-device-runtime.md) |
| 固件如何规范化和拒绝 | [固件清单与 WebBurner 导入](firmware-manifest.md) |
| 已知模拟器运行时缺口和关闭条件 | [运行时模型缺口登记](runtime-model-gap-register.md) |
| 网络如何隔离和取证 | [网络模拟方案](network-simulation-plan.md)、[网络诊断 lane](network-lane.md) |
| Core2 如何进入 QEMU 内部 HCI relay | [Core2 native HCI backend](core2-native-hci-backend.md) |
| 代码入口和证据目录 | 本文 |

旧的启动排障、渲染分析和计划文档保留为历史证据，不应覆盖上述当前状态。

## 代码目录

| 目录 | 职责 | 是否产品入口 |
| --- | --- | --- |
| `platform/tools/` | Device Service、固件导入/审查、网络策略、存储、QEMU profile 和目录生成 | 是 |
| `platform/tests/` | 平台单元/契约测试与浏览器 upload/SHA256 Node 测试；`test_docs_*_contract.py` 分域防止文档和 API 漂移 | 是 |
| `platform/peripherals/` | 芯片模型登记、运行时 coverage、设备/模型模板和完成门禁 | 是 |
| `platform/units/` | 外接 Unit 官方芯片/协议、主机物理口接线和独立 runtime 状态 | 是 |
| `platform/qemu/` | QEMU machine、runtime profile、资产和 blocker 注册表 | 是 |
| `patches/` | 可重放的 QEMU/板级补丁源；总索引见 `patches/README.md`，精确顺序见各子目录 | 是 |
| `tests/` | 测试分层、evidence 命名和 Agent 功能测试路由；入口见 `tests/README.md` | 是 |
| `tests/uiflow2/` | 外设、UI、统一运行时、Core2 无线和证据包 | 是 |
| `tests/network/` | namespace、DNS、TLS、错误密码、worker continuity 和 Core2 网络夹具；总索引见 `tests/network/README.md` | 是 |
| `tests/firmware/` | FirmwareManifest、静态审查、文件系统、NVS、Core2 PSRAM/flash-IPC 探针和跨厂商运行时证据 | 是 |
| `devices/` | 源设备清单、生成后的设备档案、固件来源和说明 | 是 |
| `platform/web/` | 设备目录、Live session、WebBurner、输入和 3D 外壳 | 是 |
| `platform/runtime/wasm/` | 固定版本的第三方 `esp-emu` 运行时资产 | 仅 Tab5/诊断后端 |
| `records/` | 仓内历史调查快照；不代表当前状态 | 否，历史证据 |
| `.work/` | 本地 QEMU、ROM、工具链、固件和缓存，不提交 | 否，运行时资产 |

代码和文档发生冲突时，优先级是：本次实测 evidence 与同 commit 生成物 >
源 catalog/profile/API 契约 > `project-status.md` > 专题说明 > 历史文档。

## 代码域

顶层工具按职责归为五组；同一组内部可以复用，跨组调用应通过明确的 JSON、
CLI、HTTP 或测试契约，而不是导入对方的内部实现细节。

| 代码域 | 模块 | 入口 / 输出 |
| --- | --- | --- |
| 服务与生命周期 | `serve.py`、`device_service.py`、`worker_registry.py`、`worker_directory.py`、`worker_queue.py`、`worker_auth.py`、`worker_discovery.py`、`worker_discovery_seed.py`、`transport_security.py`、`worker_agent.py`、`storage_policy.py` | `/api/v1`、session/evidence、本地 worker lifecycle、远程注册目录、持久任务队列、worker HMAC、multicast/unicast discovery、HTTPS/mTLS、SIGHUP TLS/token rotation、executor、GC |
| 固件输入与审查 | `fetch_firmware.py`、`firmware_manifest.py`、`firmware_analysis.py`、`firmware_filesystems.py`、`firmware_static_review.py`、`nvs_image.py`、`user_firmware_matrix.py`、`user_firmware_expectations.schema.json` | 公开固件下载、manifest、sdkconfig detected / image-signature observed capability、Secure Boot v2 结构/数学验证、包内 eFuse 摘要与 anti-rollback version 对照、静态/SBOM/文件系统、NVS/SD fixture、SHA-bound UI/headless/network-first 审查预期和批量运行 |
| 网络策略与取证 | `network_policy.py`、`network_egress.py`、`network_fabric.py`、`network_sandbox.py`、`network_lane.py`、`pcap_summary.py`、`qemu_network_preflight.py` | namespace、nftables、双 guest L2、DNS/CNAME/TLS、pcap 摘要 |
| 运行时与设备登记 | `qemu_profiles.py`、`peripheral_catalog.py`、`peripheral_inventory.py`、`runtime_coverage.py`、`runtime_interfaces.py`、`xtensa_elf_symbols.py` | machine/profile、外设契约、coverage、QOM/输入接口、ELF 符号 |
| BLE/发布工具 | `ble_probe.py`、`hci_stream.py`、`generate_catalog.py`、`export_bundle.py` | 外部 peer、H4 分包、生成的设备目录和可移植资产包 |

`platform/tools/*.py` 是服务侧共享实现；`tests/uiflow2/`、`tests/network/`
和 `tests/firmware/` 是运行时/契约验证入口。若只改文档，不重启
`platform/.cache/service`；若改服务代码，按
[部署与运行时资产](deployment.md) 重启匹配进程。

## 平台工具完整清单

下表中的 `platform/tools/*.py` 都由文档测试检查，新增顶层工具时
`platform/tests/test_docs_index_contract.py` 会要求同步本页。

| 路径 | 职责 | 主要调用方 |
| --- | --- | --- |
| `platform/tools/serve.py` | HTTP/静态页面入口和 `/api/v1` 路由 | `./start.sh`、浏览器、Agent |
| `platform/tools/device_service.py` | lease、会话、运行时、证据和生命周期主编排 | `serve.py`、测试、固件矩阵 |
| `platform/tools/guest_console.py` | QEMU UART socket 单写日志、双向有界传输、流控等待与断流报告 | 同 guest UIFlow2 程序接口 |
| `platform/tools/uiflow_runtime.py` | guest raw REPL/raw-paste 传输、编译执行及增量状态标记；不在 host 执行用户代码 | Device Service program、协议测试 |
| `platform/tools/program_revisions.py` | 完整 Python 文件快照的不可变身份、完整性校验与有界存储 | program 执行记录与 evidence |
| `platform/tools/program_packages.py` | 完整源码、字节码依赖与资源的不可变文件包；规范路径、内容哈希和有界磁盘存储 | `files`/`revision_id` program请求、公共checkpoint、包证据 |
| `platform/tools/preview_service.py` | 稳定Preview/同guest Run协调、串行UART、latest-wins、实际prompt取消与输入/帧身份门禁 | authenticated Preview HTTP、宿主并发负控 |
| `platform/tools/preview_store.py` | SQLite WAL/FULL短事务ledger、幂等原收据、generation和不可复活状态转换、revision pins | Preview协调器、retention |
| `platform/tools/preview_retention.py` | ledger/managed磁盘历史/运行中引用扫描与删除代际门禁；未知分配及损坏元数据fail closed | Device Service cache/history/manual/bulk清理 |
| `platform/tools/micropython_repl.py` | 单 owner 的有限 raw REPL RPC、raw-paste credit、双 EOF 与错误恢复门禁；不 soft reset | guest 文件传输与读回 |
| `platform/tools/uiflow_package_runtime.py` | guest 文件暂存、逐文件 SHA/size 读回、发布与工作目录/托管模块切换 | 同 guest 文件包部署 |
| `platform/tools/mpy_bytecode.py` | 固定官方 v6 容器与指令边界的有界静态检查，递归拒绝 native；非 VM 类型验证或沙箱 | `.mpy` 依赖准入、负控测试 |
| `platform/tools/frame_cache.py` | QEMU预览显式按需single-flight/TTL样本、采集身份和失效门禁；默认fresh取证不进入缓存 | `preview_frame`、条件GET与Live sessions |
| `platform/tools/unit_runtime.py` | 外接 Unit 目录、物理口准入、输入范围与同 guest QOM 读回；不在 Python 执行芯片协议 | Device Service、Unit panel、契约检查 |
| `platform/tools/unit_adc_fixture.py` | 绑定已知应用字节的合成 S3 ADC eFuse 校准与独立数值 oracle；不访问物理硬件 | Angle/Light 测试、会话 eFuse fixture 与证据 |
| `platform/tools/sync_visual_models.py` | 从固定公开模型 commit 显式导入运行源码、许可、Three.js 依赖与 hash 清单 | 外壳更新、来源复核 |
| `platform/tools/worker_registry.py` | 本地 worker identity、独占锁、generation、heartbeat、lease、drain/resume 和重启分类 | Device Service、worker 测试 |
| `platform/tools/worker_directory.py` | 远程 worker 持久目录、identity/generation 冲突、heartbeat/drain/stop、capability 和有界结果元数据 | Device Service、worker directory 测试 |
| `platform/tools/worker_queue.py` | 持久 job queue、idempotency、capability matching、claim/lease/heartbeat、超时重试、terminal result 和 worker 失联回收 | Device Service、worker queue 测试 |
| `platform/tools/worker_auth.py` | 严格 token-file 读取、master token 派生 worker key、时间戳/nonce HMAC、body/path identity binding 和 replay cache | Device Service、worker agent、auth 测试 |
| `platform/tools/worker_agent.py` | HTTP-only worker executor：持久 generation、可达 endpoint 注册、按剩余预算限时的 reconnect/re-register、heartbeat、network/409 lease fence、中央 claim/result、bounded evidence delay，可选独立 runtime API 负责 session、evidence 和 stop | worker CLI、executor/restart/partition/fencing 测试 |
| `platform/tools/worker_discovery.py` | HMAC-authenticated IPv4 multicast beacon、routable unicast seed fetch、TTL/clock validation、token rotation-aware announcer 和 worker discovery client | `serve.py`、`worker_agent.py`、discovery tests |
| `platform/tools/worker_discovery_seed.py` | 独立 unicast seed HTTP service；每次请求重新读取 token 并返回当前 signed beacon | cross-subnet worker bootstrap、deployment |
| `platform/tools/transport_security.py` | TLS 1.2+ server/client context、服务端证书校验、可选 client CA 和 mTLS 客户端证书 | `serve.py`、`worker_agent.py`、TLS tests |
| `platform/tools/storage_policy.py` | 历史、Flash 和缓存保留/回收策略 | Device Service |
| `platform/tools/xtensa_elf_symbols.py` | 从 ELF32 LE Xtensa 符号表严格解析 Core2 native-VHCI 调用地址和 native-HCI hook/HLI 地址 | Device Service、Core2 runners |
| `platform/tools/fetch_firmware.py` | 查询、校验、下载和缓存公开 M5Burner 固件 | 本地准备、固件矩阵 |
| `platform/tools/firmware_manifest.py` | merged/segmented/ZIP/WebBurner 导入和 manifest | CLI、Device Service |
| `platform/tools/firmware_analysis.py` | ESP image、分区、应用描述和静态镜像分析 | manifest、矩阵 |
| `platform/tools/firmware_filesystems.py` | LittleFS、FAT12/16/32 与 SPIFFS 只读清单、LUT/对象页校验、哈希和 SPDX | manifest |
| `platform/tools/firmware_static_review.py` | 脱敏 URL/凭据/高熵审查、SBOM 摘要 | manifest |
| `platform/tools/user_firmware_matrix.py` | 热门公开固件的 SHA-bound UI/headless/network-first Device Service 批量仿真；可加载 session-isolated NVS fixture | 回归操作员 |
| `platform/tools/user_firmware_expectations.schema.json` | review expectation v1 的 JSON Schema；绑定 device/firmware/SHA，禁止明文 WiFi 密码 | matrix、审查工具 |
| `platform/tools/nvs_image.py` | 确定性 NVSv2 namespace/string fixture 生成器 | Device Service、firmware probes |
| `platform/tools/network_policy.py` | isolation/egress/DNS/TLS/pcap 策略校验 | Device Service |
| `platform/tools/network_egress.py` | 精确 IPv4/IPv6 地址/协议/端口、双栈 veth/route/NAT、IPv6 neighbor control 和清理 | Device Service、隔离测试 |
| `platform/tools/network_fabric.py` | private namespace、双 TAP/bridge DHCP primitive 和双 guest QEMU socket L2 switch | lab-fabric runner、CI |
| `platform/tools/network_sandbox.py` | Linux private net/mount namespace、controlled DNS A/AAAA、exact/domain/CNAME answer binding、严格 Host authority 和 bounded CNAME chain | 隔离 runner、worker |
| `platform/tools/network_lane.py` | `esp-emu` 网络诊断与 SoftAP provisioning lane | CLI、Device Service |
| `platform/tools/unified_http_guestfwd.py` | QEMU user-net `guestfwd` 的 per-connection HTTP fixture；避免并发 session 共享宿主 18089 端口 | Device Service、Core2 concurrent runner |
| `platform/tools/pcap_summary.py` | pcap flow/DNS/DHCP/ARP 和 payload hash 摘要 | Device Service、测试 |
| `platform/tools/ble_runtime_limits.py` | BLE reconnect、reconnect delay、hold 和 session-readiness-bound peer scan 的共享上限，以及按 cycle/delay 计算的 readiness workload 预算 | Device Service、BLE probe、Core2 runner |
| `platform/tools/ble_probe.py` | 外部 BLE peer、scan/connect/GATT 验证，以及同一 peer process 内的多轮 disconnect/reconnect | unified/BLE runners |
| `platform/tools/hci_stream.py` | H4 HCI command/event/ACL 分包工具 | BLE runners、测试 |
| `platform/tools/qemu_network_preflight.py` | 检查 QEMU user-net/网络后端能力 | 部署和测试 |
| `platform/tools/qemu_accel.py` | Core2 deterministic TCG、bounded 128 MiB translation buffer 和默认固定 `icount shift=5`；`M5_CORE2_ICOUNT_SHIFT` 仅接受 `auto` 或 `0-10` 作为显式诊断覆盖 | Device Service、Core2 runners、回归测试 |
| `platform/tools/qemu_profiles.py` | 检查/查询 machine、profile、runtime 和资产；`--check` 同时拒绝 profile/catalog 的生成日期及验证日期/状态漂移 | CI、设备中心 |
| `platform/tools/peripheral_catalog.py` | 检查设备硬件需求、模型、blocker 和覆盖 | CI |
| `platform/tools/peripheral_inventory.py` | 生成设备中心可消费的外设/控制清单 | `serve.py`、设备页 |
| `platform/tools/runtime_coverage.py` | 检查 simulated 模型到设备级运行证据的映射 | CI |
| `platform/tools/runtime_interfaces.py` | 从 evidence/case 生成 QOM、输入和文件接口 | 设备中心 |
| `platform/tools/project_snapshot.py` | 从设备、profile、外设、固件 evidence、Backlog、文档新鲜度表和全量 Markdown 清单生成并校验项目快照；分别标记权威页与委派文档的旧复核日期 | CI、交接、文档维护 |
| `platform/tools/generate_catalog.py` | 从源 catalog 生成设备 JSON/README | 发布与 CI |
| `platform/tools/export_bundle.py` | 导出可移植设备/运行时资产包 | 部署 |

Unit 集成的其他入口：`platform/web/unit-visual-mappings.js` 与
`unit-panel.js` 负责控件和模型读回；`tests/units/run_service_cases.py`、
`run_sensor_cases.py`、`run_control_cases.py`、`run_io_cases.py` 分组执行
Device Service 固件探针；`run_live_unit_batch.py` 验证同guest多Unit连续程序，
`run_frame_preview.py` 与 `platform/tests/test_frame_preview.mjs` 分别验证实际预览和浏览器异步隔离。
`preview-client.js`由SessionVisual、ProgramPanel与UnitPanel共享，用权威Preview/Run查询、generation/epoch及冻结context协调输入、完整包编辑、续租/取消/关闭和Run帧；`test_preview_client.mjs`与面板fixture属于宿主/浏览器证据，实际链路由显式opt-in的`test_live_preview_service_browser.mjs`另验。
`DeviceService.create/get_program_revision`提供完整package公共保存/查询；`DeviceSession.run_program`按引用读取且不重建revision。`test_program_revision_api.py`区分宿主HTTP/准入与guest部署，`run_live_package.py --revision-references`以8787实际会话验证原文件包路径；新接口不等于Preview/Run协调器。`serial_read`按offset seek读取有界窗口，任意byte切片的UTF-8 replace解码边界保持。
`test_model_shell.mjs`及`model_shell_probe_helpers.mjs`以有界context/PNG decode核固定vendor、全部printed-artwork种类和公开LED/joint输出；默认配置、census、明确变体和真实guest证据分别标记，不从新增视觉壳子继承Unit协议准入。
`arrayLedFeedback`在默认无binding时只映射全N灯同色，非对称/不可用状态撤回旧颜色并标unknown；`test_uniform_unit_led_feedback.mjs`核真实mounted材质与销毁/失败fixture，`test_live_uniform_led_service_browser.mjs`经可见session核原I2C/RMT驱动、同VM四阶段与默认网页反馈。`device_service._public_device`的`program_features`显式发布入口/字节码/namespace/清理边界；[固定源码与真实guest研究](evidence/2026-10-26-uniform-led-and-program-capabilities/README.md)不等于二进制入口已实现。
`scroll_protocol_probe.py`/`run_live_scroll.py`经同guest原ScrollUnit与raw I2C验证Scroll限定协议；`test_live_scroll_service_browser.mjs`验证真实Web按键、RGB灯与屏幕，`test_scroll_visual_mapping.mjs`另做无guest的可信pointer/零回声/销毁fixture。`0043-unit-scroll-controller.patch`为独立部分C模型；RGB队列、回绕、bootloader/持久化与机械角度不能继承PASS。证据见[Scroll](evidence/2026-10-26-scroll-controller/README.md)。
`scripts/bootstrap-unit-runtime.py` 和
`patches/qemu-unit-runtime/README.md` 固定公开源码、依赖与补丁顺序；
`platform/tests/test_unit_runtime.py` 校验冻结 schema、拓扑和输入准入，
并通过 `_unit_host_control_evidence.py` 核对显式控制类/Web证据契约：原始
准备字段、精确附件接线、同guest数据面、直接PID、原生帧和实际停止历史。
`_unit_host_sensor_evidence.py` 独立核对 sensor/Web 契约：原初始化负控、两组
实际逐字段 POST 后的新鲜串口、adapter/完整 VFS、冻结源与 exact Git baseline
重建、三路非原子帧和停止历史；人工可读性另绑原始 review。
旧主机探针的双观察者契约仍单独保留，功能通过与显示可读性分开记录。
AtomS3R/StickS3/StopWatch 的五款控制类入口是
`tests/units/prepare_host_controls.py`、`run_host_control_cases.py` 与
`host_controls_probe/`：前者按实际参考分区离线打包，后者默认离线核对当前
依赖/工具链和准备产物，只有显式 `--execute` 才经 Device Service 与真实 Web
运行原控制类断言。命令见 `tests/units/README.md`；
`test_host_control_preparation.py` 保护来源漂移与执行前拒绝边界。
六类 I2C sensor 对应 `prepare_host_sensors.py`、`run_host_sensor_cases.py` 与
`host_sensors_probe/`；`test_host_sensor_preparation.py` 与
`test_host_sensor_execution.py` 保护离线准备、准入、来源和实际输入窗口。
十二款 IO 对应 `prepare_host_io.py`、`run_host_io_cases.py` 与
`host_io_probe/`；准备采用实际 reference VFS 和原 IO 驱动/流程，执行默认
离线预检，只在显式执行时经真实 Web/Device Service 运行原断言。Python 3.12
ABI、精确来源冻结、ADC blocker、默认 IR/Buzzer 与显式 custom 边界及 root
独占 API 规则见 [Unit 测试入口说明](../tests/units/README.md)。Thermal 仍走
独立 sensor 路径；`test_host_io_preparation.py`、`test_host_io_execution.py`
保护准备/执行门禁，不把离线结果升级为功能 PASS。
`tests/units/test_sensor_evidence.py` 校验传感器证据故障边界。脚本或构建成功
不等于完整 Unit 功能 PASS；结果链接到项目状态和验证台账。

`tests/units/run_web_cases.py` 通过可选 `web_ui_bridge.py` 和
`platform/tests/unit_web_bridge.mjs` 将同一批 guest probe 的正向输入交给真实
产品控件，并保存实际 HTTP、DOM、模型与 PID/binary 证据；负向 API 路径单列。
`tests/units/check_batch_evidence.py` 使用显式选择清单核对全部 Unit 的
controller、live browser 和 bridge contract 三层，逐项校验 ZIP 与原工件
hash，区分直接 PID 与间接 generation、原驱动与 custom guest，不自动挑选
最新的成功尝试。`test_batch_evidence.py` 覆盖错配、缺件和输入覆盖拒绝。

`tests/units/run_web_recovery.py` 与
`platform/tests/test_live_unit_recovery.mjs` 在一个可见 Button 会话中对实际
产品页面延迟模型加载并丢弃一次松开请求，核对画面保留、实际控制器状态、
guest GPIO 串口、自动松开补偿及正常手势无额外 POST。测试只改变网络交付时序，
不替换 guest 或输入/读回数据；结果需要独立 evidence，不继承批次功能结论。
`platform/tests/test_frontend_recovery.mjs` 在 CI 中检查异步 owner、异常清理与
松开补偿的确定性故障边界；内存 API/DOM fixture 不作为实际会话证据。

`platform/web/unit-annotations.js` 在交互画布外显示静态 Unit 的实时读数，
以实际 sensor anchor 与同号标签关联。数值需同时满足冻结 session 定义、
live 响应、guest-QOM 单元来源、running/available 和字段范围；不从 pending
输入或目录默认值补数值。`test_unit_annotation_contract.mjs` 在 CI 中验证来源、
方向、范围及可选读数异常不影响输入确认。`tests/units/run_annotation_cases.py`
和 `platform/tests/unit_annotation_bridge.mjs` 复用原 service/sensor/io guest，
仅 `--execute` 才创建可见会话，核对实际 HTTP/控制器/DOM、停止前 ZIP 和终态
清值；默认 preflight 不创建会话。几何部件绑定覆盖与读数展示是独立层级。
`tests/units/annotation_contract.py` 约束十二款 rail 的阶段、单位、原 guest
读数、严格输入 POST 与新鲜度；Light 首次 false 的无操作必须有真实先前 GET。
Buzzer 的定时零必须先于后续手动写入；显式 custom wrapper 适配位于
`patches/uiflow2-unit-buzzer/`，默认原驱动与补丁结果分开记录。

`tests/units/prepare_host_sensors.py`、`run_host_sensor_cases.py` 和
`host_sensors_probe/` 是三主机六传感器的准备/执行边界。完整 VFS、原驱动、
初始化/负控/采样链和实际配置逐项绑定；未准入组合在任何 API 前拒绝，
离线产物不扩展运行时或硬件结论。

`platform/web/unit-assembly-layout.js` 只为已检查的 CoreS3 单层紧凑 HUB 装配
提供外观布局，使用公开 unitFrame/cable API、真实尺寸与端口坐标；不改总线、
输入或厂商模型几何。adapter 对可选布局失败隔离，范围外保持原 pose。
所有新浏览器/执行冻结清单纳入该依赖，历史源冻结保持原样。
`unit_web_bridge.mjs` 的长卡片取图使用有界 CDP document clip，避免元素截图
二次滚动造成 sticky 导航遮挡；真实标题命中、完整 PNG 与旧实现负控分别核对。

## 测试入口归属

| 入口 | 负责范围 | 何时运行 |
| --- | --- | --- |
| `platform/tests/` | Python API/契约与 Node SHA256/upload client 测试 | 每次代码改动 |
| `platform/tests/test_docs_*_contract.py` | 文档契约分域：`test_docs_index_contract.py`、`test_docs_current_state_contract.py`、`test_docs_core2_runtime_contract.py`、`test_docs_firmware_security_contract.py`、`test_docs_network_worker_contract.py`；兼容入口为 `test_docs_consistency.py`；退役说法由 `fixtures/stale_doc_claims.json` 数据化 | 文档、当前状态、Backlog、API 或 evidence 口径变化 |
| `platform/tools/project_snapshot.py --check` | 校验自动项目快照是否与 catalog/profile/evidence/Backlog 同步 | 状态、设备或 Task 变化后 |
| `platform/tests/test_ble_probe.py` | Bumble no-response HCI compatibility 回归 | `ble_probe.py` controller compatibility 改动 |
| `platform/tests/test_ble_runtime_limits.py` | reconnect cycle/delay 上限与 workload-aware readiness 预算 | BLE 长任务预算或参数范围改动 |
| `platform/tests/test_core2_hci_ack_observability.py` | 绑定 `0010` aggregate/summary/trace 哈希，校验首条 ACK 为空、response→HLI 顺序及“host trace time 不是 guest 虚拟时间”的文档/元数据口径 | Core2 ACK 根因、trace 证据或当前状态描述改动 |
| `tests/uiflow2/run_device_matrix.py` | 设备首帧、输入、烧录和板型 smoke | 设备/固件 profile 改动 |
| `tests/uiflow2/run_profile_ui_test.py` | 单 profile UI 回归开发 | 显示/输入改动 |
| `tests/uiflow2/run_peripheral_matrix.py` | 控制器/总线/驱动/API 外设数据面 | 外设改动、里程碑全矩阵 |
| `tests/uiflow2/unified_*/` | 单 guest board + WiFi + BLE 设备切片 | unified profile 或共享 radio 改动 |
| `tests/uiflow2/core2_native_hci/run_service_5x.py` | 在首个 lease 前冻结 firmware/ELF/QEMU 哈希，通过真实 Device Service API 租用 `core2-native-hci`，支持 hold、reconnect、并发 batches、startup stagger 和 session-overlap 证据，低频采样 host RSS；失败时保留 partial evidence 并汇总 aggregate FAIL。文件名保留历史 `5x` 以维持 evidence/复现路径稳定，实际已参数化为任意 attempts/concurrency | Core2 native-HCI、extended-run/soak/reconnect/concurrency、Device Service profile 或 ELF hook 改动 |
| `tests/uiflow2/core2_native_hci/run_service_teardown.py` | 在 BLE/HTTP companion 仍活跃时 DELETE session，验证 stopped、无错误、companion terminate、QEMU/BLE PID reap、worker lease release，并连续创建下一 session 验证恢复 | Core2 stop/teardown、companion cleanup、worker lease lifecycle 改动 |
| `tests/network/` | namespace、DNS/TLS、精确 egress、DHCP renewal、radio/AP 重连、双 guest lab fabric 和 worker-local QEMU | 网络策略/运行时改动 |
| `tests/network/dns_cname_chain/` | Controlled resolver 的 2-hop chain、A/AAAA chain encoding、CNAME query、NXDOMAIN、非法图与 8 跳边界 | `network_sandbox.py` resolver/CNAME 策略改动 |
| `tests/network/cname_guest_lifecycle/` | 三个独立 Device Service lease 的同一 guest CNAME→A→HTTP、denied-name/port、pcap、namespace cleanup 与 startup failure 诊断 | CNAME guest lifecycle、network evidence ZIP 或 namespace teardown 改动 |
| `tests/network/wrong_password/` | ESP-IDF 错误密码拒绝、重试、no-DHCP/no-HTTP 负向门禁和脱敏 evidence | `network_lane.py` 错误密码 profile 改动 |
| `tests/firmware/evidence-*.json` | 固件导入、静态 review、LittleFS/FAT/SPIFFS/NVS capability 证据 | manifest/filesystem/NVS/capability 改动 |
| `tests/firmware/security_preflight/run_test.py` | 用 synthetic Secure Boot v2 image、sdkconfig、eFuse summary 和篡改 aggregate 对照 Device Service security preflight；任何已声明 enabled 但 profile 未建模的链均 fail closed | security fields、Secure Boot/Flash Encryption preflight 或 schema enum 改动 |
| `tests/firmware/unknown_required_capability/run_test.py` | 对同一 public StickS3 SHA 同时跑 merged/WebBurner baseline、unknown required 和 unknown optional；验证 required 未知时 CLI/import fail closed，optional 仅 warning | capability policy、Manifest importer 或 WebBurner capability 输入改动 |
| `tests/firmware/manifest_policy/run_test.py` | 验证根 `capabilities`/`required`/`optional` 必填、数组边界、signed-image status understatement、eFuse enum、key mismatch 和 secure-version rollback 都 fail closed | Manifest schema、capability policy 或 Security preflight 改动 |
| `tests/firmware/webburner_import_policy/run_test.py`、`platform/tests/test_webburner_import_policy_evidence.py` | 验证 ZIP path 归一/casefold/symlink、文件/目录父子冲突、manifest/sdkconfig/eFuse/flasher/SBOM 唯一性、sdkconfig 明确优先级和多 build SoC 选择都 fail closed | WebBurner/ZIP importer、资源发现或 build 选择改动 |
| `tests/firmware/openai_nvs_precondition/` | 对照空 NVS、Open/WPA2 正确密码和错误密码，绑定 NVS overlay、EAPOL/CCMP、DHCP/DNS/TCP 与 pcap | NVS fixture、generic S3 qemu-wifi、S3 WPA2 或该样本分类改动 |
| `tests/firmware/core2_flash_ipc/run_test.py` | 通过独立 Device Service lease 执行 ESP-IDF CPU1 partition reads；默认校验已知 image/ELF SHA，按 first boot 分类 PASS、interrupt-WDT、spinlock assert，并保存 serial/evidence hash | Core2 flash/IPC、timer/WDT、flash-cache/DPORT 或 `RUNTIME-03` 探针改动 |
| `tests/cardputer_zero/` | 独立 Linux ARM64 后端 | CardputerZero 改动 |
| `platform/tests/test_worker_registry.py` | worker 状态转换、独占锁、重启 abandoned lease 和 recent result | worker 生命周期改动 |
| `platform/tests/test_worker_directory.py` | 远程 worker 注册、持久化、generation、stale/drain/stop、容量和结果元数据契约 | `/api/v1/workers` 或 `worker_directory.py` 改动 |
| `platform/tests/test_worker_queue.py` | job submit/replay、capability、lease、expiry、retry、result/cancel、worker supervisor 和 schema 校验 | `/api/v1/jobs` 或 `worker_queue.py` 改动 |
| `platform/tests/test_worker_auth.py` | path 分类、签名、body tamper、时间窗、generation key 和 nonce replay | `worker_auth.py` 或 handler auth 改动 |
| `platform/tests/test_worker_agent.py` | generation 持久化、job 执行、evidence 保存、失败清理、control restart 重注册/同 lease result、409/network blackhole 后 bounded runtime stop 与 stale result suppression，以及 control/runtime API 请求平面分离 | `worker_agent.py` 或 executor 协议改动 |
| `platform/tests/test_worker_discovery.py` | signed beacon、错误 token/group、过期、URL/包上限、真实 multicast loopback、unicast seed、redirect rejection 和 token verification | `worker_discovery.py`、seed service 或 discovery CLI 改动 |
| `tests/network/worker_discovery_seed/` | 两个 subnet、IPv4 forwarding、masquerade、multicast isolation、unicast seed、错误/旧 token、rotation 和 cleanup | cross-subnet discovery 改动 |
| `tests/network/worker_partition_fencing/` | worker→control blackhole、bounded heartbeat、OS process 与真实 worker-local QEMU PID stop/reap、lease expiry/requeue 和 retry completion | heartbeat/reconnect、lease ownership 或 runtime cleanup 改动 |
| `tests/network/worker_cross_netns/` | 两个 veth 连接 namespace 中的 Bearer+HMAC control plane，以及 worker-local Device Service、StickS3 QEMU、artifact/firmware、evidence、QEMU reap 和 cleanup | worker control/runtime plane、本地 QEMU executor 或 cleanup 改动 |
| `tests/network/worker_cross_container/` | 两个独立 Docker 容器、user-defined bridge、central queue/directory、worker-local runtime/QEMU、terminal evidence 和容器/网络 cleanup | cross-container worker executor、Docker image、bridge 或 runtime asset binding 改动 |
| `platform/tests/test_transport_security.py` | 真实 HTTPS、mTLS 客户端证书、未知服务端证书拒绝和 TLS 参数校验 | `transport_security.py`、`serve.py` 或 `worker_agent.py` TLS 改动 |

`run_profile_ui_test.py`、`run_peripheral_matrix.py` 和直接 QEMU 启动是仓库
回归开发入口；Agent 触发的普通固件功能测试必须走 Device Service，避免产生
不可观察、不可保留的临时结果。

## 当前代码组织债务

静态盘点显示生产代码中没有未处理的 `TODO/FIXME/HACK`，主要债务是文件边界
和测试体积。会随提交变化的模块行数由
[自动项目快照](project-snapshot.md#代码与文档规模)生成，本页不再手写。

| 位置 | 现象 | 处理原则 |
| --- | --- | --- |
| `platform/tools/device_service.py` | `ServiceError`、`DeviceSpec`、三个 session class、`DeviceService`、`ArtifactStore`、`FirmwareStore` 和请求解析仍集中在同一模块；Core2 并发 evidence 还绑定该文件 SHA | 按 `SVC-03` 先锁契约并计划配套 evidence 重跑，再移无状态配置/解析、存储、runtime adapter、evidence 和 history；不得让新代码借用旧 tool hash |
| `platform/tests/test_device_service.py` | 大型 service 契约测试，覆盖多个生命周期和数据面 | 跟随后续 service 模块拆分，不先做无语义的测试改名 |
| `tests/uiflow2/run_peripheral_matrix.py` | 大型 case 注册、输入和断言集合 | case registry、输入注入和断言可拆；每个设备 probe 仍保留设备本地证据 |
| `tests/uiflow2/unified_*/` | S3/C6 与 Core2 radio profiles 有相似的 board/WiFi/BLE 外壳 | 先抽无设备语义的 transport/evidence helper；不要用一个万能 probe 吞掉设备差异 |

这些是维护成本，不是当前功能失败。没有 API 契约测试和同路径 evidence
保护时，不做跨文件大重构。

`SVC-03` 的目标不是一次搬空 `device_service.py`，而是按可回滚边界拆：

1. 锁定并测试 `/api/v1`、session JSON、evidence ZIP、历史恢复和现有公开符号；
2. 提取无状态请求解析、运行参数构造与设备规格加载；
3. content-addressed firmware/artifact store 与 resumable upload；
4. session repository、状态机和历史恢复；
5. QEMU、esp-emu/Tab5、network runtime adapters；
6. serial/frame/QOM/audio/network evidence collector；
7. HTTP handler 与 orchestration facade。

每一步先保留现有 `/api/v1`、session JSON、evidence ZIP 和 stopped-session
恢复契约，再迁移一个边界；禁止在同一变更里同时改 API、存储布局和运行时。

## 运行链路

### Device Service

```text
HTTP / browser
  -> platform/tools/serve.py
  -> platform/tools/device_service.py
       -> worker_registry.py (local process)
       -> worker_directory.py (remote registrations)
       -> worker_queue.py (durable job/lease state)
       <- worker_agent.py (HTTP-only executor)
       <- worker_discovery.py (signed control URL)
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
| `platform/tools/device_service.py` | lease、artifact/firmware 存储、可恢复 chunk upload、会话生命周期、QEMU/esp-emu 编排、证据包 |
| `platform/tools/uiflow_source.py` | 将获准 UIFlow2 reference 的真实 LittleFS VFS 叠加 caller Python，重新挂载核对持久字节、保留原文件并记录源码/镜像/工具链 provenance；不在宿主执行 guest 代码 |
| `platform/tools/worker_registry.py` | 单 worker 的持久化 heartbeat、generation、租约和 drain 状态机 |
| `platform/tools/worker_directory.py` | 远程 worker 持久注册表、identity/generation 校验、stale/drain/stop 和有界结果索引 |
| `platform/tools/worker_queue.py` | 持久任务、幂等提交、能力匹配、worker lease、超时重试和 terminal result |
| `platform/tools/worker_auth.py` | worker-specific HMAC key derivation、request signature、timestamp 和 replay 防护 |
| `platform/tools/worker_agent.py` | 独立 HTTP executor、中央 worker/job heartbeat、可选 worker-local runtime 的 session/evidence/stop 和 result 回报 |
| `platform/tools/worker_discovery.py` | active-token HMAC multicast beacon、过期/来源校验和无硬编码 URL 的 worker bootstrap |
| `platform/tools/storage_policy.py` | 会话历史、Flash 保留与缓存 GC |
| `platform/tools/qemu_profiles.py` | QEMU profile、machine、runtime 和资产检查；验证日期/状态必须与设备目录一致 |
| `platform/web/` | 设备目录、会话观察和浏览器设备外壳 |

`device_service.py` 仍是主要编排热区。修改时应先锁定对外 API 和会话状态机，
用平台单元测试保护，再拆内部模块；不要把尚未验证的控制器逻辑移到 Python
设备服务层。

### 固件输入

```text
M5Burner / WebBurner / ESP-IDF / merged / segmented
  -> platform/web/firmware.html (optional browser path)
  -> firmware_manifest.py
  -> normalized flash + manifest.json
  -> optional resumable /api/v1/artifact-uploads/<id>/chunks
  -> POST /api/v1/firmware/import or /api/v1/firmware (kind=manifest)
  -> capability/security preflight
  -> session
```

| 路径 | 职责 |
| --- | --- |
| `platform/tools/fetch_firmware.py` | 公开 M5Burner 固件查询、校验、下载与缓存 |
| `platform/tools/firmware_analysis.py` | ESP image、分区、应用描述和静态镜像分析 |
| `platform/tools/firmware_filesystems.py` | LittleFS 挂载、FAT12/16/32 与 SPIFFS 只读解析、文件哈希、敏感路径脱敏和 SPDX 提取 |
| `platform/tools/firmware_manifest.py` | ZIP/目录导入、sparse 补齐、content-stable `manifest_id`、sdkconfig detected、低置信度 image-signature observed、Secure Boot v2/eFuse 摘要与 anti-rollback version 对照；known/unknown required capability mismatch fail closed，unknown optional 保持 warning；security aggregate 不能被 sdkconfig、signed/invalid image 或 eFuse 的 enabled 证据 understate |
| `platform/tools/firmware_static_review.py` | URL/凭据/高熵脱敏审查与 SBOM 摘要 |
| `platform/tools/firmware_manifest.schema.json` | 版本化 manifest schema |
| `platform/tools/user_firmware_matrix.py` | 通过 Device Service 批量运行热门公开固件 |
| `platform/tools/user_firmware_expectations.schema.json` | UI/headless/network-first review expectation v1 schema |
| `platform/tools/nvs_image.py` | 生成确定性 NVSv2 namespace/string 配置 fixture |
| [`tests/firmware/`](../tests/firmware/README.md) | FirmwareManifest、静态审查、文件系统、NVS/OpenAI、Core2 PSRAM/flash-IPC 专用探针和跨厂商运行时 evidence |
| `platform/tools/generate_catalog.py` | 从 `catalog.source.json` 生成目录、设备 JSON 和 README |
| `platform/web/firmware.html`、`firmware.js`、`firmware-report.js`、`firmware-upload.js`、`sha256.js` | 浏览器 WebBurner 包上传、流式 SHA256、重试/取消/刷新恢复、manifest 导入、sdkconfig/image capability 来源与 warning 展示 |

### 网络与 BLE

| 路径 | 职责 |
| --- | --- |
| `platform/tools/network_policy.py` | `isolation`、`egress`、controlled DNS、exact Host/domain suffix 和 pcap 策略 |
| `platform/tools/network_egress.py` | 有界 IPv4/IPv6 地址或 CIDR/协议/端口、nftables、per-session 双栈 veth/NAT、IPv6 neighbor control 和清理 |
| `platform/tools/network_fabric.py` | private namespace、双 guest QEMU socket switch、DHCP reservation、TAP/bridge primitive |
| `platform/tools/network_sandbox.py` | Linux net/mount namespace、controlled A/AAAA + label-boundary domain suffix resolver、exact/domain/CNAME explicit answer binding、严格 Host authority、lab-only 无路由、allowlist nft 执行和 fail-closed 启动 |
| `platform/tools/network_lane.py` | `esp-emu` 诊断/Provisioning 网络 lane |
| `platform/tools/pcap_summary.py` | flow、DNS、DHCP message/transaction/renewal、ARP、egress scope 和 payload hash |
| `platform/tools/ble_probe.py` | 外部 BLE peer / GATT 验证；默认一轮，可要求同一 peer 进程连续多轮 |
| `platform/tools/hci_stream.py` | H4 command/event/ACL 分包 |
| `platform/tools/runtime_interfaces.py` | 对外汇总设备、外设和运行时可注入接口 |
| `tests/uiflow2/core2_native_vhci/` | stock Core2 VHCI→Bumble GATT runner |
| `tests/uiflow2/core2_native_hci/` | QEMU native-HCI transport、无 GDB H2C/C2H、完整 GATT、Device Service repeated lease 和 evidence 生成 |
| `tests/uiflow2/core2_radio_probe/native_vhci_bridge.py` | legacy/diagnostic GDB H2C/C2H bridge；不是新调用首选，更不能作为稳定生产证明 |
| `tests/network/tls_allowlist/` | 测试 CA、namespace-local HTTPS gateway、Host 允许/拒绝和 pcap 断言 |
| `tests/network/idf_dhcp_renewal/` | ESP-IDF `netifapi_dhcp_renew()`、Device Service 和 pcap renewal 断言 |
| `tests/network/lab_fabric/` | 两台 StickS3 QEMU guest 的 DHCP、guest TCP、双侧 pcap、宿主隔离和 TAP/bridge primitive |
| `tests/network/worker_lifecycle/` | 真实 StickS3 QEMU lease 的 heartbeat、drain、resume、强杀清理和下一代 abandoned lease 分类 |
| `tests/network/` | 隔离、错误密码、有界 CIDR/dual-stack egress、domain-set、radio/AP 丢失重连和 Core2 网络夹具 |

QEMU 主路径必须在同一个 guest 内同时具备板级外设、网络和 HCI/BT 数据面。
`runtime=network` 只用于诊断，不能和另一条 QEMU 板级结果拼成整机 PASS。

### 运行时优先级

| 层级 | 入口 | 用途 | 结论边界 |
| --- | --- | --- | --- |
| 产品验收 | `runtime=qemu-unified` + `*-unified` profile | 单 lease、单 guest 的 board/WiFi/BLE/evidence | 当前 S3/C6 和 Core2 `core2-native-hci` 的主路径 |
| 兼容无线 | `qemu-wifi`、`qemu-ble` | 旧 profile 和单选无线诊断 | `qemu-ble` 不应作为新调用默认值 |
| 网络诊断 | `runtime=network` / `network_lane.py` | WiFi/BLE blocker、SoftAP、DNS/TCP/UDP/HCI | 没有同 guest 板级结论 |
| Tab5 例外 | `esp-emulator-native` | P4 rom/ELF、显示、触摸和 ESP-Hosted | `partial`，不是完整 P4 外设模型 |
| 历史实验 | 无服务入口的临时 QEMU worktree、旧 evidence | 根因调查 | 不能写成当前产品能力 |

### 设备契约与 QEMU

| 路径 | 职责 |
| --- | --- |
| `devices/catalog.source.json` | 设备源清单；当前数量由自动项目快照读取 |
| `devices/catalog.json` | 生成后的展示/API 清单 |
| `platform/peripherals/catalog.json` | 芯片模型、总线、地址、QOM、注入和数据面 |
| `platform/peripherals/runtime-coverage.json` | 模型到设备级测试证据的映射 |
| `platform/qemu/profiles.json` | machine 与 runtime profile |
| `patches/` | 可提交的 QEMU/板级补丁源 |
| `.work/` | 本机不可提交的 QEMU、ROM、工具链和运行时缓存 |

修改设备或外设后，至少同步源清单、生成目录、外设契约、runtime coverage、
profile、设备级测试和文档；生成目录不得手改成与源清单和校验器不同的状态。

## 验证入口

下表是“源码/测试/证据在什么位置”的索引，不是当前验证快照。表中的
PASS 比例、轮次、资源数值和哈希都只属于所链接的 evidence；新运行应先更新
`validation-ledger.md` 和 evidence，不要求逐行改本表。只有入口、补丁或测试
路径变化时才改这里。

| 层级 | 命令或入口 | 能证明什么 |
| --- | --- | --- |
| 平台单元/契约 | `platform/tests/` | 解析、目录一致性、API、manifest、网络策略和文档契约 |
| 外设矩阵 | `tests/uiflow2/run_peripheral_matrix.py` | 控制器/总线/驱动/API 的数据面 |
| 单设备统一运行时 | `tests/uiflow2/unified_*` | 单 QEMU guest 的板级、WiFi 和 HCI BLE |
| Core2 stock VHCI BLE（legacy diagnostic） | `tests/uiflow2/core2_native_vhci/run_test.py --symbol-source pinned` | ELF 固定地址下验证 GDB/API boundary 交互；单次通过和 `1/2` repeated lease 只用于诊断，不是稳定主路径 |
| Core2 unified native-VHCI（legacy diagnostic） | `qemu-unified/profile=core2-native-vhci`；`tests/uiflow2/unified_core2/run_test.py --ble-transport native-vhci` | 保留兼容和根因对照；GDB 仍控制暂停/注入/return |
| Core2 native HCI `HCI-1` | `patches/qemu-core2-native-hci/`；`tests/uiflow2/core2_native_hci/test_transport.py` | QEMU H4 chardev framing、bounded queue、overflow、peer lifecycle、counters 和 clean shutdown PASS |
| Core2 guest H2C `HCI-2` | `tests/uiflow2/core2_native_hci/test_guest_h2c.py` | 不启动 GDB，从真实 VHCI shared memory 捕获 stock HCI Reset `01030c00` 并转发 peer |
| Core2 C2H callback `HCI-3a` | `tests/uiflow2/core2_native_hci/test_guest_h2c.py --enable-c2h` | 诊断性单包路径：从 ELF 分配 guest buffer，调用注册的 `notify_host_recv` 和 send-available；Reset Complete 后 guest 发出下一条 H2C，targeted `5/5`；不能扩展为产品 C2H 后端 |
| Core2 HLI event `HCI-3b` | `patches/qemu-core2-native-hci/0002-esp32-native-hci-hli-event.patch`；`tests/uiflow2/core2_native_hci/test_hli_event.py`；`evidence-2026-10-24-hli-event-5x.json` | 池分配真实 Reset Complete 经 event 13 和 `ble_transport_to_hs_evt_impl` 交付；guest 从 `01030c00` 前进到 `01011000`，连续 `5/5` |
| Core2 full HCI/GATT `HCI-3b` | `patches/qemu-core2-native-hci/0003-*.patch`、`0004-*.patch`、`0005-*.patch`；`tests/uiflow2/core2_native_hci/run_full.py`；`evidence-2026-10-24-hli-api-gatt-5x.json` | 无 GDB HLI/API-boundary H2C 完成外部 NUS GATT `5/5`；trace 证明旧 24-byte ATT PDU 在默认 MTU 23 被 L2CAP 拒绝，合法 17-byte PDU 命中 ATT/Python/notify/Bumble ACK。post-pass teardown `EIO` 单独记录 |
| Core2 native HCI `HCI-4` | `qemu-unified/profile=core2-native-hci`；`tests/uiflow2/core2_native_hci/run_service_5x.py`；`evidence-2026-10-24-hci4-service-5x.json` | 五个独立 `/api/v1` lease 均通过 frame、27 节点 QOM、WiFi/公网、外部 NUS GATT、pcap 和 evidence ZIP；`gdb_bridge=false`；新 runner 在首 lease 前冻结资产哈希并在结束时拒绝静默资产漂移 |
| Core2 extended-run failure history | `run_service_5x.py --hold-seconds`；`evidence-2026-10-24-extended-run-fail.json` | 历史 `PC=0`、`semphr_give_wrapper` 和 Cache-error 失败保留；被 halt-gated 修复证据取代 |
| Core2 extended-run `CORE2-02` | `0005-*.patch`；`run_service_5x.py --hold-seconds 10`；`evidence-2026-10-24-hci4-halted-gate-5x.json` | 两批独立 `5×10s` hold 合计 `10/10`；每轮 frame/QOM/WiFi/公网/NUS GATT/pcap/evidence 与 HLI health 全部 PASS |
| Core2 60-second hold | `run_service_5x.py --hold-seconds 60`；`evidence-2026-10-24-hci4-hold60-3x.json` | 3 个独立 lease `3/3`；BLE peer 正常关闭后设备保持 running，HLI errors 与队列深度为零 |
| Core2 120-second hold | `run_service_5x.py --hold-seconds 120`；`evidence-2026-10-24-hci4-hold120-2x.json` | 2 个独立 lease `2/2`；每轮 frame/QOM、WiFi、公网、NUS GATT、pcap、evidence 和 HLI health 均 PASS，peer-close queue-full 尾态单独分类 |
| Core2 active-BLE 120-second hold | `run_service_5x.py --hold-seconds 120` + `network.ble_linger_seconds=180`；`evidence-2026-10-24-hci4-active-ble-hold120-2x.json` | 2 个独立 lease `2/2`；peer 在 hold 完成时仍连接，`peer-closed=0`、TX queue 和 last error 均为 0 |
| Core2 active-BLE 600-second hold | `run_service_5x.py --hold-seconds 600` + `ble_runtime_limits.py`；`evidence-2026-10-24-hci4-active-ble-hold600-2x.json` | 2 个独立 lease `2/2`；peer 在 600 秒结束时仍连接，HLI `45/45`、`peer-closed=0`、TX queue 和 last error 均为 0 |
| Core2 active-BLE 7200-second diagnostic hold | `run_service_5x.py --hold-seconds 7200`；`evidence-2026-10-24-hci4-active-ble-hold7200-diagnostic.json` | WiFi/公网/GATT/frame/pcap 保持两小时且 HLI health 正常；QEMU 在 run 中被重编，旧 runner 未冻结启动哈希，因此仅 `DIAGNOSTIC_PASS`；新 runner 已加入输入哈希绑定与 RSS 采样 |
| Core2 artifact-bound 7200-second hold（历史未限容） | `run_service_5x.py --hold-seconds 7200`；`evidence-2026-10-24-hci4-active-ble-hold7200-artifact-bound-1x.json` | firmware/ELF/QEMU 在首 lease 前冻结且无运行期漂移；frame/QOM、WiFi、公网、GATT、pcap、HLI `45/45` 与清理 PASS。QEMU host RSS `744160→1202176 KiB`，后续归因到未限容 TCG translation buffer |
| Core2 bounded TCG memory | `platform/tools/qemu_accel.py`；`run_service_5x.py --hold-seconds 120`；`evidence-2026-10-24-hci4-tb128-hold120-1x.json` | `tb-size=128` 后 120 秒 WiFi/公网/GATT/frame/pcap/HLI 全 PASS；RSS `323600→323584 KiB`、phys footprint `214016→196608 KiB`；最终 7200 秒限容门禁独立保留 |
| Core2 final bounded 7200-second hold | `run_service_5x.py --hold-seconds 7200 --attempts 1`；`evidence-2026-10-25-hci4-active-ble-hold7200-tb128-artifact-bound-1x.json` | 1/1 artifact-bound lease；`bounded_tcg_cache`、frame/QOM、WiFi/公网、active NUS GATT、pcap、HLI `45/45`、active peer、evidence 和 cleanup 全 PASS；240 个资源采样 RSS `323536→252992 KiB`、phys footprint `250880→188416 KiB`，输入与工具哈希无漂移 |
| Core2 PSRAM/QOM and bank switch | `device_service.qemu_runtime_memory()`；`0030-core2-eight-mib-psram.patch`；`tests/firmware/core2_psram_himem/` | CLI `-m 0` 与 QOM-effective `8 MiB` 分开记录；普通 DRAM1 heap 保持 `4 MiB`，upper-bank `esp_himem` MMU remap 3/3 PASS；物理 cache/PSRAM 仍为 `NOT RUN` |
| Core2 flash/IPC timer diagnostic | `tests/firmware/core2_flash_ipc/`；`run_test.py`；`evidence-2026-10-26-core2-flash-ipc-wdt.json`；`evidence-2026-10-26-core2-ccompare-equal-deadline.json`；`0033-esp32-s32c1i-trace.patch` 与 `0034-xtensa-ccompare-equal-deadline.patch` | 最小 probe 捕获到 ISR 写入 `CCOMPARE == CCOUNT` 后旧 QEMU 安排 `2^32` ticks；`0034` 只把相等期限安排到下一 cycle，trace 开/关和 `shift=5`/`auto` 对照通过首启动门禁。早期 4096-byte 局部 buffer 放在 4096-byte task stack 导致错误断言，证据已明确撤销；通过率、哈希和逐轮分类只看 evidence/验证台账 |
| Core2 stateful SSI/QIO | `include/hw/ssi/ssi.h`、`hw/ssi/ssi.c`、`hw/block/m25p80.c`、`hw/ssi/esp32_spi.c`；`0036-ssi-transfer-buf.patch`；`evidence-2026-10-26-core2-ssi-transfer-buf.json` | 新增可选 byte-buffer SSI 接口；m25p80 只在 `STATE_READ` 批量读取并保留 CS/command/address/dummy/wrap 状态，ESP32 SPI 只在 receive-only data phase 使用。批量字节等价与 Core2 UIFlow2 设备组通过，但 normal-WDT legacy 仍失败；该补丁是数据面优化，不是 `RUNTIME-03` 关闭证据。精确计数只查 evidence/验证台账 |
| Core2 unified handoff timeline | `include/hw/misc/esp32_handoff_trace.h`、cross-core、DPORT、TIMG、UART、ESP32 SPI；`0037-esp32-handoff-trace.patch`；`tests/firmware/core2_handoff_trace/` | 默认关闭的 `M5SW_ESP32_HANDOFF_TRACE` 统一记录 virtual time、CPU、guest PC 与四个事件值；timeout/int/reset 始终记录，常规事件可采样。早期 normal-WDT 配置观察到最后 feed 后 `800 ms` timeout，WDT-disabled `sample=1024` 与 trace-off Serial 相同；该 `800 ms` 现象已在三次当前 liveness 配置中标记为未复现而不是当前根因。`audit_elf_bin_mapping.py` 证明 local UIFlow2 v2.5.3 ELF 在三个 CPU0 采样地址上与 public legacy v1.15.4 BIN 字节不一致，因此旧 UART/VM 符号映射被拒绝；BIN 自身控制流落在 cross-core/DPORT Flash-cache disable 候选区，精确函数仍未绑定。`0037` 绑定 `0036` 后的目标树，不是裸上游单补丁；它关闭“缺少统一时间轴”前置条件，不关闭 `RUNTIME-03` |
| Core2 exact-time handoff freeze | `hw/misc/esp32_dport.c`；`0038-esp32-handoff-pause.patch`；`M5SW_ESP32_HANDOFF_PAUSE_NS`；`evidence-2026-10-26-core2-handoff-pause.json` | 在指定 QEMU virtual time 输出 pause marker 后 `SIGSTOP`。14.800 s 早窗口无固定 PC；15.301 s 晚窗口 CPU0 `0x40087980` / CPU1 `0x40084484`，BIN 源码形态匹配 Flash block/cache handshake。不启用 PC sampling，不改变 WDT/controller；仍未证明具体未返回操作 |
| Core2 exact-time state sweep | `0039-esp32-handoff-state-dump.patch`；`run_pause_sweep.py`；`evidence-2026-10-26-core2-handoff-state-sweep.json` | pause 前直接记录 CPU、DCACHE handoff flag、DPORT cache control、cache-sync、SSI 和 cross-core counters；`PAUSE_ACTION=exit` 允许每个独立 lease 采一个 virtual-time 点。14.8/15.3/15.9 s 中 CPU0 等待与 CPU1 变化并存；changed-page 计数停在 6679，而 SSI transaction/cross-core 继续增加，排除两核永久停止 |
| Core2 handoff setter PC trace | `0040-xtensa-handoff-pc-trace.patch`；`run_pc_trace.py`；`evidence-2026-10-26-core2-handoff-pc-trace.json` | 默认关闭的 `M5SW_XTENSA_PC_TRACE` 只记录显式 BIN-bound PC。complete/can-start set/clear 四个 setter 在首轮 reset 前各命中约 4,377 次，stage-0 WDT 首次 timeout 为 5.913935 s、reset 为 15.914787 s；证明 cache handoff 反复完成，不再支持简单永久 deadlock。该 trace 默认关闭且不绑定 ELF 符号名 |
| Core2 WDT liveness | `run_wdt_liveness.py`；`evidence-2026-10-26-core2-wdt-liveness-3x.json`；`test_core2_wdt_liveness.py` | 三次独立 18 秒运行关闭 PC trace、启用 TIMG verbose trace：TG0 stage-0 在约 `5.91 s` 被 mask，TG0 stage-1 在约 `15.91 s` 触发首次 reset；TG1 完成 6,618-6,807 次 feed，最大相邻间隔 8.478-10.410 ms，最后 feed 距 reset 1.779-4.271 ms，`0` 次 TG1 timeout，且 stage-0 后没有 TG0 feed/reconfigure/protect 写入。当前分类为 `BOOTLOADER_TG0_STAGE1_RESET_WITH_TG1_LIVE`；历史 `800 ms` gap 记为 `NOT_REPRODUCED` |
| Core2 WDT-off late state | `0041-esp32-handoff-register-stack-dump.patch`；`run_pause_sweep.py --disable-wdt`；`evidence-2026-10-26-core2-wdt-off-late-state.json`；`test_core2_wdt_off_late_state.py` | 默认关闭的 `M5SW_ESP32_HANDOFF_STACK_WORDS` 增加 A0-A15、PS、对象指针和最多 64-word stack dump。45/120 秒独立 lease 均停在 CPU0 `0x4026306e` waiti idle、CPU1 `0x40100049` spin；Flash/SSI 活动约 44 秒结束。BIN-bound 分析确认 `A2` 是 `lv_disp_buf_t`、`A2+24` 是 `flushing=1`，`A10` 是 display driver、`A10+28` 是空 `wait_cb` |
| Core2 LVGL/SPI completion diagnostic | `0042-esp32-spi-trans-done-irq-diagnostic.patch`；`evidence-2026-10-26-core2-lvgl-spi-wait.json`；`test_core2_wdt_off_late_state.py` | 补 `SPI_SLAVE.TRANS_DONE/TRANS_INTEN` 与 SPI IRQ level，并增加 bounded object-word dump。`0x40100010` 绑定为 LVGL `lv_refr_vdb_flush`，display `flush_cb=0x40174758` 在 WDT-off 中执行，但 completion `0x40174884`/`lv_disp_flush_ready` 未出现；normal-WDT 仍在 TG0 stage-1 reset。该补丁是 partial diagnostic，不关闭 `RUNTIME-03` |
| Core2 legacy timing/cross-core diagnostic | `hw/misc/esp32_crosscore_int.c`、`hw/misc/esp32_dport.c`、`target/xtensa/`；`0035-esp32-timg-wdt-int-ena.patch`；`evidence-2026-10-26-core2-qio-crosscore-diagnostic.json` | `0035` 修正 `INT_RAW & INT_ENA` 的 WDT level 语义。直接 state trace 观察到 flash-op can-start/complete 与 cross-core reason 反复完成；旧 direct-read REPL 在当前重建中未复现。该阶段曾把累计 Flash/cache 吞吐列为候选，后续 `0041/0042` 证明 Flash/SSI 活动有终点，当前边界改为 LVGL/SPI flush completion chain |
| Core2 legacy shared I2C bus | `hw/m5stopwatch/m5core2.c`；`0031-core2-shared-board-i2c.patch`；`M5SW_I2C_CTRL_TRACE=1`；`evidence-2026-10-25-core2-shared-board-i2c.json` | Port trace 证明旧固件在 controller 0 上访问 AXP/RTC；两个 controller 现共享 GPIO21/22 板级 bus，`0x34`/`0x51`/INA `0x40` 均 ACK，原 I2C error 消失。后续 interrupt-WDT 与 black frame 仍为 OPEN；现有 Core2 UIFlow2 设备组保持通过 |
| Core2 legacy WDT timing | `hw/timer/esp32_timg.c`；`0032-esp32-timg-wdt-trace.patch`；`M5SW_TIMG_TRACE=1`；`evidence-2026-10-25-core2-wdt-timing.json` | 默认单会话可持续 feed；并发 lease 会出现 CPU/PC 不固定的 interrupt-WDT。`thread=single`、`thread=multi` 和 `icount shift=0/5` 均不能稳定修复，thread/icount 对照还暴露 TG hardware reset。当前调查点是长同步启动阶段与虚拟时间/宿主调度的组合；数量和哈希只查 evidence/验证台账 |
| Core2 guest PSRAM sustained stress | `tests/uiflow2/unified_core2/main.py`；`run_service_5x.py --require-psram`；`evidence-2026-10-25-core2-psram-sustained-8m-3x120.json` | 3 个独立 120 秒 lease 各完成 35 次 `1 MiB` 全缓冲校验（累计 `105 MiB`），同时执行 30 次受控 HTTP、10 次公网 recheck 并保持 active BLE/frame/QOM/pcap；QOM 8 MiB，物理 cache timing 不在结论内 |
| Core2 guest PSRAM 600-second stress | `run_service_5x.py --require-psram --hold-seconds 600 --attempts 1`；`evidence-2026-10-25-core2-psram-sustained-1x600.json`；pcap summary | 单 lease 600 秒完成 179 次 `1 MiB` 全缓冲校验（约 `179 MiB`）、51 次受控 HTTP、18 次公网 recheck；active BLE/HLI/bounded TCG/frame/QOM/912-packet pcap/evidence/cleanup PASS；物理边界不变 |
| Core2 concurrent unified leases | `run_service_5x.py --attempts 2/3/4/5/6/8 --concurrency 2/3/4/5/6/8 --stagger-seconds 0/30 --hold-seconds 120`；`unified_http_guestfwd.py`；`qemu_accel.py` 固定 `shift=5`；`0007` valid-queue gate；`0008` guest event/ACL preallocation；`0009` `8/4` expanded reserve；`0010` ACK-state observability；五/六/八实例 focused tests；当前 tool hash 的 `2026-10-26` 八实例 A/B | 当前服务容量内的并发门禁覆盖双实例到八实例，包含零错峰和错峰、固定 `shift=5`/BLE-first、PSRAM、WiFi/公网、GATT、frame/QOM、pcap、HLI health 和失败 control。`manifest_id` 语义变更后已用当前 Device Service 重跑两批 `8×120s`，避免复用旧 tool-hash PASS。具体批次、通过率、资源数值和 transient 只查验证台账与 evidence；大于八实例、持续吞吐和其他 teardown 不继承 |
| Core2 same-guest reconnect | `ble_runtime_limits.py:reconnect_workload_timeout_seconds`；`run_service_5x.py --ble-reconnect-cycles 20/30/60/120/121`；`ble_probe.py --reconnect-cycles`；`test_ble_probe.py`；`test_ble_runtime_limits.py`；`test_device_service.py`；`0006-esp32-native-hci-observability.patch`；20/30/60/120 轮、两个 121 harness failure 和 121 three-lease PASS evidence | 3 个独立 stock-firmware lease 各完成 20、30、60、120 轮；120 轮每 lease HLI `3377/3377`、events 2297、ACLs 1080；参数范围 `1–121`，`122` 拒绝。修复固定 readiness 预算和 reconnect-only accelerator 采样后，3 个独立 lease 均完成 `121/121`，同 firmware/ELF/QEMU/工具哈希 |
| Core2 evidence binding | `run_service_5x.py:tool_hashes`；`qemu_accel.py`；`ble_runtime_limits.py`；五/六/八实例 focused tests；`test_qemu_accel.py`；`test_docs_core2_runtime_contract.py` | runner 在首 lease 前记录工具哈希，运行期对 firmware/ELF/QEMU 做漂移检查；每轮同时断言 bounded `tb-size=128` 和实际 `icount shift=5`。五/六/八实例证据还锁定原始 JSON SHA；八实例 control 绑定旧 runner hash，证明阈值是唯一变更。该机制只绑定本轮实现，不替代设备功能或物理等价证据 |
| GDMA external memory + full matrix | `tests/uiflow2/evidence-2026-10-24-gdma-external-memory-matrix.json` | AES/GDMA 外部内存修复后 67/67、274/274，全部首轮无重试 |
| Dual-guest WiFi + latest full matrix | `tests/uiflow2/evidence-2026-10-24-dual-guest-fabric-matrix.json` | patch `0028` 后 67/67、274/274；Cardputer-ADV 键盘 settle 加固后所有 case 首轮 PASS |
| S3 WPA2-PSK data plane | `patches/qemu-m5stack-peripherals/0029-esp32s3-wpa2-psk-data-plane.patch`；`tests/firmware/openai_nvs_precondition/run_test.py`；`tests/uiflow2/evidence-2026-10-25-s3-wpa2-regression.json` | WPA2 RSN、M1-M4、正确/错误密码、CCMP RX、eFuse/NIC MAC 绑定和 unicast DHCP；三组 Device Service session 均绑定同一 OpenAI BIN SHA，AtomS3R/StickS3/CoreS3 定向矩阵 15/15 PASS |
| Firmware redacted review | `tests/firmware/evidence-2026-10-23-static-review.json` | URL/访问凭据脱敏、高熵块指纹、SBOM 和真实公开固件 round-trip |
| Firmware license policy | `tests/firmware/evidence-2026-10-24-license-policy.json` | 声明来源汇总、allowlist/denylist、REVIEW/REJECTED 边界；不是完整源码扫描或法律意见 |
| Filesystem inventory | `tests/firmware/evidence-2026-10-24-filesystem-inventory.json` | StickS3 `sys`/`vfs` LittleFS 文件、大小、哈希和分区摘要 |
| FAT inventory | `tests/firmware/evidence-2026-10-24-fat-inventory.json` | 合成 FAT12/16/32、LFN、循环链、多簇哈希、敏感路径、erased partition 与真实 PaperColor FAT12 样本 |
| SPIFFS inventory | `tests/firmware/evidence-2026-10-24-spiffs-inventory.json` | 8 个声明配置的自包含多索引样本、LUT mismatch/随机损坏负例、ESP-IDF canonical `spiffsgen.py` 镜像和 manifest 脱敏 |
| Resumable artifact upload | `tests/firmware/evidence-2026-10-24-streaming-artifact-upload.json`; `DeviceServiceUnitTests.test_streamed_*`; `DeviceServiceHttpTests.test_streamed_artifact_http_upload` | 连续 offset、per-chunk/final hash、失败 append 回滚、resume、abort 和 abandoned staging GC |
| WebBurner browser intake | `platform/web/firmware.html`; `platform/tests/test_firmware_upload.mjs`; `tests/firmware/evidence-2026-10-24-webburner-ui.json` | 9.44 MiB / 3 chunk、浏览器 SHA256、进度重试、刷新续接、取消清理和 WebBurner ZIP → manifest import |
| Manifest 公共样本/WebBurner | `firmware_manifest.py`；`test_firmware_manifest.py`；`evidence-2026-10-24-public-manifest-web-conformance.json` | 同一公开固件的 merged 与 WebBurner 输入规范化到同一 artifact hash；`camera`-on-StickS3 结构化拒绝；安全证据分层和 HTTP import PASS |
| WebBurner part integrity | `firmware_manifest.py:_web_part_integrity`；`firmware_manifest.schema.json`；`webburner_part_integrity/run_test.py`；`evidence-2026-10-25-webburner-part-integrity.json` | `parts[]` 可选 size/SHA-256/SHA-1/MD5 流式复算；mismatch、非法 digest、冲突声明或未知 integrity 字段在规范化前拒绝；成功 manifest 记录算法集合和 weak-digest 标志，不声称签名或发布者认证 |
| Image capability observation | `tests/firmware/image_capability_observation/run_test.py`；`unknown_required_capability/run_test.py`；`test_unknown_required_capability_evidence.py`；`test_firmware_manifest.py`；`evidence-2026-10-25-image-capability-observation.json`；`evidence-2026-10-26-unknown-required-capability-fail-closed.json` | 无 sdkconfig 的公开 StickS3 Weather 镜像观察到 wifi/display；required wifi PASS，required camera 仍结构化拒绝；未知 required capability 在 merged/WebBurner 两条路径均 fail closed，未知 optional 仅 warning；observed entry 固定 low-confidence，不冒充运行态能力使用 |
| Public artifact refresh invariant | `user_firmware_matrix.py:download_candidates`；`test_user_firmware_matrix.py`；`firmware-manifest.md` | 每个 matrix run 重新解析公开版本并 `force=True` 下载；同 firmware/version ID 的缓存不能证明当前 CDN 内容；新 SHA 必须重新执行 Device Service 才能继承功能结论 |
| SD media fixture | `platform/tools/sd_image.py`；`test_sd_image.py`；Device Service `storage.sd_image_artifact_id` | 纯 Python 生成确定性 FAT32+MBR 或 FAT16 superfloppy raw image；Device Service 拒绝无 SD 模型的设备，校验 512-byte 对齐，复制到 session 后重新哈希并以 writable `if=sd` 挂载 |
| NVS partition fixture | `platform/tools/nvs_image.py`；`test_nvs_image.py`；Device Service `nvs.image_artifact_id` | 生成与 ESP-IDF generator 逐字节一致的 NVSv2 namespace/string 数据；服务按固件分区表校验 label/offset/size，只覆盖 session Flash 副本并记录 base/effective SHA |
| OpenAI first-boot NVS precondition | `tests/firmware/openai_nvs_precondition/run_test.py`；`evidence-2026-10-25-openai-nvs-precondition.json` | 公开 BIN 的 NVS 全空；Open 与正确 WPA2-PSK 都完成关联、DHCP、`api.openai.com` DNS 与 TCP/443；WPA2 路径完成 M1-M4 和成对密钥 CCMP，错误密码在 M2 MIC 被拒绝且无 DHCP |
| SHA-bound network-first expectation | `user_firmware_matrix.py`；`user_firmware_expectations.schema.json`；`test_user_firmware_matrix.py`；`evidence-2026-10-25-network-first-review-expectation.json` | UI/headless/network-first 由 device/firmware/SHA 绑定；required/forbidden markers、network status、expectation 与 NVS digest 同 result key；OpenAI 无需 frame 即完成 guest 联网 marker、DHCP、DNS、TCP/443、pcap 与 stop cleanup |
| Refreshed public artifacts functional | `user_firmware_matrix.py`；`test_user_firmware_matrix.py`；`evidence-2026-10-25-refreshed-four-functional-sd-mbr/evidence.json`；`evidence-2026-10-25-openai-nvs-precondition.json` | 4 个当前公开 BIN 的 Device Service 结果为 `3 PASS / 1 PARTIAL`；XiaoZhi/EDC/CrossPoint 达到 frame/input 层 PASS；OpenAI 的 UI/input 规则仍为 PARTIAL，但空 NVS、WPA2 与错误密码前置条件已分层验证 |
| 跨厂商公开固件 runtime matrix | `user_firmware_matrix.py`；`test_user_firmware_matrix.py`；S3/C6 与 Core2 evidence | 7 台设备、21 个公开样本；10 PASS / 11 PARTIAL；Core2 PMIC/AWS ATECC 与 C6 Zigbee 归类为 `runtime_model_gap` |
| C6 Zigbee `thread-sim` 可行性 | `tests/firmware/c6_zigbee_thread_sim/run_feasibility.py`；`evidence-2026-10-24-c6-zigbee-thread-sim-feasibility.json` | 双实例 UDP relay 观察到双向 802.15.4 帧，但 commissioning/join 未完成；结果为 `PARTIAL/runtime_model_gap` |
| 运行时模型缺口登记 | `runtime-model-gap-register.md`；C6 Flash/PMP patches；Core2 flash-IPC/QIO/cross-core/WDT-liveness/late-state 探针；timer/WDT-mask/stateful-SSI/handoff-trace patches；LVGL/SPI completion diagnostic；跨厂商与修复 evidence | `RUNTIME-01` 已关闭；`RUNTIME-02` 为 802.15.4 ACK/commissioning；`RUNTIME-03` 已把 normal-WDT 首 reset 归到 TG0 stage-1，并把约 44 秒后的 CPU1 wait 绑定到 LVGL double-buffer flush；SPI completion/`lv_disp_flush_ready`、reset PC `0` 和非空帧仍开放；`RUNTIME-04` 为 ATECC608 |
| 网络隔离 | `tests/network/linux_isolation/` | Linux private namespace、无外部路由、pcap |
| 错误密码 P0 | `tests/network/wrong_password/run_test.py`；`evidence-2026-10-24-wrong-password-pass.json` | 6 次 auth/reject、无 DHCP、无 HTTP、固件失败 marker 和 SoftAP wrong-password warning 同次 `7/7 PASS` |
| 错误密码/radio 重连 | `network_lane.py`、`tests/network/reconnect_probe/run_test.py`；`evidence-2026-10-24-radio-loss-recovery-pass.json` | radio QOM `false→true`、scan `1→0→1`、双 DHCP、前后 HTTP 200、双侧流 pcap 和同 session 证据 |
| DNS/UDP 数据面 | `network_lane.py`、`tests/network/idf_dns_udp/`；`evidence-2026-10-24-dns-udp-pass.json` | host-forwarder DNS、host 收到固定 UDP 载荷、guest 收到同载荷回包；不冒充 controlled DNS policy |
| Core2 WiFi-only deterministic repeat | `tests/network/core2_openmac_wifi/run_test.py`；`evidence-2026-10-24-deterministic-5x.json` | runner 显式传入 `tcg,thread=single,tb-size=128` + `icount`；scan/association/DHCP/HTTP 独立 `5/5`，不含 BLE/DNS/公网 |
| DNS + TLS/Host allowlist | `tests/network/tls_allowlist/`、QEMU patch `0027` | Linux namespace 下允许域名 A/拒绝 NXDOMAIN、TLS CA、允许 200/拒绝 403 和 pcap PASS |
| UIFlow2 guest IPv6 lifecycle | `tests/network/ipv6_end_to_end/`；test-only patch；`evidence-2026-10-24-guest-ipv6-direct-test-build-pass.json`；`evidence-2026-10-25-ipv6-namespace-aaaa-http-pass.json` | Direct run 在同一 StickS3 guest 创建 link-local 并完成 IPv6 HTTP；Linux namespace run 进一步由同一 test-build guest 完成 controlled AAAA、allowed HTTP、denied-port、pcap、namespace/QEMU cleanup。原厂 UIFlow2 仍未默认启用 IPv6，结果不等于公网 IPv6 或 RF |
| Bounded CIDR/dual-stack egress | `tests/network/egress_allowlist/` | nftables 默认 drop、IPv4 CIDR 与 IPv6 exact 地址的允许/拒绝端口/地址、worker→upstream 双栈 veth/NAT、源地址转换、IPv6 neighbor control、namespace/NAT 清理 |
| Controlled domain set | `network_policy.py`；`network_sandbox.py`；`test_network_policy.py`；`test_network_sandbox.py` | suffix 只在 DNS label boundary 匹配；exact 优先、最长 suffix 优先；每个 exact/domain/CNAME terminal answer 必须被 allowed endpoint 地址/CIDR 覆盖；IPv4-mapped IPv6 record 拒绝；`evilallowy.test` 不匹配 `allowy.test` |
| HTTP Host authority | `network_sandbox.normalize_http_authority()`；`ControlledHttp`；`test_network_sandbox.py`；`evidence-2026-10-26-host-authority-exact-dns-namespace-pass.json` | 只接受单一 Host header、可选数字端口、origin-form target 和严格 DNS label；拒绝 userinfo、逗号/multi-colon、越界端口、absolute-form 和重复 Host；Linux namespace 下同一 StickS3 guest 完成 DNS/TLS/DHCP/pcap |
| Controlled CNAME lifecycle | `network_sandbox.py`；`device_service.py`；`tests/network/dns_cname_chain/`；`tests/network/cname_guest_lifecycle/` | resolver 覆盖最多 8 跳、cycle/权限/冲突；三个独立 lease 由同一 stock UIFlow2 guest 完成 CNAME→terminal A→HTTP、denied-name/port、pcap、namespace cleanup。evidence ZIP 同时带 DNS/HTTP fixture 和 isolation 文件 |
| DHCP renewal | `tests/network/idf_dhcp_renewal/` | guest 调用 renew API；pcap 区分初次 DORA 与后续 REQUEST/ACK，lease/地址/HTTP 联合 PASS |
| 双设备 lab fabric | `tests/network/lab_fabric/`、patches `0028` | private namespace 内两台 QEMU guest 完成 DORA、A→B TCP 和双侧 pcap；宿主、公网、metadata、默认路由不可达并按预期清理。QEMU 运行路径是 socket switch；TAP/bridge 是独立 primitive |
| 热门用户固件 | `platform/tools/user_firmware_matrix.py` | 公开固件的启动、首帧、输入和串口结果 |
| 公共 API | `/api/v1` Device Service | 可观察、可保留的 session/evidence |
| Worker lifecycle | `/api/v1/worker`、`/worker/drain`、`/worker/resume`；`platform/tests/test_worker_registry.py` | stable ID、独占状态目录、heartbeat、generation、drain/resume、active/abandoned lease 和 bounded results；不含远程调度或活动 QEMU re-attach |
| Remote worker directory | `/api/v1/workers`、`/workers/{id}/heartbeat`、`drain`、`stop`、`results`；`platform/tests/test_worker_directory.py` | 持久 identity/generation、stale 判定、live-instance 冲突、capability/结果上限和原子 `0600` 状态文件；不启动、调度或接管 worker |
| Remote job queue | `/api/v1/jobs`、`/jobs/claim`、`heartbeat`、`result`、`cancel`；`platform/tests/test_worker_queue.py`、`test_device_service.py` | 持久幂等任务、capability match、worker lease、expiry/retry、stale/stop/generation 回收、re-claim 后旧 lease result 的 409 fencing 和原子 `0600` 状态文件；不执行任务、不接管活动 QEMU |
| Authenticated worker discovery | `worker_discovery.py`; `worker_discovery_seed.py`; `serve.py --worker-discovery-*`; `worker_agent.py --discover-control` / `--discover-control-seed-url`; discovery tests | active-token HMAC multicast 与 unicast seed beacon、TTL/clock/URL/包上限、零硬编码 control URL bootstrap、错误/旧 token reject、SIGHUP rotation；两个独立 subnet + masquerade 的 seed 路径连续 `3/3 PASS` |
| Worker control-plane restart continuity | `worker_agent.py --control-reconnect-timeout`; `worker_queue.py` result lease binding; `tests/network/worker_control_restart/` | 初始 `runtime=qemu` 非网络 session 暴露 `nic` 未初始化 FAIL 并保留；修复后真实 central/runtime Device Service 分离，central 停止 2.2s 后同 state 重启，worker 重注册、继续 heartbeat、同一 identity/generation/lease 完成 PASS、evidence ZIP、runtime session stop 和 QEMU reap PASS；不覆盖 runtime restart/cross-host migration |
| Worker runtime-service restart continuity | `worker_agent.py --runtime-reconnect-timeout` / `evidence_delay_seconds`; `device_service.py` QEMU + companion recovery; `tests/network/worker_runtime_restart/` | runtime Service SIGKILL 2.2s 后同 state 重启，同一 session/PID 重新接管；trusted-host unified fixture 重建 HTTP generation 2、adopt 同 BLE peer、完成 GATT cycle 2 和 guest HTTP recheck；worker status/evidence/stop retry，原 job/lease PASS，ZIP 含两代 HTTP/serial/network/pcap，session 与 QEMU/companion cleanup PASS；cross-host/namespace-managed/Tab5 migration 不覆盖 |
| Session-create idempotency | `device_service.py` `session-idempotency.json`; `worker_agent.py` job+lease key; `tests/network/session_idempotency/` | 并发同 key 同请求只建一个 session/QEMU lease；key/request 只存 SHA，异请求 409，service restart 后仍返回原 session；跨主机/跨租户存储 NOT RUN |
| Worker executor, discovery and rotation | `platform/tools/worker_agent.py`、`worker_auth.py`、`worker_discovery.py`、`worker_discovery_seed.py`、`transport_security.py`、auth/discovery/executor/TLS tests、`tests/network/worker_discovery_seed/`、`tests/network/worker_partition_fencing/`、`tests/network/worker_executor/`、`tests/network/worker_tls/`、`tests/network/worker_cross_netns/`、`tests/network/worker_cross_container/` | 同主机真实 QEMU job、worker HMAC、evidence ZIP/SHA256 和 terminal result；control/runtime 双 URL 由单测、两个 veth namespace 和三个独立 Docker 容器对验证，central control plane 不接收 session API；QEMU 前绑定 source firmware、normalized artifact 和 QEMU SHA，serial/frame/QOM、terminal result、QEMU reap、namespace/container/bridge cleanup 均 PASS。loopback 真实 HTTPS/mTLS、服务端校验、客户端证书、签名请求、真实 StickS3 QEMU job 和 unified board/WiFi/BLE job over mTLS PASS；SIGHUP rotation、overlap 和自动 migration PASS；trusted-host unified companion continuity PASS；multicast 与 unicast seed discovery、错误/旧 token reject 和 rotation 后重新发现 PASS；network blackhole 后 bounded heartbeat fence、OS process 与真实 QEMU PID stop/reap、lease expiry/requeue 和 retry 各自 `3/3 PASS`；worker-local `qemu-unified` lane 另以三次独立运行证明同 session HTTP/BLE/pcap 在 fence 后随 companion 一起终止，fresh retry 完成 unified evidence。QEMU 内 guest/device-controller side effect、物理跨主机 executor、无 reachable seed 的任意 NAT traversal、跨主机 reattach 和 namespace-managed/Tab5/cross-host companion 仍开放 |
| Worker restart integration | `tests/network/worker_lifecycle/evidence-2026-10-24-pass.json` | 真实 QEMU session 跨 drain 保持；停止后 drained；SIGKILL 后 generation 2 记录 abandoned lease 并将会话恢复为 interrupted failed；进程组清理 PASS |

设备级 PASS 至少要有固件 hash、runtime/profile、输入、串口、frame 和对应
数据面证据。进程启动、版本匹配或单条日志不能单独作为应用 PASS。

## Companion recovery boundary

trusted-host unified companion recovery 已闭合：

- `DeviceSession.reattach()` 先验证 QEMU PID/start-time、QMP ownership 和
  running 状态；
- HTTP fixture 每次请求原子写入 `http-fixture.json`，重启后按 profile port
  和递增 generation 重建；
- BLE peer 只在 PID、精确 start-time 和完整 process command SHA256 全部匹配
  时 adopt；缺少 ownership 或没有完成证据时 fail closed；
- unified StickS3 live fixture 在重启后完成 BLE GATT cycle 2 和 guest HTTP
  recheck，并在同一 job/lease evidence ZIP 中保留两代 HTTP、serial、network
  和 pcap。

namespace-managed、Tab5 和 cross-host companion recovery，以及连续外部
evidence stream 仍开放；这些场景不能从 trusted-host PASS 继承。

## 证据优先级

1. 同一固件路径的物理硬件验证。
2. 同一固件路径的 validated virtual-device 验证。
3. 模型/协议单测和静态分析，只作为实现支撑，不单独发布固件结论。

任何虚拟结果都要标记为 virtual-device validation；RF、功耗、声学、光学、
机械和电气结论不能由当前 QEMU/esp-emu 路径替代。

## 文档维护规则

- 当前能力变更：更新 `README.md`、`docs/project-status.md` 和对应专题页。
- 计划或缺口变更：只更新 `docs/project-backlog.md` 或专项 backlog。
- 用户交接、代码阅读顺序或工作流摘要变化：先核对当前状态、Backlog 和代码
  入口，再更新 `docs/engineering-handoff.md`；不要把动态计数或逐次运行流水
  复制进去。
- API 变更：同步 `docs/device-service-api.md`、OpenAPI 和 tests。
- 设备/外设变更：同步源清单、生成目录、契约、coverage 和矩阵文档。
- 验证结果：写回测试 evidence 或 `agent-work-logs`，不要只留在会话里。
- 新增 `runtime_model_gap`：同步缺口登记和 Backlog，保留原失败 evidence；
  修复后追加新 evidence，不改写当时诊断。
- 新文档：先登记到 [文档导航](README.md)，并标明它是当前事实、契约、
  专题说明还是历史证据。
- 被推翻的当前结论：在所有当前入口删除旧陈述，在历史页保留原日期并写明
  取代关系；不要只在新页面加一句更正而留下互相矛盾的主入口。
