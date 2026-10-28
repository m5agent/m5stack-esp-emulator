# 项目当前状态

日期：`2026-10-29`。Unit 历史 PASS 精确绑定旧固件/运行时，raw 归档已外置，读取规则见[证据说明](evidence-retention.md)。

本文是当前能力和边界的权威说明。当前未完成工作只在[项目 Backlog](project-backlog.md)维护，逐次运行与 evidence 只在
[验证证据台账](validation-ledger.md)维护，设备/Task 计数由
[自动项目快照](project-snapshot.md)生成。代码阅读顺序见
[工程交接总览](engineering-handoff.md)，工作流归属见
[工作流总台账](workstreams.md)，源码与测试入口见
[代码与验证入口地图](code-map.md)。

## 一页结论

UIFlow 实时执行在原 MicroPython VM 经UART REPL部署运行，首次初始化后不重复刷固件；AIFlow/Agent使用Preview/checkpoint/Run协调，普通非托管会话保留`/program`。四款准入主机的
PIR/Relay 已验证同 PID/固件/VM、原驱动、应用帧、循环替换与 SyntaxError 恢复。
真实 CoreS3 Web 编辑器另验证双向输入/输出和实际帧像素送达屏幕，见[既有程序证据](https://github.com/m5agent/m5stack-esp-emulator/blob/a37342f61c05964c060719a6e35c2d568c828e84/docs/evidence/2026-10-26-live-program-web-and-hosts/README.md)。
CoreS3/AtomS3R/StickS3/StopWatch 的 HUB 下 ENV III/NCIR/TVOC 与
Encoder/8Encoder/Joystick v1.1 已验证同 guest 原驱动、独立leaf输入、I2C/QOM和guest LED写回，见[本轮证据](https://github.com/m5agent/m5stack-esp-emulator/blob/a37342f61c05964c060719a6e35c2d568c828e84/docs/evidence/2026-10-26-live-unit-preview/README.md)。
QEMU 新增显式 `max_age_ms=1..1000` 的按需共享帧样本和 ETag/304；默认 GET、
evidence、wait 与 stop 仍采集新帧。无后台采样或固定FPS保证，Tab5/network不继承。
时间与程序身份冻结于真实采集，preview样本序号不代表guest重绘或与Unit状态的原子快照；真实CoreS3的条件请求、程序/重置失效、历史和导出边界已验收。
独立有界帧请求与owner/decode隔离、CoreS3 PIR/Relay共享帧与双向控制已验；六leaf另有CoreS3真实网页输入/DOM读回。RGB/Encoder/8Encoder默认全灯同色反馈按排列不变性实现，非对称/不可用时撤色并标unknown；逐灯与旋转binding仍为UNIT-HOST-29 OPEN，范围见[本块证据](https://github.com/m5agent/m5stack-esp-emulator/blob/a37342f61c05964c060719a6e35c2d568c828e84/docs/evidence/2026-10-26-uniform-led-and-program-capabilities/README.md)。
`/program`支持完整文件/资源和纯字节码`.mpy`依赖，同guest校验发布与托管模块替换；公共完整checkpoint保存/查询及同步revision引用已实现，串口按offset只读有界窗口。program_features明确main.py/fresh-globals/interrupt-only；普通导入不运行if-main，1.44可保存/读取main.mpy checkpoint，四主机双lane拒绝不打断旧程序已验；1.45显式manifest base沿传安全/能力/PSRAM并拒绝CAS来源冲突，CoreS3候选loader同VM重跑/异常/Ctrl-C/PIR诊断已验，1.46受控bootstrap真实bytecode canary后有条件开放main.mpy，gen45 CoreS3 stock保护/兼容固件ordinary与真实Preview Web共14执行（8MPY）已验；gen46最终恢复门禁另验2会话9执行（5MPY），最终平台1218项通过；默认stock仍false，更多固件/主机及完整清场按UNIT-HOST-33继续，见[公共入口验收](https://github.com/m5agent/m5stack-esp-emulator/blob/a37342f61c05964c060719a6e35c2d568c828e84/docs/evidence/2026-10-27-public-main-mpy/README.md)、[入口研究](https://github.com/m5agent/m5stack-esp-emulator/blob/a37342f61c05964c060719a6e35c2d568c828e84/docs/evidence/2026-10-26-uniform-led-and-program-capabilities/main-mpy/README.md)、[文件包证据](https://github.com/m5agent/m5stack-esp-emulator/blob/a37342f61c05964c060719a6e35c2d568c828e84/docs/evidence/2026-10-26-live-package-and-detent/README.md)和[当前块](https://github.com/m5agent/m5stack-esp-emulator/blob/a37342f61c05964c060719a6e35c2d568c828e84/docs/evidence/2026-10-26-visual-refresh-and-checkpoints/README.md)。
FlashLight U152为partial GPIO/虚拟时钟模型：0046/3f1617的四host路由历史与CoreS3 Web限定验收保留，旧完整矩阵66/67、Core2 IMU仍OPEN。0047补真实pad连续观察与无假边沿冷复位，C组合已验；首候选的CoreS3显示/电源回归已定位为软I2C缺显式上拉，修复及必要验证见[本轮收尾](https://github.com/m5agent/m5stack-esp-emulator/blob/a37342f61c05964c060719a6e35c2d568c828e84/docs/evidence/2026-10-27-flashlight-cold-pad/README.md)。该旧轮未跑新FlashLight四host API/Web；本轮新完整矩阵见下方审计，37/36及动态S1/PWM/光度/真机不关闭。Scroll原驱动/Web按键/RGB/屏幕保留[限定验收](https://github.com/m5agent/m5stack-esp-emulator/blob/a37342f61c05964c060719a6e35c2d568c828e84/docs/evidence/2026-10-26-scroll-controller/README.md)，RGB队列、轴角、回绕、bootloader/持久化仍开放；其它Unit、更多主机/固件main.mpy、保存开机、Preview恢复/GC、SSE与AIFlow目标继续按[评估计划](plans/2026-10-26-aiflow-live-preview-api.md)维护待办。本轮按用户要求收尾停止扩展。
1.42稳定Preview/异步Run、持久化幂等/latest-wins、真实prompt独立取消、输入drain/帧门禁与保留保护已有[限定验收](https://github.com/m5agent/m5stack-esp-emulator/blob/a37342f61c05964c060719a6e35c2d568c828e84/docs/evidence/2026-10-27-preview-run-control/README.md)，含PIR包writing中取消后同VM恢复；1.43接通Live sessions托管消费者和完整文件读取，CoreS3 PIR/Relay外部完整包→Web保留MPY/资源编辑→同VM Run/输入输出/选定帧像素、取消恢复/续租关闭/ZIP与清理已验，见[Web验收](https://github.com/m5agent/m5stack-esp-emulator/blob/a37342f61c05964c060719a6e35c2d568c828e84/docs/evidence/2026-10-27-preview-web-consumer/README.md)。重启恢复/并发仅有宿主负控。新增四主机HUB控制组与U131 2Relay的托管Preview限定验收，原驱动、按键/触摸、双GPIO/蓝灯、取消恢复和清理已通过；2Relay另核精确历史帧SHA。窄屏/长dt构图UNIT-HOST-35限定修复，见[本块证据](https://github.com/m5agent/m5stack-esp-emulator/blob/a37342f61c05964c060719a6e35c2d568c828e84/docs/evidence/2026-10-27-preview-controls-and-2relay/README.md)；不继承其它guest/AIFlow/硬件PASS。
interrupt-only 不保证清空 native/定时器/IRQ/线程，断流/重连缺口保持 unknown。
启动取消已有生命周期事务、pending自动收尾、停止意图版本、Network child收据和draining所有权门禁，见[取消回归](https://github.com/m5agent/m5stack-esp-emulator/blob/a37342f61c05964c060719a6e35c2d568c828e84/docs/evidence/2026-10-26-session-cancellation-f309/README.md)。
Unit客户端旧请求/队列和装配污染已有[响应隔离](https://github.com/m5agent/m5stack-esp-emulator/blob/a37342f61c05964c060719a6e35c2d568c828e84/docs/evidence/2026-10-26-preview-client-fencing/README.md)；
本客户端隔离不建立多客户端server快照全序，其它后端现场执行不继承宿主回归。

项目已经不是单固件 PoC，而是可执行的多设备 virtual-device 平台：

- Device Service 支持 lease、虚拟 Flash、串口、frame/input/QOM、网络故障、
  pcap、evidence、历史恢复和 worker 生命周期；
- S3/C6/Core2 的规范整机路径是 `qemu-unified`，同一 lease 和同一 guest
  内组合板级、WiFi、BLE 与 evidence；Core2 使用 `core2-native-hci`；
- 网络路径包含 controlled DNS/TLS、exact/domain/CNAME answer binding、
  严格 Host authority、有界 IPv4/IPv6 egress、WPA2、断线恢复、双 guest
  fabric、namespace/container worker 和 pcap。
  同 guest CNAME→HTTP 与专用测试构建的 IPv6 TCP/HTTP 已覆盖，原厂 UIFlow2 默认未启用
  IPv6 link-local；`RUNTIME-05` 的 S3 WPA2-PSK 成对密钥路径已关闭；
- 固件入口包含 FirmwareManifest、WebBurner/M5Burner/ESP-IDF、capability、
  文件系统、session-isolated NVS/SD fixture、静态审查和 Secure Boot v2
  镜像分析；
- Tab5、CardputerZero 和视觉外壳仍是可用子集，不能继承 S3/C6/Core2 的
  完整度。

当前阶段仍是 `PILOT`。`API-01` 的双主机接口审计、QEMU 0051–0067 与 SDK 候选修正见[本轮证据](evidence/2026-10-27-uiflow2-api-sweep/README.md)；最终 runtime 完整矩阵 68/68、零自动重试，stock 失败/配置/模型/可选外设边界继续保留，不能称全接口功能 PASS。2026-10-28 又在 StopWatch、StickS3、Core2 的当前 v2.5.3 镜像上完成三设备复测：system runtime、sockets、MQTT、network、EzData 和候选 HTTP/Modbus 路径稳定，确认并修复 requests2、BLE UUID32、Modbus transform/async、M5UI Canvas/Image/Spinbox 共享缺陷；随后分别重建三台候选 application，QRCode.setText 从旧文本 oracle 失败转为新文本 PASS，TLS epoch 从证书过期转为三台各 5/5 mTLS HTTPS PASS。`Display.drawPixel` 定位为 framebuffer panel 缺少 Python transaction，而非 CO5300 单像素限制；候选三台通过 standalone 奇偶像素、相邻像素保留和显式嵌套事务。三台 Mic `record`/`recordWavFile` 与 Speaker raw、WAV/file 已在最终 QEMU 完成数据面验证；`0062` 修复 ESP32-S3 固定两秒/128 描述符后停止 DMA completion。Core2 A/B/C 经 FT5x06 触控条、PWR 经 AXP2101 事件，四例 `WAS_HOLD` 与 remove 均通过最终 runtime；`0063` 首版曾吞掉 `key:p`，现已修复并由 `test_core2_touch_buttons_patch` 锁定。物理触控、声学、PMIC 电气和真机仍 `NOT RUN`。`0067` 的 opt-in ESP-NOW virtual-peer loopback 已让三台原厂 `espnow`/`m5espnow` 的 unicast、broadcast、recv 和 IRQ 通过正常 controller TX/RX DMA；外部 peer、PMK 加密 payload、跨设备 fabric 与 RF/timing 仍为 `RUNTIME-06`。见[三设备证据](evidence/2026-10-28-multi-board-uiflow2-revalidation/README.md)、[音频证据](evidence/2026-10-28-three-board-audio/README.md)、[Core2 输入证据](evidence/2026-10-28-core2-touch-buttons/README.md)、[QR/TLS 候选固件证据](evidence/2026-10-28-qrcode-tls-candidate-firmware/README.md)、[drawPixel 证据](evidence/2026-10-28-stopwatch-drawpixel-transaction/README.md)和[最终接口复测](evidence/2026-10-28-espnow-and-three-board-interface-retest/README.md)。Core2 UIFlow2 公开最小首帧/WLAN 及 SPI DMA 双消费撕裂已修复，离线 MAC/MMIO/DMA/IRQ、Widgets、字形与显式 WiFi 分别验证；[本轮证据](evidence/2026-10-27-core2-startup/README.md)不关闭旧 UIFlow1 LVGL7 `RUNTIME-03`，原始私有完整应用及物理硬件也不继承通过。

最终 runtime `78555183…` 的三设备 system、shared、17 个设备组和通信/音频/候选接口均重绑 PASS 且无 retry；Device Service API 的 81 operations/95 cases 也 PASS。stock HTTP、Modbus async 和 TLS epoch 缺陷继续保留，固定候选分别在相同 runtime 通过 2/2、50/50 和三台各 5/5，见[最新接口复测](evidence/2026-10-28-three-board-uiflow2-latest-runtime/README.md)。`0070` UART virtual-clock trace 进一步证明 legacy Core2 的 BOARD/APIKEY 发生在 normal-WDT 后，shift=2 仍 reset，不能把 accelerator override 当修复；`RUNTIME-03` 保持 OPEN。
2026-10-29 又在 QEMU `fccfa931…` 上完成 StopWatch、StickS3、Core2 的三设备全接口复测：system 各 `50 PASS + 1 STATE_PASS`、shared 各 `7/7`，通信、EzData、音频、ESP-NOW 和已选设备组稳定。StopWatch/Core2 各完成 28 类、505 个 M5UI 文档方法，stock 仍稳定复现 Canvas triangle、Image float scale 和 integer Spinbox step 三个缺陷；StopWatch candidate 状态和画面均通过，Core2 candidate 状态 `4/4`。该轮当时仍观察到 Core2 全屏刷新条带；后续 `0074` 定位为 DMA descriptor 与 CPU data-register 对同一 panel flush 的双消费，修复后 hash-pinned candidate 的 triangle/image 两个 frame oracle 均为 `FRAME_PASS`，见[M5UI DMA 修复证据](evidence/2026-10-29-core2-m5ui-dma-dedup/README.md)。三台 stock GATT 在该轮因 internal controller/board-ready 边界不可用；后续 Core2 改用 `core2-native-hci` + matching ELF，独立 `ble-nus` session 全部通过，见[Core2 stock BLE 证据](evidence/2026-10-29-core2-stock-ble-native-hci/README.md)。StopWatch/StickS3 stock controller、BLE 安全、RF 和真机仍开放。本轮同时修复 M5UI 设备尺寸与旋转、Core2 超时预算、完整 BLE 身份表和 Core2 blocker 文案，见[三设备全接口证据](evidence/2026-10-29-three-board-uiflow2-full-retest/README.md)；该结果不关闭 Core2 legacy `RUNTIME-03` 或任何真机边界。
Core2 legacy 旧裸 QEMU 控制同时缺少 matching LittleFS2 VFS 和 `misc.esp32_wifi` NIC；改用 UIFlow 自带 packer 与 `/api/v1` 的 `runtime=qemu-wifi` 后，120 秒诊断已执行注入的 `CORE2_LEGACY_VFS_BOOT`。随后 `0068` 修复 legacy HSPI/SPI2 与 UIFlow2 VSPI/SPI3 的共享 panel routing，legacy `m5stack`/`lcd` probe 从 0 变为 1422 nonblack pixels；`0069` 修正 protected `WDTPROTECT` 下合法 `WDTFEED` 被丢弃的模型错误，但同固件 60 秒正常 WDT 仍在 `17.2529 s` 触发 TG0 stage-1 reset。原厂 startup UI、setup/REPL 和应用帧仍未完成，`RUNTIME-03` 保持 `OPEN`。
`0071`-`0073` 又把 WDT-off 的工作预算收窄到稳定的 `0xBB/64 -> 0x05/1` 循环：`0x05` 主要由 ROM read-command 区间的 `0x4006222c` 发起，`0xBB/64` 主要来自应用 segment 5 的 `0x40093b57`；同一 frozen QEMU 的 normal-WDT 仍在 `17.2536 s` reset。没有 matching legacy ELF/MAP，当前仍不能把 issuer PC 命名成精确应用函数或据此关闭启动问题，见[issuer PC 证据](evidence/2026-10-29-core2-ssi-command-pc/README.md)。旧无 NIC 黑帧不再单独作为显示完成路径结论，见[协作 IRQ/RMT 证据](evidence/2026-10-28-cooperative-highint-rmt/README.md)、[VFS/WiFi fixture 校正](evidence/2026-10-28-core2-legacy-vfs-wifi-fixture/README.md)、[dual-SPI panel routing](evidence/2026-10-28-core2-dual-spi-panel-routing/README.md)和[最终接口复测](evidence/2026-10-28-espnow-and-three-board-interface-retest/README.md)。
## 本轮目标盘点

| 目标 | 已经落地 | 当前缺口 | 结论 |
| --- | --- | --- | --- |
| 网络 namespace、DNS/egress、pcap、错误密码、断线和重连 | controlled DNS A/AAAA/CNAME、有界 IPv4/IPv6 egress、TLS/Host policy、pcap、WPA2-PSK 正确/错误密码、radio/AP 恢复、DHCP renewal、双 guest fabric 和 worker-local QEMU | `NET-04` 的物理跨主机 executor/reattach、跨主机幂等、无 reachable seed 的任意 NAT、QEMU guest/controller 内部状态和外部 side-effect ownership | 核心虚拟设备路径可用，生产网络仍为 `PILOT` |
| Core2 cache/PSRAM、原生 BT controller、DNS/公网 | QOM `8 MiB` PSRAM、upper-bank MMU、虚拟 PSRAM 压力、OpenMAC WiFi、公网 DNS/HTTP、native-HCI、外部 NUS GATT、重连、长稳、当前容量并发和 legacy dual-SPI panel routing | 物理 PSRAM/cache timing、bit-exact BT controller/baseband、更大规模和持续吞吐；legacy startup UI 与 normal-WDT 仍未完成，probe 非空帧不等于原厂应用帧 | 功能级路径可用，物理/controller 等价性和 legacy 启动仍 `OPEN` |
| FirmwareManifest、WebBurner、安全配置和 capability mismatch | merged/segmented、WebBurner/M5Burner/ESP-IDF、content-stable manifest、ZIP path/casefold/symlink 与资源唯一性、显式 sdkconfig 优先级和 multi-build SoC 选择 fail closed、mandatory capability policy、unknown required capability fail closed、文件系统/NVS/SD、静态审查、Secure Boot v2 镜像数学，以及 aggregate/image/eFuse understatement、key mismatch 和 secure-version rollback fail closed | 运行态 ACL/许可、live eFuse/trust root、生产 key、bootloader anti-rollback 执行、真实云端业务和更多固件族 | 导入与静态审查可用，运行态安全和通用兼容性仍为 `PILOT` |

这三组能力已经串进同一个 Device Service lease/evidence 模型，但“同一 guest
完成某条路径”只证明该固件、设备、profile、输入和观察窗口，不等于物理 RF、
电气测量、生产密钥或任意固件兼容。

> 以下 Core2 段落不是逐日进度流水，而是当前 `RUNTIME-03` 的阻断摘要。
> `0031-0041` 中被否定的旧假设仍保留，是为了让后续维护者不要把 UART
> storm、永久 handoff deadlock、TG1 feed 停止或“Flash 扫描永不结束”重新
> 当作当前根因。精确运行序列只在验证台账和 evidence 中维护。

Core2 legacy I2C 的 board-bus routing 已修正：AXP `0x34` 与 RTC `0x51`
现在共享 `/machine/soc/i2c0/i2c` 并正常 ACK，原 `I2C bus error (19)` 消失。
同一固件随后由 TG0 stage-1 触发 watchdog system reset，仍没有非空应用帧，
因此 `RUNTIME-03` 继续作为当前调查入口，但不能再用 PMIC 寄存器或 I2C
routing 解释首个失败点。

TIMG watchdog trace 已证明默认单会话能够持续喂狗，而并发 lease 或显式
accelerator 对照会在不同 CPU/PC 触发 interrupt-WDT；这些结果已排除了把问题
归因于单一固定 PC、PMIC 或 RTC 地址的做法，但说明 legacy 路径仍与宿主调度
和启动期同步有关。最小 ESP-IDF 探针又抓到了一个
独立的 generic Xtensa timer 缺陷：timer ISR 在最后的相等窗口写入
`CCOMPARE == CCOUNT` 时，旧减法把下一次到期算成 `2^32` ticks，等价于在
Core2 上延迟约 26.8 秒，足以触发 interrupt-WDT。`0034` 只把相等期限安排到
下一 cycle，其他 32 位回绕语义保持不变；修复后的
`CORE2_FLASH_IPC_READ_START` 首启动门禁已在 trace 开/关和固定/auto icount
对照中通过。此前“flash 读取前 spinlock owner
mismatch”来自探针把 4096-byte 局部数组放进 4096-byte 任务栈，已经作为
harness 缺陷撤销。

这个修复没有关闭 legacy UIFlow：同一公开固件仍在初始化阶段由 TG0
stage-1 触发 system reset，reset CPU PC `0` 并保持黑帧。因此
`RUNTIME-03` 的 timer-deadline 子问题已经 `FIXED`，但 legacy 应用初始化、
TG0 stage-1 reset 和累计 Flash/cache-handoff 服务进度仍 `OPEN`。

后续 high-priority IRQ 诊断确认，早期固定 CPU0 `0x400843…` / CPU1 `0x400864…` 双等待是单线程 TCG slice 造成的调度 artifact：发送端会在 peer handler 观察共享 start/end flags 前开始下一轮。旧 setter trace 在 reset 前记录约 `4,376` 次 completed handoff；`0065` 进一步在 handler `memw` 发布 start 后和 sender `retw` 返回 end 路径时协作让出，五轮首启动均在约 `5 s` 越过旧固定双 PC。

另一个独立失败来自 classic ESP32 RMT 未实现：`conf0.mem_size=0` 会让 Neopixel translator 分配 0-byte buffer 并报 `OSError`。`0066` 补寄存器、RMTMEM、threshold、`TX_END` 与 INTMATRIX source 47 后，同一固件到达 `BOARD NAME`/`APIKEY`，WDT-off 68 秒仍为黑帧。

继续对照后又确认两个独立模型事实：

- TIMG 旧模型在 `INT_ENA.WDT=0` 时仍抬高 WDT level IRQ，与
  `INT_RAW & INT_ENA` 的 masked-status 语义不符；`0035` 只修正该寄存器
  语义。修复后同一 legacy 固件仍进入 `TG0WDT_SYS_RESET` 和 reset PC
  `0`，所以它不能关闭 `RUNTIME-03`；
- legacy 启动期的 QIO Flash 扫描是明显的逐字节 SSI 成本热点。临时
  `blk_pread` 诊断路径在抽样 cache line 上与后续 SSI 数据流逐字节一致，
  但该路径绕过 SSI 数据阶段；先前一次到达 `Performing initial setup`、
  MicroPython 版本和 `>>>` 的结果在当前重建的 120 秒窗口中未复现；
- `0036` 新增保留 m25p80 命令/地址/dummy/STATE_READ 语义的 SSI 批量
  数据面。抽样批次与原逐字节路径完全一致，Core2 UIFlow2 设备组和共享
  控制器完整 UIFlow2 矩阵都通过；但正常 WDT 下 legacy 仍在观察窗口内
  复位，关闭 WDT 后也没有进入 setup/REPL；
- 直接物理内存 state trace 观察到 `s_flash_op_can_start`、
  `s_flash_op_complete` 和 cross-core reason 反复在 0/1 间变化。CPU0
  会多次位于 `spi_flash_op_block_func` 等待路径，CPU1 位于 cache/DPORT
  或任务切换路径，但这不支持“握手永久不完成”的旧判断。
- `0037` 增加默认关闭的统一 handoff trace，把 virtual time、CPU、guest PC、
  cross-core、DPORT cache、SSI transaction 和 TIMG WDT 写进同一日志格式。
  早期 normal-WDT 配置曾观察到 TG1 最后一次 feed 后恰好
  `800,000,000 ns` 进入 stage-0 timeout；该现象保留为特定 trace 配置下的
  历史观测，不能用它继续断言当前固定配置必然出现 TG1 feed gap。
  WDT-disabled `sample=1024` 与 trace-off 产生相同 Serial SHA，均为
  启动 banner、无 setup/REPL，说明该采样级别没有改变序列结果。
- 额外的 1 ms PC 采样对照仍复现固定 800 ms gap，但更早 reset。最终窗口
  的地址簇是 CPU0 `0x400843ac/af/b1`、CPU1 `0x4008649c/9e`。后续
  BIN/ELF 字节审计否定了此前沿用的 UART ISR/MicroPython VM 符号：local
  UIFlow2 v2.5.3 ELF 与 public UIFlow_Core2 v1.15.4 BIN 在三个 CPU0
  地址上全部不一致。BIN 自身在该区域是包含 CPU ID、DPORT
  `0x3ff000e8/e4` 和 Flash/cache handoff 状态的控制流，但精确函数仍未被
  matching ELF/MAP 绑定。UART storm 解释因此撤回。
- `0038` 增加默认关闭的 `M5SW_ESP32_HANDOFF_PAUSE_NS`：QEMU 在指定
  virtual time 输出 pause marker 后对自身发送 `SIGSTOP`，不启用高频 PC
  采样。两次独立冻结分别落在 `14.800033 s` 和 `15.301447 s`：
  - 早窗口没有固定 PC；
  - 晚窗口中 CPU0 停在 `0x40087980`，CPU1 停在 `0x40084484`；
  - CPU1 `INTSET=0x40`、`interrupt_request=CPU_INTERRUPT_HARD`；
  - BIN 自身在 CPU0 地址附近清零 `0x3ffc7ec8`、置位
    `0x3ffc7ec9` 后循环等待前者，形态与旧 ESP-IDF
    `spi_flash_op_block_func` 的 complete/can-start 握手一致；
  - CPU1 地址附近清零 `0x3ffc7750/54`，调用者位于同族的 cache handoff
    路径。
- `0039` 在 pause 前直接记录 CPU、handoff flag、DPORT/cache、SSI 和
  cross-core counters。14.8/15.3/15.9 s 三点中 CPU0 前两点均停在
  `0x40087980`，CPU1 在 15.9 s 进入不同路径；cache-sync calls 增加
  `16144 → 16180 → 17444`，changed-page 累计值停在 `6679`，而 SSI
  transactions `6984 → 6998 → 7506`、cross-core writes
  `40274 → 40566 → 43584` 继续增加。两核整体永久停止被排除。
- `0040` 用默认关闭的 BIN-bound PC 列表记录 complete/can-start
  set/clear 四个 setter。首轮 normal-WDT 在 `5.913935 s` 出现 stage-0
  timeout、`15.914787 s` 首次 reset；reset 前四个 setter 各命中约
  `4,377` 次。cache handoff 反复返回，不再支持“单次 handshake 永久
  不返回”。
- 新增 `run_wdt_liveness.py` 的三次独立 artifact-bound 对照关闭 PC trace、
  保留 TIMG verbose trace。三次运行都在约 `5.91 s` 观察到 TG0 stage-0
  timeout，此时 WDT 中断被 mask；随后同一 TG0 在约 `15.91 s` 进入
  stage-1 system reset。TG1 每轮仍完成 `6,618-6,807` 次 feed，最大相邻
  间隔 `8.478-10.410 ms`，最后一次 feed 距 reset 仅
  `1.779-4.271 ms`，`0` 次 TG1 interrupt-WDT；stage-0 后也没有 TG0
  feed、reconfigure 或 protect 写入。当前首 reset 分类为
  `BOOTLOADER_TG0_STAGE1_RESET_WITH_TG1_LIVE`，历史 `800 ms` TG1 gap
  为 `NOT_REPRODUCED`。
- WDT-off 只作为诊断 control：新增 `0041` register/pointer/stack dump 后，
  45 秒与 120 秒两个独立 lease 都停在 CPU0 `0x4026306e`（`waiti` idle）和
  CPU1 `0x40100049`（LVGL 双缓冲 flush wait）。flash-cache handoff 计数在两次
  snapshot 中均为 `49,848` calls / `45,847` changed pages，SSI 均为
  `22,554` transactions / `671,936` RX bytes，最后活动停在约
  `43.91-44.00 s`；cross-core writes 仍从 `123,476` 增加到 `139,094`。
  BIN-bound 反汇编把 wait 定位到 LVGL 7 `lv_refr_vdb_flush`：`A2` 是
  `lv_disp_buf_t`，`A2+24` 是 `flushing=1`；`A10` 是 display driver，
  `A10+28` 是可空的 `wait_cb=0`。两次 flush 的显示对象都有两个有效
  buffer，因此这是在等上一帧异步 flush 完成。
- `0x40174758` display `flush_cb` 在 WDT-off trace 中于
  `44.198632 s` 调用一次，但本应调用 `lv_disp_flush_ready()` 的
  `0x40174884` completion callback 没有出现；302-byte 黑帧不变。
  `0042` 补了 `SPI_SLAVE.TRANS_DONE/TRANS_INTEN` 到 SPI IRQ 的模型，
  可观察到 `trans_done=1/trans_inten=1/level=1`，但 50 秒窗口内仍未看到
  completion callback，normal-WDT 仍在约 `15.9157 s` 由 TG0 stage-1
  首 reset。因此后续问题已经从“未知 late object”收敛到 display
  flush -> SPI interrupt -> completion 链。

当前工作假设是 legacy 应用先经历约 44 秒的大量 Flash/cache handoff，随后
进入 LVGL 双缓冲 flush completion wait；TG1 feed 并非当前配置下的停摆点。
高频采样下
的固定 UART/VM PC 簇不再成立；“单次 cache restore 未返回”被
`0039/0040` 否定；历史 `800 ms` TG1 gap 在三次当前配置中为
`NOT_REPRODUCED`，不能继续作为首要根因。下一步是确认 SPI interrupt
在 guest intmatrix/ISR 中的实际投递和 queue/status 更新，直到
`0x40174884` 完成 callback 与 `lv_disp_flush_ready()` 可观测。
v1.15.4 ELF/MAP 仍可并行取得，但不再是理解该 loop 的必要条件。
精确批次、通过率、
artifact 哈希和符号化结果见[验证证据台账](validation-ledger.md)。

所有仓库结果默认是 `virtual-device validation`。只有明确标注
`hardware validation` 的同固件路径结果才能描述物理 RF、功耗、声学、光学、
机械、电气或真机安全状态。

## 当前工作与下一门禁

`UNIT-01` 外壳固定更新至公开 `3681a6482aff96501d44659ba5a1603246f1fe1f`：
14主机/113视觉Unit及287张许可PNG通过独立完整浏览器检查，默认配置不外推83项变体；
80款仅视觉；内部协议登记34种，新增U131双GPIO/蓝灯、8Servos HAT/Unit、Joystick2 与 NFC Unit；Scroll及2Relay均保留partial边界；不得继承MCU完整行为、机械或电气等价结论。
见[外壳与checkpoint证据](https://github.com/m5agent/m5stack-esp-emulator/blob/a37342f61c05964c060719a6e35c2d568c828e84/docs/evidence/2026-10-26-visual-refresh-and-checkpoints/README.md)及[Scroll证据](https://github.com/m5agent/m5stack-esp-emulator/blob/a37342f61c05964c060719a6e35c2d568c828e84/docs/evidence/2026-10-26-scroll-controller/README.md)：新pin下同色灯/Scroll实际Web复测与原I2C/RMT驱动分层验收；九patch冷构建和四主机同VM程序属于前轮控制器证据。新10-patch独立冷构建850426下CoreS3定向7PASS、完整矩阵66/67；Core2 IMU相同marker黑、UART正确，独立单例PASS不回写完整轮，UNIT-HOST-21仍OPEN。34款协议登记可从固定源码栈重建，精确范围见[本块证据](https://github.com/m5agent/m5stack-esp-emulator/blob/a37342f61c05964c060719a6e35c2d568c828e84/docs/evidence/2026-10-27-preview-controls-and-2relay/README.md)；视觉和协议保留独立来源。

CoreS3 的逐型号功能证据现已通过严格三层汇总：同 guest/controller、真实
浏览器和全型号桥契约分别核对；每个运行例都有实际 PID→QEMU SHA、同固件、
串口、帧、冻结 Unit contract、停止前 ZIP 和保留历史。显式选择来自 gen7 的
16 个成功记录与 gen8 的 11 个补测记录；原轮失败、中断和未执行项保留，不能
称为单次 27 项全绿运行。见[严格选择与范围](https://github.com/m5agent/m5stack-esp-emulator/blob/a37342f61c05964c060719a6e35c2d568c828e84/docs/evidence/2026-10-26-unit-final-selection-a8fe/README.md)。
该历史选择中 26 款使用原 Unit 驱动路径，IR 只在明确 opt-in 的 custom callback-root
补丁下闭环；原发布包装驱动的 GC 回调和 uint8/native16 TX 边界仍单列。
后续更严格的 Buzzer 定时检查发现旧断言会接受稍后的手动关闭；原版 once
自动停止现为 FAIL，显式 custom wrapper 结果另列，不能继承该历史汇总。

共享控制器已在冻结 Xtensa `a8fe15db…` / RISC-V `ff6c2ef7…` 的独立完整轮次
通过；初轮失败与 VFS 定向复跑保留为历史。这不关闭 Core2 legacy WDT/黑帧。
服务启动的 QMP 建连竞态和握手异常 socket 清理已修复；真实冷写入会话自然从
flashing 到 running，并在不刷新页面的情况下恢复 Unit 控件和读回。

Button/Relay/ENV III 在 AtomS3R、StickS3、StopWatch 的九个独立 gen9 session
已通过设备本地 guest/controller 与真实 Web 严格功能验证，停止前 ZIP 和历史
均保留。九张 native frame 完整；三张 ENV 浏览器截图的标题上缘被 sticky
header 遮挡，构图单列 `PARTIAL`，不称完整视觉验收。
见[九组合证据与边界](https://github.com/m5agent/m5stack-esp-emulator/blob/a37342f61c05964c060719a6e35c2d568c828e84/docs/evidence/2026-10-26-unit-host-web-gen9-a8fe/README.md)。
Joystick v1.1、Encoder、8Encoder、CardKB、RFID2 在这三款 S3 主机的显示
修正固件已完成三个独立 gen9 批次、十五个可见 session 的功能验证；原驱动
断言、真实 Web、直接 PID、ZIP 和实际停止历史均绑定。十五张实际最终原生
帧清楚分行，StopWatch 文本在圆内；可读性只覆盖这些捕获帧，未外推到所有
中间态或极值组合。见[新固件三批证据](https://github.com/m5agent/m5stack-esp-emulator/blob/a37342f61c05964c060719a6e35c2d568c828e84/docs/evidence/2026-10-26-unit-control-display-gen9-a8fe/README.md)。
精确主机/固件结果已加入 `host_validation`。原批 AtomS3R 的功能 PASS / 原生
多行可读性 `PARTIAL` 保留为[历史证据](https://github.com/m5agent/m5stack-esp-emulator/blob/a37342f61c05964c060719a6e35c2d568c828e84/docs/evidence/2026-10-26-unit-atom-controls-r1-a8fe/README.md)，未回写旧记录。
上述八款的主机本地结果保留。整体 runtime 状态保持 `implemented`，具体
固件/主机/浏览器结果单列，不从子批次升级整个工作流。
三主机五款控制类的准备与执行入口已收拢到 `tests/units/`：按真实参考镜像
分区打包，默认离线核对当前源码、工具链、完整准备文件树和 VFS；源码漂移
必须重新准备。显式执行复用原 CONTROL 断言与真实 Web，并直接保存停止后的
历史响应；入口迁移不扩大既有主机准入或已归档功能结论。
三主机六传感器的 `prepare_host_sensors.py` / `run_host_sensor_cases.py`
也已迁入，18 份完整 VFS 镜像与离线候选逐字节相同。原驱动与初始化/负控/
采样链保持；初始 BLOCKED / NOT EXECUTED 与开发准入 NOT RUN 记录保留。
后续完整的 18 组合已通过 gen9/a8fe 可见会话：36 个新鲜串口输入向量、84 次
真实产品 POST、93 条初始化负控和 294 项原控制器断言分别核对。外部精确
scan、内部 BMI before/after/loop、实际字体与布局、直接 PID/固件/worker、
停止前 ZIP 和停止后的历史均绑定。主机结果只登记对应固件，其他组合不继承。
见[传感器三主机实际证据](https://github.com/m5agent/m5stack-esp-emulator/blob/a37342f61c05964c060719a6e35c2d568c828e84/docs/evidence/2026-10-26-unit-host-sensors-gen9-a8fe/README.md)。
18 张最终历史原生帧及 Heart 两张不同的早期 controller 帧已逐张看图；可读性
只覆盖这 20 张实际图像。Heart 原驱动在有效样本间出现零值，StickS3/StopWatch
的分次帧也不同，三路采集分别绑定，不声称跨请求原子一致或 BPM/SpO2。
通用 QOM 树截断在 Unit 前，路径证据来自冻结 contract/查询实现与实际 guest-QOM
和 chip 计数。准备工具本身不授予 PASS；其余未准入组合仍在 API 操作前拒绝。
视觉绑定仍分为已映射、待绑定、定性活动和面板展示；未确认的 LED 位置、
轴向/角度和机械响应不能称为已完成动画。物理硬件验证仍为 `NOT RUN`。

异步模型加载现在隔离 DOM 归属；本客户端松开请求失败后保留意图并做一次
有界补偿。23 项确定性故障回归和一个真实 CoreS3 Button 会话均通过；晚到模型
不清空 2D 帧，实际丢失 release 后 controller/guest 自动释放，普通手势不增 POST。
见[前端恢复专项](https://github.com/m5agent/m5stack-esp-emulator/blob/a37342f61c05964c060719a6e35c2d568c828e84/docs/evidence/2026-10-26-unit-web-recovery-a8fe/README.md)。
该补偿不是服务端多客户端同键仲裁，也不关闭其余视觉与跨主机覆盖范围。

12 款静态 Unit 现通过画布外读数 rail 显示当前控制器标量；来源必须是
running session 的冻结定义与 live guest-QOM，停止、不可用或越界时不显示
未确认数值。模拟输入、固件输出、Thermal fixture readiness 与控制寄存器
状态分别标注。离线语义、反例和四项浏览器回归均通过；真实 CoreS3 ENV III
两向量及 Relay 双输出态的[首批实时读数证据](https://github.com/m5agent/m5stack-esp-emulator/blob/a37342f61c05964c060719a6e35c2d568c828e84/docs/evidence/2026-10-26-unit-readout-live-a8fe/README.md)
保持不变。后续显式选择九款成功记录与 Light/Thermal 的新双例批次，11 款
原驱动路径均完成新的 guest/HTTP/QOM/DOM、直接 PID、停止前 ZIP 和历史
检查，见[扩展读数证据](https://github.com/m5agent/m5stack-esp-emulator/blob/a37342f61c05964c060719a6e35c2d568c828e84/docs/evidence/2026-10-26-unit-readout-expanded-a8fe/README.md)。
Light 实际五次 POST，首次 false 由首 POST 前的真实 GET 证明；Thermal 两个
raw fixture 均经过 guest 768 像素及 9 样本计算，rail 仍只表示 6401 控制字和
fixture-ready=true。旧 Light 计数失败不回写；大尺寸整页截图只核完整解码，
不等于构图验收，独立帧/轮询也不证明原子快照。

Buzzer 原固件的 once 自动停止失败：natural 镜像到期后真实控制器仍约 50%，
独立 trace 镜像抓到 frozen SoftTimer 调用 Haptic callback 的 TypeError 和
后台线程退出。显式 opt-in 的 custom Buzzer wrapper 适配 timer 参数后，
六个 rail 阶段及手动输出前的自动归零通过；相同新断言下原版仍 FAIL。
默认原版镜像 SHA 不变，QEMU/frozen 模块不改，见
[Buzzer 专项](https://github.com/m5agent/m5stack-esp-emulator/blob/a37342f61c05964c060719a6e35c2d568c828e84/docs/evidence/2026-10-26-unit-buzzer-once-a8fe/README.md)。
S3 getter 缺支已有 `0037` 受限修复：同固件 SHA 的实际 getter/MMIO A/B
验证稳定 set+update 路径，pending/current-cycle、fade 与其它时钟仍是缺口。
Buzzer 浏览器试听由实际 guest-QOM 驱动、用户启用，停止时关闭音频上下文；
自定义诊断固件的显式零 setter 与静音准备窗均单独标记。原发布驱动的 once
问题与物理声学边界继续开放。该 `29d8f6ec…` 轮尚未修复初始化 QOM 刷新，
完整矩阵为 66/67；Core2 IMU 串口正确但帧标记缺失，单例复测通过，不能
拼成全量 PASS。完整范围与失败保留见[本轮证据](https://github.com/m5agent/m5stack-esp-emulator/blob/a37342f61c05964c060719a6e35c2d568c828e84/docs/evidence/2026-10-26-unit-ledc-audio-29d8/README.md)。

三主机十二 IO 的正式入口已完成离线准备与开发准入，原协议/负控/采样/断言和
官方驱动保留；ADC 的 app calibration 与 ADC2 oracle 条件在 API 前阻塞。
这些新准备包不授予功能 PASS，源码合并变化后必须重新准备。用户已将近期
交付聚焦于外部 Agent 的 HTTP 链路：创建虚拟设备、选择 Unit、提交 UIFlow
源码、运行和实时状态/双向控制。已合入最新主线 `f206175`（merge `c53950a`），
新增 `POST /api/v1/firmware/uiflow`：在已知 reference 的真实 LittleFS 中写入
源码、读回并保留其它资源，创建 session 时强制 caller-source SHA pin，
provenance 随历史和 evidence ZIP 保存。当前仅准入 CoreS3/AtomS3R/StickS3/
StopWatch 四主机 reference；源码 HTTP 与解码后累计源码分别限 1 MiB。

CoreS3 的 Button/Relay/ENV III/RGB/Encoder 五例已通过该源码入口实际运行，
包括 Web→guest 输入、guest→Web 输出和 RGB 短帧负控。指南逐字 Button 与
HUB+ENV III+NCIR 另两个 session 也通过，验证自动 boot、两个 leaf 独立
I2C 读写和同 guest 的屏幕反馈。合计覆盖七种 Unit 的源码 API 路径；HUB
是被动接线，不凭其零事务值判失败或虚构控制器。所有八个会话（含单独 Button
预检）停止前取 ZIP、保留历史、PID 退出并释放 Flash。截至该首批，其余三主机
只有源码打包离线检查，不能继承 CoreS3 的此次运行 PASS。调用方式见
[外部 Agent 指南](unit-agent-api.md)，精确 SHA/输入/原始证据见
[本轮归档](https://github.com/m5agent/m5stack-esp-emulator/blob/a37342f61c05964c060719a6e35c2d568c828e84/docs/evidence/2026-10-26-unit-source-api-29d8/README.md)。

CoreS3 选定源码场景覆盖27种Unit：25种原驱动及IR/Buzzer两种显式custom，
来自多批独立会话，不是单次原版27项全绿。扩展批22个功能PASS与Thermal
missing-fixture负控分列；raw fixture功能例不混计。四控制例保留原驱动/断言，
只作可逆display-only调整。Fan动画限100% duty观测，Heart不证明BPM/SpO2。
原IR为协议观察通过、GC长期风险OPEN；原Buzzer自然timer-zero仍FAIL，手动OFF
不能补PASS。旧harness误要求output-only输入POST的browser_error不算产品故障。
相关固定上游wrapper/native源码保留callback/保活模式，但不外推所有port/发行
固件。caller、fixture、source pin及原驱动/custom精确边界见
[扩展证据](https://github.com/m5agent/m5stack-esp-emulator/blob/a37342f61c05964c060719a6e35c2d568c828e84/docs/evidence/2026-10-26-unit-source-api-expanded-29d8/README.md)及
[27种源码指南](unit-agent-api.md#已验证的-27-种源码场景)。

AtomS3R、StickS3、StopWatch各有11种选定源码场景：先前Button/Relay/ENV III
九组合，后续PIR、DualButton、LIMIT、Key、RGB、Fan、RS485、HUB共24组合，
HUB含ENV III/NCIR/TVOC三个leaf。后批Fan3在cba4e3c、rest21在0a6a9a2同步主线后
执行；两批481项源码依赖字节相同，runtime均d1ba/gen12，每份19个caller保留。
同guest的host字体/canvas/BMI内部总线及GPIO/RMT/LEDC/UART/I2C断言、新鲜串口
上下界、真实Web、source pin、PID、停止前ZIP与历史/Flash清理有独审。
指南共60份请求；三HUB原生数字token拆行仍PARTIAL，完整精确数值由UART/QOM
单列验证。非空帧/尺寸不等于所有UI状态可读，也不继承其它组合、ADC/Thermal、
原IR/Buzzer、hotplug或硬件。见[九组合](https://github.com/m5agent/m5stack-esp-emulator/blob/a37342f61c05964c060719a6e35c2d568c828e84/docs/evidence/2026-10-26-unit-source-hosts-29d8/README.md)、
[后续24组合](https://github.com/m5agent/m5stack-esp-emulator/blob/a37342f61c05964c060719a6e35c2d568c828e84/docs/evidence/2026-10-26-unit-source-host-io-d1ba/README.md)与
[源码请求](unit-agent-api.md)。

0038关闭初始化GPIO路由观察缺口：route改变时只读重算现有LEDC状态，不重放
MMIO或由Python填值。d1ba来自独立冷构建/八patch重放；同固件/caller/CAS、
无初始化后setter，旧29d8八窗0Hz/0%，新d1ba八窗2000Hz/0%。每组仅约4秒guest
采样，非60秒soak、上电首瞬间连续证明或物理脉冲。独立单次完整回归全量通过，
无重试；精确计数见验证台账，旧失败轮不改写，Core2偶发marker
根因仍OPEN。完整ROM/C6仅mid/end freeze、PaperColor RGB命令静态重构、六IR
mutable Flash hash变化但最终源码相同等限制均保留。完整PWM周期/latch/fade、
原Buzzer定时回调、其它固件和硬件仍OPEN，精确来源见
[PWM修复与回归](https://github.com/m5agent/m5stack-esp-emulator/blob/a37342f61c05964c060719a6e35c2d568c828e84/docs/evidence/2026-10-26-unit-pwm-route-d1ba/README.md)。

CoreS3 无 DinBase、单层直连 HUB 的紧凑附件布局已加入全尺寸展开与真实端口
线缆布置。ENV III/ToF/Color 四档场景、手机 Button 输入/聚焦和失败回滚共
13 组通过；合入后的 model/panel/bridge/mount/HUB 五项浏览器回归也通过。
可选布局异常不会销毁成功附件或改写兄弟输入归属。其他排列、主机、深层 HUB
和 custom pose 不继承几何通过；手机总览按钮触控舒适度仍为 `PARTIAL`。
见[限定布局与证据](https://github.com/m5agent/m5stack-esp-emulator/blob/a37342f61c05964c060719a6e35c2d568c828e84/docs/evidence/2026-10-26-unit-hub-layout/README.md)。
长卡片证据截图改为不二次滚动的完整 document clip，真实标题命中与旧实现
负控通过；历史 ENV 截图的 framing `PARTIAL` 不改写。

| Task / 工作流 | 已具备的可执行面 | 下一项最小交付 | 不可继承边界 |
| --- | --- | --- | --- |
| `RUNTIME-03` Core2 legacy I2C / UIFlow 启动 | shared I2C、timer deadline、WDT mask、stateful SSI、pending SPI remap、high-priority DPORT handoff、classic RMT、exact-time state sweep、LVGL wait、UART virtual-clock、pre-boot phase、SSI transaction profile、command correlation 和 command issuer PC 已验证；`0065` 五轮关闭调度诱导双 PC deadlock，`0066` 越过 Neopixel RMT 初始化错误，`0071/0072` 确认 `0xBB/64 → 0x05/1` 循环且 `82.4%` gap 位于下一次 status read 前，`0073` 将主要 issuer 绑定到 ROM `0x4006222c` 与应用 segment 5 `0x40093b57` | 保持 `0065/0066/0071-0073` 回归，在 transaction-bound gap 内结合 matching symbols、IRQ delivery、cache/MMU 和 PC 路径解释 pre-BOARD/APIKEY 工作预算；随后证明 setup/REPL、startup UI、display completion 和非空帧 | WDT-off、RMT 初始化、独立 SPI probe、UIFlow2 设备组、立即切核或 accelerator 都不能继承为 legacy PASS |
| 设备与统一运行时 | `qemu-unified` 单 lease、单 guest、板级 + 网络 + BLE + evidence | 代表设备同 SHA 真机验证；按新固件重新校验符号/profile | 同 SoC、同设备名或其他固件 SHA 不继承 PASS |
| `NET-04` 网络与 worker | namespace/container worker、discovery、TLS/mTLS、queue、fencing、local QEMU | 物理跨主机 executor/reattach、跨主机幂等、任意 NAT、外部 side-effect fence | 单机 namespace/container 不等于物理多机；PID 回收不等于 guest 内部 quiesce |
| `CORE2-02` Core2 长稳/等价性 | native-HCI、WiFi/公网/GATT、8 MiB PSRAM QOM、upper-bank MMU、重连、active-stop | 大于当前容量、持续吞吐、其他 teardown、bit-exact controller、物理 PSRAM/cache 和真机 | `CORE2-02` 仍为 P0；固定虚拟时钟不代表实时速度，虚拟容量不代表物理性能 |
| `FW-01`、`FW-02`、`FW-03` 固件审查 | Manifest/WebBurner、capability、文件系统、SD/NVS、SBOM/许可声明、Secure Boot v2 镜像分析 | 运行态 ACL/许可、Live eFuse/生产 key、真实云端业务、更多固件族 | 静态扫描、签名数学和包内摘要自洽不等于运行态授权或设备 trust root |
| `RUNTIME-02`、`RUNTIME-04` 模型缺口 | C6 Zigbee 与 Core2 ATECC608 已有失败/可行性 evidence；`RUNTIME-01` Flash/PMP 与 `RUNTIME-05` WPA2 已关闭 | commissioning/join 或 ATECC608 fixture | 观察到帧或读取地址不等于完整生命周期 |
| `SVC-01`、`SVC-02`、`SVC-03` | durable queue、HMAC、TLS/mTLS、rotation、trusted-host restart/reattach、companion recovery | namespace-managed/Tab5/cross-host companion、warm pool、服务模块拆分 | 单机恢复不能继承为跨主机迁移或生产调度 |
| `HW-01` 真机同路径 | 测试入口和分层规则已定义 | 代表设备同固件 SHA、同输入、同关键路径的 hardware validation | 仓库当前没有可引用的真机安全/RF/电气结论 |
| `TAB5-01` / `UI-01` / `CZ-01` | Tab5 与 Linux ARM64 有可用子集；StopWatch 为参考外壳 | P4 backend 决策、逐设备视觉回归、CardputerZero 收尾 | `partial` 是可运行子集，不是完整设备或全固件兼容 |

## 能力状态

| 能力 | 当前状态 | 主要边界 |
| --- | --- | --- |
| Device Service 与 Live sessions | 可用 | 当前是可信本地/单机服务，不是恶意多租户 VM 沙箱 |
| 公众 C/QEMU / CoreS3 | 本地、Linux Actions 与正式 GitHub Pages 限定通过 | 浏览器本地组合固定示例、LCD/触摸/PIR/暂停/分享重开；正式 HTTPS 地址独立 21 项验收通过。虚拟时间和 WDT 为墙钟 1/8，UART 只输出，无 Flash 持久化；其它设备/固件/Unit 不继承。[正式部署证据](evidence/2026-10-29-github-pages-production/README.md) / [部署](pages-deployment.md) |
| `qemu-unified` S3/C6 | 可用 | 功能级 WiFi/HCI；不是 RF/PHY、功耗或电气模型 |
| Core2 non-display | 可用 | native-HCI hook 绑定已验证 UIFlow2 build；stock BLEUART NUS 已限定通过。`m5ble.Server.get_client` 仍暴露 stock SDK `set` indexing 错误；新固件需重新校验 |
| Core2 legacy UIFlow/FactoryTest | `PARTIAL` | I2C、timer、WDT mask、SSI、DPORT handoff 与 classic RMT 子问题已修复；WDT-off Serial 到达 `APIKEY`，normal-WDT 在 BOARD/APIKEY 前 reset。pre-boot work/WDT deadline、display completion、PSRAM/cache、reset PC `0` 和非空帧仍未闭环；FactoryTest 修复后 `NOT RUN` |
| FirmwareManifest / WebBurner | 可用 | live trust root、生产 key、运行态 ACL 和完整云端业务未闭环 |
| 网络隔离与取证 | 可用 | 有界策略不是任意公网解析器；不可信固件仍需 disposable VM |
| Worker 产品化 | 单机/跨容器 `PILOT` | active-token multicast discovery、cross-subnet/NAT unicast seed discovery、credential generation-pointer migration、lease 409 fence、worker-local StickS3 QEMU 和真实 QEMU PID reap 已可用；物理跨主机、迁移、任意 NAT 和生产调度未完成 |
| Tab5 | `partial` | CSI、I2S/PCM、USB Host、SDIO、动态 I2C 和 ST7123 controller 未闭环 |
| CardputerZero | `partial` | 独立 Linux 后端；完整系统/时序/真机回归未闭环 |
| 设备视觉 | `partial` | StopWatch 是唯一参考质量外壳 |
| 真机验证 | `NOT RUN` | 必须提供同固件路径的 `hardware validation` |

## 设备矩阵

| 设备 | SoC / 后端 | 当前可执行范围 | 主要边界 |
| --- | --- | --- | --- |
| StopWatch | ESP32-S3 / QEMU | 显示、触摸、电源、IMU、音频、振动和外设数据面 | 高保真外观、RF 和真机 `NOT RUN` |
| StickS3 | ESP32-S3 / QEMU | 显示、按键、电源、IMU、音频、IR、WiFi/BLE；Hat2-Bus 8Servos 控制器路径 | RF、舵机机械/电流和真机 `NOT RUN` |
| CoreS3 | ESP32-S3 / QEMU | 显示、触摸、电源、IMU、音频、摄像头、USB Host；Port B 8Servos、双 Joystick2 和 NFC Unit 控制器路径 | 启动菜单透明/调色板图像仍有模拟条纹；新增 Unit 只覆盖寄存器与虚拟 fixture |
| AtomS3R | ESP32-S3 / QEMU | 显示、按键、IMU、磁力计、RGB、IR | 高保真外观和真机 |
| Cardputer-ADV | ESP32-S3 / QEMU | 显示、键盘、IMU、音频、SD、NFC、CC1101、IR；精确 app-bound synthetic ADC calibration、Canvas/键盘/扬声器/IMU 启动路径，以及 `0x69` BMI270 官方 API 注入回读 | 高保真外观、物理 IMU/ADC 精度、电气特性和真机 |
| PaperColor | ESP32-S3 / QEMU | Spectra 6、按键、电源、SHT4X、音频、SD、RGB、IR | 刷新时序和光学真机表现 |
| PaperMono | ESP32-S3 / QEMU | 灰度屏、触摸、电源、IMU、RTC、音频、NFC、LoRa、RGB | 刷新手感和显示真机表现 |
| StackChan | ESP32-S3 / QEMU | 显示、触摸、摄像头、环境/运动传感器、音频、NFC、IR、舵机 | 机械运动、声学和光学 |
| StamPLC | ESP32-S3 / QEMU | 显示、按键、继电器/输入、CAN、RS-485、温度、蜂鸣器 | 工业电气特性和真机 |
| NanoC6 | ESP32-C6 / QEMU | 无屏控制台、GPIO、RGB、按键、IR、WiFi、BLE | Zigbee/802.15.4 由 `RUNTIME-02` 跟踪 |
| Nesso N1 | ESP32-C6 / QEMU | 显示、触摸、扩展 IO、电源、IMU、LoRa、IR、蜂鸣器、WiFi/BLE | RGB 未验；Meshtastic 独立应用异常待归因 |
| Core2 | ESP32 LX6 / QEMU | 显示、触摸、PMIC、IMU、RTC、音频、WiFi、公网、HCI/native-HCI、PSRAM/MMU、timer/WDT-mask/stateful SSI、pending SPI/INTMATRIX remap fixes | legacy UIFlow 在 display completion 前的 reset/stop、`lv_disp_flush_ready` 与缓存 wait 未闭环、黑帧、物理 PSRAM/cache、bit-exact controller 和真机 |
| Tab5 | ESP32-P4 / esp-emu | 烧录、启动、1280×720、触摸、RS-485、ESP-Hosted、静态 I2C | P4 外设和 P4↔C6 unified network 仍 `partial` |
| CardputerZero | BCM2837 / Linux ARM64 | 系统、显示、键盘、I2C、PCM、USB Hub、摄像头、Ethernet | 完整系统回归、生产级 USB/时序和真机 |

设备、后端、外设和 profile 的动态计数见
[自动项目快照](project-snapshot.md)。

## 当前风险

1. **仿真边界**：QEMU/esp-emu PASS 不等于 RF、功耗、声学、光学、机械、
   电气或真机安全 PASS。
2. **Core2 启动兼容性**：`0065` 已关闭旧固定双 PC 的 high-priority
   DPORT handoff 调度死锁；`0066` 已补 classic RMT 并关闭 Neopixel
   translator 初始化错误。最终 WDT-off 控制到达 `APIKEY`，但 68 秒帧仍为
   302-byte、0 个非黑像素；normal-WDT 仍在 `17.249530334 s` 由 TG0
   stage-1 触发 `TG0WDT_SYS_RESET`，display completion、setup/REPL 与非空
   应用帧继续 `OPEN`。不能把
   I2C ACK、RMT 初始化、probe/UIFlow2 PASS、关闭 WDT、accelerator 或 host
   假值当作 legacy 启动 PASS。
3. **Core2 等价性**：native-HCI 是功能级 controller boundary；不是
   bit-exact Espressif baseband。QOM 模型提供 8 MiB PSRAM/MMU，但不证明
   物理板载 `8 MiB` cache timing 或性能。
4. **Worker 隔离**：409/network-partition fence 只覆盖 worker-owned 可达
   runtime；QEMU 内 guest/controller 和外部 side effect 仍需单独关闭。
5. **固件安全**：Manifest、签名数学、包内 eFuse 摘要和 anti-rollback version
   对照不能替代公钥 authenticity、Live eFuse trust root、bootloader 执行、
   Flash Encryption 和生产 key 流程。
6. **通用兼容性**：同芯片不代表同板级、分区、eFuse、安全模式、外设和控制器
   自动兼容；未知能力必须 fail closed。
7. **视觉与 Linux 后端**：除 StopWatch 外外壳仍是近似模型；CardputerZero
   不能继承 ESP32 结论。

## 证据与文档职责

- 当前能力与风险：本文。
- 未完成范围、优先级和验收：[项目 Backlog](project-backlog.md)。
- 带日期的运行结果和 evidence：[验证证据台账](validation-ledger.md)。
- 设备、固件样本、模型缺口和 Task 计数：
  [自动项目快照](project-snapshot.md)。
- 源码、测试和生成物入口：[代码与验证入口地图](code-map.md)。
- 已知模型缺口与关闭条件：
  [运行时模型缺口登记](runtime-model-gap-register.md)。
- 单 lease/单 guest 验收：[统一设备运行时契约](unified-device-runtime.md)。
- API：[Device Service API](device-service-api.md) 与
  [OpenAPI](device-service.openapi.yaml)。
- 网络：[网络模拟方案](network-simulation-plan.md) 与
  [网络诊断 lane](network-lane.md)。
- 固件：[FirmwareManifest](firmware-manifest.md) 与
  [固件审查工作流](firmware-review-and-simulation-workflow.md)。
- Core2 历史诊断：[cache/panic 调查](core2-cache-panic-investigation.md)、
  [QIO/cross-core evidence](../tests/firmware/evidence-2026-10-26-core2-qio-crosscore-diagnostic.json)、
  [handoff timeline evidence](../tests/firmware/core2_handoff_trace/evidence-2026-10-26-core2-handoff-timeline.json)、
  [state sweep evidence](../tests/firmware/core2_handoff_trace/evidence-2026-10-26-core2-handoff-state-sweep.json)、
  [setter PC trace evidence](../tests/firmware/core2_handoff_trace/evidence-2026-10-26-core2-handoff-pc-trace.json)。
- 文档契约：五个 `platform/tests/test_docs_*_contract.py` 领域模块，以及
  `platform/tests/fixtures/stale_doc_claims.json` 结构化退役说法目录。

详细运行轮次、旧失败 control 和 evidence 不回写本页；当前入口已推翻的旧
说法应删除，历史页保留原日期并标明取代关系。
