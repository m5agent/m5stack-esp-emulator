# 项目 Backlog

日期：`2026-10-24`

本文只记录**尚未完成**的工作、优先级、依赖和验收条件。当前能力、已闭合
边界和风险见 [项目当前状态](project-status.md)，历史验证见
[验证证据台账](validation-ledger.md)，代码入口见
[代码与验证入口地图](code-map.md)。

## 使用规则

- 任务只有满足本节对应“验收”后才能从 Backlog 移到当前状态页或证据台账。
- 本页不保存完成日志。若需要理解某个未完成项从哪里起步，只引用当前代码、
  测试入口和仍未满足的条件。
- 每个 PASS 必须绑定设备、runtime/profile、固件 SHA 和可复现 evidence。
- virtual-device 结果与 hardware validation 分开记录；RF、功耗、声学、
  光学、机械和电气结论必须来自真机。
- 安全状态未知必须保持 `unknown`/`REVIEW`，不能为了推进任务写成 PASS。

## 优先级总览

| 优先级 | 工作流 | 完成标准 | 主要依赖 / 风险 |
| --- | --- | --- | --- |
| P0 | 网络产品化 | 持久任务队列、worker supervisor、调度和活动 QEMU re-attach | Linux worker；远程注册目录；证据回传 |
| P0 | Core2 native HCI | 无 GDB 完成完整 HCI/GATT，并连续 `5/5` | classic ESP32 VHCI queue/IRQ 语义或 in-process controller |
| P0 | 通用固件安全 | 权限/许可、安全启动/Flash Encryption/key 流程、跨厂商回归 | 多格式镜像；真机安全配置 |
| P0 | 真机同路径验证 | 代表设备使用同固件 SHA 和同测试计划通过 | 物理设备、测试槽、证据采集 |
| P1 | 外部 IPv6 | exact IPv6 endpoint、veth/route、NAT 和清理 | worker 双栈；nftables |
| P1 | 服务池与调度 | warm pool、配额、对象存储、审计、多机容量 | supervisor、监控、隔离 |
| P1 | Tab5 P4 后端 | 关闭 CSI、I2S/PCM、USB Host、SDIO、动态 I2C、ST7123 | 可重建或可扩展 P4 backend |
| P1 | 设备视觉保真 | 逐设备结构、材质、hitbox 和视觉回归 | 官方尺寸/参考图 |
| P2 | CardputerZero 收口 | 系统、驱动、USB/网络竞态和长期回归 | 独立 Linux ARM64 后端 |

## 当前执行顺序

1. `CORE2-01`：`HCI-3b` 已用 `0003`/`0004` patch 和合法 17-byte ATT PDU
   连续 `5/5` 完成外部 NUS GATT；下一项只做 `HCI-4`，把同一路径接入
   Device Service 并从生产调用中移除 GDB 诊断桥。
2. `NET-04` / `SVC-01`：在本地 worker lifecycle 和远程注册目录基础上完成
   持久队列、worker supervisor、调度和活动实例 re-attach；`NET-05` 独立
   推进 IPv6。
3. `FW-01`：补运行时权限、完整源码级许可扫描和法律审批；随后 `FW-03`
   扩跨厂商样本，
   `FW-02` 做生产 key/eFuse 与真机安全配置。
4. `CORE2-02`、`HW-01`：controller/baseband 物理边界和同路径真机证据。
5. `SVC-02`、`SVC-03`、`TAB5-01`、`UI-01`、`CZ-01`：服务化、专项后端和
   视觉工作，不与当前 P0 混算完成。

## 可执行任务板

| ID | 状态 | 下一项最小交付 | 验收 |
| --- | --- | --- | --- |
| `NET-04` | 进行中 | 持久任务队列、worker supervisor、调度和活动 QEMU re-attach | worker 失联/重启可收敛；namespace 失败 fail-closed；evidence 可回传 |
| `NET-05` | 待做 | 外部 IPv6 exact endpoint 的 nftables + gateway 路径 | 允许/拒绝可重复，veth/route/NAT 与清理有同次 evidence |
| `CORE2-01` | 进行中 | `HCI-4` Device Service repeated lease 与 GDB 控制面移除 | 同一 stock 固件无 GDB 完成 NUS GATT，Device Service `5/5` |
| `CORE2-02` | 待做 | bit-exact controller/baseband、物理 cache/PSRAM、coexistence 和 soak | 物理边界可证；真机/RF 结论不冒充 |
| `FW-01` | 进行中 | 运行时权限、完整源码级许可扫描与法律审批 | 文件清单可追踪；声明策略、资源权限和最终许可结论可审计且不混算 |
| `FW-02` | 进行中 | 真机 secure boot、Flash Encryption、eFuse 和生产 key 流程 | 支持矩阵与拒绝路径明确，敏感 key 不入库 |
| `FW-03` | 待做 | ESP-IDF/Arduino/MicroPython/vendor 跨厂商回归集 | 每样本分层记录导入、capability、boot 和功能 |
| `SVC-01` | 进行中 | 持久队列、远程 supervisor 与活动 QEMU re-attach 契约 | 服务重启可接管或明确失败，不产生假 running |
| `SVC-02` | 待做 | warm pool、队列、配额、对象存储和审计 | latency/CPU/RSS/queue/GC 可观测，租户状态隔离 |
| `SVC-03` | 待做 | 拆分 `device_service.py` 的存储、runtime、evidence 和 session 状态机 | 对外 API/evidence 不回归；模块边界有契约测试 |
| `HW-01` | 待做 | 代表设备同固件 SHA 的真机测试计划 | evidence 明确标为 hardware validation |
| `TAB5-01` | 决策 | 重建或扩展 P4 backend | CSI、I2S/PCM、USB Host、SDIO、动态 I2C、ST7123、IP2326 有执行路径 |
| `UI-01` | 待做 | 逐设备高保真外壳、hitbox 和截图阈值 | 每台设备独立结构证据和视觉回归 |
| `CZ-01` | 待做 | CardputerZero 系统、驱动和长期回归 | 启动、USB、网络、音频、摄像头和真机边界明确 |

## P0：网络与 worker

### NET-04 远程 worker

当前缺口：

- 本地 worker identity、generation、heartbeat、drain/resume、
  abandoned lease 和 bounded result 已实现；
- 远程 worker 注册目录已实现 identity/generation、heartbeat、drain/stop、
  capability 和有界结果元数据，但它只是目录，不是 supervisor；
- 没有持久任务队列、跨 worker 调度、容量租约和多机状态收敛；
- 服务重启后，仍在运行的活动 QEMU 进程不能 re-attach；
- 双 guest lab fabric 和 Linux policy CI 尚未成为自托管 worker 的正式
  调度与 evidence replay 路径。

下一项最小交付：

1. 在现有 register/heartbeat/drain/result 契约上实现远程 worker supervisor
   与失联收敛。
2. 定义任务提交、排队、租约、取消、重试和 evidence 回传状态机。
3. 对活动 QEMU 实现“重新接管”或明确 `interrupted_failed`，禁止假装仍在
   running。
4. 把 namespace、pcap、session history 和 cleanup 结果绑定到同一个 lease。

验收：

- worker 强杀、重启、失联和 drain 都有确定终态；
- 远程 worker 的 Linux policy 失败时 fail-closed；
- 任务、实际执行 worker、generation、QEMU 进程和 evidence 可关联；
- 活动实例 re-attach 有重复测试和清理证据。

### NET-05 外部 IPv6

当前缺口：exact IPv4 IP/protocol/port 已通过，外部 IPv6、IPv6 DNS、
veth/route、NAT 和清理尚未实现；IPv6 请求必须继续拒绝，不能隐式放行。

验收：允许与拒绝端点可重复；policy、guest 访问、pcap 和 cleanup 在同一次
evidence 中成立。

## P0：Core2 native HCI

设计见 [Core2 native HCI backend](core2-native-hci-backend.md)。

### CORE2-01 `HCI-4`

当前缺口：

- `HCI-3b` 独立 runner 已使用 `0003` API-boundary H2C 和 `0004`
  CCOUNT TB-yield patch，经 HLI event/ACL 完成外部 NUS GATT `5/5`。
  旧失败已确认来自 21-byte probe 形成 24-byte ATT PDU、超过默认 MTU 23；
  这不是 controller 或 guest handler 缺陷。
- Device Service 的生产 `core2-native-vhci` profile 仍使用 GDB 暂停、
  callback 注入和 synthetic return；同 commit repeated lease 只有 `1/2`。
- QEMU native-HCI 路径尚未进入 `/api/v1` 的完整 lease 生命周期、证据包、
  停止/失败分类和 repeated 门禁。
- 单次 runner 中的 peer teardown 会产生 post-pass H2C `EIO`；它不影响已
  完成的事务，但 Device Service 必须区分事务内错误与 session 关闭噪声。

下一项最小交付：

1. 将 `0003`/`0004` 和对应 QEMU build fingerprint 纳入 Device Service
   native-HCI profile，不再调用 GDB bridge。
2. 用同一个 `/api/v1` lease 同时采集 frame、QOM、WiFi/DNS/HTTP、HLI、
   Bumble peer、pcap 和 final evidence。
3. 连续 `5/5`；失败必须区分 transaction error 与 BLE peer 断开后的
   teardown error，禁止 retry 后只保留成功次数。
4. 通过门禁后删除 `HCI-4` 的生产 GDB callback injection/synthetic return，
   保留显式诊断模式。

验收：

- 同一 stock 固件 SHA、ELF SHA、QEMU build 和 profile；
- 无 GDB callback injection 或 synthetic return；
- Device Service `/api/v1` 连续 `5/5` 完成外部 NUS GATT；
- frame、QOM、WiFi/公网、pcap 和 peer evidence 不回退。

### CORE2-02 物理与 controller 边界

仍未完成：

- bit-exact Espressif BT controller/baseband，而不是 VHCI 边界替换；
- 物理 cache/PSRAM 时序对比；
- coexistence、throughput 和 long soak；
- 同固件路径真机验证。

## P0：通用固件审查

### FW-01 文件系统、权限与许可

当前缺口：LittleFS、FAT12/16/32 和常见 ESP-IDF SPIFFS 配置已有只读清单；
provenance/文件系统/SBOM 声明已可汇总为显式 allowlist/denylist 决策，且
未配置 allowlist、无声明和未知表达式会保持 `REVIEW_REQUIRED`。运行时文件
权限、完整源码级许可扫描和真实法律审批仍开放。

验收：

- 不支持的 SPIFFS 配置明确返回 `INVALID`，不能猜测文件名；
- 每个资源项记录来源、哈希、权限策略和在适用时的许可结论；
- listing 有资源上限和截断标记；
- 许可策略区分声明、未知、允许、拒绝和法律结论；
- `unknown` 安全状态不能被写成 PASS。

### FW-02 真机安全配置

当前缺口：包内 sdkconfig、分区 flag、脱敏 eFuse summary 和 capability
preflight 已有；真机 secure boot、Flash Encryption、eFuse 和生产 key
状态尚未闭环。

验收：明确区分镜像声明、运行态和真机验证；测试/生产 key 不进入仓库或公开
日志；无权威输入时保持 `unknown`。

### FW-03 跨厂商回归

当前缺口：ESP-IDF、Arduino、MicroPython 和 vendor 固件样本覆盖仍不足。

验收：每个样本记录 importer、chip/board/profile、partition、capability、
boot 和功能层；结构 PASS、UI PASS、功能 PASS、安全 PASS 不混算。

## P0：真机同路径

### HW-01

当前缺口：现有能力全部是 virtual-device validation，没有可引用的同固件
SHA 真机记录。

验收：代表设备用同固件 SHA、同测试计划和相同关键输入运行；明确标注
`hardware validation`，并保留串口、画面、网络/外设和必要测量证据。

## P1：服务化与代码整理

### SVC-01 活动实例接管

与 `NET-04` 共用 worker 状态机。先完成“接管或明确失败”，再实现 warm pool；
不能把已失去父进程的 QEMU 子进程默认为 running。

### SVC-02 服务池

仍未做 warm pool、队列、配额、对象存储、审计、多租户隔离和容量指标。
不可信固件最终需要 disposable VM / copy-on-write flash，而不是当前单机
namespace 即视为恶意代码沙箱。

### SVC-03 编排拆分

`platform/tools/device_service.py` 仍是大型编排热区，覆盖 session、存储、
runtime、证据和 HTTP 边界。拆分必须按以下顺序：

1. 固定 `/api/v1`、session JSON、evidence ZIP 和历史恢复契约；
2. 拆 content-addressed firmware/artifact store；
3. 拆 QEMU、Tab5、network runtime adapters；
4. 拆 evidence collector 和 lifecycle/history repository；
5. 最后收敛 HTTP/orchestration facade。

验收：平台测试、目标 unified lease、停止后历史恢复和 evidence 字段兼容。

## P1：专项

### TAB5-01

当前缺口：动态 I2C/RTC/IMU/INA226/PI4IOE/IP2326、P4 I2S/PCM、MIPI-CSI、
USB Host、SDIO、controller-level ST7123 和 P4↔C6 ESP-Hosted 端到端网络。
先决定重建或扩展 P4 backend；当前闭源后端无法给出可靠完成日期。

### UI-01

当前缺口：StopWatch 是唯一参考质量外壳，CoreS3/StickS3 已有专门 renderer，
其余仍是通用近似外壳。逐设备需要结构尺寸、面板开孔、材质、hitbox 和视觉
回归阈值。

## P2：CardputerZero

### CZ-01

当前缺口：完整系统回归、USB split timing、网络性能/隔离、
摄像头/音频/电源/键盘 soak 和真机同路径。

## 发布门禁

发布或外部结论前至少完成：

1. 平台测试、runtime coverage、peripheral catalog 和 QEMU profiles check；
2. 受影响设备组 targeted matrix；
3. 共享 QEMU/controller 变更时跑最新 full matrix；
4. 用目标 commit 和同主机架构重建 runtime；
5. 更新当前状态、证据台账、API/OpenAPI、专题页和发版说明；
6. 外部结论附 full-commit-SHA permalink，并明确验证层级。
