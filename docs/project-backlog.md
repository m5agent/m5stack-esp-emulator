# 项目 Backlog

日期：`2026-10-29`

本文只记录尚未完成的工作、依赖和验收条件。当前能力见
[项目当前状态](project-status.md)，历史运行和 evidence 见
[验证证据台账](validation-ledger.md)，代码入口见
[代码与验证入口地图](code-map.md)。

## 使用规则

- 任务达到验收后从本页移出；完整结果写入 `project-status.md` 和
  `validation-ledger.md`。
- 本页最多保留一句“已满足的前置基线”。轮次、PASS 计数、SHA、资源数值和
  失败 control 不在 Backlog 复制。
- 每个 PASS 必须绑定设备、runtime/profile、固件 SHA 和可复现 evidence。
- virtual-device 结果与 hardware validation 分开；RF、功耗、声学、光学、
  机械和电气结论必须来自真机。
- 模型缺口、fixture 缺口、基础设施失败和固件 FAIL 不得混算。
- 安全状态未知时保持 `unknown`/`REVIEW`，不能为了推进任务写成 PASS。

## 已完成，不再作为待办

以下里程碑已经进入当前状态和验证台账，只作为后续工作的依赖，不再重复列入
任务板：

- S3/C6/Core2 的统一 QEMU 板级、WiFi、BLE、frame/QOM、pcap 和 evidence
  主路径；
- controlled DNS A/AAAA/CNAME、有界 IPv4/IPv6 egress、TLS/Host policy、
  WPA2 正误密码、断线恢复、DHCP renewal、双 guest fabric 和 pcap；
- worker durable queue、HMAC、HTTPS/mTLS、credential rotation、
  multicast/unicast discovery、restart/reattach、跨 namespace/container
  QEMU，以及 worker-owned process/companion fencing；
- Core2 native-HCI、WiFi/公网/GATT、重连、active-stop、QOM `8 MiB` PSRAM、
  upper-bank MMU 和当前服务容量内并发；
- Cardputer-ADV 当前 UIFlow2 参考固件的 BMI270 `0x69` 初始化、官方
  `Imu.getAccel/getGyro`、QOM 注入回读、串口和可见 frame 闭环；
- FirmwareManifest/WebBurner、content-stable manifest、unknown required
  capability fail closed、mandatory capability policy、文件系统/SD/NVS
  fixture、静态审查、Secure Boot v2 镜像数学，以及
  aggregate/image/eFuse understatement、key mismatch 和 secure-version
  rollback fail closed。

“已完成”只关闭对应里程碑，不关闭更大范围。例如 WPA2 成对密钥路径完成，
不关闭 WPA3/真实 RF；Core2 功能级 native-HCI 完成，不关闭 bit-exact
controller 或物理 PSRAM/cache；Secure Boot v2 镜像验证完成，不关闭 live
eFuse 或生产 key。

## 优先级总览

| 优先级 | 工作流 | 未完成范围 | 主要风险 |
| --- | --- | --- | --- |
| P0 | Core2 legacy UIFlow 启动 | 共享 I2C、timer deadline、WDT mask、stateful SSI、pending SPI remap、high-priority DPORT handoff 和 classic RMT 已修复/验证；legacy Serial 已到 `APIKEY`，但 normal WDT 仍 reset，WDT-off 仍是黑帧 | probe/UIFlow2 PASS、RMT 初始化、SPI IRQ level、临时 bulk read、关闭 WDT 或 accelerator 都不代表 legacy 应用启动 |
| P0 | 网络产品化 | 物理跨主机 worker、跨主机幂等、任意 NAT 和外部 side-effect fence | 单机 namespace/container 不能替代物理多机 |
| P0 | Core2 物理/controller 等价性 | 更大规模、持续吞吐、其他 teardown、bit-exact controller 和物理 PSRAM/cache | 虚拟容量与物理时序不可互换 |
| P0 | 通用固件安全 | 运行态 ACL/许可、真机安全配置和更多真实业务 | 静态声明、镜像摘要自洽不等于设备 trust/ACL |
| P0 | 真机同路径 | 代表设备同固件 SHA 的 hardware validation | 当前仓库没有可继承的硬件结论 |
| P1 | 服务池与调度 | warm pool、配额、对象存储、审计和多机容量 | 当前仍是单机按需执行 |
| P1 | Tab5 P4 后端 | CSI、I2S/PCM、USB Host、SDIO、动态 I2C 和 controller touch | 闭源后端缺执行路径 |
| P1 | 设备视觉保真 | 逐设备结构、材质、hitbox 和视觉回归 | 功能 PASS 不等于外观保真 |
| P1 | Unit 外设集成 | 固定版本主机外壳、官方芯片协议、主机总线接线和 Web 双向状态 | 视觉模型和寄存器实现不能替代同 guest 的数据面证据 |
| P2 | CardputerZero | 系统、驱动、USB/网络竞态和长期回归 | 独立 Linux 后端不能继承 ESP32 结论 |

## 当前执行顺序

用户当前优先公众模拟器页面、最新模型与 GitHub Pages 分享入口；执行安排见
[公众入口计划](plans/2026-10-28-public-simulator.md)。按最新要求先完成
[纯浏览器执行调研](browser-runtime-feasibility.md)，已在独立 worktree 实现
browser backend、公众首页与模型更新，限定官方固件的当前结果见
[公众入口证据](evidence/2026-10-28-public-simulator/README.md)。创建响应丢失后的同key/body恢复与安全停止已完成限定真实回归；
最终合并检查已通过；按用户澄清优先复用定制C/QEMU，Rust两款演示保留为
研究原型且暂不发布。WASM构建与无固件控制前置见
[C/QEMU实验](qemu-wasm-port-research.md)；继续CoreS3真实
LVGL/输入/Unit及实际guest停止重开已完成限定fixture，主CPU jump栈恢复已有修正；后续处理默认时钟下LVGL队列/未覆盖异常路径，公众浏览器离线 profile、资源生命周期和正式 GitHub Pages 已取得限定准入；正式 HTTPS 地址已独立复验，其它范围按[本轮证据](evidence/2026-10-29-github-pages-production/README.md)保留。

`API-01` 已扩展到 StopWatch、StickS3 与 Core2 的当前 v2.5.3 复测；本轮
确认的 requests2、BLE UUID32、Modbus transform/async 和 M5UI 共享源码缺陷已有
hash-pinned 候选修正及三设备虚拟结果，见
[三设备证据](evidence/2026-10-28-multi-board-uiflow2-revalidation/README.md)。
QRCode.setText 与 TLS epoch 已完成三台 matching preimage→candidate 固件对照，
见[候选固件证据](evidence/2026-10-28-qrcode-tls-candidate-firmware/README.md)。
`Display.drawPixel` 的 framebuffer transaction 已在三台候选固件验证，见
[drawPixel 证据](evidence/2026-10-28-stopwatch-drawpixel-transaction/README.md)。
三台 Mic、Speaker raw/WAV、`playWavFile` 和 `playWav → playWavFile`
数据面已在最新 QEMU 上通过，并修复 ESP32-S3 DMA completion 的固定时间窗
缺陷，见[三设备音频证据](evidence/2026-10-28-three-board-audio/README.md)。
Core2 A/B/C 的 FT5x06 触控条和 PWR 的 AXP2101 事件路径已在最终 runtime
完成回调、hold 状态与 remove 验证；首版分支吞掉 `key:p` 的路由问题已修复，
见[Core2 输入证据](evidence/2026-10-28-core2-touch-buttons/README.md)。
`0067` 已通过 opt-in virtual-peer loopback 验证三台原厂
`espnow`/`m5espnow` 的 controller TX/RX DMA、unicast、broadcast、receive
和 IRQ；`0076` 又让 StopWatch↔StickS3、Core2↔StopWatch 两对独立 guest
经正常 TX/RX DMA 完成未加密双向 action-frame exchange。PMK/LMK/CCMP、
错误 key、完整 peer 生命周期与 RF/timing 仍由 `RUNTIME-06` 跟踪。
StopWatch/Core2 的 28 类、505 个 M5UI 文档方法已
完整执行；stock 仍保留 Canvas triangle、Image float scale 和 integer
Spinbox step 三个失败。Core2 candidate 的条带随后定位为 panel DMA 与
CPU data-register 双写，`0074` 修复后状态 `4/4` 和 triangle/image
`2/2 FRAME_PASS`，见
[Core2 M5UI DMA 修复](evidence/2026-10-29-core2-m5ui-dma-dedup/README.md)。
最终 `78555183…` runtime 的三设备并发回归为 system runtime 各 `51` 项零失败、
共享候选修复各 `7/7`、设备组 StopWatch `6/6`、StickS3 `5/5`、Core2
`6/6`，全部首轮 PASS 且无 retry；sockets/MQTT/network/EzData、audio
wrapper、requests/Modbus candidate、TLS candidate 和 Device API 也在同一
binary 重绑；stock HTTP/Modbus/TLS 的原始失败继续保留。见
[最新接口复测](evidence/2026-10-28-three-board-uiflow2-latest-runtime/README.md)。
2026-10-29 的三设备全接口复测进一步确认 system/shared、通信、音频、
ESP-NOW 和已选外设稳定，并修复 M5UI 设备尺寸/旋转、Core2 程序预算、
完整 BLE 身份表与 Core2 blocker 文案。Core2 candidate 帧条带/坐标问题
随后由 `0074` 关闭模型根因；stock Core2 `ble-nus` 又改走
`core2-native-hci` + matching ELF，三个独立 session 各 `8/8 PASS`。
StopWatch/StickS3 stock internal-controller BLE 仍阻塞。见
[全接口证据](evidence/2026-10-29-three-board-uiflow2-full-retest/README.md)、
[Core2 M5UI DMA 修复](evidence/2026-10-29-core2-m5ui-dma-dedup/README.md)
和[Core2 stock BLE 证据](evidence/2026-10-29-core2-stock-ble-native-hci/README.md)。
Core2 stock `m5ble-server` 的 `Server.get_client` SDK 错误另由 `0025`
候选源码修复，两轮独立 session 均为 `22/22 PASS`；stock 失败与
candidate lane 分开保留，见
[get_client 候选证据](evidence/2026-10-29-m5ble-get-client-candidate/README.md)。
`9bf74439…` 的三设备再次复测已重绑这些路径：system/shared、协议、
ESP-NOW、音频和板级接口稳定；StopWatch/Core2 M5UI 的 505 个 widget
方法均有结果，candidate state/frame 均通过；requests2、Modbus async、
TLS 和三设备 M5BLE candidate 也重新通过。新增结果没有改变本文仍开放的
stock SDK、StopWatch/StickS3 controller、真机和物理边界，见
[接口再次复测](evidence/2026-10-29-three-board-uiflow2-interface-retest-r2/README.md)。
当前 QEMU `dd4b1b34…` 的 r4 三设备并发复测再次重绑 system/shared、
通信、audio、ESP-NOW、BLE、M5UI 和板级接口；Core2 network 首轮
`14/14`，没有新增稳定模拟器缺陷。stock/candidate 分层与以上开放边界
保持不变，见[接口复测 r4](evidence/2026-10-29-three-board-uiflow2-interface-retest-r4/README.md)。
Core2 legacy 另由 `0065` 关闭 high-priority DPORT handoff 调度死锁，由
`0066` 补 classic RMT 并越过 Neopixel 初始化错误；`APIKEY` 后黑帧和
  normal-WDT reset 继续保留；`0070` 的 virtual UART trace 又证明 BOARD/APIKEY
  晚于 stage-1 deadline，而降低 icount shift 仍不消除 reset，见
  [UART clock 证据](evidence/2026-10-29-core2-legacy-uart-clock/README.md)。
  新 phase profile 在 WDT-off 80 秒内记录 `103,058` SSI transactions、
  `3,181,984` RX bytes，CPU0 约 60% 采样落 `0x40087980..8e` 的 handoff
  簇。`0071` 的完整 controller 直方图进一步得到无采样 80 秒控制
  `104,302` transactions，其中 `0x05` `49,489`、`0xBB/64B` `49,586`；
  相邻 command gap 合计 `79.699109375 s`，主要分布在 `1-10 us`、
  `100 us-1 ms` 和 `1-10 ms`。`0072` 进一步确认
  `0xBB/64 -> 0x05/1 -> 0xBB/64` 主循环，`82.4%` gap 位于下一次 `0x05`
  前，平均 `1.3115 ms`。`0073` 进一步把主要 issuer 绑定到 ROM
  read-command 区间 `0x4006222c` 与应用 segment 5 `0x40093b57`，
  `105,161` 个 transaction 均有 PC 记录且 overflow 为 `0`。立即切核
  四类控制均没有改善 normal-WDT 启动预算，已全部丢弃。下一步结合
  matching legacy source/ELF/MAP、IRQ delivery 和 cache/MMU 状态解释该
  路径。`0075` 已记录 `RDSR` 返回值、前序 64-byte read、cache delta 与
  有界 `s32c1i` caller/lock/holder-PC；status bit0 始终为 `0`，但
  `0x3ffbf2cc` 上存在真实跨核锁竞争。failed-CAS slice yield 与原
  normal-WDT 均在同一 TG0 stage-1 边界 reset，不能作为修复。见
  [status/CAS 证据](evidence/2026-10-29-core2-legacy-status-cas/README.md)。

此前用户要求先完成 `API-01`：CoreS3（LVGL）与 Cardputer-ADV（无 LVGL）的
全部 UIFlow2 接口盘点、实际执行、选定 Unit 联合测试和 Device Service API
易用性修复。按[验证计划](plans/2026-10-27-uiflow2-complete-api-sweep.md)逐项
对账，清单、导入和调用返回不能代替行为 PASS；模型/fixture/固件差异逐项保留。
本轮修复与逐项审计见[交付证据](evidence/2026-10-27-uiflow2-api-sweep/README.md)；
后续优先关闭保留的 stock SDK/绑定失败、WDT warm reboot、未实现控制器和未选外设场景。

此前AIFlow实时编程/实时预览场景仍按 `UNIT-01` 队列补预览执行闭环：
已满足前置为取消事务、同 guest UART raw REPL、Web 程序面板、限定HUB传感器/
控制leaf的原驱动执行及显式按需共享QEMU帧样本，范围见[本轮证据](https://github.com/m5agent/m5stack-esp-emulator/blob/a37342f61c05964c060719a6e35c2d568c828e84/docs/evidence/2026-10-26-live-unit-preview/README.md)。
完整文件包/资源与纯字节码`.mpy`依赖已实现，范围见[文件包证据](https://github.com/m5agent/m5stack-esp-emulator/blob/a37342f61c05964c060719a6e35c2d568c828e84/docs/evidence/2026-10-26-live-package-and-detent/README.md)。
Scroll限定原驱动与按键/RGB闭环、公共完整checkpoint及同步revision引用已有前置；1.42 Preview/Run协调已完成CoreS3 PIR/Relay同VM、pending覆盖、运行中prompt取消再跑与ZIP清理的[限定验收](https://github.com/m5agent/m5stack-esp-emulator/blob/a37342f61c05964c060719a6e35c2d568c828e84/docs/evidence/2026-10-27-preview-run-control/README.md)。CoreS3 PIR另完成真实包部署事务中取消及同VM恢复（不声称单chunk中断）；继续补其它Unit/主机、guest重启恢复、二进制入口/保存开机、AIFlow checkpoint事件/虚拟目标、SSE及程序revision引用保留/有界回收。源码与完整包配额均可显式配置，不关闭长期引用保留/有界回收。
双向动画继续闭合 `UNIT-HOST-29`：默认全灯同色反馈取任意通道排列均相同的准确子集；
非对称逐灯颜色仍需官方通道到模型位置依据，旋转需独立物理source和计数/方向标定，
不能把逻辑counter写入/reset当轴运动。验收须核真实mounted组件。
已有共享样本不关闭 Preview 执行资源或推送协议；Tab5原GDB帧与reset/stop的
共同生命周期门禁按 `UNIT-HOST-28` 另做，不继承QEMU缓存准入。
二进制入口须按`UNIT-HOST-33`先取得固件run-as-main/loader路径；普通`.mpy`导入不具备完整脚本入口语义。1.44已分开二进制checkpoint存储与执行，四host双lane旧Run保护已验；1.45严格显式base与CoreS3候选loader固定SHA的模块身份/重复Run/异常/Ctrl-C已取得限定guest诊断，1.46已接有条件公共入口且CoreS3 stock/兼容固件及Web通过，继续更多固件/主机、reset/重连后能力恢复与完整清场；FlashLight部分数字路径/四host和CoreS3 mounted已验，动态S1、PWM/冷route边界仍开放，见[新证据](https://github.com/m5agent/m5stack-esp-emulator/blob/a37342f61c05964c060719a6e35c2d568c828e84/docs/evidence/2026-10-27-flashlight-and-uiflow-base/README.md)。4Relay/FlashLight新协议冲突与模型边界见[本块证据](https://github.com/m5agent/m5stack-esp-emulator/blob/a37342f61c05964c060719a6e35c2d568c828e84/docs/evidence/2026-10-27-binary-checkpoint-admission/README.md)。
FlashLight的OUT_SEL旧资格问题已按[限定路由证据](https://github.com/m5agent/m5stack-esp-emulator/blob/a37342f61c05964c060719a6e35c2d568c828e84/docs/evidence/2026-10-27-flashlight-route-history/README.md)闭合；0047已有真实GPIO/IOMUX/RTC来源与无边沿连续低的C实现，软I2C显式上拉修复记录在[本轮收尾](https://github.com/m5agent/m5stack-esp-emulator/blob/a37342f61c05964c060719a6e35c2d568c828e84/docs/evidence/2026-10-27-flashlight-cold-pad/README.md)。用户要求当前bug修完即收尾，37仍需新runtime四host原constructor/API/取消再Run与mounted Web，及独立完整矩阵；准备包不算执行。36hard-reset、S1/PWM和电气边界继续开放。
运行时不可中断、native/IRQ/thread 清理及重连缺口须保守处理，不承诺低秒级 SLA。验收见
[AIFlow API评估计划](plans/2026-10-26-aiflow-live-preview-api.md)。AIFlow本身的
checkpoint/artifact snapshot/virtual target也需衔接；Preview服务端与限定Web消费者已实现，SSE与AIFlow消费者未接。
Live sessions托管消费者已有CoreS3 PIR/Relay的[限定Web验收](https://github.com/m5agent/m5stack-esp-emulator/blob/a37342f61c05964c060719a6e35c2d568c828e84/docs/evidence/2026-10-27-preview-web-consumer/README.md)，不转授其它Unit/主机或AIFlow；四主机HUB控制组和U131双GPIO/蓝灯、UNIT-HOST-35窄屏/长dt构图已完成[限定验收](https://github.com/m5agent/m5stack-esp-emulator/blob/a37342f61c05964c060719a6e35c2d568c828e84/docs/evidence/2026-10-27-preview-controls-and-2relay/README.md)；继续补未验Unit/主机与AIFlow调用侧，共享Bearer仍不等于多租户控制权。后续按既有Unit队列推进，并衔接AIFlow checkpoint/虚拟目标、SSE与revision有界回收。
初始picker的跨主机竞态已修复并保留失败负控；范围见[新实时程序证据](https://github.com/m5agent/m5stack-esp-emulator/blob/a37342f61c05964c060719a6e35c2d568c828e84/docs/evidence/2026-10-26-live-program-web-and-hosts/README.md)。
三主机HUB数字token换行按`UNIT-HOST-23`单独改善，保留既有controller PASS。

`UNIT-01` 已具备 CoreS3 27种选定场景与三主机各11种
场景的源码API→可见session→实时读写控制闭环；新增24组合已完成，范围与入口见
[源码 API 指南](unit-agent-api.md)。预览API闭环之后的Unit支线包括这三款主机剩余 Unit 的实际
源码 API 执行，并解决这些主机的 ADC app calibration/ADC2 oracle 与 Thermal
fixture 准入；继续处理新 HUB 拓扑、视觉、原 IR GC 长期风险、原 Buzzer、
完整 PWM 周期语义。初始化 route 已修复，历史d1ba完整轮曾通过；当前3f1617独立完整轮66/67、Core2 IMU仍OPEN，
范围见当前状态页；不关闭其它原驱动或真机门禁。实现契约见
[Unit 集成计划](plans/2026-10-25-unit-runtime-integration.md)，精确批次与证据
见验证台账；CoreS3 已通过的场景不替代其它主机验收或真机同路径验证。

主线其余 P0 继续按以下顺序推进，已有修复和诊断不扩大为 legacy 应用启动：

1. `RUNTIME-03`：pending SPI remap、high-priority DPORT handoff 和 classic
   RMT 已验证。`0065` 以 `5/5` 首启动关闭调度诱导 deadlock；`0066` 让
   WDT-off legacy Serial 从 Neopixel `OSError` 前进到 `APIKEY`，但 normal
   WDT 在 BOARD/APIKEY 之前 reset。下一步先解释 pre-boot guest/controller
   工作预算和 watchdog deadline，不能把 accelerator override 作为修复。
2. `NET-04`：把已验证的单机 worker 边界推进到物理跨主机和完整 side-effect
   ownership。
3. `CORE2-02`：补更大规模、持续吞吐、其他 teardown 和物理/controller 等价性。
4. `FW-01/02/03`：补运行态权限/许可、真机安全配置和真实业务覆盖。
5. `RUNTIME-02/04/06`、`HW-01`：补 C6 Zigbee、ATECC608、ESP-NOW
   加密/lifecycle peer 和真机同路径。
6. `SVC-01/02/03`、`TAB5-01`、`UI-01`、`CZ-01`：服务化和专项收尾。

## 依赖与并行原则

| 类别 | Task | 开始条件 | 与其他工作的关系 |
| --- | --- | --- | --- |
| 立即可做 | `RUNTIME-03`、`FW-01`、`FW-03`、`SVC-03`、`UI-01` | 当前仓库、测试和本地 runtime 可用 | `RUNTIME-03` 触碰 Core2 QEMU 时与 `CORE2-02` 串行；`SVC-03` 先做无语义移动并保持 API/evidence 契约 |
| 需要多机环境 | `NET-04`、`SVC-01`、`SVC-02` | 至少两个可失联、可 drain、可独立寻址的执行节点 | `SVC-01/02` 的跨主机部分依赖 `NET-04`；单机 namespace/container 结果不能替代 |
| 需要真机或外部控制面 | `FW-02`、`HW-01` | 同固件 SHA 的设备控制、串口、画面、网络和外设观测入口 | `FW-02` 还必须取得 live eFuse/生产 key 流程授权；静态镜像分析不能代填 |
| 后端/外部 peer 阻塞 | `RUNTIME-02`、`RUNTIME-04`、`RUNTIME-06` | 可重建 802.15.4 MAC 路径、公开固件匹配 ELF/ATECC608 配置，或 key-bound/CCMP ESP-NOW controller 路径 | 在 blocker 消除前保持 `PARTIAL`/`runtime_model_gap`，不承诺完整兼容 |
| 决策或独立后端 | `TAB5-01`、`CZ-01` | P4 backend 重建/扩展决策；CardputerZero Linux 回归资源 | 不继承 S3/C6/Core2 的完成度，可与主线并行 |

## 可执行任务板

| ID | 状态 | 下一项最小交付 | 验收 |
| --- | --- | --- | --- |
| `API-01` | 进行中 | 接续 stock SDK/绑定失败、WDT warm reboot、native build feature、未实现控制器与未选外设；扩展 Cardputer-ADV Unit 准入及同固件更多行为域。`0074` 已关闭 Core2 candidate M5UI frame routing/oracle；Core2 stock BLE NUS 已通过 native-HCI，`Server.get_client` 已有 hash-pinned 候选修复；StopWatch/StickS3 stock controller 仍开放 | 保留失败负控；stock/matching/candidate 分 lane，具体行为/控制器数据与 session/固件/runtime/串口/帧/ZIP/清理绑定，不能用审计数量或局部通过关闭全部接口/硬件范围 |
| `RUNTIME-03` | 进行中 | `0065` 关闭 high-priority DPORT handoff 调度死锁，`0066` 补 classic RMT，`0068` 将 legacy HSPI/SPI2 与 UIFlow2 VSPI/SPI3 都接到同一 panel sink，`0069` 修正 protected `WDTFEED` 语义；`0071/0072` 精确得到 `0xBB/64 -> 0x05/1 -> 0xBB/64` 主循环；`0073` 绑定主要 issuer；`0075` 排除 RDSR WIP/busy 错误并把成本定位到 scheduler/list 跨核锁竞争，failed-CAS slice yield 无效 | 同固件 SHA 在正常 WDT、真实 Flash 数据面和 WiFi-backed Device Service 路径下渲染完成启动 UI/应用帧并保持运行；DPORT 协作、classic RMT、dual-SPI、stateful SSI、pending SPI remap、protected WDT feed、0071-0073 transaction/issuer profile、0075 status/CAS 关联和最终三设备组保持可重放 |
| `RUNTIME-06` | 进行中 | `0067` 已用 controller TX/RX DMA loopback 验证三台 unicast/broadcast/receive/IRQ；`0076` 已完成 StopWatch↔StickS3 和 Core2↔StopWatch 的独立 guest 明文 exchange；下一项是 PMK/LMK/CCMP、错误 key、peer 生命周期与丢包/重试 | 至少一个 encrypted lane 使用实际 key-bound controller/CCMP 完成正负控；保留 loopback、external plaintext、encrypted 和 RF/timing 分 lane |
| `NET-04` | 进行中 | 物理跨主机 executor/reattach、跨主机幂等、任意 NAT、QEMU 内 guest/controller 和外部 side-effect fence | 跨主机 job 可迁移、重放、接管和清理；ownership 无法确认时 fail closed |
| `CORE2-02` | 进行中 | 大于当前服务容量、持续吞吐、其他 teardown、bit-exact controller/baseband、物理 PSRAM/cache timing 和真机 | 结果绑定固件/ELF/QEMU/工具哈希；虚拟容量不外推为物理等价 |
| `FW-01` | 进行中 | 运行态 ACL/权限、完整源码和依赖许可覆盖、法律审批 | 镜像属性与运行态分开；unknown 不写成 PASS |
| `FW-02` | 进行中 | 真机 Secure Boot、Flash Encryption、live eFuse、bootloader anti-rollback 和生产 key | 测试/生产 key 不入库；安全状态可审计 |
| `FW-03` | 进行中 | 真实 key/云端业务；更多设备与 firmware family；继续扩展 SD/NVS 和网络预期 | 导入、capability、boot、输入、功能和网络分层记录 |
| `RUNTIME-02` | 进行中（backend blocked） | C6 802.15.4 MAC ACK/commissioning 和 join/收发/离网生命周期 | 真实 guest 驱动完成生命周期；否则保持显式 `runtime_model_gap` |
| `RUNTIME-04` | 进行中 | ATECC608 I2C 命令和测试 slot/config fixture | 固件越过安全元件初始化并进入应用帧；不提交生产私钥 |
| `SVC-01` | 进行中 | namespace-managed/Tab5/cross-host companion 和跨主机 idempotency | 重启后接管或明确失败，不产生假 running |
| `SVC-02` | 待做 | warm pool、配额、对象存储、审计和容量指标 | 租户状态隔离，资源与 GC 可观测 |
| `SVC-03` | 待做 | 先提取纯配置/请求解析边界，再拆 store、runtime adapter、evidence collector 和 session 状态机 | 每一步只移动一个边界；对外 API、历史恢复和 evidence 字段不回归 |
| `HW-01` | 待做 | 代表设备的同固件 SHA 真机测试计划 | evidence 明确标为 hardware validation |
| `TAB5-01` | 决策 | 重建或扩展 P4 backend | 缺失控制器与端到端网络有执行路径 |
| `UI-01` | 待做 | 逐设备结构、材质、hitbox 和截图阈值 | 设备本地视觉回归，不跨设备继承 |
| `UI-02` | 进行中 | C/QEMU默认时钟LVGL队列、未覆盖异常路径、长期稳定性及持久化；扩展设备/固件/Unit准入；Rust演示仅作研究原型 | 各后端按设备/固件准入；丢失响应后能恢复owned session并安全停止；静态构建不含凭据/固件/raw；用户审阅后再部署 |
| `UNIT-01` | 进行中 | 其余同guest Unit（issue #5–#8 已补控制器路径，仍需更广固件/主机矩阵）、FlashLight冷route的有效pad来源/连续低观察生命周期、更多主机/固件的二进制入口验收与保存开机程序；AIFlow checkpoint/虚拟目标、Preview后续恢复与GC、SSE/实时分发；程序revision引用保留/有界回收；Tab5 GDB frame生命周期与其它后端取消场景实际会话验证；其它准入主机/固件的实际源码API执行、ADC2 oracle与Thermal fixture、新HUB拓扑、原IR GC/原Buzzer、完整PWM周期、Heart生理算法及视觉缺口；Scroll的TIM回绕、RGB多槽队列、轴角/方向标定、bootloader/Flash持久化与地址0；Roller485协议与功能准入 | 新固件重新验证；逐型号同guest读写、Web输入/输出、可见session和evidence；未准入组合不能凭离线产物升级；分次帧不假称原子一致，可读性不外推所有UI；Core2 IMU偶发marker保留独立完整轮，不以单例补PASS；主机问题单独记录，不以诊断、custom guest或桥契约替代原固件结论；真机同路径另验 |
| `CZ-01` | 待做 | CardputerZero 系统、驱动和长期回归 | 启动、USB、网络、音频、摄像头和真机边界明确 |

## P0：Core2 legacy UIFlow 运行时

### RUNTIME-03

已满足的前置基线：shared I2C、equal-deadline timer、WDT mask、stateful
SSI、handoff timeline/state sweep/setter trace、三次 WDT liveness、
pending SPI remap、high-priority IRQ 协作和 classic RMT 均可重放。

上述结果都没有把 legacy 固件变成产品 PASS。精确时间线、哈希和检查数只在
[验证证据台账](validation-ledger.md)；缺口语义见
[运行时模型缺口登记](runtime-model-gap-register.md)。

当前阻断：

- service-form functional lane 必须使用 `runtime=qemu-wifi`。早先默认
  `runtime=qemu` 的直接诊断没有 `misc.esp32_wifi`，guest 可能在
  `0x60033d24` 的 WiFi DMA status alias 上等待无设备状态，不能单独作为
  legacy 启动或黑帧根因证据；
- 通用 LittleFS 会被 legacy guest 拒绝并重新格式化。使用 UIFlow
  checkout 自带 LittleFS2 packer 后，`qemu-wifi` 120 秒已执行注入的
  `/flash/boot.py` 并输出 `CORE2_LEGACY_VFS_BOOT`，但 setup/main 仍未出现；
- normal-WDT 在同一 public legacy SHA 上仍触发 TG0/TG1 system reset，
  没有完成原厂 startup UI；
- 关闭 WDT 只作为诊断 control 后，120 秒仍为 302-byte 黑帧；该轮 CPU0
  `0x40249c5d`、CPU1 `0x400e1ffd`，旧 CPU1 `0x40100049` LVGL wait
  未复现，后续必须在 matching VFS + WiFi lane 上重新定位；
- BIN-bound 映射已把该 wait 定位到 `lv_refr_vdb_flush`；display flush
  callback 曾在旧 runtime control 中调用，但 SPI completion 与
  `lv_disp_flush_ready` 未出现。该结论保留为历史无 NIC 控制，不自动继承到
  corrected fixture；
- `0064` 已修复 pending SPI source 在 mapping 写回时不重算的通用缺陷，
  独立 Core2 ESP-IDF probe 在同一固件/ELF 上由 callback timeout 变为
  fixed PASS；最新 legacy runtime 仍没有到达 display completion，
  60 秒 PC trace 在约 `15.53 s` reset 前未命中 flush/callback；
- `0065` 证明旧固定双 PC 死锁由大 TCG slice 让 sender 抢先清共享 flag
  引起；level-4/5 handler 在 `memw` 发布 start 后、sender 在 `retw` end
  路径协作让出，五轮首启动均到 `5 s` 边界且不再固定旧双 PC；
- `0066` 补 classic ESP32 RMT 寄存器、RMTMEM、threshold、`TX_END` 和
  INTMATRIX source 47；同一 legacy 固件不再报 Neopixel translator
  `OSError`，Serial 到达 `APIKEY`。该历史 WDT-off 轮未使用 matching VFS
  和 WiFi NIC，因此其黑帧只保留为无网络诊断控制；
- `0068` 修正 Core2 面板控制器路由：UIFlow2 使用 VSPI/SPI3，而公开
  legacy `display.TFT` 使用 HSPI/SPI2。SPI3-only 负控的 legacy panel
  DMA 写入为 `0`，同固件 dual-SPI 后 legacy probe 得到 1422 nonblack
  pixels；这不代表原厂 startup UI 已完成；
- 当前 local UIFlow2 ELF 与该 BIN 字节仍不一致，因此函数命名全部来自
  BIN 指令/结构匹配，不声明 ELF 符号等价；
  `Core2FactoryTest` 在 I2C 修复后仍未重跑。

开放范围：

1. 取得 public `UIFlow_Core2 v1.15.4` 的 matching ELF/MAP。byte audit 已证明
   local UIFlow2 v2.5.3 ELF 不能用于符号命名；
2. 在 matching LittleFS2 VFS 与 `runtime=qemu-wifi` lane 重新观察旧
   `0x40100049` BIN-bound LVGL wait；修正后的 120 秒点未复现该地址，
   不能把旧对象/寄存器结论直接继承为当前第一失败点；
   `0071/0072` 已给出完整 command/RX-length/gap、联合键、per-command gap
   和 transition 分布；`0073` 已绑定主要 issuer PC，`0075` 已排除
   RDSR busy 位并定位到 scheduler/list 跨核锁竞争；下一步结合
   matching symbols、tick/IRQ rate 与最长锁持有区间解释 `0x05` 前的
   transaction-bound gap；
3. 保持 `0064` 的 pending SPI remap、`TRANS_DONE && TRANS_INTEN` 与 guest
   callback 回归；在 WiFi-backed 系统菜单初始化中定位下一个未完成路径，
   再决定 display completion/`lv_disp_flush_ready` 是否仍是当前阻断；
   保留 `0036` stateful SSI 数据面，不使用 `blk_pread` bypass；
4. 在 normal WDT 下把 TG0 stage-1、TG1 feed、interrupt mask 和 late phase
   放回同一条启动时间线，解释 reset 与 late state 的关系；
5. 保持同一 public SHA 的 AXP2101/AXP192 A/B 对照，并重跑
   `Core2FactoryTest` 与 Core2 UIFlow2 设备组，防止 shared bus 回归；
6. 保持 `0065` 的 IRQ enter/return/reset active-state 与 `memw`/`retw`
   协作边界，保持 `0066` 的 RMT controller memory-TX 契约；从最终
   `APIKEY` 状态定位下一个未完成 guest/controller 路径。

验收：

- 已满足的最小 probe 首启动门禁继续可重放，且业务补丁不包含 trace/ring；
- 同一 UIFlow 固件 SHA 在正常 WDT、`0036` stateful SSI/m25p80 数据面下
  出现非空应用帧并稳定运行；不得依赖 `M5SW_DISABLE_WDT`、bulk-read
  bypass、accelerator override 或 retry；
- legacy TG0/TG1 reset 的触发点有证据，shared bus、TIMG trace 和 Core2
  UIFlow2 外设组回归保持 PASS；`0065`/`0066` 契约继续可重放；
- BIN-bound trace 能解释 display flush callback、SPI completion 和
  LVGL `flushing` 清零关系；normal-WDT TG0 stage-1 reset 与 late phase
  分开记录；matching ELF/MAP 若取得则只能提高符号置信度，不能替代运行证据。

## P0：网络与 worker

### NET-04

已满足的前置基线：durable queue、HMAC、TLS/mTLS、发现、同机 reattach、
container-local QEMU、409 ownership fence 和 worker-owned companion
partition fence 已进入状态页与台账。

开放范围：

- 物理跨主机 worker、QEMU executor、迁移、reattach 和持续 evidence 流；
- 跨主机 job/session/evidence idempotency 与旧 lease result fence；
- 无 reachable discovery seed 时的任意 NAT traversal；
- QEMU 内 guest/device-controller 状态和 worker 未拥有的外部 side effect；
- namespace-managed、Tab5 和 cross-host companion recovery；
- 生产容量调度、对象存储、审计和 warm pool。

验收：

- worker 强杀、重启、失联、迁移和 drain 都有确定终态；
- 任务、worker generation、QEMU PID/start time、lease 和 evidence 可关联；
- ownership 无法确认时停止可达 runtime，拒绝 stale result，不产生假
  running；
- 物理多机与单机 namespace/container 结果分层记录。

## P0：Core2 controller 与物理边界

### CORE2-02

已满足的前置基线：`core2-native-hci`、WiFi/公网/GATT、QOM 8 MiB PSRAM、
upper-bank MMU、重连、长稳、active-stop 和当前服务容量门禁已有虚拟设备
evidence。精确结果只在验证台账维护。

开放范围：

- 大于当前服务单设备容量；
- 持续吞吐和其他 teardown 模式；
- bit-exact Espressif BT controller/baseband；
- 物理板载 PSRAM/cache timing 与性能；
- 同固件路径真机验证；
- 新目标固件必须重新校验符号/hook 偏移，不能按 SoC 继承 PASS。

验收：

- 每项结果绑定 firmware/ELF/QEMU/工具哈希和实际运行参数；
- 失败 control、可恢复 transient 和 panic 符号化保留；
- 虚拟结果不写成物理 controller、RF、cache timing 或真机 PASS。

## P0：通用固件审查

### FW-01 文件系统、权限与许可

已满足的前置基线：LittleFS/FAT/SPIFFS 只读清单、文件哈希、敏感路径、
镜像可见权限、SBOM/SPDX 和有界许可 allowlist/denylist 可执行。

开放范围：

- 固件运行态 ACL、权限和执行策略；
- 生成代码、包外 vendor 依赖和完整源码/依赖许可覆盖；
- 法律审批工作流。

验收：镜像属性与运行态强制执行分开；资源、来源、哈希、声明和最终结论
可审计；不支持的文件系统配置返回 `INVALID`；unknown 不被提升为 PASS。

### FW-02 真机安全配置

已满足的前置基线：Secure Boot v2 signature sector CRC、镜像摘要、
RSA-PSS/ECDSA 数学验证、包内公钥摘要和 secure-version 对照可执行。

开放范围：

- 包内 summary 的权威来源和公钥 authenticity；
- live eFuse trust root、bootloader anti-rollback 执行；
- 真机 Secure Boot、Flash Encryption 和生产 key 流程；
- 测试/生产 key 的隔离和审计。

验收：镜像声明、运行态和真机验证分层；生产敏感值不进入仓库或日志；
无法取得权威输入时保持 `unknown`。

### FW-03 跨厂商回归

已满足的前置基线：Manifest、WebBurner ZIP path/casefold/symlink 与资源
唯一性、显式 sdkconfig 优先级、多 build SoC 选择、公开 CDN 强制刷新、
SHA-bound expectation、SD/NVS fixture、静态/文件系统审查和 network-first
执行路径可用的样本已进入状态页与台账。

开放范围：

- issues #2/#3 的原始私有完整 Core2 应用归档复跑；公开最小启动路径与
  UIFlow2 LVGL 字形已修复验证，不能替代原归档或私有业务验收；
- 真实 key、Realtime、音频和云端业务结果；
- 更多设备、ESP32 LX6/P4 和 vendor/MicroPython framework；
- 新的 SD/NVS、输入和网络 fixture；
- 失败根因闭环与 capability/security evidence 冲突处置。

验收：

- 每轮绑定实际 BIN、expectation 和 fixture SHA；
- 同 ID/version 但字节变化时重新执行；
- `runtime_model_gap`、`runtime_fixture_gap`、`INFRA_ERROR` 和固件 FAIL
  分开记录。

## P0：运行时模型缺口

### RUNTIME-02 C6 Zigbee/802.15.4

当前缺口：QEMU C6 缺少完整 802.15.4 MAC/commissioning 路径；另一个后端
只观察到双向帧，未完成 join 或 On/Off。

下一项最小交付：补 MAC ACK/commissioning 语义，或取得公开固件匹配 ELF，
并用 `tests/firmware/c6_zigbee_thread_sim/run_feasibility.py` 验证加入、收发
和离网。

验收：真实 guest 驱动完成完整生命周期；否则保持 `runtime_model_gap`，
不承诺所有 C6 固件兼容。

### RUNTIME-06 ESP-NOW 加密与 peer 生命周期

已满足的前置基线：`0067-esp32-espnow-controlled-peer-loopback.patch`
在 StopWatch、StickS3 和 Core2 上，用原厂 `espnow`/`m5espnow` 栈完成
controller TX DMA action frame、虚拟 peer echo、RX DMA 和 IRQ 回调；
unicast、broadcast、receive、peer table 与状态边界均绑定同一 session。
该 loopback 默认关闭，只由 `M5SW_ESPNOW_LOOPBACK=1` 显式启用。

`0076-esp32-external-espnow-peer-bridge.patch` 已完成下一层基线：两个
独立 guest 使用显式配对的 loopback UDP 端口和固定受控 peer
`02:00:00:00:00:43`，让 StopWatch↔StickS3 与 Core2↔StopWatch 通过正常
controller TX/RX DMA 双向交换未加密 action frame。四个 session 均保留
evidence、使用 `purge=0` 停止，并确认 runtime PID 消失。该 bridge 默认
关闭，拒绝残缺/相同端口和与 `0067` 混用，只转发 management action frame。

开放范围：

- PMK/LMK 加密 payload、CCMP 和错误 key 负控；
- peer add/update/delete、重放、丢包/重试和生命周期；
- channel/rate、bit-exact controller、RF/antenna 和电气时序。

验收：external plaintext 与 encrypted lane 分开记录，不能在 Python 中合成
payload、CCMP 或 callback；encrypted lane 必须使用实际 key-bound
controller 路径并包含错误 key 负控，否则保持 `runtime_model_gap`。

### RUNTIME-04 Core2 for AWS ATECC608

当前缺口：公开固件依赖的 ATECC608 安全元件未建模，初始化后主动 abort。

下一项最小交付：实现固件实际使用的 I2C 命令和测试 slot/config fixture；
生产私钥不得入仓。

验收：安全元件初始化通过并进入非空应用帧；安全元件证据与普通功能证据
分开记录。

## P0：真机同路径

### HW-01

当前缺口：没有与虚拟设备相同固件 SHA、测试计划和关键输入的真机记录。

验收：代表设备完成 `hardware validation`，保留串口、画面、网络/外设和必要
测量证据；不得从同 SoC 其他设备或其他固件 SHA 继承。

## P1：服务化与代码整理

### SVC-01 活动实例接管

开放范围：namespace-managed/Tab5/cross-host companion、跨主机接管和连续
external evidence 流。当前同机 QEMU/QMP 与 trusted-host companion 恢复是
前置基线，不是跨主机完成证据。

验收：服务重启后接管或明确失败；ownership 全部匹配才 adopt；不产生假
running。

### SVC-02 服务池

开放范围：warm pool、队列、配额、对象存储、审计、多租户隔离和容量指标。
不可信固件最终需要 disposable VM/copy-on-write，而不是当前单机 namespace
直接充当恶意代码沙箱。

### SVC-03 编排拆分

`platform/tools/device_service.py` 仍承担 session、存储、runtime、证据和
HTTP 热区。Core2 并发 evidence 绑定该文件的 tool hash，因此任何拆分都必须
配套重跑受影响证据，不能让新代码继承旧 PASS。按以下顺序拆：

1. 固定 `/api/v1`、session JSON、evidence ZIP 和历史恢复契约，并记录当前
   `device_service.py` 的公开符号；
2. 先移动无状态请求解析、运行参数构造和设备规格加载，保持原模块 re-export；
3. 拆 content-addressed firmware/artifact store；
4. 拆 QEMU、Tab5、network runtime adapters；
5. 拆 evidence collector 和 lifecycle/history repository；
6. 最后收敛 HTTP/orchestration facade。

验收：每步单独可回滚；平台测试、目标 unified lease、历史恢复和 evidence
字段不回归；不在移动文件的同时改变错误码、状态机、运行参数或 evidence 结构。

## P1：专项

### TAB5-01

当前缺口：动态 I2C/RTC/IMU/INA226/PI4IOE/IP2326、P4 I2S/PCM、MIPI-CSI、
USB Host、SDIO、controller-level ST7123 和 P4↔C6 ESP-Hosted 端到端网络。
先决定重建或扩展 P4 backend，不能从 QEMU S3/C6/LX6 继承完成度。

### UI-01

当前缺口：14 款主机已接入固定版本模型外壳，加载失败时保留原 renderer
回退；StopWatch 仍是唯一参考质量外壳。模型接入不替代逐设备结构尺寸、
面板开孔、材质、hitbox 和截图阈值的保真验收。

## P2：CardputerZero

### CZ-01

当前缺口：完整系统回归、USB split timing、网络性能/隔离、
摄像头/音频/电源/键盘 soak 和真机同路径。

## 发布门禁

发布或外部结论前至少完成：

1. 平台测试、runtime coverage、peripheral catalog、QEMU profiles 和
   project snapshot check；
2. 受影响设备组 targeted matrix；
3. 共享 QEMU/controller 变更时跑最新 full matrix；
4. 用目标 commit 和同主机架构重建 runtime；
5. 更新当前状态、验证台账、API/OpenAPI、专题页和发版说明；
6. 外部结论附 full-commit-SHA permalink，并明确
   `virtual-device validation` 或 `hardware validation`。
