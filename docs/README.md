# 文档导航与新鲜度规则

日期：`2026-10-28`

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

Unit 历史 raw 归档已从源码交付外置，固定旧提交链接只用于历史审计；普通 CI
不下载归档，具体保留范围与显式验证入口见[证据保留规则](evidence-retention.md)。

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
10. [公众模拟器计划](plans/2026-10-28-public-simulator.md)与[纯浏览器调研](browser-runtime-feasibility.md)：Pages 入口、浏览器与原生后端的分界和对照实验。

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
| [工程交接总览](engineering-handoff.md) | 人读交接 | `2026-10-28` | 先按本轮 P0 区分已完成、在推进和未开始，再给出产品边界、代码盘点、成熟度、阅读顺序、工作流、下一步和文档职责；动态事实仍链接权威入口 |
| [工作流总台账](workstreams.md) | 工作流导航与当前在途 | `2026-10-28` | 维护已交付代码面、当前在途、推进顺序、下一验收门禁、稳定代码入口和未完成 Task ID |
| [自动项目快照](project-snapshot.md) | 生成事实 | `2026-10-26` | 分别记录 catalog 日期、当前事实复核和最新 evidence；从 profile/evidence/Backlog 自动生成设备、样本、缺口、Task、测试规模，并盘点权威页和委派文档的新鲜度 |
| [项目当前状态](project-status.md) | 当前结论 | `2026-10-28` | 唯一维护当前能力与边界；按网络、Core2、FirmwareManifest 汇总 P0 已完成和缺口，并保留 Unit 当前范围；最终三设备接口回绑与 ESP-NOW loopback 边界见对应 evidence，Core2 legacy 已校正 VFS/WiFi fixture，setup/main、非空帧和正常 WDT 仍 OPEN |
| [项目 Backlog](project-backlog.md) | 待办 | `2026-10-28` | 先列出已完成里程碑和“局部完成不扩大结论”的解释，再只保留尚未达到验收条件的任务、依赖、并行条件和验收；`0067` 已完成 ESP-NOW controller loopback，外部/加密 peer 仍为 `RUNTIME-06`；Core2 下一门禁是 matching VFS + `qemu-wifi` 下的系统菜单初始化、normal-WDT 和同 SHA 非空应用帧 |
| [代码与验证入口地图](code-map.md) | 实现地图 | `2026-10-27` | 当前源码、FirmwareManifest/Secure Boot、runtime priority、Core2 flash-IPC/timer/stateful-SSI/cross-core、CIDR/domain/CNAME、multicast/unicast discovery、worker-local QEMU 与 `qemu-unified` partition fencing、namespace/container-local execution、Unit、测试/evidence/文档生成入口；包含 `SVC-03` 的低风险拆分顺序 |
| [验证证据台账](validation-ledger.md) | 证据历史 | `2026-10-28` | 按日期追加当时结论、检查项和 evidence，不反向定义当前能力 |
| [GitHub issues #2–#10 顺序复测](evidence/2026-10-27-issues-2-10/README.md) | 历史证据 | `2026-10-27` | 固定最终 runtime、session、固件、串口/QOM/帧/evidence 哈希；#2/#3 失败保持 open，#4–#10 的限定虚拟设备结论不转授物理硬件 |
| [证据保留规则](evidence-retention.md) | 交付契约 | `2026-10-27` | 必要 fixture、哈希、精简总结和复现入口；历史 raw 外置，普通 CI 与显式归档审计分开 |
| [纯浏览器执行调研](browser-runtime-feasibility.md) | 架构调查 | `2026-10-28` | esp-online-tester 固定源码、体积与板级范围；独立源码构建的当前浏览器实验及不可继承边界 |
| [GitHub Pages 虚拟设备部署](pages-deployment.md) | 部署契约 | `2026-10-28` | C/QEMU CoreS3 浏览器入口、固定源码构建、共享内存首控、管理员部署步骤和许可边界 |
| [正式 GitHub Pages 部署](evidence/2026-10-29-github-pages-production/README.md) | 当前部署证据 | `2026-10-29` | 原仓库 Actions 构建/部署成功；正式 HTTPS 地址独立执行真实 CoreS3 C/QEMU 21 项检查，LCD/触摸/PIR/QMP/分享重开/清理通过 |
| [CoreS3 C/QEMU 静态网页验收](evidence/2026-10-28-qemu-wasm-pages/README.md) | 历史证据 | `2026-10-28` | 固定源码完整构建、浏览器本地组合、真实 LCD/触摸/PIR及第二场分享启动/清理，Pages 单独记录 |
| [现有C/QEMU到WASM实验](qemu-wasm-port-research.md) / [构建与浏览器宿主证据](evidence/2026-10-28-qemu-wasm-build/README.md) / [CoreS3 guest证据](evidence/2026-10-28-qemu-wasm-cores3/README.md) | 执行研究 | `2026-10-28` | 完整WASM/CLI/QMP；主CPU栈恢复修正后64KiB运行，显式慢虚拟时钟和stdio主循环QMP下CoreS3完整LVGL帧/触摸/PIR/停止重开；默认时钟队列缺口开放，不属公众产品准入 |
| [公众模拟器计划](plans/2026-10-28-public-simulator.md) | 进行中计划 | `2026-10-28` | 公众首页、Unit信息层级、新模型、URL分享、静态导出与部署前门禁 |
| [公众入口证据](evidence/2026-10-28-public-simulator/README.md) | 当前浏览器证据 | `2026-10-28` | exact WASM/ROM/固件绑定、真实串口/帧/输入/暂停停止；模型与原生桥接分别验证，未部署 |
| [Unit 源码 PR 精简](plans/2026-10-27-source-pr-cleanup.md) | 收尾计划 | `2026-10-27` | 重建精简分支、去除本机和历史附件隐式依赖，执行干净检出门禁 |
| [UIFlow2 双主机审计与修复](evidence/2026-10-27-uiflow2-api-sweep/README.md) / [计划](plans/2026-10-27-uiflow2-complete-api-sweep.md) | 当前审计 | `2026-10-28` | UI/硬件/系统/HTTP 逐项状态、原厂与 SDK 候选分 lane；最终完整矩阵 68/68，模型/配置/可选外设及 stock 失败仍保留 |
| [StopWatch / StickS3 / Core2 UIFlow2 三设备复测](evidence/2026-10-28-multi-board-uiflow2-revalidation/README.md) | 当前三设备证据 | `2026-10-28` | system、协议、M5UI 和 shared SDK 候选；requests2、BLE UUID32、Modbus transform/async 与 M5UI 缺陷有候选修复，其余模型/固件边界显式保留 |
| [QRCode.setText 与 TLS epoch 三设备候选固件](evidence/2026-10-28-qrcode-tls-candidate-firmware/README.md) | 当前候选固件证据 | `2026-10-28` | StopWatch/StickS3/Core2 各自完成 stock→candidate 对照；QR 旧文本失败均转为新文本解码 PASS，TLS 证书过期均转为 5/5 mTLS HTTPS PASS；incremental relink、真机和公网 PKI NOT RUN |
| [Display.drawPixel framebuffer transaction](evidence/2026-10-28-stopwatch-drawpixel-transaction/README.md) | 当前候选固件证据 | `2026-10-28` | StopWatch preimage 的 standalone even/odd 像素均未 flush；三台候选均通过 standalone 奇偶像素、相邻像素保留和显式嵌套事务；不是 CO5300 单像素限制 |
| [StopWatch / StickS3 / Core2 UIFlow2 音频数据面](evidence/2026-10-28-three-board-audio/README.md) | 当前三设备证据 | `2026-10-28` | 六个并发可见会话验证 Mic `record`/WAV 与 Speaker raw/WAV/file；修复 ESP32-S3 I2S completion 的固定时间窗；物理声学仍 NOT RUN |
| [Core2 UIFlow2 触控条与电源键回调](evidence/2026-10-28-core2-touch-buttons/README.md) | 当前 Core2 输入证据 | `2026-10-28` | A/B/C 经 FT5x06 触控条、PWR 经 AXP2101 事件；四个回调与 remove 全通过，修复首次触控分支吞掉 `key:p` 的路由错误 |
| [Core2 pending SPI IRQ remap](evidence/2026-10-28-core2-intmatrix-pending-irq/README.md) | 当前 Core2 中断证据 | `2026-10-28` | `0064` 修复 source level 已高时映射写回不重算的 INTMATRIX 缺陷；同固件/ELF pre-fix timeout、fixed guest callback PASS，Core2 UIFlow2 设备组保持 6/6；legacy `RUNTIME-03` 仍 OPEN |
| [Core2 协作 IRQ、classic RMT 与三设备回归](evidence/2026-10-28-cooperative-highint-rmt/README.md) | 当前 Core2 运行时 / 三设备证据 | `2026-10-28` | `0065` 五轮关闭 high-priority DPORT handoff 调度死锁；`0066` 补 classic RMT 并越过 Neopixel 初始化错误，legacy 到达 `APIKEY`；normal-WDT reset、黑帧、display completion 和 setup/REPL 仍 OPEN。最终 runtime 三设备 system/候选/设备组并发回归 |
| [Core2 legacy VFS 与 WiFi fixture 校正](evidence/2026-10-28-core2-legacy-vfs-wifi-fixture/README.md) | 当前 Core2 运行时证据 | `2026-10-28` | 通用 LittleFS 与缺 NIC 裸 QEMU 会污染 legacy 黑帧结论；matching LittleFS2 + `runtime=qemu-wifi` 120 秒已执行注入的 boot marker，但 setup/main、非空帧和 normal-WDT 仍失败，`RUNTIME-03` 保持 OPEN |
| [Core2 legacy dual-SPI panel routing](evidence/2026-10-28-core2-dual-spi-panel-routing/README.md) | 当前 Core2 显示证据 | `2026-10-28` | `0068` 将同一 panel sink 同时接到 HSPI/SPI2 与 VSPI/SPI3；legacy `m5stack` 绘制 probe 从 `0` 转为 `1422` nonblack pixels；原厂 startup UI 与 normal-WDT 仍 OPEN |
| [ESP-NOW loopback 与三设备接口复测](evidence/2026-10-28-espnow-and-three-board-interface-retest/README.md) | 当前三设备证据 | `2026-10-28` | `0067` 在 controller TX/RX DMA 上完成 opt-in ESP-NOW 同 guest peer loopback；三台 system/shared/17 设备组、通信、音频 wrapper 和候选 TLS/requests/Modbus 在同一 final runtime 重绑；外部/加密 peer、RF、物理硬件仍 NOT RUN |
| [三设备并发复测与 runner 竞态修复](evidence/2026-10-28-concurrent-fixture-and-ready-state/README.md) | 当前三设备证据 / 测试基础设施 | `2026-10-28` | 设备间并发完成 system/shared/协议/音频复测；`network.http_fixture=false` 消除固定端口竞争，marker action 等待 session `running` 消除首次 key 409，Core2 18 秒预算在隔离顺序复测中恢复三帧；stock HTTP/Modbus/M5UI 缺陷与真机边界保留 |
| [最新 runtime 三设备 UIFlow2 接口复测](evidence/2026-10-28-three-board-uiflow2-latest-runtime/README.md) | 当前三设备证据 | `2026-10-28` | `78555183…` 上三台 system/shared/17 设备组、socket/MQTT/network/EzData/ESP-NOW/audio 与 Device API 81 operations 通过；stock HTTP/Modbus/TLS 缺陷仍保留，requests/Modbus/TLS 候选在同一 runtime 重新 PASS |
| [Core2 TIMG WDTFEED 写保护语义](evidence/2026-10-28-core2-timg-wdt-feed/README.md) | 当前 Core2 运行时证据 | `2026-10-28` | `0069` 让 `WDTFEED` 在 `WDTPROTECT` 下仍可喂狗，同时保留配置写保护；同固件 60 秒正常 WDT 仍在 `17.2529 s` TG0 stage-1 reset，startup UI、setup/REPL 和应用帧仍 OPEN |
| [Core2 legacy UART 与虚拟时钟对齐](evidence/2026-10-29-core2-legacy-uart-clock/README.md) | 当前 Core2 启动证据 | `2026-10-29` | `0070` 给 opt-in UART trace 加虚拟时间戳；WDT-off 下 BOARD/APIKEY 到 `55.00 s`、boot.py 到 `77.11 s`，normal WDT 仍 `17.25 s` reset；`shift=2` 也未消除 reset，不能把 accelerator override 当修复 |
| [Device Service API](device-service-api.md) / [OpenAPI](device-service.openapi.yaml) | 契约 | `2026-10-28` | `1.43.0`；公共完整checkpoint、同guest程序/字节码依赖、Preview/Run协调和限定Web消费者；保留Unit准入、冻结schema、lease/evidence及网络契约，SSE/AIFlow调用侧仍开放 |
| [外部 Agent Unit API](unit-agent-api.md) | 调用指南 | `2026-10-27` | UIFlow2 源码提交、caller-source pin、可见 session、Unit 配置和取证；CoreS3 选定场景的源码请求与原驱动/custom 边界，硬件 NOT RUN |
| [统一设备运行时契约](unified-device-runtime.md) | 契约 | `2026-10-26` | 单 lease、单 guest、单固件、单 evidence bundle 的不变量和状态语义 |
| [Core2 native HCI backend](core2-native-hci-backend.md) | 设计 / 验证专题 | `2026-10-26` | native-HCI 数据面、PSRAM/MMU、长稳、重连、active-stop 和当前容量门禁；轮次与哈希只在该专题的日期化证据中，旧失败 control 保留为历史 |
| [FirmwareManifest](firmware-manifest.md) | 契约 | `2026-10-26` | 导入、规范化、ZIP path/casefold/symlink 与资源唯一性、多 build SoC 选择、mandatory `capabilities.required/optional`、WebBurner 分段 size/digest 复算及来源展示、Secure Boot v2 签名/包内 eFuse 摘要与 anti-rollback version 对照、aggregate/image/eFuse understatement fail-closed、文件系统/许可策略、sdkconfig detected / image observed capability 和 evidence 分层 |
| [运行时模型缺口登记](runtime-model-gap-register.md) | 缺口登记 | `2026-10-28` | 每个 `RUNTIME-*` 的现象、证据、修复状态和关闭条件；`0067` 将 ESP-NOW 提升为同 guest controller-DMA loopback `PARTIAL`，外部/加密 peer 由 `RUNTIME-06` 跟踪；legacy `RUNTIME-03` 已修复 VFS/WiFi fixture 与 dual-SPI panel routing，原厂 startup UI、normal-WDT 和非空应用帧仍未闭环；`RUNTIME-05` S3 WPA2-PSK 路径已关闭，WPA3/group multicast 仍未覆盖 |
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
| [Unit 集成计划](plans/2026-10-25-unit-runtime-integration.md) | 实现设计 | `2026-10-27` | 同guest程序、限定Unit原驱动与QEMU按需共享采样；完整文件包/纯字节码依赖已接入；其余Unit、AIFlow/Preview/SSE及保存开机仍开放；视觉与功能协议分别验收 |
| [Unit 接入问题](unit-integration-host-issues.md) | 参考记录 | `2026-10-27` | 接入期间发现的主机问题与处理边界 |
| [AIFlow实时预览API评估计划](plans/2026-10-26-aiflow-live-preview-api.md) | 实现/设计 | `2026-10-27` | UIFlow同guest程序、QEMU按需共享帧和1.42 Preview/Run基础已实现；限定Web托管消费者已验，SSE与AIFlow完整接入仍待做，继承Unit/服务Backlog |
| [同VM Preview/Run控制面](plans/2026-10-27-preview-run-control.md) | 实施计划 | `2026-10-27` | 持久化身份/幂等/latest-wins、真实prompt取消、managed session与输入/帧fence；CoreS3 PIR/Relay限定实际会话与宿主负控已验，PIR部署事务取消已验，AIFlow/其它Web组合/GC仍开放 |
| [Preview Web消费者](plans/2026-10-27-preview-web-consumer.md) | 实施计划 | `2026-10-27` | 共享Preview身份、完整包保留编辑、主机/Unit输入、Run帧与生命周期；CoreS3 PIR/Relay限定真实Web验收完成，AIFlow/SSE仍开放；构图限定修复见下一块 |
| [Preview 控制组与 2Relay](plans/2026-10-27-preview-controls-and-2relay.md) | 实施计划 | `2026-10-27` | 四主机同VM丰富HUB控制组、U131双GPIO/蓝灯和限定窄屏/长dt相机已验；新运行时定向7PASS、完整矩阵66/67，边界保留 |
| [二进制checkpoint与Unit协议](plans/2026-10-27-binary-checkpoint-and-unit-protocols.md) | 实施计划 | `2026-10-27` | 分开不可变二进制包存储与固件loader能力，先验证旧Run不被不支持入口打断；兼容固件隔离构建与4Relay/FlashLight协议核对进行中 |
| [FlashLight与显式UIFlow base](plans/2026-10-27-flashlight-and-uploaded-uiflow-base.md) | 实施计划 | `2026-10-27` | 本块完成严格base、候选loader诊断与FlashLight限定GPIO/Web验收；公共main.mpy、动态route历史与AIFlow继续 |
| [公共main.mpy实时入口](plans/2026-10-27-public-main-mpy-runtime.md) | 实施计划 | `2026-10-27` | 真实bytecode canary、会话身份绑定、显式base Preview与同VM import派发/恢复；stock能力保持分层 |
| [FlashLight路由历史](plans/2026-10-27-flashlight-route-history.md) | 实施计划 | `2026-10-27` | UNIT-HOST-38真实GPIO路由生命周期、旧资格失效与新EN复位恢复；冷route/PWM/S1保持独立 |
| [FlashLight冷pad观察](plans/2026-10-27-flashlight-cold-pad-observation.md) | 实施计划 | `2026-10-27` | UNIT-HOST-37真实GPIO/IOMUX/OE/来源事件、无边沿连续低基线与原驱动自然复位；不造边沿或借用未知历史 |
| [Core2 首帧与网络修复](plans/2026-10-27-core2-startup-issues.md) | 实施计划 | `2026-10-27` | issues #2/#3 的固件身份核对、离线 WLAN 控制器与 UIFlow2 LVGL 实际画面验证；不继承 legacy LVGL7 结论 |
| [Core2 启动修复验收](evidence/2026-10-27-core2-startup/README.md) | 历史证据 | `2026-10-27` | 固定 UIFlow2 v2.5.3 的离线 WLAN、实际 LVGL 画面及运行时/历史保留门禁；原始私有归档与硬件边界分开 |
| [Unit 官方协议](unit-research/official-protocols.md) | 参考依据 | `2026-10-26` | 官方芯片、驱动、物理端口、版本冲突与离线参考；不是 runtime PASS |
| [Scroll与Roller485官方协议审计](unit-research/scroll-roller485.md) | 参考依据 | `2026-10-26` | 固定官方驱动/内部固件；Scroll独立partial模型与RGB队列/回绕/bootloader缺口，Roller485仍visual-only；来源存在不替代逐主机验证 |
| [Encoder 协议冲突](unit-research/encoder-protocol-conflicts.md) | 参考依据 | `2026-10-26` | 官方文字与 executable driver 的按压极性冲突；保留原证据并按驱动路径验证 |
| [S3 ADC 合成校准](unit-research/esp32s3-adc-calibration.md) | 参考依据 | `2026-10-26` | 固定 IDF/app 字节、17字段白名单、整数 oracle 和虚拟 eFuse fixture；不是物理精度 |
| [Unit 视觉绑定边界](unit-research/visual-bindings-and-component-gaps.md) | 参考依据 | `2026-10-26` | 官方链顺序与物理位置区分、组件缺口、读回色块和 Fan 定性活动；不推断 RPM 或缺少依据的姿态映射 |
| [Unit 主机兼容性研究](unit-research/host-runtime-compatibility.md) | 参考依据 | `2026-10-26` | S3 端口、ADC、console/VFS 与板内共享总线冲突，其他后端的明确控制器门槛；不是跨主机 PASS |

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


- [UIFlow2 全接口双主机验证](plans/2026-10-27-uiflow2-complete-api-sweep.md)
- [Unit 外设与视觉模型集成计划](plans/2026-10-25-unit-runtime-integration.md)
- [Unit 接入期间的主机问题](unit-integration-host-issues.md)
- [Unit 官方芯片与协议研究](unit-research/official-protocols.md)
- [GitHub issues #2–#10 顺序复测](evidence/2026-10-27-issues-2-10/README.md)
- [Core2 首帧、离线 WLAN 与 LVGL 修复](evidence/2026-10-27-core2-startup/README.md)
- [固定版本外壳浏览器集成证据](https://github.com/m5agent/m5stack-esp-emulator/blob/a37342f61c05964c060719a6e35c2d568c828e84/docs/evidence/2026-10-26-visual-model-integration/README.md)
- [Encoder 官方协议冲突](unit-research/encoder-protocol-conflicts.md)
- [Unit 首批控制器运行证据](https://github.com/m5agent/m5stack-esp-emulator/blob/a37342f61c05964c060719a6e35c2d568c828e84/docs/evidence/2026-10-26-unit-runtime/README.md)
- [S3 ADC 合成校准依据](unit-research/esp32s3-adc-calibration.md)
- [Unit 视觉绑定与组件缺口](unit-research/visual-bindings-and-component-gaps.md)
- [Unit 首轮控制类运行证据](https://github.com/m5agent/m5stack-esp-emulator/blob/a37342f61c05964c060719a6e35c2d568c828e84/docs/evidence/2026-10-26-unit-controls-service/README.md)
- [Unit I/O 与 IR 分层运行证据](https://github.com/m5agent/m5stack-esp-emulator/blob/a37342f61c05964c060719a6e35c2d568c828e84/docs/evidence/2026-10-26-unit-io-final/README.md)
- [Unit 控制类冻结运行复跑](https://github.com/m5agent/m5stack-esp-emulator/blob/a37342f61c05964c060719a6e35c2d568c828e84/docs/evidence/2026-10-26-unit-controls-final/README.md)
- [Unit 真实浏览器同会话证据](https://github.com/m5agent/m5stack-esp-emulator/blob/a37342f61c05964c060719a6e35c2d568c828e84/docs/evidence/2026-10-26-unit-browser-final/README.md)
- [Unit 主机兼容性与扩展门槛](unit-research/host-runtime-compatibility.md)
- [Core2 SoftI2C 接管 A/B 与回归](https://github.com/m5agent/m5stack-esp-emulator/blob/a37342f61c05964c060719a6e35c2d568c828e84/docs/evidence/2026-10-26-core2-soft-i2c-handoff/README.md)
- [Unit 全型号真实 Web 同会话取证](https://github.com/m5agent/m5stack-esp-emulator/blob/a37342f61c05964c060719a6e35c2d568c828e84/docs/evidence/2026-10-26-unit-web-live-final/README.md)
- [a8fe Unit Web 原轮与失败边界](https://github.com/m5agent/m5stack-esp-emulator/blob/a37342f61c05964c060719a6e35c2d568c828e84/docs/evidence/2026-10-26-unit-web-cohort-a8fe/README.md)
- [Unit Web 就绪与进程证明回归](https://github.com/m5agent/m5stack-esp-emulator/blob/a37342f61c05964c060719a6e35c2d568c828e84/docs/evidence/2026-10-26-unit-web-readiness-regression/README.md)
- [QMP 启动连接竞态与清理修复](https://github.com/m5agent/m5stack-esp-emulator/blob/a37342f61c05964c060719a6e35c2d568c828e84/docs/evidence/2026-10-26-qmp-startup-connection/README.md)
- [QMP 原失败调查时间线](https://github.com/m5agent/m5stack-esp-emulator/blob/a37342f61c05964c060719a6e35c2d568c828e84/docs/evidence/2026-10-26-qmp-startup-connection/review-summary.md)
- [Unit 严格显式选择与固件身份](https://github.com/m5agent/m5stack-esp-emulator/blob/a37342f61c05964c060719a6e35c2d568c828e84/docs/evidence/2026-10-26-unit-final-selection-a8fe/README.md)
- [Unit gen8 逐型号补证](https://github.com/m5agent/m5stack-esp-emulator/blob/a37342f61c05964c060719a6e35c2d568c828e84/docs/evidence/2026-10-26-unit-web-supplement-gen8-a8fe/README.md)
- [Unit 自然冷写入生命周期](https://github.com/m5agent/m5stack-esp-emulator/blob/a37342f61c05964c060719a6e35c2d568c828e84/docs/evidence/2026-10-26-unit-web-flashing-gen8-a8fe/README.md)
- [Unit 窄屏键名与截图滚动回归](https://github.com/m5agent/m5stack-esp-emulator/blob/a37342f61c05964c060719a6e35c2d568c828e84/docs/evidence/2026-10-26-unit-panel-readability-capture-regression/README.md)
- [Unit 三主机九组合与视觉边界](https://github.com/m5agent/m5stack-esp-emulator/blob/a37342f61c05964c060719a6e35c2d568c828e84/docs/evidence/2026-10-26-unit-host-web-gen9-a8fe/README.md)
- [Unit 九组合独立选择与配置晋级](https://github.com/m5agent/m5stack-esp-emulator/blob/a37342f61c05964c060719a6e35c2d568c828e84/docs/evidence/2026-10-26-unit-host9-selection-a8fe/README.md)
- [前端异步与松开故障回归](https://github.com/m5agent/m5stack-esp-emulator/blob/a37342f61c05964c060719a6e35c2d568c828e84/docs/evidence/2026-10-26-frontend-recovery-regression/README.md)
- [Unit 真实会话故障恢复](https://github.com/m5agent/m5stack-esp-emulator/blob/a37342f61c05964c060719a6e35c2d568c828e84/docs/evidence/2026-10-26-unit-web-recovery-a8fe/README.md)

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
