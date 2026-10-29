<!-- GENERATED FILE: run `python3 platform/tools/project_snapshot.py --write` -->

# 项目快照（自动生成）

设备目录日期：`2026-10-26`；当前事实复核：`2026-10-29`；最新 evidence 日期：`2026-10-28`。

本页只汇总机器可读源和已提交 evidence，避免在多个文档手写同一组动态事实。实现结论、风险说明和验证层级仍以[项目当前状态](project-status.md)、[验证证据台账](validation-ledger.md)和 [项目 Backlog](project-backlog.md) 为准。

## 设备与后端

- 设备登记：`14` 台；Device Service 可创建：`13` 台。
- 设备分组：`esp32-c6` 2，`esp32-lx6` 1，`esp32-p4` 1，`esp32-s3` 9，`linux-arm64` 1。
- 外设状态：`partial` 1，`simulated` 13。

| 设备 | SoC | 后端 | 外设 | 最近验证 | 当前边界 |
| --- | --- | --- | --- | --- | --- |
| StopWatch (`stopwatch`) | ESP32-S3R8 | `qemu-esp32s3` | `simulated` | `2026-10-23` / `display-touch-peripherals-wifi-ble-pass` | 无登记 blocker |
| AtomS3R (`atoms3r`) | ESP32-S3-PICO-1-N8R8 | `qemu-esp32s3` | `simulated` | `2026-10-25` / `display-input-peripherals-wifi-ble-pass` | 无登记 blocker |
| CoreS3 (`cores3`) | ESP32-S3 | `qemu-esp32s3` | `simulated` | `2026-10-25` / `display-touch-peripherals-wifi-ble-pass` | UIFlow startup-menu palette PNG/tRNS assets render striped artifacts; ordinary RGB PNG and opaque drawing paths are correct |
| StickS3 (`sticks3`) | ESP32-S3-PICO-1-N8R8 | `qemu-esp32s3` | `simulated` | `2026-10-25` / `display-input-peripherals-wifi-ble-pass` | 无登记 blocker |
| Cardputer-ADV (`cardputer-adv`) | ESP32-S3FN8 | `qemu-esp32s3` | `simulated` | `2026-10-23` / `display-keyboard-peripherals-wifi-ble-pass` | 无登记 blocker |
| StackChan (`stackchan`) | ESP32-S3 | `qemu-esp32s3` | `simulated` | `2026-10-23` / `display-input-peripherals-wifi-ble-pass` | 无登记 blocker |
| StamPLC (`stamplc`) | ESP32-S3FN8 | `qemu-esp32s3` | `simulated` | `2026-10-23` / `display-input-peripherals-wifi-ble-pass` | 无登记 blocker |
| PaperColor (`papercolor`) | ESP32-S3R8 | `qemu-esp32s3` | `simulated` | `2026-10-23` / `display-input-peripherals-wifi-ble-pass` | 无登记 blocker |
| PaperMono (`papermono`) | ESP32-S3R8 | `qemu-esp32s3` | `simulated` | `2026-10-23` / `display-touch-peripherals-wifi-ble-pass` | 无登记 blocker |
| NanoC6 (`nanoc6`) | ESP32-C6FH4 | `qemu-esp32c6` | `simulated` | `2026-10-24` / `board-peripherals-wifi-ble-pass` | Zigbee/802.15.4 controller data plane is not modeled (RUNTIME-02) |
| Arduino Nesso N1 (`nesso-n1`) | ESP32-C6 | `qemu-esp32c6` | `simulated` | `2026-10-24` / `display-touch-peripherals-wifi-ble-pass` | Meshtastic remains PARTIAL after an independent post-application instruction access fault (RUNTIME-01 flash/PMP defect is fixed) |
| CardputerZero (`cardputer-zero`) | RP3A0 (BCM2837) | `external-linux-arm64` | `simulated` | `2026-10-22` / `linux-display-input-i2c-audio-power-usb-camera-partial` | not an ESP32 firmware target |
| Core2 (`core2`) | ESP32-D0WDQ6-V3 | `qemu-esp32lx6` | `simulated` | `2026-10-28` / `display-input-peripherals-wifi-ble-pass` | Core2 legacy UIFlow shared I2C, equal-deadline timer and TIMG WDT-mask semantics are fixed. Patches 0036-0042 add stateful SSI, unified timeline, exact-time pause/state sweep, BIN-bound setter trace, bounded register/object/stack dumps, and a partial SPI TRANS_DONE/TRANS_INTEN IRQ model. Patch 0064 fixes pending SPI source delivery when the interrupt matrix is remapped while the level is already high; an isolated ESP-IDF SPI3 guest probe changes from pre-fix callback timeout to fixed 3/3 PASS. Historical no-NIC controls mixed a generic LittleFS image with a runtime that omitted misc.esp32_wifi; a matching LittleFS2 VFS through Device Service runtime=qemu-wifi executes the injected /flash/boot.py at 120 s. Patch 0068 attaches the same ILI9342 panel sink to legacy HSPI/SPI2 and UIFlow2 VSPI/SPI3. The SPI3-only negative control had 0 panel DMA writes and 412 writes to another controller; with dual-SPI routing the legacy m5stack/lcd probe reaches 1422 nonblack pixels. The original startup UI, normal-WDT path and complete application frame still fail. TG0 stage-0 is masked at about 5.91 s and TG0 stage-1 triggers the first reset at about 15.91 s while TG1 remains live. The old 0x40100049 LVGL wait is not reproduced and requires a new same-lane binding. Temporary bulk-read and watchdog-disable diagnostics are not product fixes; physical cache/PSRAM timing equivalence remains NOT RUN; bit-exact ESP32 BT baseband/controller remains NOT RUN; virtual-device concurrency gates cover the current service capacity; more-than-eight-instance stability, sustained throughput and teardown modes beyond active-stop remain OPEN (CORE2-02); the bounded-TCG host-memory result is validated only for the tested long-hold workload |
| Tab5 (`tab5`) | ESP32-P4NRW32 | `esp-emulator-native` | `partial` | `2026-10-22` / `display-touch-rs485-pass-peripherals-partial` | SC2356 MIPI CSI-2 controller/frame path missing from esp-emu 0.50.0; ES8388/ES7210 I2S register and PCM endpoints missing from esp-emu 0.50.0; ESP32-P4 USB Host controller and endpoint attachment missing; Tab5 ST7123 touch is currently a firmware GDB mailbox rather than an I2C chip model; Tab5 SDIO storage is not wired to a host block backend; Tab5 INA226 register preload reaches Power as 8000 mV/1248 mA/87%, direct machine.I2C write/read reaches RX8130 registers, and PI4IOE CHG_STAT/CHG_EN reach Power.isCharging() in both charging and discharging scenarios, but RTC progression, dynamic I2C/time injection and IP2326 analog current/termination behavior remain partial; BMI270 identity also remains partial |

## 外接 Unit 库存与准入

- Unit 登记：`34` 款；主机接线登记：`14` 款。
- Runtime profile 状态：`implemented` 34。
- 固定视觉源：[https://github.com/yuyun2000/m5stack-models](https://github.com/yuyun2000/m5stack-models)，commit `c48940c3aad3f2e8e9b8906b82071a88f2a3de1e`；包含 `17` 款主机、`184` 款 Unit。视觉库存不构成控制器或电气验证。
- 仅视觉主机：`atom-lite`，`atom-matrix`，`atoms3-lite`；这些型号没有设备运行登记，不能创建 Device Service 会话。
- 仅视觉、尚无内部协议契约：`4relay`，`8angle`，`8servos2-chain`，`8servos2-i2c`，`ac-measure`，`accel`，`acssr`，`adc`，`adc-v11`，`ain4-20ma`，`ameter`，`asr`，`audioplayer`，`bldc-driver`，`bmm350`，`bps`，`bytebutton`，`byteswitch`，`c6l`，`cams3-5mp`，`can`，`cardkb-original`，`cardkb2`，`cat1-cn`，`catm`，`catm-gnss`，`chainbus`，`co2`，`co2l`，`dac`，`dac2`，`dcssr`，`dds`，`dlight`，`dmx`，`dof10`，`dof6`，`dof9`，`earth`，`env`，`env-ii`，`env-iv`，`env-pro`，`esp32cam`，`extencoder`，`extio`，`extio2`，`fader`，`finger`，`fingerprint2`，`gateway-h2`，`gesture`，`glass`，`glass2`，`gps`，`gps-sma`，`gps-v11`，`grove-to-grove`，`hall`，`hbridge`，`hbridge-v11`，`hex`，`ina226-10a`，`ina226-1a`，`joystick`，`kmeter-iso-v11`，`laser-rx`，`laser-tx`，`lcd`，`lora-e220-433`，`lora-e220-920`，`lorawan-as923`，`lorawan-cn470`，`lorawan-eu868`，`lorawan-us915`，`m5-bit`，`m5camera`，`m5camera-x`，`mic`，`midi`，`mini-bps-v11`，`mini-can`，`mini-imu`，`mini-imu-pro`，`mini-oled`，`mini-pdm`，`mini-proto`，`mini-scales`，`mini-tof-90`，`mq`，`nbiot-cn`，`nbiot2`，`ncir2`，`neco`，`neohex`，`oled`，`op180`，`op90`，`pahub-v20`，`pahub-v21`，`pbhub`，`pbhub-v11`，`poe-cam-w`，`poe-cam-w-v11`，`poe-p4`，`poesp32`，`proto`，`puzzle`，`qrcode`，`rca`，`reflective-ir`，`rf433r`，`rf433t`，`rfid`，`rgb-led-10cm`，`rgb-led-strip-50cm`，`roller485`，`roller485-lite`，`rollercan`，`rollercan-lite`，`rs485-iso`，`rtc`，`scales`，`ssr`，`step16`，`synth`，`thermal2`，`timercamera`，`timercamera-f`，`timercamera-x`，`timerpwr`，`tmos-pir`，`tof4m`，`tube-pressure`，`typec-to-grove`，`uhf-rfid`，`ultrasonic-io`，`unit-396`，`unit-id`，`unitv-m12`，`unitv-ov7740`，`unitv2`，`unitv2-m12`，`unitv2-usb`，`uwb`，`vibrator`，`vmeter`，`watering`，`weight`，`weight-i2c`，`zigbee`；这些型号不计 runtime 准入，也不能创建功能附件。
- 数据源：[`catalog`](../platform/units/catalog.json)，[`runtime_profiles`](../platform/units/runtime-profiles.json)，[`host_ports`](../platform/units/host-ports.json)，[`visual_vendor`](../platform/web/vendor/m5stack-models/vendor-manifest.json)。

准入仅统计 `implemented`/`validated` profile 的主机声明和已确认主机接口；准入不等于同设备固件、Web 或真机验证。`planned`/`partial`/`unsupported` 不计准入，`implemented` 不提升为 `validated`。

| 主机 | Profile 准入 Unit 数 | implemented | validated |
| --- | ---: | ---: | ---: |
| `atoms3r` | 29 | 29 | 0 |
| `cardputer-adv` | 0 | 0 | 0 |
| `cardputer-zero` | 0 | 0 | 0 |
| `core2` | 0 | 0 | 0 |
| `cores3` | 33 | 33 | 0 |
| `nanoc6` | 0 | 0 | 0 |
| `nesso-n1` | 0 | 0 | 0 |
| `papercolor` | 0 | 0 | 0 |
| `papermono` | 0 | 0 | 0 |
| `stackchan` | 0 | 0 | 0 |
| `stamplc` | 0 | 0 | 0 |
| `sticks3` | 30 | 30 | 0 |
| `stopwatch` | 29 | 29 | 0 |
| `tab5` | 0 | 0 | 0 |

## 通用固件审查

历史哈希绑定公开样本基线（来源日期 `2026-10-24`）覆盖 `7` 台设备、`21` 个固件：`10` PASS、`11` PARTIAL、`0` FAIL。PARTIAL 不自动等于固件缺陷；`runtime_model_gap` 必须保留模型边界。之后刷新、专项 fixture、安全与导入结果分别回查专题页和验证台账，不把新 evidence 自动并入这份历史样本计数。

## 运行时模型缺口

| ID | 状态 | 缺口 |
| --- | --- | --- |
| `RUNTIME-01` | `FIXED` | C6 软件复位后 chip-id 错误 |
| `RUNTIME-05` | `FIXED` | S3 QEMU AP WPA2-PSK 数据面 |
| `RUNTIME-02` | `OPEN` | C6 Zigbee/802.15.4 运行时未建模 |
| `RUNTIME-03` | `OPEN` | scheduler/DPORT 与经典 RMT 初始化已修复，legacy WDT/LVGL/应用帧未闭环 |
| `RUNTIME-06` | `PARTIAL` | ESP-NOW controller loopback 已验证，外部/加密 peer 未建模 |
| `RUNTIME-04` | `OPEN` | Core2 for AWS ATECC608 未建模 |

## Backlog Task 板

| Task | 当前状态 | 下一项最小交付 |
| --- | --- | --- |
| `API-01` | 进行中 | 接续 stock SDK/绑定失败、WDT warm reboot、native build feature、未实现控制器与未选外设；扩展 Cardputer-ADV Unit 准入及同固件更多行为域。`0074` 已关闭 Core2 candidate M5UI frame routing/oracle；Core2 stock BLE NUS 已通过 native-HCI，`Server.get_client` 已有 hash-pinned 候选修复；StopWatch/StickS3 stock controller 仍开放 |
| `RUNTIME-03` | 进行中 | `0065` 关闭 high-priority DPORT handoff 调度死锁，`0066` 补 classic RMT，`0068` 将 legacy HSPI/SPI2 与 UIFlow2 VSPI/SPI3 都接到同一 panel sink，`0069` 修正 protected `WDTFEED` 语义；`0071/0072` 精确得到 `0xBB/64 -> 0x05/1 -> 0xBB/64` 主循环；`0073` 绑定主要 issuer；`0075` 排除 RDSR WIP/busy 错误并把成本定位到 scheduler/list 跨核锁竞争，failed-CAS slice yield 无效 |
| `RUNTIME-06` | 进行中 | `0067` 已用 controller TX/RX DMA loopback 验证三台 unicast/broadcast/receive/IRQ；下一项是外部 peer、PMK 加密 payload、跨设备 fabric 与错误/丢包生命周期 |
| `NET-04` | 进行中 | 物理跨主机 executor/reattach、跨主机幂等、任意 NAT、QEMU 内 guest/controller 和外部 side-effect fence |
| `CORE2-02` | 进行中 | 大于当前服务容量、持续吞吐、其他 teardown、bit-exact controller/baseband、物理 PSRAM/cache timing 和真机 |
| `FW-01` | 进行中 | 运行态 ACL/权限、完整源码和依赖许可覆盖、法律审批 |
| `FW-02` | 进行中 | 真机 Secure Boot、Flash Encryption、live eFuse、bootloader anti-rollback 和生产 key |
| `FW-03` | 进行中 | 真实 key/云端业务；更多设备与 firmware family；继续扩展 SD/NVS 和网络预期 |
| `RUNTIME-02` | 进行中（backend blocked） | C6 802.15.4 MAC ACK/commissioning 和 join/收发/离网生命周期 |
| `RUNTIME-04` | 进行中 | ATECC608 I2C 命令和测试 slot/config fixture |
| `SVC-01` | 进行中 | namespace-managed/Tab5/cross-host companion 和跨主机 idempotency |
| `SVC-02` | 待做 | warm pool、配额、对象存储、审计和容量指标 |
| `SVC-03` | 待做 | 先提取纯配置/请求解析边界，再拆 store、runtime adapter、evidence collector 和 session 状态机 |
| `HW-01` | 待做 | 代表设备的同固件 SHA 真机测试计划 |
| `TAB5-01` | 决策 | 重建或扩展 P4 backend |
| `UI-01` | 待做 | 逐设备结构、材质、hitbox 和截图阈值 |
| `UI-02` | 进行中 | C/QEMU默认时钟LVGL队列、未覆盖异常路径、长期稳定性及持久化；扩展设备/固件/Unit准入；Rust演示仅作研究原型 |
| `UNIT-01` | 进行中 | 其余同guest Unit（issue #5–#8 已补控制器路径，仍需更广固件/主机矩阵）、FlashLight冷route的有效pad来源/连续低观察生命周期、更多主机/固件的二进制入口验收与保存开机程序；AIFlow checkpoint/虚拟目标、Preview后续恢复与GC、SSE/实时分发；程序revision引用保留/有界回收；Tab5 GDB frame生命周期与其它后端取消场景实际会话验证；其它准入主机/固件的实际源码API执行、ADC2 oracle与Thermal fixture、新HUB拓扑、原IR GC/原Buzzer、完整PWM周期、Heart生理算法及视觉缺口；Scroll的TIM回绕、RGB多槽队列、轴角/方向标定、bootloader/Flash持久化与地址0；Roller485协议与功能准入 |
| `CZ-01` | 待做 | CardputerZero 系统、驱动和长期回归 |

## 代码与文档规模

- `platform/tools`：`60` 个 Python 模块，`44054` 行；规模最大的模块如下。

| 模块 | 行数 |
| --- | ---: |
| `device_service.py` | 11895 |
| `firmware_manifest.py` | 3612 |
| `user_firmware_matrix.py` | 2069 |
| `network_sandbox.py` | 1681 |
| `serve.py` | 1557 |
| `firmware_filesystems.py` | 1469 |

- `tests/`：`129` 个可执行 Python 测试文件，分布在 `58` 个目录；`223` 个 evidence JSON。
- `patches/`：`15` 个补丁组，`151` 个 patch 文件。
- 文档：`415` 个 Markdown 页面；除本生成页外共 `40469` 行。

## 文档与测试

- 平台测试：`1433` 项。
- Docs 新鲜度登记：`91` 行；其中非历史页 `81` 行，历史固定页 `10` 行。
- 文档职责分布：待办 `3`，契约 `8`，证据/差异 `29`，历史固定 `10`，实现/设计 `9`，参考 `28`，工作流/导航 `4`。
- 全量文档盘点：`415` 个 Markdown 页面；职责分布：权威/专题页 `91`，设备档案 `18`，示例 `1`，治理/入口 `3`，文档导航 `1`，其他 `3`，补丁说明 `18`，平台说明 `9`，仓内历史记录 `5`，测试/用例说明 `159`，未登记 docs 页面 `3`，第三方来源说明 `104`。
- 复核日期早于当前事实日期的非历史页：[engineering-handoff.md](engineering-handoff.md) `2026-10-28`，[workstreams.md](workstreams.md) `2026-10-28`，[project-snapshot.md](project-snapshot.md) `2026-10-26`，[code-map.md](code-map.md) `2026-10-27`，[evidence-retention.md](evidence-retention.md) `2026-10-27`，[browser-runtime-feasibility.md](browser-runtime-feasibility.md) `2026-10-28`，[pages-deployment.md](pages-deployment.md) `2026-10-28`，[qemu-wasm-port-research.md](qemu-wasm-port-research.md) `2026-10-28`，[plans/2026-10-28-public-simulator.md](plans/2026-10-28-public-simulator.md) `2026-10-28`，[evidence/2026-10-28-public-simulator/README.md](evidence/2026-10-28-public-simulator/README.md) `2026-10-28`，[plans/2026-10-27-source-pr-cleanup.md](plans/2026-10-27-source-pr-cleanup.md) `2026-10-27`，[evidence/2026-10-27-uiflow2-api-sweep/README.md](evidence/2026-10-27-uiflow2-api-sweep/README.md) `2026-10-28`，[evidence/2026-10-28-multi-board-uiflow2-revalidation/README.md](evidence/2026-10-28-multi-board-uiflow2-revalidation/README.md) `2026-10-28`，[evidence/2026-10-28-qrcode-tls-candidate-firmware/README.md](evidence/2026-10-28-qrcode-tls-candidate-firmware/README.md) `2026-10-28`，[evidence/2026-10-28-stopwatch-drawpixel-transaction/README.md](evidence/2026-10-28-stopwatch-drawpixel-transaction/README.md) `2026-10-28`，[evidence/2026-10-28-three-board-audio/README.md](evidence/2026-10-28-three-board-audio/README.md) `2026-10-28`，[evidence/2026-10-28-core2-touch-buttons/README.md](evidence/2026-10-28-core2-touch-buttons/README.md) `2026-10-28`，[evidence/2026-10-28-core2-intmatrix-pending-irq/README.md](evidence/2026-10-28-core2-intmatrix-pending-irq/README.md) `2026-10-28`，[evidence/2026-10-28-cooperative-highint-rmt/README.md](evidence/2026-10-28-cooperative-highint-rmt/README.md) `2026-10-28`，[evidence/2026-10-28-core2-legacy-vfs-wifi-fixture/README.md](evidence/2026-10-28-core2-legacy-vfs-wifi-fixture/README.md) `2026-10-28`，[evidence/2026-10-28-core2-dual-spi-panel-routing/README.md](evidence/2026-10-28-core2-dual-spi-panel-routing/README.md) `2026-10-28`，[evidence/2026-10-28-espnow-and-three-board-interface-retest/README.md](evidence/2026-10-28-espnow-and-three-board-interface-retest/README.md) `2026-10-28`，[evidence/2026-10-28-concurrent-fixture-and-ready-state/README.md](evidence/2026-10-28-concurrent-fixture-and-ready-state/README.md) `2026-10-28`，[evidence/2026-10-28-three-board-uiflow2-latest-runtime/README.md](evidence/2026-10-28-three-board-uiflow2-latest-runtime/README.md) `2026-10-28`，[evidence/2026-10-28-core2-timg-wdt-feed/README.md](evidence/2026-10-28-core2-timg-wdt-feed/README.md) `2026-10-28`，[device-service-api.md](device-service-api.md) `2026-10-28`，[unit-agent-api.md](unit-agent-api.md) `2026-10-27`，[unified-device-runtime.md](unified-device-runtime.md) `2026-10-26`，[core2-native-hci-backend.md](core2-native-hci-backend.md) `2026-10-26`，[firmware-manifest.md](firmware-manifest.md) `2026-10-26`，[runtime-model-gap-register.md](runtime-model-gap-register.md) `2026-10-28`，[network-simulation-plan.md](network-simulation-plan.md) `2026-10-26`，[network-lane.md](network-lane.md) `2026-10-26`，[qemu-device-adaptation-matrix.md](qemu-device-adaptation-matrix.md) `2026-10-26`，[uiflow2-peripheral-test-matrix.md](uiflow2-peripheral-test-matrix.md) `2026-10-26`，[tab5-deferred-backlog.md](tab5-deferred-backlog.md) `2026-10-26`，[device-visual-fidelity-backlog.md](device-visual-fidelity-backlog.md) `2026-10-26`，[deployment.md](deployment.md) `2026-10-26`，[device-center-adapter.md](device-center-adapter.md) `2026-10-26`，[device-functional-test-workflow.md](device-functional-test-workflow.md) `2026-10-26`，[firmware-review-and-simulation-workflow.md](firmware-review-and-simulation-workflow.md) `2026-10-26`，[peripheral-simulation-architecture.md](peripheral-simulation-architecture.md) `2026-10-26`，[p4-peripheral-backend-requirements.md](p4-peripheral-backend-requirements.md) `2026-10-26`，[simulator-service-architecture.md](simulator-service-architecture.md) `2026-10-26`，[user-firmware-simulation-matrix.md](user-firmware-simulation-matrix.md) `2026-10-26`，[cores3-image-rendering-boundary.md](cores3-image-rendering-boundary.md) `2026-10-26`，[plans/2026-10-25-unit-runtime-integration.md](plans/2026-10-25-unit-runtime-integration.md) `2026-10-27`，[unit-integration-host-issues.md](unit-integration-host-issues.md) `2026-10-27`，[plans/2026-10-26-aiflow-live-preview-api.md](plans/2026-10-26-aiflow-live-preview-api.md) `2026-10-27`，[plans/2026-10-27-preview-run-control.md](plans/2026-10-27-preview-run-control.md) `2026-10-27`，[plans/2026-10-27-preview-web-consumer.md](plans/2026-10-27-preview-web-consumer.md) `2026-10-27`，[plans/2026-10-27-preview-controls-and-2relay.md](plans/2026-10-27-preview-controls-and-2relay.md) `2026-10-27`，[plans/2026-10-27-binary-checkpoint-and-unit-protocols.md](plans/2026-10-27-binary-checkpoint-and-unit-protocols.md) `2026-10-27`，[plans/2026-10-27-flashlight-and-uploaded-uiflow-base.md](plans/2026-10-27-flashlight-and-uploaded-uiflow-base.md) `2026-10-27`，[plans/2026-10-27-public-main-mpy-runtime.md](plans/2026-10-27-public-main-mpy-runtime.md) `2026-10-27`，[plans/2026-10-27-flashlight-route-history.md](plans/2026-10-27-flashlight-route-history.md) `2026-10-27`，[plans/2026-10-27-flashlight-cold-pad-observation.md](plans/2026-10-27-flashlight-cold-pad-observation.md) `2026-10-27`，[plans/2026-10-27-core2-startup-issues.md](plans/2026-10-27-core2-startup-issues.md) `2026-10-27`，[unit-research/official-protocols.md](unit-research/official-protocols.md) `2026-10-26`，[unit-research/scroll-roller485.md](unit-research/scroll-roller485.md) `2026-10-26`，[unit-research/encoder-protocol-conflicts.md](unit-research/encoder-protocol-conflicts.md) `2026-10-26`，[unit-research/esp32s3-adc-calibration.md](unit-research/esp32s3-adc-calibration.md) `2026-10-26`，[unit-research/visual-bindings-and-component-gaps.md](unit-research/visual-bindings-and-component-gaps.md) `2026-10-26`，[unit-research/host-runtime-compatibility.md](unit-research/host-runtime-compatibility.md) `2026-10-26`。这不自动表示内容错误；状态页变更时应优先复核。
- 带显式旧复核日期的委派文档（需按相邻索引和权威页复核）：
  - [platform/web/vendor/m5stack-models/docs/INTEGRATION.md](../platform/web/vendor/m5stack-models/docs/INTEGRATION.md) `2026-10-25`
  - [patches/README.md](../patches/README.md) `2026-10-26`
  - [patches/qemu-core2-ble-controller/README.md](../patches/qemu-core2-ble-controller/README.md) `2026-10-26`
  - [patches/qemu-core2-native-hci/README.md](../patches/qemu-core2-native-hci/README.md) `2026-10-26`
  - [patches/qemu-core2-openmac-wifi/README.md](../patches/qemu-core2-openmac-wifi/README.md) `2026-10-26`
  - [patches/qemu-esp32c6-uiflow2-adapters/README.md](../patches/qemu-esp32c6-uiflow2-adapters/README.md) `2026-10-26`
  - [patches/qemu-multi-board-uiflow2/README.md](../patches/qemu-multi-board-uiflow2/README.md) `2026-10-26`
  - [platform/web/vendor/m5stack-models/docs/STICKER-COVERAGE.md](../platform/web/vendor/m5stack-models/docs/STICKER-COVERAGE.md) `2026-10-26`
  - [platform/web/vendor/m5stack-models/docs/THERMAL-MODEL-NOTES.md](../platform/web/vendor/m5stack-models/docs/THERMAL-MODEL-NOTES.md) `2026-10-26`
  - [tests/README.md](../tests/README.md) `2026-10-26`
  - [tests/firmware/README.md](../tests/firmware/README.md) `2026-10-26`
  - [tests/firmware/image_capability_observation/README.md](../tests/firmware/image_capability_observation/README.md) `2026-10-26`
  - [tests/firmware/manifest_policy/README.md](../tests/firmware/manifest_policy/README.md) `2026-10-26`
  - [tests/firmware/openai_nvs_precondition/README.md](../tests/firmware/openai_nvs_precondition/README.md) `2026-10-26`
  - [tests/firmware/webburner_import_policy/README.md](../tests/firmware/webburner_import_policy/README.md) `2026-10-26`
  - [tests/firmware/webburner_part_integrity/README.md](../tests/firmware/webburner_part_integrity/README.md) `2026-10-26`
  - [tests/network/README.md](../tests/network/README.md) `2026-10-26`
  - [tests/network/cname_guest_lifecycle/README.md](../tests/network/cname_guest_lifecycle/README.md) `2026-10-26`
  - [tests/network/core2_openeth/README.md](../tests/network/core2_openeth/README.md) `2026-10-26`
  - [tests/network/core2_openmac_wifi/README.md](../tests/network/core2_openmac_wifi/README.md) `2026-10-26`
  - [tests/network/dns_cname_chain/README.md](../tests/network/dns_cname_chain/README.md) `2026-10-26`
  - [tests/network/egress_allowlist/README.md](../tests/network/egress_allowlist/README.md) `2026-10-26`
  - [tests/network/idf_dhcp_renewal/README.md](../tests/network/idf_dhcp_renewal/README.md) `2026-10-26`
  - [tests/network/ipv6_end_to_end/README.md](../tests/network/ipv6_end_to_end/README.md) `2026-10-26`
  - [tests/network/linux_isolation/README.md](../tests/network/linux_isolation/README.md) `2026-10-26`
  - [tests/network/reconnect_probe/README.md](../tests/network/reconnect_probe/README.md) `2026-10-26`
  - [tests/network/worker_cross_container/README.md](../tests/network/worker_cross_container/README.md) `2026-10-26`
  - [tests/network/worker_cross_netns/README.md](../tests/network/worker_cross_netns/README.md) `2026-10-26`
  - [tests/network/worker_executor/README.md](../tests/network/worker_executor/README.md) `2026-10-26`
  - [tests/network/worker_queue/README.md](../tests/network/worker_queue/README.md) `2026-10-26`
  - [tests/network/worker_reattach/README.md](../tests/network/worker_reattach/README.md) `2026-10-26`
  - [tests/network/worker_tls/README.md](../tests/network/worker_tls/README.md) `2026-10-26`
  - [tests/network/wrong_password/README.md](../tests/network/wrong_password/README.md) `2026-10-26`
  - [tests/uiflow2/README.md](../tests/uiflow2/README.md) `2026-10-26`
  - [tests/uiflow2/core2_native_hci/README.md](../tests/uiflow2/core2_native_hci/README.md) `2026-10-26`
  - [tests/uiflow2/core2_native_vhci/README.md](../tests/uiflow2/core2_native_vhci/README.md) `2026-10-26`
  - [tests/uiflow2/sticks3_peripherals/README.md](../tests/uiflow2/sticks3_peripherals/README.md) `2026-10-26`
  - [tests/uiflow2/unified_core2/README.md](../tests/uiflow2/unified_core2/README.md) `2026-10-26`
  - [docs/plans/2026-10-27-uiflow2-complete-api-sweep.md](plans/2026-10-27-uiflow2-complete-api-sweep.md) `2026-10-27`
  - [docs/evidence/2026-10-28-qemu-wasm-build/README.md](evidence/2026-10-28-qemu-wasm-build/README.md) `2026-10-28`
  - [platform/README.md](../platform/README.md) `2026-10-28`
- 代码边界和大型模块的维护建议由[代码与验证入口地图](code-map.md)维护。

## 维护入口

- 当前能力、风险和真机边界：[项目当前状态](project-status.md)。
- 未完成 Task、依赖和验收：[项目 Backlog](project-backlog.md)。
- 带日期的验证结果和 evidence：[验证证据台账](validation-ledger.md)。
- 代码、测试和证据路径：[代码与验证入口地图](code-map.md)。
- 测试分层和 evidence 规则：[测试总索引](../tests/README.md)。
- QEMU/固件补丁分组：[补丁总索引](../patches/README.md)。
- 文档职责和新鲜度：[文档导航](README.md)。
