# 项目当前状态

日期：`2026-10-26`

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
同一固件随后进入独立的 TG0/TG1 watchdog reset 循环，仍没有非空应用帧，因此
`RUNTIME-03` 继续作为当前调查入口，但不能再用 PMIC 寄存器或 I2C routing
解释首个失败点。

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

这个修复没有关闭 legacy UIFlow：同一公开固件仍在初始化后进入
`TG0WDT_SYS_RESET`/`TG1WDT_SYS_RESET`、reset CPU PC `0` 和黑帧循环。
因此 `RUNTIME-03` 的 timer-deadline 子问题已经 `FIXED`，但 legacy
interrupt-WDT reset 与累计 Flash/cache-handoff 服务进度仍 `OPEN`。

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
  两次 normal-WDT 运行都在 TG1 最后一次 feed 后恰好 `800,000,000 ns`
  进入 stage-0 timeout，再经过约 `1.6 s` 进入 reset；timeout PC 可变化。
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

当前工作假设是大量已经完成的 Flash/cache/DPORT 周期与启动 workload
超过 watchdog budget，或首个 stage-0 timeout 后有一条独立 service/feed
liveness 路径没有被恢复。高频采样下的固定 UART/VM PC 簇不再成立；
“单次 cache restore 未返回”也被 `0039/0040` 否定。下一步是围绕首个
stage-0 timeout 前后继续量化 WDT feed、service task 和 controller 操作，
同时取得 v1.15.4 ELF/MAP。
精确批次、通过率、
artifact 哈希和符号化结果见[验证证据台账](validation-ledger.md)。

所有仓库结果默认是 `virtual-device validation`。只有明确标注
`hardware validation` 的同固件路径结果才能描述物理 RF、功耗、声学、光学、
机械、电气或真机安全状态。

## 当前工作与下一门禁

| Task / 工作流 | 已具备的可执行面 | 下一项最小交付 | 不可继承边界 |
| --- | --- | --- | --- |
| `RUNTIME-03` Core2 legacy I2C / UIFlow 启动 | shared I2C、timer deadline、WDT mask、stateful SSI、统一 timeline、错误 ELF 映射拒绝、exact-time state sweep 和 setter PC trace 已验证；已证明 CPU1 持续执行且 handoff 在 reset 前完成约 4,376 次 | 量化首个 stage-0 timeout 前后 WDT feed/service/controller liveness，解释为何完成周期和约 250 KiB SSI 数据仍无应用进度；取得 matching ELF/MAP 可并行 | 临时 `blk_pread`、关闭 WDT、accelerator、probe PASS 或 UIFlow2 设备组 PASS 都不能继承为 legacy PASS；UART 高频 PC 映射和“永久 handoff deadlock”都不得复用 |
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
| Core2 legacy UIFlow/FactoryTest | `PARTIAL` | I2C routing、timer deadline、TIMG WDT mask 和 stateful SSI 已验证；统一 timeline 复现最后 feed 后固定 800 ms timeout，但 legacy reset、reset PC `0` 和该停滞窗口的 guest 根因未闭环；FactoryTest 修复后 `NOT RUN` |
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
| Core2 | ESP32 LX6 / QEMU | 显示、触摸、PMIC、IMU、RTC、音频、WiFi、公网、HCI/native-HCI、PSRAM/MMU、timer/WDT-mask/stateful SSI fixes | legacy UIFlow 后初始化 TG0/TG1 WDT/黑帧、累计 Flash/cache-handoff 吞吐、物理 PSRAM/cache、bit-exact controller 和真机 |
| Tab5 | ESP32-P4 / esp-emu | 烧录、启动、1280×720、触摸、RS-485、ESP-Hosted、静态 I2C | P4 外设和 P4↔C6 unified network 仍 `partial` |
| CardputerZero | BCM2837 / Linux ARM64 | 系统、显示、键盘、I2C、PCM、USB Hub、摄像头、Ethernet | 完整系统回归、生产级 USB/时序和真机 |

设备、后端、外设和 profile 的动态计数见
[自动项目快照](project-snapshot.md)。

## 当前风险

1. **仿真边界**：QEMU/esp-emu PASS 不等于 RF、功耗、声学、光学、机械、
   电气或真机安全 PASS。
2. **Core2 启动兼容性**：legacy UIFlow 的共享 I2C routing 已修正，最小
   probe 暴露的 `CCOMPARE == CCOUNT` timer deadline，以及 `0035` 的
   masked WDT interrupt 语义也已修复；`0036` 又验证了保留 m25p80 状态的
   SSI 批量数据面，但同一 legacy 固件仍会在 PMIC/RTC 初始化后进入
   `TG0/TG1WDT_SYS_RESET`/黑帧，reset CPU PC 为 `0`。不能用 I2C ACK、
   probe/UIFlow2 PASS、旧 REPL 观察、关闭 WDT、accelerator 或 host 假值
   当作 legacy 启动 PASS。当前证据显示 flash-operation/cross-core flags
   会反复完成；`0037` 已把 controller batch、两核 PC 与 watchdog feed
   放到同一虚拟时间轴，并复现最后 feed 后固定 800 ms timeout。`0039/0040`
   又证明 CPU1 持续执行且 handoff 在 reset 前完成约 4,376 次。下一步是
   解释首个 stage-0 timeout 后的 feed/service liveness，而不是继续寻找
   单次未返回 handoff；该轮仍属于 legacy `flash-cache/IPC/DPORT` 启动
   边界，量化结果只以验证台账和 evidence 为准。
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
