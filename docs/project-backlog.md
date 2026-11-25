# 项目 Backlog

日期：`2026-11-25`

本文是未完成工作、依赖和验收条件的唯一队列。当前能力见
[项目当前状态](project-status.md)，运行历史和精确身份见
[验证证据台账](validation-ledger.md)，入口见[代码地图](code-map.md)。

## 使用规则

- 已完成的子路径只保留必要前置，轮次、SHA、PASS 数量和失败 control 链接台账，不在本页重复。
- 每项验收绑定同一设备、固件、runtime/profile、实际输入、输出、归档和清理；同版本换字节须重验。
- virtual-device validation 与 hardware validation 分开；RF、功耗、声学、光学、机械和电气属性按需实测。
- 模型缺口、fixture 缺口、基础设施失败和固件 FAIL 分开；未知安全状态保持 `unknown`/`REVIEW`。
- 不以关闭 watchdog、延时规避、改原 BIN、放宽门槛或单次未复现替代原失败路径的修复验收。

## 优先级总览

| 优先级 | 工作流 | 未完成范围 | 主要风险 |
| --- | --- | --- | --- |
| P0 | 原版固件审查数据面 | 语义输入、存储、同 guest 网络、Tab5、崩溃与任务观测 | 受理、局部协议和取帧不等于整应用就绪 |
| P0 | 网络产品化 | 物理跨主机、复制/对象存储、NAT 与外部 side-effect fence | 同机 namespace/container 不替代物理多机 |
| P0 | Core2 功能容量 | 更大规模冷启、ACK 竞态、持续吞吐和复杂 teardown | 虚拟容量不外推物理 controller 或 PSRAM/cache |
| P0 | 通用固件安全与运行时 | guest ACL、许可/安全配置、固件覆盖和开放模型缺口 | 只在明确声称物理属性时另验；unknown 不升 PASS |
| P1 | 服务、外设与视觉 | 接管/服务池/编排、未验外设、浏览器与正式托管门禁 | 不从已验组合或原生路径继承 |
| P2 | CardputerZero 与准入归因 | 独立 Linux 后端、更多能力/布局/故障场景 | 不混淆不支持、未建模、环境与应用失败 |

## 当前执行顺序

恢复执行后先按下列 P0 的最小交付推进，再处理 P1、P2；依赖未满足时保持阻塞，不宣称已开始。
`NET-04`、`SVC-01/02` 的跨主机验收需要可独立失联和 drain 的节点；
`RUNTIME-02`、`TAB5-01` 需要相应后端或权威固件资料；`FW-02` 的 live eFuse/生产 key 需要明确授权。
浏览器继续采用定制 C/QEMU 单一架构，Rust 演示与独立 JIT 仅研究；Pages 不自动跟随 main。

PaperDIY 的原版 CrossPoint 仍需按原 BIN、实际配置输入和同会话应用输出验证网络。
已具备的原生 STA 板级准入仅关闭关联/DHCP 资格前置，不能替代其 TCP/UDP、
HTTP 或其它应用语义；[精确前置证据](evidence/2026-11-23-paperdiy-native-sta/summary.json)保留范围。
StopWatch Demo Plus 原始空 NVS 的固定开放实验网络已完成 AP 门户提交、退出、
STA DHCP 与保存重启回连；[冷启动证据](evidence/2026-11-23-stopwatch-factory-provisioning/summary.json)
只关闭这条精确原版/板型/原生路径。WPA2、浏览器及外网语义需独立验收；先前
已配网前置、ROI 漂移和空 NVS AP 观察仍保留在[原版对照](evidence/2026-11-23-stopwatch-native-sta/summary.json)。

S3-watch 0.1 (worked) 原版在 native macOS arm64 已完成成熟初态→B 关闭→B
重开的同来宾 WPA2、DHCP/ARP 与只读 HTTP，错误口令被实际 guest 握手拒绝；
[精确正负控](evidence/2026-11-23-s3-watch-native-wpa2/summary.json)只关闭这份原版的
固定原生路径。初始不同 SSID/open 广播的具体启动分支、Reviewer 自动编排、
Linux/浏览器及其它安全模式仍需各自证据，不能从 HTTP PASS 外推。
组合 runtime `67e78237…` 的 StopWatch 旧模式对照出现两次 PARTIAL，
而 `5b8b3f24…` 同配置 PASS；必须定位并修复后才可提升共享运行时。

## 可执行任务板

为保持索引兼容，保留已完成编号及原状态；已完成行不是活动队列。详细开放项和验收在下文。

| ID | 状态 | 下一项最小交付 | 验收 |
| --- | --- | --- | --- |
| `API-01` | 进行中 | 补 stock SDK/绑定、WDT warm reboot、native build feature、未实现控制器和未选外设；扩展 ADV Unit 与 legacy Core2 setup/REPL、完整 factory application | stock/matching/candidate 分 lane；同固件的行为、控制器、串口、帧、ZIP 和清理可复核，局部通过不关闭完整 API |
| `RUNTIME-03` | 已完成（virtual-device stock startup） | stock startup 已完成；setup/REPL 与任意 legacy application 由 `API-01` 跟踪 | 保持 normal-WDT startup 与 shared bus 回归，不重开已关闭的 TG0 stage-1 子问题 |
| `RUNTIME-06` | 已完成（virtual-device） | virtual-device ESP-NOW 已完成；物理 controller/RF 边界不继承 | 原生及 wrapper 的 key、peer、replay、路由与生命周期证据保留在台账 |
| `NET-04` | 进行中 | 物理跨主机 executor/reattach、queue/session/evidence 复制、任意 NAT 和外部 side-effect fence | 失联、迁移、drain 与重试有确定终态；异请求、旧 lease 和错误 evidence binding fail closed |
| `CORE2-02` | 进行中 | 重绑无宿主过载的八实例 cold-start，定位九实例 ACK 竞态，再补持续吞吐与复杂 teardown；PSRAM/cache timing 只在明确声称物理属性时另验 | 绑定固件/ELF/QEMU/工具；不得放宽 timeout/floor 或忽略 panic 准入，虚拟容量不外推物理等价 |
| `FW-01` | 进行中 | guest filesystem 运行态 ACL、完整源码/依赖许可和法律审批 | 镜像属性、service ACL、guest 强制执行分开；不支持配置 INVALID，unknown 不升 PASS |
| `FW-02` | 进行中 | 公钥权威性、live eFuse、bootloader anti-rollback、真机加密与生产 key 流程 | 镜像、运行态和硬件分层；生产敏感值不入库，缺权威输入保持 unknown |
| `FW-03` | 进行中 | 原始私有 Core2 业务复跑、真实 key/云端/音频与更多 firmware family、SD/NVS/网络 fixture | 按实际 BIN 与 fixture 绑定；模型缺口、fixture 缺口、环境故障与固件 FAIL 分开 |
| `RUNTIME-02` | 进行中（backend blocked） | C6 802.15.4 MAC ACK、commissioning、join/收发/离网生命周期 | 真实 guest 驱动完成生命周期；否则保持 runtime_model_gap，不承诺所有 C6 固件兼容 |
| `RUNTIME-07` | 进行中 | 定位 StamPLC 原多指令 TB 策略硬复位后 SYSTIMER PIF | 同固件采集 MMIO/region/TLB/TB 与 CPU1 reset/IRQ；修复原路径并回归，oneInsn 规避不关闭缺口 |
| `RUNTIME-08` | 进行中 | 捕获 Cardputer-ADV 原工作台复位后的 WASM OOB trap 与恢复状态 | 同二进制符号、复位/负载对照及同异常路径修复；保留首次失败和 fallback 清理 |
| `RUNTIME-09` | 进行中 | 定位 AtomS3 Lite 工作台首次启动及 oneInsn 硬 reset PIF | 取得 MMIO/region/TLB/TB/IRQ 证据；修复后通过启动、代码、reset、输入和清场 |
| `RUNTIME-10` | 进行中 | StickS3 其它内置 BLE 构建、IMU 报告、受保护 802.11 RX 与高吞吐捕获 | 按缺口登记逐路径验收，不从已验证 PM1/USB CDC/AirMouse/Evil Probe 子路径继承 |
| `SVC-01` | 进行中 | namespace-managed/Tab5/cross-host companion 与跨主机 session/evidence 连续性 | ownership 完全匹配才 adopt；重启后接管或明确失败，不产生假 running |
| `SVC-02` | 待做 | warm pool、队列/配额、对象存储、审计、多租户隔离和容量指标 | 资源及 GC 可观测；不可信固件使用 disposable VM/copy-on-write，namespace 不是恶意代码沙箱 |
| `SVC-03` | 进行中 | 继续提取请求解析/运行参数，再拆 store、runtime adapter、evidence collector 与生命周期/HTTP 编排 | 每步只移动一个可回滚边界，保持 API、错误码、参数、历史恢复和 evidence 契约 |
| `TAB5-01` | 阻塞 | 等待上游 P4 兼容与控制器支持 | 同原版越过 CSR/DSI 阻断后，以公开接口验证板级器件和数据面 |
| `UI-01` | 待做 | 逐设备结构、材质、hitbox 和截图阈值；host 接入战役不重开 | 逐设备视觉回归；仅视觉/组合件不继承独立 host 或硬件结果 |
| `UI-02` | 进行中 | 更多固定固件、浏览器性能/长期稳定性及逐固件 CPU、输入、存储与复位缺口 | 同 Flash/runtime/profile/input/frame 绑定；native 或 compiled_profiles 不授浏览器 PASS |
| `UI-03` | 进行中 | 正式托管同版本完整串行门禁、独立 HTTPS 编辑器/输入与偶发启动/复位故障 | 保留真实输入、输出、清场和历次失败；局部 HTTPS 例不覆盖全设备 |
| `UNIT-01` | 已完成（virtual-device） | 接入战役已完成；仅保留 `UNIT-DEFER-01` 和下文预览/原驱动覆盖的独立余量 | 不把视觉模型、主机通过或已选组合结果转授未验 Unit/主机 |
| `CZ-01` | 待做 | CardputerZero 系统、驱动、USB/网络竞态及摄像头/音频/电源/键盘长期回归 | 独立 Linux 后端的功能与长期边界明确，不继承 ESP32 结果 |

## P0：固件审查数据面

### 语义输入与应用断言

- **Dial**：保留普通 35 ms 与显式高速输入；继续定位原版 5/8 ms 轮询空档、UIFlow2 RotaryIRQ 和 Arduino 快速整周计数，并对照同一 BIN 的实体旋钮。控制器完整相位不能代替应用计数。[原版漏选与交付](validation-ledger.md#2026-11-19-dial-原版-8-ms-漏选)
- **AtomS3 Spirit Level**：保留原版去抖后计时及最后按住采样语义，验证临界时长和标准审核的应用状态断言，不将一次临界输入推广为稳定阈值。[原版按键与时长](validation-ledger.md#2026-11-19-atoms3-原版实体键与时长)
- **Core2 2048 与通用输入**：扩展按板型的键盘、组合键、触摸和编码器断言；已有四向与底色识别通过不替代同 BIN 的实体触摸对照。取得可用 Core2/触摸条件后再验。[四向与原帧证据](validation-ledger.md#2026-11-19-core2-2048-棋盘底色识别)
- 验收以控制器/guest 驱动读回和实际应用状态为准，接受回执或输入请求成功不能单独关闭语义输入。

### 存储、显示与原版复用

- 扩展 LittleFS 的 SDK/设备、更多原版应用的实际文件读写与断言；内部分区、服务重启、停机导出和新会话复用按原身份保留。[跨芯片与文件断言](../tests/firmware/littlefs_partition/cross-chip-persistence-summary.json)
- 扩展 CardputerDict 版本/设备、原版 SD 读动作与其他板型；StickS3/Dial 外接 SD 需独立接线模型。原生完整 modeled response 不等于固件消费。[SD 读取契约](../tests/firmware/spi_sd_media/read-stats-summary.json)
- **NC1020**：继续定位原版停刷时空完成队列的发生过程，对照真机并验收发布者更新后的固件；保存/G0、冷导入与跨服务恢复通过不关闭完整出帧。保留同原版两种停刷终态及上游 SPI 锁修订重建对照。[当前原版与重建对照](validation-ledger.md#当前运行时的原版停刷与重建对照)
- 验收必须将源介质、动作、指定文件/缺失文件、保留产物和恢复后的应用行为关联到同一次运行。

### 同 guest 网络与常驻 worker

- **#238 review-sta**：便携 profile 与 8 款板卡控制固件已有 virtual-device 结果。审查服务已改用 `review-sta`，当前网络任务不再因命名空间或目录未公布转人工。剩余：这些原版应用需在界面中配置 Wi-Fi，按应用补保存快照的配网输入（键盘/按键序列）后才能得到 PASS/FAIL；Core2 触摸条 B 的 setup 对照；Cardputer 键盘与 PaperS3 触摸的 setup 输入对照；更多原版应用的事件断言。[控制固件证据](evidence/2026-11-24-review-sta-portable/README.md)；2026-11-25 增加驱动初始化判定与 `until=joined`，Monster 3.0.2 在收到 OFFER 后不发 DHCPREQUEST 待查 [证据](evidence/2026-11-25-review-sta-activity/README.md)
- 扩展更多原版的常驻准入/拒绝、HTTPS/云端协议、SoftAP 门户与应用断言；按板型补 Wi-Fi 事件。保持既有网络授权及隔离约束，固定夹具不转授任意外网能力。[既有保存快照数据面](../tests/network/native_sta_peers/local-streams-saved-review-summary.json)
- 继续验证切换 Worker 时的待恢复绑定、可信冷恢复、持久卷独占及宿主资源回收，以及宿主断电/系统重启；正常同卷重启、运行器退出隔离和单机 VZ 不替代这些范围。[安装与生命周期](macos-linux-review-worker.md) · [既有常驻与隔离证据](validation-ledger.md#2026-11-19-常驻-linux-的-cardputerdict-adv-独立复审)
- 验收关联同 guest 的 DNS/HTTP/TCP/UDP 或 TLS、缓存/介质与 PCM；错误回复、策略拒绝、前置动作不足和环境不能准入分别出结论。更多原版应用仍开放。

### Tab5 启动、输入与控制器

- **98TAB5**：修复原版正常冷启动的有盘/无盘画面，再验证 PC-98 启动和多应用 OTA。单 OTA0 身份、合成 IDE/FAT16 识别及无调试批量对照不等于画面恢复；继续关联 CPU0 缓存维护与 CPU1 启动读交叠。[原版对照](evidence/2026-11-18-tab5-stock-frame-comparison/README.md)
- **ST7123/GT911 与 M5TabOS**：补原版拖动语义、多点、其他板型电源路径；继续更短输入间隔、联网设置、其他板型和非正常关机恢复。欢迎页/时区/离线向导与正常保存通过不关闭这些范围。[既有连续触摸](validation-ledger.md#2026-11-19-tab5-m5tabos-原版连续触摸复验)
- **显示链路**：验收高压下连接保持时的静默丢帧与稀疏差分；断线重连通过不替代长期稳定性。[既有 DSI 重连](validation-ledger.md#2026-11-19-tab5-原版-dsi-重连)
- **音频与启动盘**：补其他固件、格式和多动作审核，以及原版启动盘、C6/SDIO、USB Host、CSI 和其它控制器数据面。UserDemo 专用 Part 的音乐、双麦及回放不转授全部 P4 应用。
- **#227 历史边界**：CarPlay 原版普通启动、匹配板型取帧和实际触摸已有证据；USB/iPhone 数据面仍须独立验收，不回退为未验证 UI，也不扩大为完整 CarPlay。[原版板型与触摸](validation-ledger.md#2026-11-19-tab5-原版-carplay-板型探测复验)
- 取帧未就绪、后端需匹配 ELF、固件 watchdog/reset 和静态受理分别归因，保留 #188、#226 的独立关闭条件。

### 崩溃、任务与睡眠观测

- 扩展其它运行时的任务详情、Flash 转储、保存栈展开及其它 RISC-V 实时 PC；无/错 ELF 不得假展开，实时 PC 不代替保存上下文或应用就绪。[既有诊断身份](../tests/firmware/crash_diagnostics/s3-flash-task-summary.json)
- 在具备显式外部输入的 ESP32-S3 夹具验证 32.768 kHz 慢钟、其他深睡唤醒源与 RTC 保留模式；原版 Watch 菜单、GPIO/定时唤醒与内部慢钟结果只作前置。[睡眠与唤醒台账](validation-ledger.md#2026-11-19-sticks3-原版手表唤醒后操作)
- 验证异常转储写失败时的收据一致性；保留 98TAB5 失败与“已保存”报告冲突，不把串口报告当物理 Flash 成功。[既有写入分类](../tests/firmware/crash_diagnostics/stock-write-report-summary.json)

## P0：社区固件与兼容缺口

| 对象 | 剩余最小交付与关闭条件 | 证据入口 |
| --- | --- | --- |
| UIFlow2 WebREPL | 修复云端未回复标准 WebSocket control Ping/Pong；用原 BIN 跨多个超时周期复验。身份、配对码或文本心跳通过不关闭 | [断开方向回放](validation-ledger.md#2026-11-19-uiflow2-webrepl-断开方向回放) |
| [#216](https://github.com/m5agent/m5stack-esp-emulator/issues/216) Nesso/Launcher/RFID | 原 BIN 不继承 Launcher 重建触摸修复。定位原版 TWDT/IDLE 未喂狗与载荷长度处理，验证真实 PN532Killer 应答、标签读取及独立 Zigbee 数据面；保留有效/错校验 UART1 对照 | [当前原版](../tests/firmware/esp32c6_mwdt_clock/current-main-rfid-summary.json) · [M5GFX #416](https://github.com/m5stack/M5GFX/pull/416) |
| [#223](https://github.com/m5agent/m5stack-esp-emulator/issues/223) StackChan UserDemo/GPT | 当前公开包仍是已失败原 BIN；发布含官方 ESP-IDF I2C 修复的新包并按新身份验收动画、触摸和 UART 舵机。重建正控不关闭原包 FAIL，不用模拟器延时或改原 BIN 隐藏 SDK 竞态 | [问题与原版证据](validation-ledger.md) |
| [#188](https://github.com/m5agent/m5stack-esp-emulator/issues/188) Tab5 UIFlow2 v2.5.4 | 让板型专用 DSI 读响应经 ESP32-P4 DSI RX FIFO 返回；同原版 GT911/ILI9881C 普通冷启动出帧并实测触摸。ST7123 离线通过不转授该板型，联网/配对另验 | [同原版板型对照](https://github.com/m5agent/agent-work-logs/blob/6a4fd8c724d6f9b215e900e21fd9787aeaf15900/records/esp-emulator/2026-11-14-p4-v1-originals/followups/2026-11-18-tab5-uiflow254-196-board-compare/README.md) |
| [#226](https://github.com/m5agent/m5stack-esp-emulator/issues/226) Maker Fighter USB Host | 原版虽已初始化 DWC、注册客户端及根端口供电，仍须实际外设连接、HID/MSC 枚举、数据传输和应用画面 | [已有能力接口对照](https://github.com/m5agent/agent-work-logs/blob/cb240b4d96bfa470ff7aa19926c8c9f74931a418/records/esp-emulator/2026-11-14-p4-v1-originals/followups/2026-11-18-maker-fighter-dwc-self-check/followups/2026-11-18-maker-fighter-host-setup/followups/2026-11-18-tab5-226-usb-host-capability/README.md) |
| PaperColor | 定位原版 xTaskPriorityDisinherit 的完整锁操作与共享外设事务；#217 宿主竞争、#220 USB 子路径修复均不关闭 guest 断言 | [无 USB 原版对照](validation-ledger.md#2026-11-19-papercolor-原版启动互斥锁断言) |
| C6/NanoC6 身份 | 实现 802.15.4 extended-address 寄存器数据面，再验收 Zigbee 身份和协议；不能用报告字段伪造，NanoC6 子路径不转授其它板型 | [身份分层](evidence/2026-11-14-native-identity-delivery/README.md) |
| Nesso N1 中断 | BMI270 数据/运动事件与 IRQ 使能，FT6336 模式/脉冲/扫描时序，NMI/source 31、睡眠唤醒/滤波须各经原驱动、真实控制器输入和复位对照；普通 GPIO source 30 不关闭 | [已有 GPIO 路径](evidence/2026-11-14-c6-gpio-irq/README.md) |
| StickC Plus2 / Honeypot | 分别验收 BLE HID 数据面，以及 AP 关联/HTTP 数据面；JIGGLER 看门狗或配置控制台通过不转授这些功能 | [原版边界](evidence/2026-11-14-native-identity-delivery/README.md) |
| [#178](https://github.com/m5agent/m5stack-esp-emulator/issues/178) classic 上传 | 全 classic 多轮高负载冷烧录稳定性；保留 ROM stub 一次有界低速重试及 Atom Lite 已验证的恢复路径 | [历史台账](validation-ledger.md) |

**#234 历史边界**：Cardputer ADV 原版 16 MiB 超容量受理拒绝与官方 8 MiB 正对照已验证。
此结果不判定原固件内容有缺陷，也不授予不兼容布局运行；新布局、板型和后端仍按下方准入归因验收。
见[结构化 Flash 容量归因](validation-ledger.md#2026-11-19-cardputer-adv-flash-容量结构化归因)。

## P0：Core2 legacy UIFlow 运行时

### RUNTIME-03：已完成（virtual-device stock startup）

stock startup 已关闭；其 WDT/shared bus、stateful SSI、dual-SPI、DPORT、RMT 前置见[台账](validation-ledger.md)。
`API-01` 仍需：

- 取得公开 UIFlow_Core2 v1.15.4 的 matching ELF/MAP；旧 UIFlow2 ELF 不可冒作匹配符号。
- 在 matching LittleFS2、qemu-wifi 和正常 WDT 下进入 setup/REPL、完整 factory application；旧 BIN-bound 0x40100049 等待未在后续检查点复现，不继承为当前第一失败点。
- 解释 display flush callback、SPI completion、lv_disp_flush_ready、tick/IRQ 与应用生命周期；保留 pending SPI remap、TRANS_DONE/TRANS_INTEN、guest callback 和真实 SSI 数据面，不走 bulk-read bypass。
- 同 public SHA 的 AXP2101/AXP192 对照及 Core2FactoryTest、UIFlow2 设备组复验。保持正常 WDT 和 TIMG 中断回归，保留 TG0 stage-1 reset 的已验证边界。
- 继续 stock SDK/绑定和 native build feature、WDT warm reboot、未实现控制器/未选外设；保留 stock HTTP/requests2、Modbus transform/async、TLS epoch、BLE UUID32/get_client 及 Canvas triangle/Image float scale/integer Spinbox step 的原始失败与候选修复边界。
- StopWatch/StickS3 的 stock internal-controller BLE 仍开放；Core2 native-HCI 或 matching/candidate 通过不转授这些路径。

## P0：网络与 worker

### NET-04

剩余：物理跨主机 QEMU executor/迁移/reattach 与持续 evidence 流，queue/session/evidence
复制或对象存储（无共享文件系统），无 discovery seed 的任意 NAT，以及 QEMU 内 guest/device-controller
状态和 worker 未拥有的外部 side effect。namespace-managed/Tab5/cross-host companion 与容量服务化按 `SVC-01/02` 共同验收。

验收：强杀、重启、失联、迁移、drain 均有确定终态；generation、进程身份、lease、任务和证据可关联；
ownership 不明时停止可达 runtime 并拒绝 stale result。claim response 丢失与 evidence 上传 response 丢失的
同键/同 bytes 重试保持原 job/lease/evidence 绑定，不重复领取第二个任务；异请求、异 bytes、过期 lease 或错误 result binding fail closed。
物理多机与同机 namespace/container/VZ 结果分层，既有前置见[网络与 worker 台账](validation-ledger.md)。

## P0：Core2 controller 与物理边界

### CORE2-02

当前容量前置见[工具 hash 重绑](evidence/2026-10-30-core2-toolhash-rebind/README.md)。开放项：
无宿主过载的八实例冷启重绑、九实例 ble_hs_hci_process_ack 竞态修复后再准入、更大规模、持续吞吐及复杂 teardown。
每个新固件重新校验符号/hook，结果绑定固件/ELF/QEMU/工具及参数；不得放宽 timeout/floor 或忽略 panic。

bit-exact Espressif controller/baseband、物理板载 8 MiB PSRAM/cache timing 与同固件真机边界
只在明确声称物理属性时另验；虚拟并发或 QOM PSRAM 不外推物理等价。

## P0：通用固件审查

### FW-01 文件系统、权限与许可

- 补 guest filesystem 运行态 ACL、权限/不可变策略；operator-owned service ACL 不是任意 native firmware 沙箱。
- 补生成代码、包外 vendor 依赖和完整源码/依赖许可，以及法律审批。
- 验收镜像属性与运行态强制执行分层，资源、来源、哈希、声明及结论可审计；不支持配置返回 INVALID，unknown 不升 PASS。

### FW-02 真机安全配置

- 补包内 summary 的权威来源、公钥 authenticity、live eFuse trust root 和 bootloader anti-rollback。
- 按授权验证真机 Secure Boot、Flash Encryption、生产 key 流程与测试/生产 key 隔离审计。
- 镜像数学验证不替代运行态或物理 trust；生产敏感值不入库/日志，缺权威输入保持 unknown。

### FW-03 跨厂商回归

- 重跑 issues #2/#3 原始私有完整 Core2 应用归档；公开最小启动或 UIFlow2 字形修复不替代私有业务。
- 扩展真实 key、Realtime/音频/云端业务、设备及 ESP32 LX6/P4/vendor/MicroPython family，以及 SD/NVS、输入/网络 fixture。
- 补失败根因闭环与 capability/security evidence 冲突处置；同 ID/version 字节变化重验，模型/fixture/环境/固件失败分层。

## P0：运行时模型缺口

### RUNTIME-02 C6 Zigbee/802.15.4

补可重建的 MAC ACK/commissioning，或取得公开固件 matching ELF，以真实 guest 驱动验证 join、收发和离网；
另一个后端仅双向帧不算完整生命周期。否则保持 runtime_model_gap，不承诺所有 C6 固件兼容。

### RUNTIME-09 AtomS3 Lite 工作台首次启动及硬复位 PIF

同精确固件的原多指令和 oneInsn 策略采集 MMIO、MemTxResult、region/TLB、TB 恢复及双核 IRQ/reset 顺序，
定位已映射寄存器读 PIF。修复必须命中原失败路径，再验首次启动、代码、硬 reset、输入及清场；诊断、其它环境或策略通过不关闭。

### RUNTIME-08 Cardputer 浏览器复位后 WASM OOB

核验各 Worker 的 Runtime/Debugger ACK，取得原 trap function/offset、同二进制符号与 CPU/TB/MMU/协程栈恢复状态，
分开独占/多 guest 负载。保留首次失败与 fallback，修复后重验代码、硬 reset、输入输出和 QMP/Worker 清场。

### RUNTIME-07 StamPLC 浏览器硬件复位后 PIF

原多指令 TB、同固件/runtime 下分开首次启动、程序前后和硬 reset，采集实际 MMIO/MemTxResult、region/TLB、
指令恢复与 CPU1 reset/IRQ；不预设控制器缺失或固件根因。修复同异常路径后验 reset、旧程序取消、新代码、输入输出和清场，
并补受影响板型。oneInsn 规避及未知 Flash 不关闭缺口。[缺口登记](runtime-model-gap-register.md#runtime-07stamplc-浏览器多指令-tb-下硬件复位后-pif-异常)

### RUNTIME-10 StickS3 剩余路径

其它内置 BLE 构建/IMU 报告、受保护 802.11 RX 和高吞吐捕获分别验收，不由已验 PM1、USB CDC、AirMouseS3 BtnA 或 Evil Probe Sniffing 关闭。
详见[运行时缺口](runtime-model-gap-register.md#runtime-10sticks3-固件审查中的-pm1usbble-hid-与-wi-fi-monitor)。

### RUNTIME-06 ESP-NOW 加密与 peer 生命周期

virtual-device 范围已完成，不重开；fixture/guest-key、shared-LMK/per-peer-key、replay、cross-wire、PN exhaustion、
loss/channel/rate 与 peer 生命周期的历史结果见[台账](validation-ledger.md)。物理 RF/controller/电气等价仍独立。

## P1：服务化与代码整理

### SVC-01 活动实例接管

补 namespace-managed/Tab5/cross-host companion、跨主机接管和连续 external evidence 流。
ownership 全匹配才 adopt，服务重启后接管或明确失败，不产生假 running。

### SVC-02 服务池

补 warm pool、队列/配额、对象存储、审计、多租户与容量指标，资源和 GC 可观测。
不可信固件需 disposable VM/copy-on-write，现有 namespace 不当作恶意代码沙箱。

### SVC-03 编排拆分

按无语义变动顺序继续请求解析/运行参数 → content-addressed store → QEMU/Tab5/network adapters →
evidence collector、lifecycle/history → HTTP/orchestration。保持原模块 re-export；每步独立可回滚，
API、错误码、运行参数、历史和 evidence 不回归，按受影响工具身份重绑已有容量/lease 证据。

## P1：专项

### TAB5-01

等待兼容旧 P4 CSR/DSI 且公开相应控制器扩展的上游后端；同原版先验启动，再逐项验动态 I2C/RTC/IMU/
INA226/PI4IOE/IP2326、I2S/PCM、CSI、USB Host、SDIO、controller-level touch 及 P4↔C6 ESP-Hosted 端到端网络。
已验证的板型/专用 Part 不转授其它配置；不支持时保留静态/串口证据，画面和数据面按实际标注。

### 音频与其它外设

- 优先审核侧 Unit 挂载；补 Dial AudioPlayer 多目录、实体介质和更多格式；更多固件/板型的录音与 PCM，播放通过、错误音断言和取证不足分别验收。
- 补 NFC、其它 Joystick 接线、外接 I2C/SPI 收发控制器、IMU/Camera/IR、ADC/PMIC/RTC。
- 常规 USB 设备模式补 HID 枚举/报告和 MSC 读写；PaperColor 原版 LBA0/LBA1 已读回，仍需固件断言、长期读取和写入。
- PaperS3/PaperDIY EPD、前光及电源/音频/存储，CoreS3 Camera/NFC/音频，Atom IR 与无显示路径分别取证。[外设台账](validation-ledger.md)

### UI-01（已完成收口；5 款仅视觉边界保留）

host 接入战役已收口；任务板 `UI-01` 的未完成范围仅为逐设备结构、材质、hitbox 和视觉阈值。
AtomS3R-Ext、StickV 为 boundary-only；AtomS3R-AI Chatbot、AtomS3R-CAM AI Chatbot、AtomS3R-M12 Volcengine Kit 为 composition-only。仅出现准确该板官方固件/新后端时重开，
不以同 SoC 或组合件冒作独立 host。M5Stick EasyLoader FactoryTest 的 legacy I2C FIFO、MPU/按键/最终 UI 仍 blocked/partial。
[边界决策](plans/2026-11-02-host-boundary-decisions.md) · [历史汇总](evidence/2026-11-03-visual-campaign-summary/README.md)

### UI-02 浏览器范围与 UI-03 正式托管

- **UI-02**：补更多固定固件和长期稳定性，定位 StackChan 原舞蹈固件 Core1 ROM 字面量启动异常与独立触摸，官方 Factory WDT/异常，其它应用 CPU/触摸延迟、stock SDK C Timer coalescing 与 Flash 持久化。
- 分别验 C6 RISC-V、P4 controller 数据面和 Linux ARM64 浏览器执行；保留 PaperMono 逻辑校准、StopWatch 触摸偏差、Cardputer CFG1 时序、Plus2 USB sleep/EXT0/RTC CRC、StackChan 其它固件/运动模式边界。
- **UI-03**：完成正式托管同版本完整串行门禁及独立 HTTPS 编辑器/输入；处理 ADV 原厂键盘释放、初代 Cardputer 冷启 PIF 与其它偶发启动/复位，逐板性能和长期稳定性另验。
- 更多固件、短按负载、未取得的用户镜像与自然 PWR 回收仍独立开放。保留真实输入/输出/清场断言、失败对照和同层 Worker 生命周期；原生、编译板型或局部 HTTPS 例不授全板浏览器结果。[本地与托管边界](evidence/2026-11-14-pages-local-qualification/README.md)

### UI-02/03 文档例程 WASM 试点

- 在文档预览单独验证能开启跨源隔离的托管方式，再接入 CoreS3 和 Cardputer-Adv 的已验例程。验收包括同页运行、首个可操作画面、实际交互输出、跳转或停止后回收及其他文档资源加载。[正式文档嵌入阻塞](https://github.com/m5agent/m5stack-esp-emulator/issues/242)
- 保持原始 Arduino、UIFlow2 和 ESP-IDF 例程的源版本与镜像哈希。Cardputer-Adv 的候选涉及新 WASM 源层，正式托管需回归相同的原显示、键盘和参考镜像。CoreS3 摄像头、Unit 和 Cardputer-Adv LoRa Cap 分别验完整数据路径与界面反馈。[ADV 板型探测](https://github.com/m5agent/m5stack-esp-emulator/issues/245) · [CoreS3 摄像头](https://github.com/m5agent/m5stack-esp-emulator/issues/243) · [CoreS3 Unit](https://github.com/m5agent/m5stack-esp-emulator/issues/246) · [ADV LoRa Cap](https://github.com/m5agent/m5stack-esp-emulator/issues/244)

- 按例程加入可控网络及其他 Unit。固件固定、真实帧、控制器和资源生命周期一起验收。CoreS3 卡载 WAV 可读，播放仍需验证。[例程预置 #255](https://github.com/m5agent/m5stack-esp-emulator/issues/255) · [音频 #248](https://github.com/m5agent/m5stack-esp-emulator/issues/248)

### UNIT-DEFER-01：Unit 剩余 planned/DEFER（收口后仅 2 项）

- `mini-bps-v11`（U090-B）：QMP6988 页面/I2C 索引 0x56 与冻结驱动 0x70 冲突；取得确证地址的官方 datasheet/驱动或产品实测前不猜地址、不建模型。
- `mini-pdm`（U089）：缺公开 Unit PDM 驱动；板级 SPM1423 PDM RX 不等于 Unit attachment，取得官方协议/驱动及可复现挂载路径前不伪造 PCM。
- 关闭前 catalog/profile 保持 planned；不把主机、模型或其它 Unit 的结果转授。[接入与边界汇总](evidence/2026-11-03-visual-campaign-summary/README.md)

## P2：CardputerZero

### CZ-01

补完整系统回归、USB split timing、网络性能/隔离和摄像头/音频/电源/键盘 soak；
Linux 后端启动、驱动及长期边界独立验收，不继承 ESP32。

### 能力与故障归因

按只读能力与运行模式细化控制器/fixture 受理；扩展其他板型、固件布局和后端故障。
目标不支持、未建模、环境失败与有 guest 证据的应用失败分别归因，保留 #234 Flash 容量、
XIAOZHI 目标受理及磁盘不足/同任务恢复的已验证边界，不回写成固件缺陷。[归因台账](validation-ledger.md)

## 其它开放项：Unit 预览与新增主机

### 实时预览、程序与原驱动覆盖

- 继续未验 Unit/主机的原源码 API、guest 重启恢复、二进制入口/保存开机、完整包/资源及依赖覆盖；已选组合不转授。
- `UNIT-HOST-33`：固件 run-as-main/loader 语义与普通 .mpy 导入分开；扩展固件/主机、reset/重连后的能力恢复与完整清场。
- 继续 AIFlow checkpoint/artifact snapshot/virtual target、SSE、内嵌消费者，以及 program revision 引用保留/有界回收；局域网调用侧实例与产品化仍待验，共享 Bearer 不等于多租户控制权。
- `UNIT-HOST-28`：Preview 执行资源/推送与 Tab5 GDB 帧、reset/stop 共同生命周期单独验收，不继承 QEMU 缓存准入。
- `UNIT-HOST-29`：非对称逐灯颜色需官方通道到模型位置依据；旋转需独立物理 source、计数/方向标定并核真实 mounted 组件，不把 counter/reset 当轴运动。
- `UNIT-HOST-23`：三主机 HUB 数字 token 换行另行改善，保留 controller 前置。
- 补 ADC app calibration/ADC2 oracle、Thermal fixture、Core2 IMU、新 HUB 拓扑/视觉、原 IR GC 长期风险、原 Buzzer 自然 timer-zero 和完整 PWM 周期语义。
- FlashLight 实时 Web 轮询、动态 S1、PWM 和完整 controller/电气边界仍开放；已关闭的 `UNIT-HOST-35`、`UNIT-HOST-36`、`UNIT-HOST-37` 窄屏、Relay reset 与 cold 路由不重开。
- native/IRQ/thread 不可中断及重连清理保守处理，不承诺低秒级 SLA。[API 指南](unit-agent-api.md) · [AIFlow 计划](plans/2026-10-26-aiflow-live-preview-api.md)

### 新增主机剩余工作

- **CoreMatrix C158**：原版浏览器外部堆为空，补 8 MiB Quad PSRAM、Wi-Fi 数据面和浏览器硬 reset；默认 Device Service 上传契约和普通会话生命周期单独验收。
- **PaperS3**：Factory V0.5 仍间歇漏响应；关联原生 GT911 迟采样与原版前台绘图入队/其它操作，再用稳定帧、浏览器及同板真机对照区分各运行时延迟。已修扫描周期不关闭应用响应。[既有总线与帧](evidence/2026-11-18-papers3-browser-gt911/README.md)
- PaperDIY、初代 Cardputer 与 PaperS3 的其它电源、音频、存储和外设按上方数据面逐型号验收。

## 已完成，不再作为待办

`RUNTIME-03` stock startup、`RUNTIME-04` ATECC608、`RUNTIME-06` ESP-NOW 与 `UNIT-01` 接入里程碑的限定结果见
[当前状态](project-status.md)和[验证台账](validation-ledger.md)。这些前置不关闭任意应用、物理等价或仍列出的独立需求；原历史证据全部保留。

## 发布门禁

研发恢复后的代码/发布变更按根仓库和 tests 指南执行受影响检查、必要矩阵、同目标重建及相应文档更新；
纯文档整理不启动 guest 或服务。外部功能结论须附 full-commit-SHA 证据并准确标注 virtual-device validation/hardware validation，
不得把静态、构建或一次工具成功替代同路径验证。[仓库规则](../AGENTS.md) · [验证台账](validation-ledger.md)
