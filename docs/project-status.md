# 项目当前状态

日期：`2026-10-25`

本文是当前能力和边界的权威说明。当前未完成工作只在
[项目 Backlog](project-backlog.md)维护，逐次运行与 evidence 只在
[验证证据台账](validation-ledger.md)维护，设备/Task 计数由
[自动项目快照](project-snapshot.md)生成。代码阅读顺序见
[工程交接总览](engineering-handoff.md)，工作流归属见
[工作流总台账](workstreams.md)，源码与测试入口见
[代码与验证入口地图](code-map.md)。

## 一页结论

项目已经不是单固件 PoC，而是可执行的多设备 virtual-device 平台：

- Device Service 支持 lease、虚拟 Flash、串口、frame/input/QOM、网络故障、
  pcap、evidence、历史恢复和 worker 生命周期；
- S3/C6/Core2 的规范整机路径是 `qemu-unified`，同一 lease 和同一 guest
  内组合板级、WiFi、BLE 与 evidence；Core2 使用 `core2-native-hci`；
- 网络路径包含 controlled DNS/TLS、CNAME、有界 IPv4/IPv6 egress、WPA2、
  断线恢复、双 guest fabric、namespace/container worker 和 pcap。
  同 guest CNAME→HTTP 与专用测试构建的 IPv6 TCP/HTTP 已覆盖，原厂 UIFlow2 默认未启用
  IPv6 link-local；`RUNTIME-05` 的 S3 WPA2-PSK 成对密钥路径已关闭；
- 固件入口包含 FirmwareManifest、WebBurner/M5Burner/ESP-IDF、capability、
  文件系统、session-isolated NVS/SD fixture、静态审查和 Secure Boot v2
  镜像分析；
- Tab5、CardputerZero 和视觉外壳仍是可用子集，不能继承 S3/C6/Core2 的
  完整度。

当前阶段仍是 `PILOT`，不是“任意固件、任意设备都能自动审查”的完成态。
Core2 legacy I2C 的 board-bus routing 已修正：AXP `0x34` 与 RTC `0x51`
现在共享 `/machine/soc/i2c0/i2c` 并正常 ACK，原 `I2C bus error (19)` 消失。
同一固件随后进入独立的 interrupt-WDT reset/panic，仍没有非空应用帧，因此
`RUNTIME-03` 继续作为当前调查入口，但不能再用 PMIC 寄存器或 I2C routing
解释首个失败点。

新增 TIMG watchdog trace 后，默认单会话可持续喂 TG0/TG1 超过三分钟，而多个
Core2 legacy 并发 lease 会以不同 CPU/PC 触发 interrupt-WDT。显式
`thread=single`、`thread=multi` 和 `icount shift=0/5` 都没有修复，部分对照
转而更早触发 TG hardware reset。当前结论是 legacy 启动路径对宿主调度和虚拟
时间高度敏感，尚无证据支持“某一个固定外设缺失”或“固件必然死锁”。

所有仓库结果默认是 `virtual-device validation`。只有明确标注
`hardware validation` 的同固件路径结果才能描述物理 RF、功耗、声学、光学、
机械、电气或真机安全状态。

## 当前工作与下一门禁

| Task / 工作流 | 已具备的可执行面 | 下一项最小交付 | 不可继承边界 |
| --- | --- | --- | --- |
| `RUNTIME-03` Core2 legacy I2C / UIFlow 启动 | shared GPIO21/22 board bus 已修正；TIMG trace 证明默认单会话可持续 feed，并发和 accelerator 对照则暴露不同形态的 WDT | 隔离启动期长同步路径与 QEMU 虚拟时间/宿主调度；同 SHA 非空应用帧并保持运行 | WDT 不固定在单一 PC 或外设；I2C ACK 与单次短稳都不代表应用启动 |
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
| `qemu-unified` S3/C6 | 可用 | 功能级 WiFi/HCI；不是 RF/PHY、功耗或电气模型 |
| Core2 non-display | 可用 | native-HCI hook 绑定已验证 UIFlow2 build；新固件需重新校验 |
| Core2 legacy UIFlow/FactoryTest | `PARTIAL` | I2C routing 已修复；后续 interrupt WDT 和 black frame 未闭环 |
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
| StickS3 | ESP32-S3 / QEMU | 显示、按键、电源、IMU、音频、IR、WiFi/BLE | RF 和真机 `NOT RUN` |
| CoreS3 | ESP32-S3 / QEMU | 显示、触摸、电源、IMU、音频、摄像头、USB Host | 启动菜单透明/调色板图像仍有模拟条纹 |
| AtomS3R | ESP32-S3 / QEMU | 显示、按键、IMU、磁力计、RGB、IR | 高保真外观和真机 |
| Cardputer-ADV | ESP32-S3 / QEMU | 显示、键盘、IMU、音频、SD、NFC、CC1101、IR | 高保真外观和真机 |
| PaperColor | ESP32-S3 / QEMU | Spectra 6、按键、电源、SHT4X、音频、SD、RGB、IR | 刷新时序和光学真机表现 |
| PaperMono | ESP32-S3 / QEMU | 灰度屏、触摸、电源、IMU、RTC、音频、NFC、LoRa、RGB | 刷新手感和显示真机表现 |
| StackChan | ESP32-S3 / QEMU | 显示、触摸、摄像头、环境/运动传感器、音频、NFC、IR、舵机 | 机械运动、声学和光学 |
| StamPLC | ESP32-S3 / QEMU | 显示、按键、继电器/输入、CAN、RS-485、温度、蜂鸣器 | 工业电气特性和真机 |
| NanoC6 | ESP32-C6 / QEMU | 无屏控制台、GPIO、RGB、按键、IR、WiFi、BLE | Zigbee/802.15.4 由 `RUNTIME-02` 跟踪 |
| Nesso N1 | ESP32-C6 / QEMU | 显示、触摸、扩展 IO、电源、IMU、LoRa、IR、蜂鸣器、WiFi/BLE | RGB 未验；Meshtastic 独立应用异常待归因 |
| Core2 | ESP32 LX6 / QEMU | 显示、触摸、PMIC、IMU、RTC、音频、WiFi、公网、HCI/native-HCI、PSRAM/MMU | legacy UIFlow 后初始化 WDT/黑帧、物理 PSRAM/cache、bit-exact controller 和真机 |
| Tab5 | ESP32-P4 / esp-emu | 烧录、启动、1280×720、触摸、RS-485、ESP-Hosted、静态 I2C | P4 外设和 P4↔C6 unified network 仍 `partial` |
| CardputerZero | BCM2837 / Linux ARM64 | 系统、显示、键盘、I2C、PCM、USB Hub、摄像头、Ethernet | 完整系统回归、生产级 USB/时序和真机 |

设备、后端、外设和 profile 的动态计数见
[自动项目快照](project-snapshot.md)。

## 当前风险

1. **仿真边界**：QEMU/esp-emu PASS 不等于 RF、功耗、声学、光学、机械、
   电气或真机安全 PASS。
2. **Core2 启动兼容性**：legacy UIFlow 的共享 I2C routing 已修正，但同一
   固件仍会在 PMIC/RTC 初始化后进入 interrupt-WDT/黑帧；不能用 I2C ACK、
   chip-id 成功或 host 假值当作启动 PASS。
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
- 文档契约：五个 `platform/tests/test_docs_*_contract.py` 领域模块，以及
  `platform/tests/fixtures/stale_doc_claims.json` 结构化退役说法目录。

详细运行轮次、旧失败 control 和 evidence 不回写本页；当前入口已推翻的旧
说法应删除，历史页保留原日期并标明取代关系。
