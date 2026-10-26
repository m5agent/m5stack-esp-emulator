# 项目 Backlog

日期：`2026-10-26`

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
| P0 | Core2 legacy UIFlow 启动 | 共享 I2C、timer deadline、WDT mask 和 QIO/stateful SSI 批量数据面已修复/验证；TG0 stage-1/TG1-live 已取证；WDT-off 45/120 秒状态显示 flash-cache/IPC/DPORT Flash 工作约 44 秒结束，随后 CPU1 持续等待 `0x40100049` 的 flag/object | probe/UIFlow2 PASS、单次 REPL marker、临时 bulk read、关闭 WDT 或 accelerator 都不代表 legacy 应用启动 |
| P0 | 网络产品化 | 物理跨主机 worker、跨主机幂等、任意 NAT 和外部 side-effect fence | 单机 namespace/container 不能替代物理多机 |
| P0 | Core2 物理/controller 等价性 | 更大规模、持续吞吐、其他 teardown、bit-exact controller 和物理 PSRAM/cache | 虚拟容量与物理时序不可互换 |
| P0 | 通用固件安全 | 运行态 ACL/许可、真机安全配置和更多真实业务 | 静态声明、镜像摘要自洽不等于设备 trust/ACL |
| P0 | 真机同路径 | 代表设备同固件 SHA 的 hardware validation | 当前仓库没有可继承的硬件结论 |
| P1 | 服务池与调度 | warm pool、配额、对象存储、审计和多机容量 | 当前仍是单机按需执行 |
| P1 | Tab5 P4 后端 | CSI、I2S/PCM、USB Host、SDIO、动态 I2C 和 controller touch | 闭源后端缺执行路径 |
| P1 | 设备视觉保真 | 逐设备结构、材质、hitbox 和视觉回归 | 功能 PASS 不等于外观保真 |
| P2 | CardputerZero | 系统、驱动、USB/网络竞态和长期回归 | 独立 Linux 后端不能继承 ESP32 结论 |

## 当前执行顺序

1. `RUNTIME-03`：timer、WDT mask、stateful SSI 和统一 handoff timeline 已
   验证。三次 WDT liveness 都显示 TG0 stage-1 首次 reset、TG1 仍 live；
   WDT-off 45/120 秒对照显示 Flash 工作约在 44 秒结束，随后 CPU0 idle、
   CPU1 在同一 `0x40100049` flag/object 上持续等待。PC 地址有效，但 local
   UIFlow2 v2.5.3 ELF 与 public legacy v1.15.4 BIN 字节不一致，不能复用
   符号。下一步识别这个 late-boot object。
2. `NET-04`：把已验证的单机 worker 边界推进到物理跨主机和完整 side-effect
   ownership。
3. `CORE2-02`：补更大规模、持续吞吐、其他 teardown 和物理/controller 等价性。
4. `FW-01/02/03`：补运行态权限/许可、真机安全配置和真实业务覆盖。
5. `RUNTIME-02/04`、`HW-01`：补 C6 Zigbee、ATECC608 和真机同路径。
6. `SVC-01/02/03`、`TAB5-01`、`UI-01`、`CZ-01`：服务化和专项收尾。

## 依赖与并行原则

| 类别 | Task | 开始条件 | 与其他工作的关系 |
| --- | --- | --- | --- |
| 立即可做 | `RUNTIME-03`、`FW-01`、`FW-03`、`SVC-03`、`UI-01` | 当前仓库、测试和本地 runtime 可用 | `RUNTIME-03` 触碰 Core2 QEMU 时与 `CORE2-02` 串行；`SVC-03` 先做无语义移动并保持 API/evidence 契约 |
| 需要多机环境 | `NET-04`、`SVC-01`、`SVC-02` | 至少两个可失联、可 drain、可独立寻址的执行节点 | `SVC-01/02` 的跨主机部分依赖 `NET-04`；单机 namespace/container 结果不能替代 |
| 需要真机或外部控制面 | `FW-02`、`HW-01` | 同固件 SHA 的设备控制、串口、画面、网络和外设观测入口 | `FW-02` 还必须取得 live eFuse/生产 key 流程授权；静态镜像分析不能代填 |
| 后端/ELF 阻塞 | `RUNTIME-02`、`RUNTIME-04` | 可重建 802.15.4 MAC 路径，或公开固件匹配 ELF、ATECC608 命令与测试配置 | 在 blocker 消除前保持 `PARTIAL`/`runtime_model_gap`，不承诺完整兼容 |
| 决策或独立后端 | `TAB5-01`、`CZ-01` | P4 backend 重建/扩展决策；CardputerZero Linux 回归资源 | 不继承 S3/C6/Core2 的完成度，可与主线并行 |

## 可执行任务板

| ID | 状态 | 下一项最小交付 | 验收 |
| --- | --- | --- | --- |
| `RUNTIME-03` | 进行中 | `0041` plus WDT-off 45/120 秒状态把失败收敛到约 44 秒后 CPU1 `0x40100049` wait：A2+24 保持 1，但 A10+28 为 0。下一项是识别该 flag/object 和最后启动 phase；matching ELF/MAP 可并行 | 同固件 SHA 在正常 WDT、真实 Flash 数据面下渲染非空应用帧并保持运行；stateful batch、timer/WDT liveness 与 late-state 对照保持可重放 |
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
| `CZ-01` | 待做 | CardputerZero 系统、驱动和长期回归 | 启动、USB、网络、音频、摄像头和真机边界明确 |

## P0：Core2 legacy UIFlow 运行时

### RUNTIME-03

已满足的前置基线：shared I2C、equal-deadline timer、WDT mask、stateful
SSI、handoff timeline/state sweep/setter trace、三次 WDT liveness 和
WDT-off 45/120 秒 late-state 捕获均可重放。

上述结果都没有把 legacy 固件变成产品 PASS。精确时间线、哈希和检查数只在
[验证证据台账](validation-ledger.md)；缺口语义见
[运行时模型缺口登记](runtime-model-gap-register.md)。

当前阻断：

- normal-WDT 在同一 public legacy SHA 上仍由 TG0 stage-1 触发首次 system
  reset，reset CPU PC 为 `0`，没有非空应用帧；
- 关闭 WDT 只作为诊断 control 后，Flash/SSI 活动约在 44 秒结束，但 CPU1
  到 120 秒仍停在 `0x40100049` 的 flag/object wait，无 setup/REPL；
- 当前 local UIFlow2 ELF 与该 BIN 字节不一致，late object 不能命名；
  `Core2FactoryTest` 在 I2C 修复后仍未重跑。

开放范围：

1. 取得 public `UIFlow_Core2 v1.15.4` 的 matching ELF/MAP。byte audit 已证明
   local UIFlow2 v2.5.3 ELF 不能用于符号命名；
2. 在 matching symbol 缺失时，沿 BIN 的 call/return 和数据结构访问绑定
   `0x40100049`、`A2+24`、`A3`、`A10+28`，确定 flag 的生产者、消费者和
   最后一次可能释放点；
3. 关联最后 SSI 活动（约 44 秒）、cross-core writes 与 late loop，回答
   “Flash 工作结束后为何没有进入 setup/REPL”；保留 `0036` stateful SSI
   数据面，不使用 `blk_pread` bypass；
4. 在 normal WDT 下把 TG0 stage-1、TG1 feed、interrupt mask 和 late phase
   放回同一条启动时间线，解释 reset 与 late state 的关系；
5. 保持同一 public SHA 的 AXP2101/AXP192 A/B 对照，并重跑
   `Core2FactoryTest` 与 Core2 UIFlow2 设备组，防止 shared bus 回归。

验收：

- 已满足的最小 probe 首启动门禁继续可重放，且业务补丁不包含 trace/ring；
- 同一 UIFlow 固件 SHA 在正常 WDT、`0036` stateful SSI/m25p80 数据面下
  出现非空应用帧并稳定运行；不得依赖 `M5SW_DISABLE_WDT`、bulk-read
  bypass、accelerator override 或 retry；
- legacy TG0/TG1 reset 的触发点有证据，shared bus、TIMG trace 和 Core2
  UIFlow2 外设组回归保持 PASS；
- matching ELF/MAP 或 direct runtime trace 能解释 WDT-off late loop 和
  normal-WDT TG0 stage-1 reset 的关系；失败 trace、设备未建模部分和固件
  行为分开记录。

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

已满足的前置基线：Manifest、WebBurner、公开 CDN 强制刷新、SHA-bound
expectation、SD/NVS fixture、静态/文件系统审查和网络-first 执行路径可用的
样本已进入状态页与台账。

开放范围：

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

当前缺口：StopWatch 是唯一参考质量外壳，CoreS3/StickS3 有专门 renderer；
其余设备仍是通用近似外壳。每台设备需要结构尺寸、面板开孔、材质、hitbox
和截图阈值。

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
