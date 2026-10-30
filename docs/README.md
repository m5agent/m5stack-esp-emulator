# 文档导航与新鲜度规则

日期：`2026-10-30`

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
Core2 legacy 的最新 status/CAS 诊断见
[RDSR 与锁竞争关联](evidence/2026-10-29-core2-legacy-status-cas/README.md)；
`0088` 的跨核 CAS 调度 A/B 见
[contended-CAS scheduler](evidence/2026-10-29-core2-contended-cas-scheduler/README.md)；
这些是历史排查证据，不单独证明 legacy 启动通过。当前原厂 normal-WDT startup 的限定通过见
[WDT level delivery 后续证据](evidence/2026-10-30-core2-legacy-wdt-level-delivery/README.md)，
setup/REPL、任意应用与物理等价仍需分别验证。

浏览器低帧率、正常时钟候选与逐设备准入按
[WASM 性能与多设备计划](plans/2026-10-29-wasm-performance-devices.md)推进；
原生设备验证与浏览器准入分别绑定执行产物。测量与准入见
[浏览器性能证据](evidence/2026-10-29-wasm-performance-devices/README.md)，
SDK 候选见[LVGL 正常时钟证据](evidence/2026-10-29-browser-lvgl-wallclock/README.md)。
新增六板已按[后续 Xtensa 接入计划](plans/2026-10-29-wasm-remaining-xtensa.md)完成固定示例准入；
编译、文件组合、模型检查与最终单板浏览器准入分开记录，正式部署另验。

模型仓库新增的 21 款主机按[主机模型接入计划](plans/2026-10-29-expanded-host-models.md)
同步；当前视觉库存为 38 主机、184 Unit，中央运行目录 24 款。
[逐板原厂固件验证](evidence/2026-10-29-expanded-hosts/README.md)记录输入、控制器与显示/LED，
仅模型、候选和通过的功能范围分别标注。

## 首页与维护入口

面向使用者的首页为默认中文 [README](../README.md)，英文入口为 [README.en](../README.en.md)。
维护者先读根 [AGENTS.md](../AGENTS.md)，再按职责查看
[服务工具](../platform/tools/AGENTS.md)、[浏览器/模型](../platform/web/AGENTS.md)、
[设备登记](../devices/AGENTS.md)、[运行时测试](../tests/AGENTS.md)、
[补丁](../patches/AGENTS.md)和[文档维护](AGENTS.md)。指引保存稳定规则，当前能力仍查权威页。

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

证据与计划行的“事实基线”是该日期当时的结果，不是今天的项目状态；后续
证据可以关闭历史 `OPEN`/`PARTIAL`，但不会改写原记录。当前结论始终回到
项目状态、Backlog、运行时缺口登记和验证台账。

| 页面 | 类型 | 最近核对 | 事实基线 |
| --- | --- | --- | --- |
| [AIFlow simulator skill consumer](plans/2026-10-27-aiflow-simulator-skill.md) | 调用侧历史验证 | `2026-10-27` | CoreS3/PIR 本机限定验证，远端 AIFlow 未验 |
| [通用与 AIFlow Agent Skills](plans/2026-10-29-agent-skills.md) | 调用侧分发 | `2026-10-29` | 独立 helper、配置与打包；不继承硬件 PASS |
| [文档维护指引](AGENTS.md) | 维护契约 | `2026-10-30` | 首页双语对齐、权威/历史职责、插图来源、链接检查与生成快照顺序 |
| [文档与首页整理计划](plans/2026-10-30-docs-readme-refresh.md) | 交付计划 | `2026-10-30` | 文档范围盘点、精简中文首页、英文入口、本轮截图和分层 AGENTS 的验收 |
| [首页插图来源](images/README.md) | 插图来源 | `2026-10-30` | 本轮浏览器运行与仅模型画廊的不同来源、范围、复现及视觉检查 |
| [文档整理验证](evidence/2026-10-30-docs-homepage-refresh/README.md) | 文档验证证据 | `2026-10-30` | 盘点修订、双语页面、插图、指引和离线检查；不增加硬件或完整设备 PASS |
| [工程交接总览](engineering-handoff.md) | 人读交接 | `2026-10-30` | 先按本轮 P0 区分已完成、在推进和未开始，再给出产品边界、代码盘点、成熟度、阅读顺序、工作流、下一步和文档职责；动态事实仍链接权威入口 |
| [工作流总台账](workstreams.md) | 工作流导航与当前在途 | `2026-10-30` | 维护已交付代码面、当前在途、推进顺序、下一验收门禁、稳定代码入口和未完成 Task ID |
| [自动项目快照](project-snapshot.md) | 生成事实 | `2026-10-30` | 分别记录 catalog 日期、当前事实复核和最新 evidence；从 profile/evidence/Backlog 自动生成设备、样本、缺口、Task、测试规模，并盘点权威页和委派文档的新鲜度 |
| [项目当前状态](project-status.md) | 当前结论 | `2026-10-30` | 唯一维护当前能力和限制，区分浏览器/原生/模型/物理边界；Core2 legacy stock startup 已有限定虚拟证据，更广 setup/REPL 与任意应用继续开放 |
| [项目 Backlog](project-backlog.md) | 待办 | `2026-10-30` | 先列出已完成里程碑和“局部完成不扩大结论”的解释，再只保留尚未达到验收条件的任务、依赖、并行条件和验收；Cardputer-ADV 当前参考 BMI270 已移出，`FW-03` 仍保留真实业务和更多固件族 |
| [代码与验证入口地图](code-map.md) | 实现地图 | `2026-10-30` | 当前源码、FirmwareManifest/Secure Boot、runtime priority、Core2 flash-IPC/timer/stateful-SSI/cross-core、CIDR/domain/CNAME、multicast/unicast discovery、worker-local QEMU 与 `qemu-unified` partition fencing、namespace/container-local execution、Unit、测试/evidence/文档生成入口；包含 `SVC-03` 的低风险拆分顺序 |
| [验证证据台账](validation-ledger.md) | 证据历史 | `2026-10-30` | 按日期追加当时结论、检查项和 evidence，不反向定义当前能力 |
| [GitHub issues #2–#10 顺序复测](evidence/2026-10-27-issues-2-10/README.md) | 历史证据 | `2026-10-27` | 固定最终 runtime、session、固件、串口/QOM/帧/evidence 哈希；#2/#3 失败保持 open，#4–#10 的限定虚拟设备结论不转授物理硬件 |
| [证据保留规则](evidence-retention.md) | 交付契约 | `2026-10-27` | 必要 fixture、哈希、精简总结和复现入口；历史 raw 外置，普通 CI 与显式归档审计分开 |
| [纯浏览器执行调研](browser-runtime-feasibility.md) | 架构调查 | `2026-10-28` | esp-online-tester 固定源码、体积与板级范围；独立源码构建的当前浏览器实验及不可继承边界 |
| [GitHub Pages 虚拟设备部署](pages-deployment.md) | 部署契约 | `2026-10-30` | C/QEMU 逐板准入、两种 CoreS3 示例、共享帧与每次构建的全公开板型门禁；固定源码构建、管理员部署步骤和许可边界 |
| [WASM 性能与多设备计划](plans/2026-10-29-wasm-performance-devices.md) | 本轮交付计划 | `2026-10-29` | 共享帧、宿主等待、正常时钟候选和四板逐例准入；归档、验证和 PR 交付范围 |
| [运动、电源与复位修复](plans/2026-10-29-motion-power-device-adaptation.md) | 当前交付计划 | `2026-10-29` | Arduino/UIFlow 舵机输出、板级 PMIC 与保持供电、同实例复位、剩余 Atom/Stick 接入 |
| [StackChan Arduino 浏览器兼容性](stackchan-arduino-browser.md) | 固件行为与实现边界 | `2026-10-29` | 固定 Dance 的扭矩策略、真实串口/位置诊断、S3 Flash QIOR 相位与同实例复位 |
| [Arduino NVS 与供电复测](evidence/2026-10-29-stackchan-arduino-nvs/README.md) | 限定虚拟设备证据 | `2026-10-29` | 同固件新旧 Flash 读取对照、NVS 重开/复位保留、真实 torque 与 Plus2 USB/电池供电路径 |
| [舵机命令与经典主机后续验证](evidence/2026-10-29-motion-command-followup/README.md) | 限定虚拟设备证据 | `2026-10-29` | 重复扭矩与模式恢复、新增四板浏览器准入、PM1 真实单击复位及 IRQ 模式回归 |
| [Cardputer 与 StackChan 输入修复计划](plans/2026-10-30-cardputer-stackchan-input.md) | 当前交付计划 | `2026-10-30` | 原键盘 IRQ、横竖屏与局部刷新、运动期间屏幕触摸及阻塞负控 |
| [Cardputer 与 StackChan 输入证据](evidence/2026-10-30-cardputer-stackchan-input/README.md) | 限定浏览器虚拟设备证据 | `2026-10-30` | 67-patch 新 WASM、ADV 原键盘与四旋转、StackChan 后台 UART 与真实短按、保留失败 |
| [StackChan 跳舞与 ADV 全键证据](evidence/2026-10-30-stackchan-dance-and-cardputer-all-keys/README.md) | 精确镜像虚拟设备证据 | `2026-10-30` | 跳舞 BIN app-bound div6、真实 SCS 位移、56 物理键与 55 PC code；硬件 `NOT RUN` |
| [新增主机模型接入](plans/2026-10-29-expanded-host-models.md) | 主机视觉接入计划 | `2026-10-29` | 21 款新增主机、完整 Atom/Stick 系列、型号配置、贴图、实际工作台入口与能力边界 |
| [Atom / Stick 原厂固件运行接入](evidence/2026-10-29-expanded-hosts/README.md) / [Dial 旋钮诊断](evidence/2026-10-29-expanded-hosts/dial-rotary.md) | 当轮逐板限定验证 | `2026-10-29` | 原厂固件、原生与纯浏览器、GPIO/I2C/RMT、Flash 修复及未完成边界 |
| [剩余 Xtensa 浏览器接入](plans/2026-10-29-wasm-remaining-xtensa.md) | 后续交付计划 | `2026-10-29` | 六板独立组合、矩阵键盘、EPD QUALITY 抖色与真实输入/帧/清理；新 runtime 逐板验收后才能准入 |
| [剩余 Xtensa 浏览器准入证据](evidence/2026-10-29-wasm-remaining-xtensa/README.md) | 本地浏览器证据 | `2026-10-29` | 46 层固定源码、独立 engine Worker、矩阵键盘和 TCA W1C、EPD 精确抖色、10 板 11 例最终门禁；正式部署另验 |
| [浏览器性能与板型证据](evidence/2026-10-29-wasm-performance-devices/README.md) | 本地浏览器证据 | `2026-10-29` | 同固件 CPU 对照、实际动画像素变化与剩余触摸延迟；四板五示例按两个导出清单分别取证，不冒称正式 Pages 已更新 |
| [LVGL 正常时钟候选](evidence/2026-10-29-browser-lvgl-wallclock/README.md) | 限定候选证据 | `2026-10-29` | 显式 SDK Python 调度候选在同 guest 验证时间推进、真实字形/动画/触摸/PIR 和清理；stock SDK、C Timer 第一层和硬件不继承 |
| [正式 GitHub Pages 部署](evidence/2026-10-29-github-pages-production/README.md) | 当前部署证据 | `2026-10-29` | 原仓库 Actions 构建/部署成功；正式 HTTPS 地址独立执行真实 CoreS3 C/QEMU 21 项检查，LCD/触摸/PIR/QMP/分享重开/清理通过 |
| [Cardputer-ADV 用户固件兼容](evidence/2026-10-29-cardputer-adv-user-firmware/README.md) | 当前用户固件证据 | `2026-10-29` | 同一完整 Flash 的 ADC 错误、完整原生帧、自动竖屏设备/平面帧旋转、墙钟比例和旧矩阵输入门控；物理硬件不继承 |
| [CoreS3 C/QEMU 静态网页验收](evidence/2026-10-28-qemu-wasm-pages/README.md) | 历史证据 | `2026-10-28` | 固定源码完整构建、浏览器本地组合、真实 LCD/触摸/PIR及第二场分享启动/清理，Pages 单独记录 |
| [现有C/QEMU到WASM实验](qemu-wasm-port-research.md) / [构建与浏览器宿主证据](evidence/2026-10-28-qemu-wasm-build/README.md) / [CoreS3 guest证据](evidence/2026-10-28-qemu-wasm-cores3/README.md) | 历史执行研究 | `2026-10-28` | 固定当时完整WASM/CLI/QMP、CPU栈恢复、慢时钟CoreS3帧/触摸/PIR/停止重开；当时默认时钟失败保留，后续显式正常时钟候选、公众准入和部署分别以新证据为准 |
| [公众模拟器计划](plans/2026-10-28-public-simulator.md) | 进行中计划 | `2026-10-28` | 公众首页、Unit信息层级、新模型、URL分享、静态导出与部署前门禁 |
| [舵机、电源与复位预览](evidence/2026-10-29-motion-power-preview/README.md) | 限定虚拟设备与部署证据 | `2026-10-29` | StackChan UART/QOM 关节输出、同实例复位、真实 PMIC 关机及 fork Pages；Plus2 与完整回归仍开放 |
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
| [StopWatch / StickS3 / Core2 UIFlow2 全接口复测](evidence/2026-10-29-three-board-uiflow2-full-retest/README.md) | 当前三设备证据 / runner 修复 | `2026-10-29` | `fccfa931…` 上完成 system/shared、通信、音频、ESP-NOW、BLE 和已选外设；StopWatch/Core2 M5UI 505 方法全量审计，stock 三缺陷与 Core2 candidate 帧路由问题保留；修复设备尺寸/旋转、Core2 预算、BLE identity 和 blocker 文案 |
| [Core2 TIMG WDTFEED 写保护语义](evidence/2026-10-28-core2-timg-wdt-feed/README.md) | 当前 Core2 运行时证据 | `2026-10-28` | `0069` 让 `WDTFEED` 在 `WDTPROTECT` 下仍可喂狗，同时保留配置写保护；同固件 60 秒正常 WDT 仍在 `17.2529 s` TG0 stage-1 reset，startup UI、setup/REPL 和应用帧仍 OPEN |
| [Core2 legacy UART 与虚拟时钟对齐](evidence/2026-10-29-core2-legacy-uart-clock/README.md) | 当前 Core2 启动证据 | `2026-10-29` | `0070` 给 opt-in UART trace 加虚拟时间戳；WDT-off 下 BOARD/APIKEY 到 `55.00 s`、boot.py 到 `77.11 s`，normal WDT 仍 `17.25 s` reset；`shift=2` 也未消除 reset，不能把 accelerator override 当修复 |
| [Core2 legacy status/CAS 关联](evidence/2026-10-29-core2-legacy-status-cas/README.md) | 当前 Core2 诊断证据 | `2026-10-29` | `0075` 证明 RDSR WIP/BUSY 始终为 0，主要预算位于 `0xBB/64` 后的 scheduler/list 跨核锁竞争；failed-CAS slice yield 与原 normal-WDT 都在约 `17.249 s` 重置，`RUNTIME-03` 仍 OPEN |
| [Core2 legacy contended-CAS episodes](evidence/2026-10-29-core2-legacy-cas-episodes/README.md) | 当前 Core2 诊断证据 / 诊断修复 | `2026-10-29` | `0086` 修正 no-I/O TB 的 `Bad icount read`；热锁结构匹配到 `xTaskQueueMutex`/queue mux，failed-CAS yield 可缩短 10 秒 task-queue 等待，但 15 秒时等待转移到 queue mux 且 normal-WDT reset 不变；`RUNTIME-03` 仍 OPEN |
| [Core2 contended-CAS scheduler attribution](evidence/2026-10-29-core2-contended-cas-scheduler/README.md) | 当前 Core2 调度证据 | `2026-10-29` | `0088` 同 binary A/B 将 5 秒 CAS/contended/episode time 从 `1,070,625/984,964/2.240 s` 降到 `91,465/2,702/1.018 s`，SSI 工作近似不变；normal-WDT 仍 TG0 stage-1 reset，只证明 100 ms RR 放大 spin，不关闭 `RUNTIME-03` |
| [Core2 legacy IPC/flash handoff attribution](evidence/2026-10-29-core2-ipc-handoff-attribution/README.md) | 当前 Core2 诊断证据 / runner 控制 | `2026-10-29` | 三次 `17.2 s` normal-WDT freeze 稳定 CPU0 在 `spi_flash_op_block_func` 等待、CPU1 在 IPC/调度启动路径变化；显式 `--trace-sample` 防止跨 transaction 配对，2 秒全量控制的 13 对事务均为同步 `0 ns`；`RUNTIME-03` 仍 OPEN |
| [Core2 legacy flash handoff episode budget](evidence/2026-10-29-core2-handoff-episode-budget/README.md) | 当前 Core2 诊断证据 / 诊断修复 | `2026-10-29` | `0089` 修复 PC trace 的 `Bad icount read`；两次 normal-WDT 运行记录 reset 前约 `12.6k` 个 handoff，CPU0 block wait 累计约占 `57%`，单次最大 `<6.8 ms`；否定单次长 deadlock，启动仍在 WDT 前未完成，`RUNTIME-03` 保持 OPEN |
| [Core2 legacy handoff issuer/phases](evidence/2026-10-29-core2-handoff-issuer-phases/README.md) | 当前 Core2 诊断证据 | `2026-10-29` | 无 Flash issuer 的 handoff 仍约 `0.89 ms`；含一条 `0xBB/64` 和 status read 的 handoff 约 `0.86 ms`；initiator IPC 往返 source shape 独占约 `0.616 ms`。100us RR 与临时 can_start immediate-yield 均无改善，随后由 `0090` 的 per-vCPU icount budget cap 降低固定等待 |
| [Core2 per-vCPU icount fairness budget](evidence/2026-10-29-core2-icount-percpu-budget/README.md) | 当前 Core2 调度证据 / 默认修复 | `2026-10-29` | `0090` 为双 vCPU deterministic icount 增加默认 `10 us` per-vCPU budget cap；同 trace A/B 将 initiator `can_start→IPC return` 从 `563.7 us` 降到 `56.2 us`、peer block wait 从 `728.4 us` 降到 `184.7 us`，Core2 UIFlow2 设备组 `6/6 PASS`；normal WDT 仍在 `17.2429 s` reset，`RUNTIME-03` 保持 OPEN |
| [Core2 legacy boot budget 与 WiFi/UI wait](evidence/2026-10-30-core2-legacy-boot-to-ui-wait/README.md) | 当前 Core2 诊断证据 | `2026-10-30` | `shift=2` + `1 us` 在 normal WDT 下 `4.66 s` 到 BOARD/APIKEY、`8.50 s` 执行完原厂 boot.py，但仍为黑帧；WDT-off 15/20 秒双核 Waiti 且 Flash/cache 停在约 `9.36 s`，UART 诊断栈定位到 `wifiWebCfg/menu-wifi/m5stack_ui`，timing 控制不是产品修复 |
| [Core2 TIMG watchdog feed rescheduling](evidence/2026-10-30-core2-timg-feed-reschedule/README.md) | 当前 Core2 watchdog 语义修复 | `2026-10-30` | `0091` 用 `timer_mod_ns()` 替换 anticipate 语义，使 `WDTFEED` 可推迟已武装的后续阶段；重建运行得到 `3,651` nonblack pixels 的 live frame，但 TG0 stage-1 仍 reset，`RUNTIME-03` 保持 OPEN |
| [Core2 legacy menu after WiFi configuration stub](evidence/2026-10-30-core2-wifi-stub-menu/README.md) | 当前 Core2 启动诊断 | `2026-10-30` | 仅 stub `wifiWebCfg.config_by_web`，当前显示/LVGL 路径即可渲染完整 `320x240` UIFlow 菜单帧（`76,760` nonblack / `417` colors）；原厂 WiFi 配置分区仍为空，故 `RUNTIME-03` 保持 OPEN |
| [Core2 legacy deviceCfg WiFi overlay](evidence/2026-10-30-core2-legacy-wifi-config-overlay/README.md) | 当前 Core2 配置 fixture / 诊断 | `2026-10-30` | Core2 `qemu-wifi` 只对 session Flash 副本应用严格校验的 legacy `deviceCfg`，并记录 hashed SSID/base/effective SHA；同一 effective Flash 在诊断控制下显示真实 `Connecting to myssid`，默认 WDT 仍在 boot 后触发 cache panic，`RUNTIME-03` 保持 OPEN |
| [Core2 concurrent capacity boundary](evidence/2026-10-30-core2-concurrent-capacity-boundary/README.md) | 当前 Core2 容量 / 重检证据 | `2026-10-30` | 九实例两次 `9/9 PASS`、一次 `8/9` 并在 `ble_hs_hci_process_ack` panic，因此默认单设备容量保持 8；当前 tool hash 两批 `2x60s` 为 `4/4 PASS`，网络重检有限重试、PSRAM/network error 分字段，八实例 cold-start 重绑和物理/controller 边界仍 OPEN |
| [Core2 current tool-hash rebind](evidence/2026-10-30-core2-toolhash-rebind/README.md) | 当前 Core2 工具哈希回归 | `2026-10-30` | SVC-03 拆分后 `device_service` hash 更新为 `a96b1506…`；在 `origin/main@3fc436e4` 上两批独立零错峰 `2x60s` 均 `2/2 PASS`，合计 `4/4`，HLI/PSRAM/网络/GATT/frame/QOM/pcap/evidence/cleanup 全部通过；不覆盖八实例 cold-start、九实例容量或物理边界 |
| [Device Service storage/NVS parsing boundary](evidence/2026-10-30-svc03-execution-parsing/README.md) | `SVC-03` 边界重构证据 | `2026-10-30` | storage/NVS execution request parser 移至独立无状态模块，`device_service.py` 保持 same-object re-export；专向 `5/5`、Device Service `126/126`，错误码、返回结构和 API 不变 |
| [Device Service network execution parsing boundary](evidence/2026-10-30-svc03-network-execution/README.md) | `SVC-03` 边界重构证据 | `2026-10-30` | esp-emu network execution request parser 移至独立无状态模块，`device_service.py` 保持 same-object re-export；专向 `4/4`、Device Service `126/126`，profile/port/ELF/I2C 契约不变 |
| [Device Service QEMU WiFi semantic boundary](evidence/2026-10-30-svc03-qemu-wifi/README.md) | `SVC-03` 边界重构证据 | `2026-10-30` | QEMU WiFi security parser 和 runtime-env projection 移至独立模块，`device_service.py` 保持 same-object re-export；专向 `4/4`、Device Service `126/126`，open/WPA2 与 S3 trace gate 不变 |
| [Core2 WiFi IRQ cache handoff gate](evidence/2026-10-30-core2-wifi-irq-cache-gate/README.md) | 历史 Core2 中断语义修复 | `2026-10-30` | `0092` 在 instruction cache disabled 时只暂存 WiFi MAC level，cache restore 后重放；默认 budget 的同固件不再出现 cache-disabled panic，并到达 API Key 页面。该里程碑后的 TG0 WDT reset 已由 `0095` 记录解除 |
| [Core2 classic WiFi station timing and data path](evidence/2026-10-30-core2-classic-wifi-station-time/README.md) | 历史 Core2 WiFi 语义/数据面修复 | `2026-10-30` | `0093/0094` 将 classic WiFi beacon/inject/timestamp 改用 virtual time，并让 station DHCP 与双向数据使用正常 slirp 路径；stock Core2 WiFi scan→association→DHCP→HTTP `5/5 PASS`、IP `10.0.2.15`。该轮 normal-WDT reset 后由 `0095` 记录解除 |
| [Core2 legacy WDT level delivery](evidence/2026-10-30-core2-legacy-wdt-level-delivery/README.md) | 当前 Core2 watchdog/startup 修复 | `2026-10-30` | `0095` 按 `WDTCONFIG0.LEVEL_INT_EN` 修复 legacy task-WDT level delivery；同一 public SHA 三次 normal-WDT Device Service 均越过原 stage-1 reset、稳定到 guest virtual 300 秒以上并保持 API Key startup UI，Core2 设备组 `6/6 PASS` |
| [Device Service network parsing boundary](evidence/2026-10-30-svc03-network-parsing/README.md) | `SVC-03` 边界重构证据 | `2026-10-30` | network policy/CNAME parser 移到 `device_service_network.py`，`device_service.py` 保持 same-object re-export；定向与 network-focused tests PASS，不改变 HTTP/state/evidence 语义 |
| [Device Service device-spec boundary](evidence/2026-10-30-svc03-device-specs/README.md) | `SVC-03` 边界重构证据 | `2026-10-30` | `DeviceSpec`、catalog/matrix/profile 解析、backend 路径与 runtime profile 选择移到 `device_service_specs.py`；原模块 same-object re-export，定向 `5/5 PASS`，不改变 HTTP/QEMU/session/evidence 语义 |
| [Cardputer-ADV 当前参考固件 BMI270 闭环](evidence/2026-10-29-cardputer-adv-imu/README.md) | 当前设备证据 | `2026-10-29` | I2C `0x69`、CHIP_ID/INIT/data-ready 与 `0x0C..0x17` 读取可达；Device Service 注入经官方 `Imu.getAccel/getGyro` 回读，原样矩阵首轮 PASS；关闭当前参考固件 IMU 全零待办，物理精度仍 NOT RUN |
| [Core2 legacy pre-boot phase profile](evidence/2026-10-29-core2-preboot-phase-profile/README.md) | 当前 Core2 诊断证据 | `2026-10-29` | 显式 PC/UART sampling 记录 WDT-off 80 秒的 SSI transaction/RX 聚合总量与 108 个采样 begin event；全量 command/length 分布仍未知，四类立即切核控制均无改善并丢弃，normal-WDT 仍 stage-1 reset |
| [Core2 SSI transaction profile](evidence/2026-10-29-core2-ssi-transaction-profile/README.md) | 当前 Core2 诊断证据 | `2026-10-29` | `0071` 输出完整 command、RX-length、completion→next-command gap 聚合；无采样控制得到约五万组 `0x05` 与 `0xBB/64B`，`79.7/80 s` 位于相邻 command 间隔；normal-WDT 仍 `17.2537 s` reset，`RUNTIME-03` 保持 OPEN |
| [Core2 SSI command correlation](evidence/2026-10-29-core2-ssi-command-correlation/README.md) | 当前 Core2 诊断证据 | `2026-10-29` | `0072` 确认 `0xBB/64 -> 0x05/1 -> 0xBB/64` 主循环；`82.4%` gap 位于下一次 status read 前，平均 `1.3115 ms`；normal-WDT 仍 `17.2494 s` reset，`RUNTIME-03` 保持 OPEN |
| [Core2 SSI command issuer PC](evidence/2026-10-29-core2-ssi-command-pc/README.md) | 当前 Core2 诊断证据 | `2026-10-29` | `0073` 将 `0x05` 主要绑定到 ROM `esp_rom_spiflash_read_user_cmd` 区间的 `0x4006222c`，将 `0xBB/64` 主要绑定到应用 segment 5 的 `0x40093b57`；PC 表总数等于 `105,161` transactions，normal-WDT 仍 `17.2536 s` reset，无 matching ELF 函数名，`RUNTIME-03` 保持 OPEN |
| [Core2 M5UI panel DMA 双写修复](evidence/2026-10-29-core2-m5ui-dma-dedup/README.md) | 当前 Core2 UIFlow2 证据 | `2026-10-29` | `0074` 修复 DMA descriptor 与 CPU data-register 对同一 panel flush 的双消费；`6400`-byte strip 从写成 `12736` bytes 变为 exact，candidate 4 个状态与 2 个 frame oracle 全部 PASS |
| [Core2 post-reset teardown](evidence/2026-10-29-core2-post-reset-teardown/README.md) | 当前 CORE2-02 teardown 证据 | `2026-10-29` | 三个 ready session 先冻结 frame/QOM/network/GATT/pcap，再执行 guest `system_reset`；同一 QEMU PID reboot-in-flight 时仍 running，随后 stop、companion/PID/lease cleanup 与下一轮恢复均 `3/3 PASS`；不关闭 controller/物理/真机边界 |
| [Core2 stock BLE via native HCI](evidence/2026-10-29-core2-stock-ble-native-hci/README.md) | 当前 Core2 BLE 证据 / runner 修正 | `2026-10-29` | stock UIFlow2 `ble-nus` 改走 `core2-native-hci` + matching ELF；三个独立 session 各 `8/8 PASS`，peer 实际收到 `ACK:M5_CORE2_UNIFIED`；StopWatch/StickS3 stock controller、安全与 RF 不继承 |
| [Device Service runtime boundary 与 Core2 unified 稳定性](evidence/2026-10-29-svc03-runtime-boundary/README.md) | 当前 service 证据 / 调度修复 | `2026-10-29` | 无状态 runtime 参数/脱敏边界独立；profile QOM 跟随 session readiness，Core2 unified 默认 180 秒；BLE peer 在订阅后等待 10 秒再写，避免慢 guest TX 未就绪；最终 firmware/ELF/QEMU 三条独立 lease 全 PASS，WiFi、公网、NUS ACK、frame/QOM、HLI、pcap、ZIP 和清理完整 |
| [Core2 `m5ble.Server.get_client` candidate](evidence/2026-10-29-m5ble-get-client-candidate/README.md) | 当前 Core2 BLE 候选证据 / teardown 时序 | `2026-10-29` | stock `m5ble-server` 保留 `21 PASS + 1 ERROR`；`0021 → 0025` 最终候选两轮均 `22/22 PASS`；并发断连后的 `deinit` 竞争以 2 秒 settle 修正，stock/candidate 复核均 PASS；真机/安全/RF NOT RUN |
| [StopWatch / StickS3 / Core2 UIFlow2 接口再次复测](evidence/2026-10-29-three-board-uiflow2-interface-retest-r2/README.md) | 当前三设备证据 / M5UI runner | `2026-10-29` | `9bf74439…` 上三台重新完成 system/shared、协议、板级接口和 ESP-NOW；StopWatch/Core2 重跑 28 类、505 个 M5UI widget 方法与两个 lifecycle 项；requests2/Modbus/TLS/M5UI 与 `0021+0025` M5BLE candidate 全部复验；stock SDK、StopWatch/StickS3 BLE 和物理边界保留 |
| [最新 QEMU 三设备 UIFlow2 接口复测](evidence/2026-10-29-three-board-uiflow2-interface-retest-r3/README.md) | 当前三设备证据 | `2026-10-29` | `05a43941…` 上三台 system/shared、协议、audio、ESP-NOW、BLE 和板级接口重跑；StopWatch/Core2 M5UI 仍 507 结果零漏测；stock SDK 缺陷和 candidate 结果保持不变；Core2 network 首轮并发扫描毛刺经隔离及 4 次并发重复控制；真机/RF/legacy 边界保留 |
| [当前 QEMU 三设备 UIFlow2 接口复测 r4](evidence/2026-10-29-three-board-uiflow2-interface-retest-r4/README.md) | 当前三设备证据 | `2026-10-29` | `dd4b1b34…` 上三台并发重跑 system/shared、协议、audio、ESP-NOW、BLE、M5UI 和板级接口；Core2 network 首次并发恢复 `14/14`；stock SDK 与 BLE 边界不变，三台协议 candidate 和 StopWatch/Core2 M5UI candidate 全部通过 |
| [ESP-NOW 外部明文 peer](evidence/2026-10-29-espnow-external-peer/README.md) | 当前 ESP-NOW 外部 peer 证据 | `2026-10-29` | `0076` 以成对 loopback UDP 端口连接两个独立 controller；StopWatch↔StickS3、Core2↔StopWatch 均经正常 TX/RX DMA 双向收到 action-frame payload；四个 session evidence/清理完整；PMK/LMK/CCMP、错误 key、lifecycle、RF 和真机仍 NOT RUN |
| [ESP-NOW external peer CCMP](evidence/2026-10-29-espnow-external-ccmp/README.md) | 当前 ESP-NOW 加密证据 | `2026-10-29` | `0077` 在 external bridge 执行 PMK-wrapped LMK、AES-CCMP/MIC 和 drop-before-DMA；正确 key 跨 StopWatch/StickS3/Core2 交付，错误 LMK 双向 `rx_packets=0`，wrong-PMK/same-LMK 按官方语义 PASS；guest key-state 传播、replay、lifecycle、RF 和真机仍 NOT RUN |
| [ESP-NOW external CCMP replay](evidence/2026-10-29-espnow-external-ccmp-replay/README.md) | 当前 ESP-NOW replay 证据 | `2026-10-29` | `0078` 对 MIC 成功的单 peer CCMP PN 执行 monotonic guard；UDP proxy 重复一帧后 receiver 记录一次 replay drop 且 guest payload 不重复；wrong-LMK 与 Core2 encrypted 回归保持；多 peer/乱序窗口、key rotation、RF 和真机仍 NOT RUN |
| [ESP-NOW native peer lifecycle](evidence/2026-10-29-espnow-peer-lifecycle/README.md) | 当前 ESP-NOW lifecycle 证据 | `2026-10-29` | stock native API 在 StopWatch/StickS3/Core2 完成 encrypted add、delete、NOT_FOUND 负控、modify、re-add 与 post-resume delivery；双向 PRE barrier 修复 Core2 首轮竞态；guest key-state 写入 bridge、key rotation、多 peer replay、RF 和真机仍 NOT RUN |
| [M5ESPNow wrapper lifecycle](evidence/2026-10-29-espnow-m5espnow-lifecycle/README.md) | 当前 ESP-NOW wrapper 证据 | `2026-10-29` | `m5espnow.M5ESPNow` 在 StopWatch/StickS3/Core2 完成 set_add_peer、peer list 清空、delete 后 send_data no-op、re-add 与 post-resume；guest key-state、key rotation、多 peer replay、RF 和真机仍 NOT RUN |
| [ESP-NOW CCMP replay window](evidence/2026-10-29-espnow-external-ccmp-window/README.md) | 当前 ESP-NOW reorder 证据 | `2026-10-29` | `0079` 提供单 peer 64-frame authenticated window；UDP ReorderProxy 交换两帧后 replay drop 为 0 且双向 payload 保持；duplicate replay 仍 drop，Core2 encrypted 回归 PASS；multi-peer window、key rotation、RF 和真机仍 NOT RUN |
| [ESP-NOW guest controller key-state](evidence/2026-10-29-espnow-guest-key-state/README.md) | 当前 ESP-NOW key lifecycle 证据 | `2026-10-29` | `0080` 将 classic ESP32/S3 crypto key store 接到 external bridge；runtime-env 不含 PMK/LMK 时，stock guest 写入 slot 24 后正控双向交付，不同 guest LMK 两端 `rx_packets=0`，delete/re-add/modify 轮换新共享 LMK 后恢复；multi-peer、PN wrap、RF 和真机仍 NOT RUN |
| [ESP-NOW 三 guest shared-LMK fabric](evidence/2026-10-29-espnow-peer-fabric/README.md) | ESP-NOW shared-LMK fabric 证据 | `2026-10-29` | `0081` 让 StopWatch/StickS3/Core2 经同一个 broker 双向三端交付；synthetic MAC 在 CCMP 前写入，replay window 按 source peer 分片 8×64；重复真实 forwarded frame 仅目标 receiver 记录一次 drop；0081 本身限定 shared LMK，per-peer routing 由后续 0082 单独验证 |
| [ESP-NOW per-peer LMK routing](evidence/2026-10-29-espnow-per-peer-key-routing/README.md) | ESP-NOW pairwise-key 证据 | `2026-10-29` | `0082` 从 stock key entry bytes `0..5` 取 peer MAC、`8..23` 取 LMK，TX/RX 按方向选 key，并为每 slot 保存独立 TX PN；三个 pairwise key 的六方向 PASS，B/A cross-wire 只使 A↔B 归零；shared-LMK 与 direct guest-key 回归保持；PN lifecycle 由后续 0083 单独验证 |
| [ESP-NOW CCMP PN exhaustion and rekey](evidence/2026-10-29-espnow-ccmp-pn-exhaustion/README.md) | 当前 ESP-NOW PN lifecycle 证据 | `2026-10-29` | `0083` 在 `0xffffffffffff` fail closed、不回绕；新 LMK 后恢复双向 payload，相同 LMK 重写保持 PN/replay 并继续 drop；shared-LMK、pairwise 正控和 cross-wire 回归 PASS；loss/retry、channel/rate、RF 和真机仍 NOT RUN |
| [ESP-NOW loss/retry, channel/rate and soak](evidence/2026-10-29-espnow-loss-channel-rate/README.md) | 当前 ESP-NOW link-condition 证据 | `2026-10-29` | `0084` 在真实 frame bridge 上传递并校验 channel/rate metadata；受控丢两帧后重试恢复，channel 6 正控 PASS、1↔6 各 40 次 drop，11/24 Mbps 混合交付，60 秒双向 soak 超千次 TX/RX 且无重复/错误；仅为 virtual link，RF、bit-exact controller 和真机仍 NOT RUN |
| [Worker claim response-loss idempotency](evidence/2026-10-29-worker-claim-idempotency/README.md) | 当前 durable queue claim 证据 | `2026-10-29` | 真实 HTTP/WorkerAgent 在首个 claim response 被丢弃后复用同 key 重试；restart 前后同 job/lease，第二 job 保持 queued，异请求 409、过期 lease fail closed，raw key 不落盘；物理跨主机、QEMU guest 和外部 side-effect fence 仍 NOT RUN |
| [Lease-bound remote evidence store](evidence/2026-10-29-lease-bound-evidence-store/README.md) | 当前 worker evidence 证据 | `2026-10-29` | 真实 HTTP WorkerAgent 上传约 2 MiB ZIP，上传 response 丢失后同 bytes 重试返回原 evidence ID；control-plane restart 后 metadata/content 一致，异 bytes 与错误 result binding 409，`0600` 文件且 raw payload 不进入 queue/log；物理跨主机和对象存储复制仍 NOT RUN |
| [Device Service runtime ACL](evidence/2026-10-29-runtime-acl/README.md) | 当前 service runtime policy 证据 | `2026-10-29` | 外部 operator JSON 按设备限制 serial/input/reset、program execute/interrupt/read、package write 和 flash read；真实 HTTP 的未授权操作在 console/QMP/flash I/O 前 403，policy hash/有效权限可审计，package deny path 不创建 revision；guest filesystem ACL、native firmware 沙箱、QEMU 和真机仍 NOT RUN |
| [Core2 for AWS ATECC608](evidence/2026-10-29-core2-atecc608/README.md) | 当前 Core2 runtime-model 证据 | `2026-10-29` | `0085` 在 `0x35` 实现 wake/Read/Info/CRC 和锁定测试 config，并修复 classic ESP32 DMA link-start/DC；公开固件三个独立 session 从 `atcab_init=f0`/abort 推进到 `atecc608: ok: 60 02` 与非空帧；生产 key、ECDSA、电气和真机不继承 |
| [Unit Relay/Relay2 hard-reset边界](evidence/2026-10-29-unit-hard-reset-output-boundary/README.md) | 当前 Unit 复位证据 | `2026-10-29` | `0087` 让共享 GPIO reset 先建立复位后电平/通知 observer，再走正常 listener；AtomS3R 同固件 A/B 中 pre-fix 单 Relay/Relay2 计数跨 reset 泄漏，fixed 在 reset 清零后分别从独立高电平重新计数；数字 GPIO only，机械/电气/其它 Unit reset 不继承 |
| [FlashLight cold-route四host](evidence/2026-10-29-flashlight-cold-route-four-host/README.md) | 当前 Unit 冷启动证据 | `2026-10-29` | `0047/e318` 在 CoreS3/AtomS3R/StickS3/StopWatch 用原厂constructor、100%/220ms Flash和Run替换，从`ready-low`到`flash-active`再回`ready-low`；actual QOM mounted replay PASS，实时Web、动态S1/PWM/光电/热/真机不继承 |
| [Device Service API](device-service-api.md) / [OpenAPI](device-service.openapi.yaml) | 契约 | `2026-10-29` | `1.51.0`；新增 operator-owned runtime ACL/执行策略，session/capacity 暴露 policy hash 与有效权限；保留 1.50 worker evidence、claim response-loss replay、Unit准入、冻结 schema、lease/evidence 及网络契约 |
| [外部 Agent Unit API](unit-agent-api.md) | 调用指南 | `2026-10-29` | UIFlow2 源码提交、caller-source pin、可见 session、Unit 配置和取证；CoreS3 选定场景的源码请求与原驱动/custom 边界，Relay/Relay2 hard-reset A/B 已限定闭环，硬件 NOT RUN |
| [统一设备运行时契约](unified-device-runtime.md) | 契约 | `2026-10-26` | 单 lease、单 guest、单固件、单 evidence bundle 的不变量和状态语义 |
| [Core2 native HCI backend](core2-native-hci-backend.md) | 设计 / 验证专题 | `2026-10-30` | native-HCI 数据面、PSRAM/MMU、长稳、重连、active-stop、post-reset stop、八实例容量和九实例 fail-closed 边界；轮次与哈希只在该专题的日期化证据中，旧失败 control 保留为历史 |
| [FirmwareManifest](firmware-manifest.md) | 契约 | `2026-10-26` | 导入、规范化、ZIP path/casefold/symlink 与资源唯一性、多 build SoC 选择、mandatory `capabilities.required/optional`、WebBurner 分段 size/digest 复算及来源展示、Secure Boot v2 签名/包内 eFuse 摘要与 anti-rollback version 对照、aggregate/image/eFuse understatement fail-closed、文件系统/许可策略、sdkconfig detected / image observed capability 和 evidence 分层 |
| [运行时模型缺口登记](runtime-model-gap-register.md) | 缺口登记 | `2026-10-30` | 每个 `RUNTIME-*` 的现象、证据、修复状态和关闭条件；`0095` 已关闭 legacy Core2 normal-WDT stock startup，setup/REPL 与任意应用转 `API-01`；`RUNTIME-02` Zigbee commissioning 仍 `OPEN`；`RUNTIME-06` virtual-controller 已完成，bit-exact controller、物理 RF/电气和真机仍独立 |
| [网络模拟方案](network-simulation-plan.md) | 架构 / 验收专题 | `2026-10-26` | 网络模式、有界 CIDR egress、domain/CNAME、multicast/unicast discovery、worker process/QEMU 与 `qemu-unified` companion partition fencing、namespace/container-local execution、同 guest 网络生命周期和证据要求；运行比例转交验证台账 |
| [网络诊断 lane](network-lane.md) | 专题 | `2026-10-26` | 只描述诊断/Provisioning，不混同 unified 验收；Linux namespace IPv6 guest 生命周期已 PASS |
| [虚拟主机矩阵](qemu-device-adaptation-matrix.md) | 当前事实 | `2026-10-26` | 当前登记设备与各 QEMU/Tab5/Linux 后端、稳定运行时映射和能力边界；设备数量与运行比例分别转交自动快照和验证台账 |
| [UIFlow2 外设矩阵](uiflow2-peripheral-test-matrix.md) | 当前事实 | `2026-10-26` | 外设数据面和 runner 语义；主线完整矩阵基线由 `0036` stateful SSI 重建定义，`0038` 为 exact-time 诊断加定向回归；Unit 扩展 runtime 的完整门禁分别核验，不跨 binary 拼接；轮次和 case/check 数量只查验证台账与 evidence |
| [Tab5 暂缓项](tab5-deferred-backlog.md) | 专项 Backlog | `2026-10-26` | 能力仍以 2026-10-22 定向证据为基线；后来的 S3/C6/Core2 无线工作不继承给 P4 |
| [设备视觉保真](device-visual-fidelity-backlog.md) | 专项 Backlog | `2026-10-26` | StopWatch 是唯一参考质量外壳；后续功能验证不代表视觉模型已升级 |
| [Core2 cache/WDT 调查](core2-cache-panic-investigation.md) | 历史根因 | `2026-10-30` | 保留旧命名和复现、TCG translation-buffer 归因与 UIFlow2 门禁；补充 timer/WDT-mask、stateful SSI、统一 timeline、WDT-disabled 对照、public BIN/local ELF 字节审计、exact-time SIGSTOP freeze 和三次 WDT liveness 对账。历史 `800 ms` 现象未在当前配置复现；后续 `0095` 关闭 virtual stock startup，setup/REPL 与任意应用另验 |
| [跨设备回归审计](uiflow2-cross-device-regression-audit.md) | 历史证据 | `2026-10-21` | 固定在当轮修复和截图 |
| [StopWatch QEMU 启动](stopwatch-uiflow2-qemu.md) | 历史证据 | `2026-10-20` | 解释初轮启动链，不描述后续 multi-board 能力 |
| [部署与运行时资产](deployment.md) | 运维指南 | `2026-10-30` | 区分目录/浏览器导出/原生服务资产，解释匹配源码与主机架构、历史运行时包和隔离权限的边界 |
| [设备中心接入契约](device-center-adapter.md) | 接口契约 | `2026-10-26` | 目录、外设接口、设备状态、worker lifecycle 与页面消息 |
| [虚拟设备功能测试工作流](device-functional-test-workflow.md) | 工作流契约 | `2026-10-30` | 原生功能测试使用可观察 Device Service 会话；显式浏览器验证另保留同实例输入/帧与清理，不混用证据 |
| [固件审查与仿真工作流](firmware-review-and-simulation-workflow.md) | 工作流契约 | `2026-10-26` | 审查方法和证据分层、Secure Boot v2/包内 eFuse 摘要与 anti-rollback version 对照、公开 BIN 刷新/SHA 绑定、运行路径和发布门禁；当前进度回权威状态页 |
| [外设仿真架构](peripheral-simulation-architecture.md) | 实现专题 | `2026-10-26` | catalog、runtime coverage、S3 WPA2/Core2 native-HCI 边界和后端数据面 |
| [P4 外设后端要求](p4-peripheral-backend-requirements.md) | 专项设计 | `2026-10-26` | Tab5 缺失的 P4 控制器、DMA 和端点；仍以 2026-10-22 focused probe 为能力基线 |
| [模拟器服务架构](simulator-service-architecture.md) | 设计 / 运维 | `2026-10-26` | 单机模块化单体、control/runtime 分离、multicast/unicast discovery、network-partition fence、双 namespace worker-local QEMU、companion recovery 和 warm-pool 边界 |
| [热门用户固件矩阵](user-firmware-simulation-matrix.md) | 验证工具与历史基线 | `2026-10-30` | 历史哈希绑定结果、公开 CDN 强制刷新、四个刷新样本、SD/NVS fixture、OpenAI 首次启动对照；Core2 2026-10-26 基线之后由 `0095` 关闭 virtual stock startup，setup/REPL 与任意应用仍另验 |
| [CoreS3 图像边界](cores3-image-rendering-boundary.md) | 已知差异 | `2026-10-26` | 仍固定在 2026-10-22 透明度/调色板图像分析，状态保持 `OPEN` |
| [CoreS3 三渲染器](cores3-three-renderer.md) | 历史证据 | `2026-10-22` | 固定三种渲染路径的对比 |
| [StickS3 三渲染器](sticks3-three-renderer.md) | 历史证据 | `2026-10-22` | 固定三种渲染路径的对比 |
| [多设备模拟器设计](plans/2026-10-20-multi-device-emulator-design.md) | 历史设计 | `2026-10-20` | 早期后端和能力分层，不代表当前设备状态 |
| [Unit 集成计划](plans/2026-10-25-unit-runtime-integration.md) | 实现设计 | `2026-10-27` | 同guest程序、限定Unit原驱动与QEMU按需共享采样；完整文件包/纯字节码依赖已接入；其余Unit、AIFlow/Preview/SSE及保存开机仍开放；视觉与功能协议分别验收 |
| [Unit 接入问题](unit-integration-host-issues.md) | 参考记录 | `2026-10-29` | 接入期间发现的主机问题与处理边界；UNIT-HOST-36 以数字 Relay/Relay2 A/B 关闭 |
| [AIFlow实时预览API评估计划](plans/2026-10-26-aiflow-live-preview-api.md) | 实现/设计 | `2026-10-27` | UIFlow同guest程序、QEMU按需共享帧和1.42 Preview/Run基础已实现；限定Web托管消费者已验，SSE与AIFlow完整接入仍待做，继承Unit/服务Backlog |
| [同VM Preview/Run控制面](plans/2026-10-27-preview-run-control.md) | 实施计划 | `2026-10-27` | 持久化身份/幂等/latest-wins、真实prompt取消、managed session与输入/帧fence；CoreS3 PIR/Relay限定实际会话与宿主负控已验，PIR部署事务取消已验，AIFlow/其它Web组合/GC仍开放 |
| [Preview Web消费者](plans/2026-10-27-preview-web-consumer.md) | 实施计划 | `2026-10-27` | 共享Preview身份、完整包保留编辑、主机/Unit输入、Run帧与生命周期；CoreS3 PIR/Relay限定真实Web验收完成，AIFlow/SSE仍开放；构图限定修复见下一块 |
| [Preview 控制组与 2Relay](plans/2026-10-27-preview-controls-and-2relay.md) | 实施计划 | `2026-10-27` | 四主机同VM丰富HUB控制组、U131双GPIO/蓝灯和限定窄屏/长dt相机已验；新运行时定向7PASS、完整矩阵66/67，边界保留 |
| [二进制checkpoint与Unit协议](plans/2026-10-27-binary-checkpoint-and-unit-protocols.md) | 实施计划 | `2026-10-27` | 分开不可变二进制包存储与固件loader能力，先验证旧Run不被不支持入口打断；兼容固件隔离构建与4Relay/FlashLight协议核对进行中 |
| [FlashLight与显式UIFlow base](plans/2026-10-27-flashlight-and-uploaded-uiflow-base.md) | 实施计划 | `2026-10-27` | 本块完成严格base、候选loader诊断与FlashLight限定GPIO/Web验收；公共main.mpy、动态route历史与AIFlow继续 |
| [公共main.mpy实时入口](plans/2026-10-27-public-main-mpy-runtime.md) | 实施计划 | `2026-10-27` | 真实bytecode canary、会话身份绑定、显式base Preview与同VM import派发/恢复；stock能力保持分层 |
| [FlashLight路由历史](plans/2026-10-27-flashlight-route-history.md) | 实施计划 | `2026-10-27` | UNIT-HOST-38真实GPIO路由生命周期、旧资格失效与新EN复位恢复；冷route/PWM/S1保持独立 |
| [FlashLight冷pad观察](plans/2026-10-27-flashlight-cold-pad-observation.md) | 实施计划 | `2026-10-29` | UNIT-HOST-37真实GPIO/IOMUX/OE/来源事件、无边沿连续低基线与原驱动自然复位；新四host原厂constructor/API和QOM Web replay已闭合cold baseline，实时Web/动态S1/PWM仍独立 |
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
- [Cardputer-ADV BMI270 当前参考固件闭环](evidence/2026-10-29-cardputer-adv-imu/README.md)
- [Cardputer-ADV 用户固件显示、时钟与输入兼容](evidence/2026-10-29-cardputer-adv-user-firmware/README.md)
- [Core2 legacy pre-boot phase profile](evidence/2026-10-29-core2-preboot-phase-profile/README.md)
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
- [Worker claim response-loss idempotency](../tests/network/worker_claim_idempotency/README.md)
- [Lease-bound remote evidence persistence](../tests/network/evidence_store/README.md)
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

## Agent Skills 调用侧资料

- [通用与 AIFlow Skill 分发](plans/2026-10-29-agent-skills.md)
- [AIFlow consumer 历史验证](plans/2026-10-27-aiflow-simulator-skill.md)
- [安装与打包](../skills/README.md)
