# 项目 Backlog

日期：`2026-10-30`

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
- `RUNTIME-04` Core2 for AWS ATECC608 的 wake/Read/Info/CRC 初始化路径、确定性测试
  config、classic ESP32 DMA link/DC 修复和三次非空应用帧；
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
| 已完成（virtual-device） | Core2 legacy UIFlow startup | 共享 I2C、timer deadline、WDT level、stateful SSI、pending SPI remap、high-priority DPORT handoff、classic RMT 和 normal-WDT startup 已修复/验证；原厂 API Key startup UI 可稳定运行并进入真实 Wi-Fi Connect 页面 | startup PASS 不授予 setup/REPL、完整 factory application、任意用户程序或物理边界；这些更广覆盖转入 `API-01` |
| P0 | 网络产品化 | 物理跨主机 worker、主文件系统/队列/证据跨主机复制、任意 NAT 和外部 side-effect fence | 单机 namespace/container 和单个 control-plane evidence store 不能替代物理多机或对象存储 |
| P0 | Core2 物理/controller 等价性 | 更大规模、持续吞吐、active-stop/post-reset 之外 teardown、bit-exact controller 和物理 PSRAM/cache | 虚拟容量与物理时序不可互换 |
| P0 | 通用固件安全 | guest filesystem ACL、完整许可、真机安全配置和更多真实业务；service runtime ACL 已完成 | 静态声明、镜像摘要自洽、service ACL 不等于设备文件权限/trust |
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
[C/QEMU实验](qemu-wasm-port-research.md)。已满足的浏览器前置基线：固定
CoreS3 fixture、主 CPU jump 栈恢复、离线 profile、资源生命周期与既有正式
GitHub Pages 均有独立证据；本轮共享帧/host poll 修复和显式正常时钟 SDK
候选的限定结果见[性能与板型证据](evidence/2026-10-29-wasm-performance-devices/README.md)
及[LVGL 候选证据](evidence/2026-10-29-browser-lvgl-wallclock/README.md)。
原仓库正式站点与 fork 预览的验证版本分别记录在[Pages 指南](pages-deployment.md)；
部署不会自动跟随 main。剩余浏览器范围统一维护在 `UI-02`，不从原生设备矩阵或
编译板型表继承准入。

Cardputer 原 IRQ/四旋转与 StackChan 默认 UART/触摸并行的限定前置见
[本轮输入修复](evidence/2026-10-30-cardputer-stackchan-input/README.md)；继续扩展
更多固件、短按负载与长期稳定性，未取得的用户镜像和自然 PWR 回收仍独立开放。

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
经正常 TX/RX DMA 完成未加密双向 action-frame exchange。`0077` 随后用
显式 PMK/LMK fixture 在 bridge 边界执行 AES-CCMP/MIC；正确 key 双向交付，
错误 LMK 在 RX DMA 前丢弃，错误 PMK 但同 LMK 按官方语义继续通信。
完整 peer 生命周期与 RF/timing 仍由 `RUNTIME-06`
跟踪。
`0078` 又为单个 encrypted external peer 增加 CCMP PN 单调 anti-replay：
MIC 成功后拒绝 equal/older PN，并在 RX DMA 前丢弃；UDP replay proxy
重复一帧后只有一次 `CCMP PN replay` drop，正确 payload 与 Core2 回归保持。
随后 stock `espnow.ESPNow` lifecycle 在两个设备对完成 encrypted
add/delete/modify/re-add：删除后 `peer_count=[0,0]`、`get_peer` 与
`send` 均被拒绝，重新注册后恢复 `[1,1]` 和双向 payload。
`m5espnow.M5ESPNow` wrapper 也在同样两个设备对完成
`set_add_peer`/`set_delete_peer`/re-add：删除后 peer list 为空且
`send_data` 保持 no-op，重加后 peer list 与双向传输恢复。
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
  `0086` 随后修正 episode 诊断在 no-I/O TB 中读取 virtual clock 导致
  `Bad icount read` 的问题，并完成正常 WDT/WDT-off 两个同 SHA 10 秒
  freeze：`0x3ffbf2cc` 分别记录 `162/166` 个等待区间、累计
  `6.743/6.601 s`、最长 `483/581 ms`，最长连续失败尝试为
  `53/65`。BIN/控制流与 public ESP-IDF v3.3.5 匹配后，热锁是
  `xTaskQueueMutex`，主要 waiter 为 `xTaskIncrementTick` 和
  `vTaskSwitchContext`；第二热点是某个 `Queue_t + 76` mux。失败 CAS
  yield 在 10 秒把 task-queue 等待从 `6.601 s` 降到 `0.446 s`，但
  15 秒时 queue mux 等待从 `0.825 s` 升到 `4.534 s`，总 episode
  仍约 `5.4 s`，因此 normal-WDT reset 不变。下一步须取得 exact legacy
  ELF/MAP，区分 host-vCPU 调度延迟与 guest 长临界区；不能把 WDT-off、
  扩大超时、改变原子指令语义或局部 yield 当作修复。见
  [episode 证据](evidence/2026-10-29-core2-legacy-cas-episodes/README.md)。
  `0088` 随后用同一 QEMU binary 完成默认关闭的 contended-RR A/B：5 秒
  WDT-off 控制/候选的 CAS 为 `1,070,625→91,465`、跨核 contended 为
  `984,964→2,702`、episode time 为 `2.240→1.018 s`，而 SSI `0x05` 与
  `0xBB/64` 仅相差 8；说明 100 ms 单线程 RR 确实放大了 spin，而不是
  Flash 数据面变慢。候选仍无法阻止 normal-WDT 在 `17.248 s` 触发 TG0
  stage-1 reset，所以 `RUNTIME-03` 继续 OPEN。见
  [scheduler 证据](evidence/2026-10-29-core2-contended-cas-scheduler/README.md)。
  三次 `17.2 s` normal-WDT bounded-stack freeze 进一步把 CPU0 稳定绑定到
  `spi_flash_op_block_func` 等待循环，CPU1 则在 IPC/队列/调度路径间变化；
  同 binary 的 sampled trace 不能把 1024 分频后的 begin/end 当作同一
  transaction，新增 `--trace-sample` 显式控制后，短窗全量 trace 的 13 对
  事务均为同步 `0 ns`。下一步量化 per-operation CPU0 park time 与 CPU1
  启动阶段，而不是继续猜测匿名 vtable。见
  [IPC handoff 证据](evidence/2026-10-29-core2-ipc-handoff-attribution/README.md)。
  `0089` 随后修复 PC trace 在 no-I/O TB 中读取虚拟时钟触发的
  `Bad icount read`，并完成两次 50 秒 wall-time、normal-WDT 复测。固定版
  QEMU 在 reset 前记录 `12,645/12,693` 次完整 handoff；CPU1 block wait
  累计 `9.8519/9.8288 s`，约占 reset 预算 `57%`，单次最大仅约
  `6.7-6.8 ms`。下一项应降低正常 handoff 周期频率或单周期成本，而不是
  继续寻找一个不存在的长锁超时。见
  [episode budget 证据](evidence/2026-10-29-core2-handoff-episode-budget/README.md)。
  issuer 关联进一步表明 `8,234` 个 episode 中有 `6,806` 个各只有一条
  `0xBB/64` 和一条 status read，但“完全无 Flash 命令”的 episode 仍约
  `0.89 ms`；phase split 把单次主成本定位到 initiator 的 IPC 往返
  source shape（约 `0.616 ms`），而不是 64-byte 数据、直接 Flash 命令或
  cache-disable。`100 us` CAS quantum 和临时 `can_start` immediate-yield
  均无改善并已丢弃。`0090` 随后把双 vCPU deterministic `-icount` 的
  per-vCPU budget 默认限制为 `10 us`；同 trace A/B 把 initiator
  `can_start→IPC return` 从 `563.7 us` 降到 `56.2 us`、peer block wait
  从 `728.4 us` 降到 `184.7 us`，Core2 UIFlow2 设备组保持 `6/6 PASS`。
  最终 normal-WDT 仍在 `17.2429 s` reset 且没有 BOARD/APIKEY/REPL，因此
  下一项应继续解释其余 guest 工作预算，而不继续压 RR 参数；见
  [issuer/phase 证据](evidence/2026-10-29-core2-handoff-issuer-phases/README.md)
  和[per-vCPU budget 证据](evidence/2026-10-29-core2-icount-percpu-budget/README.md)。
  2026-10-30 的 timing sweep 进一步区分了“启动预算”和“启动后等待”：
  `shift=2` + `1 us` 在 normal WDT 下 `4.66 s` 到 BOARD/APIKEY、
  `8.50 s` 执行完原厂 boot.py；`shift=3` + `1 us` 分别约 `8.38/14.38 s`。
  两者都没有 factory UI，默认产品 lane 仍保持 `shift=5` + `10 us`。
  `shift=2` 的 WDT-off 15/20 秒快照均双核 Waiti，Flash/cache 最后活动在
  `9.36 s`，而 FRC timer 仍有 callback；UART 诊断栈位于
  `wifiWebCfg.py::_thread_task -> menu/wifi.py -> m5stack_ui.py:526`。
  下一项应解释 boot.py 后的 WiFi 配置/UI 线程等待，再检查 display flush
  completion。见[post-boot wait 证据](evidence/2026-10-30-core2-legacy-boot-to-ui-wait/README.md)。
  `0091` 另修正 TIMG watchdog stage timer 的 feed 重调度语义：
  `timer_mod_anticipate_ns()` 会保留更早的 pending deadline，不能在
  `WDTFEED` 后正确替换后续阶段。改用 `timer_mod_ns()` 后，同固件
  8 秒虚拟时点得到 `320x240`、`3,651` nonblack pixels 的 live frame；
  但长窗仍在约 `15.56 s` 触发 TG0 stage-1 reset，因此该修复只关闭
  watchdog timer replacement 子问题，`RUNTIME-03` 继续 OPEN。见
  [feed-reschedule 证据](evidence/2026-10-30-core2-timg-feed-reschedule/README.md)。
  同一 diagnostic QEMU 上，仅把 `wifiWebCfg.config_by_web` stub 为返回
  true，就得到完整 `320x240` UIFlow App/Flow/Setup 菜单帧（`76,760`
  nonblack pixels、`417` colors）。原厂镜像的专用 `wifi` 分区为空，
  因此剩余原厂路径是提供有效 WiFi 配置并重跑真实 `wifiWebCfg`/WiFi
  UI 生命周期，而不是继续修 display/LVGL。见
  [WiFi stub 菜单证据](evidence/2026-10-30-core2-wifi-stub-menu/README.md)。
  Core2 `qemu-wifi` 随后增加严格的 legacy `deviceCfg` overlay：只处理
  session Flash 副本中的 `config` 分区，校验 schema、长度和 checksum，
  记录 hashed SSID/base/effective SHA，其他固件逐字节不变。service 产物与
  诊断使用的 effective Flash 相同；诊断控制可显示真实
  `Connecting to myssid`，默认 WDT 仍在 boot 后触发 cache-disabled panic。
  因此这是配置/取证里程碑，`RUNTIME-03` 继续 OPEN。见
  [legacy WiFi config 证据](evidence/2026-10-30-core2-legacy-wifi-config-overlay/README.md)。
  `0092` 接着把 DPORT 的 per-CPU instruction-cache-ready 状态送入
  INTMATRIX，在 cache disabled 窗口只暂存 WiFi MAC level，恢复后重放；
  cross-core、timer 和 cache-illegal source 不受门控。默认 budget 的
  normal-WDT 会话不再出现 cached ISR panic，并渲染原厂 API Key 页面，但
  随后仍进入 TG0 WDT reset。因此 cache/WiFi IRQ 子问题已修复，稳定
  startup、setup/REPL 和应用帧继续 OPEN。见
  [WiFi IRQ cache gate 证据](evidence/2026-10-30-core2-wifi-irq-cache-gate/README.md)。

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
二进制入口须按`UNIT-HOST-33`先取得固件run-as-main/loader路径；普通`.mpy`导入不具备完整脚本入口语义。1.44已分开二进制checkpoint存储与执行，四host双lane旧Run保护已验；1.45严格显式base与CoreS3候选loader固定SHA的模块身份/重复Run/异常/Ctrl-C已取得限定guest诊断，1.46已接有条件公共入口且CoreS3 stock/兼容固件及Web通过，继续更多固件/主机、reset/重连后能力恢复与完整清场；FlashLight cold constructor已按[四host证据](evidence/2026-10-29-flashlight-cold-route-four-host/README.md)闭合，实时Web轮询、动态S1、PWM和完整controller边界仍开放。4Relay/FlashLight新协议冲突与模型边界见[本块证据](https://github.com/m5agent/m5stack-esp-emulator/blob/a37342f61c05964c060719a6e35c2d568c828e84/docs/evidence/2026-10-27-binary-checkpoint-admission/README.md)。
FlashLight的OUT_SEL旧资格问题已按[限定路由证据](https://github.com/m5agent/m5stack-esp-emulator/blob/a37342f61c05964c060719a6e35c2d568c828e84/docs/evidence/2026-10-27-flashlight-route-history/README.md)闭合；`0047` cold constructor/低基线已由新runtime四host原厂API、同PID Run替换和actual QOM Web replay验证；`UNIT-HOST-37`关闭该数字边界。`UNIT-HOST-36` Relay/Relay2 hard-reset数字边界已另按[0087 fixed/pre-fix](evidence/2026-10-29-unit-hard-reset-output-boundary/README.md)闭合；FlashLight实时Web、S1/PWM和电气边界继续开放。
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

`RUNTIME-03` 的 stock startup 已在 virtual-device scope 关闭；
setup/REPL 与任意 legacy application 继续由 `API-01` 覆盖。其余 P0 按以下
顺序推进：

1. `NET-04`：把已验证的单机 worker 边界推进到物理跨主机和完整 side-effect
   ownership。
2. `CORE2-02`：当前工具 hash 的双实例回归已重绑；先完成当前高负载
   宿主条件下的八实例 cold-start 重绑；
   九实例需先修复 `ble_hs_hci_process_ack` 竞态，再补持续吞吐、其他
   teardown 和物理/controller 等价性。
3. `FW-01/02/03`：补 guest filesystem 权限/完整许可、真机安全配置和真实业务覆盖。
4. `RUNTIME-02`、`HW-01`：补 C6 Zigbee 生命周期和代表设备真机同路径。
5. `SVC-01/02/03`、`TAB5-01`、`UI-01`、`CZ-01`：服务化和专项收尾。

## 依赖与并行原则

| 类别 | Task | 开始条件 | 与其他工作的关系 |
| --- | --- | --- | --- |
| 立即可做 | `FW-01`、`FW-03`、`SVC-03`、`UI-01` | 当前仓库、测试和本地 runtime 可用 | `SVC-03` 先做无语义移动并保持 API/evidence 契约 |
| 需要多机环境 | `NET-04`、`SVC-01`、`SVC-02` | 至少两个可失联、可 drain、可独立寻址的执行节点 | `SVC-01/02` 的跨主机部分依赖 `NET-04`；单机 namespace/container 结果不能替代 |
| 需要真机或外部控制面 | `FW-02`、`HW-01` | 同固件 SHA 的设备控制、串口、画面、网络和外设观测入口 | `FW-02` 还必须取得 live eFuse/生产 key 流程授权；静态镜像分析不能代填 |
| 后端阻塞 | `RUNTIME-02` | 可重建 802.15.4 MAC 路径，或公开固件匹配 ELF | 在 blocker 消除前保持 `PARTIAL`/`runtime_model_gap`，不承诺完整兼容 |
| 决策或独立后端 | `TAB5-01`、`CZ-01` | P4 backend 重建/扩展决策；CardputerZero Linux 回归资源 | 不继承 S3/C6/Core2 的完成度，可与主线并行 |

## 可执行任务板

| ID | 状态 | 下一项最小交付 | 验收 |
| --- | --- | --- | --- |
| `API-01` | 进行中 | 接续 stock SDK/绑定失败、WDT warm reboot、native build feature、未实现控制器与未选外设；扩展 Cardputer-ADV Unit 准入及同固件更多行为域；继续补 legacy Core2 setup/REPL 与任意 factory application。`0074` 已关闭 Core2 candidate M5UI frame routing/oracle；Core2 stock BLE NUS 在 native-HCI 上完成 session-readiness 与 peer write settle 后由多轮独立 service lease 复核，`Server.get_client` 已有 hash-pinned 候选修复；StopWatch/StickS3 stock controller 仍开放 | 保留失败负控；stock/matching/candidate 分 lane，具体行为/控制器数据与 session/固件/runtime/串口/帧/ZIP/清理绑定，不能用审计数量或局部通过关闭全部接口/硬件范围 |
| `RUNTIME-03` | 已完成（virtual-device stock startup） | `0065` 关闭 high-priority DPORT handoff 调度死锁，`0066` 补 classic RMT，`0068` 将 legacy HSPI/SPI2 与 UIFlow2 VSPI/SPI3 都接到同一 panel sink，`0069` 修正 protected `WDTFEED` 语义；`0071/0072` 精确得到 `0xBB/64 -> 0x05/1 -> 0xBB/64` 主循环；`0073` 绑定主要 issuer；`0075` 排除 RDSR WIP/busy 错误并把成本定位到 scheduler/list 跨核锁竞争；`0086` 修正 episode 诊断的 `Bad icount read`，将热锁结构匹配到 `xTaskQueueMutex`/queue mux；`0089/0090` 完成 icount-safe phase trace 与双 vCPU fairness cap；`0093/0094` 修复 classic WiFi virtual time、station 双向数据面和 Service SSID/auth 传递；`0095` 修复 legacy task-WDT level delivery，三次 normal-WDT service 运行稳定到 guest virtual 300 秒以上 | DPORT 协作、classic RMT、dual-SPI、stateful SSI、pending SPI remap、protected WDT feed、0071-0073 transaction/issuer profile、0075 status/CAS 关联、0086 episode profile、0089/0090 IPC budget、0092 cache gate、0093/0094 classic WiFi data plane、0095 WDT level 和 Core2 设备组保持可重放；setup/REPL 与任意 legacy application 转 `API-01` |
| `RUNTIME-06` | 已完成（virtual-device） | `0067` loopback、`0076` plaintext、`0077` CCMP、`0078/0079` replay window、native/M5ESPNow lifecycle、`0080` key-state、`0081` shared-LMK fabric、`0082` per-peer routing、`0083` PN exhaustion/rekey 与 `0084` loss/retry/channel/rate/60 秒 soak 均已完成 | fixture/guest-key、shared-LMK/per-peer-key、replay、cross-wire、PN exhaustion、loss 和 channel/rate 分 lane 保留；bit-exact controller/RF/电气/真机继续独立登记，不回写为已完成的物理结论 |
| `NET-04` | 进行中 | claim response-loss idempotency 与 lease-bound central evidence store 已完成；继续物理跨主机 executor/reattach、queue/session/evidence 跨主机复制、任意 NAT、QEMU 内 guest/controller 和外部 side-effect fence | 跨主机 job 可迁移、重放、接管和清理；claim/evidence response 丢失不重复写入；跨主机节点无法共享同一文件系统时仍能读取确定性证据 |
| `CORE2-02` | 进行中 | post-reset teardown 已完成；当前 `origin/main` 工具 hash 的双实例回归已重绑。继续在没有宿主过载的条件下重绑八实例 cold-start；九实例两次通过、一次在 `ble_hs_hci_process_ack` panic，先修复该竞态后才可重开。随后补持续吞吐、更复杂 teardown、bit-exact controller/baseband、物理 PSRAM/cache timing 和真机 | 结果绑定固件/ELF/QEMU/工具哈希；九实例不得通过放宽 timeout/floor 或忽略单次 guest panic 准入；虚拟容量不外推为物理等价 |
| `FW-01` | 进行中 | operator-owned runtime ACL/执行策略已完成；继续 guest filesystem 权限、完整源码和依赖许可覆盖、法律审批 | 镜像属性、service ACL 与 guest runtime 分开；unknown 不写成 PASS |
| `FW-02` | 进行中 | 真机 Secure Boot、Flash Encryption、live eFuse、bootloader anti-rollback 和生产 key | 测试/生产 key 不入库；安全状态可审计 |
| `FW-03` | 进行中 | 真实 key/云端业务；更多设备与 firmware family；继续扩展 SD/NVS 和网络预期 | 导入、capability、boot、输入、功能和网络分层记录 |
| `RUNTIME-02` | 进行中（backend blocked） | C6 802.15.4 MAC ACK/commissioning 和 join/收发/离网生命周期 | 真实 guest 驱动完成生命周期；否则保持显式 `runtime_model_gap` |
| `SVC-01` | 进行中 | namespace-managed/Tab5/cross-host companion 和跨主机 session/evidence 持久性 | 重启后接管或明确失败，不产生假 running；claim response-loss 已由 durable queue 覆盖 |
| `SVC-02` | 待做 | warm pool、配额、对象存储、审计和容量指标 | 租户状态隔离，资源与 GC 可观测 |
| `SVC-03` | 进行中 | `ServiceError`、首批无状态 parser、QEMU/runtime 内存策略、私有 env 脱敏、network policy/CNAME parsing、设备规格/profile 加载、storage/NVS、esp-emu network execution 和 QEMU WiFi security/env 已移到独立模块并由 `device_service.py` re-export；继续提取其余请求解析/运行参数，再拆 store、runtime adapter、evidence collector 和 session 状态机 | 每一步只移动一个边界；对外 API、历史恢复和 evidence 字段不回归 |
| `HW-01` | 待做 | 代表设备的同固件 SHA 真机测试计划 | evidence 明确标为 hardware validation |
| `TAB5-01` | 决策 | 重建或扩展 P4 backend | 缺失控制器与端到端网络有执行路径 |
| `UI-01` | 待做 | 逐设备结构、材质、hitbox 和截图阈值 | 设备本地视觉回归，不跨设备继承 |
| `UI-02` | 进行中 | 继续归因正常时钟候选的触摸延迟与 CPU 开销，补 stock SDK 第一层 C Timer coalescing、异常路径、长期稳定性和 Flash 持久化；已准入固定示例的 Xtensa 板型继续扩展应用与长期验证，保留 PaperMono stock 逻辑校准、StopWatch 触摸偏差及 Cardputer IRQ/chord/CFG1 时序边界；C6 RISC-V 浏览器构建、P4 可用 backend 与 Linux ARM64 浏览器执行分别立证；继续扩展 StackChan 其它 Arduino/UIFlow 固件、零位和连续转动模式；补 Plus2 浏览器 USB sleep、显式 EXT0 唤醒及 RTC CRC 等价性，并继续经典 Atom/Stick 的真实浏览器准入；扩展固件/Unit，Rust 演示保持研究原型 | 精确绑定完整 Flash SHA、runtime/profile 和单板真实输入/帧；native PASS、compiled_profiles 和正常时钟候选不能授予其它板型或 stock SDK PASS；保留旧 div8 示例/分享兼容及取消/停止契约；静态构建不含凭据/固件/raw；本轮新版本部署后另验正式 HTTPS |
| `UNIT-01` | 进行中 | 其余同guest Unit（issue #5–#8 已补控制器路径，仍需更广固件/主机矩阵）、FlashLight实时Web与动态S1/PWM、更多主机/固件的二进制入口验收与保存开机程序；AIFlow checkpoint/虚拟目标、Preview后续恢复与GC、SSE/实时分发；程序revision引用保留/有界回收；Tab5 GDB frame生命周期与其它后端取消场景实际会话验证；其它准入主机/固件的实际源码API执行、ADC2 oracle与Thermal fixture、新HUB拓扑、原IR GC/原Buzzer、完整PWM周期、Heart生理算法及视觉缺口；Scroll的TIM回绕、RGB多槽队列、轴角/方向标定、bootloader/Flash持久化与地址0；Roller485协议与功能准入 | 新固件重新验证；逐型号同guest读写、Web输入/输出、可见session和evidence；未准入组合不能凭离线产物升级；分次帧不假称原子一致，可读性不外推所有UI；Core2 IMU偶发marker保留独立完整轮，不以单例补PASS；主机问题单独记录，不以诊断、custom guest或桥契约替代原固件结论；真机同路径另验 |
| `CZ-01` | 待做 | CardputerZero 系统、驱动和长期回归 | 启动、USB、网络、音频、摄像头和真机边界明确 |

## P0：Core2 legacy UIFlow 运行时

### RUNTIME-03：已完成（virtual-device stock startup）

已满足的前置基线：shared I2C、equal-deadline timer、WDT level、stateful
SSI、handoff timeline/state sweep/setter trace、三次 WDT liveness、
pending SPI remap、high-priority IRQ 协作和 classic RMT 均可重放。

上述结果都没有把 legacy 固件变成产品 PASS。精确时间线、哈希和检查数只在
[验证证据台账](validation-ledger.md)；缺口语义见
[运行时模型缺口登记](runtime-model-gap-register.md)。

历史阻断与关闭依据：

- service-form functional lane 必须使用 `runtime=qemu-wifi`。早先默认
  `runtime=qemu` 的直接诊断没有 `misc.esp32_wifi`，guest 可能在
  `0x60033d24` 的 WiFi DMA status alias 上等待无设备状态，不能单独作为
  legacy 启动或黑帧根因证据；
- 通用 LittleFS 会被 legacy guest 拒绝并重新格式化。使用 UIFlow
  checkout 自带 LittleFS2 packer 后，`qemu-wifi` 120 秒已执行注入的
  `/flash/boot.py` 并输出 `CORE2_LEGACY_VFS_BOOT`，但 setup/main 仍未出现；
- normal-WDT 已由 `0095` 解除：同一 public legacy SHA 的三次独立
  Device Service 运行均越过原 stage-1 reset，完成 boot markers 和至少一次
  reconnect lifecycle，稳定到 guest virtual `300 s` 以上并保持原厂 API Key
  startup UI；setup/REPL 和完整 factory application 转 `API-01`；
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

独立后续覆盖（不阻塞 `RUNTIME-03`，转入 `API-01`）：

1. 取得 public `UIFlow_Core2 v1.15.4` 的 matching ELF/MAP。byte audit 已证明
   local UIFlow2 v2.5.3 ELF 不能用于符号命名；
2. 在 matching LittleFS2 VFS 与 `runtime=qemu-wifi` lane 重新观察旧
   `0x40100049` BIN-bound LVGL wait；修正后的 120 秒点未复现该地址，
   不能把旧对象/寄存器结论直接继承为当前第一失败点；
   `0071/0072` 已给出完整 command/RX-length/gap、联合键、per-command gap
   和 transition 分布；`0073` 已绑定主要 issuer PC，`0075` 已排除
   RDSR busy 位并定位到 scheduler/list 跨核锁竞争；`0086/0088` 已证明
   单线程 RR 的 100 ms quantum 会放大 spin，但缩短 contended quantum
   不能单独解除 normal-WDT reset，最终由 `0095` 的 WDT level delivery
   修复越过。下一步用相同 lane 进入 setup/REPL，并结合 matching symbols
   与 tick/IRQ rate 解释剩余 application lifecycle；
3. 保持 `0064` 的 pending SPI remap、`TRANS_DONE && TRANS_INTEN` 与 guest
   callback 回归；`0093/0094` 已让 classic station DHCP、双向 host 数据和
   Service SSID/auth 走正常路径，stock Core2 WiFi 五轮首启动 PASS，且
   legacy WDT-off 可稳定到 API Key 页面；下一项是在 normal WDT 下解释
   boot done 后仍无新的 TG0 feed，再决定源码启动修复与 display
   completion/`lv_disp_flush_ready` 的顺序；保留 `0036` stateful SSI
   数据面，不使用 `blk_pread` bypass；
4. 保留 `0095` 的三次 normal-WDT 中断链证据；不再把 TG0 stage-1 reset
   当作当前 blocker，后续时间线用于 setup/REPL 和 application phase；
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
- normal-WDT 的 `INT_ENA=2/int_raw=4/level raise/WDTFEED/INT_CLR`
  中断链在三次独立运行中可重放且不进入 TG0 stage-1；shared bus、TIMG
  trace 和 Core2 UIFlow2 外设组回归保持 PASS；`0065`/`0066` 契约继续可重放；
- BIN-bound trace 能解释 display flush callback、SPI completion 和
  LVGL `flushing` 清零关系；setup/REPL 与 application lifecycle 分开记录；
  matching ELF/MAP 若取得则只能提高符号置信度，不能替代运行证据。

## P0：网络与 worker

### NET-04

已满足的前置基线：durable queue、HMAC、TLS/mTLS、发现、同机 reattach、
container-local QEMU、409 ownership fence 和 worker-owned companion
partition fence 已进入状态页与台账。真实 HTTP/WorkerAgent 路径也已证明：
committed claim response 被客户端丢弃后，同一 identity-bound
`claim_idempotency_key` 可跨 control-plane restart 返回原 job/lease；
第二个 queued job 不被误领，异请求与 expired lease fail closed，raw key
不写入 `jobs.json`。真实 WorkerAgent 还可在结果上报前把多 MiB evidence
ZIP 上传到 HMAC-authenticated、job/lease/generation-bound 的中央内容寻址
store；丢失上传 response 后同 bytes 重试返回原 evidence ID，不同 bytes
返回 409，metadata/content 跨 control-plane restart 可读，result 必须匹配
同一 evidence ID + SHA256。

开放范围：

- 物理跨主机 worker、QEMU executor、迁移、reattach 和持续 evidence 流；
- queue/session/evidence 的跨主机复制/对象存储、共享文件系统之外的持久性
  与旧 lease result fence；
- 无 reachable discovery seed 时的任意 NAT traversal；
- QEMU 内 guest/device-controller 状态和 worker 未拥有的外部 side effect；
- namespace-managed、Tab5 和 cross-host companion recovery；
- 生产容量调度、对象存储、审计和 warm pool。

验收：

- worker 强杀、重启、失联、迁移和 drain 都有确定终态；
- 任务、worker generation、QEMU PID/start time、lease 和 evidence 可关联；
- ownership 无法确认时停止可达 runtime，拒绝 stale result，不产生假
  running；
- claim response 丢失、服务重启和同 key 重试保持原 job/lease，不能分配
  第二个 job；
- evidence 上传 response 丢失、control-plane restart 和同 bytes 重试返回
  原 evidence ID；异 bytes、旧 lease 或错误 result binding fail closed；
- 物理多机与单机 namespace/container 结果分层记录。

## P0：Core2 controller 与物理边界

### CORE2-02

已满足的前置基线：`core2-native-hci`、WiFi/公网/GATT、QOM 8 MiB PSRAM、
upper-bank MMU、重连、长稳、active-stop、post-reset stop；当前 `origin/main`
工具 hash 的双实例回归已重绑。九实例两次通过、一次在 ACK 路径 panic，
已明确拒绝。精确结果只在验证台账和
[当前工具 hash 重绑](evidence/2026-10-30-core2-toolhash-rebind/README.md)维护。

开放范围：

- 大于当前服务单设备容量；
- 持续吞吐以及 active-stop/post-reset 之外更复杂的 teardown 模式；
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
镜像可见权限、SBOM/SPDX 和有界许可 allowlist/denylist 可执行；Device
Service API `1.51.0` 增加 operator-owned runtime ACL，对 serial/input/reset、
program execute/interrupt/read、package write 和 flash read 按设备 fail closed，
入口点与 guest package 路径另有 allow/deny 规则，policy hash 和有效权限进入
session/capacity；未配置时显式保持兼容模式。

开放范围：

- 固件自身/guest filesystem 的运行态 ACL、权限和不可变策略；当前 1.51
  policy 只约束 Device Service 管理的 guest-facing 操作，不是任意 native
  firmware 沙箱；
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

`0077-esp32-espnow-external-ccmp.patch` 在 bridge 边界补上真实 AES-CCMP：
PMK 以 AES-128-ECB wrap LMK，controller 状态不保存 plaintext LMK；TX 去掉
guest hardware envelope 后以新 PN/8-byte MIC 加密 action body，RX 在正常
DMA 注入前验证 MIC。StopWatch↔StickS3 与 Core2↔StopWatch 的正确 key、
错误 LMK 和 wrong-PMK/same-LMK 场景均完成；错误 LMK 两个方向的
`rx_packets=0`。PMK/LMK 从 API/persisted session snapshot 脱敏。该实现仍是
外部 key fixture，不证明 guest `set_pmk`/`add_peer` 已把 key-state 写入
controller。

`0078-esp32-espnow-external-ccmp-replay.patch` 为当前单 peer lane 保存
最后一个 MIC 成功的 CCMP PN；equal/older PN 在正常 RX DMA 前丢弃，
authentication failure 不推进 state。StopWatch→StickS3 的 UDP replay proxy
在两个方向均开始通信后重复一帧，StickS3 记录一次 replay drop，guest
payload 仍为正常唯一帧数量；wrong-LMK 和 Core2 encrypted 回归保持。

`0079-esp32-espnow-external-ccmp-window.patch` 将严格 monotonic guard
升级为 64-frame bitmap。新 PN 推进窗口、window 内未见 older PN 接受一次，
duplicate 和窗口外 PN 丢弃。UDP ReorderProxy 交换两帧后 receiver
`replay_drops=0` 且双向 payload 保持；duplicate replay 仍记录一次 drop，
Core2 encrypted 回归保持。

`0080-esp32-espnow-guest-key-state.patch` 映射 classic ESP32 与 ESP32-S3
WiFi crypto key store。external bridge 未配置 PMK/LMK fixture 时，guest
通过 stock `set_pmk`/`add_peer` 写入的 extended key slot 只有在完整
16-byte LMK 和 controller valid bit 都到达后才被采用；delete、
re-add/modify 和 key replacement 会重置 active key/replay state。两设备对
均在不传 runtime-env key 的情况下完成正控，不同 guest LMK 两端均
`rx_packets=0`，轮换到新共享 LMK 后 post-resume 交付恢复。

`0081-esp32-espnow-peer-fabric.patch` 完成三 guest shared-LMK fabric：
StopWatch、StickS3 和 Core2 各自在加密前写入 synthetic public MAC，连接
同一个 IPv4 loopback UDP broker；broker 不再于 CCMP 后改写 transmitter 或
address3。three-peer 正控中三端 `peer_count=[2,2]`，各自收到另外两个 peer
的 payload。replay window 按 authenticated source-peer MAC 分片，共 8 个
slot、每 slot 64 frame；负控重复一帧真实 forwarded frame 后只有目标
StickS3 记录一次 drop，其它两端为 `0`，三方正常 payload 保持。

`0082-esp32-espnow-per-peer-key-routing.patch` 根据 stock
`hal_crypto_set_key_entry` 写入的 key-entry metadata，把 entry bytes `0..5`
识别为 peer MAC、`8..23` 识别为 LMK。fabric TX 按 receiver peer、RX 按
transmitter peer 选择 guest key，并为每个 key slot 保存独立 TX PN。三个
不同 pairwise LMK 的六条 directed path 全部交付；cross-wire 负控只把 B 对
A 的 LMK 改成 B-C 的 key，broker 仍转发全部路径，但 A↔B 双向归零，A↔C
和 B↔C 保持。direct guest-key pair 回归也通过。

`0083-esp32-espnow-ccmp-pn-exhaustion.patch` 禁止 48-bit CCMP transmit
PN 从 `0xffffffffffff` 回绕到 zero。测试 seed 从上限前 64 帧开始，
正常 encrypted barrier 后 burn 到 exhaustion；相同 LMK 重写保持 PN/
replay 状态，后续 payload 为 `0`。安装新 LMK 后 PN 从 zero 重启并恢复
双向 payload。shared-LMK、pairwise 正控和 B/A cross-wire 回归保持。

原生 `espnow.ESPNow` lifecycle 场景在 StopWatch↔StickS3 与
Core2↔StopWatch 完成 encrypted `add_peer`、pre-sync、`del_peer`、
`get_peer`/`send` NOT_FOUND 负控、`add_peer`、`mod_peer` 和 post-resume
双向 payload。runner 在第一次收到 peer PRE 后继续广播 1.5 秒，避免较慢
Core2 在另一侧先删除时看不到回向 PRE；首轮一方向 `pre_synced=false`
保留为 ignored failure control。

`m5espnow.M5ESPNow` wrapper 同样在两个设备对完成 `set_add_peer`、
`set_delete_peer`、peer list/count 清空、delete 后 `send_data` no-op、
re-add 和 post-resume。wrapper 在 delete 后有意静默跳过发送，与 native
`send` 的 `OSError` 行为分开记录。

`0084-esp32-espnow-loss-channel-rate.patch` 在真实 action frame 外增加
8-byte channel/rate envelope，RX 在 CCMP/DMA 前校验 envelope。受控 UDP
proxy 丢弃 StopWatch→StickS3 前两帧后，应用重试恢复双向 payload。两端
切换 home channel 6 后正控 PASS；channel 1↔6 两端各记录 40 次 drop，
正常 RX packet 为 `0`。channel 6 上 11/24 Mbps 混合发送时，接收端
metadata 互见对端 rate。60 秒 soak 中 A/B TX/RX 为 `528/527` 与
`527/528`，payload matches 为 `526/527`，duplicate、unexpected source
和 TX error 均为 `0`。direct encrypted、replay、reorder、三 guest
shared/pairwise fabric、cross-wire 和 PN rekey 回归保持。

虚拟验收已关闭。仍独立保留：

- bit-exact controller、RF/antenna 和电气时序。

验收：external plaintext 与 encrypted lane 分开记录，不能在 Python 中合成
payload、CCMP 或 callback；encrypted lane 必须使用实际 key-bound
controller 路径并包含错误 key 负控。`0077` 已满足 fixture 路径，
`0080` 已满足单 peer stock guest key-state 与 rotation，`0081` 已满足
shared-LMK 三 guest fabric 与 per-source replay，`0082` 已满足 per-peer
LMK routing 与 cross-wire fail-closed，`0083` 已满足 PN exhaustion 和
same-LMK fail-closed，`0084` 已满足 loss/retry、channel/rate 和 60 秒
soak；`RUNTIME-06` 的 virtual-device 边界已完成。物理 RF/controller
等价性仍按独立 gate 记录。

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

1. 已固定 `ServiceError.payload()`、当前 parser 行为及 public re-export，并由
   `test_device_service_parsing.py` 锁定；
2. 已移动 `parse_int`、`parse_size`、`parse_capture_pcap`、SHA256 检查、
   QEMU/runtime 内存策略和私有 runtime env 脱敏；生产 Core2 unified
   service path 已在同一变更中完成三次重绑，并修正 QOM readiness 与 peer
   write settle。2026-10-30 又移动 network policy 与 CNAME 解析到
   `device_service_network.py`，并把设备 catalog/matrix/profile 解析、
   backend 路径和 runtime profile 选择移到 `device_service_specs.py`；
   storage/NVS execution request parser 已移到
   `device_service_execution_parsing.py`，esp-emu network execution request
   parser 已移到 `device_service_network_execution.py`，QEMU WiFi security
   parser 与 environment projection 已移到 `device_service_qemu_wifi.py`。
   五个边界均由原模块 same-object re-export。继续移动其余无状态请求解析
   和运行参数构造，保持原模块 re-export；
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

当前视觉库存为 38 款主机，包含本轮新增的完整 Atom/Stick 系列及 Dial、Basic；
24 款有运行登记，其余 14 款仅模型，不能提示连接服务即可运行固件。
固定来源、配置及验收见[新增主机计划](plans/2026-10-29-expanded-host-models.md)。
本轮 AtomS3/Lite、StickC/SE/Plus2 的原生显示或 LED、输入及选定外设已有
[限定验证](evidence/2026-10-29-expanded-hosts/README.md)，浏览器逐板准入独立维护。
经典 Atom 三板官方固件启动与原 StickC Plus 准确镜像已有独立原生和浏览器上传
固定示例证据，见[后续验证](evidence/2026-10-29-motion-command-followup/README.md)。
StackChan 正常长按已到 guest SHUTDOWN/exit0，但最终自然关机仍有一个 engine
CDP target 残留；需补 owner 最终回收兜底，并在关闭浏览器上下文前独立验证
全部 Worker 归零。本轮 Arduino 屏幕/舵机并行的普通 Stop 也有预算内 engine
target 未消失，后续 case 累计归零不能关闭首次失败。一次原样 Dance 启动出现 PSRAM/OOB，后续通过不能关闭
该偶发问题。原 StickC Plus 默认入口的首次超时虽有同镜像后续通过，
仍需定位启动时序并验证稳定性。还需用实际短间隔命令验证中途改目标，不能用超过原动作时长的
两次目标变化替代。
继续绑定 Matrix stock 固件的 IMU 轴向语义、非均色灯阵链序、Dial 旋钮稳定投送，
以及已启动设备未覆盖的音频/IR/电源/网络等数据面；不能以编译或另一板 PASS 关闭。
其它 14 款视觉主机按实际芯片、板修订和准确固件逐个接入，StickV 的 K210、
StickT2 等异构芯片不使用 ESP32 alias。

加载失败时保留原 renderer 回退；StopWatch 仍是唯一参考质量外壳。
模型接入不替代逐设备结构尺寸、
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
