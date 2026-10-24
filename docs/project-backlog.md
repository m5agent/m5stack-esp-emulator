# 项目 Backlog

日期：`2026-10-25`

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
| P0 | 网络产品化 | 自动发现/跨主机 worker 迁移、跨主机 QEMU executor、companion/evidence continuity、跨主机 reattach 和生产调度 | durable queue/lease supervisor；HTTPS/mTLS；SIGHUP rotation + request drain + bounded credential overlap；同主机 generation-pointer migration + receipts；同主机 authenticated executor；本地 QEMU/QMP reattach |
| P0 | 通用固件安全 | 权限/许可、安全启动/Flash Encryption/key 流程、跨厂商回归 | 多格式镜像；真机安全配置 |
| P0 | 运行时模型缺口 | C6 Zigbee commissioning；Core2 legacy I2C controller/board-bus routing；Core2 for AWS ATECC608 | 802.15.4 ACK/controller；controller port/pin 到板级 bus；安全元件 fixture |
| P0 | 真机同路径验证 | 代表设备使用同固件 SHA 和同测试计划通过 | 物理设备、测试槽、证据采集 |
| P1 | 服务池与调度 | warm pool、配额、对象存储、审计、多机容量 | supervisor、监控、隔离 |
| P1 | Core2 长稳与物理/controller 等价性 | 完成 `tb-size=128` 的 artifact-bound `7200s` 复测；执行 3 个独立 lease × 121 轮 reconnect，再验证吞吐/teardown 与 bit-exact controller/cache/PSRAM | 未限容 RSS 已定位到 TCG translation buffer，120 秒限容验证 PASS；两小时限容 evidence 完成前仍为 `REVIEW`；reconnect 参数范围已扩到 1–121，运行待验 |
| P1 | Tab5 P4 后端 | 关闭 CSI、I2S/PCM、USB Host、SDIO、动态 I2C、ST7123 | 可重建或可扩展 P4 backend |
| P1 | 设备视觉保真 | 逐设备结构、材质、hitbox 和视觉回归 | 官方尺寸/参考图 |
| P2 | CardputerZero 收口 | 系统、驱动、USB/网络竞态和长期回归 | 独立 Linux ARM64 后端 |

## 当前执行顺序

1. `CORE2-02`：收集正在运行的 `tb-size=128` artifact-bound `7200s`
   extended-run 最终 evidence；检查资产/工具哈希、`bounded_tcg_cache`、
   frame/QOM、WiFi/公网/GATT、pcap、HLI health、RSS/phys footprint 和
   cleanup。只有全部门禁成立才关闭内存风险。
2. `CORE2-02`：在隔离于 soak 的新 service 上执行 3 个独立 lease × 121 轮
   reconnect，随后补长时吞吐/teardown、controller/baseband 和物理边界。
3. `NET-06`：在 privileged Linux namespace 中用同一 UIFlow2 测试 guest
   完成 controlled AAAA、允许 IPv6 HTTP、denied-port、pcap、namespace/NAT
   cleanup 和 QEMU reap。原厂 UIFlow2 未启用 IPv6，不能升级为默认能力。
4. `FW-03`：重跑公开 CDN 当前 BIN 并记录新 SHA；先覆盖已刷新的 AtomS3R
   XiaoZhi / OpenAI Voice Assistant 和 PaperMono EDC Book / CrossPoint，
   再扩到更多设备与 firmware family。
5. `NET-04` / `SVC-01`：在现有 durable queue、HTTPS/mTLS、rotation/drain、
   同主机 generation-pointer migration 和本地 QEMU/QMP reattach 上补自动
   主机发现/跨主机迁移；先用 control/runtime 双端点跑真实 worker-local
   QEMU，再补跨主机 reattach、companion/evidence continuity 和多机调度。
6. `FW-01/02`、`RUNTIME-02`、`HW-01`：补运行态权限/许可、生产 key/eFuse、
   C6 Zigbee 决策和代表设备同固件 SHA 的真机验证。
7. `SVC-02`、`SVC-03`、`TAB5-01`、`UI-01`、`CZ-01`：服务池、模块拆分、
   专项后端和视觉工作，不与当前 P0 混算完成。

## 可执行任务板

| ID | 状态 | 下一项最小交付 | 验收 |
| --- | --- | --- | --- |
| `NET-04` | 进行中 | 真实 server/worker network namespace 已通过 Bearer+HMAC 注册、submit/claim、worker/job heartbeat、result 和 cleanup；`WorkerAgent` 已把中央 control API 与本地 runtime API 拆开并有单元契约，下一步启动真实 worker-local QEMU 与 evidence 路径，再补自动主机发现/跨主机迁移、reattach、companion/evidence continuity、生产调度 | worker 重启后 job/evidence 可收敛；rotation 已完成；控制面不创建 session，执行面拥有 QEMU/evidence/cleanup；receipts 可审计；namespace 失败 fail-closed；活动实例不产生假 running |
| `NET-06` | 进行中 | controlled resolver A/AAAA、IPv6 forwarding 预检和专用 UIFlow2 测试构建的 guest IPv6 TCP/HTTP 已实现；下一步在同一 Linux guest 完成 controlled AAAA、denied-port 与 namespace cleanup | 同一 lease/guest 内 AAAA 允许/拒绝、IPv6 egress、pcap 和 cleanup 成立；不能用 host probe 或另一 session 拼接固件结论；原厂 UIFlow2 未启用 link-local |
| `CORE2-02` | 进行中 | 3 个独立 lease 各 20/30/60/120 轮、`5×10s`、`3×60s`、`2×120s`、active-BLE `600s` 与 artifact-bound `7200s` 功能保持已通过；RSS 增长定位到默认 1 GiB TCG buffer，`tb-size=128` 120 秒验证 PASS；限容两小时复测运行中；参数范围扩到 1–121 | 限容两小时功能与 RSS/phys footprint 稳定、资产无漂移；3 个独立 lease 各 121 轮完整 scan/connect/GATT/disconnect 无 retry PASS；随后补 controller/baseband、物理 cache/PSRAM 和真机 |
| `FW-01` | 进行中 | 运行时权限、完整源码级许可扫描与法律审批 | 文件清单可追踪；声明策略、资源权限和最终许可结论可审计且不混算 |
| `FW-02` | 进行中 | 真机 secure boot、Flash Encryption、eFuse 和生产 key 流程 | 支持矩阵与拒绝路径明确，敏感 key 不入库 |
| `FW-03` | 进行中 | API/WebBurner 已能声明 required/optional capability；required/optional 重叠会拒绝，optional 不匹配只 warning；sdkconfig WiFi/BT/PSRAM 作为 detected warning 进入 manifest。矩阵已改为每轮强制刷新公开 BIN。已有 7 台设备、21 个历史哈希绑定样本；下一步先跑当前 AtomS3R/PaperMono 四样本，再扩更多设备与 firmware family | 每样本分层记录导入、capability、boot、输入和功能；同 ID/version 旧缓存不得复用；模型缺口不得混作固件 FAIL |
| `RUNTIME-02` | 进行中（backend blocked） | esp-emu `--thread-sim` 已观察到双向 802.15.4 帧，但 commissioning/join 未完成；补 MAC ACK/commissioning 语义或取得公开固件匹配 ELF | 完成至少一个真实 guest 生命周期并保留证据；否则继续显式返回 `runtime_model_gap` 且保留阻断证据 |
| `RUNTIME-03` | 进行中 | 对齐 Core2 legacy I2C controller port、SCL/SDA pin 与板级 bus；确认 `disable_timer_interrupt()` 的 BM8563 RTC 路径 | `UIFlow_Core2` 同固件 SHA 渲染非空帧，AXP2101 与 AXP192 差异有同日 evidence |
| `RUNTIME-04` | 进行中 | 为 Core2 for AWS 提供 ATECC608 测试 slot/config fixture | 固件越过安全元件初始化并渲染应用帧；不提交生产私钥 |
| `SVC-01` | 进行中 | companion/evidence continuity、worker 主机自动发现与跨主机 reattach | 服务重启可接管或明确失败，不产生假 running |
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
  worker/generation HMAC、timestamp/nonce replay 防护。服务端与 worker
  client 已支持 TLS 1.2+，配置 client CA 后强制 mTLS，并有真实 loopback
  进程、证书拒绝/通过、签名请求和 `SIGHUP` A/B TLS/token rotation 证据。
  rotation 会先完成活动请求，并以 previous token/CA 提供有界旧/新重叠，
  最终移除 previous 文件后拒绝旧身份与旧 token，再由新凭据完成真实
  QEMU job。同主机双 worker 已通过不可变 generation 目录、单个原子
  pointer 和 secret-free receipt 自动迁移，无需逐个发送 worker `SIGHUP`；
  两个独立 network namespace 中的真实 Device Service 和 `WorkerAgent`
  已跨 veth 完成认证注册、job submit/claim、worker/job heartbeat、terminal
  result、token 不落日志和 namespace 清理；仍没有 worker 主机自动发现、
  跨主机 QEMU job、跨 worker 容量调度和多机状态收敛；
- `worker_agent.py` 现支持 `--runtime-service-url`：中央服务只负责
  claim/heartbeat/result，独立 runtime service 负责 session、evidence 和
  stop。单元契约已验证请求平面分离；Linux fixture 已加入 worker namespace
  内真实 QEMU/artifact/evidence 模式但尚未执行；runtime health 未通过时
  worker 会在注册/claim 前失败，该端到端门禁仍是下一步；
- 本地 QEMU/QMP 控制面可在 PID start-time、QMP ownership 和
  `query-status=running` 验证后 re-attach；Tab5/network lane、paused QEMU、
  companion HTTP/BLE helper、evidence 流和跨主机进程仍不能接管；
- 双 guest lab fabric 和 Linux policy CI 尚未成为自托管 worker 的正式
  调度与 evidence replay 路径。

下一项最小交付：

1. 用 control/runtime 双端点启动真实 worker-local Device Service + QEMU，
   验证 artifact/firmware 上传、首帧/串口、evidence SHA、stop 和 namespace
   cleanup；随后在现有 HTTPS/mTLS、HMAC executor、`SIGHUP` rotation、activity drain、
   bounded credential overlap 和同主机 generation-pointer migration 上补
   worker 主机自动发现、跨主机 QEMU job 和外部 side-effect fencing，禁止
   旧 agent 覆盖新 generation。
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

### NET-06 同 guest IPv6 DNS/HTTP

当前已具备：

- exact IPv4/IPv6 endpoint、双栈 veth/default route/NAT 和 cleanup；
- Device Service 对含外部 IPv6 endpoint 的请求执行 IPv6 forwarding
  capability 预检；
- controlled resolver 对同一 allowlisted 名称返回 exact A/AAAA，并拒绝
  unknown name；
- resolver-level UDP 查询、response type/address 和 decision log 有契约测试；
- 专用 UIFlow2 StickS3 测试构建在 `IP_EVENT_STA_GOT_IP` 后创建 IPv6
  link-local，同一 guest 已完成 `fec0::2:18095` 的 TCP/HTTP；pcap、串口
  marker 和 firmware/QEMU 哈希在同次 evidence 中。

当前缺口：原厂 UIFlow2 没有创建 IPv6 link-local，因此直接使用原厂镜像会
`EHOSTUNREACH`；测试构建不能描述成原厂默认能力。尚未在 Linux namespace
中让同一 guest 完成 controlled AAAA、denied-port 和 cleanup。

验收：同一 lease/guest 中，允许名称解析到 exact AAAA，guest 访问配置的
IPv6 endpoint 并完成 HTTP；拒绝地址/端口仍被 nftables 阻断；pcap、
namespace/NAT 清理和串口 marker 属于同一份 evidence。

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
- 第一轮 GATT、active-BLE 120 秒 hold 和同一 guest 多轮重连均已通过。
  reconnect blocker 根因是外部 Bumble compatibility 层错误地为无响应的
  `HCI_Host_Number_of_Completed_Packets (0x0c35)` 返回 Command Status；
  下一命令消费 stale ACK 后触发 `BLE_HS_ECONTROLLER (12)` 与 reset。
  QEMU HLI、NimBLE host 连接池和 GATT/L2CAP 池均已排除；
- 三十轮门禁已完成：3 个独立 lease 各 30 轮，每 lease HLI `857/857`、
  events `587`、ACLs `270`，无错误、无 panic、连接池回到 `3/9/3`；
- 六十轮门禁已完成：3 个独立 lease 各 60 轮，每 lease HLI
  `1697/1697`、events `1157`、ACLs `540`，无错误或 panic；
- 120 轮门禁已完成：3 个独立 lease 各 120 轮，每 lease HLI
  `3377/3377`、events `2297`、ACLs `1080`，无错误、dropped 或 panic；
- active-BLE 600 秒门禁已完成：2 个独立 lease `2/2`，peer 全程保持连接；
- 旧 `7200s` active-BLE 行为保持保留为 `DIAGNOSTIC_PASS`，因为 QEMU 路径在
  run 中被临时重编；
- hash-freeze runner 的重跑完成 artifact-bound `7200s` 功能门禁：首 lease 前
  冻结 firmware/ELF/QEMU，运行期无资产漂移，HLI `45/45`、网络、GATT、
  frame、pcap、evidence 和清理均 PASS；
- 同一次运行采样 QEMU host RSS 从 `744160 KiB` 增至 `1202176 KiB`
  （`+458016 KiB`）；后续归因到未限容的 TCG translation buffer。功能
  长稳 PASS 不等于内存有界，`tb-size=128` 最终两小时复测尚未完成；
- 仍未完成：最终两小时限容复测、121 轮连接、长时吞吐/并发和
  process-stop/teardown 竞态；
- 当前 native-HCI hook 偏移只对已验证的 UIFlow2 v2.5.3 build 成立；
  其他 Core2 固件需要新的符号/偏移校验，不能按 SoC 继承 PASS；
- bit-exact Espressif BT controller/baseband，而不是 VHCI 边界替换；
- 物理 cache/PSRAM 时序对比；
- 同固件路径真机验证。

新调用必须使用 `core2-native-hci`。`core2-native-vhci` 依赖 GDB，只允许
作为显式诊断/兼容路径，不能用来证明稳定生产能力。

验收追加条件：

- 同一 guest 121 轮完成 scan/connect/NUS GATT/disconnect 且无 retry，
  每轮都有 guest RX、notification、peer/pcap/evidence 和 HLI health；
- 完成 `tb-size=128` 的 7200 秒 artifact-bound 复测，并保持资产、
  RSS/phys footprint 与功能检查稳定；再验证 121 轮、长时吞吐/并发和 teardown；
- runner 在失败时必须输出 aggregate `FAIL`，不能丢 traceback 或只保留成功
  次数；
- 首轮 panic 必须先于 reboot 次生故障被分类和符号化；
- `HCI-4` 历史 `5/5` 可以继续引用，但不得替代新的长稳结果。

## P0：通用固件审查

### FW-01 文件系统、权限与许可

当前缺口：LittleFS、FAT12/16/32 和常见 ESP-IDF SPIFFS 配置已有只读清单；
每个文件都有结构化 `permission_policy`，FAT 原生属性已记录，LittleFS/SPIFFS
明确标记无 Unix mode。provenance/文件系统/SBOM 声明已可汇总为显式
allowlist/denylist 决策，且未配置 allowlist、无声明和未知表达式会保持
`REVIEW_REQUIRED`。包内源文件已有有界 SPDX header 扫描；固件运行时的实际
权限/ACL 强制、生成代码/包外 vendor 依赖的完整许可覆盖和真实法律审批仍开放。

验收：

- 不支持的 SPIFFS 配置明确返回 `INVALID`，不能猜测文件名；
- 每个资源项记录来源、哈希、镜像可见的权限策略和在适用时的许可结论；
- 运行态权限必须由真实 guest/系统路径验证，不能把 FAT read-only attribute
  或“无 Unix mode”写成 ACL/执行权限 PASS；
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

当前缺口：已有 21 个公开非基线样本的历史哈希绑定结果覆盖 7 台设备，并
区分 10 PASS、11 PARTIAL；公开 CDN 已观察到一个 firmware ID/version ID
背后的 BIN 可变化，所以矩阵现在每轮强制刷新，旧缓存不能证明当前制品。
其中 S3/C6 的 18 样本快照包含 2 个历史 runtime model gap，
C6 软件复位 chip-id 缺口已经由 `RUNTIME-01` 修复并在 Device Service 重跑中移除
`runtime_model_gap`，但该样本仍有独立应用异常。仍未覆盖全部设备、
ESP32 LX6/P4、更多 MicroPython/vendor framework 和失败根因闭环。
Zigbee 缺口继续由 `RUNTIME-02` 管理，不把“已分类”算成该任务完成。

CLI、WebBurner 和 `/api/v1/firmware/import` 已统一接受 required/optional
capability。网页上传不再只能生成空声明；`screen` 等别名会规范化，
`camera`-on-StickS3 等不匹配在 manifest 阶段返回结构化 409。该声明仍由
操作者提供，不能由二进制自动证明“代码确实调用了该外设”。
包内 `sdkconfig` 的 WiFi、Bluetooth 和 PSRAM 开关会作为 detected
capability 保留 flag/source；目标 profile 缺失时只 warning，不会把
“编译时启用”误当成“运行时使用”。

验收：每个样本记录 importer、chip/board/profile、partition、capability、
boot 和功能层；结构 PASS、UI PASS、功能 PASS、安全 PASS 不混算。

### RUNTIME-02 C6 Zigbee/802.15.4

当前缺口：QEMU C6 profile 没有 IEEE 802.15.4/Zigbee controller，官方
NanoC6 Zigbee HA light 最终触发 task watchdog。另用 `esp-emu 0.50.0` 的
`--thread-sim` 运行源码构建的 C6 switch/light 对后，已观察到双向
802.15.4 帧、协调器组网和 light steering 启动，但没有完成 commissioning、
join 或 On/Off 命令。公开 M5Burner Zigbee bin 的 ELF SHA 没有匹配文件，
因此该公开样本不能直接用当前 bridge 验证。继续把 QEMU watchdog 标成固件
`FAIL` 会污染审查结论。

下一项最小交付：补可验证的 802.15.4 MAC ACK/commissioning 语义，或取得
公开固件的签名匹配 ELF；用
`tests/firmware/c6_zigbee_thread_sim/run_feasibility.py` 复查 join、
On/Off 和离网生命周期。当前 backend 下不得用 host 伪造 Zigbee 状态。

验收：至少通过真实 guest 驱动的加入、收发和离网生命周期后才能改为支持；
如果无法取得权威控制器语义，则保留结构化 `runtime_model_gap`，明确不支持，
不承诺全 C6 固件兼容。详情见
[运行时模型缺口登记](runtime-model-gap-register.md)。

### RUNTIME-03 Core2 legacy I2C controller/board-bus routing

当前缺口：`UIFlow_Core2` 与 `Core2FactoryTest` 都发现 AXP I2C 地址；
Controller/device trace 已确认 AXP2101 chip id `0x4a` 可以读出。随后
`disable_timer_interrupt()` 的下一事务发往 address `0x51`、`start_rc=1`
（无 ACK），并在生成新的 address `0x34` 事务前返回
`OSError: I2C bus error (19)`。冻结 qstr 中的 BM8563/`__read_byte` 和
`0x51` RTC 地址指向 RTC-candidate 路径。默认 AXP2101 和
`M5SW_CORE2_PMIC=axp192` 都失败，因此当前首要边界是 legacy controller
到板级物理 I2C bus 的 routing/handoff，而不是已经证实的 PMIC 寄存器
响应错误。

下一项最小交付：在 trace 中补 I2C port id、SCL/SDA pins、目标 QEMU bus
和板级 slave bus；取得匹配 UIFlow1 源码/frozen bytecode 后确认 BM8563
实际使用的 controller/address API；修 routing 而不是把同一设备复制到多条
总线。公开 `M5Stack_MicroPython` 当前没有找到匹配旧 UIFlow1 类，frozen
MPY 提取也尚未成功，因此下一步要在独立 QEMU 构建中先记录 port/pin/GPIO
mux/bus handoff；当前 Core2 soak 期间不得替换正在使用的 QEMU。若后续事务
到达 AXP 设备，再修对应数据面；
`M5SW_CORE2_PMIC` 仍只允许通过受限 `runtime_env` 选择，不得用 host 假值
伪造启动结果。

验收：同一 `UIFlow_Core2` SHA 在指定 PMIC 变体下进入应用帧并保持运行。

### RUNTIME-04 Core2 for AWS ATECC608

当前缺口：`Core2_For_AWS` 在 `ATECC608` 安全元件初始化失败后主动
`abort()`。这是缺失板级安全元件模型，不能直接记成固件崩溃。

下一项最小交付：为 QEMU 增加 ATECC608 I2C 命令和测试 slot/config fixture，
禁止提交生产私钥；先让公开固件的安全元件初始化通过，再单独验证应用帧。

验收：固件进入非空应用帧，安全元件和普通功能证据分层记录；若只能伪造
返回值则继续 `runtime_model_gap`。

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
