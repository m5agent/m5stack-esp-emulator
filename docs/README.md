# 文档导航与新鲜度规则

日期：`2026-10-25`

本页只维护阅读顺序、职责和新鲜度。动态测试计数、设备/Task 计数以及
“非历史页是否落后于当前事实日期”由[自动项目快照](project-snapshot.md)
生成；当前能力结论在[项目当前状态](project-status.md)，带日期的历史快照只在
[验证证据台账](validation-ledger.md)追加。这里不把“测试通过”写成
“全部功能或真机通过”。

项目文档很多，但不是所有页面都描述“当前能力”。本页定义阅读顺序、文档职责
和新鲜度规则，避免把历史排障、计划或单次证据误当成今天的实现状态。

## 先看这九页

1. [工程交接总览](engineering-handoff.md)：用一页理解产品边界、代码阅读顺序、
   当前工作流和下一步；不复制动态计数。
2. [自动项目快照](project-snapshot.md)：从 catalog、profile、evidence 和 Backlog
   自动汇总的设备、样本、缺口与 Task 板。
3. [工作流总台账](workstreams.md)：按工作流串起代码、权威状态入口和 Task ID。
4. [项目当前状态](project-status.md)：现在能做什么、已经验证什么、仍有什么风险。
5. [项目 Backlog](project-backlog.md)：尚未完成的工作、优先级、依赖和验收条件。
6. [代码与验证入口地图](code-map.md)：实现落在哪些模块、测试如何复现、证据在哪里。
7. [验证证据台账](validation-ledger.md)：按日期保存当时的检查项、结论和 evidence。
8. [统一设备运行时契约](unified-device-runtime.md)：Device Service、单 guest、
   board/WiFi/BLE/evidence 的产品验收边界。
9. [运行时模型缺口登记](runtime-model-gap-register.md)：已知“固件已执行但
   模拟器能力不足”的缺口、证据、边界和关闭条件。

如果页面之间冲突，以当前代码、生成后的 catalog/coverage、最新测试证据和
`project-status.md` 为准；`project-backlog.md` 不描述完成状态，日期较早的
调查页也不自动代表当前结论。

## P0 与模型缺口的权威入口

- 当前能力、已闭合边界和风险只看 [项目当前状态](project-status.md)。
- 未完成 Task ID、依赖和验收只看 [项目 Backlog](project-backlog.md)。
- 某项结论何时、用什么证据验证，只看 [验证证据台账](validation-ledger.md)。
- 具体设备/样本/Task 计数看 [自动项目快照](project-snapshot.md)；它由源文件
  生成，不替代上述人工结论和边界说明。
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
| [工程交接总览](engineering-handoff.md) | 人读交接 | `2026-10-25` | 产品边界、成熟度、代码阅读顺序、当前工作流、P0 下一步和文档职责；动态事实仍链接权威入口 |
| [工作流总台账](workstreams.md) | 工作流导航与当前在途 | `2026-10-25` | 维护已交付代码面、当前在途、下一验收门禁、稳定代码入口和未完成 Task ID |
| [自动项目快照](project-snapshot.md) | 生成事实 | `2026-10-25` | 从 catalog/profile/evidence/Backlog 自动生成设备、样本、缺口、Task、测试规模，并盘点权威页和委派文档的新鲜度 |
| [项目当前状态](project-status.md) | 当前结论 | `2026-10-25` | 唯一维护当前能力、最新验证结论和已知风险的系统性叙述 |
| [项目 Backlog](project-backlog.md) | 待办 | `2026-10-25` | 只保留尚未达到验收条件的任务、依赖和验收 |
| [代码与验证入口地图](code-map.md) | 实现地图 | `2026-10-25` | 当前源码、FirmwareManifest/Secure Boot 入口、runtime priority、CIDR/domain/CNAME、multicast/unicast discovery、worker-local QEMU 与 `qemu-unified` partition fencing、worker namespace/container-local execution、测试、evidence 和文档生成入口 |
| [验证证据台账](validation-ledger.md) | 证据历史 | `2026-10-25` | 按日期追加当时结论、检查项和 evidence，不反向定义当前能力 |
| [Device Service API](device-service-api.md) / [OpenAPI](device-service.openapi.yaml) | 契约 | `2026-10-25` | `1.33.0`；API、对象、状态机、错误码、worker lease ownership fence、8 MiB Core2 PSRAM/MMU、有界地址/CIDR、controlled domain suffix/CNAME chain、同 guest CNAME 网络证据和 transport 契约 |
| [统一设备运行时契约](unified-device-runtime.md) | 契约 | `2026-10-25` | 单 lease、单 guest、单固件、单 evidence bundle 的不变量和状态语义 |
| [Core2 native HCI backend](core2-native-hci-backend.md) | 设计 / 验证专题 | `2026-10-25` | native-HCI 数据面、legacy GDB 对照、QOM 8 MiB PSRAM + upper-bank MMU remap、artifact-bound 两小时、121 轮、active-stop/recovery、持续压力、错峰 `2/2`、双/三/四实例无错峰和五实例错峰 `10/10`；四实例 `1/4` 与五实例零错峰 `5/5 PASS`/`3/5 FAIL` 不稳定对照均保留 |
| [FirmwareManifest](firmware-manifest.md) | 契约 | `2026-10-25` | 导入、规范化、WebBurner 分段 size/digest 复算、Secure Boot v2 签名/包内 eFuse 摘要与 anti-rollback version 对照、文件系统、许可策略、sdkconfig detected / image observed capability、WebBurner 来源展示和 evidence 分层 |
| [运行时模型缺口登记](runtime-model-gap-register.md) | 缺口登记 | `2026-10-25` | 每个 `RUNTIME-*` 的现象、证据、修复状态和关闭条件；`RUNTIME-05` 的 S3 WPA2-PSK 路径已关闭，WPA3/group multicast 仍明确为未覆盖边界 |
| [网络模拟方案](network-simulation-plan.md) | 架构 / 验收专题 | `2026-10-25` | 网络模式、有界 CIDR egress、domain/CNAME、multicast/unicast discovery、worker process/QEMU/`qemu-unified` companion partition fencing、同 guest 网络生命周期和证据要求 |
| [网络诊断 lane](network-lane.md) | 专题 | `2026-10-25` | 只描述诊断/Provisioning，不混同 unified 验收；Linux namespace IPv6 guest 生命周期已 PASS |
| [虚拟主机矩阵](qemu-device-adaptation-matrix.md) | 当前事实 | `2026-10-25` | 当前登记设备与各 QEMU/Tab5/Linux 后端，设备数量见自动快照；Core2 121 轮、双/三/四实例无错峰、五实例错峰 `10/10`、零错峰不稳定、持续 PSRAM/周期联网与物理边界已回写 |
| [UIFlow2 外设矩阵](uiflow2-peripheral-test-matrix.md) | 当前事实 | `2026-10-25` | 外设数据面覆盖；Core2 `0008` 后完整回归 `67/67`、`274/274`；`0009` 源码构建的定向 Core2 组 `6/6`、`24/24`，固定脱敏汇总已入仓 |
| [Tab5 暂缓项](tab5-deferred-backlog.md) | 专项 Backlog | `2026-10-25` | 能力仍以 2026-10-22 定向证据为基线；后来的 S3/C6/Core2 无线工作不继承给 P4 |
| [设备视觉保真](device-visual-fidelity-backlog.md) | 专项 Backlog | `2026-10-25` | StopWatch 是唯一参考质量外壳；后续功能验证不代表视觉模型已升级 |
| [Core2 cache/WDT 调查](core2-cache-panic-investigation.md) | 历史根因 | `2026-10-25` | 保留旧命名和复现，补充 TCG translation-buffer 归因与当前门禁 |
| [跨设备回归审计](uiflow2-cross-device-regression-audit.md) | 历史证据 | `2026-10-21` | 固定在当轮修复和截图 |
| [StopWatch QEMU 启动](stopwatch-uiflow2-qemu.md) | 历史证据 | `2026-10-20` | 解释初轮启动链，不描述后续 multi-board 能力 |
| [部署与运行时资产](deployment.md) | 运维指南 | `2026-10-25` | `.work/` 不随仓库发布；提供已验证 macOS arm64 runtime release，QEMU/namespace 的资产和权限要求 |
| [设备中心接入契约](device-center-adapter.md) | 接口契约 | `2026-10-25` | 目录、外设接口、设备状态、worker lifecycle 与页面消息 |
| [虚拟设备功能测试工作流](device-functional-test-workflow.md) | 工作流契约 | `2026-10-25` | 功能测试必须走 Device Service、保留 session evidence，并按 PID/QMP ownership 接管或明确失败 |
| [固件审查与仿真工作流](firmware-review-and-simulation-workflow.md) | 工作流契约 | `2026-10-25` | 审查证据分层、Secure Boot v2/包内 eFuse 摘要与 anti-rollback version 对照、公开 BIN 刷新/SHA 绑定、运行路径和发布门禁 |
| [外设仿真架构](peripheral-simulation-architecture.md) | 实现专题 | `2026-10-25` | catalog、runtime coverage、S3 WPA2/Core2 native-HCI 边界和后端数据面 |
| [P4 外设后端要求](p4-peripheral-backend-requirements.md) | 专项设计 | `2026-10-25` | Tab5 缺失的 P4 控制器、DMA 和端点；仍以 2026-10-22 focused probe 为能力基线 |
| [模拟器服务架构](simulator-service-architecture.md) | 设计 / 运维 | `2026-10-25` | 单机模块化单体、control/runtime 分离、multicast/unicast discovery、network-partition fence、双 namespace worker-local QEMU、companion recovery 和 warm-pool 边界 |
| [热门用户固件矩阵](user-firmware-simulation-matrix.md) | 当前验证工具 | `2026-10-25` | 历史哈希绑定结果、公开 CDN 强制刷新、四个当前样本、SD/NVS fixture、OpenAI 首次启动对照和模型/fixture 边界 |
| [CoreS3 图像边界](cores3-image-rendering-boundary.md) | 已知差异 | `2026-10-25` | 仍固定在 2026-10-22 透明度/调色板图像分析，状态保持 `OPEN` |
| [CoreS3 三渲染器](cores3-three-renderer.md) | 历史证据 | `2026-10-22` | 固定三种渲染路径的对比 |
| [StickS3 三渲染器](sticks3-three-renderer.md) | 历史证据 | `2026-10-22` | 固定三种渲染路径的对比 |
| [多设备模拟器设计](plans/2026-10-20-multi-device-emulator-design.md) | 历史设计 | `2026-10-20` | 早期后端和能力分层，不代表当前设备状态 |

当前入口出现冲突时先修 `project-status.md`、Backlog、代码地图和契约页；
历史页只允许补充“被哪一页取代”，不能反向把旧结论写回当前入口。

## 委派文档怎么读

新鲜度台账只登记需要人工维护当前结论的页面。设备档案、测试/用例 README、
补丁说明、平台目录说明和仓内历史记录属于**委派文档**：它们负责
局部实现、运行方式和当时证据，不应复制一份新的项目总状态。自动项目快照会
盘点全部 Markdown 页面，并单列“带显式旧复核日期的委派文档”；进入这类
页面时，结论顺序始终是：

1. 相邻总索引（`devices/README.md`、`tests/README.md`、
   `tests/network/README.md`、`patches/README.md`、`platform/README.md`）；
2. [项目当前状态](project-status.md)；
3. [项目 Backlog](project-backlog.md)；
4. 页内引用的 evidence 和代码入口。

委派页面的旧日期表示“最后一次局部复核”，不自动证明今天已经失效；但如果
它把已完成项写成待办、把 `runtime_model_gap` 写成固件 FAIL，或与权威页
冲突，就必须修改局部页或明确标为历史。机器生成设备 README 只保留硬件档案、
验证状态和 blocker，详细运行流水统一放在验证台账和专题页。

## 入口索引

### 状态、计划与维护

- [工程交接总览](engineering-handoff.md)
- [自动项目快照](project-snapshot.md)
- [工作流总台账](workstreams.md)
- [项目当前状态](project-status.md)
- [项目 Backlog](project-backlog.md)
- [代码与验证入口地图](code-map.md)
- [验证证据台账](validation-ledger.md)
- [部署与运行时资产](deployment.md)
- [仓库维护规则](../AGENTS.md)
- [测试入口与 evidence 规则](../tests/README.md)
- [QEMU / 固件补丁总索引](../patches/README.md)

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
- [Controlled DNS CNAME chain](../tests/network/dns_cname_chain/README.md)
- [Firmware guest CNAME lifecycle](../tests/network/cname_guest_lifecycle/README.md)
- [精确 IP/端口 egress allowlist](../tests/network/egress_allowlist/README.md)
- [DNS/UDP 数据面探针](../tests/network/idf_dns_udp/README.md)
- [DHCP renewal probe](../tests/network/idf_dhcp_renewal/README.md)
- [UIFlow2 guest IPv6 TCP/HTTP test build](../tests/network/ipv6_end_to_end/README.md)
- [双设备私有 lab fabric](../tests/network/lab_fabric/README.md)
- [本地 worker drain/restart lifecycle](../tests/network/worker_lifecycle/README.md)
- [远程 durable job queue 与 lease supervisor](../tests/network/worker_queue/README.md)
- [HTTP-only worker executor](../tests/network/worker_executor/README.md)
- [Worker HTTPS/mTLS transport](../tests/network/worker_tls/README.md)
- [Authenticated worker discovery](../tests/network/worker_discovery/README.md)
- [Worker control-plane restart continuity](../tests/network/worker_control_restart/README.md)
- [Worker runtime-service restart continuity](../tests/network/worker_runtime_restart/README.md)
- [Idempotent session creation](../tests/network/session_idempotency/README.md)
- [本地 QEMU PID/QMP restart re-attach](../tests/network/worker_reattach/README.md)
- [Cross-network-namespace worker control plane](../tests/network/worker_cross_netns/README.md)
- [Cross-container worker QEMU execution](../tests/network/worker_cross_container/README.md)
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
- 设备、profile、固件矩阵或 Backlog Task 板变化后运行
  `python3 platform/tools/project_snapshot.py --write`，并让 `--check` 通过。
- 新增或关闭 `runtime_model_gap`：同步
  `runtime-model-gap-register.md` 和 Backlog；分类证据与修复证据分开保存。
- 历史页保留原日期；若结论被推翻，在页首加“已由某页取代”，不要静默改写成
  好像当时就知道后来结果。
- 非历史页复核后更新本页新鲜度表；自动快照会列出复核日期早于当前事实日期的
  页面，CI 不把历史固定页误报为过期。
- 同一证据的 SHA、测试数、Task 状态不要复制到历史页或设计页；应链接当前
  状态/Backlog，减少多处数字漂移。

文档一致性由 `platform/tests/test_docs_consistency.py` 检查，包括关键文件、
相对链接、API 版本、设备计数和已知过期陈述。

设备本地 case README 只说明该 case 的运行方式和当时边界，不是当前能力
来源。查当前状态先读 `project-status.md`，查动态设备/Task 计数先读
`project-snapshot.md`，查测试归属先读 `tests/README.md`。
