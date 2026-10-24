# 文档导航与新鲜度规则

日期：`2026-10-24`

本页只维护阅读顺序、职责和新鲜度。动态测试计数、最新矩阵结果和当前能力
只在[项目当前状态](project-status.md)维护；带日期的历史快照只在
[验证证据台账](validation-ledger.md)追加。这里不把“测试通过”写成
“全部功能或真机通过”。

项目文档很多，但不是所有页面都描述“当前能力”。本页定义阅读顺序、文档职责
和新鲜度规则，避免把历史排障、计划或单次证据误当成今天的实现状态。

## 先看这七页

1. [工作流总台账](workstreams.md)：按工作流串起当前状态、代码、证据和下一任务。
2. [项目当前状态](project-status.md)：现在能做什么、已经验证什么、仍有什么风险。
3. [项目 Backlog](project-backlog.md)：尚未完成的工作、优先级、依赖和验收条件。
4. [代码与验证入口地图](code-map.md)：实现落在哪些模块、测试如何复现、证据在哪里。
5. [验证证据台账](validation-ledger.md)：按日期保存当时的检查项、结论和 evidence。
6. [统一设备运行时契约](unified-device-runtime.md)：Device Service、单 guest、
   board/WiFi/BLE/evidence 的产品验收边界。
7. [运行时模型缺口登记](runtime-model-gap-register.md)：已知“固件已执行但
   模拟器能力不足”的缺口、证据、边界和关闭条件。

如果页面之间冲突，以当前代码、生成后的 catalog/coverage、最新测试证据和
`project-status.md` 为准；`project-backlog.md` 不描述完成状态，日期较早的
调查页也不自动代表当前结论。

## P0 与模型缺口的权威入口

- 当前能力、已闭合边界和风险只看 [项目当前状态](project-status.md)。
- 未完成 Task ID、依赖和验收只看 [项目 Backlog](project-backlog.md)。
- 某项结论何时、用什么证据验证，只看 [验证证据台账](validation-ledger.md)。
- 固件行为与模拟器差异不能直接归因时，先查
  [运行时模型缺口登记](runtime-model-gap-register.md)；分类不是修复。

不要在 README、专题页或历史调查中复制第三份 P0 状态表。

## 文档分层

| 类型 | 作用 | 代表页面 |
| --- | --- | --- |
| 当前事实 | 只描述当前实现、验证日期和已知边界 | [项目当前状态](project-status.md) |
| 待办 | 只列未完成工作、依赖和验收条件 | [项目 Backlog](project-backlog.md) |
| 契约 | 定义 API、manifest、运行时和发布门禁 | [Device Service API](device-service-api.md)、[FirmwareManifest](firmware-manifest.md)、[统一运行时](unified-device-runtime.md) |
| 实现地图 | 指到源码、测试、证据和生成物 | [代码与验证入口地图](code-map.md) |
| 验证台账 | 按日期保存当时结论、检查项和 evidence | [验证证据台账](validation-ledger.md) |
| 专题说明 | 深入解释某一类模型、流程或边界 | [网络模拟](network-simulation-plan.md)、[外设架构](peripheral-simulation-architecture.md) |
| 历史证据 | 保留当时的复现、根因或阶段计划 | [StopWatch QEMU 适配](stopwatch-uiflow2-qemu.md)、[多设备设计](plans/2026-10-20-multi-device-emulator-design.md) |

## 新鲜度台账

“最近核对”表示该页结论已经和当前主入口对齐，不表示所有底层矩阵都在同一天
重跑；真正的验证时间以页内 evidence 和 JSON 为准。

| 页面 | 类型 | 最近核对 | 事实基线 |
| --- | --- | --- | --- |
| [工作流总台账](workstreams.md) | 当前工作台账 | `2026-10-24` | 交付状态、代码/证据入口和未完成 Task ID |
| [项目当前状态](project-status.md) | 当前事实 | `2026-10-24` | 最新全矩阵、网络/CI、Core2、FirmwareManifest 与平台测试快照 |
| [项目 Backlog](project-backlog.md) | 待办 | `2026-10-24` | 只保留尚未达到验收条件的任务 |
| [代码与验证入口地图](code-map.md) | 实现地图 | `2026-10-24` | 当前源码、runtime priority 与 evidence 入口 |
| [验证证据台账](validation-ledger.md) | 证据历史 | `2026-10-24` | 按日期记录当时结论、检查项和 evidence，不反向定义当前能力 |
| [Device Service API](device-service-api.md) / [OpenAPI](device-service.openapi.yaml) | 契约 | `2026-10-24` | runtime contract `1.21.0`；同 peer-process 多轮 BLE scan/connect/GATT/disconnect 参数和 active BLE peer linger；HTTPS/mTLS server/client 配置、真实 QEMU 与 unified StickS3 job over mTLS、token-file、SIGHUP rotation、active-request drain、previous token/client-CA bounded overlap 和 final cutover；保留 worker HMAC、QEMU restart re-attach、durable queue、WebBurner、resumable upload、staging GC 和 nftables egress |
| [统一设备运行时契约](unified-device-runtime.md) | 契约 | `2026-10-24` | 14 个 unified profile；Core2 主路径为 `core2-native-hci`，`HCI-1` 至 `HCI-4` PASS；旧的 native-VHCI GDB 路径仅保留为诊断/兼容 |
| [Core2 native HCI backend](core2-native-hci-backend.md) | 设计 / 当前实现 | `2026-10-24` | `HCI-1` 至 `HCI-4` PASS；`60s`、`120s` 和 active-BLE `120s` 门禁通过；同 guest 二十轮和三十轮 GATT 分别在 3 个独立 lease 中 PASS。三十轮运行每 lease HLI 857/857、events 587、ACLs 270，连接池回到空闲基线。根因是 Bumble 对 `HCI_Host_Number_of_Completed_Packets (0x0c35)` 返回了不该存在的 Command Status；首次 10 轮运行的 Device Service 30 秒等待误杀已修复；参数范围 `1–30`，下一门禁是超过三十轮和多小时 soak；物理等价性与真机仍开放 |
| [FirmwareManifest](firmware-manifest.md) | 契约 | `2026-10-24` | WebBurner browser intake、eFuse summary、LittleFS/FAT12/16/32/SPIFFS 清单和声明级许可 allowlist/denylist 已通并有 evidence；运行时权限、完整源码级许可扫描和法律审批仍开放 |
| [运行时模型缺口登记](runtime-model-gap-register.md) | 缺口登记 | `2026-10-24` | C6 软件复位 chip-id 的 `RUNTIME-01` 已由 Flash 三字节写擦/PMP 复位修复关闭；C6 Zigbee/802.15.4 的 `RUNTIME-02` 仍 `OPEN`；Meshtastic 修复后仍有独立应用异常，未写成完整功能 PASS |
| [网络模拟方案](network-simulation-plan.md) | 专题 | `2026-10-24` | namespace/egress CI、controlled DNS、TLS、pcap、radio/AP 丢失恢复、双 guest lab fabric、worker SIGHUP rotation、active-request drain、bounded credential overlap 和 final cutover 已通；自动化客户端迁移、跨主机与 QEMU worker 边界单列 |
| [网络诊断 lane](network-lane.md) | 专题 | `2026-10-24` | 只描述诊断/Provisioning，不混同 unified 验收 |
| [虚拟主机矩阵](qemu-device-adaptation-matrix.md) | 当前事实 | `2026-10-24` | 14 台设备与各 QEMU/Tab5/Linux 后端 |
| [UIFlow2 外设矩阵](uiflow2-peripheral-test-matrix.md) | 当前事实 | `2026-10-24` | 外设数据面覆盖；最新计数和边界见项目当前状态 |
| [Tab5 暂缓项](tab5-deferred-backlog.md) | 专项 Backlog | `2026-10-24` | 能力仍以 2026-10-22 定向证据为基线 |
| [设备视觉保真](device-visual-fidelity-backlog.md) | 专项 Backlog | `2026-10-24` | StopWatch 是唯一参考质量外壳 |
| [Core2 cache/WDT 调查](core2-cache-panic-investigation.md) | 历史根因 | `2026-10-24` | 保留旧命名和复现，不覆盖当前状态 |
| [跨设备回归审计](uiflow2-cross-device-regression-audit.md) | 历史证据 | `2026-10-21` | 固定在当轮修复和截图 |
| [StopWatch QEMU 启动](stopwatch-uiflow2-qemu.md) | 历史证据 | `2026-10-20` | 解释初轮启动链，不描述后续 multi-board 能力 |
| [部署与运行时资产](deployment.md) | 运维指南 | `2026-10-24` | `.work/` 不随仓库发布；QEMU/namespace 的资产和权限要求 |
| [设备中心接入契约](device-center-adapter.md) | 接口契约 | `2026-10-24` | 目录、外设接口、设备状态与页面消息 |
| [虚拟设备功能测试工作流](device-functional-test-workflow.md) | 工作流契约 | `2026-10-24` | 功能测试必须走 Device Service 并保留 session evidence |
| [固件审查与仿真工作流](firmware-review-and-simulation-workflow.md) | 工作流契约 | `2026-10-24` | 审查证据分层、运行路径和发布门禁 |
| [外设仿真架构](peripheral-simulation-architecture.md) | 实现专题 | `2026-10-24` | catalog、runtime coverage、后端数据面和设备本地验收 |
| [P4 外设后端要求](p4-peripheral-backend-requirements.md) | 专项设计 | `2026-10-24` | Tab5 缺失的 P4 控制器、DMA 和端点 |
| [模拟器服务架构](simulator-service-architecture.md) | 设计 / 运维 | `2026-10-24` | 当前单机模块化单体与后续 worker/warm-pool 路线 |
| [热门用户固件矩阵](user-firmware-simulation-matrix.md) | 当前验证工具 | `2026-10-24` | 6 台 S3/C6、18 个公开样本的历史矩阵；10 PASS / 8 PARTIAL；`RUNTIME-01` 已重跑关闭，样本转为独立应用异常；Zigbee `RUNTIME-02` 仍开放 |
| [CoreS3 图像边界](cores3-image-rendering-boundary.md) | 已知差异 | `2026-10-22` | 固定在当轮透明度/调色板图像分析 |
| [CoreS3 三渲染器](cores3-three-renderer.md) | 历史证据 | `2026-10-22` | 固定三种渲染路径的对比 |
| [StickS3 三渲染器](sticks3-three-renderer.md) | 历史证据 | `2026-10-22` | 固定三种渲染路径的对比 |
| [多设备模拟器设计](plans/2026-10-20-multi-device-emulator-design.md) | 历史设计 | `2026-10-20` | 早期后端和能力分层，不代表当前设备状态 |

当前入口出现冲突时先修 `project-status.md`、Backlog、代码地图和契约页；
历史页只允许补充“被哪一页取代”，不能反向把旧结论写回当前入口。

## 入口索引

### 状态、计划与维护

- [工作流总台账](workstreams.md)
- [项目当前状态](project-status.md)
- [项目 Backlog](project-backlog.md)
- [代码与验证入口地图](code-map.md)
- [验证证据台账](validation-ledger.md)
- [部署与运行时资产](deployment.md)
- [仓库维护规则](../AGENTS.md)

### Device Service 与固件

- [Device Service API](device-service-api.md)
- [OpenAPI 3.1](device-service.openapi.yaml)
- [WebBurner 浏览器固件导入](../platform/web/firmware.html)
- [Device Center adapter](device-center-adapter.md)
- [服务架构与 worker 路线](simulator-service-architecture.md)
- [虚拟设备功能测试工作流](device-functional-test-workflow.md)
- [固件审查与仿真测试工作流](firmware-review-and-simulation-workflow.md)
- [FirmwareManifest 与 WebBurner 导入](firmware-manifest.md)
- [运行时模型缺口登记](runtime-model-gap-register.md)
- [固件验证 evidence 目录](../tests/firmware/README.md)

### 设备、外设与运行时

- [设备档案矩阵](../devices/README.md)
- [虚拟主机适配矩阵](qemu-device-adaptation-matrix.md)
- [UIFlow2 外设测试矩阵](uiflow2-peripheral-test-matrix.md)
- [外设仿真架构](peripheral-simulation-architecture.md)
- [统一设备运行时契约](unified-device-runtime.md)
- [热门用户固件仿真矩阵](user-firmware-simulation-matrix.md)

### 网络与 BLE

- [网络模拟方案](network-simulation-plan.md)
- [网络诊断 lane](network-lane.md)
- [Linux 隔离测试](../tests/network/linux_isolation/README.md)
- [断线重连探针](../tests/network/reconnect_probe/README.md)
- [错误密码负向回归](../tests/network/wrong_password/README.md)
- [TLS Host allowlist 探针](../tests/network/tls_allowlist/README.md)
- [精确 IP/端口 egress allowlist](../tests/network/egress_allowlist/README.md)
- [DNS/UDP 数据面探针](../tests/network/idf_dns_udp/README.md)
- [DHCP renewal probe](../tests/network/idf_dhcp_renewal/README.md)
- [双设备私有 lab fabric](../tests/network/lab_fabric/README.md)
- [本地 worker drain/restart lifecycle](../tests/network/worker_lifecycle/README.md)
- [远程 durable job queue 与 lease supervisor](../tests/network/worker_queue/README.md)
- [HTTP-only worker executor](../tests/network/worker_executor/README.md)
- [Worker HTTPS/mTLS transport](../tests/network/worker_tls/README.md)
- [本地 QEMU PID/QMP restart re-attach](../tests/network/worker_reattach/README.md)
- [Core2 stock VHCI BLE](../tests/uiflow2/core2_native_vhci/README.md)
- [Core2 native HCI backend](core2-native-hci-backend.md)

### 专项 Backlog

- [Tab5 暂缓项](tab5-deferred-backlog.md)
- [设备视觉保真](device-visual-fidelity-backlog.md)
- [P4 外设后端要求](p4-peripheral-backend-requirements.md)

### 历史调查和阶段性方案

- [StopWatch UIFlow2 QEMU](stopwatch-uiflow2-qemu.md)
- [Core2 cache/panic 调查](core2-cache-panic-investigation.md)
- [CoreS3 图像渲染边界](cores3-image-rendering-boundary.md)
- [CoreS3 三渲染器对比](cores3-three-renderer.md)
- [StickS3 三渲染器对比](sticks3-three-renderer.md)
- [跨设备回归审计](uiflow2-cross-device-regression-audit.md)
- [多设备模拟器设计](plans/2026-10-20-multi-device-emulator-design.md)

历史页可以解释“为什么这样实现”，但更新当前能力时必须回到
`project-status.md`，更新待办时必须回到 `project-backlog.md`。

## 更新规则

- 项目级当前能力以 `project-status.md` 为准；设备矩阵只提供该页引用的设备
  明细。README 和本页只做摘要，工作流页只维护工作流级索引和下一步，不复制
  逐设备验证明细。
- 能力变化：同步 `README.md`、`project-status.md` 和对应专题页。
- 计划变化：只改 `project-backlog.md` 或专项 backlog。
- API 变化：同步 Markdown、OpenAPI、服务实现和契约测试。
- 设备/外设变化：同步源 catalog、生成目录、peripheral catalog、runtime
  coverage、profile、设备级用例和矩阵文档。
- 新验证：保存 evidence，必要时写入 `agent-work-logs`；不要把聊天摘要当作证据。
- 新验证记录：追加到 `validation-ledger.md`，并回查它是否改变
  `project-status.md` 或 `project-backlog.md`。
- 新增或关闭 `runtime_model_gap`：同步
  `runtime-model-gap-register.md` 和 Backlog；分类证据与修复证据分开保存。
- 历史页保留原日期；若结论被推翻，在页首加“已由某页取代”，不要静默改写成
  好像当时就知道后来结果。
- 同一证据的 SHA、测试数、Task 状态不要复制到历史页或设计页；应链接当前
  状态/Backlog，减少多处数字漂移。

文档一致性由 `platform/tests/test_docs_consistency.py` 检查，包括关键文件、
相对链接、API 版本、设备计数和已知过期陈述。
