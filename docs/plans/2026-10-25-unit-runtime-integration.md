# Unit 外设与视觉模型集成

日期：2026-10-26。状态：进行中。执行任务登记在 `docs/project-backlog.md` 的
`UNIT-01`；本页维护实现契约与验收证据，不建立独立任务队列。

## 用户目标

把持续开发的视觉模型库中已完成的主机外壳接入现有平台；为对应的一批 Unit
实现官方芯片/协议层功能，并接入当前主机。固件输出驱动画面与动画，Web
输入通过真实总线/控制器影响主机与外设，两条方向都需要运行证据。发现的
主机问题记录在本项目；仅直接阻断接入或范围明确的小问题随本次修复。

2026-10-26 用户补充：本控制器验证块结束后拉取并合并最新主线，再继续 Unit。
近期交付按外部 Agent 可调用的链路验收：创建虚拟设备、选择 Unit、提交 UIFlow
Python 源码运行，网页实时显示同一 guest/controller 的主机与 Unit 状态，并可
双向操作。保留后续型号范围，先交付能完整走通接口链路的一批 Unit。

## 并行开发边界

- 从 `main@eff1561` 建立隔离工作树和 `codex/unit-runtime-integration` 分支。
- 不修改另一个会话的模型源码；导入公开库固定 commit 的运行文件、来源
  清单和许可。后续同步必须显式，不能从不断变化的工作目录隐式加载。
- 主机运行时、API 和已有固件路径保持兼容；新增 source pin 只在新 UIFlow
  源码固件的 session 中必填，旧固件路径保持原请求方式。
- 私有研究素材、凭据、固件/ROM/运行时二进制不入 Git。
- 用户已明确本任务不归档外部 `agent-work-logs`（`SKIPPED_BY_USER`）；
  仓库内的实现文档、验证台账和可复现 evidence 继续维护。

## 实现契约

视觉资源采用模型库公开 API。适配层负责屏幕、按钮、触摸、LED、关节、
附件和释放生命周期；视觉状态回放不能产生新的输入事件。

Unit 目录单独记录 SKU/版本、官方来源、芯片、地址/引脚、驱动路径、输入/
输出范围、运行时模型、主机端口兼容性和验证状态。视觉 modeled、协议
implemented 和运行 validated 是独立层级；不支持的主机/协议明确拒绝。

Session 的附件配置必须持久化并进入证据包。每份附件有稳定实例 ID 和
QOM/控制器路径；Web 输入需验证字段和物理范围。读回必须来自当前 guest
所连接的模型，不能由 Python 缓存输入假装完成数据面。

I2C/SPI/UART/GPIO/ADC/PWM/单线总线按真实控制器接线。若现有后端缺路径，
记录具体 blocker，继续补控制器，而不把 host 假值标记为 simulated。

## 验收

- 已完成外壳接入现有设备页与 Live sessions，固件 framebuffer 与实体输入
  兼容；真实浏览器检查所有主机，保留截图和控制交互证据。
- Unit 批次以固定视觉目录为范围快照，逐项保留官方协议依据、接线、模型
  和同设备固件 probe；后续新增型号可以显式追加，不隐式扩大 PASS。
- 至少逐 Unit 验证 Web→模型→guest 读取，以及 guest 写入→模型→Web
  输出；记录相应总线/控制器计数、串口、画面和证据 ZIP。
- 功能验证统一走 `/api/v1` 可见会话，停止前取证，`purge=0` 保留历史。
- 平台契约、目录/coverage/profile/snapshot 检查和受影响设备回归通过。
  共享控制器变更需要按仓库规则运行 full matrix；缺运行时不写运行 PASS。
- 更新状态、Backlog、API/OpenAPI、代码地图、验证台账及工作记录；主机
  问题和暂未完成型号保持明确开放，不把子批次当作全部目标完成。

## 当前检查点

已定位模型会话「为 M5Stack Unit 建立 3D 模型」，公开库
`m5stack-models` 固定导入候选 `48ab992f5ff63c1a91296051e1afcb5959877903`，
包含 14 款主机和 27 款 Unit。视觉源声明 `visual-only`，当前没有内部电气
模拟，必须由本项目补齐。

初始检查发现系统 `python3` 为 3.9；本轮使用 Python 3.12 和独立依赖目录。
Xtensa 运行时已恢复并从固定公开源码冷构建，补丁正反重放及源码指纹可核对。
27 款 runtime 条目均是 `implemented`，全部型号已准入 CoreS3；
Button/Relay/ENV III 另有 AtomS3R、StickS3、StopWatch 的设备本地证据。
五款 I2C 控制类的显示修正固件已分别完成这三主机的设备本地功能验证，
实际最终帧可读；精确结果加入主机验证元数据。原批 AtomS3R 的原生多行
可读性 `PARTIAL` 仍为历史；新固件有独立执行，不继承旧固件 PASS。
来源和范围见状态页与[三批归档](../evidence/2026-10-26-unit-control-display-gen9-a8fe/README.md)。
首批 Button/Relay/ENV III 已完成 Device Service 同 guest 功能取证；其他
控制类、传感器与 I/O 分组分别验证，最终结论只在状态页和验证台账维护。

Session 已冻结 Unit schema/QOM mapping 与源文件 hash，并将契约纳入 ZIP；
HUB 使用显式 `parent_id` 与三输出口的附件树，继承真实物理 pins，不是
PAHUB multiplexer。多个 I2C leaf 的重复地址、拓扑循环和未建模的 GPIO
并联冲突必须拒绝。共享控制器已在六层补丁的独立完整轮次中通过，详见
验证台账；CoreS3 逐型号 Web 选择和三主机首批证据分开维护。12 款读数已接入
严格来源的 rail。扩展读数按显式九款原批成功记录加 Light/Thermal 新批选择，
11 款原驱动路径通过；旧 Light 五/六 POST 预期失败保持原样，新检查同时要求
首 POST 前真实 GET 证明初始 false。Thermal 两份 raw fixture 经过 guest
计算，rail 只展示控制字与就绪状态。Buzzer 原版 once 自动关闭失败，独立
trace 抓到 callback 参数 TypeError 与线程退出；显式 custom wrapper 六阶段
通过，原版负控在新自然归零断言下仍失败。guest PWM getter 与 QOM 不一致
另列；新增 `0037` 只修复稳定 set+update 的 S3 寄存器读回，不能掩盖
固件 callback 问题，完整周期/fade 语义继续开放。跨主机剩余 Unit、其他 HUB 布局
与未确认的视觉绑定仍待收敛，不因已通过的子批次而关闭本任务。

CoreS3 单层 HUB 紧凑场景的全尺寸展开、实际端口线缆与可选失败隔离已实现，
四视口 fixture 和合入后的五项浏览器回归通过。手机总览按钮舒适度、其他排列/
主机/深层树与真实 guest 几何联动仍分别保留边界；不从浏览器 fixture 推导新
控制器或物理结果。

跨主机控制类的可复用入口已迁入 `tests/units/prepare_host_controls.py`、
`run_host_control_cases.py` 与 `host_controls_probe/`，不再读取旧 `.work` 候选
manifest。原五个 guest 文件、官方驱动与 CONTROL 断言保留；准备与默认
预检均离线，当前源码/工具链/完整文件树漂移时拒绝。显式执行保留可见会话、
真实 Web、直接 PID、停止前 ZIP 和停止后原始历史响应。此工具交付不变更
runtime 状态或其它主机/Unit 的验证范围；命令与依赖见 `tests/units/README.md`。

实时读数验收覆盖现有十二款标量 rail，原驱动与显式 custom Buzzer 分开。
沿用 service/sensor/io guest，逐阶段核对新鲜串口、控制器、真实 GET 原文和 DOM。
Thermal 只验控制寄存器/fixture 就绪状态，Heart 只验原始样本；Buzzer 的短
输出阶段使用无截图的实时状态观测，最后稳态仍验文字手势与截图。阶段前的
旧 GET 不能授权新阶段，也不从独立串口/页面观测推导原子快照。

三主机六类 sensor 的正式准备/执行入口已迁入 `tests/units/`，18 镜像与
候选逐字节相同，源/工具链/配置与完整 VFS 绑定。原 sensor 初始化、负控、
采样和运行断言保留，使用私有 module 适配准备边界。初始未准入记录保留；
官方 pins 与固定 QEMU 通用路由支持显式开发准入，离线包不授予 PASS。之后的
完整 18 组合已独立执行并通过同 guest 原驱动、真实 Web、内部 BMI、直接 PID、
停止前 ZIP 和实际历史验证；精确元数据与[归档](../evidence/2026-10-26-unit-host-sensors-gen9-a8fe/README.md)
单独登记。原准备包的 NOT RUN 字段保留，不回写成已执行。

原生可读性只覆盖人工看过的实际捕获帧。Heart 的零值暂态单列；controller、
evidence 和 stopped history 分别取图，不要求或声称原子同帧。新 SENSOR 契约
独立核对原负控、逐字段 POST、新鲜串口、完整 VFS/adapter、Git 基线来源重建与
三路 PNG；原 CONTROL 和双观察者契约保持独立。默认及被拒绝的 execute 均零
API；元数据更新后的源码已变化，再次执行需重新准备，不复用过期 freeze。

本轮七层冷构建、同 SHA getter/MMIO A/B 和独立自定义固件的实际浏览器试听
已取证；原失败尝试保留。共享控制器完整轮出现 Core2 IMU 帧标记缺失，单例
复测通过，完整门禁仍开放。证据见[读回与试听归档](../evidence/2026-10-26-unit-ledc-audio-29d8/README.md)。
三主机 IO 的默认准备/执行入口已完成，ADC 在执行前阻塞，原 IR/Buzzer 风险
没有从 CoreS3 继承成新主机 FAIL；离线准备也不授予 PASS。合并主线导致来源
变化时重新准备，后续接口源码打包沿用真实 Flash/VFS 与可见 Device Service。


2026-10-26 已先 checkpoint `ca8245e`，再合入 `origin/main@f206175` 的
21 个提交，merge 为 `c53950a`；只在隔离 worktree 继续开发。源码 API
`/firmware/uiflow` 与强制 source pin 已接入真实 Flash/VFS 和 session
provenance。gen11/29d8 下五例 Button/Relay/ENV III/RGB/Encoder，以及
指南逐字 Button 和 HUB+ENV III+NCIR 两例全部实际通过；另一次独立 Button
预检也通过。该批限 CoreS3，不能继承为其它三主机的源码执行或全部 Unit
完成；具体固件、输入、源码与证据见
[源码 API 归档](../evidence/2026-10-26-unit-source-api-29d8/README.md)。

同一 gen11/29d8 后续新增 25 个可见源码会话：sensor 七例、IO 九例、
controls 四例及显式 custom IR/Buzzer 两例功能通过；独立 Thermal 缺 fixture
负控通过。原版 IR 本次协议通过但仍为 `REVIEW_REQUIRED`，不关闭历史 GC
引用风险；原版 Buzzer 自然 timer zero 未通过，输出型用例被旧浏览器检查误
分类另作 harness 限定，不写成产品故障。原批与本批选定场景合计覆盖 27 种
Unit，其中 25 种原 driver、两种 custom；只限 CoreS3 的源码运行，不从旧
镜像路径继承其它主机的源码 PASS。controls 为保留原驱动与断言的 CoreS3
display-only 适配；Fan 图形活动只覆盖实际观测段。
原始 HTTP、源码请求、分段串口、QOM、原生帧、浏览器、停止前 ZIP、历史及
独立审查保存在[扩展源码归档](../evidence/2026-10-26-unit-source-api-expanded-29d8/README.md)。
本批未改共享 runtime，不补全旧完整矩阵；跨主机、原驱动缺口和视觉/物理
映射继续在权威 Backlog 中推进。完成该检查点并提交后，再拉取最新主线、
审查合并影响并继续 Unit；不覆盖其它会话的工作目录。

扩展源码块已提交为 `0fe6a01`，之后正式 fetch 并合并检查 `origin/main`
仍为 `f206175`，已包含最新远端。全新准备的 AtomS3R/StickS3/StopWatch ×
Button/Relay/ENV III 九个源码 API 会话全部通过，原 host probe、板载 BMI270
总线隔离、显示与原断言保留。该结果只授予这九个新固件/场景，不继承其它
二十四种 Unit；精确 source pin、同 guest/Web/QOM、ZIP、直接 PID 及清理见
[三主机源码归档](../evidence/2026-10-26-unit-source-hosts-29d8/README.md)。

后续 `UNIT-HOST-20` 采用独立候选源码/冷构建处理 GPIO matrix 路由建立后的
PWM 观察器刷新。通知只重算现有 LEDC 寄存器，不重放寄存器写入或强设 Unit
值，保留 `0037` 的读回及 immediate-duty/fade 边界。验收使用同一 caller CAS
与固件 SHA：首次 PWM 初始化后只读取 getter/heartbeat，在固定旧运行时与
候选运行时分别经可见 Device Service 取新串口→QOM→新串口、实际 DOM 和
停止前 ZIP，不加入补偿 zero setter，不混入原 Buzzer SoftTimer 故障。
路由建立、移走、换 channel、零 duty、输出屏蔽及布局隔离另有实际 C 合同；
共享控制器候选还须冷构建和完整矩阵门禁。未取得这些证据前，本条保持 OPEN，
旧完整轮与旧初始化失败记录均保留。

`0038` 的同固件可见 A/B 已完成：旧29d8为 `FAIL_REPRODUCED`，新d1ba八窗
2000Hz/0%通过，无后续setter。冷构建、18组实际C片段、两轮独审及新独立完整
矩阵67/67、274/274通过，平台652项零跳过通过；`UNIT-HOST-20` 只关闭初始化
路由观察，原Buzzer与完整PWM周期仍开放。旧66/67保留，新Core2绿帧不关闭偶发
根因。完整ROM/C6无全轮起始freeze、PaperColor RGB命令摘要覆盖以及六个IR例
mutable Flash hash变化均如实保留，最终Python源码与输入冻结一致。
详见[本块证据](../evidence/2026-10-26-unit-pwm-route-d1ba/README.md)。外部
agent-work-logs继续 `SKIPPED_BY_USER`。本块提交后再次fetch/merge，再按新HEAD
准备三主机其余IO源码会话；此前Fan3证据与后续21例分批记录。

PWM块 `0a6a9a2` 后已正式fetch/merge最新origin/main@f206175，结果Already up
to date、工作树干净。随后全新准备rest21，与Fan3组成24源码IO会话，八种×三
主机全部PASS；两个准确HEAD和相同481依赖字节分别保留，不假称同HEAD。
19caller/原驱动/host与IO断言、fresh UART/实际Web/controller/source-pin/PID、
ZIP-before-stop/history/Flash/idle通过；具体可读性与两间接依赖精确omission见
[本批证据](../evidence/2026-10-26-unit-source-host-io-d1ba/README.md)。外部日志仍SKIPPED_BY_USER。下一步
继续剩余传感器/控制器源码场景、ADC/Thermal门禁、原IR/Buzzer与视觉固定版本
导入；不关闭整个UNIT-01或推及真机。

按最新用户的AIFlow实时编程/预览场景，后续优先级已转入API执行闭环，详见
[API评估计划](2026-10-26-aiflow-live-preview-api.md)。当前仅评估与host取消竞态
复现完成，新Preview/Revision/Run/stream与同guest部署尚未实现；实际队列仍以
Backlog为准。三HUB数字token拆行另记UNIT-HOST-23，取消竞态记UNIT-HOST-24。
