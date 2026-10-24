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
| P0 | 网络产品化 | 跨主机 executor、TLS/mTLS、credential rotation、companion/evidence continuity、跨主机 reattach 和生产调度 | durable queue/lease supervisor；同主机 authenticated executor；本地 QEMU/QMP reattach |
| P0 | 通用固件安全 | 权限/许可、安全启动/Flash Encryption/key 流程、跨厂商回归 | 多格式镜像；真机安全配置 |
| P0 | 真机同路径验证 | 代表设备使用同固件 SHA 和同测试计划通过 | 物理设备、测试槽、证据采集 |
| P1 | 外部 IPv6 | exact IPv6 endpoint、veth/route、NAT 和清理 | worker 双栈；nftables |
| P1 | 服务池与调度 | warm pool、配额、对象存储、审计、多机容量 | supervisor、监控、隔离 |
| P1 | Core2 长稳与物理/controller 等价性 | 在已通过的十轮 reconnect 上扩大到当前 1–10 API 上限之外的轮次，并扩大 `5×10s` / `3×60s` / `2×120s` 到多小时 soak/coexistence，再评估 bit-exact controller、cache/PSRAM | 十轮 GATT 与 active hold 已通过；物理或权威模型证据 |
| P1 | Tab5 P4 后端 | 关闭 CSI、I2S/PCM、USB Host、SDIO、动态 I2C、ST7123 | 可重建或可扩展 P4 backend |
| P1 | 设备视觉保真 | 逐设备结构、材质、hitbox 和视觉回归 | 官方尺寸/参考图 |
| P2 | CardputerZero 收口 | 系统、驱动、USB/网络竞态和长期回归 | 独立 Linux ARM64 后端 |

## 当前执行顺序

1. `NET-04` / `SVC-01`：在 durable queue、同主机 HTTP executor、远程注册
   目录、lease supervisor、worker HMAC 和本地 QEMU/QMP reattach 基础上补
   跨主机 executor/reattach、TLS/mTLS、credential rotation、
   companion/evidence continuity 和多机调度；`NET-05` 独立推进 IPv6。
2. `FW-01`：补运行时权限、完整源码级许可扫描和法律审批；随后 `FW-03`
   扩跨厂商样本，
   `FW-02` 做生产 key/eFuse 与真机安全配置。
3. `CORE2-02`：`5×10s`、`3×60s`、`2×120s` extended-run 和同 guest 十轮
   reconnect 已通过；下一项扩大当前 1–10 API 上限、补多小时 soak 和 WiFi/BLE
   coexistence。之后处理 controller/baseband 物理边界。`HW-01` 独立推进
   同路径真机证据。
4. `SVC-02`、`SVC-03`、`TAB5-01`、`UI-01`、`CZ-01`：服务化、专项后端和
   视觉工作，不与当前 P0 混算完成。

## 可执行任务板

| ID | 状态 | 下一项最小交付 | 验收 |
| --- | --- | --- | --- |
| `NET-04` | 进行中 | 跨主机 executor/reattach、TLS/mTLS、credential rotation、companion/evidence continuity、生产调度 | worker 重启后 job/evidence 可收敛；namespace 失败 fail-closed；活动实例不产生假 running |
| `NET-05` | 待做 | 外部 IPv6 exact endpoint 的 nftables + gateway 路径 | 允许/拒绝可重复，veth/route/NAT 与清理有同次 evidence |
| `CORE2-02` | 进行中 | 已通过 3 个 lease 各自 10 轮的 GATT 与 `5×10s`、`3×60s`、`2×120s` active hold；下一项扩大当前 1–10 API 上限，再做多小时 hold 和 WiFi/BLE coexistence | 同一 guest 超过 10 轮完整 scan/connect/GATT/disconnect 无 retry PASS；每轮保留 serial/peer/pcap/evidence 与 HLI health；随后补 controller/baseband、物理 cache/PSRAM |
| `FW-01` | 进行中 | 运行时权限、完整源码级许可扫描与法律审批 | 文件清单可追踪；声明策略、资源权限和最终许可结论可审计且不混算 |
| `FW-02` | 进行中 | 真机 secure boot、Flash Encryption、eFuse 和生产 key 流程 | 支持矩阵与拒绝路径明确，敏感 key 不入库 |
| `FW-03` | 待做 | ESP-IDF/Arduino/MicroPython/vendor 跨厂商回归集 | 每样本分层记录导入、capability、boot 和功能 |
| `SVC-01` | 进行中 | 跨主机 TLS/mTLS/rotation、companion/evidence continuity 与跨主机 reattach | 服务重启可接管或明确失败，不产生假 running |
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
- durable job queue 已实现幂等提交、capability matching、claim/lease、
  expiry retry、cancel/result 和 worker stale/stop/generation 回收；
- 同主机 HTTP executor 已能 claim job、运行真实 session、下载 evidence
  ZIP/SHA256 并回报；启用 API token 时 worker-only mutation 已有
  worker/generation HMAC、timestamp/nonce replay 防护；没有跨主机
  TLS/mTLS、credential rotation、跨 worker 容量调度和多机状态收敛；
- 本地 QEMU/QMP 控制面可在 PID start-time、QMP ownership 和
  `query-status=running` 验证后 re-attach；Tab5/network lane、paused QEMU、
  companion HTTP/BLE helper、evidence 流和跨主机进程仍不能接管；
- 双 guest lab fabric 和 Linux policy CI 尚未成为自托管 worker 的正式
  调度与 evidence replay 路径。

下一项最小交付：

1. 在现有同主机 HMAC executor 上补跨主机 TLS/mTLS、credential rotation
   和外部 side-effect fencing，禁止旧 agent 覆盖新 generation。
2. 实现跨 worker 容量调度、持久 evidence 存储、幂等重放和队列审计。
3. 在本地 QEMU/QMP reattach 之上补 companion 状态重建、evidence 流连续性和
   跨主机接管；无法证明 ownership 时明确 `interrupted_failed`。
4. 把 namespace、pcap、session history 和 cleanup 结果绑定到同一个 lease。

验收：

- worker 强杀、重启、失联和 drain 都有确定终态；
- 远程 worker 的 Linux policy 失败时 fail-closed；
- 任务、实际执行 worker、generation、QEMU PID/start time 和 evidence
  可关联；
- 本地 reattach 有 PID reuse、stale start-time、QMP 缺失、正常停止和残留清理
  证据；跨主机/companion reattach 仍待补。

### NET-05 外部 IPv6

当前缺口：exact IPv4 IP/protocol/port 已通过，外部 IPv6、IPv6 DNS、
veth/route、NAT 和清理尚未实现；IPv6 请求必须继续拒绝，不能隐式放行。

验收：允许与拒绝端点可重复；policy、guest 访问、pcap 和 cleanup 在同一次
evidence 中成立。

## P1：Core2 物理与 controller 边界

设计见 [Core2 native HCI backend](core2-native-hci-backend.md)。

### CORE2-02 物理与 controller 边界

短时 `5×10s` 门禁已经通过：两批独立运行合计 `10/10`，每轮
`hli-errors=0`、HLI/meta queue 深度为 0。此前失败已定位到两个 QEMU
guest-call 上下文问题并修复：

- 历史失败：`HCI-4 5/5` 之后，带 hold 的独立运行曾在
  READY、WiFi/公网和 BLE 连接之后 panic。一次首轮
  `IllegalInstruction` 落在 `semphr_give_wrapper`
  (`components/bt/controller/esp32/bt.c:677`)，后续
  `InstrFetchProhibited` 形成 reboot loop；另一轮在 attempt 4 直接出现
  `PC=0` panic。失败发生在 hold 检查前，不能归因于“hold 太长”；
- 修复：恢复 nested guest call 的 caller-saved sregs，并只在
  halted/idle vCPU 注入 HLI allocator/callback；
- 后续 `3×60s` hold 也 `3/3` PASS，2 个 `120s` hold 为 `2/2`，覆盖
  BLE peer 正常关闭后的尾态；
- 第一轮 GATT、active-BLE 120 秒 hold 和同一 guest 十轮重连均已通过。
  reconnect blocker 根因是外部 Bumble compatibility 层错误地为无响应的
  `HCI_Host_Number_of_Completed_Packets (0x0c35)` 返回 Command Status；
  下一命令消费 stale ACK 后触发 `BLE_HS_ECONTROLLER (12)` 与 reset。
  QEMU HLI、NimBLE host 连接池和 GATT/L2CAP 池均已排除；
- 仍未完成：超过十轮连接、多小时 soak、吞吐、coexistence 和
  process-stop/teardown 竞态；
- 当前 native-HCI hook 偏移只对已验证的 UIFlow2 v2.5.3 build 成立；
  其他 Core2 固件需要新的符号/偏移校验，不能按 SoC 继承 PASS；
- bit-exact Espressif BT controller/baseband，而不是 VHCI 边界替换；
- 物理 cache/PSRAM 时序对比；
- 同固件路径真机验证。

新调用必须使用 `core2-native-hci`。`core2-native-vhci` 依赖 GDB，只允许
作为显式诊断/兼容路径，不能用来证明稳定生产能力。

验收追加条件：

- 同一 guest 超过 10 轮 scan/connect/NUS GATT/disconnect 无 retry PASS，
  每轮都有 guest RX、notification、peer/pcap/evidence 和 HLI health；
- 在已通过的十轮 reconnect 与 `5×10s` / `3×60s` / `2×120s` 基础上继续多小时 soak；
- runner 在失败时必须输出 aggregate `FAIL`，不能丢 traceback 或只保留成功
  次数；
- 首轮 panic 必须先于 reboot 次生故障被分类和符号化；
- `HCI-4` 历史 `5/5` 可以继续引用，但不得替代新的长稳结果。

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

与 `NET-04` 共用 worker 状态机。本地 QEMU/QMP 已按 PID start-time、QMP
ownership 和 running 状态完成“接管或明确失败”；下一步补 companion
HTTP/BLE helper、evidence 流、Tab5/network lane 和跨主机接管，再实现 warm
pool。不能把已失去父进程或 ownership 不匹配的进程默认为 running。

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
