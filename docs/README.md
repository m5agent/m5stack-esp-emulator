# 文档导航与新鲜度规则

日期：`2026-10-26`

本页只维护阅读顺序、职责和新鲜度。动态测试计数、设备/Task 计数以及
“非历史页是否落后于当前事实日期”由[自动项目快照](project-snapshot.md)
生成；当前能力结论在[项目当前状态](project-status.md)，带日期的历史快照只在
[验证证据台账](validation-ledger.md)追加。这里不把“测试通过”写成
“全部功能或真机通过”。

项目文档很多，但不是所有页面都描述“当前能力”。本页定义阅读顺序、文档职责
和新鲜度规则，避免把历史排障、计划或单次证据误当成今天的实现状态。

## 五分钟阅读顺序

只想知道“现在做到哪、还差什么”时，不需要从头读所有专题：

1. [工程交接总览](engineering-handoff.md)：当前工作、代码边界和下一步；
2. [项目当前状态](project-status.md)：已经具备的能力与不可继承边界；
3. [项目 Backlog](project-backlog.md)：仍未完成的任务、依赖和验收；
4. [验证证据台账](validation-ledger.md)：上述结论对应的日期化 evidence；
5. 需要改代码时再读[代码与验证入口地图](code-map.md)和相关专题页。

文档按“事实层级”使用，而不是按修改时间判断可信度：

| 层级 | 可以回答什么 | 不能回答什么 |
| --- | --- | --- |
| 当前事实 | `project-status.md` 描述当前能力和边界 | 具体历史轮次、失败 control |
| 待办 | `project-backlog.md` 描述未完成工作和验收 | 已完成能力的完整证据 |
| 生成快照 | `project-snapshot.md` 汇总动态计数和新旧日期 | 人工判断、硬件结论 |
| 契约 | API、Manifest、统一运行时和部署页面定义稳定接口 | 今天某项固件是否 PASS |
| 专题/历史 | 解释某条实现、根因或单次验证 | 不能覆盖当前状态页；即使页首日期较新，也要看 evidence 日期 |

页首“最近核对”表示维护者已确认该页与当前入口不冲突，不表示页内所有底层
矩阵都在当天重跑。页内固件 SHA、轮次、截图和失败 control 只覆盖其 evidence
日期；看到 `PASS`、`current` 或 `latest` 时，必须继续核对它指向的 artifact
和设备/profile。

## 按角色继续阅读

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

自动快照区分三种日期，避免把设备目录的生成时间误当成项目事实日期：

- 设备目录日期：`devices/catalog.source.json` 的 `generated_at`；
- 当前事实复核：机器源日期、最新 evidence 和五个项目入口复核日期中的最大值；
- 最新 evidence 日期：已提交 `tests/**/evidence-YYYY-MM-DD-*.json` 的最大日期。

因此 catalog 未变化但新 evidence 已提交时，快照仍会推进“当前事实复核”，并把
显式复核日期更早的权威页、委派页分别列为待复核项。待复核是审计信号，不是
自动判定内容错误。

| 页面 | 类型 | 最近核对 | 事实基线 |
| --- | --- | --- | --- |
| [工程交接总览](engineering-handoff.md) | 人读交接 | `2026-10-26` | 先按本轮 P0 区分已完成、在推进和未开始，再给出产品边界、代码盘点、成熟度、阅读顺序、工作流、下一步和文档职责；动态事实仍链接权威入口 |
| [工作流总台账](workstreams.md) | 工作流导航与当前在途 | `2026-10-26` | 维护已交付代码面、当前在途、推进顺序、下一验收门禁、稳定代码入口和未完成 Task ID |
| [自动项目快照](project-snapshot.md) | 生成事实 | `2026-10-26` | 分别记录 catalog 日期、当前事实复核和最新 evidence；从 profile/evidence/Backlog 自动生成设备、样本、缺口、Task、测试规模，并盘点权威页和委派文档的新鲜度 |
| [项目当前状态](project-status.md) | 当前结论 | `2026-10-26` | 唯一维护当前能力与边界；按网络、Core2、FirmwareManifest 汇总 P0 已完成和缺口，并保留 Unit 当前范围；Core2 TIMG WDT-mask、stateful SSI、handoff、WDT liveness 和 LVGL/SPI flush wait 的逐项证据仍转验证台账 |
| [项目 Backlog](project-backlog.md) | 待办 | `2026-10-26` | 先列出已完成里程碑和“局部完成不扩大结论”的解释，再只保留尚未达到验收条件的任务、依赖、并行条件和验收；Core2 的下一门禁是修 SPI completion/`lv_disp_flush_ready`、matching ELF/MAP 和同 SHA 非空应用帧 |
| [代码与验证入口地图](code-map.md) | 实现地图 | `2026-10-26` | 当前源码、FirmwareManifest/Secure Boot、runtime priority、Core2 flash-IPC/timer/stateful-SSI/cross-core、CIDR/domain/CNAME、multicast/unicast discovery、worker-local QEMU 与 `qemu-unified` partition fencing、namespace/container-local execution、Unit、测试/evidence/文档生成入口；包含 `SVC-03` 的低风险拆分顺序 |
| [验证证据台账](validation-ledger.md) | 证据历史 | `2026-10-26` | 按日期追加当时结论、检查项和 evidence，不反向定义当前能力 |
| [Device Service API](device-service-api.md) / [OpenAPI](device-service.openapi.yaml) | 契约 | `2026-10-26` | `1.34.0`；Unit 准入、HUB 拓扑、冻结 schema/QOM mapping、输入/状态/取证；保留 API 对象/状态机/错误码、worker lease ownership fence、8 MiB Core2 PSRAM/MMU、有界地址/CIDR、controlled exact/domain/CNAME answer binding、严格 Host authority、同 guest CNAME 网络证据和 transport 契约 |
| [统一设备运行时契约](unified-device-runtime.md) | 契约 | `2026-10-26` | 单 lease、单 guest、单固件、单 evidence bundle 的不变量和状态语义 |
| [Core2 native HCI backend](core2-native-hci-backend.md) | 设计 / 验证专题 | `2026-10-26` | native-HCI 数据面、PSRAM/MMU、长稳、重连、active-stop 和当前容量门禁；轮次与哈希只在该专题的日期化证据中，旧失败 control 保留为历史 |
| [FirmwareManifest](firmware-manifest.md) | 契约 | `2026-10-26` | 导入、规范化、ZIP path/casefold/symlink 与资源唯一性、多 build SoC 选择、mandatory `capabilities.required/optional`、WebBurner 分段 size/digest 复算及来源展示、Secure Boot v2 签名/包内 eFuse 摘要与 anti-rollback version 对照、aggregate/image/eFuse understatement fail-closed、文件系统/许可策略、sdkconfig detected / image observed capability 和 evidence 分层 |
| [运行时模型缺口登记](runtime-model-gap-register.md) | 缺口登记 | `2026-10-26` | 每个 `RUNTIME-*` 的现象、证据、修复状态和关闭条件；`RUNTIME-03` 的共享 I2C routing 已修，late loop 已绑定为 LVGL `lv_refr_vdb_flush` 双缓冲等待，flush callback 已执行但 SPI completion/`lv_disp_flush_ready` 未出现，normal-WDT 仍无应用进度；`RUNTIME-05` S3 WPA2-PSK 路径已关闭，WPA3/group multicast 仍未覆盖 |
| [网络模拟方案](network-simulation-plan.md) | 架构 / 验收专题 | `2026-10-26` | 网络模式、有界 CIDR egress、domain/CNAME、multicast/unicast discovery、worker process/QEMU 与 `qemu-unified` companion partition fencing、namespace/container-local execution、同 guest 网络生命周期和证据要求；运行比例转交验证台账 |
| [网络诊断 lane](network-lane.md) | 专题 | `2026-10-26` | 只描述诊断/Provisioning，不混同 unified 验收；Linux namespace IPv6 guest 生命周期已 PASS |
| [虚拟主机矩阵](qemu-device-adaptation-matrix.md) | 当前事实 | `2026-10-26` | 当前登记设备与各 QEMU/Tab5/Linux 后端、稳定运行时映射和能力边界；设备数量与运行比例分别转交自动快照和验证台账 |
| [UIFlow2 外设矩阵](uiflow2-peripheral-test-matrix.md) | 当前事实 | `2026-10-26` | 外设数据面和 runner 语义；主线完整矩阵基线由 `0036` stateful SSI 重建定义，`0038` 为 exact-time 诊断加定向回归；Unit 扩展 runtime 的完整门禁分别核验，不跨 binary 拼接；轮次和 case/check 数量只查验证台账与 evidence |
| [Tab5 暂缓项](tab5-deferred-backlog.md) | 专项 Backlog | `2026-10-26` | 能力仍以 2026-10-22 定向证据为基线；后来的 S3/C6/Core2 无线工作不继承给 P4 |
| [设备视觉保真](device-visual-fidelity-backlog.md) | 专项 Backlog | `2026-10-26` | StopWatch 是唯一参考质量外壳；后续功能验证不代表视觉模型已升级 |
| [Core2 cache/WDT 调查](core2-cache-panic-investigation.md) | 历史根因 | `2026-10-26` | 保留旧命名和复现、TCG translation-buffer 归因与 UIFlow2 门禁；补充 timer/WDT-mask、stateful SSI、统一 timeline、WDT-disabled 对照、public BIN/local ELF 字节审计、exact-time SIGSTOP freeze 和三次 WDT liveness 对账。历史 `800 ms` 现象未在当前配置复现，TG1 在 TG0 stage-1 reset 前仍持续 feed |
| [跨设备回归审计](uiflow2-cross-device-regression-audit.md) | 历史证据 | `2026-10-21` | 固定在当轮修复和截图 |
| [StopWatch QEMU 启动](stopwatch-uiflow2-qemu.md) | 历史证据 | `2026-10-20` | 解释初轮启动链，不描述后续 multi-board 能力 |
| [部署与运行时资产](deployment.md) | 运维指南 | `2026-10-26` | `.work/` 不随仓库发布；提供已验证 macOS arm64 runtime release，QEMU/namespace 的资产和权限要求 |
| [设备中心接入契约](device-center-adapter.md) | 接口契约 | `2026-10-26` | 目录、外设接口、设备状态、worker lifecycle 与页面消息 |
| [虚拟设备功能测试工作流](device-functional-test-workflow.md) | 工作流契约 | `2026-10-26` | 功能测试必须走 Device Service、保留 session evidence，并按 PID/QMP ownership 接管或明确失败 |
| [固件审查与仿真工作流](firmware-review-and-simulation-workflow.md) | 工作流契约 | `2026-10-26` | 审查方法和证据分层、Secure Boot v2/包内 eFuse 摘要与 anti-rollback version 对照、公开 BIN 刷新/SHA 绑定、运行路径和发布门禁；当前进度回权威状态页 |
| [外设仿真架构](peripheral-simulation-architecture.md) | 实现专题 | `2026-10-26` | catalog、runtime coverage、S3 WPA2/Core2 native-HCI 边界和后端数据面 |
| [P4 外设后端要求](p4-peripheral-backend-requirements.md) | 专项设计 | `2026-10-26` | Tab5 缺失的 P4 控制器、DMA 和端点；仍以 2026-10-22 focused probe 为能力基线 |
| [模拟器服务架构](simulator-service-architecture.md) | 设计 / 运维 | `2026-10-26` | 单机模块化单体、control/runtime 分离、multicast/unicast discovery、network-partition fence、双 namespace worker-local QEMU、companion recovery 和 warm-pool 边界 |
| [热门用户固件矩阵](user-firmware-simulation-matrix.md) | 当前验证工具 | `2026-10-26` | 历史哈希绑定结果、公开 CDN 强制刷新、四个当前样本、SD/NVS fixture、OpenAI 首次启动对照；Core2 legacy UIFlow 的原始无 ACK 结果与 shared-bus 后续复核分层记录 |
| [CoreS3 图像边界](cores3-image-rendering-boundary.md) | 已知差异 | `2026-10-26` | 仍固定在 2026-10-22 透明度/调色板图像分析，状态保持 `OPEN` |
| [CoreS3 三渲染器](cores3-three-renderer.md) | 历史证据 | `2026-10-22` | 固定三种渲染路径的对比 |
| [StickS3 三渲染器](sticks3-three-renderer.md) | 历史证据 | `2026-10-22` | 固定三种渲染路径的对比 |
| [多设备模拟器设计](plans/2026-10-20-multi-device-emulator-design.md) | 历史设计 | `2026-10-20` | 早期后端和能力分层，不代表当前设备状态 |
| [Unit 集成计划](plans/2026-10-25-unit-runtime-integration.md) | 实现设计 | `2026-10-26` | 当前优先补外部 Agent UIFlow 源码→Device Service API→可见 session/多 Unit→实时读写；固定公开模型源、控制器数据面、Web 双向状态和完整批次门禁仍分别验收 |
| [Unit 接入问题](unit-integration-host-issues.md) | 参考记录 | `2026-10-26` | 接入期间发现的主机问题与处理边界 |
| [S3 LEDC 读回与试听](evidence/2026-10-26-unit-ledc-audio-29d8/README.md)、[七层重放](evidence/2026-10-26-unit-ledc-audio-29d8/replay/README.md)、[getter独审](evidence/2026-10-26-unit-ledc-audio-29d8/replay/getter-independent-review/README.md) | 历史证据 | `2026-10-26` | 同 SHA getter/MMIO A/B、真实音频图与停止静音；完整回归66/67与独立复测分开，完整门禁仍OPEN |
| [三主机六传感器实际证据](evidence/2026-10-26-unit-host-sensors-gen9-a8fe/README.md) | 历史证据 | `2026-10-26` | 18 个同 guest/Web 会话、原驱动负控、fresh 串口、直接 PID、三路非原子帧和保留历史；Heart 零值暂态与人工可读性分别记录 |
| [Unit 官方协议](unit-research/official-protocols.md) | 参考依据 | `2026-10-26` | 官方芯片、驱动、物理端口、版本冲突与离线参考；不是 runtime PASS |
| [外壳浏览器集成证据](evidence/2026-10-26-visual-model-integration/README.md) | 历史证据 | `2026-10-26` | 固定提交的浏览器像素/输入/装配验证，不是固件或电气结论 |
| [Encoder 协议冲突](unit-research/encoder-protocol-conflicts.md) | 参考依据 | `2026-10-26` | 官方文字与 executable driver 的按压极性冲突；保留原证据并按驱动路径验证 |
| [Unit 首批运行证据](evidence/2026-10-26-unit-runtime/README.md) | 历史证据 | `2026-10-26` | CoreS3 Button/Relay/ENV III 同 guest 路径、固件/runtime hash、串口、画面、冻结契约与保留历史；不代表整批完成 |
| [S3 ADC 合成校准](unit-research/esp32s3-adc-calibration.md) | 参考依据 | `2026-10-26` | 固定 IDF/app 字节、17字段白名单、整数 oracle 和虚拟 eFuse fixture；不是物理精度 |
| [Unit 视觉绑定边界](unit-research/visual-bindings-and-component-gaps.md) | 参考依据 | `2026-10-26` | 官方链顺序与物理位置区分、组件缺口、读回色块和 Fan 定性活动；不推断 RPM 或缺少依据的姿态映射 |
| [Unit 首轮控制类证据](evidence/2026-10-26-unit-controls-service/README.md) | 历史证据 | `2026-10-26` | 固定旧运行时的 Joystick、Encoder、8Encoder、CardKB 和 RFID2 同 guest 记录；最终候选运行结果另存，不覆盖本轮 |
| [Unit I/O 运行证据](evidence/2026-10-26-unit-io-final/README.md) | 历史证据 | `2026-10-26` | 冻结运行时的 GPIO/ADC/LEDC/RMT/UART 与 HUB 同 guest 记录；IR 原包装驱动回调保持 PARTIAL，GC 对照不代替修复 |
| [Unit 控制类冻结复跑](evidence/2026-10-26-unit-controls-final/README.md) | 历史证据 | `2026-10-26` | 同一冻结运行时的五款控制类报告、原样 probe 和运行时证明；直接 PID 与 worker generation 的关联分开 |
| [Unit 真实浏览器链路](evidence/2026-10-26-unit-browser-final/README.md) | 历史证据 | `2026-10-26` | 真实浏览器到虚拟设备的 Button/Key/Fan 同会话输入、输出与历史证据；不是物理硬件测量 |
| [Unit 主机兼容性研究](unit-research/host-runtime-compatibility.md) | 参考依据 | `2026-10-26` | S3 端口、ADC、console/VFS 与板内共享总线冲突，其他后端的明确控制器门槛；不是跨主机 PASS |
| [Core2 SoftI2C 接管回归](evidence/2026-10-26-core2-soft-i2c-handoff/README.md) | 历史证据 | `2026-10-26` | classic 控制器永久 handoff 的同固件 A/B、最小兼容补丁与 Core2 组回归；不关闭 legacy WDT |
| [Unit 全型号真实 Web 取证](evidence/2026-10-26-unit-web-live-final/README.md) | 历史证据 | `2026-10-26` | 真实产品控件、HTTP、同 guest 串口/控制器和 DOM/模型读回逐项取证；保留测试工具失败尝试及 custom IR 身份 |
| [a8fe Unit Web 原轮](evidence/2026-10-26-unit-web-cohort-a8fe/README.md) | 历史证据 | `2026-10-26` | gen7 原轮成功、失败、中断与未执行项分别保存；不是一次全绿运行 |
| [Unit Web 就绪回归](evidence/2026-10-26-unit-web-readiness-regression/README.md) | 历史证据 | `2026-10-26` | 真实页面 running/enabled 同步、trusted 输入和跨平台进程证明故障对照 |
| [QMP 启动连接修复](evidence/2026-10-26-qmp-startup-connection/README.md) | 历史证据 | `2026-10-26` | 启动建连竞态的源码 A/B、AF_UNIX 对照、同锁连接归属与异常 socket 清理 |
| [QMP 调查时间线](evidence/2026-10-26-qmp-startup-connection/review-summary.md) | 历史证据 | `2026-10-26` | 两次原失败的 UTC 时间线、竞争机制与不能重演历史线程顺序的边界 |
| [Unit 最终显式选择](evidence/2026-10-26-unit-final-selection-a8fe/README.md) | 历史证据 | `2026-10-26` | 固定 gen7 的16例和 gen8 的11例，严格同会话/direct PID 汇总与 custom IR 限制 |
| [Unit gen8 补证](evidence/2026-10-26-unit-web-supplement-gen8-a8fe/README.md) | 历史证据 | `2026-10-26` | 修复后的11个逐型号真实 Web 会话及工具/运行时来源 |
| [Unit 冷写入生命周期](evidence/2026-10-26-unit-web-flashing-gen8-a8fe/README.md) | 历史证据 | `2026-10-26` | 独立固件SHA、自然flashing→running、真实手势、ZIP与历史；不混入主27选择 |
| [Unit 键名与截图回归](evidence/2026-10-26-unit-panel-readability-capture-regression/README.md) | 历史证据 | `2026-10-26` | 全型号四视口、CardKB完整键名、截图前滚动坐标和sticky导航位置 |
| [Unit 三主机九组合](evidence/2026-10-26-unit-host-web-gen9-a8fe/README.md) | 历史证据 | `2026-10-26` | 三主机各三款的严格功能通过；三张ENV浏览器构图PARTIAL，其余Unit未运行 |
| [Unit 九组合独立选择](evidence/2026-10-26-unit-host9-selection-a8fe/README.md) | 历史证据 | `2026-10-26` | 三份canonical27部分覆盖与9组合strict汇总，执行工具来源边界和配置晋级 |
| [前端恢复故障回归](evidence/2026-10-26-frontend-recovery-regression/README.md) | 历史证据 | `2026-10-26` | 23项异步归属/松开意图故障对照、独立mount浏览器布局与源码阶段边界 |
| [Unit 实际会话故障恢复](evidence/2026-10-26-unit-web-recovery-a8fe/README.md) | 历史证据 | `2026-10-26` | 实际晚到模型2D保帧、丢失一次松开POST、同guest释放与正常两POST |
| [Unit 读数语义审核](evidence/2026-10-26-unit-readout-semantic-review/README.md) | 历史证据 | `2026-10-26` | 17项语义、23项恢复与5种源码负控，来源/范围/方向及可选注释异常隔离；不是guest执行 |
| [Unit 读数浏览器回归](evidence/2026-10-26-unit-readout-browser-regression/README.md) | 历史证据 | `2026-10-26` | 四项当前源suite、四视口readout placement；HUB housing互叠仍开放 |
| [Unit 读数候选设计](evidence/2026-10-26-unit-readout-browser-regression/candidate/DESIGN.md) | 历史证据 | `2026-10-26` | promote前的画布外rail设计、源码清单与适用边界 |
| [Unit 读数迭代记录](evidence/2026-10-26-unit-readout-browser-regression/iterations.md) | 历史证据 | `2026-10-26` | 保留overlay至rail的迭代与原始失败，不覆盖历史尝试 |
| [Unit 同guest实时读数](evidence/2026-10-26-unit-readout-live-a8fe/README.md) | 历史证据 | `2026-10-26` | CoreS3 ENV两fresh向量/六POST、Relay零输入双态、terminal清值、同会话ZIP与独立330项审查；整页构图PARTIAL |
| [Unit 扩展同guest读数](evidence/2026-10-26-unit-readout-expanded-a8fe/README.md) | 历史证据 | `2026-10-26` | 明确9+2跨批选择，11款原驱动路径、fresh GET/body/serial/ZIP与停止历史；大fullPage图只核完整解码 |
| [Buzzer原版与显式custom](evidence/2026-10-26-unit-buzzer-once-a8fe/README.md) | 历史证据 | `2026-10-26` | 原版once负控FAIL、custom六阶段PASS，natural/trace不同SHA和后台TypeError分层；PWM getter读回仍OPEN |
| [Buzzer LEDC getter调查](evidence/2026-10-26-unit-buzzer-once-a8fe/getter-investigation/investigation.md) | 历史证据 | `2026-10-26` | 实际getter0/QOM非零、固定QEMU读分支与官方MicroPython/IDF链；dirty编译来源与动态MMIO验证仍未闭环 |
| [Unit HUB限定布局](evidence/2026-10-26-unit-hub-layout/README.md) | 历史证据 | `2026-10-26` | CoreS3紧凑单层HUB全尺寸布局、13组fixture与合入后五项browser回归；长卡片标题/完整PNG与旧bridge负控；其他排列/主机未继承 |
| [AtomS3R 控制类原批](evidence/2026-10-26-unit-atom-controls-r1-a8fe/README.md) | 历史证据 | `2026-10-26` | 五款控制类功能通过；380项源可重建、同session/直接PID/Web/ZIP/停止历史；原生多行文本可读性PARTIAL，显示修正需新固件验证 |
| [控制类证据契约归一化](evidence/2026-10-26-unit-atom-controls-r1-a8fe/post-execution-review/DESIGN.md) | 历史证据 | `2026-10-26` | 后置审核区分原准备字段与实际执行，保留旧双观察者规则；五真实正例和十九语义负控 |
| [控制类显示修正三主机证据](evidence/2026-10-26-unit-control-display-gen9-a8fe/README.md) | 历史证据 | `2026-10-26` | 三个独立批次十五session功能通过、同421源与实际停止历史；原生可读性仅实际最终帧，非所有状态或硬件结论 |
| [HUB候选交接](evidence/2026-10-26-unit-hub-layout/candidate/README.md) | 历史证据 | `2026-10-26` | 冻结候选补丁、量测、scope、旧失败与推广依赖清单 |
| [HUB布局候选设计](evidence/2026-10-26-unit-hub-layout/candidate/DESIGN.md) | 历史证据 | `2026-10-26` | 真实unitFrame/线缆API、尺寸与可选失败隔离，不修改控制器接线 |
| [HUB候选范围计划](evidence/2026-10-26-unit-hub-layout/candidate/PLAN.md) | 历史证据 | `2026-10-26` | 固定浏览器场景的实施与验证边界，不是项目执行队列 |

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

用例 README 中的 `Status: PASS`、固件 SHA、案例计数和截图都表示**该用例
最后一次 evidence**，不是今天的产品总状态。看到 `current`、`latest` 或
`canonical` 时，应同时确认它指向的 profile/commit 是否仍是
`project-status.md` 中的规范路径；被新路径取代的诊断 lane 必须明确标成
`historical` 或 `diagnostic`。

## 入口索引

### 状态、计划与维护

- [Unit 外设与视觉模型集成计划](plans/2026-10-25-unit-runtime-integration.md)
- [Unit 接入期间的主机问题](unit-integration-host-issues.md)
- [Unit 官方芯片与协议研究](unit-research/official-protocols.md)
- [固定版本外壳浏览器集成证据](evidence/2026-10-26-visual-model-integration/README.md)
- [Encoder 官方协议冲突](unit-research/encoder-protocol-conflicts.md)
- [Unit 首批控制器运行证据](evidence/2026-10-26-unit-runtime/README.md)
- [S3 ADC 合成校准依据](unit-research/esp32s3-adc-calibration.md)
- [Unit 视觉绑定与组件缺口](unit-research/visual-bindings-and-component-gaps.md)
- [Unit 首轮控制类运行证据](evidence/2026-10-26-unit-controls-service/README.md)
- [Unit I/O 与 IR 分层运行证据](evidence/2026-10-26-unit-io-final/README.md)
- [Unit 控制类冻结运行复跑](evidence/2026-10-26-unit-controls-final/README.md)
- [Unit 真实浏览器同会话证据](evidence/2026-10-26-unit-browser-final/README.md)
- [Unit 主机兼容性与扩展门槛](unit-research/host-runtime-compatibility.md)
- [Core2 SoftI2C 接管 A/B 与回归](evidence/2026-10-26-core2-soft-i2c-handoff/README.md)
- [Unit 全型号真实 Web 同会话取证](evidence/2026-10-26-unit-web-live-final/README.md)
- [a8fe Unit Web 原轮与失败边界](evidence/2026-10-26-unit-web-cohort-a8fe/README.md)
- [Unit Web 就绪与进程证明回归](evidence/2026-10-26-unit-web-readiness-regression/README.md)
- [QMP 启动连接竞态与清理修复](evidence/2026-10-26-qmp-startup-connection/README.md)
- [QMP 原失败调查时间线](evidence/2026-10-26-qmp-startup-connection/review-summary.md)
- [Unit 严格显式选择与固件身份](evidence/2026-10-26-unit-final-selection-a8fe/README.md)
- [Unit gen8 逐型号补证](evidence/2026-10-26-unit-web-supplement-gen8-a8fe/README.md)
- [Unit 自然冷写入生命周期](evidence/2026-10-26-unit-web-flashing-gen8-a8fe/README.md)
- [Unit 窄屏键名与截图滚动回归](evidence/2026-10-26-unit-panel-readability-capture-regression/README.md)
- [Unit 三主机九组合与视觉边界](evidence/2026-10-26-unit-host-web-gen9-a8fe/README.md)
- [Unit 九组合独立选择与配置晋级](evidence/2026-10-26-unit-host9-selection-a8fe/README.md)
- [前端异步与松开故障回归](evidence/2026-10-26-frontend-recovery-regression/README.md)
- [Unit 真实会话故障恢复](evidence/2026-10-26-unit-web-recovery-a8fe/README.md)

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
- [Core2 stock VHCI BLE（legacy GDB 诊断）](../tests/uiflow2/core2_native_vhci/README.md)
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
- PASS/FAIL 比例、轮次、资源数值、固件/工具哈希和逐项检查数只维护在
  `validation-ledger.md`、专题日期化证据或 evidence JSON。README、当前状态、
  Backlog、交接页和工作流页只描述稳定结论与不可继承边界；需要量化时链接
  台账，避免一次新运行迫使多个入口同步改写。

文档一致性由五个 `platform/tests/test_docs_*_contract.py` 模块分域检查，
覆盖导航/链接、当前状态、Core2、固件安全和网络/worker；
`platform/tests/test_docs_consistency.py` 只保留兼容入口。检查内容包括关键
文件、相对链接、API 版本、设备计数和已知过期陈述；退役说法存放在
`platform/tests/fixtures/stale_doc_claims.json`；目录级字段列权威文档路径，
每条 claim 包含稳定 ID、禁止文本和退役原因。

设备本地 case README 只说明该 case 的运行方式和当时边界，不是当前能力
来源。查当前状态先读 `project-status.md`，查动态设备/Task 计数先读
`project-snapshot.md`，查测试归属先读 `tests/README.md`。
