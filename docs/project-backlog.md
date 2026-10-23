# 项目 Backlog

日期：`2026-10-24`

本文只记录**尚未完成**的工作、依赖和验收条件。已有能力、验证日期和证据
统一见 [项目当前状态](project-status.md)，代码与测试入口见
[代码与验证入口地图](code-map.md)。

## 使用规则

- 有代码、单元测试或一次 virtual-device evidence，不等于正式 CI、生产隔离
  或真机能力已经完成。
- 任务只有满足“验收”后才能移到当前状态页；不得在 Backlog 中保留完成日志。
- 每个 PASS 必须绑定设备、runtime/profile、固件 SHA 和可复现 evidence。
- 仿真结果必须标记 virtual-device；RF、功耗、声学、光学、机械和电气结论
  必须来自真机。

## 优先级总览

| 优先级 | 工作流 | 完成标准 | 依赖 / 风险 |
| --- | --- | --- | --- |
| P0 | 网络策略与 worker | 双设备 fabric、自托管 QEMU worker 生命周期 | Linux worker；QEMU network backend；fail-closed |
| P0 | Core2 生产化 | 去掉 GDB 暂停/注入/return 控制、重复 lease 稳定门禁、controller/baseband 语义、物理 cache/PSRAM、coexistence/soak | classic ESP32 BT/PHY；真机 |
| P0 | 通用固件审查 | SPIFFS、权限/许可策略、真机 eFuse/安全启动/key 流程、跨厂商回归 | 多格式镜像；生产安全配置 |
| P0 | 真机同路径验证 | 代表设备用同固件 SHA、同测试计划通过 UART/画面/网络/外设 | 物理设备和测试槽 |
| P1 | 外部 IPv6 egress | v6 veth/route/NAT 与 exact endpoint 规则 | worker 双栈配置；当前 IPv6 请求会被拒绝 |
| P1 | 服务 worker 与调度 | supervisor、heartbeat、drain/re-attach、warm pool、多机容量 | 生产部署；对象存储；审计 |
| P1 | Tab5 后端补齐 | I2S/PCM、CSI、USB Host、SDIO、动态 I2C、ST7123、IP2326 | 可扩展 P4 backend 或重建 |
| P1 | 设备视觉保真 | 逐设备结构、材质、hitbox 和视觉回归 | 官方尺寸/结构资料 |
| P2 | CardputerZero 收口 | 系统、驱动、USB/网络竞态和长期回归 | 独立 Linux ARM64 后端 |

## 当前执行顺序

1. `CORE2-01` / `HCI-3b`：单包 C2H callback 已通过，继续稳定完整 Bumble
   HCI/GATT sequence。
2. `CORE2-01` / `HCI-4`：用同一 stock 固件通过 Device Service repeated
   lease `5/5`，再删除 GDB callback 注入和 synthetic return。
3. `NET-03`：完成双设备 lab fabric。
4. `NET-04` / `SVC-01`：把 Linux policy CI 和 QEMU evidence 路径接入正式
   worker。
5. `FW-01`：完成 SPIFFS、权限和许可策略；FAT12/16/32 已进入主线。
6. `FW-03/02`：扩跨厂商样本，再补生产 key/eFuse 与真机路径。
7. `CORE2-02`、`HW-01`、`NET-05`：controller/物理边界、同路径真机证据和
   外部 IPv6 端点策略。
8. Tab5、worker pool、视觉保真和 CardputerZero 作为后续专项推进。

## 可执行任务板

| ID | 状态 | 下一项最小交付 | 验收 |
| --- | --- | --- | --- |
| `NET-03` | 待做 | 两个 guest 的 private lab fabric | 两台 guest 只通过预期 fabric 通信，宿主 LAN/控制面不可达 |
| `NET-04` | 进行中 | GitHub Actions 已跑 namespace/egress；继续接 QEMU runtime、pcap/reconnect 和正式 worker | CI 可重复产出 evidence；namespace 失败保持 fail-closed；worker 可 drain/re-attach |
| `NET-05` | 待做 | 外部 IPv6 exact endpoint 的 nftables + gateway 路径 | 允许/拒绝可重复，veth/NAT 与清理有同次 evidence |
| `CORE2-01` | 进行中 | ELF 符号查询已固定；`HCI-1` PASS、`HCI-2` 首包 PARTIAL、`HCI-3a` 单包 C2H callback `5/5`；下一最小交付是 `HCI-3b` 完整 HCI/GATT，随后 `HCI-4` repeated lease | 同一 stock 固件通过 Device Service `5/5`；最终无 GDB 完成外部 NUS GATT，evidence 不回退 |
| `CORE2-02` | 待做 | BT controller/baseband 语义、物理 cache/PSRAM、coexistence/soak | controller 协议与真机收敛；物理边界和长时间稳定性可证 |
| `FW-01` | 进行中 | 评估并实现 SPIFFS 只读 parser/host helper；继续补权限与许可策略 | 文件系统返回可验证清单或明确 `UNSUPPORTED`；权限/许可结论可追踪 |
| `FW-02` | 进行中 | 包内安全摘要已支持；继续做真机 eFuse、secure boot、Flash Encryption 和生产 key 流程 | 支持矩阵与拒绝路径明确，敏感 key 不入库 |
| `FW-03` | 待做 | ESP-IDF/Arduino/MicroPython/vendor 固件回归集 | 每个样本记录导入、capability、boot 层，不混算 PASS |
| `SVC-01` | 待做 | worker supervisor、注册/心跳、drain、re-attach | 服务重启可收敛 worker，lease 有明确接管或失败状态 |
| `SVC-02` | 待做 | warm pool、队列、配额、对象存储和审计 | latency/CPU/RSS/queue/GC 可观测，租户状态不泄漏 |
| `SVC-03` | 待做 | 拆分 `device_service.py` 的固件存储、运行时适配器、证据和会话状态机 | 对外 API/evidence 不回归；单文件职责和测试边界清晰 |
| `HW-01` | 待做 | 代表设备同固件 SHA 的真机测试计划 | evidence 明确标为 hardware validation，虚拟结果不冒充 |
| `TAB5-01` | 决策 | 重建或扩展 P4 backend | 关闭 CSI、I2S/PCM、USB Host、SDIO、动态 I2C 和 ST7123 |
| `UI-01` | 待做 | 逐设备高保真外壳、hitbox 和截图阈值 | 每台设备有独立尺寸/结构/回归，不只改通用 CSS |
| `CZ-01` | 待做 | CardputerZero 系统与驱动长期回归 | 启动、USB、网络、音频、摄像头和真机边界明确 |

## P0：网络策略、隔离与 CI

### NET-03 双设备 fabric

交付：

- 两台 guest 位于独立 namespace 和唯一 bridge/fabric；
- 只允许预期 peer 和端口；
- host-to-device 入口、workstation LAN、云元数据和控制面均不可达。

### NET-04 CI 与 worker

交付：

- GitHub Actions 的完整平台测试和 namespace/egress fail-closed 回归已完成；
- QEMU runtime、pcap retention、reconnect evidence 进入自托管 Linux worker；
- worker 注册、心跳、drain、重排和 evidence 上传可观测；
- namespace 创建/权限失败时 fail-closed；
- 超时、残留进程、临时盘和失败重试都有结构化结果。

## P0：Core2 生产化

### CORE2-01 无 GDB VHCI

实现路线和阶段验收见
[Core2 native HCI backend](core2-native-hci-backend.md)。

阶段状态：

| 阶段 | 状态 | 已证明 | 仍未证明 |
| --- | --- | --- | --- |
| `HCI-1` host transport | `PASS` | H4 command/event/ACL/SCO framing、32 packet bounded queue、overflow/drop、peer lifecycle、counters、clean shutdown | guest VHCI 数据面 |
| `HCI-2` H2C | `PARTIAL` | 不启动 GDB，从真实 VHCI shared memory 捕获 stock HCI Reset `01030c00` | controller response 后的完整 H2C 命令序列 |
| `HCI-3a` C2H callback | `PASS` | Reset Complete 经 firmware `notify_host_recv` 交付，callback status 0，send-available 后 guest 发出下一条 H2C；targeted `5/5` | packet order/flow control 和完整 controller sequence |
| `HCI-3b` complete sequence | `OPEN` | 探索性 Bumble 运行可到广播/连接 | 完整 HCI init、ATT/GATT service discovery 必须稳定，不靠 retry |
| `HCI-4` stability | `OPEN` | 现有 GDB 诊断桥有过单 lease PASS | Device Service 连续 `5/5`、无 GDB callback injection/synthetic return、故障分类 |

已经完成：

- 从匹配 Xtensa ELF 解析 `API_vhci_host_send_packet`、`vhci_env_p` 和
  `esp_cpu_wait_for_intr`，Device Service 与独立 runner 传固定地址；
- pinned-symbol standalone 外部 NUS GATT `5/5`；
- pinned-symbol 同 guest board+WiFi+公网+native-VHCI BLE `3/3`；
- Device Service `core2-native-vhci` 已有一个带 symbol event 的单 lease
  PASS；
- QEMU `H4 transport-only` targeted test `11/11` PASS；
- 不启动 GDB 捕获首个 stock H2C Reset，QOM 和 dummy peer 字节一致。

仍未完成：

- `HCI-3a` 已把单个 Reset Complete 交给 guest 的注册 callback；`HCI-3b`
  仍需稳定多 packet Bumble event/ACL、广播、连接和 ATT/GATT sequence；
- `HCI-4` 尚无以 Device Service `/api/v1` 连续 `5/5` 的无 GDB 门禁；
- GDB 仍负责 guest 暂停、breakpoint/callback 注入和 synthetic return；
- 尚未形成同 commit、固定次数的重复 Device Service lease 门禁；
- 当前同 commit repeated lease 为 `1/2`。失败时 Bumble C2H
  `LE Set Event Mask` response 在 H2C sender context 调用 host callback
  返回 `2559356`，随后 GDB target-running，guest
  `InstrFetchProhibited` 并重启；
- 尚无 QEMU 内部或无调试器 backend。

交付：

- 先跑固定次数独立 lease，失败分类必须区分 target running、
  `INJECT_REJECTED`、double exception、GDB exit 和 peer timeout；
- 先让 `HCI-3b` 的 QEMU 内部 C2H 完成稳定完整数据面，再由
  `HCI-4` 验证 Device Service `5/5`；
- 同一 stock 固件和 ELF 通过 scan/connect/NUS subscribe/write/notify；
- Device Service 单 lease、pcap、bridge log 和 peer evidence 不回退。

### CORE2-02 controller 与物理边界

交付：

- Espressif BT controller/baseband 协议语义，而不是只在 VHCI 边界替换；
- physical cache/PSRAM 对比、coexistence、throughput 和 long soak；
- 真机同路径证据区分 virtual/firmware/hardware 结论。

## P0：通用固件审查

### FW-01 文件系统与权限

LittleFS 和 FAT12/16/32 已支持文件/目录、大小、SHA256、敏感路径脱敏和
SPDX；FAT parser 包含 LFN 校验、循环链拒绝、目录/文件上限和 erased
partition 分类。下一项是 SPIFFS 只读 parser 或基于 ESP-IDF 的可审计 host
helper；实现前保持 `UNSUPPORTED`。

验收：

- SPIFFS 返回可验证清单或明确 `UNSUPPORTED`；
- 资源项记录来源、哈希、权限策略和许可结论；
- `unknown` 安全状态不能被写成 PASS；
- 所有 listing 有截断标记和资源上限。

### FW-02 安全配置

- 包内 sdkconfig、分区 flag、`espefuse summary --format json` 和 key purpose
  已能分层记录；原始 key/value 不复制到输出；
- 仍需识别真机 secure boot、Flash Encryption、eFuse 和 key 状态；
- 明确镜像声明 / 运行态 / 真机验证三层；
- 测试 key、生产 key 和拒绝路径不进入仓库或公开日志；
- 无权威输入时保持 `unknown`。

### FW-03 跨厂商回归

- 扩充 ESP-IDF、Arduino、MicroPython 和 vendor 样本；
- 每样本记录 importer、chip/board/partition、capability 和 boot 层；
- 不得把结构 PASS、UI PASS、功能 PASS 或安全 PASS 混成一个结论。

## P1：服务 worker 与调度

当前是单机模块化单体；历史会话可恢复，但活动 QEMU 进程不能跨服务重启接管。

顺序：

1. supervisor、端口、临时目录和 evidence collector 拆成 worker；
2. 注册、心跳、drain、re-attach 和故障收敛；
3. runtime image cache、少量 warm pool；
4. 队列、配额、对象存储、retention、审计和租户隔离；
5. 可疑固件使用 disposable VM / copy-on-write flash；
6. 观测 start latency、CPU/RSS、queue time、失败率和 cleanup。

### SVC-03 Device Service 编排拆分

`platform/tools/device_service.py` 是大型单文件编排热区，同时承担会话模型、
固件存储、QEMU/esp-emu 启动、网络策略、输入、证据、历史恢复和 HTTP 适配。
继续叠加能力会扩大回归面；规模以当前源码为准，不在文档保存易漂移的行数。

拆分顺序：

1. 先固定 `/api/v1`、session JSON、evidence ZIP 和历史恢复的契约测试；
2. 拆出 content-addressed firmware/artifact store；
3. 拆出 QEMU、Tab5、network 三类 runtime adapter；
4. 拆出 evidence collector 和 lifecycle/history repository；
5. 最后收敛 HTTP handler，不在拆分过程中改变 API 语义。

验收必须保留当前平台测试、目标设备 unified lease、停止后历史恢复和
evidence ZIP 的字段兼容性。

## P1：Tab5

当前是 `partial`：virtual flash、boot、1280×720 framebuffer、touch mailbox、
RS-485、C6 ESP-Hosted 和静态 I2C 可用。

未完成：

- dynamic I2C/RTC/IMU/INA226/PI4IOE/IP2326 状态机；
- P4 I2S/PCM、ES7210/ES8388；
- MIPI-CSI/SC2356；
- P4 USB Host；
- SDIO block backend；
- controller-level ST7123 touch；
- P4↔C6 ESP-Hosted end-to-end association/DHCP/DNS/TCP。

先决定重建/扩展 P4 backend；没有该前提不承诺日期。详见
[Tab5 暂缓项](tab5-deferred-backlog.md) 和
[P4 外设后端要求](p4-peripheral-backend-requirements.md)。

## P1：视觉保真

StopWatch 是当前唯一参考质量外壳。其余设备需要独立完成尺寸、分层机体、
屏幕开孔、按键、接口、材质、物理 hitbox、framebuffer clipping 和截图阈值。

见 [设备视觉保真 Backlog](device-visual-fidelity-backlog.md)。

## P2：CardputerZero

CardputerZero 是独立 ARM64 Linux 后端，不属于 ESP32/UIFlow2 `/api/v1`
设备路径。仍缺完整启动/服务回归、USB split timing、网络性能与隔离、
摄像头/音频/电源/键盘 soak 和真机同路径验证。

## 发布门禁

发布或外部结论前至少完成：

1. 最新平台测试、runtime coverage、peripheral catalog 和 QEMU profiles check；
2. 受影响设备组 targeted matrix；
3. 共享 QEMU/控制器变更时跑最新 67-case 全矩阵；
4. 用目标 commit 和同主机架构重建 runtime；
5. 声明分层为 hardware validation 或 virtual-device validation；
6. 更新 README、当前状态、API/OpenAPI、专题文档和工作记录；
7. 外部结论附 full-commit-SHA permalink 和可复现 evidence。
