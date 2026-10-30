# 验证证据台账

日期：`2026-10-30`

Unit 历史原始归档未迁入精简源码分支。下方外部链接固定到旧提交，记录中的
PASS 不代表本次检出重跑；材料、哈希和显式审计入口见[证据说明](evidence-retention.md)。

本文只记录带日期的验证结果和证据入口。它用于回答“这项结论是什么时候、
用什么路径验证的”，不定义当前能力，也不定义待办。当前能力以
[项目当前状态](project-status.md) 为准，未完成工作以
[项目 Backlog](project-backlog.md) 为准。

所有未明确标为 hardware validation 的结果都是 virtual-device validation。
一次 PASS 只覆盖对应 commit、固件 SHA、runtime/profile、设备和检查项；
不能把同 SoC 的另一台设备、另一个安全模式或物理 RF 行为自动视为通过。

## 2026-10-30

| 工作流 | 结果 | 证据 |
| --- | --- | --- |
| `UI-02` / Cardputer-ADV 与 StackChan 输入 | 基线 main `e3f149c1`；67-patch 全新 WASM `a7fe7180…`。ADV 原 IRQ reader 的 56 物理键、PC 双 Shift/grave/Fn-Up、四旋转/四角/局部绘图及纹理读回通过。StackChan 原默认同步工作饥饿有计时负控，真实 UART 后台线程版 V4 默认镜像 `407f6260…` 的实际 105/302/803ms 点按与 Touch 坐标、同时实际位移、帧及正常 Stop 六 Worker 清场通过；187ms 最大观察轮询间隔不授任意短按保证。Arduino 对照独立记录；原用户镜像、硬件和本轮完整 native 矩阵未运行 | [范围、失败、复现](evidence/2026-10-30-cardputer-stackchan-input/README.md) |
| `CORE2-02` current tool-hash rebind | SVC-03 的三个无语义边界移动将 `device_service.py` 工具哈希从 `5b4ed0f5…` 更新为 `a96b1506…`；在 `origin/main` `3fc436e4…` 上重跑两批独立零错峰 `2x60s`，均 `2/2 PASS`，合计 `4/4`。四个 lease 均完成三次 1 MiB PSRAM sweep、两次 controlled HTTP/公网 recheck、WiFi/DHCP、外部 NUS GATT、非空 frame、32 节点 QOM、pcap、evidence 和 cleanup；每 lease HLI `45/45`、36 events/9 ACLs，errors/prealloc/panic/GATT timeout/dropped 为 0。输入在首 lease 前冻结且运行期无漂移。该结果只关闭当前工具哈希的双实例回归，不覆盖八实例 cold-start、九实例容量、吞吐或物理边界 | [重绑证据](evidence/2026-10-30-core2-toolhash-rebind/README.md)、[机器摘要](evidence/2026-10-30-core2-toolhash-rebind/summary.json)、[runner](../tests/uiflow2/core2_native_hci/run_service_5x.py) |
| `SVC-03` QEMU WiFi security/env boundary | `parse_qemu_wifi_security` 与 `apply_qemu_wifi_environment` 移入 `device_service_qemu_wifi.py`，`device_service.py` 以 same-object 方式 re-export。open/WPA2-PSK validation、password normalization、SSID bounds、S3-only trace gate 和 runtime env key/value 保持不变。专向 `4/4`、Device Service `126/126`、platform `1,678` 项为 `1,677 PASS + 1 skip`，生成器、compileall、scoped Ruff 和 diff check PASS。该结果仅为 platform-contract 边界重构，不改变 HTTP、network 配置、QEMU、session、evidence 或硬件语义 | [边界证据](evidence/2026-10-30-svc03-qemu-wifi/README.md)、[机器摘要](evidence/2026-10-30-svc03-qemu-wifi/summary.json)、[boundary tests](../platform/tests/test_device_service_qemu_wifi.py) |
| `SVC-03` esp-emu network execution parsing boundary | `parse_network_execution` 移入 `device_service_network_execution.py`，只依赖 `ServiceError`、共享 SHA256/capture parser、`DeviceSpec` 和 network-lane normalizer；`device_service.py` 以 same-object 方式 re-export。profile 默认值、WiFi/BLE/TCP booleans、hostfwd/I2C normalization、ELF requirement、PSRAM 与 expected-marker bounds、network pcap rejection 和返回结构不变。专向 `4/4`、Device Service `126/126`、platform `1,674` 项为 `1,673 PASS + 1 skip`，生成器、compileall、scoped Ruff 和 diff check PASS。该结果仅为 platform-contract 边界重构，不改变 HTTP、network runtime、session、evidence、QEMU 或硬件语义 | [边界证据](evidence/2026-10-30-svc03-network-execution/README.md)、[机器摘要](evidence/2026-10-30-svc03-network-execution/summary.json)、[parser tests](../platform/tests/test_device_service_network_execution.py) |
| `SVC-03` storage/NVS execution parsing boundary | storage/NVS 执行请求解析移入 `device_service_execution_parsing.py`，只依赖 `ServiceError`、共享 SHA256 validator 和 `DeviceSpec`；`device_service.py` 以 same-object 方式 re-export。SD capability、unknown-field fail closed、NVS partition label bounds、错误码与返回结构均不变。专向 `5/5`、Device Service `126/126`、platform `1,670` 项为 `1,669 PASS + 1 skip`，四个生成器检查和 scoped Ruff/compileall/diff check PASS。该结果是 platform-contract 边界重构，不改变 HTTP、session、runtime、evidence、QEMU 或硬件语义 | [边界证据](evidence/2026-10-30-svc03-execution-parsing/README.md)、[机器摘要](evidence/2026-10-30-svc03-execution-parsing/summary.json)、[parser tests](../platform/tests/test_device_service_execution_parsing.py) |
| `CORE2-02` 九实例容量边界与网络重检恢复 | 三次独立零错峰 `9x120s` 中，两次 `9/9 PASS`，第三次 `8/9`；失败 attempt 8 在已有真实并发 9 时触发 `ble_hs_hci_process_ack` `LoadProhibited`（`0x402630cc`），随后 `0x40092e43` 为复位次生 panic。九实例因此不进入默认容量，Device Service/runner 保持 `max-per-device=8`，并新增 concurrency 9 fail-closed 契约。当前固件/ELF/QEMU/工具 hash 下，两批独立零错峰 `2x60s` 均 `2/2 PASS`，合计 `4/4`；每 lease 完成三次 1 MiB PSRAM 连续读回、两次 controlled HTTP 和公网 recheck、WiFi/DHCP、NUS GATT、frame/32 节点 QOM、pcap、evidence 和 cleanup，HLI `45/45`，errors/prealloc/panic/GATT timeout 为 0。guest 网络 recheck 现最多三次、间隔 1 秒；PSRAM error 与可恢复 network error 分字段记录。当前 120 秒持续压力 floor 经最新 runtime 校准为 `hold/40` 且最低三次 sweep。当前高负载宿主下的八实例 cold-start tool-hash 重绑仍未 PASS，不能用旧 A/B 或宿主 BLE 初始化超时替代。全部为 virtual-device validation | [容量边界](evidence/2026-10-30-core2-concurrent-capacity-boundary/README.md)、[机器摘要](evidence/2026-10-30-core2-concurrent-capacity-boundary/summary.json)、[runner](../tests/uiflow2/core2_native_hci/run_service_5x.py)、[guest probe](../tests/uiflow2/unified_core2/main.py)、[容量契约](../platform/tests/test_core2_concurrent_capacity_boundary.py) |

## 2026-10-29

| 工作流 | 结果 | 证据 |
| --- | --- | --- |
| `UI-02` / Cardputer-ADV 用户固件 | `Piano Tiles ADV 2.0` 完整 Flash `470aabe2…872f0a` 在最终 49-patch browser QEMU 中通过：ADC calibration 错误 `0`，240×135 原生帧全部有内容，135×240 竖屏自动旋转且无裁切，5.0126 秒墙钟对应 5.0119 秒虚拟时间。该固件发布于 M5GFX `5f8a783f` 修复前，确实上报 board 14；仅在 guest 实际执行旧矩阵扫描时启用兼容输入，Enter 保持 500ms 后画面切换、帧序号差 23。未把兼容路径称为 ADV 原生旧键盘接线或物理硬件 PASS | [范围、根因与复现](evidence/2026-10-29-cardputer-adv-user-firmware/README.md)、[机器摘要](evidence/2026-10-29-cardputer-adv-user-firmware/summary.json) |

## 2026-10-28

| 工作流 | 结果 | 证据 |
| --- | --- | --- |
| `UI-02` / CoreS3 C/QEMU浏览器guest | 同步main；typed SHA callback与Asyncify Fiber/SjLj主CPU jump栈恢复修正，独立C/libffi负控复现下降、正控64KiB/2MiB零漂移；真实CoreS3每场64组Flash-MMU入口SP平稳。默认wallclock r11因LVGL queue full为PARTIAL，两个single/icount对照失败。r15/r16重开QMP失败已保留，40秒负控证明socket/guest/主循环仍活且专用context不再poll fd0。0012仅浏览器stdio改用既有main-loop context（无OOB）；最终显式vm-div8保留双CPU/原WDT，两场58检查的完整RGB/负触摸/两次计数/PIR QOM→GPIO→guest→帧、两ZIP/历史/leaseFlash释放/exit0与各5Worker自然退出通过，另三次冷启smoke通过；虚拟时间和WDT墙钟到期一起慢放，非物理时序。逐轮源码、运行指纹、活跃RSS与计时口径见证据；未发布/未转授其它板型或硬件 | [证据及边界](evidence/2026-10-28-qemu-wasm-cores3/README.md)、[指纹](evidence/2026-10-28-qemu-wasm-cores3/summary.json) |
| `UI-02` / C/QEMU 静态公众入口 | 固定 C/QEMU 源码/依赖与实际 64KiB 链接审计；本地无隔离头项目子路径两场 LCD/DOM触摸/PIR/QMP暂停恢复/分享重开/21检查 PASS，10 Workers 清理；Linux固定源码重建及导出站21检查通过，13 Workers关闭；测试fork Pages部署成功，公开HTTPS同测试器另跑21检查、10 Workers关闭；首场完整LCD/输入，第二场分享启动/退出，原仓库部署仍由管理员执行 | [本轮证据](evidence/2026-10-28-qemu-wasm-pages/README.md)、[部署说明](pages-deployment.md) |
| `UI-02` / 现有C/QEMU到WASM | 固定QEMU9.2.2和完整30层板级/Unit补丁，真实依赖、编译/链接及Chromium版本/板型枚举通过；同对象256MiB初始配置CLI退出码0。无固件QMP capabilities/query-status/quit已验；初版退出未回调保留，经显式process-exit修正后三case均exit0、四Worker在强制清理前自然关闭。未跑guest/LVGL/触摸/Unit/性能；未发布 | [研究与复现](qemu-wasm-port-research.md)、[分层摘要](evidence/2026-10-28-qemu-wasm-build/summary.json)、[WASM补丁与当前选集](../patches/qemu-wasm-probe/README.md) |
| `UI-02` / 公众工作台与独立browser backend | 固定源码双archive/target重建相同WASM，PaperS3/StopWatch官方演示在Chromium真实Worker启动/帧/输入/暂停/停止通过，无仿真API；最终首页17组含实际PaperS3 URL直开、四档布局与DOM触摸，默认16契约通过；模型独立完整第三轮17主机/184附着/201预览/423PNG通过。合并origin/main@0d4f53a3后平台1363项、6可选依赖skip及四生成器通过，1902导出资源大小/SHA核验。独立CoreS3 plain源示例触摸计数0→1；最终merged真实创建首响应丢失后同key/body恢复单guest、ZIP-before-stop、明确leasefalse/历史/PID清理通过；有界停止及未知租约另有故障契约。stock输入、unified READY、完整原生矩阵、硬件和部署不继承 | [本轮范围与复现](evidence/2026-10-28-public-simulator/README.md)、[哈希与逐层状态](evidence/2026-10-28-public-simulator/summary.json)、[架构调研](browser-runtime-feasibility.md) |

## 2026-10-27

| 工作流 | 结果 | 证据 |
| --- | --- | --- |
| Core2 UIFlow2 issues #2/#3 / LVGL | 固定 stock `V2.5.3` executable 的普通会话复现 `WLAN.active(True)` 卡在缺失 MAC/MMIO；0049 补离线控制器、服务统一 Core2 时钟。截图另定位 SPI DMA OUT_LINK/USR 双消费，0050 修复后同源码标题由全宽横条变为正常字形。最终 `712851db…` 的 display/Widgets/LVGL/offline-network 四个可见 session 通过，显式 WiFi 两个连续 session 的 scan/association/DHCP/受控 HTTP/pcap 通过；先 ZIP 后停止、历史帧/串口、Flash 释放及 PID 退出均核验。Core2 设备组 6/6、24 checks 与平台1261项（1skip）通过；完整矩阵66PASS/1Cardputer-ADV IMU FAIL、274checks、无重试，未修改主线同固件也复现该FAIL；各运行时哈希及独立对照分别记录。原始私有完整 app、旧 UIFlow1 LVGL7 `RUNTIME-03` 和物理硬件不继承通过 | [根因与范围](evidence/2026-10-27-core2-startup/README.md)、[摘要与哈希](evidence/2026-10-27-core2-startup/summary.json) |
| `UNIT-01` / GitHub issues #2–#10 | 在主线 `8a0d99a0` 上以 14-patch/109-source 重冷构建 `9aca9a8d…`，经可见 `/api/v1` session 顺序复测；平台1241项PASS/1skip，四生成器、Unit定向、四个Node契约、bootstrap receipt及0048 reverse-check通过。Issue #2/#3 仍复现 Core2 WDT/reset 与 302-byte 纯黑帧，保持 open；#4 ENV III 与 #5–#8 Servo8 HAT、8Servos、Joystick2、NFC 均通过原 UIFlow2 驱动/扫描/寄存器读取；#9 Cardputer-ADV app-bound synthetic ADC calibration 消除了 calibration fatal，并达到 nonblack/running；#10 同一 Canvas/键盘/GPIO0/Speaker/IMU setup 路径显示 `ALL SETUP OK`。九份 evidence 均 ZIP-before-stop、`purge=0`；完整矩阵、物理硬件、舵机/RF/电气精度和 Tetris 逐帧逻辑 `NOT RUN`。issue #4–#10 可在公开记录固定后关闭 | [本轮 summary](evidence/2026-10-27-issues-2-10/README.md)、[machine-readable hashes](evidence/2026-10-27-issues-2-10/summary.json) |
| `UNIT-01` / 冷pad与当前bug收尾 | 0047实际GPIO/AW/RTC来源事件与连续低C实现、旧实际源码负控通过；首候选825fd6共享回归2FAIL/1PASS原样保留。CoreS3官方2.2k上拉及M5GFX探测定位后，为soft-I2C注册独立弱bias，修订13patch/109source重放和冷构建faee96通过；修复后受影响组22/22（92checks）、平台1226、四validator和旧Web两契约通过；新完整矩阵NOT RUN。旧Unit/Web冻结契约保持，不为旧runtime读取新QOM字段。用户要求bug修完即收尾，新Unit四host API/Web、新完整矩阵和硬件NOT RUN，37/36不关闭，未push | [本轮记录](https://github.com/m5agent/m5stack-esp-emulator/blob/a37342f61c05964c060719a6e35c2d568c828e84/docs/evidence/2026-10-27-flashlight-cold-pad/README.md) |
| `UNIT-01` / 路由历史块提交与主线同步 | 6ca4c158提交后fetch/merge origin/main@f2061759，已同步且无代码变化；未push。初始11436份归档指纹全部保持，独立完整副本以系统Python在/tmp通过根与四child门禁；owner隐私完整scope零命中。gen48当前83source/3f1617与全部历史包/源码记录不变，active/lease0，未新guest/再重载；原字节空白保留，整体Unit/AIFlow继续 | [同步与收尾](https://github.com/m5agent/m5stack-esp-emulator/blob/a37342f61c05964c060719a6e35c2d568c828e84/docs/evidence/2026-10-27-flashlight-route-history/integration/index.json) |
| `UNIT-01` / FlashLight OUT_SEL历史与矩阵命令 | 0046真实MMIO route生命周期撤旧资格/三timer/旧low；独立C旧26case/357checks/152失败、新0，12patch/106source冷QEMU build为3f161756…，复用43依赖缓存/3下载不含QEMU objects。gen47四host Torch/Flash八lane共168次同VM执行及CoreS3 Web14执行/13状态阶段通过；7个optional200空frame体PARTIAL。13会话原cleanup12PASS/1UNCONFIRMED，后者独立finalization证已释放不回写原失败；均ZIP-before-stop、保留精确历史末帧。最终gen47的83source/runtime一致、旧322包文件/408source record原字节保留、active/lease0。平台1220+窄24PASS；独立完整矩阵66PASS/1Core2IMU黑marker FAIL、274checks、无重试/拼补；Xtensa62与旧C6五例来源分开。UNIT-HOST-22 old/new负控及实际PaperColor命令修复通过；38仅限定route历史关闭，37/36/OEN/IOMUX/S1/PWM/硬件/AIFlow/SSE继续。后续仅元数据三路径更新、旧guest/program记录逐字节保留，窄17/文档48/五validator PASS；idle gen48同runtime重载及API/83source读回、active/lease0，无新guest | [分层证据与原始指纹](https://github.com/m5agent/m5stack-esp-emulator/blob/a37342f61c05964c060719a6e35c2d568c828e84/docs/evidence/2026-10-27-flashlight-route-history/README.md) |
| `UNIT-01` / main.mpy块提交与主线同步 | 5be2687a提交后fetch/merge origin/main@f2061759，已同步且无代码变化；未push。最终83份产品SHA与gen46启动receipt一致，active/lease均0，沿用已验runtime无需重载或重复guest；原字节CRLF与归档器失败保留，整体Unit/AIFlow继续 | [同步与收尾](https://github.com/m5agent/m5stack-esp-emulator/blob/a37342f61c05964c060719a6e35c2d568c828e84/docs/evidence/2026-10-27-public-main-mpy/integration/index.json) |
| `UNIT-01` / 公共main.mpy与动态能力 | API1.46受控bootstrap真实bytecode canary、session/固件/runtime/PID/worker绑定、显式base Preview、早拒绝/锁内复验与RESTORE_ERROR撤权；gen45/7c898 CoreS3 stock与兼容固件普通会话+真实Web共14执行（8MPY），同bytes重跑/仅dep变化、if-main/三模块身份、异常/格式拒绝、PIR真实UART/QOM/PNG、取消回同nonce/owner源码通过。最终三个ZIP86成员与精确历史帧/Flash/PID/lease清理通过；Web六阶段mandatoryPASS，8个optional HTTP200空PNG体PARTIAL，不作纹理传输证明。gen46在最终恢复门禁上另验2会话9执行（5MPY）及58ZIP成员/清理，最终平台1218PASS；异常污染guest测试被安全审查拦截，仅宿主负控，不授guest PASS。OpenAPI3.1 null/公开worker投影按766原JSON与48类型控制修正；原fixture/code-map/Preview/快照失败保留，更多主机/固件与AIFlow/SSE继续 | [分层证据](https://github.com/m5agent/m5stack-esp-emulator/blob/a37342f61c05964c060719a6e35c2d568c828e84/docs/evidence/2026-10-27-public-main-mpy/README.md) |
| `UNIT-01` / FlashLight块提交与主线同步 | 50d990ba提交后fetch/merge origin/main@f2061759，Already up to date；4897份原块文件SHA复核，原serial CRLF/空白不归一化。owned idle重载gen43，保留源码/包字节，30 Unit、FlashLight partial/creation-only、API1.45、公共MPY false和包容量1024读回一致；active/lease均0。未新跑guest，route历史缺口UNIT-HOST-38及整体Unit/AIFlow继续 | [同步与重载收据](https://github.com/m5agent/m5stack-esp-emulator/blob/a37342f61c05964c060719a6e35c2d568c828e84/docs/evidence/2026-10-27-flashlight-and-uiflow-base/integration/index.json) |
| `UNIT-01` / FlashLight、显式base与loader诊断 | API1.45严格manifest base、normalized pin与CAS冲突保护；仅非语义顶层created_at允许变化，安全/PSRAM/能力仍完整重验，包容量默认256/显式1–4096且保留历史。gen40候选CoreS3同VM loader诊断11源码阶段/171HTTP/44ZIP成员通过，公共main.mpy仍关。gen42/7c898八个最终Flash/Torch会话60Run、360ZIP成员与精确历史帧/Flash/PID/lease清理通过；15个脉冲程序qualified、17个保持unknown，不是全16码或硬件PASS。CoreS3实际mounted五阶段另通过；optional browser4个空200体单列PARTIAL。新完整矩阵独立67/67、无重试；旧Core2 IMU偶发未自动关闭。平台1162PASS；cold-route、配额、observer304/DOM失败原文保留 | [分层证据与原始指纹](https://github.com/m5agent/m5stack-esp-emulator/blob/a37342f61c05964c060719a6e35c2d568c828e84/docs/evidence/2026-10-27-flashlight-and-uiflow-base/README.md) |
| `UNIT-01` / checkpoint块提交与主线同步 | 9a107c69提交后fetch/merge origin/main@f2061759，Already up to date；8份r2执行源码SHA不变、gen38 active/lease均0，无需重载或重复guest。兼容候选仍未准入，下一块另做真实loader探针，整体Unit/AIFlow继续 | [同步收据](https://github.com/m5agent/m5stack-esp-emulator/blob/a37342f61c05964c060719a6e35c2d568c828e84/docs/evidence/2026-10-27-binary-checkpoint-admission/integration.json) |
| `UNIT-01` / 二进制checkpoint与兼容构建 | API1.44分开main.mpy不可变存储与执行；gen38/850426下四host统一r2双lane：16源码Run、12拒绝、36fresh PIR/UART/QOM/PNG、8ZIP152成员与精确历史帧/Flash/PID/lease清理通过，MPY始终未执行。r1三PASS/superseded与StopWatch圆屏角落oracle FAIL保留。官方固定CoreS3两宏候选pack_all及image/partition检查通过，但未guest准入、stock/能力声明不变；4Relay/FlashLight协议冲突已反馈，研究不授予功能准入 | [分层证据](https://github.com/m5agent/m5stack-esp-emulator/blob/a37342f61c05964c060719a6e35c2d568c828e84/docs/evidence/2026-10-27-binary-checkpoint-admission/README.md) |
| `UNIT-01` / 控制组提交与主线同步 | 9e2dc55b实现及55050f86原始日志提交后fetch/merge origin/main@f2061759，Already up to date；20份本块产品/runner SHA不变。owned idle重载为gen37，29 Unit及五类profile元数据与文件一致，runtime仍850426，active/lease均0；未重跑guest，不授予新执行结论，整体Unit/AIFlow继续 | [同步收据](https://github.com/m5agent/m5stack-esp-emulator/blob/a37342f61c05964c060719a6e35c2d568c828e84/docs/evidence/2026-10-27-preview-controls-and-2relay/integration.json) |
| `UNIT-01` / 托管控制组、U131与相机 | gen36/850426四主机各4Run HUB控制组与7Run 2Relay限定闭环通过；后者精确1512B官方源、GPIO/逐通道计数/两蓝灯、主机输入、取消再跑和精确历史帧SHA。相机四断点与长dt负控/修复、宿主负控通过；取证器RGB565 oracle、无界browser observer、IPC EOF与短按漏采的原失败/不完整轮保留，optional browser bodies缺失单列，不冒充mandatory缺证。新定向7PASS、原完整66/67，Core2单例PASS不拼全通过；硬件/AIFlow调用侧/main.mpy/SSE仍NOT RUN或开放 | [分层证据与原始SHA](https://github.com/m5agent/m5stack-esp-emulator/blob/a37342f61c05964c060719a6e35c2d568c828e84/docs/evidence/2026-10-27-preview-controls-and-2relay/README.md) |
| `UNIT-01` / Web块提交与主线同步 | f058d8d2提交后重新fetch并merge origin/main@f2061759，Already up to date；最终r4的12份产品/runner源码SHA不变，gen34 active/lease均0。整体Unit/AIFlow仍继续，窄屏构图/main.mpy/其它Unit组合等按Backlog推进 | [同步收据](https://github.com/m5agent/m5stack-esp-emulator/blob/a37342f61c05964c060719a6e35c2d568c828e84/docs/evidence/2026-10-27-preview-web-consumer/integration.json) |
| `UNIT-01` / Preview Web消费者 | API1.43完整包只读读取与共享PreviewClient接通Live sessions；gen34/b8de下最终r4两CoreS3 PIR/Relay各5/6实际execution，同PID/固件/VM nonce，外部完整包/真实MPY→Web保留依赖编辑、可信PIR输入/QOM1→0、Relay输出true、Run蓝绿PNG与Web选定像素、取消恢复/续租/关闭通过。537直接HTTP/1317browser、2ZIP含manifest共129成员hash、历史/末帧/Flash/PID/lease0经独审；r1目录401、r2raw-paste oracle误拒与r3旧按钮文字保留。平台1110、client22、program27、Unit23、frame22、create9及旧回归通过；窄屏3D裁切UNIT-HOST-35、SSE/AIFlow/GC/main.mpy仍OPEN，完整矩阵/硬件NOT RUN | [原始证据与精确边界](https://github.com/m5agent/m5stack-esp-emulator/blob/a37342f61c05964c060719a6e35c2d568c828e84/docs/evidence/2026-10-27-preview-web-consumer/README.md) |
| `UNIT-01` / Preview块提交与主线同步 | f510a908提交后重新fetch/merge origin/main@f2061759，Already up to date；clean worktree、17份实际运行源码SHA保持，gen33 active/lease均0。下一块优先UNIT-HOST-34托管Web消费者；整体Unit/AIFlow仍继续 | [同步与清理收据](https://github.com/m5agent/m5stack-esp-emulator/blob/a37342f61c05964c060719a6e35c2d568c828e84/docs/evidence/2026-10-27-preview-run-control/integration.json) |
| `UNIT-01` / 同VM Preview/Run | API1.42增加稳定Preview、持久化幂等/预分配身份/latest-wins、独立raw prompt取消、输入drain/帧fence、managed session与保留保护。gen33/b8de CoreS3 PIR/Relay各6Run意图/4execution、同PID/固件/VM nonce、公共完整包/真实MPY依赖、typed UART/rawQOM/PNG、epoch/gen/key拒绝、运行中取消后再跑及ZIP-before-close/自动ZIP/历史/Flash/PID清理通过；B/C均pending superseded；另1234HTTP的PIR样本在真实包writing确认pad131072B后取消、独立53B新prompt、未publish/START，同VM C/MPY/PIR恢复及31成员ZIP/清理通过；不声称单chunk中断。冻结平台1107、runner44、五validators及独立契约/并发/retention审查通过；8边界旧失败、两个momentary旧算法负控和语义损坏漏根复现保留。SSE/GC/main.mpy/AIFlow及Web新消费者仍OPEN，完整矩阵/硬件NOT RUN | [原始证据与范围](https://github.com/m5agent/m5stack-esp-emulator/blob/a37342f61c05964c060719a6e35c2d568c828e84/docs/evidence/2026-10-27-preview-run-control/README.md)、[API](device-service-api.md#stable-preview-and-asynchronous-runs) |
| `UNIT-01` / checkpoint块提交与主线同步 | 实现提交19f2bdeb后重新fetch/merge origin/main@f2061759，Already up to date；clean worktree、8份验证源码SHA保持。跨日索引日期不一致的原文档失败保留，修正后独立48项文档检查通过。整体Unit/AIFlow工作继续，不将本块或视觉新增数量当全部协议完成 | [同步收据](https://github.com/m5agent/m5stack-esp-emulator/blob/a37342f61c05964c060719a6e35c2d568c828e84/docs/evidence/2026-10-26-visual-refresh-and-checkpoints/integration.json)、[本块范围](https://github.com/m5agent/m5stack-esp-emulator/blob/a37342f61c05964c060719a6e35c2d568c828e84/docs/evidence/2026-10-26-visual-refresh-and-checkpoints/README.md) |

## 2026-10-26

| 工作流 | 结果 | 证据 |
| --- | --- | --- |
| `UNIT-01` / 3681外壳、公共checkpoint与同VM复测 | 固定3681a648外壳14主机/113视觉Unit/287PNG；独立完整r2核278层五类printed-artwork、196LED/44joint、59context全关闭与零资源/回声错误，83配置NOT RUN、Fader slider bridge不支持，28内部协议准入不变。旧基线和AudioPlayer固定色fixture失败均保留精确源码。gen32/b8de下两CoreS3同色灯8execution/14灯56阶段材质与独立raw QOM PASS，Scroll另1execution的API/串口/PNG/材质PASS，但独审因无逐leaf raw QOM保留PARTIAL；HUB遮挡/Encoder光学未验收。公共完整checkpoint保存/查询和同步revision引用新增15宿主HTTP测试；PIR/Relay新实际session各12execution含预期失败，合法4次只引用revision、每例8引用拒绝后B持续，983HTTP完整状态/headers/body核SHA、两ZIP共168成员。先ZIP再purge0，历史/末帧保留、PIDgone与Flash释放。串口seek有界窗口原失败/新通过；平台972、runner19与7前端fixture通过，OpenAPI240refs/59schema通过，独审所报500/503文档遗漏已修。未改QEMU/C，完整矩阵NOT RUN；Preview/Run/latest-wins/独立取消/SSE/AIFlow/GC/main.mpy及UNIT-HOST-29/33/21保持OPEN；仅虚拟设备 | [本块原始证据、失败与范围](https://github.com/m5agent/m5stack-esp-emulator/blob/a37342f61c05964c060719a6e35c2d568c828e84/docs/evidence/2026-10-26-visual-refresh-and-checkpoints/README.md)、[API](device-service-api.md)、[Agent指南](unit-agent-api.md) |
| `UNIT-01` / 默认同色灯与程序能力 | gen31/b8de下最终r3两CoreS3可见session，HUB+Encoder/8Encoder原I2C与直连RGB原RMT各同VM连续4程序，共8 execution/14灯/56阶段材质检查；uniform A/C、非对称B unknown撤色、全灭D、26次browser-only503负控与同程序恢复，原电气数组/独立raw QOM/fresh UART/真实帧分别绑定。两次main.mpy入口409未增execution，零Unit输入回声。2ZIP共46成员/12新鲜串口窗逐字节/SHA核验，先ZIP再stop/purge0；两owned PID退出、Flash释放/末帧历史保留。r3全canvas/直接renderer与RGB可见三灯已看图；HUB投影遮挡与Encoder两灯closeup可读性仍未验收，不称14灯同屏可辨。通用QOM截断不当raw证据；r1帧接口错误/r2截图裁切及独审均保留。平台952项、g版7个Node回归程序与5个生成检查通过；早期snapshot/导航失败保留。API1.40发布program_features；另固定UIFlow/MicroPython源码与gen30 CoreS3三次同VM实验确认普通.py/.mpy导入不运行if-main，独立main.mpy为UNIT-HOST-33 OPEN。不关闭UNIT-HOST-29、Preview/SSE/AIFlow/清场/硬件，完整矩阵本轮NOT RUN | [最终/早期批次、源码与边界](https://github.com/m5agent/m5stack-esp-emulator/blob/a37342f61c05964c060719a6e35c2d568c828e84/docs/evidence/2026-10-26-uniform-led-and-program-capabilities/README.md)、[main.mpy来源](https://github.com/m5agent/m5stack-esp-emulator/blob/a37342f61c05964c060719a6e35c2d568c828e84/docs/evidence/2026-10-26-uniform-led-and-program-capabilities/main-mpy/README.md)、[Agent API](unit-agent-api.md) |
| `UNIT-01` / Scroll限定控制器 | 固定内部FW ae60717a、原UIFlow ScrollUnit，独立CONTROL_SCROLL经真实主机I2C；gen28新b8de冷构建，四主机各22次有限程序/共88次，同PID/固件/VM、count低16/API偏移、TX跨程序续读/增量选择即清零、按键/RGB/改址、越界/overflow/混合请求拒绝及末帧/ZIP/history/Flash释放核验。CoreS3真实Web另验可信canvas按放、计数表单→guest、唯一RGB灯material/glow及实际PNG采样像素到mounted Display、零回声。旧Encoder/8Encoder/Joystick四主机回归通过；新完整矩阵66/67、270/274，Core2 IMU串口正确但marker黑，保留UNIT-HOST-21 OPEN，不用单例拼接。RGB只证quiescent/latest-value，队列/回绕/轴角/bootloader/持久化/地址0未完成；早期LittleFS ABI失败、source256配额429和旧探针均保留。源码容量新增显式1..4096配置，默认256；原记录逐一保留，不关闭自动回收/Preview/SSE/AIFlow或真机 | [范围、原始报告、ZIP与构建收据](https://github.com/m5agent/m5stack-esp-emulator/blob/a37342f61c05964c060719a6e35c2d568c828e84/docs/evidence/2026-10-26-scroll-controller/README.md)、[Agent使用与边界](unit-agent-api.md#scroll-的限定运行时) |
| `UNIT-01` / 同guest文件包与detent | gen24冻结源码下四主机×PIR/Relay八个8787可见session，各12次execution共96预期结果，含故意SyntaxError及4种包失败；另8个stale409不产生execution。相同main.py配A/B/C不同官方编译helper.mpy、普通/namespace模块、JSON/PNG；同PID/固件/VM、原驱动fresh UART/独立QOM/应用图像、复用完整目录/文件重验、异常恢复及8ZIP原始bytes均核验。八owned PID退出、purge0历史/末帧保留、Flash释放/active0；实际QEMU d1ba，未改controller。早期路径API及StopWatch裁切失败保留，最终独立8例不拼接；PNG bytes同guest成功，路径兼容UNIT-HOST-30 OPEN。detent position丢失已修，7项可信vendor fixture/全模型与Panel通过，但synthetic极性无guest电气binding，UNIT-HOST-29仍OPEN。native清场/二进制入口/开机保存/Preview/SSE/AIFlow/SLA/硬件不继承 | [批次、负控、固定源码与检查](https://github.com/m5agent/m5stack-esp-emulator/blob/a37342f61c05964c060719a6e35c2d568c828e84/docs/evidence/2026-10-26-live-package-and-detent/README.md)、[Agent接口](unit-agent-api.md) |
| `UNIT-01` / CoreS3 多 Unit 真实网页边界 | 两组HUB装配另以实际DOM字段输入、REST提交程序验证，共10次预期程序结果、24个逐leaf向量、92次实际POST、168次GET及58份DOM/model快照；原驱动、guest串口、QOM与DOM读回通过。Encoder两灯与8Encoder九灯的QOM/DOM颜色正确，但mounted 3D灯仍默认熄灭、旋转为零，因此功能PASS、整体动画PARTIAL，UNIT-HOST-29保持OPEN。官方链图/内部固件/模型目标未闭合电气链索引到物理光孔映射，30pulses与示例58计数也不足以确定角度；不猜绑定、不把counter写/reset解释为轴运动。两自有会话取ZIP后停止并释放Flash；只覆盖本拓扑，不授予其它主机Web、AIFlow或硬件结论 | [边界负控](https://github.com/m5agent/m5stack-esp-emulator/blob/a37342f61c05964c060719a6e35c2d568c828e84/docs/evidence/2026-10-26-live-unit-preview/unit-web/web-boundary-audit.json)、[固定来源审计](https://github.com/m5agent/m5stack-esp-emulator/blob/a37342f61c05964c060719a6e35c2d568c828e84/docs/evidence/2026-10-26-live-unit-preview/encoder-binding-research/README.md) |
| `UNIT-01` / 四主机同 guest HUB 传感器与控制 | 最终服务PID45439下CoreS3/AtomS3R/StickS3/StopWatch各HUB+ENV III/NCIR/TVOC及HUB+Encoder/8Encoder/Joystick v1.1，共8个可见session、40次程序提交的预期结果、96次逐leaf fixture全部通过；包含故意SyntaxError与恢复，不称40个程序均正常完成。每例同PID/固件/VM nonce、原驱动、精确I2C scan、fresh串口与独立QOM、A/B应用帧；Encoder灯与8Encoder九灯由guest写入，第九灯明确走原register helper。实际QEMU d1ba0063…；runner、加载服务源码收据前后相同，八ZIP成员索引/大小/SHA核验，全部导出JSON无内部mono。八自有guest PID均退出，stopped历史/最后帧保留、Flash释放；并行非本批session不算清理失败，也不冒称全服务idle。原r1保留，最新final独立成批。限这六leaf和拓扑的API/guest/controller路径，不授予六leaf真实Web、其它组合、原IR/Buzzer、物理精度或硬件结论 | [最终批次与来源](https://github.com/m5agent/m5stack-esp-emulator/blob/a37342f61c05964c060719a6e35c2d568c828e84/docs/evidence/2026-10-26-live-unit-preview/README.md)、[Agent API](unit-agent-api.md) |
| `UNIT-01` / QEMU按需共享预览 | 显式 `max_age_ms=1..1000`共享同generation的按需帧样本，ETag/304与采集时程序身份冻结；默认GET即使带条件头仍fresh，evidence/wait/stop保留直采。最终真实CoreS3通过八观察者共享样本、同像素新execution的304与新context、不同应用像素、program/reset失效和停止历史；wait及ZIP不导出内部mono。前端每visual独立有界请求、owner/慢body/decode/销毁隔离等13组browser fixture通过，资源version更新后重跑通过且当前源码SHA一致；该fixture不执行guest。独立真实Web的CoreS3 PIR/Relay两例通过125ms显式共享请求、实际B execution/采集时间、PNG→模型屏幕像素、双向Unit、DOM错误/串口与SyntaxError恢复；本轮观察200=32、304=90，非吞吐或SLA。预览序号仅计cache发布，不代表guest重绘、原子Unit快照、固定FPS或SLA；无后台producer，Tab5/network显式共享请求拒绝，旧fresh路径保留。Preview/Run资源、SSE、AIFlow接入、多文件/保存、其它leaf真实Web和硬件均继续开放 | [实际条件请求、Web与fixture范围](https://github.com/m5agent/m5stack-esp-emulator/blob/a37342f61c05964c060719a6e35c2d568c828e84/docs/evidence/2026-10-26-live-unit-preview/README.md)、[API评估计划](plans/2026-10-26-aiflow-live-preview-api.md) |
| `UNIT-01` / Web 实时程序与四主机 | `program_mode=uiflow-live` 的 CoreS3/AtomS3R/StickS3/StopWatch × PIR/Relay 八个实际可见会话、40次程序提交的预期结果全部通过；每例同 PID/固件、VM nonce、单次bootstrap、原驱动/QOM、不同应用帧、无限循环替换、故意SyntaxError与恢复及ZIP内revision/source均核验。实际QEMU为d1ba0063…，四主机各自固件SHA在原报告，不能混成同一镜像。独立真实CoreS3 Web两例通过创建/编辑/替换、PIR网页输入到guest、Relay guest输出到网页、实际frame→模型display白/绿角像素、错误可见与恢复、先ZIP后stop和保留历史；page/resource errors均空。`browser-r2` 初始picker跨主机竞态曾错选custom、返回409，修复后完整13项browser fixture与最终实际浏览器两例通过，记UNIT-HOST-27 FIXED。40次中包含预期语法失败，不称40个程序均正常完成；其它Unit、多文件/.mpy/Run Always、AIFlow/Preview/SSE、native/IRQ/thread完整清理、SLA与硬件均不继承 | [实际Web、四主机、负控与fixture](https://github.com/m5agent/m5stack-esp-emulator/blob/a37342f61c05964c060719a6e35c2d568c828e84/docs/evidence/2026-10-26-live-program-web-and-hosts/README.md)、[Agent API](unit-agent-api.md) |
| `UNIT-01` / 公开外壳更新48667b7 | 固定公开Git对象`48667b728736fbfd4365a06575473ce538d3c972`，14主机/29视觉Unit；65许可PNG精确路径/来源SHA256/notice hash、210 JS及资源闭包，Three同锁包SHA512认证的DecalGeometry全部核验。Chrome156.0.8078.48下65图image.decode、51层主机实际raster材质ready、14主机frame/input和29Unit挂载/反馈无回声/释放通过，无页面错误或404。Scroll/Roller485仅视觉，内部协议库仍27种；固定快照check与9项导入故障控制通过。本块没有QEMU/固件/硬件执行，不升级原功能证据或逐设备机械保真 | [导入清单与浏览器证据](https://github.com/m5agent/m5stack-esp-emulator/blob/a37342f61c05964c060719a6e35c2d568c828e84/docs/evidence/2026-10-26-visual-refresh-48667b7/README.md) |
| `UNIT-01` / UIFlow 同 guest 实时运行 | AtomS3R 同一初始化固件 `f9880647…`、实际 QEMU `d1ba0063…`、同 PID/VM 连续五次 `/program`，原生 UART FIFO/raw-paste。有限程序、PIR 原驱动 motion 1/0/1 新鲜串口、无限循环替换、不同应用帧、故意 SyntaxError 与恢复均通过；VM 内存nonce、单ROM/bootstrap保持，独立 execution/revision/source 及停止前ZIP的25成员大小/SHA均核验，停止后历史保留/Flash释放。单机暖VM提交确认0.190–0.328秒（5样本，非首帧/P95/SLA）；其它主机、Run Always/多文件/.mpy/AIFlow集成与硬件不继承 | [同 guest 证据与重放](https://github.com/m5agent/m5stack-esp-emulator/blob/a37342f61c05964c060719a6e35c2d568c828e84/docs/evidence/2026-10-26-uiflow-live-program/README.md)、[Agent API](unit-agent-api.md) |
| `UNIT-01` / AIFlow预览细则与客户端响应隔离 | session/input epoch、旧输入队列及跨session装配所有权已修复；同一新测试对旧产品稳定复现GET晚到覆盖POST，新产品完整browser34 checks、annotation17、audio113 assertions/15 checks、bridge31 POST/12 trusted events通过。均为离线/browser fixture，无新guest或硬件执行；本地epoch不建立server快照全序。独立复核AIFlow947d及脏树十文件稳定SHA：新增data snapshot/SSE不等于代码checkpoint；runner结束后file_ready及当前workspace下载仍需新契约。Preview/Revision/Run、输入admission/幂等/重启/GC/帧身份已细化为方案，未实现 | [客户端证据与只读收据](https://github.com/m5agent/m5stack-esp-emulator/blob/a37342f61c05964c060719a6e35c2d568c828e84/docs/evidence/2026-10-26-preview-client-fencing/README.md)、[预览首版方案](plans/2026-10-26-aiflow-live-preview-api.md) |
| `UNIT-01` / 启动取消与预览基础 | 宿主生命周期事务/单调取消/pending自动收尾、停止意图版本、Network子进程原子收据与可取消等待、重附着identity保留、Tab5 reset失败清理、lease失败重试及draining/janitor所有权已实现。真实8787/gen13下十九文件AtomS3R+PIR冷准备先ZIP再一次stop，约1.007秒pending确认且容量/lease仍占用，准备退出自动terminal、零booting/running/Flash；同镜像新guest再验证PIR true/false新鲜UART+QOM、原生帧、停止前ZIP与历史/Flash/PID/idle。固件240d70e6…、source2786bbcc…、实际QEMU d1ba。宿主回归与其它后端现场执行分列，不关闭Preview/Revision/Run/同guest重部署、首帧SLA或硬件 | [取消修复与实际会话](https://github.com/m5agent/m5stack-esp-emulator/blob/a37342f61c05964c060719a6e35c2d568c828e84/docs/evidence/2026-10-26-session-cancellation-f309/README.md)、[契约](device-service-api.md) |
| `UNIT-01` / AIFlow实时预览架构评估 | emulator0a6a与AIFlow最终b499源码只读核对；24原ZIP timeline创建→READY14.428–21.341秒、中位16.984秒，创建→booting为12.073–18.821秒；非首帧/AIFlow全链路/SLA。实际DeviceSession方法+Event屏障确认stop返回后provision仍mock launch、running和重建Flash，零API/QEMU/guest。AIFlow已有SSE但file_ready在任务结束发，缺不可变checkpoint/virtual目标；拟定Preview/Revision/Run、fence与缓存分发，未实现/部署 | [只读审查与时序](https://github.com/m5agent/m5stack-esp-emulator/blob/a37342f61c05964c060719a6e35c2d568c828e84/docs/evidence/2026-10-26-aiflow-preview-api-audit/README.md)、[实施门禁](plans/2026-10-26-aiflow-live-preview-api.md) |
| `UNIT-01` 三主机八种 Unit 源码控制 | AtomS3R/StickS3/StopWatch各PIR、DualButton、LIMIT、Key、RGB、Fan、RS485、HUB（ENV/NCIR/TVOC）共24可见源码session全PASS，均原驱动；Fan3为cba上下文，其余21在PWM块提交0a6a并fetch/merge origin/main@f206175（Already up to date）后fresh准备，481依赖字节完全相同，实际d1ba/gen12。每例19caller保留、完整原host/IO oracle、BMI内部总线、字体/canvas、真实DOM/HTTP与controller数据面、新鲜串口上下界/source-pin/PID/ZIP-before-stop/history/Flash/idle核对。RGB短帧及RS485超FIFO负控保留，Fan/RGB零正向input POST。两间接依赖源码仅精确SHA/Git blob omission，原实测数据不清洗；可读性仅捕获帧，三主机HUB数字token连续性PARTIAL。其它组合、ADC/Thermal、IR/Buzzer、hotplug/硬件不转授 | [24组合证据](https://github.com/m5agent/m5stack-esp-emulator/blob/a37342f61c05964c060719a6e35c2d568c828e84/docs/evidence/2026-10-26-unit-source-host-io-d1ba/README.md)、[60份场景请求](unit-agent-api.md#三主机新增八种-unit) |
| `UNIT-01` PWM 初始化路由与共享回归 | `0038` 独立冷构建d1ba，八patch正反重放、18组实际C片段通过。同固件81187ab0…/caller CAS9466b760…/相同请求，无后续setter；gen11旧29d8八窗0Hz/0%为FAIL_REPRODUCED，gen12新d1ba八窗2000Hz/0%为PASS，guest getter均2000/0；实际HTTP/DOM/source-pin/PID/worker/ZIP-before-stop/history/Flash/idle有独审。每批约4秒guest窗口，不是60秒soak或首瞬间连续。新完整原矩阵单次67/67、274/274首次通过，summary SHA0d518bee…，Core2实际marker绿；388输入、204最终Python源码和134 PNG/PPM核验通过。完整ROM/C6仅mid/end、PaperColor RGB launch为静态重构、六IR例mutable Flash hash变化均保留；旧66/67不改写，完整PWM周期/原Buzzer/偶发根因/硬件仍OPEN。平台652/652、零skip及四generated checks PASS | [A/B与冷构建/完整矩阵](https://github.com/m5agent/m5stack-esp-emulator/blob/a37342f61c05964c060719a6e35c2d568c828e84/docs/evidence/2026-10-26-unit-pwm-route-d1ba/README.md)、[问题范围](unit-integration-host-issues.md) |
| `UNIT-01` 同步主线后三主机源码 API | 当前工作块提交 `0fe6a013b7ca040583339ef7827d4daf8e3810dc` 后重新fetch并merge `origin/main@f2061759897955e6017d4aa2a41bd5ba962c35b6`，结果Already up to date、工作树干净；以该同步后HEAD全新准备九组合。AtomS3R/StickS3/StopWatch各Button/Relay/ENV III的九个独立gen11/29d8源码API session全部PASS，批次终态2026-10-26T04:53:58.569276Z，最终离线check通过。原host_probe四文件逐字保留、只生成主机配置，原BMI前后/loop、ENV精确scan与两fresh向量、Button四边沿、Relay双输出及原ZIP断言完整；三实际base、caller source pin、真实Web共30 POST、直接PID、停止前ZIP、purge0历史/最后帧、Flash释放和owned PID退出/active0均绑定。原生帧尺寸与非空核对；不扩大到各主机其它24种Unit、所有UI状态可读性、原子快照、完整矩阵或硬件 | [九组合与精确来源](https://github.com/m5agent/m5stack-esp-emulator/blob/a37342f61c05964c060719a6e35c2d568c828e84/docs/evidence/2026-10-26-unit-source-hosts-29d8/README.md)、[源码请求与接线](unit-agent-api.md#三主机buttonrelayenv-iii)、[同步收据](https://github.com/m5agent/m5stack-esp-emulator/tree/a37342f61c05964c060719a6e35c2d568c828e84/docs/evidence/2026-10-26-unit-source-hosts-29d8/sync) |
| `UNIT-01` 外部 Agent 源码 API 扩展 | gen11/29d8 CoreS3 二十五个独立 source HTTP→compose→source-pin session：七传感器、九 IO、四控制与两种显式 custom 共22功能PASS，Thermal missing-fixture另1负控PASS；原IR为REVIEW_REQUIRED/protocol PASS、独审OBSERVED_PROTOCOL_PASS_RISK_OPEN，历史GC风险OPEN；原Buzzer自然timer-zero FAIL，旧harness误要求输入POST的browser_error单列，手动OFF不补PASS。结合首轮选定27种源码场景为25原驱动+IR/Buzzer两custom，非单次原版27全绿。四控制只做可逆display-only调整；Fan动画限100% duty观测段，Heart只证raw IR/red/FIFO，Thermal功能使用显式raw fixture。实际同source/guest/controller/Web、直接PID、停止前ZIP与清理均绑定；其余三主机仅离线compose，完整矩阵仍66/67、270/274，hardware NOT RUN | [扩展范围与冻结输入](https://github.com/m5agent/m5stack-esp-emulator/blob/a37342f61c05964c060719a6e35c2d568c828e84/docs/evidence/2026-10-26-unit-source-api-expanded-29d8/README.md)、[27种源码请求](unit-agent-api.md#已验证的-27-种源码场景)、[原驱动风险批](https://github.com/m5agent/m5stack-esp-emulator/tree/a37342f61c05964c060719a6e35c2d568c828e84/docs/evidence/2026-10-26-unit-source-api-expanded-29d8/batches/original-risk2-r1)、[Thermal负控](https://github.com/m5agent/m5stack-esp-emulator/tree/a37342f61c05964c060719a6e35c2d568c828e84/docs/evidence/2026-10-26-unit-source-api-expanded-29d8/batches/thermal-negative-r1) |
| `UNIT-01` 原驱动上游源码查证 | 2026-10-26首末远端查询均固定m5stack/uiflow-micropython master@3a86d8f611b3639cca755a933e01a5a829771ef1；五个固定commit源码HTTP200。Buzzer/IR wrapper与vendored逐字相同，Haptic/SoftTimer/IR native与补丁依据同字节；callback参数与IR保活模式仍在，两custom patch零fuzz dry-run通过。此为只读源码调查，不推断所有port或最新发行固件失败，不替代运行验证 | [固定源码报告与hash](https://github.com/m5agent/m5stack-esp-emulator/blob/a37342f61c05964c060719a6e35c2d568c828e84/docs/evidence/2026-10-26-unit-source-api-expanded-29d8/research/upstream/report.json) |
| `UNIT-01` 外部 Agent 源码 API 首批 | 合入主线 `f206175`（21提交、merge `c53950a`）后，gen11/29d8 的 CoreS3 Button/Relay/ENV III/RGB/Encoder 五例源码 HTTP→固件→sourcepin session→guest/QOM/Web→ZIP/清理全部 PASS；RGB 完整/短帧/完整原负控保留。指南逐字 Button 与 HUB+ENV III+NCIR 两个独立 session 也 PASS，自动 boot 与两个 leaf 的 fresh 串口/独立 I2C 计数/互不改输入核对；加独立 Button 预检共八会话、七种 Unit。PID 退出、Flash false、历史与 ZIP 来源绑定；限 CoreS3，本批非硬件/全矩阵门禁 | [调用指南](unit-agent-api.md)、[原始来源与范围](https://github.com/m5agent/m5stack-esp-emulator/blob/a37342f61c05964c060719a6e35c2d568c828e84/docs/evidence/2026-10-26-unit-source-api-29d8/README.md) |
| `UNIT-01` S3 getter 与浏览器试听 | 七层源码冷构建 `29d8f6ec…`、106源及完整正反重放通过。相同 `3ce76c80…` guest 在 gen9/a8fe 与 gen10/29d8 各60 sample/480raw；修复后六档 getter/MMIO一致，严格QOM窗口76/75分别核对。独立显式zero setter+20s准备窗固件 `43e0be7b…` 的实际Chrome六档试听、默认静音/用户启用/停止context关闭通过；无额外产品POST。旧四次接入/时序失败均保留；原Buzzer.once与初始化QOM仍OPEN。新完整矩阵66/67、270/274，Core2 IMU单例复测PASS，不拼成全量通过；hardware NOT RUN | [本轮范围与清单](https://github.com/m5agent/m5stack-esp-emulator/blob/a37342f61c05964c060719a6e35c2d568c828e84/docs/evidence/2026-10-26-unit-ledc-audio-29d8/README.md)、[完整回归与复测](https://github.com/m5agent/m5stack-esp-emulator/blob/a37342f61c05964c060719a6e35c2d568c828e84/docs/evidence/2026-10-26-unit-ledc-audio-29d8/regression/aggregate.json)、[主机问题](unit-integration-host-issues.md) |
| `UNIT-01` 三主机传感器收敛检查 | 18 条精确 host_validation 合入后，平台 558 项与 Unit 离线 172 项通过；Node 读数语义/读数桥/恢复 17+39+23 项及 Web 输入桥契约通过，coverage/catalog/profile/snapshot 四检查通过。三主机实时 inventory 已读回这 18 条 SENSOR 结果，整体仍 implemented；主目录 main 干净。QEMU 未修改，本批完整矩阵 NOT RUN。外部 agent-work-logs 按用户明确指示跳过，不作为文档交付阻塞 | 本地检查 `.work/unit-host-sensors-final-checks-20261026-r1/`；[仓内证据与清单](https://github.com/m5agent/m5stack-esp-emulator/blob/a37342f61c05964c060719a6e35c2d568c828e84/docs/evidence/2026-10-26-unit-host-sensors-gen9-a8fe/README.md)；完整 UNIT-01 仍进行中 |
| `UNIT-01` 三主机六传感器实际执行 | AtomS3R/StickS3/StopWatch × Color/ToF/NCIR/Heart/TVOC/Ultrasonic-I2C 的完整 18 组合通过 gen9/a8fe 可见会话，无重试。独审核对 36 个 fresh 串口向量、84 次真实产品 POST、93 条 READY 前负控、294 项原 controller 断言及 18 个直接 PID；源/工具链/VFS/adapter、内部 BMI、ZIP 与实际停止历史绑定。18 张历史原生帧及两张不同的 Heart controller 帧逐张看图，可读性只覆盖这 20 图；Heart 零值暂态仍 OPEN，三路帧分别取证，不称原子一致。18 owned PID 已退出、active0、Flash 默认释放；hardware NOT RUN，原准备记录和初版错误帧等式的独审 FAIL 均保留 | [范围、清单与实际归档](https://github.com/m5agent/m5stack-esp-emulator/blob/a37342f61c05964c060719a6e35c2d568c828e84/docs/evidence/2026-10-26-unit-host-sensors-gen9-a8fe/README.md)、[精确主机元数据](../platform/units/runtime-profiles.json)、[主机问题](unit-integration-host-issues.md) |
| `UNIT-01` 本轮收敛验证 | 平台544项、Unit离线161项、文档契约39项和Node读数/桥/恢复17+39+23项通过；coverage/catalog/profile/snapshot四检查及diff检查通过。两次导航/源码快照格式失败保留，修复后全平台重跑通过。本轮6个owned runtime已退出、活动会话0；QEMU未改，完整矩阵本轮NOT RUN。整体目标仍进行中 | 本地收敛记录 `.work/unit-expanded-final-checks-20261026-r1/convergence.json`；两份新证据归档在仓内，预期外部工作日志仓库不存在，未声称外部归档 |
| `UNIT-01` 扩展同 guest 读数 | 显式跨批选择9款原批成功记录和Light/Thermal新双例批次，共11款通过；225外层检查、27新鲜phase GET/body、25串口offset及11ZIP核验。Light真实5POST且首前GET证明False；Thermal双rawfixture经guest768像素/9样本计算，rail仍仅控制字/ready。原Light失败保留；111PNG完整解码，20张额外大fullPage图不套用原Checker的用途上限，也不称构图验收 | [白名单归档与独审边界](https://github.com/m5agent/m5stack-esp-emulator/blob/a37342f61c05964c060719a6e35c2d568c828e84/docs/evidence/2026-10-26-unit-readout-expanded-a8fe/README.md) |
| `UNIT-01` Buzzer once | natural与独立trace诊断分别绑定固件SHA；trace直接捕获frozen scheduler调用Haptic的参数TypeError及线程退出。原版d06e243c…在收紧的自然零窗口下FAIL；显式custom wrapper 1be66530…六阶段PASS，默认原镜像字节不变，原vendor/frozen/QEMU不改。PWM getter恒0与QOM非零的差异仍OPEN，SDK dirty来源未完整绑定 | [原版负控、custom与诊断分层](https://github.com/m5agent/m5stack-esp-emulator/blob/a37342f61c05964c060719a6e35c2d568c828e84/docs/evidence/2026-10-26-unit-buzzer-once-a8fe/README.md)、[显式补丁](../patches/uiflow2-unit-buzzer/README.md) |
| `UNIT-01` 可复用传感器入口 | 三主机×六传感器18份正式准备镜像与离线候选逐字节相同，原9驱动与初始化/负控/采样链保留。完整VFS、源/工具链与配置恢复前后显式绑定；默认预检/未准入execute观测0 API。18组合仍BLOCKED，guest/Web/BMI/字宽/可读性均NOT RUN；新增测试造成旧源清单漂移时按预期拒绝，重新准备后独审通过 | [入口与限制](../tests/units/README.md)、[离线故障控制](../tests/units/test_host_sensor_preparation.py)；本地receipt `.work/unit-host-sensors-independent-review-20261026/receipt-r2.json` |
| `UNIT-01` 可复用控制类入口 | prepare `c19cf0c9…` / runner `53db1e39…`：三主机五款共 15 个离线镜像与已验证版本逐字节一致，默认预检观测到零 HTTP/socket/子进程；平台 544 项与 Unit 工具 84 项通过。StopWatch/8Encoder 代表例经新入口通过，保留原始停止历史和 health body；原始会话包仅本地保留，本项不授予新增可外发运行结论或主机准入 | [准备/执行说明](../tests/units/README.md)、[漂移与文件反例](../tests/units/test_host_control_preparation.py)；本地记录 `.work/unit-host-control-entry-validation-20261026-r1/`，外部工作日志未归档 |
| `UNIT-01` 固定视觉源 | 公开 commit `48ab992f5ff63c1a91296051e1afcb5959877903` 的 14 主机/27 Unit 接入，浏览器像素、输入意图、装配、异步竞争与释放检查通过；只证明浏览器集成 | [浏览器报告](https://github.com/m5agent/m5stack-esp-emulator/blob/a37342f61c05964c060719a6e35c2d568c828e84/docs/evidence/2026-10-26-visual-model-integration/README.md) |
| `UNIT-01` 首批 guest | CoreS3 Button、Relay、ENV III 通过同 guest 的输入 GPIO、输出电平和官方传感器补偿路径，非空画面、停止前 ZIP、冻结 Unit contract 和 `purge=0` 历史均保留；完整矩阵、其他主机和硬件 `NOT RUN` | [首批证据](https://github.com/m5agent/m5stack-esp-emulator/blob/a37342f61c05964c060719a6e35c2d568c828e84/docs/evidence/2026-10-26-unit-runtime/README.md)、[hash 汇总](../tests/units/evidence-2026-10-26-service-first3.json) |
| `UNIT-01` 构建基础 | 固定公开 QEMU commit `40edccac415693c5130f91c01d84176ae6008566`，5 层补丁的正反向应用与 106 源文件比对通过；独立冷构建成功。冷构建不替代固件功能验证，执行 hash 与构建目录分别记录 | [bootstrap 与边界](../patches/qemu-unit-runtime/README.md) |
| `UNIT-01` 冻结运行时复跑 | Xtensa SHA `1880891da692de06612aa0a10b2026c0209875f4641e837df29dc818bb3ac81d` 上首批 `3/3`、控制类 `5/5`、传感器 `7/7` / `114` 断言、I/O `11/12` 正向通过；IR 保持分层 PARTIAL。每例保留串口、帧、停止前 ZIP 与历史；直接 PID 采样与固定 worker generation 的间接运行时关联分别声明，不虚构逐 PID 证明 | [first3](https://github.com/m5agent/m5stack-esp-emulator/blob/a37342f61c05964c060719a6e35c2d568c828e84/docs/evidence/2026-10-26-unit-first3-final/summary.json)、[controls](https://github.com/m5agent/m5stack-esp-emulator/blob/a37342f61c05964c060719a6e35c2d568c828e84/docs/evidence/2026-10-26-unit-controls-final/summary.json)、[sensors](https://github.com/m5agent/m5stack-esp-emulator/blob/a37342f61c05964c060719a6e35c2d568c828e84/docs/evidence/2026-10-26-unit-sensors-final/aggregate.json)、[I/O 与保留尝试](https://github.com/m5agent/m5stack-esp-emulator/blob/a37342f61c05964c060719a6e35c2d568c828e84/docs/evidence/2026-10-26-unit-io-final/README.md)、[exact source replay](https://github.com/m5agent/m5stack-esp-emulator/blob/a37342f61c05964c060719a6e35c2d568c828e84/docs/evidence/unit-runtime-source-replay-20261026.json) |
| `UNIT-01` 服务冻结元数据 | 修复 `flashing` 或尚无运行快照即终止时 `/units` 缺少 session 冻结定义与 hash；回归覆盖三种状态，运行读数继续 unavailable。只在确认无活动会话后重启同 binary，generation 6 与新源码 hash 独立记录 | `platform/tests/test_unit_service_state.py`、[generation 6 receipt](https://github.com/m5agent/m5stack-esp-emulator/blob/a37342f61c05964c060719a6e35c2d568c828e84/docs/evidence/unit-service-generation6-20261026.json) |
| `UNIT-01` 共享控制器完整回归 | 初轮 `53 PASS / 14 FAIL` 保留；13 项由刷新 reference 的 LittleFS VFS 偏移变化引起，改为解析实际分区表后定向 `13/13 PASS`。另一项 Core2 SoftI2C handoff 回归由独立 `0036` 单行修复；六层 patch 的 fresh replay、106 源文件和正反向检查通过。新冻结 Xtensa `a8fe15db…` / RISC-V `ff6c2ef7…` 的独立全量单次执行 `67/67 cases`、`274/274 checks PASS`，全部首次通过、binary start/end 一致；不是前两轮拼接，不关闭 Core2 legacy WDT 或真机验证 | [三轮 aggregate](https://github.com/m5agent/m5stack-esp-emulator/blob/a37342f61c05964c060719a6e35c2d568c828e84/docs/evidence/2026-10-26-unit-shared-regression/aggregate.json)、[全量 run](https://github.com/m5agent/m5stack-esp-emulator/blob/a37342f61c05964c060719a6e35c2d568c828e84/docs/evidence/2026-10-26-unit-shared-regression/full-core2-compat/run-summary.json)、[源码重放](https://github.com/m5agent/m5stack-esp-emulator/blob/a37342f61c05964c060719a6e35c2d568c828e84/docs/evidence/unit-runtime-source-replay-core2-compat-20261026.json)、[Core2 A/B](https://github.com/m5agent/m5stack-esp-emulator/blob/a37342f61c05964c060719a6e35c2d568c828e84/docs/evidence/2026-10-26-core2-soft-i2c-handoff/README.md) |
| `UNIT-01` CoreS3 严格显式选择 | 冻结 Xtensa `a8fe15db…` 上，gen7 固定 16 个成功记录与 gen8 固定 11 个补测记录组成明确的 27 项选择；strict-direct CLI exit 0，guest/controller、live-browser、bridge 三层各 27 PASS。核对 266 条 guest 断言、189 条 Web 断言、617 个浏览器快照与全部 ZIP/hash/PNG；原轮非一次全绿运行。IR 仅选择明确 custom callback-root guest，不升级原发布驱动结论 | [selection/summary 与边界](https://github.com/m5agent/m5stack-esp-emulator/blob/a37342f61c05964c060719a6e35c2d568c828e84/docs/evidence/2026-10-26-unit-final-selection-a8fe/README.md)、[原轮](https://github.com/m5agent/m5stack-esp-emulator/blob/a37342f61c05964c060719a6e35c2d568c828e84/docs/evidence/2026-10-26-unit-web-cohort-a8fe/README.md)、[gen8 补证](https://github.com/m5agent/m5stack-esp-emulator/blob/a37342f61c05964c060719a6e35c2d568c828e84/docs/evidence/2026-10-26-unit-web-supplement-gen8-a8fe/README.md) |
| `UNIT-01` 启动与浏览器同步修复 | 确定性 A/B 复现启动线程与早期 frame/units 请求争抢 QMP 连接；同锁复用和失败 socket 关闭后 5/5 回归通过（ResourceWarning 作 error）。真实 11 项补测全过，另用仅增加未导入元数据模块的新 Button 固件执行自然冷写入；同会话初始 flashing 截图、自然 running、4 次真实手势/POST、GPIO/ZIP/历史全部通过，无刷新。初始 disabled 来自截图目视，未伪造数字 DOM receipt | [QMP A/B](https://github.com/m5agent/m5stack-esp-emulator/blob/a37342f61c05964c060719a6e35c2d568c828e84/docs/evidence/2026-10-26-qmp-startup-connection/README.md)、[readiness/Linux 进程证明](https://github.com/m5agent/m5stack-esp-emulator/blob/a37342f61c05964c060719a6e35c2d568c828e84/docs/evidence/2026-10-26-unit-web-readiness-regression/README.md)、[独立冷写入](https://github.com/m5agent/m5stack-esp-emulator/blob/a37342f61c05964c060719a6e35c2d568c828e84/docs/evidence/2026-10-26-unit-web-flashing-gen8-a8fe/README.md)、[gen8 receipt](https://github.com/m5agent/m5stack-esp-emulator/blob/a37342f61c05964c060719a6e35c2d568c828e84/docs/evidence/unit-service-generation8-20261026.json) |
| `UNIT-01` 跨主机九组合 | AtomS3R、StickS3、StopWatch 各自的 Button/Relay/ENV III 在 gen9 的九个独立可见 session 中严格功能 `9/9 PASS`，无失败或重试；每例同 session/firmware/direct PID、guest 控制器、真实 Web、ZIP 和历史绑定。九张 native frame 完整；三张 ENV 浏览器截图的卡片标题上缘被 sticky header 遮挡，framing 单列 `PARTIAL`，不升级成完整视觉验收。仅这九组合通过，其余每 host 的 24 Unit 未运行 | [归档与范围](https://github.com/m5agent/m5stack-esp-emulator/blob/a37342f61c05964c060719a6e35c2d568c828e84/docs/evidence/2026-10-26-unit-host-web-gen9-a8fe/README.md)、[视觉边界](https://github.com/m5agent/m5stack-esp-emulator/blob/a37342f61c05964c060719a6e35c2d568c828e84/docs/evidence/2026-10-26-unit-host-web-gen9-a8fe/visual-review.json) |
| `UNIT-01` 前端故障恢复 | 异步 shell 以独立 mount 隔离 DOM，晚到拒绝与已提交图像异常清理；本客户端 momentary 松开意图在失败后以一次有界补偿恢复。23/23 确定性故障回归通过；单个 gen9/a8fe CoreS3 Button 实际 session 验证晚到模型后保留同 SHA 的 2D 帧、恢复挂载、丢失一次 release 后 controller 仍按住、一次补偿使 guest GPIO 释放，普通手势仍两 POST、无轮询 echo。23项命名源执行前后相同，PID/firmware/worker、全部ZIP成员/CRC/hash绑定；停止前取证、purge0保留历史并释放Flash，active0。物理硬件NOT RUN，同键多客户端仲裁仍开放 | [离线回归及源码阶段](https://github.com/m5agent/m5stack-esp-emulator/blob/a37342f61c05964c060719a6e35c2d568c828e84/docs/evidence/2026-10-26-frontend-recovery-regression/README.md)、[真实故障专项](https://github.com/m5agent/m5stack-esp-emulator/blob/a37342f61c05964c060719a6e35c2d568c828e84/docs/evidence/2026-10-26-unit-web-recovery-a8fe/README.md) |
| `UNIT-01` 静态读数语义与浏览器 | 12款标量展示改为画布外rail，严格校验冻结定义、running/live/guest-QOM/available与范围；模拟输入、固件输出、Thermal模型/寄存器状态分别标注。17项语义、23项P2恢复、5种源码负控通过；四个当前源browser suite通过，46 PNG完整解码。只证明离线/fixture与placement，nested原housing互叠仍OPEN | [语义审核](https://github.com/m5agent/m5stack-esp-emulator/blob/a37342f61c05964c060719a6e35c2d568c828e84/docs/evidence/2026-10-26-unit-readout-semantic-review/README.md)、[浏览器回归](https://github.com/m5agent/m5stack-esp-emulator/blob/a37342f61c05964c060719a6e35c2d568c828e84/docs/evidence/2026-10-26-unit-readout-browser-regression/README.md) |
| `UNIT-01` 同guest实时读数 | gen9/a8fe CoreS3两个实际session：ENV III六次产品POST、两fresh向量，Relay零输入POST、guest输出false/true。实际HTTP/QOM/Panel/readout对齐，文字命中不增mutation，停止后实时字段清空；ENV16/Relay17外层检查及各6项controller检查全过。独立330项审查验证26冻结源、28工件、20 ZIP成员与16磁盘PNG；两session stopped/Flash释放/active0。整页framing PARTIAL，各通道异步抓取不证明原子LCD/DOM一致性；不升级其他10款或其他主机 | [实际读数归档](https://github.com/m5agent/m5stack-esp-emulator/blob/a37342f61c05964c060719a6e35c2d568c828e84/docs/evidence/2026-10-26-unit-readout-live-a8fe/README.md)、[独立审查](https://github.com/m5agent/m5stack-esp-emulator/blob/a37342f61c05964c060719a6e35c2d568c828e84/docs/evidence/2026-10-26-unit-readout-live-a8fe/independent-review.json) |
| `UNIT-01` 读数收敛检查 | 读数推广阶段的完整平台544项、文档契约39项、读数17项与前端恢复23项通过；runtime/peripheral/profile/snapshot四项检查及diff检查通过。此记录早于后续HUB布局和证据契约改动，未改冻结QEMU；本批不重复共享控制器67项矩阵，也不授予新设备/固件或硬件结论 | [检查命令、原始日志来源与结果](https://github.com/m5agent/m5stack-esp-emulator/blob/a37342f61c05964c060719a6e35c2d568c828e84/docs/evidence/2026-10-26-unit-readout-live-a8fe/verification/summary.json) |
| `UNIT-01` HUB限定布局与长卡片取图 | CoreS3单层直连HUB、ENV/ToF/Color四档展开，原生Button手势/focus、可选布局异常隔离和嵌套生命周期13组PASS；6144条实际线缆表面采样段0壳体命中，错误走线负控58命中后恢复0。两源精确promote后model/panel/bridge/mount/实际产品HUB五项PASS，36命名源与202 vendor资产无漂移；新增运行依赖纳入后续freeze，原归档不改。长卡片标题真实命中、完整1483px PNG/400px viewport与旧bridge隔离负控通过。仅浏览器/fixture；其他排列/主机、手机触控舒适度与物理等价未关闭 | [候选历史、合入回归与范围](https://github.com/m5agent/m5stack-esp-emulator/blob/a37342f61c05964c060719a6e35c2d568c828e84/docs/evidence/2026-10-26-unit-hub-layout/README.md) |
| `UNIT-01` AtomS3R 控制类原批 | gen9/a8fe 五个独立可见session功能5/5 PASS；CardKB 413次真实POST、四键表/修饰锁，RFID2多UID/认证/读写/错误路径通过。380项执行源、直接PID/worker、Web/ZIP/帧与实际停止历史绑定，Flash默认释放。20张磁盘PNG与五ZIP完成复核；原生多行文本覆盖，可读性PARTIAL。原始准备字段不回填，由显式功能证据契约和五份normalization receipt区分；新显示固件与其余主机未继承 | [原批与范围](https://github.com/m5agent/m5stack-esp-emulator/blob/a37342f61c05964c060719a6e35c2d568c828e84/docs/evidence/2026-10-26-unit-atom-controls-r1-a8fe/README.md)、[严格选择](https://github.com/m5agent/m5stack-esp-emulator/blob/a37342f61c05964c060719a6e35c2d568c828e84/docs/evidence/2026-10-26-unit-atom-controls-r1-a8fe/selection.json) |
| `UNIT-01` 控制类显示修正三主机 | AtomS3R/StickS3/StopWatch × Joystick/Encoder/8Encoder/CardKB/RFID2 三个独立gen9批次、十五个可见session功能15/15 PASS，无重试；三批421-entry源图及原文件SHA相同，字体实际高10/15/30与布局标记逐例核对。原CONTROL、真实产品输入、直接PID/a8fe、ZIP/帧和实际stopped/Flash false历史绑定；60张运行PNG解码、15张实际最终原生帧与before-evidence卡片图逐张复审，原生可读性只覆盖这些最终帧。严格控制类证据契约12项在实际加入15条host_validation后通过；完整平台544项与runtime/peripheral/profile/snapshot四项检查通过。旧双观察者和旧Atom r1可读性PARTIAL记录不改，QEMU未变，本批未重复67项共享矩阵。1692项公共清单重算、75PNG/15ZIP150成员受控格式核验及私有完整pipeline/故障留存复审通过；工具不授任意恶意输入安全结论，外部work-log仍NOT ARCHIVED | [三批范围与来源](https://github.com/m5agent/m5stack-esp-emulator/blob/a37342f61c05964c060719a6e35c2d568c828e84/docs/evidence/2026-10-26-unit-control-display-gen9-a8fe/README.md)、[清单](https://github.com/m5agent/m5stack-esp-emulator/blob/a37342f61c05964c060719a6e35c2d568c828e84/docs/evidence/2026-10-26-unit-control-display-gen9-a8fe/SHA256SUMS)、[精确主机元数据](../platform/units/runtime-profiles.json) |
| Core2 LVGL double-buffer flush wait and SPI transaction-done diagnostic | BIN-bound analysis of `UIFlow_Core2 v1.15.4` identified `0x40100010` as LVGL `lv_refr_vdb_flush`. At the WDT-off late state, `A2` is `lv_disp_buf_t` with both buffers valid and `flushing=1`; `A10` is the display driver with `wait_cb=0`, `flush_cb=0x40174758`. A 50-second PC trace observed `flush_cb` once at `44.198632 s`, but the completion callback `0x40174884` and `lv_disp_flush_ready` did not run; the frame stayed the same 302-byte black PNG. `0042` now models `SPI_SLAVE.TRANS_DONE/TRANS_INTEN` and drives the SPI IRQ as their logical AND, while adding bounded object-word dumps. The IRQ trace reached `trans_done=1/trans_inten=1/level=1`, but the completion callback remained unobserved in the 50-second WDT-off window. A 60-second normal-WDT run still grouped under `BOOTLOADER_TG0_STAGE1_RESET_WITH_TG1_LIVE`: stage-0 timeout `5.914197 s`, stage-1 timeout `15.915653 s`, first reset `15.915713 s`, TG1 `7,248` feeds with zero timeout, 302-byte black frame. This converts the former unknown object into a precise LVGL/SPI completion-chain blocker, but does not close `RUNTIME-03`. Only virtual-device and static BIN-bound evidence; matching ELF/MAP and physical hardware remain `NOT RUN` | [`LVGL/SPI wait evidence`](../tests/firmware/core2_handoff_trace/evidence-2026-10-26-core2-lvgl-spi-wait.json)、[`0042 patch`](../patches/qemu-m5stack-peripherals/0042-esp32-spi-trans-done-irq-diagnostic.patch)、[`PC trace runner`](../tests/firmware/core2_handoff_trace/run_pc_trace.py)、[`pause runner`](../tests/firmware/core2_handoff_trace/run_pause_sweep.py)、[`WDT liveness runner`](../tests/firmware/core2_handoff_trace/run_wdt_liveness.py)、[`contract`](../platform/tests/test_core2_wdt_off_late_state.py)、[`runtime gap`](runtime-model-gap-register.md) |
| WebBurner 导入选择与 ZIP 路径策略 | 新审计确认导入器会在以下场景静默接受歧义或平台相关输入：同包多份 WebBurner manifest、多个 `sdkconfig`/`sdkconfig.defaults`/eFuse/flasher 候选、多 build 未绑定目标 SoC、ZIP casefold/NFC 冲突或 symlink、布尔 offset 被当作整数。现在 ZIP path 先做 NFC/POSIX 归一，并拒绝绝对路径、反斜杠、控制字符、空/`.`/`..` 段、Windows 保留名/非便携名称、文件或目录 casefold 冲突、父子路径冲突和 symlink；WebBurner manifest、flasher、eFuse、ELF/MAP/SBOM 同角色资源必须唯一；实际 `sdkconfig` 明确优先于唯一的 `sdkconfig.defaults`；multi-build 包必须指定目标设备并唯一匹配一个 SoC build。验证：`test_firmware_manifest.py` `36/36`，新 static evidence `16/16` checks，manifest-policy 在最新工具哈希下 `14/14`，Secure Boot v2 重绑 `26/26`；平台 `543/543`，coverage/catalog/profile/snapshot、compileall 和 diff check PASS。该结果是导入/静态选择策略，不证明任何镜像可烧录、可启动或可运行，也不证明真机 | [`WebBurner import evidence`](../tests/firmware/evidence-2026-10-26-webburner-import-policy.json)、[`runner`](../tests/firmware/webburner_import_policy/run_test.py)、[`contract`](../platform/tests/test_webburner_import_policy_evidence.py)、[`manifest tests`](../platform/tests/test_firmware_manifest.py)、[`manifest-policy rebind`](../tests/firmware/evidence-2026-10-26-manifest-policy-fail-closed.json)、[`Secure Boot rebind`](../tests/firmware/evidence-2026-10-26-secure-boot-image-manifest-policy-v2.json)、[`FirmwareManifest`](firmware-manifest.md) |
| FirmwareManifest capability-policy and security-evidence consistency | 新审计确认三类手写/篡改 manifest 绕过：删除根 `capabilities` 后旧结构校验无错误且兼容性为 `PASS`；保留 signed image blocks 但把 `secure_boot_image.status` 改为 `not-found` 后旧 preflight 为 `PASS`；把 `efuse_summary.secure_boot/flash_encryption` 改成任意启用字符串后 schema/结构校验和 preflight 均放行。现在 root `capabilities` 及 `required`/`optional` 数组为必填，每数组最多 64 项、每项 1–64 字符；`validate_capabilities()` 独立检查缺失/畸形声明。Secure Boot image status 与 signed blocks/trust-root evidence 必须一致，eFuse summary 使用严格枚举，key digest mismatch 和 image secure-version below eFuse 直接拒绝。验证：`test_firmware_manifest.py` `32/32`、新 `manifest_policy/run_test.py` 全部 checks PASS、平台全套 `537/537`，schema JSON、runtime coverage、peripheral catalog、QEMU profiles、project snapshot、compileall 和 diff check PASS。该结果是 static manifest policy，不证明包内 eFuse 来源、live eFuse、bootloader trust-chain/anti-rollback 执行、Flash Encryption runtime、生产 key 或真机 | [`manifest policy evidence`](../tests/firmware/evidence-2026-10-26-manifest-policy-fail-closed.json)、[`runner`](../tests/firmware/manifest_policy/run_test.py)、[`contract`](../platform/tests/test_manifest_policy_evidence.py)、[`FirmwareManifest tests`](../platform/tests/test_firmware_manifest.py)、[`schema`](../platform/tools/firmware_manifest.schema.json)、[`FirmwareManifest`](firmware-manifest.md) |
| HTTP Host / exact DNS hardening and Core2 tool-hash rebind | HTTP Host authority 现在只接受单一 Host header、可选数字端口和 origin-form target，拒绝 userinfo、逗号/多重冒号、非法或越界端口、重复 Host 和 absolute-form。Controlled DNS 的 exact A/AAAA 与 CNAME terminal 都必须落在 allowed endpoint 内，IPv4-mapped IPv6 record fail closed；strict Host normalization 与 policy parser 同步收紧。Linux arm64 Docker namespace 中同一 StickS3 guest 完成 controlled DNS allow/NXDOMAIN、TLS 200/403、DHCP、pcap、namespace cleanup 和 QEMU reap，并生成 `evidence-2026-10-26-host-authority-exact-dns-namespace-pass.json`。代码变化更新 `device_service.py` 和 `network_policy.py` tool hash 后，用同一 `c3eaa35b…` firmware/`5bec056b…` ELF 独立重跑两批零错峰 `8×120s`；两批均 `8/8 PASS`，合计 `16/16`，每 lease 完成 frame/31 节点 QOM、WiFi DHCP/HTTP、公网 DNS/HTTP、NUS GATT、pcap、11–12 次 1 MiB PSRAM 全缓冲读回、bounded TCG、evidence 和 cleanup，HLI errors/reset/panic/dropped 为 0。A/B evidence SHA-256 分别为 `a4da8bc0…` 与 `6442574c…`。该结果只关闭当前虚拟网络边界和 tool-hash 容量门禁，不证明物理跨主机、任意 NAT、外部 side effect、物理 PSRAM/cache、bit-exact controller/RF 或真机 | [`Host/DNS namespace pass`](../tests/network/tls_allowlist/evidence-2026-10-26-host-authority-exact-dns-namespace-pass.json)、[`sandbox tests`](../platform/tests/test_network_sandbox.py)、[`policy tests`](../platform/tests/test_network_policy.py)、[`Core2 A`](../tests/uiflow2/core2_native_hci/evidence-2026-10-26-core2-concurrent-8x120-network-hardening-pass-a.json)、[`Core2 B`](../tests/uiflow2/core2_native_hci/evidence-2026-10-26-core2-concurrent-8x120-network-hardening-pass-b.json)、[`Core2 contract`](../platform/tests/test_docs_core2_runtime_contract.py) |
| Project code/document organization and metadata drift gate | 将当前入口收敛为“五分钟阅读顺序”，明确当前事实、待办、生成快照、契约和专题/历史证据的分层；工程交接与当前状态新增网络、Core2、FirmwareManifest 三组 P0 的已完成/缺口对照，Backlog 单列已完成里程碑并声明局部完成不扩大结论。机器可读源同步到当前证据：Core2 验证日期更新到 `2026-10-26`，AtomS3R/CoreS3/StickS3 吸收后续 WPA2-PSK 正误密码路径，生成设备目录和项目快照已重建。代码侧在 `qemu_profiles.py --check` 增加 catalog/profile 生成日期及验证日期/状态一致性门禁，并新增反例：手工制造 `generated_at` 和 Core2 日期漂移时，检查必须返回 structured errors。验证：平台 `531/531`、QEMU profile `20/20`、runtime coverage、peripheral catalog、QEMU profiles、project snapshot、`compileall` 和 `git diff --check` PASS；Ruff `E9/F` 因当前 Python 环境未安装 `ruff` 为 `NOT RUN`。本次不重跑固件或 QEMU lease，不改变 Core2、网络、固件安全或其他 runtime 结论，也不构成 hardware validation | [`docs index`](README.md)、[`engineering handoff`](engineering-handoff.md)、[`current status`](project-status.md)、[`backlog`](project-backlog.md)、[`QEMU matrix`](qemu-device-adaptation-matrix.md)、[`profile drift check`](../platform/tools/qemu_profiles.py)、[`negative test`](../platform/tests/test_qemu_profiles.py)、[`generated snapshot`](project-snapshot.md) |
| Firmware security evidence understatement fail-closed | Device Service 现在从 aggregate、sdkconfig、Secure Boot v2 image status 和包内 eFuse summary 四层联合判断。手写 manifest 把 `security.secure_boot` / `security.flash_encryption` 改成 `unknown`，但 config 声称 v2/enabled、签名镜像存在、签名证据 invalid 或 eFuse summary 声称 enabled 时，均返回结构化错误，不创建 firmware/session。结构校验要求三个核心 security 字段存在且为合法枚举，schema 增加显式 `disabled` config 值。静态 fixture `11/11` checks PASS；当前 `firmware_manifest.py` 哈希下 Secure Boot v2 原 fixture 也重跑 `26/26` PASS，signature authenticity/trust root/anti-rollback 仍固定 `not-verified`。验证：平台 `530/530`、定向 security/docs/service `28/28`、Node SHA/upload `2/2`、两类 evidence 均可重复生成且 byte-identical，coverage/catalog/profile/snapshot、compileall、Ruff `E9/F` 和 `git diff --check` PASS。该结果防止 manifest 聚合字段 understatement 绕过 preflight，不证明包内 eFuse 来源、live eFuse、ROM/bootloader 执行、Flash Encryption runtime、生产 key 或真机 | [`security preflight evidence`](../tests/firmware/evidence-2026-10-26-firmware-security-preflight-fail-closed.json)、[`runner`](../tests/firmware/security_preflight/run_test.py)、[`contract`](../platform/tests/test_security_preflight_evidence.py)、[`Secure Boot rerun`](../tests/firmware/evidence-2026-10-26-secure-boot-image-security-preflight.json)、[`FirmwareManifest`](firmware-manifest.md) |
| Core2 eight-instance evidence rebind | manifest identity 与 unknown-required capability 语义更新使 `device_service.py` tool hash 变化；按证据规则用当前代码重建同 SHA `c3eaa35b…` Core2 unified 固件，并重跑两批独立零错峰 `8×120s`。两批均 `8/8 PASS`，合计 `16/16`，`maximum_concurrent_sessions=8`；每 lease 完成 frame/31 节点 QOM、WiFi DHCP/HTTP、公网 DNS/HTTP、外部 NUS GATT、pcap、11–12 次 1 MiB PSRAM 全缓冲读回、`tcg,thread=single,tb-size=128`、`shift=5`、evidence 和 cleanup，HLI `45/45`、36 events/9 ACLs，errors/reset/panic/dropped 为 0。首次服务未设置 `M5_CORE2_RADIO_QEMU` 的 503 被视为 infrastructure control，未计入有效批次。该结果重绑当前服务容量门禁，不证明大于八实例、持续吞吐、物理 PSRAM/cache、bit-exact controller/RF 或真机 | [`rebind A`](../tests/uiflow2/core2_native_hci/evidence-2026-10-26-core2-concurrent-8x120-fixed-icount-pass-a.json)、[`rebind B`](../tests/uiflow2/core2_native_hci/evidence-2026-10-26-core2-concurrent-8x120-fixed-icount-pass-b.json)、[`runner`](../tests/uiflow2/core2_native_hci/run_service_5x.py)、[`Core2 contract`](../platform/tests/test_docs_core2_runtime_contract.py) |
| Secure Boot v2 evidence rebind after manifest identity change | `firmware_manifest.py` 的 manifest identity/capability 语义更新后，用当前工具哈希重跑 Secure Boot v2 静态 fixture。RSA-PSS、ECDSA P-192/P-256/P-384、签名数学、image digest、包内 eFuse public-key digest match/mismatch/unavailable 及 secure-version below/satisfied/unavailable 共 `26/26` checks PASS；`input_assets_unchanged=true`，authenticity/trust-root/anti-rollback 仍固定 `not-verified`。该结果只重绑静态镜像分析，不证明 boot ROM、live eFuse、生产 key、Flash Encryption 或真机执行 | [`secure-boot-image-2026-10-26.json`](../tests/firmware/evidence-2026-10-26-secure-boot-image.json)、[`runner`](../tests/firmware/secure_boot_image/run_test.py)、[`security contract`](../platform/tests/test_docs_firmware_security_contract.py) |
| Unknown required capability fail-closed / manifest identity stability | 同一 public StickS3 Weather SHA `8b7b47c8…` 分别作为 merged image 和 WebBurner 三段包导入，并绑定相同规范化 Flash SHA `d291e77f…`、8 MiB 大小和 `esp32s3`。known `wifi` required baseline 为 `PASS`；unknown `vendor-private-sensor` required 在 merged/WebBurner 两条路径均返回 `REJECTED`、CLI exit `1` 和唯一 error `unknown_required_capability`；同值作为 optional 时保持 `PASS` 并产生 `unknown_optional_capability` warning。两个内容相同但目录名不同的 WebBurner 包还验证 `manifest_id` 稳定：输出 artifact 文件名不同，但 content SHA 和 `manifest_id` 一致。Device Service manifest contract 同样拒绝对应未知 required 能力，不创建 firmware/session。验证：平台 `525/525`、定向 capability/docs/security/service `21/21`、Node SHA/upload `2/2`、两次 capability evidence 与两次 Secure Boot evidence 均 byte-identical，coverage/catalog/profile/snapshot、compileall、Ruff `E9/F` 和 `git diff --check` PASS。该结果只证明静态 capability 兼容性和 manifest identity，不证明任何 known capability 的 runtime 调用、boot、网络、安全启动或真机外设 | [`fail-closed evidence`](../tests/firmware/evidence-2026-10-26-unknown-required-capability-fail-closed.json)、[`runner`](../tests/firmware/unknown_required_capability/run_test.py)、[`contract`](../platform/tests/test_unknown_required_capability_evidence.py)、[`FirmwareManifest`](firmware-manifest.md) |
| Code/document consolidation after Core2 WDT-off late state | 将 `0041` 与 WDT-off 45/120 秒结论统一到 README、当前状态、Backlog、运行时缺口、工程交接、工作流、QEMU/固件矩阵、代码地图、平台/测试说明和历史调查。Backlog 重新收敛为“一句已满足基线 + 当前阻断 + 五步下一门禁”，不再复制 `0035-0040` 的诊断流水；工程交接删除重复的逐次时间线。新增 stale-claim 门禁，禁止“应用初始化未在 TG0 deadline 完成”“Flash 累计吞吐是当前瓶颈”等旧结论回流，并把固件测试说明、Core2 探针说明、QEMU profile 和 peripheral patch 专题纳入扫描。验证：平台 `522/522`、文档/Core2 定向 `36/36`、Node UI smoke `1/1`、Node SHA/upload `2/2`、runtime coverage/peripheral catalog/QEMU profile/project snapshot、`compileall`、Ruff `E9/F`、`git diff --check` 与 `0041` retained-tree reverse apply check PASS。该整理不重跑固件，不改变 legacy 失败状态；`RUNTIME-03` 仍 `OPEN`，仍无 normal-WDT 非空应用帧或 hardware validation | [`project-status.md`](project-status.md)、[`project-backlog.md`](project-backlog.md)、[`runtime-model-gap-register.md`](runtime-model-gap-register.md)、[`engineering-handoff.md`](engineering-handoff.md)、[`project-snapshot.md`](project-snapshot.md)、[`stale claims`](../platform/tests/fixtures/stale_doc_claims.json)、[`Core2 contract`](../platform/tests/test_docs_core2_runtime_contract.py)、[`late-state evidence`](../tests/firmware/core2_handoff_trace/evidence-2026-10-26-core2-wdt-off-late-state.json) |
| Core2 WDT-off late-boot state | `0041-esp32-handoff-register-stack-dump.patch` 给 exact-time dump 增加 A0-A15、PS、对象前向指针和最多 64-word stack window；WDT-off 只作为诊断 control。两个独立 lease 在 `45.0000355 s` 和 `120.00037 s` 均停在 CPU0 `0x4026306e` halted `waiti`、CPU1 `0x40100049` running spin。Flash handoff 均为 `49,848` cache-sync / `45,847` changed pages / `49,265` state updates，SSI 均为 `22,554` transactions / `671,936` RX bytes，最后活动约 `43.91-44.00 s`；cross-core writes 从 `123,476` 增至 `139,094`。CPU1 `A2+24=1`、`*(A3)=A10`、`A10+28=0`，Serial 均为 507-byte banner-only SHA。结论从“Flash 扫描可能无限慢”修正为“Flash phase 有终点，随后稳定 late-boot wait”；late object 无 matching ELF symbol，`RUNTIME-03` 仍 `OPEN`。该控制不是产品修复，仍需 normal-WDT 非空应用帧 | [`late-state evidence`](../tests/firmware/core2_handoff_trace/evidence-2026-10-26-core2-wdt-off-late-state.json)、[`0041 patch`](../patches/qemu-m5stack-peripherals/0041-esp32-handoff-register-stack-dump.patch)、[`pause runner`](../tests/firmware/core2_handoff_trace/run_pause_sweep.py)、[`contract`](../platform/tests/test_core2_wdt_off_late_state.py)、[`runtime gap`](runtime-model-gap-register.md) |
| Core2 WDT stage and feed-liveness reconciliation | 新增 `run_wdt_liveness.py`，在三个独立 Device Service lease 中关闭 PC trace、启用 TIMG verbose trace。三次都观察到 TG0 stage-0 在 `5.910698-5.922631 s` timeout 且中断被 mask，随后 TG0 stage-1 在 `15.911945-15.926599 s` 触发首次 system reset。TG1 分别完成 `6,807 / 6,618 / 6,681` 次 feed，最大相邻间隔 `8.478 / 10.410 / 8.505 ms`，最后 feed 距 reset `1.779 / 4.271 / 1.797 ms`，三次均 `0` TG1 timeout；stage-0 后也没有 TG0 feed/reconfigure/protect 写入。当前首 reset 分类为 `BOOTLOADER_TG0_STAGE1_RESET_WITH_TG1_LIVE`，早期 `800 ms` TG1 gap 在当前配置下为 `NOT_REPRODUCED`。Serial 均只有 MicroPython banner、无 REPL，frame 均为 302-byte black PNG。该检查点当时排除了当前配置下的 TG1 feed 停止，但仍未解释 reset 前的启动进度；只完成 virtual-device validation，不关闭 `RUNTIME-03`。验证：平台 `520/520`、Core2/文档/profile 定向 `59/59`、Node SHA/upload `2/2`、coverage/catalog/profile/snapshot、compileall、Ruff `E9/F` 和 `git diff --check` PASS | [`WDT liveness evidence`](../tests/firmware/core2_handoff_trace/evidence-2026-10-26-core2-wdt-liveness-3x.json)、[`runner`](../tests/firmware/core2_handoff_trace/run_wdt_liveness.py)、[`contract`](../platform/tests/test_core2_wdt_liveness.py)、[`runtime gap`](runtime-model-gap-register.md) |
| Code/document consolidation after completed handoff trace | 将 `0039/0040` 的结论同步到当前状态、Backlog、运行时缺口、工程交接、工作流、QEMU 矩阵、代码地图、README、平台/测试说明和历史调查；统一口径为“CPU1 持续执行、首次 reset 前约 4,376 次 handoff 已完整往返、永久 deadlock/UART 解释撤回”，并把下一门禁收敛到首个 stage-0 timeout 后的 WDT feed/service liveness 与启动 workload 累计 virtual time。文档新鲜度与自动快照重新生成；新增 state sweep/PC trace patch、runner、evidence 和契约测试。验证：平台 `515/515`、Core2 定向 `35/35`、Node SHA/upload `2/2`、runtime coverage/peripheral catalog/QEMU profile/project snapshot、`compileall`、Ruff `E9/F`、`git diff --check` 及 `0039/0040` retained-tree reverse apply check 全部 PASS。该整理不改变 legacy firmware 结果，`RUNTIME-03` 仍为 `OPEN`，仍无同 SHA 非空应用帧或 hardware validation | [`project-status.md`](project-status.md)、[`project-backlog.md`](project-backlog.md)、[`runtime-model-gap-register.md`](runtime-model-gap-register.md)、[`engineering-handoff.md`](engineering-handoff.md)、[`workstreams.md`](workstreams.md)、[`project-snapshot.md`](project-snapshot.md)、[`state sweep evidence`](../tests/firmware/core2_handoff_trace/evidence-2026-10-26-core2-handoff-state-sweep.json)、[`setter trace evidence`](../tests/firmware/core2_handoff_trace/evidence-2026-10-26-core2-handoff-pc-trace.json) |
| Core2 exact-time state sweep | `0039-esp32-handoff-state-dump.patch` 在 pause 前输出两核 PC/IRQ 状态、handoff flags、DPORT cache state、cache-sync/SSI/cross-core counters；`run_pause_sweep.py` 通过独立 Device Service leases 在 14.8、15.3、15.9 s 各采一点。CPU0 在前两点均为 `0x40087980`，CPU1 在 15.9 s 已进入不同路径；cache-sync calls `16144→16180→17444`，changed-page 累计停在 `6679`，SSI transactions `6984→6998→7506`、cross-core writes `40274→40566→43584` 继续增长。证明两核整体未永久停止，但未解释启动 liveness 或应用 PASS | [`state sweep evidence`](../tests/firmware/core2_handoff_trace/evidence-2026-10-26-core2-handoff-state-sweep.json)、[`0039 patch`](../patches/qemu-m5stack-peripherals/0039-esp32-handoff-state-dump.patch)、[`runner`](../tests/firmware/core2_handoff_trace/run_pause_sweep.py)、[`contract`](../platform/tests/test_core2_handoff_state_sweep.py)、[`runtime gap`](runtime-model-gap-register.md) |
| Core2 completed handoff setter trace | `0040-xtensa-handoff-pc-trace.patch` 新增默认关闭的 `M5SW_XTENSA_PC_TRACE` BIN-bound PC 列表。首轮 18 秒 normal-WDT run 在 `5.913935 s` 出现 stage-0 timeout，`15.914787 s` 首次 reset；reset 前 complete/can-start set/clear 四个 setter 各命中约 `4,377` 次。Serial 仍只到 MicroPython banner，无 REPL，frame SHA 仍为 `57580743…` 302-byte black frame。该结果否定了“单次 handoff 永久不返回”，但确认启动 workload/liveness 仍失败；零 changed-page flush 跳过 control 也仍进入同一 reset 和黑帧，因此被拒绝且未保留 | [`setter trace evidence`](../tests/firmware/core2_handoff_trace/evidence-2026-10-26-core2-handoff-pc-trace.json)、[`0040 patch`](../patches/qemu-m5stack-peripherals/0040-xtensa-handoff-pc-trace.patch)、[`runner`](../tests/firmware/core2_handoff_trace/run_pc_trace.py)、[`contract`](../platform/tests/test_core2_handoff_pc_trace.py)、[`runtime gap`](runtime-model-gap-register.md) |
| Core2 exact-time handoff freeze | `0038-esp32-handoff-pause.patch` 新增默认关闭的 `M5SW_ESP32_HANDOFF_PAUSE_NS`；在指定 QEMU virtual time 输出 pause marker 后向自身发送 `SIGSTOP`，不启用高频 PC sampling。两次 independent freeze：`14.800033 s` 早窗口没有固定 PC；`15.301447 s` 晚窗口 CPU0 `0x40087980`、CPU1 `0x40084484`。晚窗口 CPU1 `INTSET=0x40`、`interrupt_request=CPU_INTERRUPT_HARD`；两轮 serial 均保持同一 507-byte banner-only SHA。public BIN 自身在 CPU0 地址附近清零 `0x3ffc7ec8`、置位 `0x3ffc7ec9` 后等待，源码形态匹配旧 IDF `spi_flash_op_block_func` complete/can-start 握手；CPU1 旁路清零 `0x3ffc7750/54`，但 exact function 仍未 symbol-bound。默认 trace-off 下 Core2 UIFlow2 定向回归为 `6/6 cases`、`24/24 checks`、零 retry；平台 `508/508`。该结果证明 UART 高频 PC 簇是 sampling-dependent，并把调查收敛到 Flash/cache handoff；仍不证明具体未返回操作或应用 PASS | [`pause evidence`](../tests/firmware/core2_handoff_trace/evidence-2026-10-26-core2-handoff-pause.json)、[`0038 patch`](../patches/qemu-m5stack-peripherals/0038-esp32-handoff-pause.patch)、[`contract test`](../platform/tests/test_core2_handoff_pause.py)、[`runtime gap`](runtime-model-gap-register.md)、[`historical investigation`](core2-cache-panic-investigation.md) |
| Core2 public BIN / local ELF address audit | 新增 `audit_elf_bin_mapping.py`，从 normalized 16 MiB flash 的 app image 按 segment/VMA 提取字节，并与 local ELF 的同地址 section 字节比较。public `UIFlow_Core2 v1.15.4` BIN `152127c8…` 与 local `UIFlow2 v2.5.3` Core2 ELF `5bec056b…` 在 CPU0 样本地址 `0x400843ac/af/b1` 三处均 mismatch；因此此前 `uart_rx_intr_handler_default`、`mp_execute_bytecode` 符号映射被拒绝，UART storm 解释撤回。BIN 自身在这三个地址所在控制流中读取 CPU ID、`0x3ffc7750/48/60/58` 状态并访问 DPORT `0x3ff000e8/e4`，与 cross-core Flash/cache-disable handoff 路径一致，但因没有 matching ELF/MAP，精确函数名和等待对象仍未绑定。新增 extractor 单测与 audit evidence；只完成 static artifact mapping，不改变 legacy reset/black-frame 状态 | [`pc mapping audit`](../tests/firmware/core2_handoff_trace/evidence-2026-10-26-core2-pc-mapping-audit.json)、[`audit tool`](../tests/firmware/core2_handoff_trace/audit_elf_bin_mapping.py)、[`contract test`](../platform/tests/test_core2_pc_mapping_audit.py)、[`runtime gap`](runtime-model-gap-register.md) |
| Core2 unified flash/cache handoff timeline | `0037` 增加默认关闭的 `M5SW_ESP32_HANDOFF_TRACE`，统一记录 virtual time、CPU、guest PC，以及 cross-core、DPORT cache、SSI transaction、UART IRQ 和 TIMG WDT 事件。两次 normal-WDT 运行均在最后 TG1 feed 后恰好 `800,000,000 ns` 进入 stage-0 timeout，约 `1.6 s` 后 reset；timeout PC 在两次运行中不同。WDT-disabled `sample=1024` 与 trace-off 均为 507-byte banner-only Serial，SHA 相同，说明该采样级别没有改变序列输出。可选 1 ms PC 采样对照仍保持 800 ms gap，但 reset 提前；最终窗口 800 个样本只出现 CPU0 `uart_rx_intr_handler_default` 与 CPU1 `mp_execute_bytecode`，同一窗口没有 UART register event，因此 UART storm 只是候选而非根因。默认 trace-off 回归为 Core2 设备组 `6/6`、`24/24` checks 和完整 UIFlow2 矩阵 `67/67`、`274/274` checks，零 retry。trace 的 267/287 条采样事件覆盖到约 `14.19 s` 虚拟时间；该结果把“缺少统一时间轴”转为“CPU0 最后 800 ms 中断/服务饥饿待定位”，不关闭 `RUNTIME-03`。`0037` 以 `0036` 后的 retained target tree 为前序状态完成 forward/reverse check，不是裸上游单补丁；仅 virtual-device validation | [`handoff timeline evidence`](../tests/firmware/core2_handoff_trace/evidence-2026-10-26-core2-handoff-timeline.json)、[`summarizer`](../tests/firmware/core2_handoff_trace/summarize.py)、[`0037 patch`](../patches/qemu-m5stack-peripherals/0037-esp32-handoff-trace.patch)、[`runtime gap`](runtime-model-gap-register.md)、[`historical investigation`](core2-cache-panic-investigation.md) |
| Core2 stateful SSI batch and throughput correction | `0036` adds an optional byte-buffer SSI transfer callback with the original per-byte fallback, an m25p80 `STATE_READ` fast path, and ESP32 SPI receive-only batching. The first 512 sampled 64-byte batches matched the original per-byte implementation. After rebuilding `qemu-system-xtensa` from the exact patch set, the Core2 device group passed `6/6` cases and `24/24` checks, and the shared-controller regression passed the full `67/67` cases and `274/274` checks with no retries. The same legacy firmware still reset under the normal watchdog; with watchdog reset disabled, 180 seconds were insufficient to reach setup text or REPL. The earlier direct-read REPL observation did not reproduce in the current rebuild. A direct memory-state trace observed flash-operation can-start/complete and cross-core reason flags repeatedly transitioning, so the permanent cross-core deadlock hypothesis is retired and the next boundary is aggregate synchronous Flash/cache-handoff throughput. Patch clean-base forward/reverse check, platform `501/501`, docs `41/41`, QEMU profiles `19/19`, Node SHA/upload, worker credential migration, compileall, scoped Ruff `E9/F`, runtime coverage, peripheral catalog, project snapshot and `git diff --check` all PASS. Only virtual-device validation | [`stateful SSI evidence`](../tests/firmware/evidence-2026-10-26-core2-ssi-transfer-buf.json)、[`0036 patch`](../patches/qemu-m5stack-peripherals/0036-ssi-transfer-buf.patch)、[`QIO/cross-core diagnostic`](../tests/firmware/evidence-2026-10-26-core2-qio-crosscore-diagnostic.json)、[`Core2 group summary`](../tests/uiflow2/run_peripheral_matrix.py)、[`runtime gap`](runtime-model-gap-register.md) |
| Core2 QIO/TIMG/cross-core diagnostic reconciliation | TIMG trace proved that the old model raised the WDT level IRQ while `INT_ENA=0x00000000`, `INT_RAW=0x00000004` and masked status were `0`; `0035` now gates the level on `INT_RAW & INT_ENA` while preserving raw status and stage-timer behavior. Two Device Service controls still reached `TG0WDT_SYS_RESET`/reset PC `0` after the mask fix, so `RUNTIME-03` remains open. Legacy QIO scanning showed per-byte SSI forwarding as a major host cost. A temporary direct `blk_pread` diagnostic matched the subsequent SSI byte stream on sampled cache lines and one run reported the MicroPython banner and `>>>`; that progress did not reproduce in later rebuilds, and the path bypasses the SSI/m25p80 command/dummy/data machine. The later stateful-SSI row supersedes the REPL and permanent-deadlock interpretations. The QEMU dirty worktree and ad hoc logs are retained locally, but this evidence remains diagnostic and not artifact-bound to a product runtime. Only virtual-device validation | [`QIO/cross-core evidence`](../tests/firmware/evidence-2026-10-26-core2-qio-crosscore-diagnostic.json)、[`0035 WDT mask patch`](../patches/qemu-m5stack-peripherals/0035-esp32-timg-wdt-int-ena.patch)、[`runtime gap`](runtime-model-gap-register.md)、[`historical investigation`](core2-cache-panic-investigation.md)、[`Core2 docs contract`](../platform/tests/test_docs_core2_runtime_contract.py) |
| Code/document authority sync after equal-deadline timer work | 将 latest Core2 事实同步到顶层 README、项目状态、Backlog、工程交接、工作流、QEMU 矩阵、代码地图、公开固件矩阵、测试 README、历史调查、验证台账和运行时缺口登记；文档口径统一为“shared I2C 与 minimal-probe timer `FIXED`，legacy `TG0/TG1WDT_SYS_RESET`/reset PC `0`/black frame `OPEN`”。同时把 flash-IPC runner 的默认观察窗口修正为 `15 s`，将已进入 `READ_START` 但未完成的运行标为 `INCOMPLETE`，并把已知 image/ELF SHA 设为默认 fail-closed 门禁，阻止旧 `.work/core2-flash-ipc-16m.bin` 被上传。验证：平台 `500/500`、runtime coverage、peripheral catalog、QEMU profiles、project snapshot、compileall、Ruff `E9/F`、`git diff --check` 和 patch clean-base forward/reverse check PASS；真实 Device Service 新版 runner `3/3 PASS`，错误镜像在 SHA 门禁处 exit `2` 且未上传。仅 virtual-device validation | [`project-status.md`](project-status.md)、[`project-backlog.md`](project-backlog.md)、[`engineering-handoff.md`](engineering-handoff.md)、[`runtime-model-gap-register.md`](runtime-model-gap-register.md)、[`probe README`](../tests/firmware/core2_flash_ipc/README.md)、[`probe runner`](../tests/firmware/core2_flash_ipc/run_test.py)、[`equal-deadline evidence`](../tests/firmware/core2_flash_ipc/evidence-2026-10-26-core2-ccompare-equal-deadline.json)、[`0034 patch`](../patches/qemu-m5stack-peripherals/0034-xtensa-ccompare-equal-deadline.patch) |
| Core2 Xtensa equal-deadline timer root cause and fix | IRQ ring 在最小 `core2_flash_ipc` probe 中捕获到 timer ISR 写入 `CCOMPARE == CCOUNT` 后，旧 QEMU 算出 `dcc=0x100000000`；Core2 下一次 timer 中断因此被推迟约 `26.8 s`，随后 interrupt-WDT。业务补丁 `0034` 只把相等期限安排到下一 cycle，其他 delta 仍保留原 32 位回绕语义；补丁从 clean base forward/reverse apply check 均为 PASS，且不包含 ring/trace。冻结 image `c2762e5f…`、ELF `7636c3e5…` 后，修复版四批合计 `40/40` 首启动完成全部 1000 次 CPU1 `esp_partition_read()`，`0` interrupt-WDT、`0` spinlock assertion、`0` reboot；其中三批固定 `icount shift=5`，一批 `shift=auto`，并包含 trace-disabled control。更新 runner 后再次经真实 Device Service 运行 `3/3 PASS`，旧错误镜像在 SHA 门禁处退出且未上传。相同 public `UIFlow_Core2 v1.15.4` SHA `18d77e28…` 仍在修复版上出现 `TG1WDT_SYS_RESET`/`TG0WDT_SYS_RESET`、reset CPU PC `0` 和同一 black-frame SHA，因此只关闭 minimal-probe timer 子问题，`RUNTIME-03` 保持 OPEN；仅 virtual-device validation | [`equal-deadline evidence`](../tests/firmware/core2_flash_ipc/evidence-2026-10-26-core2-ccompare-equal-deadline.json)、[`pre-fix evidence`](../tests/firmware/core2_flash_ipc/evidence-2026-10-26-core2-flash-ipc-wdt.json)、[`probe README`](../tests/firmware/core2_flash_ipc/README.md)、[`probe runner`](../tests/firmware/core2_flash_ipc/run_test.py)、[`0034 patch`](../patches/qemu-m5stack-peripherals/0034-xtensa-ccompare-equal-deadline.patch)、[`runtime gap`](runtime-model-gap-register.md)、[`historical investigation`](core2-cache-panic-investigation.md) |
| Current work/docs consolidation after Core2 probe correction | 将最新工作回写到当前状态、Backlog、交接、工作流、QEMU 矩阵和代码地图，并把易漂移的单次运行数字从上层入口移回本台账与 evidence：`RUNTIME-03` 上层只描述“partition read 可执行，但 flash 活动后仍可复现 interrupt-WDT”，不再复制探针通过率；`CORE2-02` 的 `profiles.json` blocker 改成长稳/容量边界，不再嵌入整串并发批次。压缩 `platform/README` 的 Core2 历史流水，明确 `code-map` 验证表是指向 evidence 的入口索引而不是当前快照，并要求 PASS 比例、轮次、资源值、哈希和逐项检查数只在日期化证据维护。扩展文档契约，禁止探针比例回流到 README、状态、Backlog、交接、工作流、QEMU 矩阵和代码地图，同时验证 Core2 profile blocker 不再携带并发数。验证：平台 `500/500`、文档契约 `40/40`、QEMU profile contract `19/19`、compileall、Ruff `E9/F`、runtime coverage、peripheral catalog、QEMU profiles、project snapshot 和 `git diff --check` PASS。该结果只整理代码入口与文档口径，不改变 QEMU/固件行为，也不新增 legacy UIFlow、buffer controller、物理 PSRAM/cache、RF 或 hardware validation 结论 | [`project-status.md`](project-status.md)、[`project-backlog.md`](project-backlog.md)、[`engineering-handoff.md`](engineering-handoff.md)、[`workstreams.md`](workstreams.md)、[`code-map.md`](code-map.md)、[`platform README`](../platform/README.md)、[`QEMU profiles`](../platform/qemu/profiles.json)、[`Core2 docs contract`](../platform/tests/test_docs_core2_runtime_contract.py)、[`QEMU profile test`](../platform/tests/test_qemu_profiles.py) |
| Code/document work-state consolidation | 将总览、状态、Backlog、工作流和 QEMU 适配矩阵收敛为“当前能力 / 调查假设 / 待办依赖 / 日期化证据”四层；README、handoff、QEMU/network 专题不再复制易漂移的 PASS 比例、轮次和资源数字，具体结果统一留在本台账与 evidence。Backlog 新增立即可做、多机环境、真机/授权、后端阻塞四类依赖；`RUNTIME-03` 明确当前仅验证 flash-cache disable、跨核 IPC 与 DPORT high-interrupt 交接假设，S32C1I 锁空闲只否定首要锁泄漏假设，不写成根因。Core2 GDB/VHCI lane 统一标为 historical/diagnostic，避免 `current 1/2` 等旧措辞回流。`SVC-03` 记录“先锁 API/evidence 契约、一次只移一个边界、代码变动必须配套重跑 tool-hash-bound evidence”的拆分门禁。验证：平台 `499/499`、文档契约 `39/39`、Node SHA256/upload/UI smoke、runtime coverage、peripheral catalog、QEMU profiles、project snapshot、compileall、selected Ruff `E9/F` 和 `git diff --check` PASS；未改 `device_service.py` 或 QEMU/固件行为，未新增 hardware validation | [`project-status.md`](project-status.md)、[`project-backlog.md`](project-backlog.md)、[`workstreams.md`](workstreams.md)、[`engineering-handoff.md`](engineering-handoff.md)、[`code-map.md`](code-map.md)、[`runtime-model-gap-register.md`](runtime-model-gap-register.md)、[`project-snapshot.md`](project-snapshot.md)、[`current-state contract`](../platform/tests/test_docs_current_state_contract.py)、[`Core2 contract`](../platform/tests/test_docs_core2_runtime_contract.py) |
| Core2 flash/IPC and interrupt-WDT diagnostic | 先纠正探针自身错误：早期镜像把 4096-byte 局部 buffer 放在 4096-byte CPU1 task stack，栈溢出覆盖了同一区域的 FreeRTOS queue lock，因此旧的 `spinlock_release()` owner mismatch 被撤销。修正版改用静态 internal-RAM buffer、每 50 次读取让出 CPU；current QEMU `7226de8c…` 5 次首启动为 `1 PASS / 4 interrupt-WDT`，portable QEMU `4095fb11…` 15 次为 `13 PASS / 2 interrupt-WDT`。合并 `14 PASS / 6 WDT / 0 spinlock assert`，20/20 均出现 `READ_START`，PASS 轮完成 1000 次 4 KiB CPU1 partition read；WDT 轮已至少完成 250 次读取，CPU0/CPU1 backtrace 均为 `esp_cpu_wait_for_intr -> esp_vApplicationIdleHook -> prvIdleTask`。该结果把剩余最小复现收敛到 flash workload 开始后的虚拟 timer/interrupt 交付，不证明 legacy UIFlow 同因，也未覆盖物理时序。artifact：image `c2762e5f…`、ELF `7636c3e5…`，仅 virtual-device validation | [`probe README`](../tests/firmware/core2_flash_ipc/README.md)、[`probe runner`](../tests/firmware/core2_flash_ipc/run_test.py)、[`evidence`](../tests/firmware/core2_flash_ipc/evidence-2026-10-26-core2-flash-ipc-wdt.json)、[`runtime gap`](runtime-model-gap-register.md)、[`historical investigation`](core2-cache-panic-investigation.md) |

## 2026-10-25

| 工作流 | 结果 | 证据 |
| --- | --- | --- |
| Core2 legacy shared board I2C | 重新从公开 CDN 下载 `UIFlow_Core2 v1.15.4`，source SHA 仍为 `18d77e28…`。修复前 controller trace 的 123 个事务全部位于 `/machine/soc/i2c0`，`0x34` write/read ACK 正常，`0x51` 在 `i2c0/i2c` 上 `start_rc=1`，随后串口返回 `OSError: I2C bus error (19)`；板模型当时把 RTC 只挂在 controller 1。`0031` 将两个 controller register block 路由到唯一物理 GPIO21/22 board bus并仅挂一份器件，修复后 trace 的 480 个事务仍位于 controller 0，`0x34` write/read、`0x51` write/read 和 INA3221 `0x40` 均 ACK，原 I2C error 消失；AXP192 变体同样越过该错误。现有 UIFlow2 Core2 外设组 `6/6`、`24/24` checks PASS，无 retry。下一阻断变成独立 interrupt-WDT reset/panic，frame 仍为 black，因此不关闭 `RUNTIME-03` 或 legacy firmware PASS | [`shared-board evidence`](../tests/firmware/evidence-2026-10-25-core2-shared-board-i2c.json)、[`0031 patch`](../patches/qemu-m5stack-peripherals/0031-core2-shared-board-i2c.patch)、[`before trace`](../tests/firmware/evidence-2026-10-24-core2-axp-i2c-trace.json)、[`Core2 device group`](../tests/uiflow2/run_peripheral_matrix.py) |
| Core2 legacy WDT timing diagnosis | 同一 `UIFlow_Core2 v1.15.4` BIN/ELF-less image 在默认单会话运行 `285` 秒，TG0/TG1 持续 config/feed/arm，无 interrupt-WDT 或 TG reset。两批独立四实例默认运行各观察 `84` 秒，interrupt-WDT 分别为 `3/4` 和 `2/4`，合计 `5/8` 失败、`3/8` 未出现 WDT；失败 CPU/PC 不固定。显式 `tcg,thread=single,tb-size=128`、`tcg,thread=multi,tb-size=128`、`icount shift=5` 和 `icount shift=0` 均未修复；thread/single 与两种 icount 对照为 `4/4` TG hardware reset，multi 为 `2/4` interrupt-WDT。`icount shift=0` 单会话 trace 显示 TG1 最后一次 feed 在虚时 `13.782s`，`0.8s` 后进入 interrupt stage，再 `1.6s` 后 reset。该结果把问题从固定 I2C/PMIC 外设或单一 firmware PC 收敛为启动期长同步路径与虚拟时间/宿主调度的交互；仍未定位具体 guest 代码点，frame 仍为 black，physical hardware `NOT RUN` | [`WDT timing evidence`](../tests/firmware/evidence-2026-10-25-core2-wdt-timing.json)、[`0032 TIMG trace`](../patches/qemu-m5stack-peripherals/0032-esp32-timg-wdt-trace.patch)、[`shared-bus evidence`](../tests/firmware/evidence-2026-10-25-core2-shared-board-i2c.json)、[`QEMU TIMG model`](../patches/qemu-m5stack-peripherals/README.md) |
| Code/document current-state reconciliation | 将 shared-bus 修复回写到状态、Backlog、工作流、交接、代码地图、QEMU 矩阵、公开固件矩阵和测试 README；旧 2026-10-24 无 ACK/board-routing 结果保留为历史，当前口径统一为 I2C ACK 已修复、后续 interrupt WDT/black frame 仍开放，`Core2FactoryTest` 修复后重跑明确为 `NOT RUN`。新增 3 条退役说法，fixture 总计 `144` 条。验证：文档契约 `38/38`、平台 `498/498`、Node UI smoke、runtime coverage、peripheral catalog、QEMU profiles、project snapshot、compileall、selected Ruff `E9/F`、patch reverse-check 和 `git diff --check` PASS；当前 QEMU binary SHA-256 为 `a8070d23…`。该结果只整理代码/文档事实，不改变 WDT、黑帧、物理硬件或其他固件 SHA 的验证边界 | [`project-status.md`](project-status.md)、[`project-backlog.md`](project-backlog.md)、[`workstreams.md`](workstreams.md)、[`engineering-handoff.md`](engineering-handoff.md)、[`code-map.md`](code-map.md)、[`user-firmware-simulation-matrix.md`](user-firmware-simulation-matrix.md)、[`stale_doc_claims.json`](../platform/tests/fixtures/stale_doc_claims.json)、[`core2 contract`](../platform/tests/test_docs_core2_runtime_contract.py)、[`Node UI test`](../platform/tests/test_ui.mjs) |
| Code/document authority consolidation | 将原 6436 行 `test_docs_consistency.py` 拆为导航、当前状态、Core2、固件安全、网络/worker 五个领域契约，旧路径保留 6 行兼容入口；把 141 条退役说法迁入结构化 claim/authority JSON。`project-status.md` 从 803 行收敛到 131 行，只保留当前能力、边界和下一门禁；`project-backlog.md` 从 412 行收敛到 301 行，任务板不再复制 PASS 轮次；`workstreams.md` 从 164 行收敛到 85 行，只做工作流路由。同步修正跨容器 worker README 的过期“下一项”状态，并让 Node sessions 页测试等待 `API online` 而不是提前读取 Loading 文案。验证：平台 `497/497`、文档契约 `37/37`、Node 页面 smoke PASS；runtime coverage、peripheral catalog、QEMU profiles、project snapshot、compileall、selected Ruff `E9/F` 和 `git diff --check` 均 PASS。该结果只覆盖代码/文档组织，不重新定义固件功能；真实矩阵、Core2 legacy I2C、跨主机 worker 与 hardware validation 边界保持不变 | [`project-status.md`](project-status.md)、[`project-backlog.md`](project-backlog.md)、[`stale_doc_claims.json`](../platform/tests/fixtures/stale_doc_claims.json)、[`docs contract support`](../platform/tests/_docs_contract_support.py)、[`index contract`](../platform/tests/test_docs_index_contract.py)、[`current-state contract`](../platform/tests/test_docs_current_state_contract.py)、[`core2 contract`](../platform/tests/test_docs_core2_runtime_contract.py)、[`firmware contract`](../platform/tests/test_docs_firmware_security_contract.py)、[`network-worker contract`](../platform/tests/test_docs_network_worker_contract.py)、[`Node UI test`](../platform/tests/test_ui.mjs) |
| Core2 fixed-icount five-instance concurrency | 默认 `icount shift=5,align=off,sleep=off` 下，两批独立零错峰 `qemu-unified/profile=core2-native-hci` `5×120s` 均为 `5/5 PASS`，合计 `10/10`，最大并发 5。每个 lease 均绑定同一 firmware/ELF/QEMU/tool hashes，完成 WiFi DHCP/HTTP、公网 DNS/HTTP、外部 NUS GATT、PNG frame、31 节点 QOM、pcap、evidence 和 14–15 次 1 MiB PSRAM 全缓冲读回；HLI `45/45`、36 events/9 ACLs，errors/reset/panic/dropped/queue depth 为 0。证据原始 SHA-256 分别为 `87dd7166…` 与 `8f9a913a…`。该结果关闭五实例 120 秒 simultaneous cold-start 门禁，不证明大于五实例、持续吞吐、物理 PSRAM/cache、bit-exact controller/RF 或真机 | [`fixed icount pass A`](../tests/uiflow2/core2_native_hci/evidence-2026-10-25-core2-concurrent-5x120-fixed-icount-blefirst-pass-a.json)、[`fixed icount pass B`](../tests/uiflow2/core2_native_hci/evidence-2026-10-25-core2-concurrent-5x120-fixed-icount-blefirst-pass-b.json)、[`qemu_accel.py`](../platform/tools/qemu_accel.py)、[`run_service_5x.py`](../tests/uiflow2/core2_native_hci/run_service_5x.py) |
| Core2 fixed-icount six-instance concurrency | 同一默认 `icount shift=5,align=off,sleep=off` 与冻结输入下，两批独立零错峰 `qemu-unified/profile=core2-native-hci` `6×120s` 均为 `6/6 PASS`，合计 `12/12`，最大真实并发 6。每个 lease 完成 WiFi DHCP/HTTP、公网 DNS/HTTP、外部 NUS GATT、PNG frame、31 节点 QOM、pcap、evidence 和 12–13 次 1 MiB PSRAM 全缓冲读回；HLI `45/45`、36 events/9 ACLs，reset/panic/dropped/queue depth 为 0。batch B 的一个 lease 记录一次可恢复 `hli-prealloc-failures=1`，最终仍全部走 36/9 fast path 并完成 45/45 HLI 投递，该瞬态保留为诊断。证据原始 SHA-256 为 `ae49660b…` 与 `6131b3c6…`。该结果关闭六实例 120 秒 simultaneous cold-start 门禁，不证明大于六实例、持续吞吐、物理 PSRAM/cache、bit-exact controller/RF 或真机 | [`six-instance pass A`](../tests/uiflow2/core2_native_hci/evidence-2026-10-25-core2-concurrent-6x120-fixed-icount-pass-a.json)、[`six-instance pass B`](../tests/uiflow2/core2_native_hci/evidence-2026-10-25-core2-concurrent-6x120-fixed-icount-pass-b.json)、[`focused test`](../platform/tests/test_core2_six_instance_concurrency.py) |
| Core2 fixed-icount eight-instance concurrency | 最高服务并发 8 的首个 `8×120s` control 在旧 `hold/10` floor 下为 `4/8`，但所有 8 个 guest 的 WiFi/公网、NUS GATT、frame、31 节点 QOM、pcap/evidence、HLI health 均通过，零 reset/panic/dropped；4 个失败 lease 均完成 11 次连续 sweep，仅低于旧 12 次下限。失败 evidence 保留。将固定时钟 highest-concurrency floor 校准为 `hold/12` 后，两批独立零错峰 `8×120s` 均 `8/8 PASS`，合计 `16/16`；每 lease 完成 11–12 次 1 MiB PSRAM 全缓冲读回，两批各保留一次可恢复 prealloc transient。原始 SHA-256 为 fail `a1241057…`、pass `36d52c32…`/`96d12ff4…`。达到当前服务单设备容量上限，不证明大于八实例、持续吞吐、物理 PSRAM/cache、bit-exact controller/RF 或真机 | [`threshold fail`](../tests/uiflow2/core2_native_hci/evidence-2026-10-25-core2-concurrent-8x120-threshold-fail.json)、[`eight pass A`](../tests/uiflow2/core2_native_hci/evidence-2026-10-25-core2-concurrent-8x120-fixed-icount-pass-a.json)、[`eight pass B`](../tests/uiflow2/core2_native_hci/evidence-2026-10-25-core2-concurrent-8x120-fixed-icount-pass-b.json)、[`focused test`](../platform/tests/test_core2_eight_instance_calibration.py) |
| Core2 five-instance concurrency | 两批独立的 `qemu-unified/profile=core2-native-hci` `5×120s` 使用 30 秒错峰，均 `5/5 PASS`，合计 `10/10`，最大并发 session 数为 5。每个 lease 完成 WiFi/公网、NUS GATT、持续 PSRAM stress、frame/31-node QOM、pcap、evidence 和 cleanup；HLI `45/45`、36 events/9 ACLs、errors/reset/panic 为 0，bounded TCG 与输入哈希绑定成立。另保留相同实现的零错峰对照：一批 `5/5 PASS`，独立确认批 `3/5 FAIL`；失败包含 HLI queue 残留、`ble_hs_hci_process_ack` `LoadProhibited @ 0x402630cc` 和 external GATT exchange failure，因此五实例错峰稳态 PASS 不外推到同时冷启动，更多实例仍 `NOT RUN` | [`stagger pass A`](../tests/uiflow2/core2_native_hci/evidence-2026-10-25-core2-concurrent-5x120-stagger30-pass-a.json)、[`stagger confirm B`](../tests/uiflow2/core2_native_hci/evidence-2026-10-25-core2-concurrent-5x120-stagger30-confirm-pass-b.json)、[`no-stagger pass`](../tests/uiflow2/core2_native_hci/evidence-2026-10-25-core2-concurrent-5x120-no-stagger-pass-1.json)、[`no-stagger fail`](../tests/uiflow2/core2_native_hci/evidence-2026-10-25-core2-concurrent-5x120-no-stagger-fail-1.json)、[`runner`](../tests/uiflow2/core2_native_hci/run_service_5x.py) |
| Core2 zero-stagger ACK observability | `0010` opt-in trace 在旧 `shift=auto` 五实例零错峰 `5×20s` 诊断批中保留 `3 PASS / 2 FAIL`。失败 attempt 的首条 Reset Complete 已由 Bumble 返回，但 response→HLI 时间戳差为 `4.506306s`（host trace time，不是 guest 虚拟时钟）；期间 guest 连续发出三次 Reset，恢复后旧 Reset Complete 与新 `0x1001` response 交错，`ble_hs_hci_process_ack` 以 error `12` 调度 reset，后续 `0x402630cc` `LoadProhibited` 属于次生故障。首条 event 进入 semaphore check 时 `ack=null`、count `0`，排除初始 stale ACK pointer/semaphore state。后续 trace 将该窗口归因到 PSRAM 初始化关中断与 host-contention-scaled `shift=auto`；固定 `shift=5`/BLE-first 的替换门禁已 `10/10 PASS`，本行仅保留历史失败与 `0010` 默认关闭观测 | [`aggregate`](../tests/uiflow2/core2_native_hci/evidence-2026-10-25-core2-concurrent-5x20-ack-observability.json)、[`default PASS`](../tests/uiflow2/core2_native_hci/evidence-2026-10-25-core2-ack-observability-default-1x.json)、[`summary`](../tests/uiflow2/core2_native_hci/evidence-2026-10-25-core2-ack-observability-summary.json)、[`qemu trace summary`](../tests/uiflow2/core2_native_hci/evidence-2026-10-25-core2-ack-observability-trace-summary.log)、[`serial summary`](../tests/uiflow2/core2_native_hci/evidence-2026-10-25-core2-ack-observability-serial-summary.log)、[`0010 patch`](../patches/qemu-core2-native-hci/0010-esp32-native-hci-ack-observability.patch) |
| Core2 `0008` full peripheral matrix | `0008` guest HLI event/ACL 预分配版本在 `f2bc2b4d…` QEMU 上重跑完整 UIFlow2 外设矩阵：`67/67` case、`274/274` check PASS，全部 `attempts=1`、`retry_used=false`。Core2 六个 case 共 `24/24` check PASS，覆盖显示/触摸、RTC、电源键、NS4168/I2S DMA、SPM1423/I2S RX、INA3221、MPU6886 和 AXP192；runner 固定为 `770db317…`，原始 summary SHA-256 为 `f5029d96…`。该结果是 regression virtual-device validation，不新增物理 controller、PSRAM/cache、RF 或真机结论 | [`core2-hli-preallocation-full-matrix.json`](../tests/uiflow2/evidence-2026-10-25-core2-hli-preallocation-full-matrix.json)、[`run_peripheral_matrix.py`](../tests/uiflow2/run_peripheral_matrix.py)、[`0008 patch`](../patches/qemu-core2-native-hci/0008-esp32-native-hci-preallocate-hli-objects.patch) |
| Core2 current-binary QOM boot timing | 重建 QEMU `b5b2d878…` 后首次 Core2 六例设备组为 `5 PASS / 1 FAIL`：`core2-power-monitor` 进程正常退出但未出现 INA3221 成功 marker，画面仍显示 `bus=625 shunt=12`。同一参数无重试复跑仍 FAIL；将固定通道值从默认 post-boot `qom-set` 改为 `qom-set-boot` 后 PASS，原 post-boot 方式延长到 20 秒的对照也 PASS，因此归类为 `runtime_fixture_timing`，不是 firmware、INA3221 模型或电气结论。修正后 Core2 六例定向门禁 `6/6`、`24/24` checks，全部单次不重试；失败、扩展等待对照和通过轨迹均保留 | [`postboot-injection-fail.json`](../tests/uiflow2/evidence-2026-10-25-core2-power-monitor-postboot-injection-fail.json)、[`qom-boot-device-group.json`](../tests/uiflow2/evidence-2026-10-25-core2-qom-boot-device-group.json)、[`run_peripheral_matrix.py`](../tests/uiflow2/run_peripheral_matrix.py) |
| Secure Boot v2 image signature-sector evidence | 静态 fixture 在 bootloader 和 app partition 的 4 KiB 对齐位置构造 RSA-PSS、ECDSA P-192/P-256/SHA-256 与 ECDSA P-384/SHA-384 signature sector，验证 magic/version、block CRC32、SHA-256/SHA-384 image digest、embedded public-key digest 和最多三个 block 的解析；RSA-PSS 使用 block 内 modulus/exponent 完成 PSS/MGF1/salt 数学验签，ECDSA P-192/P-256/P-384 使用 block 内 public point/r/s 完成曲线与 recover-r 校验，坏 RSA/ECDSA 签名即使摘要和 CRC 正确也会返回 `invalid`；篡改镜像摘要或无 signature sector 分别得到 `invalid`/`not-found`。FirmwareManifest 把 signature block 的公钥 SHA-256 与包内 `espefuse` summary 的 `SECURE_BOOT_DIGEST` 做 match/mismatch/unavailable 对照并记录 `matching_pairs`；mismatch 另产生 `secure_boot_v2_image_public_key_digest_mismatch`。应用 `secure_version` 还会与 eFuse `SECURE_VERSION` 做 below/satisfied/unavailable 对照；低于最低版本产生 `secure_boot_image_secure_version_below_efuse`。`signature_authenticity`、顶层 `security.trust_root.status` 和 `security.anti_rollback.status` 都固定为 `not-verified`，因为包内 summary 是自报数据，不是 live eFuse read，bootloader 也未执行。当前 Secure Boot fixture `26/26` checks。该结果证明 RSA-PSS 与 ECDSA P-192/P-256/P-384 数学签名、镜像摘要、包内公钥摘要和 secure-version 对照自洽，但不证明 summary 来源、公钥/设备 trust root、ROM/bootloader 安全启动或 anti-rollback 执行、Flash Encryption、生产 key、真机或 RF | [`secure-boot-image.json`](../tests/firmware/evidence-2026-10-25-secure-boot-image.json)、[`run_test.py`](../tests/firmware/secure_boot_image/run_test.py)、[`firmware_analysis.py`](../platform/tools/firmware_analysis.py)、[`firmware_manifest.py`](../platform/tools/firmware_manifest.py) |
| Worker-local unified companion partition fence | 三个独立 privileged Linux Docker 运行均在 worker namespace 内启动 central Device Service、worker-local `qemu-unified` Device Service 和 8 MiB StickS3 unified firmware。partition 前要求同一 session 出现 HTTP fixture request、BLE `BLE_BUMBLE_PASS` 和非空 pcap；断网后 attempt 1 被 lease fence，QEMU PID/HTTP fixture/BLE peer 全部停用，BLE PID 消失，首轮 pcap summary `PASS`；attempt 2 启动新 unified session，再次完成 HTTP/BLE/pcap 与 terminal `PASS`。三轮均 `30/30` checks，source revision/worktree、runner/QEMU/firmware/tool hashes 一致，namespace/service/runtime cleanup 完成；平台测试 `447/447`、文档契约 `33/33`、Node `2/2`，CI `40163651476` 的 `platform-contracts` 与 `network-namespace-policy` 均 PASS。该证据关闭 worker-owned QEMU process 和 `qemu-unified` companions/pcap 的 partition fencing；QEMU 内 guest/controller 内部状态、worker 未拥有的外部 side effect、物理跨主机和真机仍 `NOT RUN` | [`partition-fencing-unified-3x.json`](../tests/network/worker_partition_fencing/evidence-2026-10-25-partition-fencing-unified-3x.json)、[`run_test.py`](../tests/network/worker_partition_fencing/run_test.py)、[`summarize_runs.py`](../tests/network/worker_partition_fencing/summarize_runs.py)、[`CI 40163651476`](https://github.com/m5agent/m5stack-esp-emulator/actions/runs/40163651476) |
| Code/document freshness reconciliation | 顶层 README 压缩为当前能力摘要；`project-status` 增加当前工作/下一门禁/不可继承边界；Backlog 删除已完成流水并保留开放项；网络与 worker 专题统一区分 worker-owned QEMU process、QEMU guest/controller、`qemu-unified` companion 和外部 side effect。自动快照新增文档职责分布及落后于事实日期的非历史页候选；文档契约新增索引重复链接、权威页重复长行和审计结构检查；清理 `qemu_profiles.py` 无占位符 f-string 与 `sd_image.py` 未使用变量。平台测试 `447/447`、文档契约 `33/33`、Node `2/2`，coverage/catalog/profile/snapshot、Ruff `E9/F`、compileall 和 `git diff --check` PASS；CI `40162500104` 的 `platform-contracts` 与 `network-namespace-policy` 均 PASS。该结果只校准代码入口、契约和文档事实，完整功能矩阵、QEMU guest 内部 side-effect fence、物理跨主机与真机仍 `NOT RUN` | [`project-status.md`](project-status.md)、[`project-backlog.md`](project-backlog.md)、[`project-snapshot.md`](project-snapshot.md)、[`test_docs_consistency.py`](../platform/tests/test_docs_consistency.py)、[`CI 40162500104`](https://github.com/m5agent/m5stack-esp-emulator/actions/runs/40162500104) |
| Worker lease ownership fencing | Queue 在 lease 过期、worker stale/stop 或 generation 变化后重新入队；下一次 claim 生成不同 `lease_id`。旧 lease 的 heartbeat/result 被 `409 job_lease_mismatch` 拒绝，不能覆盖新 claim。真实 `DeviceService` HTTP 契约验证旧 result `409`、新 result `completed`；`WorkerAgent` 单测在 job heartbeat 409 后打断 evidence wait、DELETE worker-local runtime session、写本地 `lease_fenced=true` FAIL，并完全不调用中央 result API。该证据关闭 queue result 与 worker 可达本地 runtime 的 fencing；断网远端进程、外部网络 side effect、物理跨主机和真机仍 `NOT RUN` | [`test_worker_queue.py`](../platform/tests/test_worker_queue.py)、[`test_worker_agent.py`](../platform/tests/test_worker_agent.py)、[`test_device_service.py`](../platform/tests/test_device_service.py)、[`worker_queue.py`](../platform/tools/worker_queue.py)、[`worker_agent.py`](../platform/tools/worker_agent.py) |
| Worker network-partition side-effect fencing | 两个独立 Linux namespace 运行真实 central Device Service、`WorkerAgent` 和 worker-local runtime。廉价 lane 先用 600 秒 child process；nftables 只 drop worker→control TCP，本地 runtime 仍可达。heartbeat socket timeout 现在受剩余 control recovery budget 限制；约 2 秒内 heartbeat 失败、`lease_fenced=true`、runtime DELETE、process reap、worker 不提交 stale result。中央 5 秒 lease 到期重排，网络恢复后第二个 worker 以 attempt 2 完成 PASS。真实 QEMU lane 在 worker namespace 运行 Device Service、上传完整 StickS3 image、启动真实 `qemu-system-xtensa`；同样断网后首轮 QEMU PID 被 reap，attempt 2 启动新 QEMU 并完成 PASS。两个 lane 各 `3/3 PASS`、`18/18` checks，QEMU/firmware/tool hashes 无漂移，namespace/process 清理。该证据关闭 worker-owned OS process 与 worker-local QEMU process side effect；QEMU 内 guest/device side effect、未被 worker 拥有的外部网络 side effect、物理跨主机和真机仍 `NOT RUN` | [`partition-fencing-3x.json`](../tests/network/worker_partition_fencing/evidence-2026-10-25-partition-fencing-3x.json)、[`partition-fencing-qemu-3x.json`](../tests/network/worker_partition_fencing/evidence-2026-10-25-partition-fencing-qemu-3x.json)、[`runtime_fixture.py`](../tests/network/worker_partition_fencing/runtime_fixture.py)、[`run_test.py`](../tests/network/worker_partition_fencing/run_test.py)、[`test_worker_agent.py`](../platform/tests/test_worker_agent.py) |
| Core2 8 MiB PSRAM and upper-bank MMU | `m5core2` machine 的 default/QOM 从 4 MiB 提升为 8 MiB，并模型化 PSRAM MMU 的 128 个 32 KiB DRAM1 页；普通 ESP32 heap 仍是 4 MiB 直接映射窗口。独立 ESP-IDF `esp_himem` probe 通过真实 `/api/v1` 运行 3 个 lease：每轮把两个不同 upper physical blocks 依次映射到同一个虚拟 32 KiB 窗口并反向读回，`physical_himem_bytes=4,456,448`、reserve `262,144 B`、QOM `8,388,608 B`，无 mismatch/failure marker。若 MMU 被忽略，后写块会覆盖前块并使反向校验失败。该结果是 virtual-device validation，不证明物理 PSRAM/cache timing 或真机 | [`core2-himem-bank-switch-3x.json`](../tests/firmware/core2_psram_himem/evidence-2026-10-25-core2-himem-bank-switch-3x.json)、[`app_main.c`](../tests/firmware/core2_psram_himem/main/app_main.c)、[`run_test.py`](../tests/firmware/core2_psram_himem/run_test.py)、[`0030 patch`](../patches/qemu-m5stack-peripherals/0030-core2-eight-mib-psram.patch) |
| Core2 8 MiB QOM unified sustained stress | 同一 `core2-native-hci` soak 镜像运行 3 个独立 artifact-bound lease，每轮 120 秒。QOM PSRAM device 为 `8,388,608 B`；普通 4 MiB DRAM1 heap 上分配 `1 MiB` bytearray，各完成 35/35/35 次全缓冲校验（累计 `105 MiB`）、30 次受控 HTTP、10 次公网 recheck。每轮 active BLE、HLI `45/45`、frame、QOM、pcap、evidence、bounded TCG 和 cleanup 全 PASS，firmware/ELF/QEMU/tool hashes 无漂移。物理 PSRAM/cache timing、RF 和真机仍 `NOT RUN` | [`core2-psram-sustained-8m-3x120.json`](../tests/uiflow2/core2_native_hci/evidence-2026-10-25-core2-psram-sustained-8m-3x120.json)、[`run_service_5x.py`](../tests/uiflow2/core2_native_hci/run_service_5x.py)、[`device_service.py`](../platform/tools/device_service.py) |
| Core2 2×120s staggered concurrent leases | 同一 `core2-native-hci` 固件/ELF/QEMU 同时运行两个 artifact-bound lease，启动错峰 `30s`，最大并发 session 数为 `2`。前两个对照先分别暴露共享宿主 HTTP 端口冲突和无错峰冷启动第二个 guest 在 `ble_hs_hci_process_ack` 的 LoadProhibited；随后 Device Service 为 Core2 native-HCI 使用 per-session QEMU `guestfwd` HTTP，runner 增加 `--concurrency/--stagger-seconds` 和真实 session-interval overlap 证据。最终 `2/2 PASS`：两轮均各自完成 WiFi、公网 DNS/HTTP、active BLE GATT、30+ 次 `1 MiB` PSRAM sweep、frame/QOM、pcap、bounded TCG、evidence 和 cleanup，HLI `45/45`，无 panic；frame/QOM 一致。该历史记录只覆盖 30 秒错峰后的稳态并发；同时冷启动的后续结论见同日 `guest-object preallocation` 行 | [`core2-concurrent-2x120-stagger30.json`](../tests/uiflow2/core2_native_hci/evidence-2026-10-25-core2-concurrent-2x120-stagger30.json)、[`shared-port failure`](../tests/uiflow2/core2_native_hci/evidence-2026-10-25-core2-concurrency-http-port-collision-fail.json)、[`simultaneous-start failure`](../tests/uiflow2/core2_native_hci/evidence-2026-10-25-core2-concurrency-simultaneous-start-fail.json)、[`unified_http_guestfwd.py`](../platform/tools/unified_http_guestfwd.py)、[`run_service_5x.py`](../tests/uiflow2/core2_native_hci/run_service_5x.py) |
| Core2 no-stagger extended GATT timeout | extended BLE exchange 把 Bumble GATT request 和 notification timeout 从 `10/15s` 提升到 `30s`；第一对同时冷启动 lease 达到 `2/2 PASS`，每轮仍有 WiFi、公网、NUS GATT、PSRAM、frame/QOM、pcap、bounded TCG 和 evidence。扩展为四个 lease 后结果为 `3 PASS / 1 FAIL`：失败轮仍完成 `45/45` HLI posts/consumed，WiFi/公网、PSRAM、frame/QOM、pcap 和 evidence 也通过，但 `hli-errors=3` 使 aggregate FAIL。该历史结果证明 timeout 只能改善等待预算；后续 `0007` 和 `0008` 分别处理 valid queue 与投递延迟 | [`core2-concurrent-2x120-simultaneous-timeout30-pass.json`](../tests/uiflow2/core2_native_hci/evidence-2026-10-25-core2-concurrent-2x120-simultaneous-timeout30-pass.json)、[`core2-concurrent-4x120-hli-errors-fail.json`](../tests/uiflow2/core2_native_hci/evidence-2026-10-25-core2-concurrent-4x120-hli-errors-fail.json)、[`ble_probe.py`](../platform/tools/ble_probe.py)、[`device_service.py`](../platform/tools/device_service.py) |
| Core2 no-stagger HLI valid-queue gate | `0007` 在 `esp32_native_hci_schedule_hli()` 中要求最近一次 `observe_hli()` 已观察到有效 guest scheduler/meta queue；未 ready 时保持 packet pending，而不是安排一次会递增 `hli-errors` 的投递。同一固件、ELF、QEMU 和工具哈希下，首批四个无错峰 lease 为 `4/4 PASS`，每次 `45/45` HLI、`hli-errors=0`、队列清空。独立四 lease 复核没有复现 HLI counter 错误，但首个并发批仍有一个 guest 在 `ble_hs_hci_process_ack` LoadProhibited；该历史失败随后由 `0008` object preallocation 修复 | [`core2-concurrent-4x120-simultaneous-pass.json`](../tests/uiflow2/core2_native_hci/evidence-2026-10-25-core2-concurrent-4x120-simultaneous-pass.json)、[`core2-concurrent-4x120-simultaneous-confirm-fail.json`](../tests/uiflow2/core2_native_hci/evidence-2026-10-25-core2-concurrent-4x120-simultaneous-confirm-fail.json)、[`0007 patch`](../patches/qemu-core2-native-hci/0007-esp32-native-hci-require-valid-guest-queue.patch)、[`run_service_5x.py`](../tests/uiflow2/core2_native_hci/run_service_5x.py) |
| Core2 no-stagger guest-object preallocation | Packet trace 证明旧路径中 Bumble 在约 `4.6ms` 内返回 Command Status，但 ACL FIFO head 阻塞 HLI 约 `3.660s`，超过 NimBLE `2s` command-ack budget。`0008` 在 CPU0 idle 时用真实 guest allocator 保留 2 个 event buffer 和 2 个 ACL mbuf；繁忙时直接填 `os_mbuf`/event 并投递真实 HLI callback，不使用 fake ACK。两批独立 `4×120s` 无错峰门禁各 `4/4 PASS`，合计 `8/8`；每 lease 36 events/9 ACLs 全部 fast path、2+2 spare objects、HLI `45/45`、errors/reset/panic 为 0。trace Command Status 接收→HLI 降至约 `0.328s`。只证明当前双实例虚拟 workload，不是物理 controller/RF | [`prealloc pass A`](../tests/uiflow2/core2_native_hci/evidence-2026-10-25-core2-concurrent-4x120-prealloc-pass-a.json)、[`prealloc confirm B`](../tests/uiflow2/core2_native_hci/evidence-2026-10-25-core2-concurrent-4x120-prealloc-confirm-pass-b.json)、[`latency comparison`](../tests/uiflow2/core2_native_hci/evidence-2026-10-25-core2-hli-preallocation-latency.json)、[`0008 patch`](../patches/qemu-core2-native-hci/0008-esp32-native-hci-preallocate-hli-objects.patch) |
| Core2 three-instance no-stagger concurrency | 三实例同时冷启动首先以 `0/3 FAIL` 暴露 Device Service 固定 `40s` BLE peer scan 窗口早于约 `55s` 的 guest BLE 初始化退出；peer 关闭 socket 后才出现 HCI reset/timeout，不是 guest panic。peer scan 现按 session readiness 计算 `min(120s, max(40s, ready_timeout-10s))`，与 `30s` GATT operation timeout 分离。下一轮 `1 PASS / 2 FAIL` 已完成全部 HCI/GATT/网络数据面，但两个 lease 只完成 29 次 sweep，旧 `hold/4=30` 阈值过紧；sweep 下限改为保守 `hold/5=24`，仍要求连续 sweep、heartbeat、HTTP 和公网 recheck。最终两批独立三实例 `3×120s` 各 `3/3 PASS`，合计 `6/6`；每个 PASS lease 完成 29–30 次 `1 MiB` PSRAM 全缓冲校验、HLI `45/45`、36 events/9 ACLs、WiFi/公网/GATT/frame/QOM/pcap/evidence，errors/reset/panic 为 0。pass A 的 attempt 1 记录一次启动期 prealloc allocation failure，但随后恢复 2/2 spare depth，36/9 packets 全 fast path 且 45/45 投递成功；该计数作为启动诊断保留，不代表最终对象缺失。该结果关闭当前三实例 virtual-device workload，不外推到更多实例、物理 controller/PSRAM/cache 或真机 | [`peer scan failure`](../tests/uiflow2/core2_native_hci/evidence-2026-10-25-core2-concurrent-3x120-peer-timeout-fail.json)、[`sweep calibration failure`](../tests/uiflow2/core2_native_hci/evidence-2026-10-25-core2-concurrent-3x120-scan120-threshold-fail.json)、[`pass A`](../tests/uiflow2/core2_native_hci/evidence-2026-10-25-core2-concurrent-3x120-pass-a.json)、[`confirm B`](../tests/uiflow2/core2_native_hci/evidence-2026-10-25-core2-concurrent-3x120-confirm-pass-b.json)、[`ble_runtime_limits.py`](../platform/tools/ble_runtime_limits.py) |
| Core2 four-instance no-stagger concurrency | 四个 `qemu-unified/core2-native-hci` lease 在零错峰下同时冷启动 120 秒，最大并发 session 数为 `4`，结果为 `1 PASS / 3 FAIL`。attempt 2 的 WiFi/公网/GATT/PSRAM/frame/QOM/pcap 均完成，但 QOM 记录 `hli-errors=1`、`hli-prealloc-failures=2`，因此 aggregate health 正确为 FAIL。attempt 3/4 在 `UNIFIED_CORE2_READY` 前先出现 NimBLE HCI ACK timeout/process error，反复 `LoadProhibited @ 0x402630cc`；地址符号化为 `ble_hs_hci_process_ack()` 的 `l_ble_hs_hci_ack->opcode` 读取（`ble_hs_hci.c:495`），reboot 后再出现 `PC=0` 是次生故障。四个 attempt 均保留完整 evidence ZIP/tool hashes；该结果把“大于三实例”从 `NOT RUN` 改为已执行开放项，不覆盖物理 controller/PSRAM/cache 或真机 | [`4-way failure`](../tests/uiflow2/core2_native_hci/evidence-2026-10-25-core2-concurrent-4x120-prealloc-4way-fail.json)、[`run_service_5x.py`](../tests/uiflow2/core2_native_hci/run_service_5x.py)、[`0008 patch`](../patches/qemu-core2-native-hci/0008-esp32-native-hci-preallocate-hli-objects.patch) |
| Core2 four-instance expanded HLI reserve | 四实例首批失败后，Bumble peer H4 日志证明 Reset/Read Local Version 等命令的 Command Complete 已正常从 controller 返回，差异发生在 QEMU HLI 注入侧。`0008` 的 2 event buffer 会被四条并发 guest 启动命令 burst 耗尽，而 CPU0 在等待 ACK 时没有新的 idle safe point；`0009` 将真实 guest preallocation reserve 扩为 8 event/4 ACL。两批独立四实例 `4×120s` 均 `4/4 PASS`，合计 `8/8`，firmware/ELF/QEMU/tool hashes 绑定，且 `input_assets_unchanged_during_run=true`。每 lease 完成 WiFi、公网、NUS GATT、32 次 `1 MiB` PSRAM 全缓冲校验、frame/31-node QOM/pcap/evidence，QOM 结束 depth `8/4`、HLI `45/45`、36 events/9 ACLs、errors/reset/panic 为 0。首批 attempt 2 保留 2 次 transient refill failure，最终补满且无 HCI error；确认批为 0。`0009` 源码构建的 QEMU `0e1165fb…` 同时通过 Core2 六例外设组 `6/6`、`24/24` checks，全部单次无 retry。该结果关闭当前 `4×120s` 四实例 virtual-device 边界，不覆盖五实例、bit-exact controller、物理 PSRAM/cache 或真机 | [`pass A`](../tests/uiflow2/core2_native_hci/evidence-2026-10-25-core2-concurrent-4x120-prealloc8x4-pass-a.json)、[`confirm B`](../tests/uiflow2/core2_native_hci/evidence-2026-10-25-core2-concurrent-4x120-prealloc8x4-confirm-pass-b.json)、[`0009 group`](../tests/uiflow2/evidence-2026-10-25-core2-0009-device-group.json)、[`0009 patch`](../patches/qemu-core2-native-hci/0009-esp32-native-hci-expand-hli-preallocation.patch) |
| Core2 8 MiB device-group compatibility | 同一 `m5core2` QEMU device group 在 CLI `-m 0` / QOM 8 MiB 配置下以无 retry 的 6 个 case、24 个检查全部 PASS：显示/触摸/RTC/电源键、NS4168/I2S DMA、SPM1423/I2S RX、INA3221、MPU6886 和 AXP192。该回归用于确认 memory/MMU 模型改动没有破坏既有板级路径；物理 PSRAM/cache timing 与真机仍 `NOT RUN` | [`core2-psram-device-group.json`](../tests/uiflow2/evidence-2026-10-25-core2-psram-device-group.json)、[`run_peripheral_matrix.py`](../tests/uiflow2/run_peripheral_matrix.py) |
| Worker QEMU across Docker containers | 三个独立运行均在 user-defined Docker bridge 上启动 central 与 worker 两个容器。central 容器保存 durable queue/directory；worker 容器启动独立 runtime Device Service 并创建真实 StickS3 QEMU session。每轮均完成注册、submit/claim、双 heartbeat、terminal `completed/PASS`、`execution_plane=worker-local`、source/normalized firmware/QEMU 三哈希、manifest/serial/QOM evidence、QEMU reap、token 不落日志以及 container/bridge cleanup。两次早期失败分别保留为容器网络未通与宿主绝对 QEMU 路径泄漏；修复后三个当前实现哈希一致的运行全部 PASS。该结果是两个独立容器共享 one Docker daemon 的 virtual-device validation，不是物理跨主机、进程迁移、NAT discovery 或 RF/真机 | [`cross-container-qemu-3x.json`](../tests/network/worker_cross_container/evidence-2026-10-25-cross-container-qemu-3x.json)、[`run_test.py`](../tests/network/worker_cross_container/run_test.py)、[`summarize_runs.py`](../tests/network/worker_cross_container/summarize_runs.py)、[`Dockerfile`](../tests/network/worker_cross_container/Dockerfile) |
| Firmware guest CNAME lifecycle | 三个独立 Device Service lease 均使用同一 stock StickS3 UIFlow2 probe、`qemu-wifi/uiflow2-sticks3-wifi`、Linux private namespace 和 controlled DNS。每轮 guest 查询 `alias.cname.test`，resolver 返回 CNAME→`origin.cname.test`→`10.0.2.2`；guest 完成 18080 HTTP/1.0 200，未允许名称得到 NXDOMAIN，未允许 18081 端口被阻止。resolver/HTTP fixture/pcap/isolation 文件位于同一 evidence ZIP，session stop 后 QEMU reap、DNS/HTTP close 和 namespace cleanup 全 PASS；三次 probe/QEMU/service/sandbox hash 一致。两次 pre-guest 启动失败分别定位为 DNS record 二次规范化与 QEMU ROM 目录缺失，均保留为服务启动诊断而非固件 FAIL。该结果是 virtual-device validation，不证明 public DNS/DNSSEC、RF 或真机 | [`cname-guest-lifecycle-3x.json`](../tests/network/cname_guest_lifecycle/evidence-2026-10-25-cname-guest-lifecycle-3x.json)、[`run_test.py`](../tests/network/cname_guest_lifecycle/run_test.py)、[`summarize_runs.py`](../tests/network/cname_guest_lifecycle/summarize_runs.py)、[`test_device_service.py`](../platform/tests/test_device_service.py) |
| Controlled DNS CNAME chain | 本地 controlled resolver 对两跳 exact-terminal alias 返回 A response `2 CNAME + 1 A`，对 CNAME query 返回两条 CNAME，并对 domain-suffix terminal 返回 `1 CNAME + 1 A`；未知名称保持 NXDOMAIN。结构化 log 记录 chain、terminal 和最终 exact/suffix rule；cycle、uncontrolled terminal、越权 alias、exact/domain owner 冲突均被拒绝。单元测试另锁定最多 8 跳包含边界与 9 跳拒绝。该结果是 resolver-data-plane validation；同 guest 固件跟随 CNAME 后完成 TCP/HTTP、namespace isolation、public DNS/DNSSEC、RF 和真机均未由本证据覆盖 | [`evidence-2026-10-25-controlled-cname-chain.json`](../tests/network/dns_cname_chain/evidence-2026-10-25-controlled-cname-chain.json)、[`run_test.py`](../tests/network/dns_cname_chain/run_test.py)、[`test_network_sandbox.py`](../platform/tests/test_network_sandbox.py)、[`test_device_service.py`](../platform/tests/test_device_service.py) |
| Public macOS runtime bundle | 复现 issue #1 的两个核心事实：`da100c90` 对公网 GitHub API 返回 422；公开 tag + zqqf16 v0.1.0 五补丁 + stopwatch patch 后，multiboard 与 peripherals 均因共享文件前像不同而失败。C6 `febae182...` 本身可公开访问，issue 中对此的笼统否定未复现。发布 `runtime-macos-arm64-2026.10.25`（71 MiB、SHA256 `735464…`）；在全新 public clone 中解压后，`sticks3` 与 `nesso-n1` 均 `backend_ready/creatable=true`，公开 StickS3 与 Nesso 固件分别取得 135×240 frame 并接受 key/touch。该 release 解决可执行运行时缺失，不是 clean-room 源码重建；一次 StickS3 QMP 启动超时保留为 residual service flake | [`evidence-2026-10-25-public-runtime-bundle.json`](../tests/firmware/evidence-2026-10-25-public-runtime-bundle.json)、[`runtime release`](https://github.com/m5agent/m5stack-esp-emulator/releases/tag/runtime-macos-arm64-2026.10.25)、[`issue #1`](https://github.com/m5agent/m5stack-esp-emulator/issues/1) |
| WebBurner part integrity | 合成的 3-segment WebBurner 包声明 size、SHA-256、SHA-1 和 MD5；importer 流式复算后 3/3 segment 记录 `status=verified`、算法集合 `[size,sha256,sha1,md5]` 与 `weak_digest=true`。负向用例覆盖 SHA-256 mismatch、size mismatch、非法 SHA-256、顶层/`integrity` 冲突声明和未知 integrity 字段，均在规范化前结构化拒绝。该结果是 static-manifest validation，不证明发布者签名、来源真实性、boot、网络、secure boot/Flash Encryption 或真机 | [`webburner-part-integrity.json`](../tests/firmware/evidence-2026-10-25-webburner-part-integrity.json)、[`run_test.py`](../tests/firmware/webburner_part_integrity/run_test.py)、[`test_firmware_manifest.py`](../platform/tests/test_firmware_manifest.py) |
| Core2 guest PSRAM sustained stress（历史基线） | `core2-native-hci` 通过真实 `/api/v1` 创建 3 个独立 artifact-bound lease，每个 120 秒。每轮 QOM 生效外部堆总量为 `4,194,304 B`，guest 分配 `1,048,576 B` bytearray，分别完成 35、35、36 次全缓冲校验，累计 `106 MiB`；每轮同时执行 10 次受控 HTTP、3–4 次公网 DNS/HTTP recheck，并保持 active BLE、34 节点 QOM、PNG frame、pcap、evidence 和 cleanup PASS。pcap 分别含 222、205、211 个包、53/46/48 flows 和 DHCP DORA；HLI `45/45`、errors/queue/panic 为 0。每轮 4 个资源采样的 RSS delta 为 `+656/+48/+112 KiB`；host-memory 结论只覆盖该 120 秒 workload。该历史基线后来由同日 8 MiB QOM/MMU 行取代；两者都不证明物理板载 PSRAM、cache timing、RF 或真机 | [`core2-psram-sustained-3x120.json`](../tests/uiflow2/core2_native_hci/evidence-2026-10-25-core2-psram-sustained-3x120.json)、[`pcap summary`](../tests/uiflow2/core2_native_hci/evidence-2026-10-25-core2-psram-sustained-3x120-pcap-summary.json)、[`main.py`](../tests/uiflow2/unified_core2/main.py) |
| Core2 guest PSRAM 600-second stress | 单 lease 600 秒完成 179 次 `1 MiB` 全缓冲校验（约 `179 MiB`）、51 次受控 HTTP 和 18 次公网 DNS/HTTP recheck。active BLE、HLI `45/45`、bounded TCG、34 节点 QOM、PNG frame、evidence 和 cleanup 全 PASS；pcap 为 `97,951 B`、912 packets、208 flows，含 DHCP DORA 与 `example.com` DNS。20 个 host RSS 采样 `327472→327824 KiB`（`+352 KiB`），phys footprint `246784→187392 KiB`；该 host-memory 结论只覆盖本 workload。仍是 `virtual-device validation`，不证明物理板载 `8 MiB`、cache/PSRAM 时序、RF 或真机 | [`core2-psram-sustained-1x600.json`](../tests/uiflow2/core2_native_hci/evidence-2026-10-25-core2-psram-sustained-1x600.json)、[`pcap summary`](../tests/uiflow2/core2_native_hci/evidence-2026-10-25-core2-psram-sustained-1x600-pcap-summary.json)、[`main.py`](../tests/uiflow2/unified_core2/main.py) |
| Core2 PSRAM threshold calibration failure | 首次 `3×120s` 运行中，第一个 lease 已 PASS 全部 guest 行为：35 次 PSRAM 全缓冲校验、10 次受控 HTTP、3 次公网 recheck、active BLE 和 bounded TCG 均正常，无 panic；但 runner 的 sweep 阈值乐观设为 `hold/3=40`，因此聚合结果 FAIL。该失败仅关闭测试阈值缺陷；阈值改为保守 `hold/4=30`，并增加 heartbeat 与最终计数器一致性检查后重跑 | [`core2-psram-sustained-threshold-fail-1x.json`](../tests/uiflow2/core2_native_hci/evidence-2026-10-25-core2-psram-sustained-threshold-fail-1x.json)、[`run_service_5x.py`](../tests/uiflow2/core2_native_hci/run_service_5x.py) |
| Core2 guest PSRAM initial path | 初始 `3×20s` 门禁每轮完成 6 次 `1 MiB` 校验（其中前 3 次用于初始 PASS），并保持 WiFi/公网/NUS GATT/frame/QOM/pcap/cleanup 同实例 PASS。该门禁证明 guest PSRAM 分配和读写路径；后续 `3×120s` sustained 证据取代其稳定性结论，原 evidence 保留为历史检查点 | [`core2-psram-guest-stress-3x.json`](../tests/uiflow2/core2_native_hci/evidence-2026-10-25-core2-psram-guest-stress-3x.json)、[`run_service_5x.py`](../tests/uiflow2/core2_native_hci/run_service_5x.py)、[`main.py`](../tests/uiflow2/unified_core2/main.py) |
| Bounded CIDR and controlled domain-set policy | Linux privileged Docker fixture 中，隔离 namespace 允许 `10.203.0.4/30` 内的 TCP 目标和精确 IPv6 目标，拒绝同一地址的未允许端口及 `/30` 外地址；IPv4/IPv6 均经 worker veth/NAT 重写，namespace 和 NAT table 清理完成，`22/22` checks PASS。单元契约另行验证 IPv4 `/16+`、IPv6 `/48+`、broad/special/mapped/SLiRP CIDR 拒绝、domain label boundary、exact/longest suffix 优先级，以及每个 domain answer 必须被 allowed endpoint 覆盖。该结果是 `linux-virtual-network-policy`，不是 guest 固件、任意公网域名解析、RF 或真机验证 | [`evidence-2026-10-25-cidr-dual-stack-docker-pass.json`](../tests/network/egress_allowlist/evidence-2026-10-25-cidr-dual-stack-docker-pass.json)、[`test_network_egress.py`](../platform/tests/test_network_egress.py)、[`test_network_policy.py`](../platform/tests/test_network_policy.py)、[`test_network_sandbox.py`](../platform/tests/test_network_sandbox.py) |
| Code/document reconciliation and CI | CIDR/domain policy 与代码地图、当前状态、Backlog 边界、OpenAPI `1.29.0`、网络方案和新鲜度断言对齐后，平台套件 `411/411 PASS`，文档契约 `22/22`，Node `2/2`，OpenAPI YAML、compileall、runtime coverage、peripheral catalog、QEMU profiles、project snapshot、selected Ruff 和 `git diff --check` 均通过。GitHub Actions run `40145733947` 在 `8c125fb` 上同时通过 `platform-contracts` 与本提交源码的 Linux `network-namespace-policy` job | [`project-status.md`](project-status.md)、[`code-map.md`](code-map.md)、[`validation-ledger.md`](validation-ledger.md)、[`CI 40145733947`](https://github.com/m5agent/m5stack-esp-emulator/actions/runs/40145733947) |
| Core2 active-stop/recovery | `run_service_teardown.py` 通过真实 `/api/v1` 连续创建 3 个 `core2-native-hci` session；每个 session 在 BLE peer 仍处于 120 秒 linger 窗口、HTTP companion 仍运行时 DELETE。停止耗时 `0.359/0.222/0.154s`，三次均为 `stopped`/无错误、HTTP/BLE companion `terminated`、BLE/QEMU PID 回收、worker active lease 为 0；随后新 session 继续通过 frame/QOM、WiFi DHCP/HTTP、公网 DNS/HTTP、外部 NUS GATT、pcap 与 evidence。firmware/ELF/QEMU/runner/service/accelerator/limits 哈希在首 lease 前冻结且运行期无漂移。GitHub Actions run `40146597625` 在 `3621301` 上通过两个 job。该结果关闭 active-stop cleanup，不覆盖长时吞吐、其他停止时序、bit-exact controller 或物理 cache/PSRAM | [`core2-active-stop-recovery-3x.json`](../tests/uiflow2/core2_native_hci/evidence-2026-10-25-core2-active-stop-recovery-3x.json)、[`run_service_teardown.py`](../tests/uiflow2/core2_native_hci/run_service_teardown.py)、[`CI 40146597625`](https://github.com/m5agent/m5stack-esp-emulator/actions/runs/40146597625) |
| Image capability observation and mismatch | 公开 StickS3 Weather 镜像没有 sdkconfig；规范化完整 Flash 的前 `8 MiB` 全部扫描，观察到 low-confidence `wifi` (`esp_wifi_init`) 和 `display` (`lcd_panel_`, `m5gfx`)。required wifi + optional display 为 PASS；required camera 在 StickS3 上仍返回结构化 `unsupported_capability`，artifact hash 与正常导入一致。observed entry 固定 `source=image-signature`/`confidence=low`；required 未观察、observed 未声明和 observed 设备不支持均为 review warning，不能降级或替代 required hard mismatch。GitHub Actions run `40147212974` 在 `9ad3771` 上通过两个 job。该结果是 static-manifest validation，不证明运行态调用、boot、网络、安全执行或真机 | [`image-capability-observation.json`](../tests/firmware/evidence-2026-10-25-image-capability-observation.json)、[`run_test.py`](../tests/firmware/image_capability_observation/run_test.py)、[`CI 40147212974`](https://github.com/m5agent/m5stack-esp-emulator/actions/runs/40147212974) |
| WebBurner capability review display | 真实 WebBurner 页面加载同一公开 StickS3 Weather Manifest；界面分别显示 `SDKConfig capabilities: none`、`Image observations: wifi (low: esp_wifi_init), display (low: lcd_panel_|m5gfx)`、`Image scan: SCANNED · 8.00 MiB / 8.00 MiB · complete`、`PASS` 和 5 条 `[warning:<code>]`。Node 契约验证纯渲染模块的 detected/observed/scan、issues 和 warning notice；未创建 Device Service session，未执行 QEMU/boot/网络，也不证明镜像运行时调用能力。GitHub Actions run `40147624694` 在 `e759777` 上通过两个 job | [`webburner-capability-display.json`](../tests/firmware/evidence-2026-10-25-webburner-capability-display.json)、[`webburner-capability-observation.jpg`](images/webburner-capability-observation.jpg)、[`firmware-report.js`](../platform/web/firmware-report.js)、[`CI 40147624694`](https://github.com/m5agent/m5stack-esp-emulator/actions/runs/40147624694) |
| Core2 bounded TCG memory and evidence binding | macOS `vmmap` 把旧两小时 soak 的 host RSS 增长归因到未限容 TCG translation buffer，而不是 guest PSRAM。全部 Core2 路径改用 `tcg,thread=single,tb-size=128`；同固件 120 秒 active-BLE WiFi/公网/GATT/frame/pcap/HLI 复测 PASS，RSS `323600→323584 KiB`、phys footprint `214016→196608 KiB`。runner 把 accelerator 的 `bounded_tcg_cache` 设为必需检查，并在首 lease 前绑定 firmware/ELF/QEMU 与 runner/service/accelerator/BLE-limit 工具哈希 | [`hci4-tb128-hold120-1x.json`](../tests/uiflow2/core2_native_hci/evidence-2026-10-24-hci4-tb128-hold120-1x.json)、[`qemu_accel.py`](../platform/tools/qemu_accel.py)、[`run_service_5x.py`](../tests/uiflow2/core2_native_hci/run_service_5x.py) |
| Core2 final bounded 7200-second hold | 1/1 artifact-bound lease PASS：launch firmware `4e1012…`、ELF、QEMU、runner、Device Service、accelerator 和 BLE limits 哈希无漂移；`bounded_tcg_cache`、frame/QOM `34`、WiFi/public DNS/HTTP、active NUS GATT、pcap `71967 B`、HLI `45/45`、active peer、evidence ZIP 和 cleanup 全部 PASS。240 个资源采样中 RSS `323536→252992 KiB`、phys footprint `250880→188416 KiB`；无 panic、dropped、queue、HLI error 或 peer close | [`hci4-active-ble-hold7200-tb128-artifact-bound-1x.json`](../tests/uiflow2/core2_native_hci/evidence-2026-10-25-hci4-active-ble-hold7200-tb128-artifact-bound-1x.json) |
| Core2 121-cycle readiness budget failure | 首次 `121` 轮运行完成 `29` 个 scan/connect/NUS GATT/disconnect cycle 并开始第 `30` 轮，应用 READY、WiFi、公网和 frame 均通过，guest 无 panic，peer 无 GATT timeout；固定的 `180s` readiness 预算仍终止了 session。runner 与 Device Service 现共享 workload-aware 预算 `min(7200, 60 + cycles × (6 + delay))s`，`121` 轮/`2s` 延迟为 `1028s`。该失败只关闭等待预算缺陷，不关闭 121 轮功能门禁 | [`hci4-reconnect121-readiness-timeout-1x.json`](../tests/uiflow2/core2_native_hci/evidence-2026-10-25-hci4-reconnect121-readiness-timeout-1x.json)、[`ble_runtime_limits.py`](../platform/tools/ble_runtime_limits.py)、[`test_ble_runtime_limits.py`](../platform/tests/test_ble_runtime_limits.py) |
| Core2 121-cycle accelerator sampling failure | 修复 readiness 后的 `121/121` 功能运行通过 WiFi/公网、NUS GATT、frame/QOM、pcap、evidence 和 HLI `3405/3405`，但 reconnect-only 路径没有进入 hold loop，QEMU accelerator 从未采样，形成 `bounded_tcg_cache` 假失败。runner 改为在 session 首次 running 时直接读取 live QEMU 命令；该失败仅关闭 harness 缺陷 | [`hci4-reconnect121-accelerator-sampling-fail-1x.json`](../tests/uiflow2/core2_native_hci/evidence-2026-10-25-hci4-reconnect121-accelerator-sampling-fail-1x.json)、[`run_service_5x.py`](../tests/uiflow2/core2_native_hci/run_service_5x.py) |
| Core2 single-lease 121-cycle reconnect | 第一份 `1/1` artifact-bound lease PASS：requested `180s`、effective `1028s`；`tcg,thread=single,tb-size=128`、WiFi DHCP/HTTP、公网 DNS/HTTP、外部 NUS GATT、3710-byte frame、34 节点 QOM、pcap、evidence 和 cleanup 全部 PASS。HLI `3405/3405`、events 2316、ACLs 1089；errors、HLI/meta/TX queue、dropped、last-error、peer-close 和 panic 均为 0。该单份证据由下一行的三 lease 聚合扩展，不单独代表复现门禁 | [`hci4-reconnect121-1x.json`](../tests/uiflow2/core2_native_hci/evidence-2026-10-25-hci4-reconnect121-1x.json) |
| Core2 three-lease 121-cycle reconnect | 三个独立 artifact-bound lease 均完成 `121/121`；firmware、ELF、QEMU 和 runner/service/accelerator/BLE-limit 工具哈希跨运行一致，drift 为空。每 lease frame/QOM、WiFi/公网、NUS GATT、pcap、evidence、cleanup、bounded TCG 与 HLI health 全 PASS；HLI `3405/3405`、events 2316、ACLs 1089，errors、queue、dropped、peer-close 和 panic 均为 0 | [`hci4-reconnect121-3x.json`](../tests/uiflow2/core2_native_hci/evidence-2026-10-25-hci4-reconnect121-3x.json) |
| Public firmware artifact refresh invariant | 发现同一 public firmware ID/version ID 背后的 CDN BIN 可以变化，旧缓存不能代表当前制品。`user_firmware_matrix.py` 现在首次运行和 `--resume` 都重新解析公开版本并强制下载；结果键为 `device:firmware:sha256`，字节变化不会复用旧完成结果。单测同时覆盖首次选择与 resume rebind。后续 functional row 对同一批刷新字节执行了 Device Service | [`user_firmware_matrix.py`](../platform/tools/user_firmware_matrix.py)、[`test_user_firmware_matrix.py`](../platform/tests/test_user_firmware_matrix.py)、[`user-firmware-simulation-matrix.md`](user-firmware-simulation-matrix.md) |
| Refreshed public artifacts static snapshot | 当前 CDN 的 4 个刷新样本已绑定实际 SHA256、字节数、芯片、Flash、bootloader、分区、app descriptor 和 partition count；四个静态结构分析均 PASS。该记录保留当时 `STATIC_PASS / FUNCTIONAL_NOT_RUN` 检查点，没有继承旧的 21 样本功能结论 | [`refreshed-public-artifacts-static.json`](../tests/firmware/evidence-2026-10-25-refreshed-public-artifacts-static.json)、[`user-firmware-simulation-matrix.md`](user-firmware-simulation-matrix.md) |
| Refreshed public artifacts full manifest | 四个刷新 BIN 均通过 FirmwareManifest validation，并绑定 source SHA、normalized artifact SHA、manifest ID、review finding 数、URL/credential/encoded blob 摘要和文件系统状态。四项 static review 均为 `REVIEW_REQUIRED`；两个 sparse 样本的归一化全 Flash SHA 与下载源 SHA 不同。该 Manifest 检查点本身不声明功能结果 | [`refreshed-public-artifacts-manifest.json`](../tests/firmware/evidence-2026-10-25-refreshed-public-artifacts-manifest.json)、[`firmware-manifest.md`](firmware-manifest.md) |
| Refreshed public artifacts functional execution | 同一四个公开 BIN 经 Device Service 执行并绑定实际 source/normalized SHA、session、frame、input 和 serial digest：`2 PASS / 2 PARTIAL / 0 FAIL`。XiaoZhi 显示 128×128 配网 UI；EDC Book 显示 480×800 启动/续读页；OpenAI Voice Assistant 因 NVS user data 缺失返回 `app_main()` 并保持黑屏；CrossPoint 因通用 session 未挂载 initialized SD fixture，重复 SDMMC OCR `0x107` 后显示 SD card error，归类 `runtime_fixture_gap` 而非 firmware FAIL。Matrix PASS 仍只覆盖 frame/input/runtime 层 | [`evidence.json`](../tests/firmware/evidence-2026-10-25-refreshed-four-functional/evidence.json)、[`user_firmware_matrix.py`](../platform/tools/user_firmware_matrix.py)、[`test_user_firmware_matrix.py`](../platform/tests/test_user_firmware_matrix.py) |
| Refreshed public artifacts with SD MBR fixture | 同一四个公开 BIN 加上内容寻址的 64 MiB FAT32+MBR SD fixture 后为 `3 PASS / 1 PARTIAL / 0 FAIL`。Device Service 把 fixture 复制到 session、重新校验 SHA 并以 writable `if=sd` 挂载；Matrix result key 包含 fixture SHA。CrossPoint 从无卡错误页进入 recent-books 主菜单并响应输入；XiaoZhi、EDC Book 保持 PASS；OpenAI Voice Assistant 仍因 NVS user data 缺失黑屏 | [`evidence.json`](../tests/firmware/evidence-2026-10-25-refreshed-four-functional-sd-mbr/evidence.json)、[`sd_image.py`](../platform/tools/sd_image.py)、[`device_service.py`](../platform/tools/device_service.py) |
| OpenAI first-boot NVS precondition | 公开 OpenAI AtomS3R BIN 的 24 KiB NVS 分区为全 `FF`，应用只读 `config/wifi_ssid`、`config/wifi_password`、`config/openaikey`。session-isolated NVS overlay 与 ESP-IDF generator 逐字节一致。Open fixture、正确 WPA2-PSK fixture 都在同一 BIN SHA 下取得 association、DHCP、`api.openai.com` DNS 与 TCP/443；WPA2 路径同时完成 M1-M4 和成对密钥 CCMP RX。错误密码 control 在 M2 MIC 被拒绝、reason 15 deauth、retry 且无 DHCP/HTTP。22/22 investigation checks PASS；真实 key/Realtime/audio、WPA3、group multicast、物理 RF 和硬件仍 `NOT RUN` | [`openai-nvs-precondition.json`](../tests/firmware/evidence-2026-10-25-openai-nvs-precondition.json)、[`run_test.py`](../tests/firmware/openai_nvs_precondition/run_test.py)、[`nvs_image.py`](../platform/tools/nvs_image.py)、[`device_service.py`](../platform/tools/device_service.py) |
| SHA-bound network-first review expectation | 通用 matrix v1 expectation 以 `device_id + firmware_id + sha256` 绑定审查意图，支持 UI、headless-serial 和 network-first；expectation digest、NVS/SD fixture SHA 进入结果键，明文 WiFi 密码被拒绝。公开 OpenAI BIN 使用 synthetic Open NVS 在 `runtime=qemu-wifi/profile=generic-observe` 完成 `wifi:connected`、DHCP、`api.openai.com` DNS、TCP/443 和 37-packet pcap；无需 UI frame 即按显式 marker/network 证据得到 PASS，session 以 `purge=0` 停止。voice、真实 key、Realtime/WebRTC、物理 WPA2/RF 和硬件仍 `NOT RUN` | [`network-first-review-expectation.json`](../tests/firmware/evidence-2026-10-25-network-first-review-expectation.json)、[`user_firmware_expectations.schema.json`](../platform/tools/user_firmware_expectations.schema.json)、[`user_firmware_matrix.py`](../platform/tools/user_firmware_matrix.py)、[`test_user_firmware_matrix.py`](../platform/tests/test_user_firmware_matrix.py) |
| S3 WPA2-PSK QEMU data plane | `runtime=qemu-wifi/profile=generic-observe` 在 ESP32-S3 上支持 Open/WPA2-PSK。Session-derived locally-administered MAC 同时写入 eFuse fixture 和 QEMU NIC；beacon/probe/assoc 广告 RSN，M1-M4 验证正确/错误密码，S3 radio RX 验证 CCMP 并提供 closed firmware 的 hardware-decrypted 布局。DHCP reply 以 pairwise-key 802.11 unicast 交付，guest 继续完成 DHCP、DNS 和 TCP/443。同一 patch 还通过 AtomS3R、StickS3、CoreS3 的 15/15 定向外设矩阵。`RUNTIME-05` 的 accepted virtual-device scope 已关闭；WPA3、group-key multicast、RF/PHY 和真机不在结论内 | [`openai-nvs-precondition.json`](../tests/firmware/evidence-2026-10-25-openai-nvs-precondition.json)、[`s3-wpa2-regression.json`](../tests/uiflow2/evidence-2026-10-25-s3-wpa2-regression.json)、[`0029-esp32s3-wpa2-psk-data-plane.patch`](../patches/qemu-m5stack-peripherals/0029-esp32s3-wpa2-psk-data-plane.patch)、[`test_device_service.py`](../platform/tests/test_device_service.py) |
| S3 WPA2 milestone regression | WPA2 patch 的 forward/reverse apply check 均 PASS；AtomS3R、StickS3、CoreS3 定向外设矩阵 `15/15 PASS`、无 retry。完整平台套件 `377/377 PASS`，文档契约 `20/20`，Node `2/2`；runtime coverage、peripheral catalog、QEMU profiles、project snapshot、selected Ruff 和 `git diff --check` 均 PASS。该结果只覆盖 virtual-device validation | [`s3-wpa2-regression.json`](../tests/uiflow2/evidence-2026-10-25-s3-wpa2-regression.json)、[`0029-esp32s3-wpa2-psk-data-plane.patch`](../patches/qemu-m5stack-peripherals/0029-esp32s3-wpa2-psk-data-plane.patch)、[`test_docs_consistency.py`](../platform/tests/test_docs_consistency.py) |
| Public firmware resume live refresh | 使用真实公开 metadata 与已存在 plan 执行 `--resume --plan-only`，四个样本全部重新下载、静态分析并重写 `refreshed_at`；SHA 与上一轮一致，未创建 Device Service session 或 QEMU。该结果验证 resume 数据面，不是固件功能结果 | [`public-resume-refresh-live.json`](../tests/firmware/evidence-2026-10-25-public-resume-refresh-live.json)、[`user_firmware_matrix.py`](../platform/tools/user_firmware_matrix.py)、[`user-firmware-simulation-matrix.md`](user-firmware-simulation-matrix.md) |
| IPv6 namespace cleanup evidence | runner 不再硬编码 `cleanup_completed`，改为读取 sandbox 实际 evidence，并联合校验 QEMU reap、DNS close 和 HTTP close；契约测试 PASS。该清理契约随后由下一行同一 guest 生命周期证据使用并关闭 | [`network_sandbox.py`](../platform/tools/network_sandbox.py)、[`ipv6_end_to_end/run_test.py`](../tests/network/ipv6_end_to_end/run_test.py)、[`test_network_sandbox.py`](../platform/tests/test_network_sandbox.py) |
| Guest IPv6 controlled AAAA + HTTP + denied-port | Linux arm64 private namespace 中，同一 UIFlow2 StickS3 test-build guest 通过 controlled resolver 取得 AAAA `FEC0::2`，完成 `/ipv6` HTTP 200，向 `fec0::2:18096` 的连接被 nftables 阻断；pcap 同时包含 allowed `18095` TCP 和 denied `18096` TCP，namespace/NAT、DNS/HTTP fixture 和 QEMU process 均清理完成。原厂 UIFlow2 仍未默认启用 IPv6 link-local | [`evidence-2026-10-25-ipv6-namespace-aaaa-http-pass.json`](../tests/network/ipv6_end_to_end/evidence-2026-10-25-ipv6-namespace-aaaa-http-pass.json)、[`uiflow2-sticks3-ipv6-test-build.patch`](../tests/network/ipv6_end_to_end/uiflow2-sticks3-ipv6-test-build.patch) |
| Worker control/runtime plane split | `WorkerAgent` 新增独立 `runtime_api` 与 `--runtime-service-url`：claim、worker/job heartbeat 和 terminal result 留在中央控制面，session create/wait/evidence/stop 全部发往执行面。单测验证控制 API 不收到任何 session 请求；真实 Linux namespace 的 no-QEMU control-plane 兼容路径在拆分后再次 `13/13 PASS`，token 未进入 server/worker 日志。该里程碑尚未启动 QEMU，执行面门禁由下一行取代 | [`worker_agent.py`](../platform/tools/worker_agent.py)、[`test_worker_agent.py`](../platform/tests/test_worker_agent.py)、[`control-runtime split smoke`](../tests/network/worker_cross_netns/evidence-2026-10-25-control-runtime-split-smoke.json) |
| Worker-local QEMU across network namespaces | central Device Service 和 worker-local runtime Device Service 分处两个 veth 连接的 Linux network namespace。worker 执行面上传并规范化 StickS3 镜像、启动真实 Linux arm64 QEMU、等待 running，再由 central service claim/heartbeat/result；source firmware、normalized artifact 和 QEMU SHA256 均绑定，manifest/serial/frame/QOM evidence 存在，token 不落日志，QEMU 与两个 namespace 均回收。18/18 checks PASS。QEMU 回收检查只认 `argv[0]` 的 `qemu-system-*`，修复了命令行参数含同名文字造成的假失败。该结果是一台主机上的两个 namespace，不声明物理跨主机 executor、自动发现、companion/evidence continuity 或生产多机调度 | [`worker-local-qemu-cross-netns-pass.json`](../tests/network/worker_cross_netns/evidence-2026-10-25-worker-local-qemu-cross-netns-pass.json)、[`run_test.py`](../tests/network/worker_cross_netns/run_test.py)、[`test_worker_cross_netns_paths.py`](../platform/tests/test_worker_cross_netns_paths.py) |
| Worker endpoint advertisement | `worker_agent.py --advertise-endpoint` 把无凭据 HTTP(S) 执行端点写入中央 worker directory；Linux veth fixture 从真实 `/api/v1/workers` 回读到该端点，连同认证、claim、heartbeat、result、cleanup 和 token redaction 共 `14/14 PASS`。这只证明静态注册，不证明自动发现或连接可达性 | [`endpoint-advertisement-smoke.json`](../tests/network/worker_cross_netns/evidence-2026-10-25-endpoint-advertisement-smoke.json)、[`worker_agent.py`](../platform/tools/worker_agent.py)、[`test_worker_agent.py`](../platform/tests/test_worker_agent.py) |
| Authenticated worker discovery | 真实 Device Service 广播 active-token HMAC 签名的 IPv4 multicast beacon；真实 `WorkerAgent --discover-control` 在无硬编码 URL 时发现 control plane、注册、heartbeat、停止并保留 worker history。错误 token 和 SIGHUP rotation 前旧 token 均无法发现/注册，rotation 后新 token 自动发现成功；token 不进入 beacon、service 或 worker 日志。未创建 Device Service session 或 QEMU。范围仅同一 multicast domain，NAT/跨子网和跨主机 executor 仍 `NOT RUN` | [`discovery-rotation-pass.json`](../tests/network/worker_discovery/evidence-2026-10-25-discovery-rotation-pass.json)、[`worker_discovery.py`](../platform/tools/worker_discovery.py)、[`test_worker_discovery.py`](../platform/tests/test_worker_discovery.py)、[`run_test.py`](../tests/network/worker_discovery/run_test.py) |
| Cross-subnet/NAT unicast discovery seed | privileged Linux fixture 建立 `10.213.2.0/24` worker 与 `10.213.1.0/24` control 两个独立 subnet，中间 router 开启 IPv4 forwarding 并 masquerade 到 control side。control-plane multicast announcer 存在但 beacon 不跨 router；worker 改用 reachable unicast seed，获取并验证同一 active-token HMAC beacon 后注册、heartbeat、停止。错误 token、rotation 前旧 token 均被拒绝；rotation 后新 token 通过 same seed 注册。control-side seed access log 只观察到 router `10.213.1.1`，证明 NAT 路径；token 不进入 beacon/log，runner/service/discovery 工具哈希无漂移，namespace、nftables 和进程全清理。三个独立运行 `3/3 PASS`、`23/23` checks。该证据是 virtual control-plane validation，不覆盖物理跨主机、无 reachable seed 的任意 NAT traversal、QEMU placement 或真机 | [`seed-nat-3x.json`](../tests/network/worker_discovery_seed/evidence-2026-10-25-seed-nat-3x.json)、[`worker_discovery_seed.py`](../platform/tools/worker_discovery_seed.py)、[`worker_discovery.py`](../platform/tools/worker_discovery.py)、[`run_test.py`](../tests/network/worker_discovery_seed/run_test.py) |
| Worker central-control-plane restart continuity | 两个真实 Device Service 分别作为 central control plane 和 worker-local runtime；worker claim job 后 central 停止并复用同一 state dir 重启，实测 downtime `2.2s`。第一次运行暴露 `runtime=qemu` 非网络 session 的 `nic` 未初始化并终止 QEMU；修复后 Worker 对 transient network failure 有界 retry，幂等重注册相同 instance/generation，原 `lease_id` heartbeat/result 收敛为 terminal `completed/PASS`；evidence ZIP 保留，runtime QEMU session 停止且进程回收。queue result 现保存 originating lease ID。该结果不覆盖 runtime service restart、跨主机进程迁移、companion 或真机 | [`initial-runtime-qemu-failure.json`](../tests/network/worker_control_restart/evidence-2026-10-25-initial-runtime-qemu-failure.json)、[`central-restart-pass.json`](../tests/network/worker_control_restart/evidence-2026-10-25-central-restart-pass.json)、[`worker_agent.py`](../platform/tools/worker_agent.py)、[`worker_queue.py`](../platform/tools/worker_queue.py)、[`run_test.py`](../tests/network/worker_control_restart/run_test.py) |
| Worker runtime-service restart continuity | Worker claim job 并启动真实 StickS3 QEMU 后，仅对 worker-local runtime Device Service 发 SIGKILL；QEMU 存活。`2.2s` 后同 port/state 新服务启动，按 PID start-time、QMP ownership 和 running 状态重新接管同一 session/PID。Worker 对已知 session 的 status/evidence/stop 做有界 transient retry；原 job/lease 最终 `completed/PASS`，evidence ZIP 含 manifest/serial，runtime session stopped、PID released、QEMU reaped。Session create 的独立 idempotency 证据见下一行；跨主机迁移和 companion/BLE 仍 `NOT RUN` | [`runtime-restart-pass.json`](../tests/network/worker_runtime_restart/evidence-2026-10-25-runtime-restart-pass.json)、[`worker_agent.py`](../platform/tools/worker_agent.py)、[`device_service.py`](../platform/tools/device_service.py)、[`run_test.py`](../tests/network/worker_runtime_restart/run_test.py) |
| Worker unified companion continuity | Trusted-host `uiflow2-sticks3-unified` session 在 BLE 初次 PASS、HTTP generation 1 已持久化后仅 SIGKILL runtime Device Service。新服务保持同一 QEMU PID，并通过 PID/start-time/command-SHA256 校验 adopt 原 BLE peer；HTTP fixture 在 profile port 重建为 generation 2。触发后，同一 peer 完成 GATT cycle 2，guest 发起第二次 `/unified` 请求并输出 `UNIFIED_STICKS3_HTTP_RECHECK_PASS`。Worker 通过有界 `evidence_delay_seconds` 等待最终状态后再取 evidence；原 job/lease `completed/PASS`，ZIP 含两代 HTTP、BLE continuity、serial、network/pcap，QEMU 和 companion 均清理，26/26 checks PASS。仅同一主机 virtual-device；namespace/Tab5/cross-host companion 与真机仍 `NOT RUN` | [`runtime-companion-continuity-pass.json`](../tests/network/worker_runtime_restart/evidence-2026-10-25-runtime-companion-continuity-pass.json)、[`README.md`](../tests/network/worker_runtime_restart/README.md)、[`ble_probe.py`](../platform/tools/ble_probe.py)、[`worker_agent.py`](../platform/tools/worker_agent.py)、[`device_service.py`](../platform/tools/device_service.py) |
| Session-create idempotency | 两个并发 `POST /sessions` 使用同一 caller key 和 canonical request，只创建一个 session/QEMU lease，两个响应返回同一 session ID；异请求复用 key 返回 `409 session_idempotency_conflict`。`session-idempotency.json` 只保存 key/request SHA 和 session ID，mode `0600`；service restart 后相同请求仍返回原 session。跨主机、跨 API token/tenant 的 idempotency 存储仍 `NOT RUN` | [`session-create-idempotency-pass.json`](../tests/network/session_idempotency/evidence-2026-10-25-session-create-idempotency-pass.json)、[`device_service.py`](../platform/tools/device_service.py)、[`worker_agent.py`](../platform/tools/worker_agent.py)、[`run_test.py`](../tests/network/session_idempotency/run_test.py) |
| Capability declaration consistency（历史检查点） | required/optional capability 归一化后若重叠，importer 与 manifest structure validation 均拒绝；未知 optional 产生 `unknown_optional_capability`，目标 profile 缺少 optional 能力产生 `unsupported_optional_capability` warning，不改变候选状态。required mismatch 仍返回结构化错误；`camera` on StickS3 的 required/optional 对照已保留。该检查点当时把 unknown required 作为 warning；其 fail-closed 语义已由 `2026-10-26` 顶部行取代，原始 evidence 不改写 | [`capability-consistency.json`](../tests/firmware/evidence-2026-10-25-capability-required-optional-consistency.json)、[`firmware_manifest.py`](../platform/tools/firmware_manifest.py)、[`test_firmware_manifest.py`](../platform/tests/test_firmware_manifest.py) |
| Capability declaration consistency | required/optional capability 归一化后若重叠，importer 与 manifest structure validation 均拒绝；未知 optional 产生 `unknown_optional_capability`，目标 profile 缺少 optional 能力产生 `unsupported_optional_capability` warning，不改变候选状态。required mismatch 仍返回结构化错误；`camera` on StickS3 的 required/optional 对照已保留 | [`capability-consistency.json`](../tests/firmware/evidence-2026-10-25-capability-required-optional-consistency.json)、[`firmware_manifest.py`](../platform/tools/firmware_manifest.py)、[`test_firmware_manifest.py`](../platform/tests/test_firmware_manifest.py) |
| Security evidence consistency | sdkconfig 与自报 eFuse summary 的 secure boot / Flash Encryption 状态现在做双向冲突检查：config on/eFuse off、config off/eFuse on、v1/v2 模式不一致，以及缺失 secure-boot/XTS key-purpose 都产生结构化 warning。eFuse 仍标记 `unverified`，不升级为真机安全 PASS | [`security-evidence-conflicts.json`](../tests/firmware/evidence-2026-10-25-security-evidence-conflicts.json)、[`firmware_manifest.py`](../platform/tools/firmware_manifest.py)、[`firmware-manifest.md`](firmware-manifest.md) |
| Radio capability detection | sdkconfig 现在把 Classic Bluetooth 与 IEEE 802.15.4/Zigbee 分别记录为 `classic-bluetooth` 和 `ieee802154`，不再把 Zigbee 构建开关当未知字符串或把 classic-only 直接等同于 BLE 数据面。目标 profile 缺失时仅产生 detected warning；这不证明 BLE/Zigbee code path 或 commissioning | [`radio-capability-detection.json`](../tests/firmware/evidence-2026-10-25-radio-capability-detection.json)、[`test_firmware_manifest.py`](../platform/tests/test_firmware_manifest.py)、[`firmware-manifest.md`](firmware-manifest.md) |
| Regression baseline | resume/SHA rebind 与 control/runtime plane split 后完整平台套件为 `351/351 PASS`；Node SHA256/upload client 测试 `2/2 PASS`；runtime coverage、peripheral catalog、QEMU profiles 和自动快照校验全部通过；Python fatal Ruff 与 touched-code `F401/F841` 检查也通过。结果只说明检查项通过，不是真机测量 | [`test_docs_consistency.py`](../platform/tests/test_docs_consistency.py)、[`project_snapshot.py`](../platform/tools/project_snapshot.py) |
| Repository reconciliation baseline | Core2 三 lease 121 轮、guest IPv6 namespace、refreshed firmware 和 session-isolated SD fixture 证据登记后，平台套件 `363/363 PASS`，文档契约 `19/19`，Node `2/2`；runtime coverage、peripheral catalog、QEMU profiles、project snapshot 和 compileall 均通过。GitHub Actions run `40127676353` 在 `437d417` 上成功，`network-namespace-policy` 与 `platform-contracts` 两个 job 均 PASS | [`project-status.md`](project-status.md)、[`test_docs_consistency.py`](../platform/tests/test_docs_consistency.py)、[`CI 40127676353`](https://github.com/m5agent/m5stack-esp-emulator/actions/runs/40127676353) |
| Worker-local execution reconciliation baseline | 将 worker-local QEMU PASS 写回当前状态、Backlog、workstreams、API、code map、网络方案、服务架构和 service README 后，平台套件 `368/368 PASS`，文档契约 `19/19`，Node `2/2`；runtime coverage、peripheral catalog、QEMU profiles、project snapshot、compileall、`E9/F` Ruff 与 `git diff --check` 均通过。GitHub Actions run `40129610677` 在 `461d489` 上成功，`network-namespace-policy` 与 `platform-contracts` 两个 job 均 PASS；前一 run 的无-QEMU result-shape 差异由本次提交修复。文档测试同时锁定“一台主机的两个 namespace 已 PASS”和“物理跨主机 executor/reattach、自动发现、companion continuity 仍 NOT RUN” | [`project-status.md`](project-status.md)、[`validation-ledger.md`](validation-ledger.md)、[`project-snapshot.md`](project-snapshot.md)、[`test_docs_consistency.py`](../platform/tests/test_docs_consistency.py)、[`CI 40129610677`](https://github.com/m5agent/m5stack-esp-emulator/actions/runs/40129610677) |
| NVS and QEMU WiFi model reconciliation baseline（历史） | 历史检查点：NVS partition fixture、任意 S3 `qemu-wifi/generic-observe`、OpenAI NVS 对照和当时仍开放的非空密码 gap 登记后，平台套件 `376/376 PASS`，OpenAI probe `13/13`。该行保留当时 `RUNTIME-05 OPEN` 的事实，当前状态已由上方正常/错误 WPA2 三组 Device Service 证据和 15/15 S3 regression 取代；不能把该历史 PASS 当作非空密码已通过 | [`openai-nvs-precondition.json`](../tests/firmware/evidence-2026-10-25-openai-nvs-precondition.json)、[`runtime-model-gap-register.md`](runtime-model-gap-register.md)、[`project-backlog.md`](project-backlog.md) |

## 2026-10-24

| 工作流 | 结果 | 证据 |
| --- | --- | --- |
| 代码与文档基线 | 动态测试/矩阵计数集中到 `project-status.md`；README、文档导航和工作流台账改为链接；设备 catalog 与 QEMU profile 增加日期/状态交叉校验，并修正 AtomS3R、PaperMono 旧元数据；该检查点为平台套件 `297/297 PASS`，后续当前总数仍只由 `project-status.md` 维护 | [`test_qemu_profiles.py`](../platform/tests/test_qemu_profiles.py)、[`test_docs_consistency.py`](../platform/tests/test_docs_consistency.py) |
| 文档结构与自动快照 | 新增 `project-snapshot.py`，从设备 catalog、QEMU profile、peripheral status、公开固件 evidence、runtime gap 和 Backlog Task 板生成项目快照；README、工作流、统一运行时契约、网络方案和适配矩阵移除重复动态事实，早期 bring-up 批次标为历史；修正 `FW-03` 的 6 台/18 样本旧计数为 7 台/21 样本。完整平台套件 `324/324 PASS`，`runtime_coverage`、`peripheral_catalog`、`qemu_profiles` 和 `project_snapshot --check` 均 PASS | [`project_snapshot.py`](../platform/tools/project_snapshot.py)、[`project-snapshot.md`](project-snapshot.md)、[`test_docs_consistency.py`](../platform/tests/test_docs_consistency.py) |
| 文件系统权限策略 | LittleFS/SPIFFS 每个文件记录 `permission_policy` 并明确 `unix_mode=not-recorded`；FAT 文件和目录记录原生 read-only/hidden/system/archive 属性；构造 read-only FAT 文件只标记属性存在，不升级成 POSIX ACL 或运行态不可变。Manifest schema 暴露 permission model/summary，运行态权限强制仍为 `NOT RUN` | [`filesystem-permission-policy.json`](../tests/firmware/evidence-2026-10-24-filesystem-permission-policy.json)、[`firmware_filesystems.py`](../platform/tools/firmware_filesystems.py)、[`test_firmware_analysis.py`](../platform/tests/test_firmware_analysis.py) |
| 包内源码许可扫描 | 对 `.c/.cc/.cpp/.h/.hh/.hpp/.py/.js/.mjs/.ts/.tsx` 执行有界 SPDX header 扫描，限制为 2048 文件、64 MiB 总计、单文件 2 MiB 和 64 KiB header；记录文件 SHA256、脱敏路径和声明，并纳入 `license_policy.source_code_declarations`。合成源码包含 MIT/Apache-2.0 与敏感路径脱敏，无 allowlist 时保持 `REVIEW_REQUIRED`；生成代码、包外 vendor 和法律结论未声明 | [`source-license-scan.json`](../tests/firmware/evidence-2026-10-24-source-license-scan.json)、[`firmware_manifest.py`](../platform/tools/firmware_manifest.py)、[`test_firmware_manifest.py`](../platform/tests/test_firmware_manifest.py) |
| Core2 legacy I2C 路由 trace | 同一 `UIFlow_Core2` public firmware 在 `m5core2` 上成功完成 AXP address `0x34` probe，并读出 chip id `0x4a`；随后 `disable_timer_interrupt()` 的下一事务发往 address `0x51`、`start_rc=1`（无 ACK），并在产生新的 address-`0x34` PMIC transaction 前返回 `I2C bus error (19)`。冻结 BM8563 qstr、RTC 地址和调用栈指向 legacy controller 到板级 I2C bus 的 routing/handoff 缺口；没有关闭 runtime gap | [`core2-axp-i2c-trace.json`](../tests/firmware/evidence-2026-10-24-core2-axp-i2c-trace.json)、[`core2-public-firmware-model-gaps.json`](../tests/firmware/evidence-2026-10-24-core2-public-firmware-model-gaps.json) |
| 网络隔离 | private net/mount namespace、fail-closed、controlled DNS、TLS/Host allowlist、200/403 与 pcap 联合 PASS | [`controlled-dns-pass.json`](../tests/network/tls_allowlist/evidence-2026-10-24-controlled-dns-pass.json) |
| Controlled DNS A/AAAA | 同一 allowlisted 名称的 UDP A、AAAA 查询分别返回类型和 payload 正确的记录；unknown name 返回 NXDOMAIN；A/AAAA decision log 与 invalid/unspecified/multicast/oversized record 拒绝契约 PASS。该行是 resolver 数据面基线；同 guest controlled AAAA 随后由 Linux namespace guest PASS 关闭 | [`controlled-dns-aaaa.json`](../tests/network/tls_allowlist/evidence-2026-10-24-controlled-dns-aaaa.json)、[`test_network_sandbox.py`](../platform/tests/test_network_sandbox.py) |
| Same-guest IPv6 TCP/HTTP with a test build | 专用 UIFlow2 StickS3 测试构建在 `IP_EVENT_STA_GOT_IP` 后创建 IPv6 link-local；同一 guest 通过 `AF_INET6` 向 `fec0::2:18095` 完成 HTTP/1.0 200，fixture 收到 `/ipv6`，pcap 记录同一条 site-local IPv6 TCP 双向流。evidence 绑定 base/probe/QEMU、test-build app/ELF 和 patch SHA256；该 direct 结果之后由 Linux namespace controlled AAAA/denied-port/cleanup PASS 扩展 | [`evidence-2026-10-24-guest-ipv6-direct-test-build-pass.json`](../tests/network/ipv6_end_to_end/evidence-2026-10-24-guest-ipv6-direct-test-build-pass.json)、[`uiflow2-sticks3-ipv6-test-build.patch`](../tests/network/ipv6_end_to_end/uiflow2-sticks3-ipv6-test-build.patch) |
| Exact IPv4/IPv6 egress | 独立 privileged Linux container 连续 `2/2 PASS`：worker namespace 经 IPv4/IPv6 default route 和 inner veth 到 upstream；允许地址/端口 200，两个拒绝端口和两个拒绝地址均超时；upstream 源地址证明 IPv4/IPv6 masquerade；nftables 默认 drop、IPv6 neighbor control、inner NAT/namespace 与 worker/upstream namespace 清理全部通过。同一 source commit 的 GitHub Actions `network-namespace-policy` job 再次 PASS，平台契约 job `336/336 PASS`。不是固件、公网或 IPv6 DNS 结论 | [`dual-stack-docker-pass.json`](../tests/network/egress_allowlist/evidence-2026-10-24-dual-stack-docker-pass.json)、[`dual-stack-github-actions-pass.json`](../tests/network/egress_allowlist/evidence-2026-10-24-dual-stack-github-actions-pass.json) |
| 错误密码 P0 | ESP32-S3 ESP-IDF guest 使用错误凭据后发生 6 次 auth/reject；无 DHCP、无 HTTP 进度；固件输出 `HTTP_TPUT_RESULT: FAILED (no IP in 20s)`，SoftAP 记录 wrong-password warning；`7/7` 负向检查同次 PASS | [`wrong-password-pass.json`](../tests/network/wrong_password/evidence-2026-10-24-wrong-password-pass.json) |
| DNS/UDP 数据面 | ESP32-S3 guest 完成 DHCP 和 DNS 解析，host peer 收到固定 UDP 载荷，guest 收到带前缀的同载荷回包；5/5 检查 PASS | [`dns-udp-pass.json`](../tests/network/idf_dns_udp/evidence-2026-10-24-dns-udp-pass.json) |
| FirmwareManifest 公共样本 | 公开 StickS3 Weather `2108939572843147265` 的 merged 与 WebBurner 三 segment 输入均规范化到同一 `8 MiB` artifact SHA256；camera-on-StickS3 返回结构化 `unsupported_capability`；Manifest 19 项、定向 service/security 6 项 PASS | [`public-manifest-web-conformance.json`](../tests/firmware/evidence-2026-10-24-public-manifest-web-conformance.json) |
| IP/端口 egress | nftables 默认 drop；允许/拒绝端口、允许/拒绝 IP、`1.1.1.1:80` veth/NAT、namespace/NAT 清理 PASS；TLS guest 在同一策略下 PASS | [`ip-port-pass.json`](../tests/network/egress_allowlist/evidence-2026-10-24-ip-port-pass.json) |
| Linux CI | Ubuntu runner 执行当时的 `236` 项平台测试和 fail-closed namespace/egress fixture；允许端点、拒绝目标、veth/NAT 与清理 PASS。该数字是历史证据，当前套件规模见项目当前状态 | [`github-actions-pass.json`](../tests/network/egress_allowlist/evidence-2026-10-24-github-actions-pass.json) |
| AP/radio loss | StickS3 guest 先 DHCP/HTTP；QOM `radio-enabled=false` 后扫描为 0，恢复后扫描为 1，同一 guest 再 DHCP 并完成 `/after` HTTP；pcap 含两组 DORA | [`radio-loss-pass.json`](../tests/network/reconnect_probe/evidence-2026-10-24-radio-loss-pass.json) |
| AP/radio loss 自动化回归 | 同一 `qemu-wifi` session 中 radio QOM `false→true`，扫描 `1→0→1`，两次 DHCP、前后 HTTP 200；pcap 含 2 组 DORA/OFFER/REQUEST/ACK 和两条受控 HTTP 流；16/16 checks PASS | [`radio-loss-recovery-pass.json`](../tests/network/reconnect_probe/evidence-2026-10-24-radio-loss-recovery-pass.json) |
| DHCP renewal | ESP-IDF guest 调用 `netifapi_dhcp_renew()`；pcap 出现初次 DORA 后的 `REQUEST/ACK`，地址保持并通过 HTTP | [`renewal-pass.json`](../tests/network/idf_dhcp_renewal/evidence-2026-10-24-renewal-pass.json) |
| 双设备 lab fabric | private namespace 内两台 StickS3 完成 DHCP；A→B TCP `19123` 请求/响应成功，两侧 pcap 均有双向 payload hash；宿主、公网、metadata、默认路由不可达，namespace 已清理 | [`two-guest-pass.json`](../tests/network/lab_fabric/evidence-2026-10-24-two-guest-pass.json) |
| 本地 worker lifecycle | 真实 StickS3 `qemu-wifi` lease：heartbeat、active lease、drain、活动会话保留、resume；强杀服务进程组后 generation 递增，旧 lease 标为 abandoned，会话恢复为 interrupted failed | [`worker-lifecycle-pass.json`](../tests/network/worker_lifecycle/evidence-2026-10-24-pass.json) |
| 远程 worker 注册目录 | 持久 identity/generation、stale 判定、live-instance 冲突、heartbeat/drain/stop、capability/结果上限、原子 `0600` 状态文件；HTTP 契约与 Bearer token 路径 PASS。该结果只证明目录 API，不证明 worker supervisor、调度或活动 QEMU 接管 | [`test_worker_directory.py`](../platform/tests/test_worker_directory.py)、[`test_device_service.py`](../platform/tests/test_device_service.py) |
| 远程 durable job queue | 幂等 submit/replay、capability matching、FIFO claim、identity-bound lease heartbeat、expiry retry、terminal result/cancel、worker stale/stop/generation 回收、持久重启恢复和 HTTP `/api/v1/jobs` 契约 PASS | [`queue-pass.json`](../tests/network/worker_queue/evidence-2026-10-24-queue-pass.json)、[`test_worker_queue.py`](../platform/tests/test_worker_queue.py)、[`test_device_service.py`](../platform/tests/test_device_service.py) |
| HTTP-only worker executor | 独立进程持久 generation、注册 worker、claim job、worker/job heartbeat、创建真实 StickS3 QEMU session、等待 running、下载 evidence ZIP/SHA256、`purge=0` 停止并提交 completed/PASS；live `1/1` PASS | [`executor-pass.json`](../tests/network/worker_executor/evidence-2026-10-24-executor-pass.json)、[`test_worker_agent.py`](../platform/tests/test_worker_agent.py) |
| Worker HMAC authentication | worker ID/instance/generation 派生 key；claim/heartbeat/result 需要 timestamp、nonce、body signature；unsigned claim `401`、body identity mismatch 与 replay 拒绝；启用 token 的真实 StickS3 job 仍 completed/PASS，live `1/1` PASS | [`executor-auth-pass.json`](../tests/network/worker_executor/evidence-2026-10-24-executor-auth-pass.json)、[`test_worker_auth.py`](../platform/tests/test_worker_auth.py) |
| Worker HTTPS/mTLS | 真实 Device Service 进程使用临时测试 PKI 启动 mTLS；TLS 1.3 协商、服务端证书校验、无可信客户端证书拒绝、有证书通过；Bearer + worker HMAC 保持，unsigned claim `401`，worker agent 注册/heartbeat/claim/stop over mTLS 退出 0；明文 HTTP 回退失败 | [`worker_tls/evidence-2026-10-24-tls-mtls-pass.json`](../tests/network/worker_tls/evidence-2026-10-24-tls-mtls-pass.json)、[`test_transport_security.py`](../platform/tests/test_transport_security.py) |
| Worker real QEMU job over mTLS | 在 mTLS 服务上上传并 compose 完整 StickS3 flash；签名 worker 领取 durable job，启动真实 QEMU session，下载 evidence ZIP，回查 SHA256 后提交 terminal `completed/PASS`，attempts=1，agent exit 0。该 job 不声明 unified board/network/UI PASS | [`worker_tls/evidence-2026-10-24-tls-mtls-qemu-job-pass.json`](../tests/network/worker_tls/evidence-2026-10-24-tls-mtls-qemu-job-pass.json) |
| Worker unified StickS3 job over mTLS | 通过 mTLS 上传并 compose unified StickS3 flash，签名 worker 在真实 `qemu-unified/profile=uiflow2-sticks3-unified` session 中完成 board/WiFi/BLE markers、network evidence、pcap、PNG frame、evidence SHA256 和 terminal `completed/PASS`，attempts=1 | [`worker_tls/evidence-2026-10-24-tls-mtls-unified-job-pass.json`](../tests/network/worker_tls/evidence-2026-10-24-tls-mtls-unified-job-pass.json) |
| Worker TLS/token rotation | 服务端和 worker 分别监听 A/B 临时 PKI 与 token 文件；原子替换后发送 `SIGHUP`。旧客户端 CA 身份和旧 master token 返回 `401`，新身份通过；worker 记录 `worker credentials reloaded`，再完成真实 QEMU job 的 `completed/PASS`、attempts=1 和 evidence SHA256 回查。只覆盖同主机 loopback 与新连接/后续请求，不声明零中断 draining | [`worker_tls/evidence-2026-10-24-security-rotation-job-pass.json`](../tests/network/worker_tls/evidence-2026-10-24-security-rotation-job-pass.json)、[`run_rotation_test.py`](../tests/network/worker_tls/run_rotation_test.py) |
| Worker rotation activity drain | 在 `SIGHUP` 前保留一个旧 token 的未完成 artifact 上传；服务先输出 drain marker，请求完成并返回 `201` 后才 reload。随后旧 CA/token 拒绝、新凭据完成真实 QEMU job；另有 gate 单元测试覆盖 active request 等待和 timeout 时保留旧配置。只覆盖同主机 loopback，不声明旧/新客户端重叠迁移 | [`worker_tls/evidence-2026-10-24-security-rotation-drain-job-pass.json`](../tests/network/worker_tls/evidence-2026-10-24-security-rotation-drain-job-pass.json)、[`test_transport_security.py`](../platform/tests/test_transport_security.py) |
| Worker credential bounded overlap | A/B previous token 与 client CA 同时启用时，旧客户端和新客户端、旧 token 和新 token 在第一阶段均可认证；worker 切到新身份后删除 previous 文件并再次 `SIGHUP`，旧 CA/token 最终拒绝，新凭据完成真实 QEMU job。客户端迁移为手工 staged，不声明自动化 fleet migration | [`worker_tls/evidence-2026-10-24-security-rotation-overlap-job-pass.json`](../tests/network/worker_tls/evidence-2026-10-24-security-rotation-overlap-job-pass.json)、[`test_worker_auth.py`](../platform/tests/test_worker_auth.py) |
| Worker generation-pointer fleet migration | Device Service 与两个独立 worker 实跑 A→A+B server-trust→B：先确认两 worker 均加载 A+B trust bridge，服务端进入 A/B overlap；原子替换单个 generation pointer 后，两 worker 在下一请求自动加载一致的 token/CA/client key 集合并写 secret-free receipt；两 worker 以 B 身份 heartbeat，移除 previous 后旧 TLS/token 拒绝。未逐个发送 worker `SIGHUP`；仍是同主机 loopback，不覆盖自动主机发现或跨主机迁移 | [`fleet-credential-migration-pass.json`](../tests/network/worker_tls/evidence-2026-10-24-fleet-credential-migration-pass.json)、[`run_fleet_migration_test.py`](../tests/network/worker_tls/run_fleet_migration_test.py)、[`test_worker_agent.py`](../platform/tests/test_worker_agent.py) |
| 本地 QEMU restart re-attach | 单元/契约覆盖 PID start-time、session QMP ownership、`query-status=running`、缺失 identity 与 stale start-time 拒绝；真实服务 SIGKILL 仅杀服务、保留 QEMU，同状态目录重启后接管同一 PID、generation 2 lease，停止时清理 QEMU，live `1/1` PASS | [`reattach-pass.json`](../tests/network/worker_reattach/evidence-2026-10-24-reattach-pass.json)、[`test_device_service.py`](../platform/tests/test_device_service.py) |
| Cross-namespace worker control plane | 真实 Device Service 与 `WorkerAgent` 分处两个 veth 连接的 network namespace；Bearer+worker HMAC 注册、capability job submit/claim、worker/job heartbeat、terminal completed、worker stop、token 不落日志和 namespace 清理均 PASS。fixture 明确 `qemu_started=false`、`device_session_created=false`；跨主机 QEMU executor/reattach 与 companion continuity 仍 `NOT RUN` | [`cross-namespace-pass.json`](../tests/network/worker_cross_netns/evidence-2026-10-24-cross-namespace-pass.json)、[`run_test.py`](../tests/network/worker_cross_netns/run_test.py) |
| 共享 WiFi + 全矩阵 | patch `0028` 后 S3/C6/Core2 `67/67` case、`274/274` check，全部 `attempts=1`、`retry_used=false`；Cardputer-ADV 键盘 settle 已加固 | [`dual-guest-fabric-matrix.json`](../tests/uiflow2/evidence-2026-10-24-dual-guest-fabric-matrix.json) |
| 共享 QEMU | ESP32-S3 AES/GDMA 外部内存读取修复；当轮全矩阵 `67/67`、`274/274`，全部首轮无重试 | [`gdma-external-memory-matrix.json`](../tests/uiflow2/evidence-2026-10-24-gdma-external-memory-matrix.json) |
| 固件文件系统 | LittleFS 与只读 FAT12/16/32 文件清单、SHA256、LFN、敏感路径脱敏与 SPDX 提取 | [`fat-inventory.json`](../tests/firmware/evidence-2026-10-24-fat-inventory.json) |
| SPIFFS 文件清单 | 8 个声明配置的自包含多索引样本 PASS；LUT 与 page header 不一致、随机损坏输入均 `INVALID`；ESP-IDF `spiffsgen.py` canonical 镜像和 60000-byte 多索引文件 PASS | [`spiffs-inventory.json`](../tests/firmware/evidence-2026-10-24-spiffs-inventory.json) |
| 固件上传 | 可恢复 chunk artifact upload 的连续 offset、per-chunk/final SHA256、失败回滚、原子 metadata、abort 和 staging GC | [`streaming-artifact-upload.json`](../tests/firmware/evidence-2026-10-24-streaming-artifact-upload.json) |
| WebBurner | 浏览器流式 SHA256、4 MiB 多 chunk、进度/重试/取消、刷新恢复和 package → FirmwareManifest import；9.44 MiB 三 chunk 探针 PASS | [`webburner-ui.json`](../tests/firmware/evidence-2026-10-24-webburner-ui.json) |
| 固件安全配置 | 解析脱敏 `espefuse summary --format json`，区分镜像、sdkconfig、分区 flag 与 eFuse 证据；安全启动/Flash Encryption preflight 按预期拒绝 | [`efuse-security.json`](../tests/firmware/evidence-2026-10-24-efuse-security.json) |
| WebBurner capability 声明 | Browser client 发送 required/optional arrays；API 规范化 `screen→display`、去重并限制 64×64；非法声明返回 `400 invalid_capability_requirements`；StickS3 上声明 `camera` 返回 `409 unsupported_firmware_capability` 和结构化 issue，而 `wifi/display` manifest PASS。该证据只覆盖 manifest/API/browser 契约，不证明声明与代码路径完全一致或真机能力 | [`webburner-capability-declarations.json`](../tests/firmware/evidence-2026-10-24-webburner-capability-declarations.json)、[`test_firmware_manifest.py`](../platform/tests/test_firmware_manifest.py)、[`test_device_service.py`](../platform/tests/test_device_service.py) |
| sdkconfig capability 观察 | 带 `CONFIG_ESP_WIFI_ENABLED=y`、`CONFIG_BT_ENABLED=y`、`CONFIG_SPIRAM=y` 的测试包在 manifest 中生成 `capabilities.detected`；Cardputer-ADV profile 缺失 PSRAM 时产生 `detected_capability_unavailable` warning，但 manifest 保持 PASS 且不把 detected 自动提升为 required。该结果只说明构建开关与 profile 不一致，不证明代码实际调用或运行态能力 | [`sdkconfig-capability-detection.json`](../tests/firmware/evidence-2026-10-24-sdkconfig-capability-detection.json)、[`test_firmware_manifest.py`](../platform/tests/test_firmware_manifest.py) |
| 固件许可策略 | provenance、文件系统 SPDX、SBOM 声明汇总；allowlist PASS、denylist REJECTED、无 allowlist/无声明/unknown 保持 REVIEW_REQUIRED；策略不是完整源码扫描或法律意见 | [`license-policy.json`](../tests/firmware/evidence-2026-10-24-license-policy.json) |
| 跨厂商公开固件 runtime matrix | 6 台 S3/C6 设备、18 个 MOST_DOWNLOADED 非基线公开样本（8 官方、10 社区）；全部静态分析有效并经 Device Service 执行。10 个渲染非空首帧、保持运行且输入可观测为 PASS；8 个 PARTIAL，其中 Zigbee 未建模 radio 和 C6 软件复位 chip-id 错误标记为 2 个 `runtime_model_gap`。不是全设备族覆盖或硬件结论 | [`cross-vendor-runtime-model-gaps.json`](../tests/firmware/evidence-2026-10-24-cross-vendor-runtime-model-gaps.json)、[`test_user_firmware_matrix.py`](../platform/tests/test_user_firmware_matrix.py) |
| C6 Zigbee `thread-sim` 可行性 | 源码构建 ESP-IDF HA switch/light 在 `esp-emu 0.50.0 --thread-sim` 下产生 21 个 switch→light 和 17 个 light→switch 802.15.4 帧；协调器组网和 light steering 均启动，但 `Joined network` 与 On/Off 命令未出现，结构化返回 `PARTIAL/runtime_model_gap` | [`c6-zigbee-thread-sim-feasibility.json`](../tests/firmware/evidence-2026-10-24-c6-zigbee-thread-sim-feasibility.json)、[`run_feasibility.py`](../tests/firmware/c6_zigbee_thread_sim/run_feasibility.py) |
| Core2 热门公开固件扩展（2026-10-24 快照） | 3 个 MOST_DOWNLOADED 官方 Core2 固件以 90 秒窗口经 Device Service 执行，全部 `PARTIAL/runtime_model_gap`、0 黑帧。`UIFlow_Core2`/`Core2FactoryTest` 在 AXP 发现后暴露当时的 I2C 板级交接缺口，默认 AXP2101 与 AXP192 override 均复现；`Core2_For_AWS` 当时为 ATECC608 未建模。matrix HTTP wait 超时误杀已修复，失败快照保留。该行是历史快照；`UIFlow_Core2` 已由 `Core2 legacy shared board I2C` 行复核并越过原 I2C 错误，`Core2FactoryTest` 的修复后重跑仍为 `NOT RUN`，ATECC608 初始化/identity 后续由 `0085` 关闭 | [`core2-public-firmware-model-gaps.json`](../tests/firmware/evidence-2026-10-24-core2-public-firmware-model-gaps.json)、[`shared-board follow-up`](../tests/firmware/evidence-2026-10-25-core2-shared-board-i2c.json)、[`ATECC608 follow-up`](evidence/2026-10-29-core2-atecc608/README.md)、[`test_user_firmware_matrix.py`](../platform/tests/test_user_firmware_matrix.py) |
| C6 软件复位 Flash/PMP 修复 | 16 MiB Flash 的 4-byte 读模式保留；legacy `0x02/0x20` 固定按 3-byte 地址解析，显式 4-byte opcode 不变；C6 reset 清空 PMP/mseccfg/TLB。同一 Meshtastic SHA 经 Device Service 重跑不再出现 `Invalid chip id`，offset 0 bootloader 头保持 chip id 13，`runtime_model_gaps=[]`；Nesso 官方外设组 `5/5`、NanoC6 板级探针 PASS。样本仍有独立 Instruction access fault，完整功能 `PARTIAL`，物理硬件 `NOT RUN` | [`c6-soft-reset-flash-addressing.json`](../tests/firmware/evidence-2026-10-24-c6-soft-reset-flash-addressing.json)、[`0006-espressif-riscv-reset-pmp.patch`](../patches/qemu-esp32c6-uiflow2-adapters/0006-espressif-riscv-reset-pmp.patch) |
| Core2 稳定性 | 确定性 TCG/icount 下独立启动 `10/10` 首轮 PASS；同 guest board+WiFi+公网+native-VHCI BLE `3/3` | [`native-vhci-pinned.json`](../tests/uiflow2/unified_core2/evidence-2026-10-24-native-vhci-pinned.json) |
| Core2 Device Service | `qemu-unified/profile=core2-native-vhci` 单 lease 返回 frame、QOM、pcap、bridge 和 peer evidence | [`native-vhci-service.json`](../tests/uiflow2/unified_core2/evidence-2026-10-23-native-vhci-service.json) |
| Core2 repeated lease | 同一 GDB 诊断桥 repeated lease 仅 `1/2`，证明该路径不能作为稳定后端 | [`native-vhci-service-stability.json`](../tests/uiflow2/unified_core2/evidence-2026-10-24-native-vhci-service-stability.json) |
| Core2 native-HCI `HCI-1` | QEMU H4 chardev framing、32 packet bounded queue、overflow、peer、clean shutdown 和 QOM counters PASS | [`transport-pass.json`](../tests/uiflow2/core2_native_hci/evidence-2026-10-24-transport-pass.json) |
| Core2 native-HCI `HCI-2` | 不启动 GDB，从真实 VHCI shared memory 捕获 stock HCI Reset `01030c00`；完整命令序列等待 C2H | [`guest-h2c.json`](../tests/uiflow2/core2_native_hci/evidence-2026-10-24-guest-h2c.json) |
| Core2 native-HCI `HCI-3a` | 诊断性单包 C2H：callback status 0，Reset Complete 后 guest 发出下一条 H2C，targeted `5/5`。后续审计不支持把它扩展成产品后端 | [`c2h-delivery.json`](../tests/uiflow2/core2_native_hci/evidence-2026-10-24-c2h-delivery.json) |
| Core2 native-HCI internal-controller relay | 历史变体：Bumble peer 已发现/连接并完成首个 ATT request/response；第二个 ATT request 后 guest `ack returned 12` 并 Reset。该路径不是最终 API-boundary/HLI 方案 | [`hci3b-diagnostic.json`](../tests/uiflow2/core2_native_hci/evidence-2026-10-24-hci3b-diagnostic.json) |
| Core2 native-HCI API boundary | GDB return 语义审计确认 pre-entry API hook 不旋转 Xtensa window；实验性 QEMU API hook 完成广播、连接、NUS discovery 和订阅，但 final write/notify transaction 仍超时，实验未保留 | [`hci3b-api-boundary-audit.json`](../tests/uiflow2/core2_native_hci/evidence-2026-10-24-hci3b-api-boundary-audit.json) |
| Core2 native-HCI MTU negative case | 历史 `2/2` 使用 21-byte probe，形成 24-byte ATT PDU，超过 guest 默认 MTU 23；协议栈 trace 显示 `chan-found=9`、`mtu-reject=1`、`rxfn=8`，在 ATT dispatch 前拒绝，后续已用 17-byte PDU 闭环 | [`notification-fail.json`](../tests/uiflow2/core2_native_hci/evidence-2026-10-24-hci3b-hli-api-notification-fail.json)、[`oversize-att-mtu.json`](../tests/uiflow2/core2_native_hci/evidence-2026-10-24-oversize-att-mtu.json) |
| Core2 native-HCI `HCI-3b` full GATT | 同固件/ELF/QEMU build 使用 15-byte probe / 17-byte ATT PDU，HLI/API-boundary H2C 完成 discovery、subscription、write、Python handler、notify 和 Bumble ACK，连续 `5/5`；旧失败由 24-byte ATT PDU 超过默认 MTU 23 解释 | [`hli-api-gatt-5x.json`](../tests/uiflow2/core2_native_hci/evidence-2026-10-24-hli-api-gatt-5x.json) |
| Core2 native-HCI `HCI-4` | 规范 profile `core2-native-hci` 通过五个独立 `/api/v1` lease/QEMU 进程；每轮 frame、27 节点 QOM、WiFi DHCP/HTTP、公网 DNS/HTTP、外部 NUS GATT、pcap 和 evidence ZIP 均 PASS，`gdb_bridge=false` | [`hci4-service-5x.json`](../tests/uiflow2/core2_native_hci/evidence-2026-10-24-hci4-service-5x.json) |
| Core2 extended-run regression（历史失败） | `HCI-4 5/5` 后，带 hold 的独立运行在 READY/联网/BLE 连接后出现 panic。另一轮在 attempt 4 出现 `PC=0`；单轮失败首轮为 `IllegalInstruction` at `0x40266960` (`semphr_give_wrapper`)，随后 `InstrFetchProhibited` reboot loop。runner 已保留 partial evidence 并输出 aggregate FAIL；由下一行 halt-gated 修复证据取代 | [`extended-run-fail.json`](../tests/uiflow2/core2_native_hci/evidence-2026-10-24-extended-run-fail.json) |
| Core2 extended-run halt-gated fix | `0005` 恢复 caller-saved Xtensa sregs，并把 HLI guest allocator/callback 注入限制在 halted/idle vCPU。中间 sregs-only build `4/5`；halt gate 后两批独立 `5×10s` hold 合计 `10/10`。每轮 frame、QOM、WiFi/公网、NUS GATT、pcap 和 evidence PASS，`hli-posts=hli-consumed=47`、events=38、ACLs=9、`hli-errors=0`、HLI/meta queue 深度为 0 | [`hci4-halted-gate-5x.json`](../tests/uiflow2/core2_native_hci/evidence-2026-10-24-hci4-halted-gate-5x.json) |
| Core2 60-second hold | 3 个独立 QEMU lease 在 WiFi/公网/GATT/pcap/evidence 后保持 60 秒；全部 `3/3` PASS。设备在 BLE peer 正常关闭后继续 running；每轮 48 posts/48 consumed、39 events、9 ACLs、`hli-errors=0`，仅允许与 `peer-closed=1` 同时出现的 write-error 尾态 | [`hci4-hold60-3x.json`](../tests/uiflow2/core2_native_hci/evidence-2026-10-24-hci4-hold60-3x.json) |
| Core2 120-second hold | 2 个独立 stock Core2 lease 在 frame、34 节点 QOM、WiFi、公网 DNS/HTTP、NUS GATT、pcap、evidence 后各保持 120 秒；全部 `2/2` PASS。每轮 48 posts/48 consumed、39 events、9 ACLs、`hli-errors=0`、HLI/meta queue 为空；GATT peer 关闭后 `tx-queue-depth=32` 与 `last-error=2` 作为显式尾态分类 | [`hci4-hold120-2x.json`](../tests/uiflow2/core2_native_hci/evidence-2026-10-24-hci4-hold120-2x.json) |
| Core2 active-BLE 120-second hold | `ble_linger_seconds=180` 让 GATT peer 贯穿整个 hold；2 个独立 lease `2/2` PASS，frame/QOM、WiFi、公网、GATT、pcap 和 evidence 全通过。每轮 47/47 HLI posts/consumed、38 events、9 ACLs、`hli-errors=0`、HLI/meta queue 和 TX queue 为空，`peer-closed=0`、`last-error=0` | [`hci4-active-ble-hold120-2x.json`](../tests/uiflow2/core2_native_hci/evidence-2026-10-24-hci4-active-ble-hold120-2x.json) |
| Core2 active-BLE 600-second hold | `ble_linger_seconds=660` 让 GATT peer 贯穿 600 秒 hold；2 个独立 lease `2/2` PASS，frame/QOM、WiFi、公网、GATT、pcap 和 evidence 全通过。每轮 45/45 HLI posts/consumed、36 events、9 ACLs、`hli-errors=0`、HLI/meta/TX queue 为空，`peer-closed=0`、`last-error=0` | [`hci4-active-ble-hold600-2x.json`](../tests/uiflow2/core2_native_hci/evidence-2026-10-24-hci4-active-ble-hold600-2x.json) |
| Core2 active-BLE 7200-second diagnostic hold | 1 个 active-BLE `7200s` hold 完成：session 全程 running，WiFi、公网 DNS/HTTP、外部 NUS GATT、frame、pcap 和 evidence 均通过；结束 HLI `45/45`、events 36、ACLs 9，errors/queue/dropped/peer-close 为 0。运行期间 QEMU 路径被临时 AXP trace build 替换，旧 runner 只在结束时计算 QEMU 哈希，因此结果为 `DIAGNOSTIC_PASS`，不关闭 artifact-bound 两小时门禁。runner 随后加入首 lease 前输入哈希冻结、运行期间资产漂移拒绝和 host RSS 采样 | [`hci4-active-ble-hold7200-diagnostic.json`](../tests/uiflow2/core2_native_hci/evidence-2026-10-24-hci4-active-ble-hold7200-diagnostic.json) |
| Core2 artifact-bound 7200-second functional hold | 1 个 active-BLE `7200s` lease 在首 lease 前绑定 firmware/ELF/QEMU，结束时 `input_assets_unchanged_during_run=true`、`input_asset_drift={}`；frame/QOM、WiFi、公网 DNS/HTTP、外部 NUS GATT、pcap、evidence 和清理 PASS。HLI `45/45`、events 36、ACLs 9，errors/HLI/meta/TX queue、dropped、peer-close 和 panic 均为 0。QEMU host RSS 从 `744160 KiB` 增至 `1202176 KiB`，增长 `458016 KiB`；功能门禁 PASS，RSS 趋势 `REVIEW`，不声明内存有界 | [`hci4-active-ble-hold7200-artifact-bound-1x.json`](../tests/uiflow2/core2_native_hci/evidence-2026-10-24-hci4-active-ble-hold7200-artifact-bound-1x.json) |
| Core2 bounded TCG memory | 未限制的 QEMU 默认可预留最多 `1 GiB` TCG translation buffer；旧 soak 的 RSS 增长主要落在 macOS `VM_ALLOCATE`。统一 accelerator 改为 `tcg,thread=single,tb-size=128` 后，同固件 120 秒 WiFi/公网/GATT/frame/pcap/HLI 全部 PASS；RSS `323600→323584 KiB`、phys footprint `214016→196608 KiB`，HLI `45/45`。后续 artifact-bound 两小时复测也 PASS，240 个资源采样为 RSS `323536→252992 KiB`、phys footprint `250880→188416 KiB` | [`hci4-tb128-hold120-1x.json`](../tests/uiflow2/core2_native_hci/evidence-2026-10-24-hci4-tb128-hold120-1x.json)、[`hci4-active-ble-hold7200-tb128-artifact-bound-1x.json`](../tests/uiflow2/core2_native_hci/evidence-2026-10-25-hci4-active-ble-hold7200-tb128-artifact-bound-1x.json)、[`qemu_accel.py`](../platform/tools/qemu_accel.py) |
| Core2 native-HCI resolved PSRAM | 同一运行中，CLI 为 `-m 0`，但 QOM snapshot 显示 `memory.size=4194304`、`has_psram=true` 和 `/machine/soc/dport/psram[0]`。因此 runtime evidence 区分 CLI request `0 MiB` 与 QOM-effective `4 MiB`；firmware manifest 的 runtime PSRAM preflight 也按 4 MiB 检查。物理 8 MiB PSRAM/cache timing 仍 `NOT RUN` | [`core2-native-hci-resolved-psram.json`](../tests/uiflow2/core2_native_hci/evidence-2026-10-24-core2-native-hci-resolved-psram.json) |
| Core2 same-guest reconnect boundary（历史失败） | `network.ble_reconnect_cycles=2` 时第一轮 scan/connect/NUS/write/notify/disconnect 成功，第二轮 advertisement 超时。重广告路径出现连续 `NimBLE: HCI process ack returned 12` 和 HCI reset；真正的 no-readvertise 对照无 reset。后续定位为 Bumble 对 `HCI_Host_Number_of_Completed_Packets (0x0c35)` 返回非法 Command Status，由下一命令消费成 stale ACK | [`reconnect2-fail.json`](../tests/uiflow2/core2_native_hci/evidence-2026-10-24-reconnect2-fail.json) |
| Core2 same-guest reconnect fix | 修正 Bumble compatibility 层，使 `0x0c35` 不再产生任何 HCI response。stock Core2 固件在 3 个独立 `/api/v1` lease 中均完成两轮 scan/connect/NUS GATT/disconnect；每轮 frame/QOM、WiFi、公网、pcap、evidence 与 HLI health PASS，第二轮有 guest RX 和 notification；`trace-hs-sched-reset=0`、`trace-gap-adv-start=2`、HLI 73/73 清空 | [`hci4-reconnect2-3x.json`](../tests/uiflow2/core2_native_hci/evidence-2026-10-24-hci4-reconnect2-3x.json) |
| Core2 five-cycle same-guest reconnect | 同一固件/QEMU build 在 3 个独立 lease 中各自完成 5 轮 scan/connect/NUS GATT/disconnect。每轮 frame/QOM、WiFi、公网、pcap、evidence 和 HLI health PASS；HLI `157/157`、events 112、ACLs 45，HLI errors 和队列深度为 0，connection/L2CAP/GATT 池回到 `3/9/3` 空闲基线，`trace-hs-sched-reset=0`、`trace-gap-adv-start=5` | [`hci4-reconnect5-3x.json`](../tests/uiflow2/core2_native_hci/evidence-2026-10-24-hci4-reconnect5-3x.json) |
| Core2 ten-cycle reconnect service timeout（历史失败） | 首次 `ble_reconnect_cycles=10` 运行完成 5 轮并开始第 6 轮，guest 无 panic；Device Service 的 `_wait_hci_probe_result()` 将 ready timeout 硬截断为 30 秒，误判 peer 未完成并终止 QEMU。该证据由下一行修复版本取代 | [`hci4-reconnect10-timeout-fail.json`](../tests/uiflow2/core2_native_hci/evidence-2026-10-24-hci4-reconnect10-timeout-fail.json) |
| Core2 ten-cycle same-guest reconnect | 等待改为使用 session ready timeout 后，同一固件/QEMU build 在 3 个独立 lease 中各自完成 10 轮 scan/connect/NUS GATT/disconnect。每轮 peer/guest 均有 PASS/RX/notification marker；HLI `297/297`、events 207、ACLs 90，HLI errors 和队列深度为 0，connection/L2CAP/GATT 池回到 `3/9/3`，`trace-hs-sched-reset=0`、`trace-gap-adv-start=10`，native-HCI health 超 30 秒回归测试 PASS | [`hci4-reconnect10-3x.json`](../tests/uiflow2/core2_native_hci/evidence-2026-10-24-hci4-reconnect10-3x.json) |
| Core2 twenty-cycle same-guest reconnect | Device Service、Bumble peer 和 service runner 的 reconnect API 上限统一扩到 `30`。同一 ELF/QEMU SHA 下，3 个独立 lease 各自完成 20 轮 scan/connect/NUS GATT/disconnect；每轮 peer/guest 均有 PASS/RX/notification，HLI `577/577`、events 397、ACLs 180，HLI errors、队列深度和 panic 均为 0，connection/L2CAP/GATT 池回到 `3/9/3`，`trace-hs-sched-reset=0`、`trace-gap-adv-start=20` | [`hci4-reconnect20-3x.json`](../tests/uiflow2/core2_native_hci/evidence-2026-10-24-hci4-reconnect20-3x.json) |
| Core2 thirty-cycle same-guest reconnect | 同一 ELF/QEMU SHA 与 unified 镜像下，3 个独立 lease 各自完成 30 轮 scan/connect/NUS GATT/disconnect，全部 `3/3 PASS`；每 lease HLI `857/857`、events `587`、ACLs `270`，HLI errors、HLI/meta/TX queue 和 panic 均为 0，connection/L2CAP/GATT 池回到 `3/9/3`，三次 frame SHA256 一致；`gdb_bridge=false`，仅 virtual-device validation | [`hci4-reconnect30-3x.json`](../tests/uiflow2/core2_native_hci/evidence-2026-10-24-hci4-reconnect30-3x.json) |
| Core2 sixty-cycle same-guest reconnect | 同一 ELF/QEMU SHA 与 unified 镜像下，3 个独立 lease 各自完成 60 轮 scan/connect/NUS GATT/disconnect，全部 `3/3 PASS`；每 lease HLI `1697/1697`、events `1157`、ACLs `540`，HLI errors、HLI/meta/TX queue 和 panic 均为 0，connection/L2CAP/GATT 池回到 `3/9/3`，三次 frame SHA256 一致；`gdb_bridge=false`，仅 virtual-device validation | [`hci4-reconnect60-3x.json`](../tests/uiflow2/core2_native_hci/evidence-2026-10-24-hci4-reconnect60-3x.json) |
| Core2 120-cycle same-guest reconnect | 同一 ELF/QEMU SHA 与 unified 镜像下，3 个独立 lease 各自完成 120 轮 scan/connect/NUS GATT/disconnect，全部 `3/3 PASS`；每 lease HLI `3377/3377`、events `2297`、ACLs `1080`，HLI errors、HLI/meta/TX queue、dropped 和 panic 均为 0，connection/L2CAP/GATT 池回到 `3/9/3`，三次 frame SHA256 一致；`gdb_bridge=false`，仅 virtual-device validation | [`hci4-reconnect120-3x.json`](../tests/uiflow2/core2_native_hci/evidence-2026-10-24-hci4-reconnect120-3x.json) |
| Core2 WiFi deterministic repeat | runner 之前文档声称使用 `tcg,thread=single` + `icount`，但代码漏传，导致 idle `WAITI` Cache error。修正后 WiFi-only scan/association/DHCP/HTTP 独立运行 `5/5` PASS | [`deterministic-5x.json`](../tests/network/core2_openmac_wifi/evidence-2026-10-24-deterministic-5x.json) |
| Core2 HLI queue | 实验写入 firmware `g_rw_schd_queue`/meta queue 并置 `INTSET[29]`；guest ISR/controller task 消费 event-13 marker，QOM 无错误、队列清空。该结果只证明交付 seam，不是 HCI/GATT PASS，实验未保留 | [`hci3b-hli-queue-diagnostic.json`](../tests/uiflow2/core2_native_hci/evidence-2026-10-24-hci3b-hli-queue-diagnostic.json) |
| Core2 HLI event | 保留的 QEMU patch 通过 guest `ble_transport_alloc_evt(0)` 分配真实 Reset Complete，经 event 13 和 `ble_transport_to_hs_evt_impl` 交付；`01030c00` 后 guest 发出 `01011000`，连续 `5/5`，HLI/meta queue 清空且无 malformed/dropped packet | [`hli-event-5x.json`](../tests/uiflow2/core2_native_hci/evidence-2026-10-24-hli-event-5x.json) |
| Core2 callback 路线审计 | safe-point callback 仍崩溃；nested `r_eif_send → vhci_send` 触发 cache-disabled 异常。两个实验均回退，patch reverse-check PASS | [`safe-point-audit.json`](../tests/uiflow2/core2_native_hci/evidence-2026-10-24-hci3b-safe-point-audit.json)、[`controller-entry-audit.json`](../tests/uiflow2/core2_native_hci/evidence-2026-10-24-hci3b-controller-entry-audit.json) |

## 2026-10-23

| 工作流 | 结果 | 证据 |
| --- | --- | --- |
| 单机网络隔离 | StickS3 QEMU guest 在 Linux private network namespace 内运行，外部路由缺失时按预期阻断 | [`linux.json`](../tests/network/linux_isolation/evidence-2026-10-23-linux.json) |
| TLS blocker | 当轮 TLS 阻塞点定位到 ESP32-S3 AES/GDMA 外部内存读取，作为后续 patch `0027` 的负向证据保留 | [`blocked.json`](../tests/network/tls_allowlist/evidence-2026-10-23-blocked.json) |
| TLS/Host allowlist | 测试 CA、允许 Host 200、拒绝 Host 403、请求决策和 pcap PASS | [`pass.json`](../tests/network/tls_allowlist/evidence-2026-10-23-pass.json) |
| 零重试矩阵 | 无自动重试的外设矩阵基线 | [`zero-retry-matrix.json`](../tests/uiflow2/evidence-2026-10-23-zero-retry-matrix.json) |
| 固件静态审查 | 公开固件 round-trip、URL/凭据脱敏、高熵块指纹和 SBOM | [`static-review.json`](../tests/firmware/evidence-2026-10-23-static-review.json) |

## 阅读规则

1. 先读 [项目当前状态](project-status.md)，确认该结论是否仍是当前能力。
2. 再读本页确认证据日期和当时边界。
3. 最后打开 evidence JSON，核对固件 SHA、runtime/profile、设备、检查项和
   `PASS`/`PARTIAL`/`FAIL` 字段。
4. 新证据按日期和主题追加，不改写旧失败；若结论被推翻，在当前状态页更新，
   在历史页说明取代关系。

## 2026-10-28：UIFlow2 双主机接口审计与修复

最终运行时 `cc21773f0ad91fa589447d3badb1eb681b74170cd8b749153f37ad23cebc70c2`，
28补丁/112文件exact-upstream正向/反向/往返回放通过；完整外设矩阵
68/68 PASS、自动重试0。Core2 IMU改用真实绘制完成marker后本轮通过，
保留前轮67/68失败收据。摄像头raw/重初始化/JPEG/BMP、Cardputer Canvas
以及两板SD/FAT、Mic PCM/WAV均有最终runtime可见session数据面收据。
SDK0001–0020独立候选与stock/matching结果分lane；0017 observer修正版
三lane对照27/27证据检查，0018 allocator含28 C cases/version与30 native契约。
逐项接口分母、失败/阻塞、固件/runtime/serial/frame/ZIP哈希及复现入口见
[本轮证据](evidence/2026-10-27-uiflow2-api-sweep/README.md)。原私有应用、旧
UIFlow1 LVGL7、未选外设和物理硬件不继承通过；API-01继续保留剩余项。

## 2026-10-28：StopWatch / StickS3 / Core2 UIFlow2 三设备复测

三台当前 M5Burner UIFlow2 v2.5.3 镜像经独立可见 Device Service 和 28 补丁
QEMU runtime 执行；全部为 virtual-device validation，physical hardware 为
`NOT RUN`。system runtime 每台 `50 PASS + 1 STATE_PASS`；sockets `23/23`、
MQTT `42/42`、network `14/14`、EasySocket `57 PASS + 1 N/A`、EzData
`17/17`。HTTP stock 三台均为 `15 PASS / 1 FAIL`，候选 form/UTF-8 三台
`2/2`；Modbus stock `42 PASS / 8 ERROR`，候选源码三台 `50/50`。

确认并固定为候选补丁的 shared defects：BLE 32-bit UUID 的
`struct.unpack("<d")`、Modbus TCP→RTU 的非法默认构造、Modbus async
`Loop.sock_recv`，以及 M5UI Canvas/Image/Spinbox Python 绑定问题。
StopWatch/Core2 的同 VM stock→candidate 对照、ESP-NOW 控制面和 WAV/mic
基线见[三设备证据](evidence/2026-10-28-multi-board-uiflow2-revalidation/README.md)。
Core2 按键在该轮只保留形状检查，最终 A/B/C/PWR 结论由后续
[Core2 触控/电源键证据](evidence/2026-10-28-core2-touch-buttons/README.md)
取代。

## 2026-10-28：QRCode.setText 与 TLS epoch 三设备候选固件

StopWatch、StickS3、Core2 分别使用匹配 cached build 增量重链接
`0014-widgets-qrcode-text` 和 `0010-mbedtls-epoch`，只替换 application
partition；所有 receipt 均确认 application 外字节不变、原始源码和 cached
library 不变。QR stock/preimage 三台均解码旧文本 `ORACLE_MISMATCH`，候选
三台均 `FRAME_PASS` 解码新文本。TLS preimage 三台均为
`2 ERROR + 3 STATE_PASS`，错误为 owned 2020–2035 证书被判过期；候选三台均
`5/5 PASS`，每台完成两次 TLSv1.2 双向认证 HTTP GET，服务端验证精确客户端
证书。StickS3 TLS 使用含 native UART REPL 的 `unified` build，并新增显式
native bootstrap，避免对 UART0 重复 `os.dupterm`。全部为 virtual-device
validation；incremental relink、公网 PKI、证书持久化和真机为 `NOT RUN`。
哈希、peer、证书和边界见
[候选固件证据](evidence/2026-10-28-qrcode-tls-candidate-firmware/README.md)。

## 2026-10-28：Display.drawPixel framebuffer transaction

此前 StopWatch `drawPixel` 失败被归因于 CO5300 单像素/偶数窗口限制；本轮
framebuffer path 对照退役该判断。StopWatch 使用 `Panel_AMOLED_Framebuffer`，
其 auto-display 只在 `endWrite()` 时提交 dirty range，而 Python
`gfx_drawPixel()` 原先直接调用 `drawPixel()`，没有打开事务。`0024` 增加嵌套
安全的 `startWrite()/endWrite()`。同一 StopWatch preimage 中，显式事务红/绿
像素出现而 standalone 青/白像素缺失；候选即使把显式事务放在 standalone
调用之前，仍保留四个目标像素并保持奇偶相邻背景。StopWatch、StickS3、Core2
三台候选均 `FRAME_PASS`。所有候选只改变 application partition；真机与长期
framebuffer DMA soak 为 `NOT RUN`。见
[drawPixel 证据](evidence/2026-10-28-stopwatch-drawpixel-transaction/README.md)。

## 2026-10-28：StopWatch / StickS3 / Core2 音频数据面

三台当前 v2.5.3 镜像在独立可见 Device Service 中完成 Mic 与 Speaker
数据面验证。同一 440 Hz、16 kHz、mono s16le、32,000-byte 输入夹具下，
三台 `Mic.record` 均产生非静音 PCM 且录音状态从 1 返回 0；
`Mic.recordWavFile` 均生成合法 32,044-byte mono s16 16 kHz WAV。最终
`03d74d53…` runtime 上，抗裁剪自相关 oracle 测得 StopWatch 440.088 Hz、
StickS3 440.088 Hz、Core2 443.792 Hz（0.86% 误差，门限 5%）。

Speaker raw/WAV/file 路径按板级原生输出格式解码：StopWatch 44.1 kHz
stereo、StickS3 22.05 kHz stereo、Core2 48 kHz mono。修复前
StopWatch/StickS3 的 `playWavFile` 在完整一秒 WAV 上阻塞，而 1/2/4 个
512-byte 分块可完成；trace 显示固件已排队到 chunk 15，但 QEMU 在
`TX_START + 2s` 或 128 个描述符后停止 DMA completion。`0062` 将持续
DMA completion 与 PCM evidence capture 窗口分开。新 runtime
`feb143e4c4f8140a8946356db39968a606861fb4b40b86f7bb50ea85603f5da2`
下，三台 raw/WAV 以及 StopWatch/StickS3 的完整 `playWavFile` 与
`playWav → playWavFile` 均到达 guest done marker，独立频谱主频为
659–662 Hz。最终六个 Mic/Speaker 会话并发复测也全部通过。全部为
virtual-device validation；物理声学、声压和真机为
`NOT RUN`。见[三设备音频证据](evidence/2026-10-28-three-board-audio/README.md)。

最终
`03d74d53ff8187c4f0a3b22d34c4e898bdd93b61cfc98432dbbeecd1beb12419`
runtime 重绑三台 Mic、WAV/file 与 raw 路径。三台 Mic 和 Speaker 六会话
首次使用固定 60 秒 guest READY 预算时 StopWatch Mic 在 QEMU 启动前超时；
runner 增加显式 `--ready-timeout` 后，以 180 秒预算重新并发六个会话，
Mic/Speaker `6/6` 一次完成，三台 raw 另行并发全部通过。第一次 Core2
并发 WAV 被旧矩形 DFT 误报为 395 Hz；同一 32,000-byte 裁剪 PCM 的自相关
主频为 443.828 Hz，单会话重复为 443.758 Hz。测试 oracle 已改为有界归一化
自相关和抛物线插值，并增加裁剪波形回归，避免把相位相关的泄漏峰当固件音频
故障。

## 2026-10-28：Core2 UIFlow2 A/B/C/PWR 回调

最终 runtime
`03d74d53ff8187c4f0a3b22d34c4e898bdd93b61cfc98432dbbeecd1beb12419`
在四个独立可见 session 中分别注入 `key:a/b/c/p`。A/B/C 经 FT5x06
触控条得到 `(53,260)`、`(160,260)`、`(266,260)`；PWR 经 AXP2101
`IRQ_STATUS1(0x49)`。四例 `WAS_HOLD` 回调均收到 `[2]`，remove 后没有
新事件，pressed/holding/released 状态及 cleanup 均通过。首版 `0063`
在 `touch_buttons` 分支无条件提前 `break`，同时吞掉 `key:p`；现只让
A/B/C 走触控条，P 继续到电源键事件路径。该结果是 virtual-device
validation，物理触控压力和 PMIC 电气为 `NOT RUN`，见
[Core2 触控/电源键证据](evidence/2026-10-28-core2-touch-buttons/README.md)。

## 2026-10-28：Core2 pending SPI IRQ remap

Core2 ESP-IDF 5.5.4 probe 以 `spi_master` queue 一个 16-byte SPI3
transaction，并要求 guest `post_cb` 和
`spi_device_get_trans_result()` 都完成。pre-fix QEMU
`03ae86b5…` 观察到 `QUEUE_OK` 后 callback timeout；trace 显示 guest
先将 source 31 映射到 CPU interrupt 5，清回 unconnected 6，抬高
`SPI_SLAVE.TRANS_DONE && TRANS_INTEN`，最后才写回 map 5。旧
interrupt-matrix 只在输入 level 变化时转发，没有在 mapping 写入时重算
pending level，因此 guest ISR 永不运行。

`0064-esp32-intmatrix-pending-irq-remap.patch` 保存 69 个输入 level，
在输入或 mapping 变化时按 CPU external interrupt 汇总所有映射 source，
并把 SPI IRQ 改为 `TRANS_DONE && TRANS_INTEN`。同一 firmware
`1f4d1b40…` / ELF `00d946fe…` 在 fixed QEMU `22bf9dba…` 上
`3/3 PASS`，每轮各一次 callback 和 queued result；平台合同直接编译
patch 的真实 C 函数并覆盖 pending remap 与同 output 多 source OR。同一
fixed runtime 的 Core2 UIFlow2 设备组 `6/6 PASS`（touch/RTC/PWR、音频、
Mic、INA3221、MPU6886 和 AXP192），均 attempt 1、无 retry。

该结果关闭通用 SPI/INTMATRIX completion 子缺口，但不关闭
`RUNTIME-03`。最新 legacy `UIFlow_Core2 v1.15.4` 的 60 秒 PC trace
没有命中 display flush/callback 地址，并在约 `15.53 s` 发生 reset；
仍无非空应用帧或 REPL。见
[`evidence`](../tests/firmware/core2_spi_irq_remap/evidence-2026-10-28-core2-spi-irq-remap.json)、
[`pre-fix control`](../tests/firmware/core2_spi_irq_remap/evidence-2026-10-28-core2-spi-irq-remap-control.json)、
[`probe`](../tests/firmware/core2_spi_irq_remap/README.md)、
[`本块说明`](evidence/2026-10-28-core2-intmatrix-pending-irq/README.md)。

## 2026-10-28：Core2 high-priority IRQ、classic RMT 与三设备最终回归

最终 QEMU
`2026673273b5bced2c2696ac4850a48f5ea47d8e9c80d6ceb2cf15f68c36d29f`
加入 `0065-xtensa-high-priority-irq-cooperative-yield.patch` 和
`0066-esp32-classic-rmt-legacy.patch`。`0065` 记录 level-4/5 handler，
只在 `memw` 发布 DPORT start 后和 sender `retw` end 路径协作让出，不改
guest 指令、virtual time 或 IRQ level；同一 legacy public firmware 的五轮
首启动均在 `5.000000002-5.000000031 s` 结束，`5/5 PASS`，旧固定 CPU0/CPU1
双等待不再复现。

`0066` 替换此前未实现的 classic ESP32 RMT region，模型 8 channel、寄存器、
2 KiB RMTMEM、`conf0.mem_size`、memory TX、threshold、`TX_END`、INTMATRIX
source 47 和有界 capture。修复前 `mem_size=0` 导致
`RMT translator buffer create fail` / Neopixel `OSError`；修复后 debug trace
捕获四次 channel 7 TX、每次 49 symbols，同一 legacy Serial 到达
`BOARD NAME`/`APIKEY`。该模型不证明 GPIO waveform、光学或电气时序。

模型修复没有关闭 `RUNTIME-03`。final runtime 的 normal-WDT control 在
`7.249439902 s` 进入 TG0 stage-0 timeout、`17.249439902 s` 进入 stage-1、
`17.249530334 s` 首次重启，串口报告 `TG0WDT_SYS_RESET` 和两核 `PC=0x0`。
WDT-off 68 秒 exact-time 控制到达 `APIKEY`，但 320x240 帧仍为 302-byte、
`0` 个非黑像素，SHA256
`57580743a08a3f4ebdf57240cbcc997002ef63b7234531f946127f1495973f43`；
display completion、setup/REPL 与非空应用帧继续 `OPEN`。

同一 final runtime 并发回归 StopWatch、StickS3、Core2 当前 UIFlow2 v2.5.3：
system runtime 每台 `50 PASS + 1 STATE_PASS`、零 ERROR/FAIL；BLE UUID 与
Modbus RTU shared candidates 每台 `7/7`；设备组 StopWatch `6/6`、
StickS3 `5/5`、Core2 `6/6`，17 个 group case 全部 attempt 1 且无 retry。
全部仅 virtual-device validation，物理硬件/RF/声学/光学/电气为 `NOT RUN`。
见[本轮证据](evidence/2026-10-28-cooperative-highint-rmt/README.md)和
[机器摘要](evidence/2026-10-28-cooperative-highint-rmt/summary.json)。

## 2026-10-28：ESP-NOW controlled loopback 与三设备接口最终重绑

新增
`0067-esp32-espnow-controlled-peer-loopback.patch`，SHA256
`d269334ac039e78a75cc3054c4f6e853865cb16f7489a242c40ddf095a57163b`。
补丁默认关闭，只在 `M5SW_ESPNOW_LOOPBACK=1` 时把 guest 经正常 TX DMA
写出的 802.11 management action frame 交换 peer/source 后从正常 RX DMA
送回；broadcast 使用固定 locally-administered fixture peer
`02:00:00:00:00:42`。最终 QEMU SHA256 为
`c3c3140322513de6f3ef724513e2f1272764e6af8a8fdd7c7bfd4448dc17f534`。

三台 StopWatch/StickS3/Core2 上，原厂 `m5espnow` 的
`send_data`、`broadcast_data`、`recv_data`、`set_irq_callback` 均 PASS，
结果为 `12 PASS + 5 STATE_PASS + 1 CONFIGURED_UNVERIFIED`；native
`espnow.ESPNow`、`ESPNowBase`、`m5espnow.M5ESPNow` 的
`send`/`recvinto`/`irq` 均 PASS，每台
`21 PASS + 21 STATE_PASS + 3 CONFIGURED_UNVERIFIED`。该结果证明同 guest
controller TX/RX DMA 和 IRQ，不证明外部 peer、PMK 加密 payload、跨设备
fabric、loss/retry、RF 或 timing；保留为 `RUNTIME-06 PARTIAL`。

同一 final runtime 重新绑定三设备 system runtime
`50 PASS + 1 STATE_PASS`、shared corrections `7/7`，以及 17 个设备组
case（StopWatch `6/6`、StickS3 `5/5`、Core2 `6/6`），全部 attempt 1、
无 retry。Sockets `23/23`、MQTT `42/42`、network `14/14`、EzData
`17/17`、requests2 candidate `2/2`、Modbus async candidate `50/50` 均在三台
PASS。audio wrapper 的 `play_tone(sync=True)` 旧 probe 在返回瞬间读取状态，
最小复现显示状态在约 1.5–2 秒后正常从 `RUNNING` 进入 `FINISHED`；probe
已改为 3 秒有界等待，StopWatch/StickS3 `audio-player 15/15`、
`audio-recorder 12/12`，Core2 `audio` 模块为 `NOT_EXPORTED`。

TLS candidate firmware 在同一 runtime 上三台各 `5/5`；StopWatch/Core2
使用 `dupterm`，StickS3 unified native-REPL image 使用 `native` bootstrap。
stock 边界仍保留：HTTP `15 PASS / 1 FAIL`、Modbus `42 PASS / 8 ERROR`、
TLS `2 ERROR + 3 STATE_PASS`。全部为 virtual-device validation；
物理硬件、RF、声学、光学和电气为 `NOT RUN`。见
[最终接口复测](evidence/2026-10-28-espnow-and-three-board-interface-retest/README.md)、
[机器摘要](evidence/2026-10-28-espnow-and-three-board-interface-retest/summary.json)、
[`0067`](../patches/qemu-m5stack-peripherals/0067-esp32-espnow-controlled-peer-loopback.patch)和
[`contract`](../platform/tests/test_esp32_espnow_loopback_patch.py)。

## 2026-10-28：Core2 legacy VFS 与 WiFi fixture 校正

复核发现旧 legacy WDT-off/黑帧诊断同时混入了两个测试 fixture 问题：通用
LittleFS 镜像被 guest 拒绝后 `/flash` 被重新格式化；直接 QEMU 控制又未传
`-nic user,model=misc.esp32_wifi,id=wifi0`，因此没有实例化 legacy 启动路径
访问的 WiFi 设备。前者使注入的 `/flash/boot.py` 从未执行，后者可能让 guest
在 `0x60033d24` 的 `WIFI_DMA_OUT_STATUS` APB alias 上等待无设备状态。

使用 UIFlow checkout 自带 LittleFS2 packer 重建 `0x6de000` VFS，再经
`/api/v1` 的 `runtime=qemu-wifi`、`profile=core2-openmac` 执行
120 秒精确时点检查后，Serial 首次出现 `CORE2_LEGACY_VFS_BOOT`，证明注入的
VFS 被识别并执行；Serial 为 575 bytes、SHA256
`f837bbcc8402c299cce8abc1ce0820c3f20b801f4e3b4e3ceceeb6823f7c08b7`。
此时 CPU0 `0x40249c5d`、CPU1 `0x400e1ffd`，旧 `0x40100049` LVGL 等待未复现；
但 setup/main marker 和非空帧仍未出现，320x240 帧为 302-byte 纯黑，normal
WDT 仍出现 `TG0/TG1WDT_SYS_RESET`。因此 `RUNTIME-03` 保持 `OPEN`，此前的
无 NIC 黑帧不能单独作为 legacy 应用到显示路径的证据。见
[夹具校正证据](evidence/2026-10-28-core2-legacy-vfs-wifi-fixture/README.md)、
[机器摘要](evidence/2026-10-28-core2-legacy-vfs-wifi-fixture/summary.json)和
[VFS probe](../tests/firmware/core2_legacy_vfs_probe/README.md)。

## 2026-10-28：Core2 legacy HSPI/VSPI panel routing

公开 UIFlow `v1.15.4` 的 `display.TFT` 路径选择 classic ESP32 HSPI/SPI2，
而 `m5core2` 板级模型此前只把 ILI9342 panel sink 接到 VSPI/SPI3。正确
LittleFS2 VFS + `runtime=qemu-wifi` 的负控中，legacy LCD DMA 在非面板
控制器记录 `412` 次 `addr=104` 写，面板控制器 `0` 次，最终帧 `0` 非黑像素。

`0068-core2-dual-spi-panel-routing.patch` 将同一个面板对象同时接到 SPI2 和
SPI3，均使用 DC GPIO15。同一 Device Service `/api/v1` WiFi-backed 会话执行
原厂 `boot.py` 的 SD 初始化后调用 legacy `m5stack`/`lcd` 绘制，Serial 为
`652` bytes、SHA256 `8c0dc777…`，120 秒帧为 `320x240`、`1422` nonblack
pixels / `2` colors，SHA256 `55249d07…`。这关闭面板控制器路由子问题；
原厂 startup UI 仍没有完成帧，normal-WDT 仍 TG0 reset，因此 `RUNTIME-03`
保持 `OPEN`。见
[dual-SPI 证据](evidence/2026-10-28-core2-dual-spi-panel-routing/README.md)、
[机器摘要](evidence/2026-10-28-core2-dual-spi-panel-routing/summary.json)、
[`0068`](../patches/qemu-m5stack-peripherals/0068-core2-dual-spi-panel-routing.patch)
和 [`contract`](../platform/tests/test_core2_dual_spi_panel_patch.py)。

## 2026-10-28：三设备 UIFlow2 并发复测与 runner 竞态修复

StopWatch、StickS3、Core2 官方 UIFlow2 `v2.5.3` 在同一最新 QEMU
`6ff2aca0…` 上以三设备并发、设备内串行复测。三台 system runtime 均为
`50 PASS + 1 STATE_PASS`，shared corrections 均 `7/7`；sockets `23/23`、
MQTT `42/42`、network `14/14`、EzData `17/17`。StopWatch/StickS3 audio
player `15/15`、recorder `12/12`，Core2 `audio` 模块 `NOT_EXPORTED`。

并发暴露了两个测试基础设施问题并已修复：多个 `qemu-wifi` 会话竞争固定
HTTP fixture 端口；串口 READY 可能早于 session 发布 `running`，使首个
marker action 得到 `409`。新增 `network.http_fixture=false`，并让
`run_hardware_guest` 在 marker action 前等待 `running`，Core2 bounded
drive 的等待上限由 10 秒放宽到 30 秒。修复后 StickS3 sockets/network 两
会话并发仍 `23/23`、`14/14`；BtnA/WAS_HOLD attach/input/remove PASS。

Core2 `core2-peripherals`、`core2-imu`、`core2-axp192` 顺序复测均为
PASS，frame 分别 `6612`、`3766`、`3917` nonblack pixels，peripherals
成功标记为绿色。此前并发批处理中的黑帧/缺 marker 保留为失败 control，
不作为 UIFlow2 API 回归。

Stock 边界继续复现：HTTP `requests2.urlencode` 失败；Modbus TCP 八个
async 方法缺少 `Loop.sock_recv`；StopWatch/Core2 M5UI 的 triangle、
image scale 和 integer spinbox step 失败；StopWatch standalone
`Display.drawPixel` 依赖既有 `0024` 候选修复。Device Service API sweep
`81` operations、`95` cases、`13` positive + `70` boundary PASS；
platform `1364` 项 `OK`、`1` skip。全部为 virtual-device validation，
物理硬件、RF、声学、光学和电气为 `NOT RUN`。见
[并发与竞态证据](evidence/2026-10-28-concurrent-fixture-and-ready-state/README.md)
和[机器摘要](evidence/2026-10-28-concurrent-fixture-and-ready-state/summary.json)。

## 2026-10-28：ESP32 TIMG WDTFEED 写保护语义

ESP-IDF v4.4.8 的 `wdt_hal_feed()` 直接调用 `mwdt_ll_feed()`，不会先解锁
`WDTPROTECT`。旧 QEMU 把 `A_TIMG_WDTFEED` 整体放在保护条件内，导致已锁定
watchdog 丢弃合法 feed。`0069` 只把 feed 路径移出保护条件，配置寄存器继续
要求 `TIMG_WDT_WKEY_VALUE`；C 合同和 patch reverse-check 通过。

同一 public legacy Core2 镜像 `4d2d648b…` 在 `runtime=qemu-wifi`、TCG
`shift=5`、TIMG trace 开启的 60 秒窗口仍显示：TG0 stage-0 timeout
`7.252822559 s`（masked），stage-1 timeout `17.252822560 s`，首个 reset
`17.252907520 s`；TG1 在 reset 前完成 `14,993` feeds、最大间隔
`5.181212 ms`。Serial 只有 MicroPython banner、无 REPL，frame 仅
`49` nonblack pixels，因此 `0069` 是模型语义修复，不是 `RUNTIME-03`
startup UI/应用帧的关闭证据。QEMU SHA256
`78555183…`；全部为 virtual-device validation，物理硬件和 watchdog 电气
行为 `NOT RUN`。见[证据](evidence/2026-10-28-core2-timg-wdt-feed/README.md)
和[机器摘要](evidence/2026-10-28-core2-timg-wdt-feed/summary.json)。

## 2026-10-28：最新 runtime 三设备 UIFlow2 接口复测

在包含 `0069` 的 QEMU
`78555183d53318fc25bc8413300e928d35bbbc1305f9d9648e97a73d34ce63b1`
上，StopWatch、StickS3、Core2 的设备间并发复测结果为：system runtime
各 `50 PASS + 1 STATE_PASS`；shared corrections 各 `7/7`；设备组分别为
`6/6`、`5/5`、`6/6`，17 个 case 首轮通过且无 retry。三台
socket `23/23`、EasySocket `57 + 1 N/A`、MQTT `42/42`、
network `14/14`、EzData `17/17`；StopWatch/StickS3 audio player
`15/15`、recorder `12/12`；三台 ESP-NOW 与 native ESP-NOW loopback
通过。Device Service API `81` operations、`95` cases 全部 PASS。

冻结 stock 固件仍分别复现 `requests2.urlencode`、Modbus async
`Loop.sock_recv` 和 mbedTLS epoch 缺陷；同一 runtime 上 hash-pinned
requests/Modbus 候选分别 `2/2`、`50/50`，TLS candidate 三台各 `5/5`。
所有可见 session 均保存 evidence 并 `purge=0` 停止。`RUNTIME-03` legacy
startup、外部/加密 ESP-NOW、显式 HCI BLE、未准入 RTU/PPP、完整 M5UI
矩阵和全部物理硬件仍为未关闭项。全部为 virtual-device validation；
物理硬件、RF、声学、光学和电气为 `NOT RUN`。见
[证据](evidence/2026-10-28-three-board-uiflow2-latest-runtime/README.md)
和[机器摘要](evidence/2026-10-28-three-board-uiflow2-latest-runtime/summary.json)。

## 2026-10-29 舵机与电源预览

固定源 `35ce38c8`、WASM `3880086c…` 与 StackChan 默认固件 `25d0ae3d…`：同 manifest 浏览器窄烟测 9/9，通过真实 present-position → 模型、同实例 reset、新 ready、6 秒 PWR 自然 exit0 与全部 Worker 清理。独立默认显示/触摸用例也通过。Fork Pages [任务 40862804528](https://github.com/yuyun2000/m5stack-esp-emulator/actions/runs/40862804528)成功，公网 manifest `5c0b933d…` 精确核验；原生 Arduino 八阶段与逐板控制器证据及明确缺口见[本轮摘要](evidence/2026-10-29-motion-power-preview/README.md)。未运行本轮完整 69-case 回归，不作为全设备新版通过。

## 2026-10-29：Core2 legacy UART 与虚拟时钟对齐

新增 `0070-esp32-uart-tx-virtual-clock.patch`，在默认关闭的
`M5SW_UART_TRACE` 输出中加入 virtual time，并让
`run_pause_sweep.py` 将逐字节输出重组为带起止时间的串口行。QEMU
`f0eb5f6c…` 上 WDT-off 80 秒诊断中，MicroPython banner 于 `2.7724 s`
完成，BOARD NAME/APIKEY 于 `54.995/55.002 s`，用户 boot.py start/done
于 `77.109/77.615 s`；80 秒状态点两核分别位于 `0x4008798e/0x40095b31`，
SSI 已执行 `104,061` transactions，cross-core writes `432,918`。

同固件 normal WDT 仍在 `17.2529 s` 触发 TG0 stage-1 reset，早于 BOARD
NAME；显式 `shift=2` 在更长墙钟窗口中仍于 `15.5609 s` reset，serial
仍未到 BOARD NAME，TG1 `0` timeout。这说明 lowering accelerator does not
change the watchdog gate and cannot be used as a product fix. `RUNTIME-03`
保持 `OPEN`；下一项是找出造成 pre-boot work budget 膨胀的 guest/controller
模型缺陷或取得 matching legacy source。全部为 virtual-device validation，
物理硬件和电气行为为 `NOT RUN`。见
[证据](evidence/2026-10-29-core2-legacy-uart-clock/README.md) 和
[机器摘要](evidence/2026-10-29-core2-legacy-uart-clock/summary.json)。

## 2026-10-29：Cardputer-ADV 当前参考固件 BMI270 闭环

官方 UIFlow2 `v2.5.3` Cardputer-ADV 参考固件在 QEMU
`f0eb5f6c…` 上通过板载 BMI270 数据面。器件位于 I2C `0x69`；QEMU
记录 CHIP_ID `0x24`、软复位、INIT_DATA/INIT_CTRL、data-ready 和
`0x0C..0x17` 连续数据读取。通过 Device Service `/api/v1` 注入
`0.25/-0.50/0.75 g` 与 `10/-20/30 dps` 后，原样用例的官方
`Imu.getAccel()` / `Imu.getGyro()` 返回
`(0.25,-0.5,0.75)` 与
`(10.009766,-20.019532,30.029296)`，串口成功标记和
`240x135` 绿色 `PASS` frame 均出现；evidence ZIP 在
`purge=0` 停止前取得，PID/历史清理通过。

仓库定向矩阵 `cardputer-adv-imu` 同底固件首轮 PASS，
`attempts=1`、`retry_used=false`、四项 checks 全通过。当前结论
关闭 Backlog 中“Cardputer-ADV 当前参考样本 IMU 全零”，历史
`66/67` 失败仍只对旧 runtime/commit 有效。本结果不证明物理 IMU
精度、噪声、温漂、轴向装配、电气特性或其它固件 SHA。见
[证据](evidence/2026-10-29-cardputer-adv-imu/README.md) 和
[机器摘要](evidence/2026-10-29-cardputer-adv-imu/summary.json)。

## 2026-10-29：Core2 legacy pre-boot phase profile

`run_pause_sweep.py` 新增显式 `--pc-sample-ns`、`--uart-trace` 和
`phase_profile`，修复此前 UART parser 未实际启用 trace、外部 PC
sampling 仍被记录为 `NOT RUN` 的工具缺口。公开
`UIFlow_Core2 v1.15.4` 在 QEMU `fccfa931…`、`qemu-wifi`、
`icount shift=5` 的 80 秒 WDT-off 诊断中记录 banner `2.7724 s`、
BOARD NAME `54.9924 s`、APIKEY `54.9971 s`、boot.py start/done
`77.8622/78.3712 s`。1,599 个 50 ms PC 样本中，CPU0 的
`0x4026306e` waiti 形态 31.0%，`0x40087980..8e` handoff 簇 60.4%；
SSI 聚合计数为 103,058 transactions、3,181,984 RX bytes（平均约
30.9 bytes/transaction），最后记录的 command/payload counter 为
`0xBB/64`。verbose trace 采样间隔 1024，仅捕获 108 个 begin event
（95 个 `0x05` status read、2 个 `0xBB` 64-byte read、10 个 `0x00`、
1 个 `0x02`），全量 command/length 分布仍未知。

同固件 normal-WDT 仍在 `7.2536 s` stage-0、`17.2536 s` stage-1 reset；
TG1 在 reset 前 14,998 次 feed、最大间隔 3.927 ms、0 timeout。
“所有 high-priority memw/retw 立即切核”“仅 CPU1 首次立即切核”
“cross-core 写时退出 TB”“SPI TRANS_DONE 时退出 TB”四类负控均执行后
丢弃，均未改善 BOARD/APIKEY 或 normal-WDT 启动预算。`RUNTIME-03`
保持 `OPEN`；下一项先补 controller 级 command/length/RX-byte 聚合直方图，
再判断 guest driver 请求分布、interrupt delivery 与缺失的 controller/DMA
bulk path。全部为 virtual-device validation；物理
Flash/cache、RF、电气和硬件时序为 `NOT RUN`。见
[phase profile 证据](evidence/2026-10-29-core2-preboot-phase-profile/README.md)
和[机器摘要](evidence/2026-10-29-core2-preboot-phase-profile/summary.json)。

## 2026-10-29：Core2 legacy SSI transaction profile

新增 `0071-esp32-ssi-transaction-profile.patch`，在默认关闭的 handoff
metrics 中记录完整 16-bit SSI command、RX payload length bucket 和
completion→next-command virtual-time gap，并只在显式 freezes 时输出。
runner 对 command 总数、RX-length 总数和 gap 总数分别与 transaction
计数交叉校验。QEMU 重建后 SHA256 为 `fbc2850c…`，patch SHA256 为
`3c53c5a7…`。

同一 `UIFlow_Core2 v1.15.4` `4d2d648b…` 在 WDT-off、`qemu-wifi`、
`icount shift=5` 下执行有无 50 ms PC sampling 两轮 80 秒控制。无采样
轮记录 `104,302` transactions：`0x05` RDSR `49,489`、`0xBB` Dual-I/O
64-byte Fast Read `49,586`、`0x00` `5,135`，其余 command `92`；
RX length `1` 为 `53,054`、`64` 为 `49,586`。`104,301` 个
completion→next-command gap 合计 `79,699,109,375 ns`，最大值
`2,693,165,726 ns`，主要分布为 `1-10 us` `50,581`、
`100 us-1 ms` `23,800`、`1-10 ms` `25,819`。开启 PC sampling 的
控制得到 `104,975` transactions 和 `79,694,773,694 ns` gap 总量，
分布形状一致，排除采样单独制造该请求形态。

新 QEMU 的 normal-WDT 控制仍在 `7.253601472 s` stage-0、
`17.253695649 s` first reset；TG1 在 reset 前 `14,998` feed、
最大间隔 `3.926687 ms`、零 timeout，和 instrumentation 前边界基本
重合。该结果证明约十万次小 transaction 是 controller 边界真实收到的
guest command 序列，且主要虚拟时间位于相邻 command 之间；仍不能命名
具体 legacy guest driver/IRQ 函数或关闭 startup UI/非空应用帧。
`RUNTIME-03` 保持 `OPEN`。全部为 virtual-device validation；物理
Flash/cache、RF、电气和硬件时序为 `NOT RUN`。见
[证据](evidence/2026-10-29-core2-ssi-transaction-profile/README.md) 和
[机器摘要](evidence/2026-10-29-core2-ssi-transaction-profile/summary.json)。

## 2026-10-29：Core2 legacy SSI command correlation

新增 `0072-esp32-ssi-command-correlation.patch`，在 `0071` 上增加有界
command-length、per-command gap 和 command transition 稀疏表；每张表都有
overflow 计数。QEMU 重建后 SHA256 为 `4aa418e6…`，patch SHA256 为
`107cc478…`。

同一 public `UIFlow_Core2 v1.15.4` 在 WDT-off、`qemu-wifi`、
`icount shift=5` 的 80 秒控制中记录 `105,346` transactions 和
`105,345` 个 gap。联合结果包括 `0x05/1` `50,071`、`0xBB/64`
`49,882`；主要 transition 为 `0xBB->0x05` `49,582`、
`0x05->0xBB` `49,600`，确认 status/64-byte read 交替循环。
command-length、per-command gap 和 transition 总数分别严格等于
transaction 或 `transaction-1`，overflow 全为 `0`。

按当前 command 归因的 gap：

- `0x05`：`65,670,563,678 ns`，占 `82.398%`，平均
  `1.3115489 ms`；
- `0x00`：`13,849,241,407 ns`，占 `17.377%`；
- `0xBB`：`152,263,360 ns`，占 `0.191%`，平均约 `3.05 us`；
- 其余 command：`28,533,432 ns`，占 `0.036%`。

因此主要预算位于 64-byte Fast Read 后、下一次 status read 前的 guest
工作区，而不是 controller 收到 status command 后的单次数据操作。
normal-WDT 控制仍在 `7.249439872 s` stage-0、
`17.249440926 s` first reset；TG1 reset 前 `14,999` feed、最大间隔
`3.926688 ms`、零 timeout，说明 instrumentation 没有改变失败边界。
具体 guest driver/IRQ 函数尚未定位，`RUNTIME-03` 保持 `OPEN`。全部为
virtual-device validation；物理 Flash/cache、RF、电气和硬件时序为
`NOT RUN`。见
[证据](evidence/2026-10-29-core2-ssi-command-correlation/README.md) 和
[机器摘要](evidence/2026-10-29-core2-ssi-command-correlation/summary.json)。

## 2026-10-29：Core2 legacy SSI command issuer PC

新增 `0073-esp32-ssi-command-pc.patch`，在 `0072` 上增加有界稀疏
command/CPU/issuer-PC 表及 overflow 计数；仅显式 freeze 时输出，不改变
SPI、调度、watchdog 或 accelerator。冻结后的 QEMU SHA256 为
`e2efbc67…`，patch SHA256 为 `3655b5b3…`。

同一 public `UIFlow_Core2 v1.15.4` 在 WDT-off、`qemu-wifi`、
`icount shift=5` 的 80 秒控制中记录 `105,161` transactions。command/
CPU/PC 表总数同为 `105,161`，overflow 为 `0`。`0x05` 共 `49,972`
次，其中 `49,961` 次来自 `0x4006222c`，该地址位于 IDF ESP32 ROM
`esp_rom_spiflash_read_user_cmd=0x400621b0` 与
`esp_rom_spiflash_read_status=0x4006226c` 之间；`0xBB/64` 共
`49,783` 次，其中 `49,452` 次来自应用 segment 5 的
`0x40093b57`（load `0x400924d8`、offset `0x167f`）。没有 matching
legacy ELF/MAP，因此不能命名精确应用函数。

同一 QEMU SHA 的 normal-WDT 控制在 `7.253606494 s` 触发 stage-0、
`17.253607230 s` 首次 reset；TG1 reset 前 `14,998` feed、最大间隔
`3.926687 ms`、最后 feed 距 reset `0.813376 ms`、零 timeout。
`RUNTIME-03` 保持 `OPEN`。并发诊断另暴露并修正 runner 的
`free_port() -> serve.py` 端口竞态：`run_wdt_liveness.py` 和
`run_pause_sweep.py` 现可显式传 `--service-port`。首轮缺 stderr 控制
保留为失败证据，不参与结论。全部为 virtual-device validation；物理
Flash/cache、RF、电气和硬件时序为 `NOT RUN`。见
[证据](evidence/2026-10-29-core2-ssi-command-pc/README.md) 和
[机器摘要](evidence/2026-10-29-core2-ssi-command-pc/summary.json)。

## 2026-10-29：正式 GitHub Pages 部署与公开 CoreS3 验收

原仓库已启用 GitHub Actions Pages 来源，并在 main 提交
`8e47c6ba83c042398d767a8d56ff47c16b927181` 手动运行
`publish=true`、前缀 `/m5stack-esp-emulator/`。固定源码 C/QEMU 构建、
LittleFS 组合、静态导出和 Actions 内真实 CoreS3 guest 验收完成；
构建 `13m53s`，部署 `14s`。正式地址
<https://m5agent.github.io/m5stack-esp-emulator/> 返回 HTTP 200，
公开 manifest 声明 `1922` 个资产、`service_url` 为空且
`firmware_bundled=false`。

部署后从正式 HTTPS 地址独立执行同一真实 C/QEMU 验收器，21 项检查全部
PASS：共享内存、实际 RGB 帧、触摸正反例、PIR 双向状态、QMP 暂停/继续、
四档布局、停止/重开、Worker/iframe 清理、无服务/本机模拟器请求及无 JavaScript
错误。公开报告 SHA256 为
`3251b33ef5fb76340a48f8cbd3e780ee3b9ce86caf613f176b58a90ffa6bee33`；
运行时/固件身份、Actions 链接与边界见
[正式部署证据](evidence/2026-10-29-github-pages-production/README.md)
和[机器摘要](evidence/2026-10-29-github-pages-production/summary.json)。
结论限定为 browser virtual-device validation；默认墙钟调度、长期稳定性、
网络、音频、其它设备/固件/Unit、Flash 持久化和物理硬件仍 `NOT RUN`。

## 2026-10-29：StopWatch / StickS3 / Core2 UIFlow2 全接口复测

三台当前原厂 UIFlow2 `v2.5.3` 在 QEMU `fccfa931…` 上并发执行：
system runtime 各 `50 PASS + 1 STATE_PASS`、shared corrections 各
`7/7`；sockets `23/23`、MQTT `42/42`、network `14/14`、EzData
`17/17`、EasySocket `57 + 1 N/A`。StopWatch/StickS3 audio player
`15/15`、recorder `12/12`；三台 ESP-NOW/native ESP-NOW loopback
分别通过 `12 + 5 STATE_PASS + 1 CONFIGURED_UNVERIFIED` 和
`21 + 21 STATE_PASS + 3 CONFIGURED_UNVERIFIED`。已选 peripherals、
IMU、电源、StopWatch IOE/PM1、StickS3 IR 和 Core2 Speaker/Mic 组完成
串口、host-action、frame/QOM 或 units 交叉核对。

StopWatch/Core2 各执行 28 类、505 个 M5UI 文档方法，分类均为
`407 STATE_PASS + 80 PENDING_FRAME_OR_INPUT + 3
PENDING_FRAME_OBJECT_REMOVAL + 11 DOCUMENTATION_MISMATCH +
1 EXPECTED_UNSUPPORTED + 3 FAIL`，最终 `28/28` 帧非黑。stock 三失败为
Canvas triangle descriptor、Image float scale 和 integer Spinbox step；
StopWatch candidate 得到 `4/4` 状态和 `2/2` frame oracle，Core2
candidate 得到 `4/4` 状态但全屏刷新仍条带/坐标错误。StickS3 当前镜像
不导出 `m5ui`。

BLE 测试身份对齐后，StopWatch/StickS3 分别用 `M5-STOPWATCH-UNIFIED`、
`M5-STICKS3-UNIFIED` 扫描仍无可连接 advertisement，Core2 在
`UNIFIED_CORE2_IO_CONFIG_READY` 前超时；stock GATT 保持
`BLOCKED_MODEL`。本轮修复 M5UI runner 的设备尺寸/旋转、最长 120 秒
program 预算、完整 BLE identity 和 Core2 blocker 文案。平台回归
`1406` 项 `OK`、`1` skip；生成器、compileall、scoped Ruff 和 diff check
均 PASS。全部为 virtual-device validation；Core2 legacy `RUNTIME-03`、
stock BLE、外部/加密 ESP-NOW、RF/timing 和物理硬件仍 `NOT RUN`。见
[证据](evidence/2026-10-29-three-board-uiflow2-full-retest/README.md)
和[机器摘要](evidence/2026-10-29-three-board-uiflow2-full-retest/summary.json)。

## 2026-10-29：Core2 M5UI panel DMA 双写修复

`0074-esp32-spi-panel-dma-dedup.patch` 修复 classic ESP32 SPI panel 的
同笔 DMA 双消费：`DMA_LINK` descriptor 已把完整像素写入 panel 后，
`SPI_CMD` 事务又通过 64-byte CPU data register 及其重复 tail 写入一次。
`M5SW_PANEL_RAMWR_TRACE` 在修复前测得 48 个 `320x10` RGB565 strip 应写
`6,400` bytes、实际写 `12,736` bytes，20x60 image window 应写 `2,400`
、实际写 `4,736`；修复后 54 个 RAMWR window 全部 `written == expected`。

同一 hash-pinned Core2 M5UI candidate 在 frozen QEMU `9bf74439…` 上由
triangle/image `2 FAIL` 变为 `2 FRAME_PASS`，4 个状态 oracle 继续
`4/4 PASS`。最终 frame SHA256 为 `5a074d29…`，画面完整且无条带。
MADCTL=true、rotation=0 和 READY 后延迟重取帧三个控制都未消除修复前
条带，排除 rotation/oracle/capture timing 解释。同一 QEMU 的三设备
并发 smoke 中，StopWatch/StickS3/Core2 system runtime 各
`50 PASS + 1 STATE_PASS`、shared corrections 各 `7/7 PASS`，所有
session 均取 evidence ZIP 后以 `purge=0` 停止。当前限定为
virtual-device validation；物理 ILI9342 DMA/SPI timing、电气和真机视觉
仍 `NOT RUN`。见[证据](evidence/2026-10-29-core2-m5ui-dma-dedup/README.md)
和[机器摘要](evidence/2026-10-29-core2-m5ui-dma-dedup/summary.json)。

## 2026-10-29：Core2 stock UIFlow2 BLE via native HCI

此前 `run_protocols.py` 把 Core2 stock BLE 强制送入 `core2-unified`，
没有上传 `core2-native-hci` 所需 matching ELF，导致 timeout 被错误归类为
stock GATT 模型阻塞。runner 现在使用 `core2-native-hci`，要求显式
`--core2-elf` 并上传 artifact；ACK oracle 改为要求同一条 peer log 内
完成 connection、GATT discovery、subscription、exact write 和 exact
notification，不再依赖 guest 完成后才会出现的 host-only cycle tail。

同一个 stock `UIFlow2 v2.5.3` base `b228c0e2…`、matching ELF
`5bec056b…` 和 frozen QEMU `9bf74439…` 上，Core2 `ble-nus` 三个独立
session 均为 `8/8 PASS`。peer 实际发现 `M5-CORE2-UNIFIED`，订阅
`6e400003…`，写入 `M5_CORE2_UNIFIED`，并收到精确通知
`ACK:M5_CORE2_UNIFIED`；所有 session 均取得 evidence ZIP 且 runtime
PID gone。Core2 `m5ble-server` 为 `21 PASS + 1 ERROR`，唯一错误是 stock
API `Server.get_client` 的 `TypeError("'set' object isn't subscriptable")`，
继续作为 SDK/API 缺陷保留。

该结果只关闭当前 Core2 stock BLE NUS/native-HCI 路径；StopWatch/StickS3
stock internal-controller、BLE 安全、RF、共存、时序和物理硬件仍
`NOT RUN`/开放。见[证据](evidence/2026-10-29-core2-stock-ble-native-hci/README.md)
和[机器摘要](evidence/2026-10-29-core2-stock-ble-native-hci/summary.json)。

## 2026-10-29：Core2 UIFlow2 `m5ble.Server.get_client` 候选修复

Core2 stock `m5ble-server` 的唯一 API 错误定位到
`Server._connected_devices` 是 `set`，而 `get_client(index)` 直接执行
`self._connected_devices[index]`。`0025` 按 `connect_handle` 对连接对象
排序后应用零基索引，不改变内部集合和其他 BLE 方法。生成器先叠加
`0021` 的 UUID32 decoder 修正，最终 candidate SHA256 为 `d82c1aec…`。

同一 stock base `b228c0e2…`、matching ELF `5bec056b…` 和 frozen QEMU
`9bf74439…` 上，最终两个并发 Core2 native-HCI session 均从 stock
`21 PASS + 1 ERROR` 转为 candidate source `22/22 PASS`。两轮 peer 均实际
完成连接、GATT discovery、CCCD 订阅、写入 `M5_CORE2_UNIFIED` 并收到
`ACK:M5_CORE2_UNIFIED`；`get_client(0)` 返回回调中的同一连接对象。
报告保持 stock firmware lane 与 candidate source lane 分离，两个 session
均取得 evidence ZIP、以 `purge=0` 停止并验证 runtime/companion PID gone。

首次候选注入轮因测试夹具错误查找模块级不存在的 `M5BLE` 符号而保留为
`KeyError: M5BLE` 诊断，不计入功能结果。并发矩阵另保留两次断连后
`deinit()` timeout：stock `BLEUARTServer` 为 `7 PASS + 1 TIMED_OUT`，
candidate `m5ble.Device` 为 `21 PASS + 1 TIMED_OUT`；两次 GATT/ACK 均已完成。
协议 probe 在显式断连后等待 `2000 ms` 让自动重广告和 BLE task 收口，随后
两轮 stock `ble-nus` 均为 `8/8 PASS`、两轮最终 candidate 均为
`22/22 PASS`，且与同一 Core2 M5UI 矩阵并发。该 settle 只修正测试时序，
不声称任意负载下固件 `active(False)` 都有有界完成时间。该结论只覆盖 Core2 当前
base/ELF/QEMU/native-HCI；StopWatch/StickS3 stock controller、BLE
pairing/security、RF、共存、controller bit-exact 和物理硬件仍
`NOT RUN`/开放。见[证据](evidence/2026-10-29-m5ble-get-client-candidate/README.md)
和[机器摘要](evidence/2026-10-29-m5ble-get-client-candidate/summary.json)。

## 2026-10-29：StopWatch / StickS3 / Core2 UIFlow2 接口再次复测

在 frozen QEMU `9bf74439ddbe7225a64eb437290043729fb032525756adb834565ec412f8c197`
上重新并发执行三台当前 stock UIFlow2 `v2.5.3`。system runtime 各
`50 PASS + 1 STATE_PASS`、shared corrections 各 `7/7`、board display
分别为 StopWatch `468x468`、StickS3 `135x240`、Core2 `320x240` PASS。
Sockets、EasySocket、MQTT、network、EzData 与 ESP-NOW/native ESP-NOW
继续保持通过；StopWatch/StickS3 的 audio player/recorder 为
`15/15`、`12/12`，Core2 当前镜像不导出这两个模块。

三台 stock 仍稳定复现 `requests2.urlencode`、八个 Modbus async
`Loop.sock_recv` 和 TLS epoch 缺陷；相同 stock base 上的 requests2
candidate 各 `2/2`、Modbus async candidate 各 `50/50`、TLS candidate
各 `5/5`。Core2 stock `m5ble-server` 保持 `21 PASS + 1 ERROR`，叠加
`0021` UUID32 与 `0025` sorted-client accessor 后为 `22/22 PASS`。
Core2 `ble-nus` 在 GATT/ACK 后增加 2 秒 teardown settle 后重新
`8/8 PASS`；首轮并发下的单次 deinit timeout 作为时序 control 保留。

StopWatch/Core2 各执行 28 个 M5UI 类、505 个 widget 方法，另加
`m5ui.init/deinit`，共 507 个结果且没有未观察方法。分类均为
`409 STATE_PASS + 80 PENDING_FRAME_OR_INPUT + 3
PENDING_FRAME_OBJECT_REMOVAL + 11 DOCUMENTATION_MISMATCH +
1 EXPECTED_UNSUPPORTED + 3 FAIL`；stock 三失败仍为 Canvas triangle、
Image float scale 和 Spinbox integer step。StopWatch/Core2 candidate
均为 `4/4` 状态和 `2/2 FRAME_PASS`，Core2 frame SHA256
`5a074d29…` 与此前 `0074` 结果一致。

三台通用硬件 probe 各得到 `115 CALL_OK + 66 API_ASSERTION_PASS +
1 OBSERVED`；StopWatch 的 M5IOE1/M5PM1/vibration、StickS3 的
peripherals/IR、Core2 的 INA3221/IMU/AXP192/Mic/Speaker 均重跑。
M5PM1 缺失 fixture 的 ImportError 和 Core2 默认 AXP2101 路径的
QOM 503 都保留为 harness control，不写成固件失败；补 fixture 与
`M5SW_CORE2_PMIC=axp192` 后均通过。全部为 virtual-device validation，
真机、RF、安全和物理 timing 仍 `NOT RUN`。见[证据](evidence/2026-10-29-three-board-uiflow2-interface-retest-r2/README.md)
和[机器摘要](evidence/2026-10-29-three-board-uiflow2-interface-retest-r2/summary.json)。

## 2026-10-29：最新 QEMU 三设备 UIFlow2 接口复测

在 QEMU `05a43941c087642f274a4521c495edde88269ec1f99187742b509cc98ac49d59`
上重新并发执行三台 stock UIFlow2 `v2.5.3`。全部报告实际加载的 runtime
哈希一致；system runtime 各 `50 PASS + 1 STATE_PASS`、shared corrections
各 `7/7`，board display 分别为 StopWatch `468x468`、StickS3 `135x240`、
Core2 `320x240`。Sockets、EasySocket、MQTT、network、EzData 和
ESP-NOW/native ESP-NOW 继续保持通过；StopWatch/StickS3 audio player/recorder
为 `15/15`、`12/12`。

三台 stock 仍复现 `requests2.urlencode`、八个 Modbus async 和 TLS epoch
缺陷；对应 candidate 分别为三台各 `2/2`、`50/50`、`5/5`。Core2 stock
`m5ble-server` 保持 `21 PASS + 1 ERROR`，`0021+0025` candidate 为
`22/22 PASS`；stock `ble-nus` 使用 `core2-native-hci` 和 matching ELF
为 `8/8 PASS`。StopWatch/StickS3 stock GATT 继续为 `BLOCKED_MODEL`，
client 组为 `NOT_RUN / BLOCKED_FIXTURE`。

StopWatch/Core2 各执行 29 个 M5UI session、507 个结果且没有漏测；分类仍为
`409 STATE_PASS + 80 PENDING_FRAME_OR_INPUT + 3
PENDING_FRAME_OBJECT_REMOVAL + 11 DOCUMENTATION_MISMATCH +
1 EXPECTED_UNSUPPORTED + 3 FAIL`。Stock 三失败保持，candidate 均为
`4/4 STATE_PASS + 2/2 FRAME_PASS`，frame SHA256 分别保持
`19523193…`、`5a074d29…`。三台 hardware matrix 各
`115 CALL_OK + 66 API_ASSERTION_PASS + 1 OBSERVED`，设备本地
StopWatch M5IOE1/M5PM1/vibration、StickS3 IR TX/RX 和 Core2
INA3221/IMU/AXP192/Mic/Speaker 均重跑。

Core2 network 在三设备首轮冷启动并发时出现过一次 re-activate 后立即 scan
未看到 fixture AP；隔离重跑与随后 `4/4` 三设备并发重复均为 `14/14 PASS`。
StickS3 TLS candidate 首轮缺少 native UART-REPL bootstrap，修正后
`5/5 PASS`。两者均保留为测试控制，不写成模拟器稳定回归。平台套件
`1432` 项 `OK`、`1` 项既有 skip，四个生成器检查和 `git diff --check`
PASS；三个隔离服务、QEMU 和 BLE peer 全部清理。全部为
virtual-device validation，真机、RF、安全、声学/光学/电气和 legacy
`RUNTIME-03` 仍 `NOT RUN`/开放。见
[证据](evidence/2026-10-29-three-board-uiflow2-interface-retest-r3/README.md)
和[机器摘要](evidence/2026-10-29-three-board-uiflow2-interface-retest-r3/summary.json)。

## 2026-10-29：当前 QEMU 三设备 UIFlow2 接口复测 r4

在 QEMU `dd4b1b34a4003a6fe84263974efade9d8d85e584fcd7397bc0f13b2d77337435`
上再次并发执行三台 stock UIFlow2 `v2.5.3`。全部报告实际加载的 runtime
哈希一致；system runtime 各 `50 PASS + 1 STATE_PASS`、shared corrections
各 `7/7`，board display 分别为 StopWatch `468x468`、StickS3 `135x240`、
Core2 `320x240`。Sockets、EasySocket、MQTT、network、EzData 和
ESP-NOW/native ESP-NOW 继续保持通过；Core2 network 在三设备首轮并发即
`14/14 PASS`，相对 r3 首轮 `13/14` 改善。StopWatch/StickS3 audio
player/recorder 为 `15/15`、`12/12`。

三台 stock 仍复现 `requests2.urlencode`、八个 Modbus async 和 TLS epoch
缺陷；对应 candidate 分别为三台各 `2/2`、`50/50`、`5/5`。Core2 stock
`m5ble-server` 保持 `21 PASS + 1 ERROR`，`0021+0025` candidate 为
`22/22 PASS`；stock `ble-nus` 使用 `core2-native-hci` 和 matching ELF
为 `8/8 PASS`。StopWatch/StickS3 stock GATT 继续为 `BLOCKED_MODEL`，
client 组为 `NOT_RUN / BLOCKED_FIXTURE`。

StopWatch/Core2 各执行 29 个 M5UI session、507 个结果且没有漏测；分类仍为
`409 STATE_PASS + 80 PENDING_FRAME_OR_INPUT + 3
PENDING_FRAME_OBJECT_REMOVAL + 11 DOCUMENTATION_MISMATCH +
1 EXPECTED_UNSUPPORTED + 3 FAIL`。Stock 三失败保持，candidate 均为
`4/4 STATE_PASS + 2/2 FRAME_PASS`，frame SHA256 分别保持
`19523193…`、`5a074d29…`。三台 hardware matrix 各
`115 CALL_OK + 66 API_ASSERTION_PASS + 1 OBSERVED`，设备本地
StopWatch M5IOE1/M5PM1/vibration、StickS3 IR TX/RX 和 Core2
INA3221/IMU/AXP192/Mic/Speaker 均重跑。

Core2 网络 profile 要求显式 `M5_CORE2_RADIO_QEMU`；缺少时 `503` 被保留
为测试控制。StopWatch TLS candidate 使用默认 `dupterm`、StickS3 使用
`native` UART-REPL bootstrap，各自 `5/5 PASS`；候选 M5UI 以
`program_transport=uart-repl` 创建可见 base session 后通过。全部为
virtual-device validation，真机、RF、安全、声学/光学/电气和 legacy
`RUNTIME-03` 仍 `NOT RUN`/开放。见
[证据](evidence/2026-10-29-three-board-uiflow2-interface-retest-r4/README.md)
和[机器摘要](evidence/2026-10-29-three-board-uiflow2-interface-retest-r4/summary.json)。

## 2026-10-29：Core2 legacy RDSR 与 CAS 关联诊断

`0075-esp32-legacy-status-cas-correlation.patch` 在既有 handoff freeze
上增加三组有界诊断：`RDSR(0x05)` 返回状态及其前序 `0xBB/64`
地址/数据前缀；两次 status read 之间的 cache counter delta；以及
`s32c1i` 的 PC/caller/lock/old-owner/跨核 holder-PC 聚合。稀疏表和
固定数组都有 overflow，输出只在显式 pause 时发生。另保留一个默认关闭的
`M5SW_XTENA_CONTENDED_CAS_YIELD`，只作为失败 CAS 的 TCG-slice
负向控制。

同一 public `UIFlow_Core2 v1.15.4` normalized SHA `4d2d648b…`、
QEMU `d60e6fb0…`、`runtime=qemu-wifi`、`icount shift=5` 的 20 秒
WDT-off 诊断得到 12,093 次 `RDSR`：`0x00` 4,278 次、`0x02` 7,815 次，
bit0 WIP/BUSY 全为 `0`。11,904 次 status read 紧跟 `0xBB/64`；
这些 status gap 合计 `17.074056543 s`，占窗口 `85.370%`。所有 status
上下文均为 PS intlevel 0 和 `interrupt_request=0`。cache sync 与
state-update counter 在大多数区间继续变化，但 illegal-read 为 `0`。

同窗口记录 6,288,123 次 `s32c1i`、537,482 次成功和 5,737,336 次真实
跨核竞争。`0x3ffbf2cc` 单独占 5,482,913 次 CAS、253,241 次成功；
old-owner 常态为 free、`0xABAB` 或 `0xCDCD`，没有证明 QEMU CAS
返回值损坏。最高 failed-CAS 调用是 CPU0 `A0=0x8009655c` 在
site `0x40095b2e` 等锁 `0x3ffbf2cc`。holder-PC 以 256-byte 桶记录，
热点覆盖 `0x400958xx-0x400961xx`、`0x40096dxx` 和
`0x40097axx-0x40097bxx`；没有 matching legacy ELF/MAP，不能命名
精确函数。

normal-WDT 与 failed-CAS slice-yield 都在约 `17.249 s` 触发
`TG0` stage-1 system reset，TG1 持续 feed 且零 timeout。两次 serial
仍只有 MicroPython banner、没有 REPL prompt，frame 仍是 302-byte
black PNG；因此 failed-CAS yield 被否定为修复，`RUNTIME-03` 保持
`OPEN`。全部为 virtual-device validation；物理 cache/PSRAM timing、
RF、电气和真机均 `NOT RUN`。见[证据](evidence/2026-10-29-core2-legacy-status-cas/README.md)
和[机器摘要](evidence/2026-10-29-core2-legacy-status-cas/summary.json)。

## 2026-10-29：浏览器共享帧、host poll 与正常时钟 LVGL 候选

在主线 `322130288ea4fb2c2aab49b689e232bb2beef7f7` 基础上，固定 QEMU
来源、43 层补丁和 146 个修改文件完整重建 WASM
`9c94a9407893fa7d953d1bf1932769ff52e90b3b1455f98a90185ff2bf05cba1`。
`0014` 从真实 QEMU display surface 读取有界共享 RGB565 快照，校验一致性
后只传 dirty update；`0015` 修正 SDK 3.1.50 忽略 poll timeout 的 host
pthread 空转，没有改 guest 时钟、WDT 或 vCPU 指令执行。

性能对照顺序运行于同一 Apple M4 Pro、Chrome 156 与 ANGLE Metal，
旧、新 runtime 使用相同 stock/div8 fixture Flash
`78961297e751ec9c743b4cdf89cc2c137e7e2c801dda3ead9df2ea45d59fbd3f`。
CPU `100%` 为一个逻辑核；早期软件 renderer 和并行编译样本未用于对照。

| 同固件测量 | 旧 runtime | 共享帧 + host 等待修复 |
| --- | ---: | ---: |
| 运行 CPU 平均 | 132.05% | 49.95% |
| 暂停 CPU 平均 | 105.60% | 4.78% |
| 停止 CPU 平均 | 3.02% | 2.62% |
| 静态画面请求/s | 1.30 | 30.99 |
| 静态画面传帧/s | 1.30（重复像素） | 0（无重绘） |
| 触摸松开到计数像素，中位数 | 1317.66 ms | 966.82 ms |

运行 CPU 下降约 `62.2%`；静态请求率不代表动画 FPS，触摸仍有明显延迟。
真实 SDK poll/pipe/pthread 的六项 host controls 另验立即就绪、有限/无限
等待和跨线程唤醒；这些 controls 本身不执行 guest。

正常时钟使用独立 Flash
`e9500994f4c0e1708ec35f5a46146225ac330d210a2427e1fc537c33635d9554`、
div1 和显式 `0026` SDK Python 调度候选。候选在已有 VM callback 内直接执行
LVGL、累计实际 guest elapsed ticks，并在 `finally` 清除 guard；未修改 stock
frozen SDK，也未实现 C Timer 第一层 coalescing。严格同 guest 回归 `25/25`
覆盖实际 RGB565/可读字形、负触摸、两次 pressed/released/clicked、PIR
`0→1→0` 与 QOM/画面变化、LVGL timer 星标动画、暂停恢复、停止前 evidence
和历史；exit `0`，五个 Workers 清零、显式 disposal 完成且 iframe 移除。
SDK 固定 preimage 的八项回归、fixture 六项、composer 七项与真实 Chromium
包装十九项分别通过，不混作 guest 功能检查。

候选持续动画的独立 20 秒窗口实际像素变化约 `8.90/s`、轨迹速度
`99.77 px/墙钟秒`（源码目标 `100 px/guest秒`），guest/LVGL 与 host 速率
约 `0.9997`、调度错误为 `0`。该负载运行 CPU 为 `161.97%`，触摸松开到
回调/计数像素中位数约 `867/1247 ms`；它与旧静态 fixture 不同，不能作为
同固件 CPU 或输入提速对照。QMP/channel ACK 约 `35 ms`，较长延迟仍位于
ACK 之后到 UART 观察到 guest release 之前，当前证据不能唯一归因到
触控控制器、guest 读取、LVGL 或 UART 观察中的某层。

这些均为本地 browser virtual-device validation；正式 Pages 仍为既有版本，
native 设备组、其余板型/固件/Unit、长期稳定性及物理硬件不继承通过。
原始 Flash/ROM/帧/日志在 ignored/local archive，完整运行、构建和报告哈希见
[性能与板型证据](evidence/2026-10-29-wasm-performance-devices/README.md)、
[性能机器摘要](evidence/2026-10-29-wasm-performance-devices/summary.json)与
[正常时钟 LVGL 候选](evidence/2026-10-29-browser-lvgl-wallclock/README.md)。

## 2026-10-29：浏览器四板五个固定 fixture 的逐板公开 UI 准入

相同 WASM `9c94a940…cba1` 下，public-v4 导出先串行完成 CoreS3
stock/div8、CoreS3 wallclock candidate、AtomS3R 和 StickS3 四个 fixture，
合计 `84/84` 检查通过。该导出 manifest SHA256 为
`baab0f78c82de2bd93013fa937934443ae363c37b212e241db4bb67e443e4bcb`，
aggregate 报告 SHA256 为
`97eb67cc97d1ab56493f66e910bd3dce65ff6f02f011a708f862e8d697c5b345`。

Core2 候选公开 UI 验证通过后，registry promotion 为 public，另导出
public-v5 并单独重验 Core2，`17/17` 检查通过。该导出 manifest SHA256 为
`187cf38ad80dc400af07d7d2ef6f35e9b9e73eaf167c9241fb76558f4204ea72`，
Core2 报告 SHA256 为
`ff67399261a7cb7e4c700d8009fe164d01f962fecf90ac3e39962e5677e550e8`。
v4→v5 仅三个元数据/fixture 资产变化，其余 1929 个资产与执行 JS/runtime
保持一致。`84+17` 是两次明确导出的检查总数，不能写成 v5 全聚合运行。

| 新增设备 | 实际 framebuffer | 完整组合 Flash SHA256 | 真实公开 UI 输入 |
| --- | --- | --- | --- |
| AtomS3R | 128×128 | `39c8204958c09516407ee6743d532777b7ac81f7650d2fbf7c1038587b361a80` | focused model button press/release |
| StickS3 | 135×240 | `a8a88bf4fd2736d4bfd2f4c629b4040c0d38ca8d1ec54156dd74b34cd5a38632` | focused model button press/release |
| Core2 | 320×240 | `5d252ee60ce0f6a481b13ccdf6f911ac0c41687b888ef273dc7c455e62a5b2c2` | DOM touch press/release |

新增三板均在 div1 下使用原固件驱动、本地 LittleFS 组合与同 guest 帧/输入；
Core2 使用保留固件 console 的专用 boot。每个 fixture 分别核对实际画面、
输入结果和退出清理，公开 profile 必须同时存在于本次 runtime 的
`compiled_profiles`；machine help、编译入库或 native PASS 不能单独准入。
六个剩余 Xtensa candidate、C6 RISC-V、P4、Linux ARM64、stock 菜单、
网络/音频/其它 Unit、任意固件和物理硬件均未继承。正式 Pages 仍为旧版本。
分批报告、runtime/ROM/固件身份与检查结果见
[性能与逐板证据](evidence/2026-10-29-wasm-performance-devices/README.md)和
[逐板准入摘要](evidence/2026-10-29-wasm-performance-devices/board-admission-summary.json)。

## 2026-10-29：ESP-NOW 两个独立 guest 的明文外部 peer 交换

新增
`0076-esp32-external-espnow-peer-bridge.patch`，SHA256
`de39dd922d15bc2ad3827a13293d86dc2a2f0dafcfe2036783730dfab8037c62`。
桥接只在两个 controller 都配置成对的 loopback UDP 端口时启用，只转发
802.11 management action frame；发送仍经 guest 正常 controller TX DMA，
接收仍经目标 controller 正常 RX DMA，不合成 Python payload/callback。
同一 guest 的 `0067` loopback 与该 lane 明确互斥。最终 QEMU SHA256 为
`df0e20f176494a9de8e32361dbc865688c5e72791207793d0bdb0b5a947b616a`。

StopWatch↔StickS3 的两个独立 session 分别收到对方 payload
`57/57` 与 `58/58`，bridge TX/RX 均为 `58/58`。Core2↔StopWatch 的
Core2 收到 `14/14`，StopWatch 收到 `44/44`；Core2 较慢的 UIFlow2 初始化
由 12 秒有界收敛窗口覆盖，4 秒窗口只作为 harness 过短失败保留在 ignored
运行记录。四个 session 均使用 `purge=0` 停止，terminal state 为
`stopped`、QEMU PID 已消失，停止前取得 serial/frame/evidence ZIP。

该结果关闭 `RUNTIME-06` 的“两个独立 guest 完成未加密 action-frame
交换”里程碑，但任务仍为 `PARTIAL`：PMK/LMK/CCMP、错误 key、
peer add/update/delete、replay、loss/retry、超过两个 peer 的 fabric、
channel/rate、bit-exact controller、RF/antenna、电气时序和真机均
`NOT RUN`。全部为 virtual-device validation。见
[证据](evidence/2026-10-29-espnow-external-peer/README.md)和
[机器摘要](evidence/2026-10-29-espnow-external-peer/summary.json)。

## 2026-10-29：ESP-NOW external peer 的 key-bound AES-CCMP

新增 `0077-esp32-espnow-external-ccmp.patch`，SHA256
`4a0aa4fa4d92ddf00d02e62136c4bc881b4a5b6e73edeb78a835feb94a74e095`。
该 patch 在 `0076` 的 independent-guest bridge 边界执行真实 AES-CCMP：
PMK 以 AES-128-ECB wrap LMK，plaintext LMK 不进入 controller state；TX
移除 guest hardware envelope 后以新 PN/8-byte MIC 加密 action body，RX 在
正常 DMA 注入前验证 MIC，认证失败直接丢弃。最终 QEMU SHA256 为
`5340171ca484ce7ee3b13a0538a35c5f22fcd3a2ff726fa7a902424ff4d7d179`。

StopWatch↔StickS3 完成明文回归、正确 key、错误 LMK 和 wrong-PMK/same-LMK
四条路径；Core2↔StopWatch 完成正确 key 与错误 LMK。十二个独立 session 中，
正确 key 均双向收到对方 payload；两条错误 LMK 场景的两个方向均为
`EXPECTED_DROP`、`rx_packets=0`，同时 bridge TX/RX 仍大于零，证明数据已到达
peer controller 后才因 MIC 失败被丢弃。wrong-PMK/same-LMK 按 ESP-NOW 语义
继续 PASS，因此不能把它当作错误 payload key 负控。所有 session 均
`purge=0` 停止，terminal state 为 `stopped`、QEMU PID 已消失并保留 history。

PMK/LMK 现在从 API snapshot 和 persisted session JSON 脱敏为
`<redacted>`。早期“原样搬运 guest protected envelope”控制在错误 LMK 下仍
PASS，因此被拒绝；只有实际 CCMP/MIC 实现进入本轮结论。

该结果关闭 `RUNTIME-06` 的 key-bound CCMP fixture 正负控，但任务仍为
`PARTIAL`：guest `set_pmk`/`add_peer` key-state 传播、key rotation、
peer add/update/delete、replay、loss/retry、超过两个 peer 的 fabric、
channel/rate、bit-exact controller、RF/antenna、电气时序和真机均
`NOT RUN`。全部为 virtual-device validation。见
[证据](evidence/2026-10-29-espnow-external-ccmp/README.md)和
[机器摘要](evidence/2026-10-29-espnow-external-ccmp/summary.json)。

## 2026-10-29：ESP-NOW external CCMP PN anti-replay

新增 `0078-esp32-espnow-external-ccmp-replay.patch`，SHA256
`b30c56272dba2fd6e4000ee8b12f82a08e57ccadf8bc8e0d0d42488b5baa1adc`。
该 patch 只允许 MIC 验证成功的 encrypted frame 推进单 peer receiver PN；
equal/older PN 在 `espnow_peer_wrap_rx_envelope` 和 normal RX DMA 之前
丢弃。Session realize/cleanup 与 wrapped key state 一起重置 PN。最终 QEMU
SHA256 为 `be7c376550829427b0fc72ada75f9d06e2246feaa64b2c222904d5a17a3c4076`。

replay fixture 使用 UDP proxy 转发真实 bridge datagram；在两个方向都已
通信后，仅对一帧 left→right datagram 额外发送一次。两个方向各转发 `58`
帧、`replay_sent=true`，StickS3 receiver 的 trace 从 `58` 增至 `59` 并记录
一次 `[espnow-peer] RX drop: CCMP PN replay`；双方正常 peer payload 仍为
`57/58`，没有重复到达 guest callback。wrong-LMK 回归两侧仍
`rx_packets=0`，Core2↔StopWatch encrypted 回归为 `15/44`。

六个 session 均 `purge=0` 停止，terminal state 为 `stopped`、QEMU PID
已消失并保留 history。该结果关闭单 peer monotonic replay fixture，但
`RUNTIME-06` 仍为 `PARTIAL`：多 peer/乱序 replay window、PN wrap 与
key rotation、guest key-state 传播、peer lifecycle、loss/retry、
channel/rate、bit-exact controller、RF/antenna、电气时序和真机均
`NOT RUN`。见[证据](evidence/2026-10-29-espnow-external-ccmp-replay/README.md)
和[机器摘要](evidence/2026-10-29-espnow-external-ccmp-replay/summary.json)。

## 2026-10-29：ESP-NOW native peer add/delete/modify 生命周期

stock UIFlow2 `espnow.ESPNow` lifecycle runner 在 QEMU
`be7c3765…` 上验证独立 guest 的 encrypted peer 生命周期。
StopWatch↔StickS3 与 Core2↔StopWatch 均完成 `add_peer` 后
`peer_count=[1,1]`、双向 PRE 同步、`del_peer` 后 `[0,0]`、删除后
`get_peer`/`send` 的 `OSError` 负控、重新 `add_peer`/`mod_peer` 后
`[1,1]`，以及 post-resume encrypted payload 双向交付。

四个 session 的 `get_peer_not_found`、`send_rejected`、`modified`、
`pre_synced`、`post_resumed` 全为 true；均 `purge=0` 停止、runtime PID
消失并保留 history。Core2 首轮暴露 runner 单向屏障竞态：StopWatch 收到
Core2 PRE 后立即删除，较慢 Core2 尚未看到回向 PRE；delete/re-add/modify
本身已 PASS。runner 改为首次匹配后继续发送 PRE 1.5 秒再删除，两个设备对
最终均 PASS。

该结果关闭 stock native guest 的 encrypted peer add/delete/modify
生命周期，但 `RUNTIME-06` 仍为 `PARTIAL`：guest key-state 写入 QEMU
bridge、key rotation、m5espnow wrapper、多 peer/乱序 replay window、
loss/retry、channel/rate、bit-exact controller、RF/antenna、电气时序和
真机均 `NOT RUN`。见[证据](evidence/2026-10-29-espnow-peer-lifecycle/README.md)
和[机器摘要](evidence/2026-10-29-espnow-peer-lifecycle/summary.json)。

## 2026-10-29：M5ESPNow wrapper peer lifecycle

stock `m5espnow.M5ESPNow` wrapper 在同一 QEMU `be7c3765…` 上完成
StopWatch↔StickS3 与 Core2↔StopWatch 的 external encrypted peer 生命周期：
`set_pmk_encrypt`、`set_add_peer`、`get_peer_list(1)`、bidirectional PRE
barrier、`set_delete_peer`、peer list/count 清空、delete 后 `send_data`
no-op、re-add、peer list 恢复和 post-resume 双向 payload。

四个 session 的 `initial_count/readded_count=[1,1]`、
`deleted_count=[0,0]`、`deleted_peer_list_empty`、
`send_after_delete_noop`、`peer_list_restored`、`pre_synced`、
`post_resumed` 均为 true。M5ESPNow wrapper 在 peer 缺失时静默跳过
`send_data`，与 native `send` 的 `OSError` 行为按 API 分开记录。所有
session 均 `purge=0` 停止、runtime PID 消失并保留 history。

该结果关闭 stock M5ESPNow wrapper 的 peer add/delete/re-add 生命周期，
但 `RUNTIME-06` 仍为 `PARTIAL`：guest key-state 写入 QEMU bridge、
key rotation、多 peer/乱序 replay window、loss/retry、channel/rate、
bit-exact controller、RF/antenna、电气时序和真机均 `NOT RUN`。见
[证据](evidence/2026-10-29-espnow-m5espnow-lifecycle/README.md)和
[机器摘要](evidence/2026-10-29-espnow-m5espnow-lifecycle/summary.json)。

## 2026-10-29：ESP-NOW external CCMP 64-frame replay window

新增 `0079-esp32-espnow-external-ccmp-window.patch`，SHA256
`c4f40a614412db0b0c642f448820bb1acb8cf9bbe980df4e20e15d5c74556e0c`。
该 patch 将单 peer 严格 monotonic PN 检查升级为 64-frame authenticated
bitmap：新 PN 向前移位窗口，window 内未见 PN 接受一次，duplicate 和窗口外
PN 在 MIC 成功后丢弃；MIC 失败不推进 state。最终 QEMU SHA256 为
`ef88746915960fe26a275cccfefcbb506cbc0f7d322747faad81a4a0916661cd`。

`ReorderProxy` 在两个方向均已通信后暂存一帧 left→right datagram，收到下一
帧后先发第二帧再发 held first frame。双向各转发 `58` 帧、`reordered=true`、
held frame released、proxy error 0；receiver `replay_drops=0`，StopWatch/
StickS3 peer payload 为 `57/58`。duplicate replay 负控仍令 StickS3 RX `59`
且记录一次 replay drop；Core2↔StopWatch encrypted 回归收到 `14/44`。

六个 session 均 `purge=0` 停止、runtime PID 消失并保留 history。该结果
关闭单 peer bounded reordering，`RUNTIME-06` 仍为 `PARTIAL`：multi-peer
replay window、PN wrap/key rotation、guest key-state 写入 bridge、
loss/retry、channel/rate、bit-exact controller、RF/antenna、电气时序和
真机均 `NOT RUN`。见
[证据](evidence/2026-10-29-espnow-external-ccmp-window/README.md)和
[机器摘要](evidence/2026-10-29-espnow-external-ccmp-window/summary.json)。

## 2026-10-29：ESP-NOW stock guest controller key-state

新增 `0080-esp32-espnow-guest-key-state.patch`，SHA256
`c827a3e6e76f591b319379342e099a5cd4ffd086029fb514cb99c61a72e2babc`。
匹配固件的 `mt_set_lmk -> ic_set_key -> hal_crypto_set_key_entry` 路径
确认 classic ESP32 key store 位于 `0x3ff74400`，ESP32-S3 位于
`0x60034400`；entry stride `40` bytes、key data offset `8`，本轮 stock
固件使用 extended slot `24` 和 valid bit `0x01000000`。

模型只在 16-byte LMK 全部写入且 valid bit 已置位后启用 external bridge
key。runtime-env 不包含 PMK/LMK。StopWatch↔StickS3 与
Core2↔StopWatch 的正控均为 PASS，双端 `guest_key_ready=1`，正常 peer
payload 分别为 `58/59` 与 `15/45`。不同 guest LMK 负控中双端均
`EXPECTED_DROP`、`rx_packets=0`，MIC failure 发生于 RX DMA 前。

delete/re-add/modify 后把双端 LMK 轮换为新共享值，两设备对的
pre-sync、peer 恢复和 post-resume 均为 true；每个 session 观察到四次
key-ready 状态和两次 clear，证明 replacement 重置 active key/replay
state 而不是继续沿用旧 fixture。十二个 session 均 `purge=0` 停止、
runtime PID 消失并保留 history。最终 QEMU SHA256 为
`d2f25608dce3d4b4ff8951b1b89a778d52a57286bfb460f7959ddec696e48796`。

该结果关闭单 peer stock guest key-state 和 key rotation，`RUNTIME-06`
仍为 `PARTIAL`：multi-peer key routing/每 peer replay window、
3+ peer fabric、PN wrap、loss/retry、channel/rate、bit-exact controller、
RF/antenna、电气时序和真机均 `NOT RUN`。见
[证据](evidence/2026-10-29-espnow-guest-key-state/README.md)和
[机器摘要](evidence/2026-10-29-espnow-guest-key-state/summary.json)。

## 2026-10-29：ESP-NOW 三 guest shared-LMK fabric

新增 `0081-esp32-espnow-peer-fabric.patch`，SHA256
`b86d3561d503139a4ae8dbda6c4699534b478113ff681784012e562d4d8cf7ca`。
该 patch 在 QEMU 二进制
`de8d5b07a31861bf3aae0731ad21da772753cb1bd1388f5b678bdcf23a0ef9b1`
上增加 opt-in 三 guest UDP broker。每个 controller 在 CCMP 前写入自己的
synthetic public MAC；broker 在 MIC 后不改写 transmitter/address3，RX
保留 broker 提供的 source peer。replay window 按 authenticated
source-peer MAC 分片，共 8 个 slot、每 slot 64 frame，且 MIC 验证先于
replay 判定。

StopWatch、StickS3、Core2 三端正控均为 PASS：`peer_count=[2,2]`，
各自收到另外两个 peer 的 payload；TX/RX 分别为 `844/854`、`828/862`、
`880/352`，各自 `guest_key_ready=2`、`replay_drops=0`。broker 观察到全部
六个 directed path，错误为 `0`。

replay 负控复制一帧真实 forwarded frame 后，StickS3 精确记录
`replay_drops=1`，StopWatch 与 Core2 精确为 `0`，三方正常 payload 仍 PASS；
runner 对这组 `1/0/0` 结果做强断言。
两轮各三个 session 均 `purge=0` 停止、runtime PID gone、history retained。
首轮“CCMP 后改写受 AAD 保护的地址”实现造成 MIC 全失败，已丢弃；最终版本
改为加密前注入 public MAC。readiness 也从独立 barrier 改为与持续 payload
交换共用同一个循环，避免慢启动 Core2 错过其它两端。

该结果关闭 `RUNTIME-06` 的三 guest shared-LMK fabric、per-source replay
window 和 fabric replay 负控。任务仍为 `PARTIAL`：per-peer LMK routing、
PN wrap、loss/retry、channel/rate、bit-exact controller、RF/antenna、
电气时序和真机均 `NOT RUN`。见
[证据](evidence/2026-10-29-espnow-peer-fabric/README.md)和
[机器摘要](evidence/2026-10-29-espnow-peer-fabric/summary.json)。

## 2026-10-29：ESP-NOW per-peer LMK routing

新增 `0082-esp32-espnow-per-peer-key-routing.patch`，SHA256
`5405d62fe3e4b6fff9cd1b41129b32d296a56b8a288e927ac19e1770acb88a6c`。
匹配的 UIFlow2 ELF 显示 stock `wDev_Insert_KeyEntry` 把 6-byte peer
address 复制到 key descriptor bytes `3..8`，`hal_crypto_set_key_entry`
再写成 controller key entry 的前 6 bytes；LMK 仍在 entry offset `8`。
classic ESP32 与 ESP32-S3 的 stock 函数分别位于 `0x402e2178` 和
`0x42182fc0`。

最终 QEMU 二进制
`9c36bb527f441b65acc16aff09728ae66e98ea19957a42fbc8bc087d52c9e5e0`
只在 valid、8-byte metadata 和 16-byte LMK 全部写入后使用 slot。fabric
TX 按 receiver peer、RX 按 frame transmitter peer 选择 guest key，每个
slot 保存独立 TX PN；replay window 继续按 source peer 分片。

shared-LMK 回归仍为三端全路径 PASS。pairwise 正控使用 A-B、A-C、B-C
三个不同 LMK，三端均把两个 peer 写入 extended slots `23`、`24`，
`guest_key_ready=2`；六条 directed payload 全部交付。TX/RX 分别为
`848/878`、`856/874`、`900/370`，全部 `replay_drops=0`。

cross-wire 负控只把 role B 对 A 的 LMK 改成 B-C 的 LMK。broker 仍转发
全部六条路径，但 A/B 对错误 peer 的 source 和 payload match 均为 `0`，
A-C/B-C 保持 PASS；A/B trace 分别出现 `470/472` 次 peer-key/CCMP
validation failure，Core2 为 `0`。runner 同时断言 expected link、source
和 payload 矩阵，不能把普通掉帧误判为该负控 PASS。

direct `guest-key` StopWatch↔StickS3 回归也保持。四条 lane 共 11 个
session，全部 `purge=0`、terminal `stopped`、runtime PID gone、history
retained。ESP-NOW controller/patch contracts 为 `47/47 PASS`，patch
forward/current-source/reverse 均 PASS。

该结果关闭 `RUNTIME-06` 的 per-peer LMK routing 和错误 peer-key
fail-closed 路径。任务仍为 `PARTIAL`：PN wrap、loss/retry、channel/rate、
bit-exact controller、RF/antenna、电气时序和真机均 `NOT RUN`。见
[证据](evidence/2026-10-29-espnow-per-peer-key-routing/README.md)和
[机器摘要](evidence/2026-10-29-espnow-per-peer-key-routing/summary.json)。

## 2026-10-29：ESP-NOW CCMP PN exhaustion and rekey

新增 `0083-esp32-espnow-ccmp-pn-exhaustion.patch`，SHA256
`3e9d54b16b0ec3429347bb9d36efe96755935e2cff3d045cf3af3b0b82adcfa9`。
48-bit CCMP transmit PN 到达 `0xffffffffffff` 后 fail closed，不再编码
zero PN。测试 seed 从上限前 64 frame 开始，最终 QEMU 为
`1f3bb7dbbf4b2b32f29e065c02dbe20f08188518c01bd39ec5eb00c724574262`。

StopWatch↔StickS3 先完成 encrypted barrier，再发送 128 个 burn frame。
两端各记录 65 次 PN exhaustion、0 replay drop；安装新 LMK 后 PN 从
zero 重启，post payload 分别为 `164/163`。相同 LMK 重写负控中
`guest_key_ready=1`，各自记录 `183` 次 exhaustion、0 replay drop，
post payload 均为 `0`，证明只重写相同 key 不会绕过 PN 耗尽。

实现同时修正 key 更新顺序：metadata/LMK 和 valid bit 全部完成后才
reconcile；相同 metadata/LMK 保留 TX PN 与 replay state，只有实际 key
变化才清 replay 并从 zero 开始。shared-LMK、pairwise 正控和 B/A
cross-wire 在最终 QEMU 上全部重绑 PASS。13 个 session 均 `purge=0`、
terminal `stopped`、runtime PID gone、history retained。ESP-NOW
controller/patch contracts 为 `51/51 PASS`，patch
forward/current-source/reverse PASS。

该结果关闭 `RUNTIME-06` 的 PN exhaustion 和 new/same-LMK rekey 语义。
任务仍为 `PARTIAL`：loss/retry、channel/rate、bit-exact controller、
RF/antenna、电气时序和真机均 `NOT RUN`。见
[证据](evidence/2026-10-29-espnow-ccmp-pn-exhaustion/README.md)和
[机器摘要](evidence/2026-10-29-espnow-ccmp-pn-exhaustion/summary.json)。
## 2026-10-29：剩余 Xtensa 浏览器准入与独立 engine Worker

同步原仓库 main 至 `96ee9f33` 后，46 层 C/QEMU 固定源码完整重建；WASM
SHA256 `9d2db548e3f4b2622d9839b57311cbab7244775a492d4fff660140c19f68ac93`，
lock SHA256 `b39bba5b0dc1aaa51ac9f98210cbaca3ed324db3251d0a3cf2da3bf281a5ef4f`。
新增六板与既有四板、CoreS3 两例在同一最终公开导出独立执行 11 例，313 项
检查全过；串口/帧/输入/暂停恢复及 engine+五 pthread 在 iframe 保留时退出
均取自各自同一 guest。正式 Pages 新部署、物理硬件与原生全矩阵为 NOT RUN。

实际 C 负控分别保留 QAPI 枚举错误、迟到 systimer deadline 重放及 TCA
未读 FIFO 被 W1C 吞掉 K_INT；45 层 Cardputer N-release 失败不被新 PASS
覆盖。PaperMono 使用固定 raw-point workaround，逻辑校准与 StopWatch 触摸
偏差仍开放。平台 1505 项检查 OK（10 skipped）；最终链接/源码/报告/固件
身份、浏览器序列和边界见
[有界证据](evidence/2026-10-29-wasm-remaining-xtensa/README.md) 与
[机器可读摘要](evidence/2026-10-29-wasm-remaining-xtensa/summary.json)。

## 2026-10-29：ESP-NOW loss/retry、channel/rate 与长稳

新增 `0084-esp32-espnow-loss-channel-rate.patch`，SHA256
`91ef766541a9802336d5a3efaefc38fd28f5d7ea55107e605e2ec37fdf2594fc`。
bridge 在真实 action frame 外增加 8-byte、versioned channel/rate
envelope；RX 在 action/CCMP/DMA 前拒绝截断、错误 magic/version、异 channel
和不支持的 rate，并把 authenticated frame 的 channel/rate 写入 controller
RX metadata。最终 QEMU 为
`54e7a7f7cd0ff6f5a1d6343c06563388f49c2b0abbca4cafb850876e57ed1254`。

第一次测试将 `add_peer(channel=6)` 用在仍连接 channel 1 AP 的 stock
driver 上，guest 自身以 `Peer channel is not equal to the home channel`
拒绝发送。最终路径先完成 Wi-Fi 基线，再 disconnect/re-activate STA 到目标
home channel，随后使用 stock ESP-NOW。该失败 control 保留，不能视为 bridge
PASS。

受控 UDP proxy 在双向流量建立后丢弃 StopWatch→StickS3 前两帧；应用重试后
两端 payload PASS，发送各 `58` 次且没有 `OSError`。channel 6 正控两端
`58/58` TX/RX，channel 1↔6 负控两端各 `40` 次 channel drop 且正常 RX
packet 为 `0`。channel 6 上以 11/24 Mbps 混合发送，接收端 metadata
互见对端 rate。60 秒 soak 中 A/B TX/RX 为 `528/527` 和 `527/528`，
payload matches 为 `526/527`，duplicate、unexpected source 与 TX error
均为 `0`。

direct encrypted、replay proxy、reorder proxy、shared/pairwise 三 guest
fabric、B/A cross-wire 与 PN exhaustion/new-LMK rekey 在最终 QEMU 上全部
重绑 PASS。全部最终 session 使用 `purge=0`、terminal `stopped`、runtime
PID gone、history retained。patch forward/current-source/reverse PASS。

该结果关闭 `RUNTIME-06` 的 virtual-device loss/retry、channel/rate 与长稳
边界。bit-exact controller/baseband、RF propagation、天线、实测 channel/rate、
电气时序和 physical hardware 仍为独立 `NOT RUN`。见
[证据](evidence/2026-10-29-espnow-loss-channel-rate/README.md)和
[机器摘要](evidence/2026-10-29-espnow-loss-channel-rate/summary.json)。

## 2026-10-29：Worker claim response-loss idempotency

Device Service API/OpenAPI 升至 `1.49.0`。durable queue 的 claim 增加可选
`claim_idempotency_key`；持久内容只包含 worker identity + key 的 SHA256、
request hash、job ID 和 lease ID，不保存 raw key。相同 request 在当前 lease
仍有效时返回原 job/lease 和 `claim_idempotent_replay=true`；相同 key 对应
不同 request 返回 `409 claim_idempotency_conflict`，lease 过期或 ownership
改变返回 `409 claim_idempotency_stale`。空 no-job poll 不持久化。

真实 HTTP fixture 注册 worker、提交两个 job，并让真实 `WorkerAgent` 发起
claim。第一次服务端已签发 lease 后，客户端故意丢弃成功响应；WorkerAgent
自动重注册并复用同一 key 重试，获得原 job/lease。同一 state directory
重启后，直接 replay 仍为同一 job/lease，第二个 job 保持 queued；新 key
才领取第二个 job。`jobs.json` 不含 raw key、mode 为 `0600`，service log
不含 token。11 项 checks 全部 PASS；平台为 `1529 OK + 1 skipped`，
runtime coverage、peripheral catalog、QEMU profiles、project snapshot、
compileall 与 Node contracts 均 PASS。

该结果关闭 `NET-04/SVC-01` 的单 control-plane claim response-loss 子缺口；
物理跨主机 executor/reattach、跨主机 queue/session/evidence 持久存储、
真正网络黑障矩阵、QEMU guest/controller 状态和 worker 未拥有的外部 side
effect 仍 `NOT RUN`。见
[证据](evidence/2026-10-29-worker-claim-idempotency/README.md)和
[机器摘要](evidence/2026-10-29-worker-claim-idempotency/summary.json)。

## 2026-10-29：Lease-bound remote evidence store

Device Service API/OpenAPI 升至 `1.50.0`。认证 worker 的 evidence ZIP
现在按 job、live lease、worker instance 和 generation 派生 immutable
evidence ID，并以 ZIP SHA256 内容寻址保存。`POST /evidence` 只接受
`application/zip`；`X-M5-Job-Id`、`X-M5-Lease-Id` 和
`X-M5-Evidence-SHA256` 联合绑定 request。相同 bytes/lease 的响应丢失重试
返回原 evidence ID；不同 bytes 返回 `409 evidence_conflict`。metadata 和
content 使用 `0600` 原子文件，默认保留 90 天，并进入 `/storage` 和
`/storage/prune`。

真实 HTTP fixture 使用 2 MiB ZIP：WorkerAgent 第一次已成功上传后被注入
响应丢失，自动重注册并复用同 bytes 重试，返回原 evidence ID。control-plane
同 state directory 重启后，metadata 与 content 的 SHA/bytes 仍一致；不同
bytes 被 409 拒绝。job result 必须同时携带正确 `evidence_id` 和
`evidence_sha256`，错误 evidence ID 在终态写入前 409 fail closed。queue
和 metadata 不含 raw ZIP payload，service log 不含 token。17 项 checks
全部 PASS。平台套件 `1535 OK + 10 skipped`，Node contracts、runtime
coverage、peripheral catalog、QEMU profiles、project snapshot、OpenAPI/YAML、
compileall 和 `git diff --check` 均 PASS。

该结果关闭 `NET-04/SVC-01` 中 single control-plane 的 lease-bound evidence
response-loss/persistence 子缺口。物理跨主机 executor、共享文件系统之外的
queue/session/evidence 复制、对象存储持久化、QEMU guest/controller 状态、
外部 side-effect fence 和 physical hardware 仍 `NOT RUN`。见
[证据](evidence/2026-10-29-lease-bound-evidence-store/README.md)。

## 2026-10-29：Core2 post-reset teardown

`run_service_teardown.py --stop-mode after-reset` 扩展 `CORE2-02` teardown
覆盖。每个 attempt 先在 ready session 内冻结 frame、32-node QOM、WiFi/
public DNS/HTTP、外部 NUS GATT、serial、pcap 和 evidence ZIP，然后向同一
session 发出 guest `system_reset`。0.25 秒 reboot-in-flight 窗口内 QEMU PID
和 session 仍为 running，HTTP/BLE companion 仍归属该进程；随后 stop 返回
`stopped` 且无错误，HTTP/BLE companion 为 terminated，BLE/QEMU PID 消失，
worker active lease 归零，下一 attempt 仍能创建并完成同样 workload。

三个独立连续 attempt 均 PASS，23/23 checks 每轮一致通过。输入在首次 lease
前绑定，运行期间 firmware/ELF/QEMU/runners 无漂移：

- firmware `c3eaa35b…`；
- ELF `5bec056b…`；
- QEMU `54e7a7f7…`；
- HLI `45/45`、36 events、9 ACLs、errors/queue/reset/panic 为 `0`；
- frame SHA256 `fa98d48f…`，QOM `32` nodes，pcap/evidence 每轮保留。

该结果只扩展 virtual-device teardown 模式，不证明 bit-exact controller/
baseband、物理 cache/PSRAM timing、RF、跨主机迁移或真机。见
[证据](../tests/uiflow2/core2_native_hci/evidence-2026-10-29-core2-post-reset-stop-recovery-3x.json)。


### 2026-10-29 / Atom 与 Stick 主机内部运行接入

AtomS3、AtomS3 Lite、StickC、StickC Plus SE 和 Plus2 各自原厂固件的原生
显示/LED、输入及选定外设通过；五款纯浏览器独立验收 117/117，WASM
`ab1691d6…`；AtomS3/Plus2 同 VM live Run/异常恢复 22/22。正式 native42
`70bd68ee…` 的既有完整矩阵 68/68；同步 main（PR #28/#29）后平台与干净克隆各
1566 项（1556 通过、10 条件跳过），Node/来源门禁通过；API 1.51 的两板
显式 default-deny ACL 16/16 与 capacity 正控通过。五款加入默认公开准入，
共 15 款；公开导出 16 case 为 439/439，18 次正常停止、104 个 Worker target
全部关闭，无 fallback、服务请求或页面错误。随后同步 main@84bc88ed（PR #31），
其两阶段退出检查按 CoreS3、AtomS3、Lite 三类测试器补验 70/70，旧 16 case
的准确测试器哈希单独保留；最终导出只修正十个目录 JSON 的限制说明，
其余 2101 个资产不变，已执行与最终元数据 manifest 分别记录。
经典 Atom 三款启动失败、原 StickC Plus 缺镜像、Dial 旋钮 deferred GPIO
callback 状态合并继续开放；50ms 操作点不作为修复。所有结果为 virtual-device，
未部署 Pages、未执行物理硬件验证。详见[限定结果与哈希](evidence/2026-10-29-expanded-hosts/README.md)。

## 2026-10-29：Device Service runtime ACL

Device Service API/OpenAPI 升至 `1.51.0`。新增外部 operator-owned runtime
ACL：policy 文件必须是最大 64 KiB 的 regular UTF-8 JSON，不允许 symlink；
unknown field/device/operation/entrypoint/path 在 listener 启动前拒绝。配置后
按设备对 `serial.read`、`input.write`、`guest.reset`、`program.read`、
`program.execute`、`program.interrupt`、`filesystem.write` 和 `flash.read`
执行 allowlist，未声明 device/operation 默认 deny；未配置时返回
`NOT_CONFIGURED` 并保留历史 local-control 兼容行为。

program execution 另行要求 `main.py`/`main.mpy` 入口点 allowlist。完整 package
在执行前逐个检查 canonical guest path，deny 优先，支持 exact path 和 trailing
`/` directory prefix。实际 HTTP runner 使用 production `RuntimeACL`、
`DeviceService`、`DeviceSession`、Handler 和 package preflight，确认 session/
capacity 暴露 semantic policy SHA256；program status 正控可读；program
execute、serial read、input、reset、flash read、program interrupt 和 denied
package path 均在 console/QMP/flash I/O 或 revision 发布前返回
`403 runtime_acl_denied`。denied operation 写入 policy-bound event，allowed
package 路径到达预期的 unavailable-console gate；snapshot/evidence 对 denied
program、serial/log 和 flash 数据显式脱敏，serial marker wait 也不能绕过
read ACL；无效 policy 由 CLI 在 listener 启动前拒绝。真实服务进程还完成
有效 SIGHUP 换 policy hash，以及后续无效 SIGHUP 保留旧 policy 的负控。
23/23 checks PASS。

该结果是 `host-runtime validation`，不是固件 guest filesystem ACL。任意 native
firmware 运行后的文件权限、guest 对 ACL 的强制执行、QEMU 沙箱、guest
quiescence 和 physical hardware 仍为 `NOT RUN`；`FW-01` 继续保留完整许可/
法律审批和 guest filesystem 权限范围。见
[证据](evidence/2026-10-29-runtime-acl/README.md)和
[机器摘要](../tests/firmware/evidence-2026-10-29-runtime-acl.json)。

## 2026-10-29：Core2 for AWS ATECC608 and DMA command phase

新增 `0085-core2-atecc608.patch`，SHA256
`797420fcb1b487f06e8e5fa1cec746ec0fd47a2316f18d10fd28e928c0872059`。
Core2 machine 在 board I2C bus 的 7-bit address `0x35` 增加 ATECC608A
slave，实现 wake/idle/sleep、CryptoAuthentication count/opcode/parameter/CRC
framing、config/lock-word Read、Info revision 和 CryptoAuthLib `0x8005`
CRC16。fixture 使用 locked deterministic config、revision `00 00 60 02`
与 zero-filled data zone，不含生产 key 或证书。

同一公开 `Core2_For_AWS` artifact
`22ee8c0f5d3c9640be370cb1a89496ed265b685d573b0e41d62320cf6288ff3a`
经 service 归一化为
`104062aa0e6f52470f0c7f409d202af5d2dad5c3e5ee8f7e65815508a512ef3c`。
最终 QEMU `a802d6a358b6bccb1e9d856b6179ca7245101751a627b7b6f3ddadc3a73fb5b0`
通过真实 `/api/v1` 连续三个独立 session：

- 串口从 `atcab_init returned f0` / `abort()` 推进到
  `atecc608: ok: 60 02`；
- 跟踪命令为 32-byte config Read、lock-word Read 和 Info；
- 三轮 live frame 均为 `320x240`、`76,800` nonblack pixels、`160`
  colors，frame SHA256 均为 `f3739940…`；
- evidence ZIP 有效，全部以 `purge=0` 停止，history 保留、QEMU PID
  消失且 worker lease 释放。

同一 guest 暴露的 classic ESP32 DMA link-start 分段写入和 DC command/data
分类也在 `0085` 中修复；否则初始化命令会被当作像素数据，应用没有可见帧。
该结果关闭 `RUNTIME-04` 的 bounded virtual-device 初始化/identity/应用帧
门禁。样本仍因独立 BMI270 错误保持 `PARTIAL`；ECDSA 生成/签名、生产
slot/trust root、side-channel、电气和 physical hardware 为 `NOT RUN`，
Core2 legacy `RUNTIME-03` 不继承。见
[证据](evidence/2026-10-29-core2-atecc608/README.md)、
[机器摘要](evidence/2026-10-29-core2-atecc608/summary.json)和
[runner](../tests/firmware/core2_atecc608/run_service.py)。

## 2026-10-29：Unit Relay/Relay2 hard-reset 输出边界

新增 `0087-unit-hard-reset-output-boundary.patch`。共享 ESP32/ESP32-S3 GPIO
hold reset 现在先清寄存器并建立复位后route/电平，再通知 reset observer，
最后才通过既有 output listener/IRQ 发布变化；Relay/Relay2 从实际post-reset
pad重定previous level并清零transition。顺序保证 high→hard-reset-low 不会
被记成新的 guest edge，Unit-local reset与GPIO reset无论先后都保持同一基线。

同一 AtomS3R UIFlow2 guest `ab4dd742…` 在 pre-fix QEMU `9aca9a8d…` 与
fixed QEMU `e318b2b7…` 上做 A/B。pre-fix单Relay reset后transition仍为`2`，
Relay2仍为`1/1`；fixed reset观测为单Relay `0`、Relay2 `0/0`，随后
gpio-1由`0/0`到`1/0`，gpio-2再到`1/1`。fixed/pre-fix每路均在停止前请求
evidence并以`purge=0`停止；fixed Relay2证据SHA256为`67acff27…`，pre-fix
为`cc259eff…`；fixed/pre-fix单Relay分别为`6ac5a022…`与`91b17622…`。

为使该Unit runtime能从干净源重建，同一轮在
`patches/qemu-unit-runtime/0003`–`0006` 增加 `0065/0066/0069/0070` 的窄范围
forward port；历史Core2诊断patch保持原字节。新源码 receipt、forward/reverse
apply与完整 `xtensa-softmmu`构建均通过；最终平台回归为
`1558 tests OK, 10 skipped`，runtime coverage/peripheral catalog/QEMU
profiles/project snapshot均PASS。该结果是
`virtual-device validation`，只关闭Relay/Relay2数字GPIO hard-reset边界；
机械触点、线圈、负载、电气、FlashLight reset、其它Unit及physical hardware
仍`NOT RUN`。见[证据](evidence/2026-10-29-unit-hard-reset-output-boundary/README.md)、
[机器摘要](evidence/2026-10-29-unit-hard-reset-output-boundary/summary.json)和
[runner](../tests/units/run_relay_reset_probe.py)。

## 2026-10-29：Core2 legacy contended-CAS hold intervals

新增 `0086-esp32-legacy-cas-episode-profile.patch`，SHA256
`4e86512c3d19a30c23ffd22824a69fc7d5d2f10d0db5aa7a2e81668090b608f8`。
该 patch 在既有 freeze-only handoff trace 中按 CPU/lock 聚合跨核
`s32c1i` episode，记录失败 attempt、区间时长、最大 attempt gap 和最后
holder CPU；桶与 lock slot 数量固定，overflow 单独计数。首版 episode
采样在 no-I/O translation block 中读取 `QEMU_CLOCK_VIRTUAL`，触发
`Bad icount read` 并终止 VM；最终版本跳过该不安全状态，不改变 guest
指令、CAS 结果、中断、watchdog 或默认调度。

同一 public `UIFlow_Core2 v1.15.4` normalized Flash
`4d2d648bd8707a1789d540366015a1b90dc816b66a04163048626ea29e333ed4`
在 QEMU `0a63c37f…` 上执行两个独立 10 秒 exact-time freeze：

| 控制 | 区间 | 总时长 | 最大 | `0x3ffbf2cc` 区间/时长/最大 | 最大失败尝试 |
| --- | ---: | ---: | ---: | --- | ---: |
| normal WDT | `238` | `9.316534114 s` | `631 ms` | `162 / 6.743534018 s / 482.823328 ms` | `53` |
| WDT-off | `253` | `7.825981502 s` | `581 ms` | `166 / 6.600981470 s / 581.176638 ms` | `65` |

两轮最后 holder 均为 CPU1；normal-WDT 中 `0x3ffb7ab0` 另有 `31`
个区间，累计 `2.559000096 s`、最长 `631 ms`。因此主锁预算来自多轮失败
CAS 形成的长持有区间，而不是孤立单次碰撞，且关闭 WDT 不会消除该模式。
所有 session 均以 `purge=0` 停止、history 保留且 QEMU PID 消失。

BIN 指令/控制流与 public `m5stack/esp-idf` v3.3.5 commit
`03810c4a065a1ecdd24a803b2c9dc4e834c7dab5` 对比：`0x3ffbf2cc`
对应 `xTaskQueueMutex`，主要 waiter 是 `xTaskIncrementTick` 和
`vTaskSwitchContext`；`0x3ffb7ab0` 对应某个 `Queue_t + 76` 的 mux。
这些是 source-structure 匹配，不是 matching application ELF/MAP 的
符号查找。

对既有 default-off failed-CAS yield 再做 10/15 秒 episode A/B：

| 控制 | 区间 | 总时长 | `xTaskQueueMutex` | `Queue_t+76` |
| --- | ---: | ---: | ---: | ---: |
| 10 s baseline | `253` | `7.825981502 s` | `6.600981470 s` | `1.133000000 s` |
| 10 s failed-CAS yield | `64` | `1.400290688 s` | `0.446291456 s` | `0.953999232 s` |
| 15 s baseline | `597` | `6.090325855 s` | `5.236325055 s` | `0.825000736 s` |
| 15 s failed-CAS yield | `101` | `5.383785888 s` | `0.849786112 s` | `4.533999776 s` |

yield 在 10 秒大幅降低 scheduler-mutex 等待，但 15 秒时总预算转移到
queue mux，episode 总时长仍约 `5.4 s`；既有 normal-WDT reset 边界不变。
因此“yield 完全无效”被修正为“等待重新分配但未闭环”，不能作为产品修复。

该结果只修正诊断并完成 `virtual-device validation`；仍没有 matching legacy
ELF/MAP，不能确认 exact queue object，也不能区分 host-vCPU 调度延迟与
guest 长临界区，也没有证明 Xtensa atomics 语义错误。normal-WDT stage-1
reset、startup UI、setup/REPL、完整应用帧和 physical hardware 仍不通过，
`RUNTIME-03` 保持 `OPEN`。见
[证据](evidence/2026-10-29-core2-legacy-cas-episodes/README.md)和
[机器摘要](evidence/2026-10-29-core2-legacy-cas-episodes/summary.json)。

## 2026-10-29：Core2 contended-CAS RR scheduling attribution

新增默认关闭的 `0088-xtensa-contended-cas-fair-yield.patch`。真实跨核
failed S32C1I 会退出当前 TCG slice，并把单线程 RR 的下一个 quantum 从
`100 ms` 缩短到 `1 ms`；guest CAS、lock owner、`-icount shift=5`、WDT
deadline 和 peripheral data plane 不变。`M5SW_XTENSA_CONTENDED_CAS_FAIR_YIELD`
未设置时保持原调度。

同一 public `UIFlow_Core2 v1.15.4` SHA 和同一 QEMU binary 的 5 秒
WDT-off A/B 中，control/candidate 的 S32C1I 为
`1,070,625→91,465`、跨核 contended 为 `984,964→2,702`、episode
count 为 `212→16`、episode time 为 `2.239772672→1.017736288 s`。
CPU0 freeze PC 从 `0x40087986` 的 handoff-spin 簇移到
`0x400951fe`。SSI `0x05` 为 `2,078→2,086`、`0xBB/64` 为
`2,386→2,394`，说明 Flash 工作类别和进度近似不变。

20 秒 WDT-off 控制仍显示 candidate 降低 CAS
`4,219,480→545,962`、contended `3,700,764→13,758`、episode time
`15.330116502→10.449083200 s`，两轮 SSI 计数完全相同。`100 us`
对照虽然进一步压低 episode time，但 CPU0 仍停在 handoff-spin 簇，
因此保留 `1 ms`。

normal-WDT control 在 `17.249535709 s`、candidate 在
`17.248020126 s` 触发同一 TG0 stage-1 reset；serial 均为
`TG0WDT_SYS_RESET`，均未到 `BOARD NAME`、setup/REPL 或应用帧。
因此该结果证明默认 `100 ms` RR 是跨核 spin 的重要放大器，但没有关闭
`RUNTIME-03`。MTTCG 与当前 deterministic `-icount` 不兼容；移除
`-icount` 后仍复位且不属于可复现验收 lane。见
[调度证据](evidence/2026-10-29-core2-contended-cas-scheduler/README.md)和
[机器摘要](evidence/2026-10-29-core2-contended-cas-scheduler/summary.json)。

## 2026-10-29：FlashLight cold constructor 四host

`run_flashlight_route_probe.py` 在 QEMU `e318b2b7…` 上为 CoreS3、AtomS3R、
StickS3、StopWatch 各创建一个独立 UIFlow-live session，并挂接 U152
Flash/Torch fixture。每个 guest 在同一 PID 依次运行原厂
`FlashLightUnit` constructor、`flash(BRIGHTNESS_100,TIME_220MS,False)` 和
off Run。

四台均在 constructor 后进入可信 `ready-low`：
`output-known/pad-synchronized/gpio-route-supported=true`，没有借用旧高电平
或 host 伪造低读数。原 API 后模型观察到一次上升沿并解出
`100% / 220ms`、`decoded-programs=1`；off Run 后回到 `ready-low`。三次
execution 保持同 PID，未增加 ESP-ROM reboot banner；每轮均在停止前请求
evidence 并以 `purge=0` 停止。

四份 evidence ZIP SHA256 分别为 CoreS3 `23b10c5f…`、AtomS3R
`3e30a300…`、StickS3 `ca96473c…`、StopWatch `5f7ec5b1…`。mounted
`test_flashlight_unit_web.mjs` 使用 CoreS3 actual QOM snapshots 回放真实
controller state，输出 `mounted Web=ACTUAL-QOM-SNAPSHOT`；实时轮询会话
仍 `NOT RUN`。最终平台回归为 `1559 tests OK, 10 skipped`，runtime
coverage/peripheral catalog/QEMU profiles/project snapshot与两项 Web
fixture均PASS。该结果关闭 `UNIT-HOST-37` 的 cold constructor/低基线数字
边界，不关闭动态 S1、EN PWM、完整 OEN/IOMUX、bit-exact 时序、光度/热/
电气或 physical hardware。见
[四host证据](evidence/2026-10-29-flashlight-cold-route-four-host/README.md)和
[机器摘要](evidence/2026-10-29-flashlight-cold-route-four-host/summary.json)。


## 2026-10-29：StackChan Arduino 上传与 S3 NVS 读取错位

同一独立 Arduino NVS 固件在旧 native/WASM 均复现 set/commit 成功但分区
读取偏移 +2，重新打开和复位后 NOT_FOUND。按实际 Flash 模型修正 S3 QIOR
phase 后，新 native `dc98b0fd…` / WASM `8f4e45bc…` 各 8 项通过，三阶段
完整 Flash SHA 跨 runtime 完全一致。三份固定官方 Dance 的上传对照 29 项
通过，但原样 torque=0 不动如实保留；显式开启后实际 UART1/SCS 位置和
3D 关节一致，NVS 零位实际读回。默认示例 v6 的运动/复位/关机 9 项通过，
最终仅调整 PWR 松开提示的 v7 另以 Arduino 上传完成 10 项，包括自然 exit0、
无错误提示和移除 iframe 前 Worker 关闭。Plus2 USB 原 API 睡眠及电池 HOLD
关断 native 13 项通过，正 EXT0、RTC 硅片等价性、其它新 runtime 板型、
完整共享控制器矩阵和硬件均不继承。平台 1590 项、10 skip；四个 validator
通过。详见[有界证据](evidence/2026-10-29-stackchan-arduino-nvs/README.md)。


该轮最终 fork Pages 发布任务 `40870676825` 成功，payload
`f0e11cd365c45289cc3a68a59f3aca05064e5c2b`，源码
`2c1be6919b542cded3f47061953228790a6c369d`，公开 manifest
`eed692b4cbdc23269b86c381737fd726d94b3efb95cac316b3cbb39ac03bae64`。
公网首页/public.js/runtime.json/完整 WASM 的 SHA 全部匹配；本轮未另跑
部署后的线上 guest，不将 HTTP 制品核验表述为公网功能复测。

## 2026-10-29：Core2 legacy IPC/flash handoff stack attribution

在同一 public `UIFlow_Core2 v1.15.4` SHA、same QEMU
`75e7fa97…`、`runtime=qemu-wifi`、`icount shift=5` 和 normal WDT
下，通过三个独立 lease 在 `17.200000 s` 做 bounded register/stack/object
freeze。三次 serial 均为 507 bytes、SHA256 `e9962765…`，没有
`BOARD NAME`、`APIKEY` 或 setup/REPL。

CPU0 分别位于 `0x40087988`、`0x40087984`、`0x4008798e`，寄存器
`A0=0x80088a31`、`A9=0x3ffc7ec8`、`A12=0x3ffbf2cc` 三次一致；
稳定栈帧含 `0x400889c4`、`0x40087950` 和 `0x800840a0`。BIN 控制流与
public ESP-IDF `cache_utils.c`/`ipc.c` source shape 匹配为
`spi_flash_op_block_func` 等 complete flag，并由 `ipc_task` 分发；
CPU1 三次 PC 分别 `0x40084312`、`0x4008448a`、`0x40095c5c`，另一次
捕获到 `xQueueGenericSend` 的 `A0=0x801ec834` IPC 返回点。

该结果再次拒绝双核永久 deadlock：CPU0 在每个 flash 操作的 block callback
中等待，CPU1 继续推进跨核 IPC 和启动工作。由于没有 matching private
legacy ELF/MAP，函数名只作为 BIN-bound source-shape 结果，不作为 exact
linker symbol。

同时修正诊断解释：默认 trace 每 1024 个 event 才保留一条，
`transaction-begin` 与后续采样 `transaction-end` 不能配对。runner 新增
`--trace-sample` 并在每个 snapshot 记录有效值；2 秒 `sample=1` 控制得到
13 个 begin、13 个 end、11 个 receive-data，13 对 begin/end 全部为同步
`0 ns`，从而排除“单个短 Flash 命令事务耗时约 0.4 秒”的误读。

normal-WDT reset、startup UI、setup/REPL、非空应用帧和 physical hardware
仍未通过，`RUNTIME-03` 保持 OPEN。下一步应直接量化 per-flash-operation
CPU0 park time 和 CPU1 boot phase，而不是继续猜测匿名 vtable。见
[证据](evidence/2026-10-29-core2-ipc-handoff-attribution/README.md)和
[机器摘要](evidence/2026-10-29-core2-ipc-handoff-attribution/summary.json)。

## 2026-10-29：Core2 legacy flash handoff episode budget

`0089-xtensa-handoff-pc-trace-io-boundary.patch` 修复 BIN-bound PC trace
在 no-I/O translation block 中读取虚拟时钟导致的 `Bad icount read`。匹配
PC 的 TB 现在通过 `translator_io_start()` 结束，helper 同时保留
`can_do_io` fail-safe。pre-fix control 在约 `2.351 s` 直接终止；修复版
QEMU `7d9b1f43…` 完成两次 50 秒 wall-time、normal-WDT 运行。

两次运行都在约 `17.25 s` 触发 `TG0WDT_SYS_RESET`，reset 前分别完成
`12,645/12,693` 个完整 handoff。CPU1 `spi_flash_op_block_func` wait：

| run | total | mean | p50 | p95 | max | reset budget |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| 1 | `9.851852864 s` | `779.110 us` | `782.400 us` | `813.312 us` | `6.655552 ms` | `57.1%` |
| 2 | `9.828771008 s` | `774.345 us` | `781.824 us` | `804.704 us` | `6.781792 ms` | `57.0%` |

“complete 到下一次 block wait”另占 `5.047361117/5.071124609 s`，两段
合计约 `86.4%` reset 预算。最大单次 wait 始终小于 `6.8 ms`，而累计
episode 频率约 `733-736/s`。因此当前不支持“某个 handshake 永久或长时间
不返回”的解释，下一优化入口是正常 handoff 周期的频率或累计成本。

两次 serial 都没有 `BOARD NAME`、`APIKEY`、setup/REPL，302-byte frame 仍为
同一黑帧 SHA。该结果是 diagnostic tooling fix 加 virtual-device 预算归因；
`RUNTIME-03`、startup UI、非空应用帧、物理 cache/Flash timing 和真机仍
`OPEN/NOT RUN`。见
[证据](evidence/2026-10-29-core2-handoff-episode-budget/README.md)和
[机器摘要](evidence/2026-10-29-core2-handoff-episode-budget/summary.json)。

## 2026-10-29：SVC-03 首批无状态解析边界

完成 `SVC-03` 的第一个无语义移动：`ServiceError` 移到
`platform/tools/device_service_errors.py`；`parse_int`、`parse_size`、
`parse_capture_pcap`、`is_sha256`/`_is_sha256` 移到
`platform/tools/device_service_parsing.py`。`device_service.py` 继续
re-export 同名对象，因此现有调用方和公开导入路径不变。

新增 `test_device_service_parsing.py` 锁定：

- `ServiceError` 的 code/message/status/extra 与 `payload()` 结构；
- decimal/prefixed integer、size、pcap bool-only parser 行为；
- lowercase 64-hex SHA256 契约；
- `device_service.py` 与解析模块的 symbol identity。

该步骤没有修改 `/api/v1` 路由、错误码、session JSON、evidence ZIP、
历史恢复或运行时参数；也没有改 store、adapter、状态机或 orchestration。
`SVC-03` 继续 `进行中`，下一项是继续提取其余请求解析、运行参数构造和
设备规格加载。

## 2026-10-29：SVC-03 runtime boundary 与 Core2 unified stability

`SVC-03` 继续按无状态边界拆分：`device_service_runtime.py` 接管
`PRIVATE_RUNTIME_ENV`、QEMU PSRAM runtime policy、
`runtime_psram_mismatch()` 和 `redacted_runtime_env()`；`device_service.py`
保留 same-object re-export。新增 `test_device_service_runtime.py` 锁定
Core2 native 8 MiB QOM policy、普通/缺失/非法 memory、mismatch payload、
私有 runtime env 脱敏和 public symbol identity。

目标 unified lease 暴露出两个 service harness 问题：

- profile QOM 注入曾固定等待 20 秒，短于 Core2 的 session readiness；
  现在跟随 `self.ready_timeout`，Core2 unified/native profiles 默认 180 秒；
- unified external peer 在订阅后只等待 2 秒便写 GATT。慢 guest 已执行
  Python RX handler，但 TX path 尚未稳定时，peer 会报 notification timeout。
  共享 unified write delay 现在为 10 秒，reconnect per-cycle budget 同步
  调整为 16 秒。

正确合成的 firmware `c3eaa35b…`、matching ELF `5bec056b…`、最终 QEMU
`568079f3…` 与当前 service hash 上，`core2-native-hci` 三个独立 lease
均为 PASS：WiFi DHCP/HTTP、公网 DNS/HTTP、Bumble NUS discovery/subscription/
write/`ACK:M5_CORE2_UNIFIED`、3,888-byte 同 SHA frame、32-node QOM、
8 MiB effective PSRAM、HLI `45/45`、36 events/9 ACLs、零 errors/queues/
drops、pcap、manifest、ZIP、stop 和清理完整。旧 QEMU `54e7a7f7…` 的同一
10 秒 settle 也为 `3/3 PASS`，用于排除单 QEMU binary 偶然性。

全量 platform 为 `1581 PASS + 1 skip`；runtime coverage、peripheral catalog、
QEMU profiles、snapshot、Ruff `E9/F`、compileall 和 diff check 均 PASS。
全部为 virtual-device validation；物理硬件、RF、BLE 安全/配对、bit-exact
controller 和 Core2 legacy `RUNTIME-03` 不继承。见
[证据](evidence/2026-10-29-svc03-runtime-boundary/README.md)和
[机器摘要](evidence/2026-10-29-svc03-runtime-boundary/summary.json)。

## 2026-10-29：Core2 legacy handoff issuer 与 phase 归因

在 `0089` 的 icount-safe PC trace 上增加 `0x40093b57` fast-read issuer 和
`0x4006222c` ROM status-read issuer，并把它们绑定到每个 initiator handoff
区间。30 秒 wall-time normal-WDT 控制到达约 `10.97 s` virtual，记录
`8,234` 个完整 episode：

| episode 内容 | 数量 | 总等待 | mean | p50 | max |
| --- | ---: | ---: | ---: | ---: | ---: |
| 一条 fast read + 一条 status read | `6,806` | `5.857184128 s` | `860.591 us` | `891.776 us` | `1.1048 ms` |
| 无这两类 issuer | `1,342` | `1.192171392 s` | `888.354 us` | `887.904 us` | `4.750784 ms` |
| 仅 status read | `48` | `0.042949728 s` | `894.786 us` | `888.832 us` | `1.020256 ms` |

无 Flash 命令的 episode 成本与 64-byte fast-read episode 基本相同，排除
数据长度/单一 Flash 命令为主要预算。随后在 initiator source-shape 路径
加入内部 PC，`1,974` 个完整 episode 的平均 phase 为：

- `0x40087a25 -> 0x40087a31`（initiator 经 IPC source shape 返回）：
  `615.595 us`；
- can_start poll exit：`2.181 us`；
- vTaskSuspendAll source shape：`1.322 us`；
- priority change source shape：`34.083 us`；
- 两级 cache-disable source shape：`101.104 + 52.053 us`；
- block wait 到 complete setter：`63.733 us`。

因此下一次修改应针对跨核 IPC handoff/wakeup 延迟，或减少每次读都触发一次
handoff；不是继续调 Flash 数据面。两个负控也已排除：
`100 us` contended-CAS RR quantum 和临时 `can_start` immediate-yield
都没有降低 block wait 或 reset 边界，未保留代码。

所有名称仍是 BIN-bound source shape；normal-WDT startup、UI、REPL、非空
帧、物理 cache/Flash timing 和硬件仍 `OPEN/NOT RUN`。见
[证据](evidence/2026-10-29-core2-handoff-issuer-phases/README.md)和
[机器摘要](evidence/2026-10-29-core2-handoff-issuer-phases/summary.json)。

## 2026-10-29：运动命令、S3 复位与 v7 浏览器后续验证

`0096` 区分重复 torque 与新运动命令，并接受官方 SCSCL 分步恢复角限的有界
中间态；`0097` 恢复 S3 复位后的软件 I²C 探测桥交接；`0098` 实现 IDF 的 S3
RXFIFO 复位脉冲。控制器源码回放均保留旧版失败负控。`0098` 覆盖真实旧 ACK
清除、ReadPos 应答、RX timeout IRQ 和 MMIO 逐字节读取，但尚未证明它是旧轮
孤立 `ReadPos=-1` 的原因。

独立完整构建的 native v7 `6b79beccc37cb5d0…`（53 patch / 130 源文件）完成
单轮 **68/68 PASS、278 checks**，956.3 秒，每项一次、无重试。132 份 guest
源码、两份 runner 和 runtime 哈希未变，205 个证据文件哈希独立核对通过，
本轮 QEMU 残留为零。五项 C6 使用另外冻结的既有完整 13 文件 runtime，不继承
Xtensa 修复。原始 summary SHA256 为
`909e9d1103690301db4ae8306066722bf47117b5e1874bf217042378ba93c707`；
57,776-byte [有界摘要](evidence/2026-10-29-motion-command-followup/peripheral-v7.summary.json)
SHA256 为 `9e4e99ecffda8134ddb5edffd3b5f48d8058d3da552d843c20dd27de52bf44f9`。
最终 Python 平台回归 `1613 tests OK, 10 skipped`，221.490 秒，日志 SHA256
`7e3dec7a73281145ef84da8ba2525d5d67ef1c57f0b52b726d2f2ee3f2fcc7dd`。

WASM v7 `d65cb046b0f759fc…` 为完整 62 patch / 158 源文件构建，本地 v12
manifest `962697a23a4826ab…` 含 2115 个资源、19 public / 0 candidate，
无捆绑固件/ROM、无服务地址。固定该导出的 StackChan SCS、校准/RESET、
生命周期、三段显式扭矩 Dance、原样未开扭矩负控五项严格路径通过。每项都在
`context.close` 之前确认零 live CDP Worker，累计精确 30 个 Worker；UART、
QOM、实际帧和独立几何读回保持同实例绑定。

PWR 正常 DOM 路径实际长按 6011.285 ms 后 guest SHUTDOWN/exit0、iframe0、
五个 pthread 退出且无 banner；但独立 CDP 等待 30 秒仍有一个 engine target，
附着后的常量求值 5 秒超时，完整退出断言 **FAIL**，修复仍在评估。owner
self-close 意图和最终强制 browser cleanup 不授予 PASS。本轮整体保持
**PARTIAL**。四款经典 Atom/Stick 的 v7 默认参考入口见下方独立结果，
不得继承旧 runtime 的本地上传结果。

旧轮 PM1/C6 失败、ReadPos fallback、v7 attempt1 原样 Dance WASM 越界和
旧 PWR 退出失败均保留；后续通过不改写旧结果或证明其原因。实际反向目标间隔
3082 ms 不构成 100 ms guest 中途反向验证；Matrix 空间灯序/IMU 轴向、速度
控制/PWM 机械运动、用户原上传固件及物理硬件均不由以上结果覆盖。见
[证据说明](evidence/2026-10-29-motion-command-followup/README.md)、
[主摘要](evidence/2026-10-29-motion-command-followup/summary.json)和
[StackChan v7 摘要](evidence/2026-10-29-motion-command-followup/stackchan-v7.summary.json)。

## 2026-10-29：Core2 per-vCPU icount fairness budget

`0090-icount-percpu-fairness-cap.patch` 给 multi-vCPU deterministic icount
加入经校验的 per-vCPU virtual-time cap；Core2 的共享 accelerator 配置默认
发送 `M5SW_ICOUNT_MAX_PERCPU_NS=10000`，设置
`M5_CORE2_ICOUNT_MAX_PERCPU_NS=0` 可关闭。该变更只限制 vCPU 切换预算，
不改变 guest 指令、WDT 配置、Flash/SSI 数据面或外设模型。

最终 QEMU `568079f3…`、同一 public legacy 固件 SHA、`runtime=qemu-wifi`、
`icount shift=5` 和 normal WDT 的同 trace A/B：

| 指标 | uncapped | `10 us` cap |
| --- | ---: | ---: |
| CPU1 initiator `can_start → IPC return` mean | `563.667 us` | `56.249 us` |
| peer `spi_flash_op_block_func` wait mean | `728.443 us` | `184.689 us` |
| handoff completed in trace window | `5,783` | `5,607` |
| first TG0 timeout | `7.253607 s` | 未到该 virtual time |

uncapped 运行在 `7.253606495 s` 记录 TG0 stage-0 timeout；capped trace
只到约 `5.39 s` virtual，因此不能把“该短窗未出现 timeout”解释为 WDT 已
修复。独立的 90 秒 wall-time capped 长窗到达 `17.242875841 s` 后仍触发
TG0 stage-1 reset，serial 没有 `BOARD NAME`/`APIKEY`/REPL，frame 仍是
302-byte 黑帧 SHA `57580743…`。

同一最终 QEMU 的 Core2 UIFlow2 设备组为 `6/6 PASS`，默认
`core2-peripherals` case 另行 `1/1 PASS`。因此该结果关闭“双 vCPU icount
固定预算放大正常 IPC handoff”这一调度子问题，并证明候选产品路径无回归；
它不关闭 `RUNTIME-03` 的正常启动、显示、REPL、非空应用帧或物理边界。
见[证据](evidence/2026-10-29-core2-icount-percpu-budget/README.md)和
[机器摘要](evidence/2026-10-29-core2-icount-percpu-budget/summary.json)。

## 2026-10-29：冻结 v12 预览部署

本轮 Pages [workflow](https://github.com/yuyun2000/m5stack-esp-emulator/actions/runs/40892573994)
成功部署 payload `6899687c1fc7208274c03de7fb6cc88218ceb708`。静态源码固定在
`88a41651efadc9f64d70a7f78949d105efb038d9`；后续 `9907eee3…` 另合入
主线 `ed612f3b…`，不将其新增原生 Core2 调度补丁授给冻结 WASM。公网 manifest
SHA256 `962697a23a4826aba73a6cebdd6df65987d903329950eb9e43c3d6b6187bdf88`
与本地一致，另核首页、public/owner 脚本、profile、runtime manifest、完整 WASM
及对应源码包，共八项 HTTP 200/字节一致。仅授予部署与完整性 PASS，不授公网
guest 或硬件 PASS。自然 PWR Worker 清理仍 PARTIAL。见
[部署摘要](evidence/2026-10-29-motion-command-followup/deployment-v12.summary.json)。

## 2026-10-29：经典四板默认参考入口收尾

固定 v7/v12 下，Atom Lite、Matrix、Matrix v1.1 分别在原始门槛内以
236.83/237.51/238.02 秒首轮通过，独立读取原 RMT/USER 和模型 LED，无屏
负控及关闭 context 前 CDP Worker 归零。原 StickC Plus 的相同
`69567208…` 完整固件首次在 240 秒 ready 门槛超时，未到首个应用标记；
不能据此认定 M5.begin 或显示控制器失败。该失败未被覆盖。仅一次独立
480 秒 ready 预算诊断在 189.00 秒完成 ready、BtnA、红绿帧/模型纹理及
正常 Stop，context.close 前独立 CDP 为精确 5/0。复核低于原 240 秒，
不能把原失败归因为预算不足或宣称启动稳定性已关闭。所有测试只使用独立
静态站端口，没有访问用户保留的服务。见
[最终有界摘要](evidence/2026-10-29-motion-command-followup/classic-default-v7.summary.json)。
## 2026-10-30：Core2 legacy boot budget 与 WiFi/UI wait

在 public `UIFlow_Core2 v1.15.4` normalized SHA `4d2d648b…`、最终 QEMU
`568079f3…`、matching VFS、`runtime=qemu-wifi/profile=core2-openmac` 下，
只调整 deterministic `-icount` 与既有 per-vCPU cap。`shift=3` + `1 us`
在 normal WDT 下于 `8.384395696/8.385523896 s` 输出 BOARD/APIKEY，
`14.191426034-14.380873848 s` 执行原厂 boot.py；`shift=2` + `1 us`
提前到 `4.659620404/4.660179256 s` 和 `8.340878020-8.504887849 s`。
两者仍未进入 factory UI，frame 均为 `57580743…` 302-byte black PNG。
默认 `shift=5` + `10 us` 保持 `17.242875841 s` normal-WDT reset 边界，
因此 timing 控制没有作为产品配置修改。

`shift=2` + `1 us` 的两个 WDT-off 控制分别在 15/20 秒停在双核 Waiti
`0x4026306e`，serial SHA 均为
`923380826ceb9be6107e6437dcb690be6a67bdccaade80164ab6537b7f458d0d`；
20 秒快照的最后 Flash/cache sync 为 `9.358926093 s`，SSI/cache counter
不再增长。FRC timer trace 仍记录到 `9.277506536 s` callback，排除全局
timer 停止。

显式 UART 诊断在 guest virtual `9.267433433 s` 捕获
`wifiWebCfg.py:84 _thread_task -> menu/wifi.py:22 -> m5stack_ui.py:526`
的现有等待栈。该输入只用于采样已存在的等待状态，不是产品路径。当前首
阻断因此从 Flash handoff 改为 boot.py 后的 WiFi 配置/UI 生命周期等待；
`RUNTIME-03`、factory UI、REPL 和非空应用帧仍 `OPEN`。全部为
virtual-device validation，真机、RF、物理 cache/PSRAM 和电气边界 `NOT RUN`。
见[证据](evidence/2026-10-30-core2-legacy-boot-to-ui-wait/README.md)和
[机器摘要](evidence/2026-10-30-core2-legacy-boot-to-ui-wait/summary.json)。

## 2026-10-30：Core2 TIMG watchdog feed rescheduling

新增 `0091-esp32-timg-feed-reschedule.patch`。旧模型对每次 watchdog arm
使用 `timer_mod_anticipate_ns()`；该 API 会保留更早的 pending deadline，
因此 `WDTFEED` 将阶段重置到 stage 0 后，旧的 stage-1 deadline 仍可能保留。
新实现改为 `timer_mod_ns()`，只替换 watchdog stage timer，不关闭 WDT、
不修改 timeout/中断配置、不 warp 虚拟时钟。

patch 正向/反向合同、protected-feed 和 status/CAS 回归均 PASS。同一
public legacy 固件 SHA
`4d2d648bd8707a1789d540366015a1b90dc816b66a04163048626ea29e333ed4`
的 `runtime=qemu-wifi` 8 秒虚拟时点产生 `320x240`、`3,651` nonblack pixels、
`36` colors 的 live frame，SHA256 为
`35aedd447284a3e812e6cd9bec3e3167559a50f2c121eb43482dcfc7ab108fcc`。
长窗仍在约 `15.56 s` 触发 TG0 stage-1 `TG0WDT_SYS_RESET`，factory UI、
REPL 和稳定应用帧仍未出现，所以 `RUNTIME-03` 保持 `OPEN`。全部为
virtual-device validation；物理 watchdog/cache/PSRAM 与真机 `NOT RUN`。
见[证据](evidence/2026-10-30-core2-timg-feed-reschedule/README.md)和
[机器摘要](evidence/2026-10-30-core2-timg-feed-reschedule/summary.json)。

## 2026-10-30：Core2 legacy menu after WiFi configuration stub

在包含 classic-panel DMA 修复的 diagnostic QEMU `7d03bb18…` 上，使用
public legacy firmware SHA `4d2d648b…` 的 VFS 诊断镜像
`f4966a4a…`，只把 `wifiWebCfg.config_by_web` stub 为返回 true，不伪造
panel/DMA 像素或 QOM 输入。`runtime=qemu-wifi/profile=core2-openmac`、
`icount shift=2`、uncapped 和 WDT-off 诊断控制下，serial 到达
BOARD/APIKEY、boot.py 与 WiFi stub marker，最终帧为 `320x240`、
`76,760` nonblack pixels、`417` colors，SHA256
`a4f683468cfb9edc70468efaabd23c226abbed7a3cdeaf6a397cab09c52a6078`，
画面包含 UIFlow 标题和 App/Flow/Setup 菜单。

原厂 normalized image 的专用 `wifi` 分区（offset `0xbff000`，size
`0x1000`）为空。stub 绕过真实配置生命周期，因此这是 menu/display
`DIAGNOSTIC_PASS`，不是原厂固件 `RUNTIME-03` PASS。剩余门禁是填充有效
WiFi 配置、运行真实 `wifiWebCfg`/WiFi UI，并在 normal WDT 下稳定完成
startup UI、REPL 和用户应用。全部为 virtual-device validation；RF、
电气和物理硬件 `NOT RUN`。见
[证据](evidence/2026-10-30-core2-wifi-stub-menu/README.md)和
[机器摘要](evidence/2026-10-30-core2-wifi-stub-menu/summary.json)。

## 2026-10-30：SVC-03 network parsing boundary

继续 `SVC-03` 的无状态请求解析拆分。新增
`platform/tools/device_service_network.py`，移动
`parse_network_policy` 和 `parse_dns_cname_records`；`device_service.py`
继续 re-export 同名对象，因此调用方、错误码、implicit endpoint merge 和
bounded CNAME binding 语义不变。

新增 `test_device_service_network.py` 锁定 policy/CNAME 行为及 public
symbol identity。定向 parser `7/7`、network boundary `6/6`、network
focused `90/90` PASS；全量平台 `1,589` 项为 `1,588 PASS + 1 skip`，
runtime coverage、peripheral catalog、QEMU profiles、project snapshot、
compileall 和 diff check 均 PASS。该步骤没有修改 HTTP、network sandbox、
session state、evidence 字段或硬件路径；物理硬件、RF 和电气验证仍
`NOT RUN`。见
[证据](evidence/2026-10-30-svc03-network-parsing/README.md)和
[机器摘要](evidence/2026-10-30-svc03-network-parsing/summary.json)。

## 2026-10-30：Core2 legacy deviceCfg WiFi overlay

Core2 `qemu-wifi` 现在识别 classic UIFlow `deviceCfg` schema、长度和
checksum，并只把请求的 SSID/password 应用到 session-isolated Flash 的
`config` 分区；非匹配固件的字节保持不变，事件只记录 hashed SSID、
base/effective Flash SHA 和 password 是否提供。标准 QEMU
`54e7a7f7…` 的 service 路径记录了 `legacy_wifi_config_applied`，并由
原始 `4d2d648b…` 得到 effective Flash `b30f3014…`；同一 effective
Flash 在 WDT-disabled 诊断控制下渲染真实 `Connecting to myssid` UI
（`320x240`、`75,373` nonblack、`305` colors、PNG SHA
`df9ba184…`）。diagnostic QEMU 的默认 WDT 控制仍到达 BOARD/APIKEY/boot
markers 后触发 `Cache disabled but cached memory region accessed`，黑帧
不变，因此只关闭配置/取证前置，`RUNTIME-03` 保持 OPEN（virtual-device
validation；物理硬件、真实 cache/PSRAM、RF、DHCP 和网络连接均 `NOT RUN`）。
见[证据](evidence/2026-10-30-core2-legacy-wifi-config-overlay/README.md)和
[机器摘要](evidence/2026-10-30-core2-legacy-wifi-config-overlay/summary.json)。

## 2026-10-30：Core2 WiFi IRQ cache handoff gate

`0092` 把 DPORT 的 per-CPU instruction-cache-ready 状态接入 ESP32
INTMATRIX，并在 cache disabled 窗口只暂存 WiFi MAC level；cache 恢复后
保留的 level 重新驱动 CPU output，因此 IRQ 被延迟而不是丢弃。cross-core、
timer 和 cache-illegal-access source 保持不门控，patch 不关闭 WDT、不修改
timeout 或 warp 虚拟时钟。

修复前 diagnostic QEMU `54d31e90…` 在同固件到达 BOARD/APIKEY/boot markers
后进入 `Cache disabled but cached memory region accessed` 并保持黑帧。
修复后 QEMU `a4cfa2b8…` 以默认 per-vCPU budget、normal WDT、`shift=2`
再次到达 BOARD/APIKEY/boot markers，不再出现该 panic，并得到
`320x240`、`75,559` nonblack pixels、`512` colors 的原厂 API Key 页面；
PNG SHA256 `737df08a…`。随后仍进入 `TG0WDT_SYS_RESET`，所以只关闭 WiFi
IRQ/cache-handoff 子问题，`RUNTIME-03` 保持 OPEN。同 patch 的 Core2
UIFlow2 设备组 `6/6 PASS`，每例 attempts 1 且无 retry。全部为
virtual-device validation；物理硬件、cache/PSRAM、RF 和电气测试
`NOT RUN`。见
[证据](evidence/2026-10-30-core2-wifi-irq-cache-gate/README.md)和
[机器摘要](evidence/2026-10-30-core2-wifi-irq-cache-gate/summary.json)。

## 2026-10-30：Core2 classic WiFi station timing and data path

`0093-esp32-classic-wifi-virtual-time.patch`（SHA256 `ecf75318…`）将
classic ESP32 beacon、injected frame 和生成的 802.11 timestamp 从
QEMU realtime 改为 virtual time；`0094-esp32-classic-wifi-station-data.patch`
（SHA256 `bead73ed…`）让 `ASSOCIATED`/`STA_DHCP`/`STA_ASSOCIATED`
station data 统一经过 Ethernet/slirp，host reply 也回到 guest station。
Device Service 同时将 SSID/password/auth 环境传给 classic 与 S3 WiFi
模型。

最终 QEMU `3e61aa64…` 上，stock Core2 UIFlow2 WiFi probe 五轮独立首启动
均为 PASS：scan count 为 `3`、识别 `myssid`、连接成功、DHCP 得到
`10.0.2.15`、完成 controlled HTTP 并输出
`CORE2_WIFI_RESULT: PASSED`。`M5SW_CLASSIC_WIFI_TRACE` 记录双向
`host-tx`/`host-rx` 和 `STA_ASSOCIATED`，证明数据经过控制器模型而不是
host-side fake。evidence SHA256 为 `b2559537…`。同一 binary 的 Core2
UIFlow2 设备组 `6/6 PASS`，每例 attempts 1 且无 retry，matrix summary
SHA256 为 `3533de10…`。

同一 legacy public firmware `4d2d648b…` 在 `shift=2`、诊断 `1 us`
per-vCPU cap、normal WDT 下到 BOARD/APIKEY/boot start/boot done，并显示
`320x240`、`75,559` nonblack、`512` colors 的 API Key 页面；随后仍
`TG0WDT_SYS_RESET`。同一最终 binary 的 WDT-disabled 诊断控制无复位运行到
guest virtual `457.794095092 s`，保留 `reconnect start/finish` 和同一
API Key 页面，说明 WiFi/UI 路径本身持续可用；该控制不是产品修复。
因此该里程碑关闭 classic WiFi station timebase 与双向 DHCP/数据面缺口，
`RUNTIME-03` 的 normal-WDT/startup/application 验收仍 OPEN。全部为
virtual-device validation；物理硬件、RF、电气和物理 cache/PSRAM timing
均 `NOT RUN`。见
[证据](evidence/2026-10-30-core2-classic-wifi-station-time/README.md)和
[机器摘要](evidence/2026-10-30-core2-classic-wifi-station-time/summary.json)。

## 2026-10-30：SVC-03 device-spec boundary

继续 `SVC-03` 的无状态边界拆分。新增
`platform/tools/device_service_specs.py`，移动 `DeviceSpec`、
`load_device_specs`、catalog/matrix/profile 路径、QEMU backend 路径与
ROM override、Core2 radio 后端选择和 network/runtime profile constants；
`device_service.py` 继续 same-object re-export，调用方、HTTP payload、
session/evidence 字段和 QEMU 行为不变。

新增 `test_device_service_specs.py` 锁定 14 个 catalog entry、Core2/Tab5/
CardputerZero 边界、绝对/相对 backend path、Core2 radio executable
fail-closed 和 public symbol identity。定向 `5/5 PASS`。该步骤只移动代码
边界；QEMU、firmware、runtime、物理硬件、RF 和电气验证均 `NOT RUN/不变`。
见[证据](evidence/2026-10-30-svc03-device-specs/README.md)和
[机器摘要](evidence/2026-10-30-svc03-device-specs/summary.json)。

## 2026-10-30：Core2 legacy WDT level delivery

`0095-esp32-legacy-wdt-level-delivery.patch`（SHA256 `df008a1f…`）修正
`0035` 对 classic ESP32 TIMG WDT level 的错误门控。公开 ESP-IDF 3.3.5
（`03810c4a…`）的 task watchdog 设置 `WDTCONFIG0.LEVEL_INT_EN` 并通过
`esp_intr_alloc(ETS_TG0_WDT_LEVEL_INTR_SOURCE)` 注册 ISR，但不写
`INT_ENA.WDT`。`0095` 保留 `INT_ST = INT_RAW & INT_ENA` 和非 WDT source
的 mask，仅让 WDT level 在 `LEVEL_INT_EN=1` 时跟随 raw status，WDT edge
路径不变。

最终 QEMU `001a9385…`、public firmware `4d2d648b…`、`runtime=qemu-wifi`、
matching `deviceCfg` overlay、`icount shift=2`、默认 `10 us` per-vCPU
budget 和 normal WDT 下完成三次独立 Device Service 运行，`3/3 PASS`。
三次保留 trace 尾部分别覆盖 guest virtual `315.55-335.55 s`、
`310.55-330.55 s`、`320.55-340.55 s`；每个相邻 stage-0 事件间隔
`5.001124 s`。trace 中 `int_ena=00000002`、`int_raw=00000004`、
`int_st=00000000` 时均出现 WDT level raise，随后 guest 写 `WDTFEED`
并以 `INT_CLR=00000004` 清除；原 `15.55 s` stage-1 reset 未再出现。
三次都完成 BOARD/APIKEY/boot-start/boot-done，保持 `320x240`、
`75,559` nonblack、`512` colors 的 API Key startup UI；其中两次完成
reconnect，第三次完成三轮 reconnect。同一最终 QEMU 的 Core2 UIFlow2
设备组 `6/6 PASS`，每例 attempts 1 且无 retry，summary SHA256
`6eaa6069…`。另一 normal-WDT session 在 boot-done 后捕获真实
`Wi-Fi Connect` / `Connecting to myssid` 页面（`75,373` nonblack、
`306` colors、PNG SHA256 `cf7ad5ab…`），但 Ctrl-C 输入没有产生 REPL
prompt。全部为 virtual-device validation；setup/REPL 独立交互、完整
factory application、物理硬件、RF、电气和物理 cache/PSRAM timing 仍分别
登记。`RUNTIME-03` 的 virtual-device stock startup 验收据此关闭；
setup/REPL 与任意 legacy application 转 `API-01`。见
[证据](evidence/2026-10-30-core2-legacy-wdt-level-delivery/README.md)和
[机器摘要](evidence/2026-10-30-core2-legacy-wdt-level-delivery/summary.json)。
