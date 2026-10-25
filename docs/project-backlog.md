# 项目 Backlog

日期：`2026-10-25`

本文只记录**尚未完成**的工作、优先级、依赖和验收条件。当前能力、已闭合
边界和风险见 [项目当前状态](project-status.md)，历史验证见
[验证证据台账](validation-ledger.md)，代码入口见
[代码与验证入口地图](code-map.md)。

需要先理解整体代码、已完成工作流和下一步执行顺序，见
[工程交接总览](engineering-handoff.md)。本页不复制已完成里程碑的完整叙事；
已经闭合的事实由当前状态页和证据台账维护。

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
| P0 | 网络产品化 | controlled DNS CNAME resolver、同 guest CNAME→HTTP 生命周期、跨 Docker 容器 worker-local QEMU、worker-local `qemu-unified` companion/pcap partition fence 和跨子网/NAT unicast seed discovery 已完成；物理跨主机 worker 迁移/QEMU executor、无 reachable seed 的任意 NAT traversal、namespace-managed/Tab5/cross-host companion、跨主机 reattach 和生产调度仍待做 | durable queue/lease supervisor；HTTPS/mTLS；SIGHUP rotation + request drain + bounded credential overlap；同主机 generation-pointer migration + receipts；同主机 authenticated executor；本地 QEMU/QMP + trusted-host companion reattach |
| P0 | 通用固件安全 | 权限/许可、安全启动/Flash Encryption/key 流程、跨厂商回归 | 多格式镜像；真机安全配置 |
| P0 | 运行时模型缺口 | C6 Zigbee commissioning；Core2 legacy I2C controller/board-bus routing；Core2 for AWS ATECC608 | 802.15.4 ACK/controller；controller port/pin 到板级 bus；安全元件 fixture |
| P0 | 真机同路径验证 | 代表设备使用同固件 SHA 和同测试计划通过 | 物理设备、测试槽、证据采集 |
| P0 | Core2 长稳与物理/controller 等价性 | 补五实例零错峰冷启动、大于五实例、持续吞吐与其他 teardown 模式，以及 bit-exact controller 和物理 PSRAM/cache timing | 3 个独立 121 轮 lease、最终 `tb-size=128` artifact-bound `7200s`、active-stop/recovery `3/3`、30 秒错峰 `2/2`、双/三/四实例各两批无错峰 PASS（`8/8`、`6/6`、`8/8`）、五实例 30 秒错峰两批 `10/10`、QOM 8 MiB、upper-bank `esp_himem` `3/3`、`3×120s` heap stress `3/3` 和单次 600 秒联网压力 `1/1` 已 PASS；四实例原始 `1/4` 失败、五实例零错峰 `5/5` 与 `3/5` 不稳定对照和 `0009` 修复均保留 |
| P1 | 服务池与调度 | warm pool、配额、对象存储、审计、多机容量 | supervisor、监控、隔离 |
| P1 | Tab5 P4 后端 | 关闭 CSI、I2S/PCM、USB Host、SDIO、动态 I2C、ST7123 | 可重建或可扩展 P4 backend |
| P1 | 设备视觉保真 | 逐设备结构、材质、hitbox 和视觉回归 | 官方尺寸/参考图 |
| P2 | CardputerZero 收口 | 系统、驱动、USB/网络竞态和长期回归 | 独立 Linux ARM64 后端 |

## 当前执行顺序

1. `NET-04` 跨主机阶段：cross-container QEMU/evidence 和 unicast seed
   跨子网/NAT discovery 已完成；补物理跨主机 QEMU executor、
   跨主机 reattach/idempotency、无 reachable seed 的任意 NAT traversal、
   QEMU 内 guest/device-controller 和 worker 未拥有的外部 side-effect fencing；两个 network
   namespace 的同主机 PASS 不能替代。trusted-host companion continuity 已
   通过；剩余单独处理 namespace-managed/Tab5/cross-host companion。
2. `CORE2-02` extended-run：`3×121`、active-BLE `600s`、
   artifact-bound `7200s`、30 秒错峰 `2/2`、两批独立无错峰
   `4×120s`（`8/8`）、两批三实例 `3×120s`（`6/6`）和两批五实例
   30 秒错峰 `5×120s`（`10/10`）已完成。下一步补五实例零错峰冷启动、
  大于五实例、持续吞吐、其他 teardown、bit-exact
  controller/baseband、物理 `8 MiB` PSRAM/cache timing 和真机路径。四实例
  首批曾 `1 PASS / 3 FAIL`，暴露 NimBLE ACK panic；`0009` 把真实 guest
  event/ACL 备用池从 `2/2` 扩到 `8/4` 后，两批独立 `4×120s` 各
  `4/4 PASS`。QOM `8 MiB`、普通 4 MiB heap `3×120s`/600s 持续压力、
  上 4 MiB `esp_himem` bank switch 3/3、周期联网、active-stop 和最多
  四实例 concurrent steady-state 不重复列为待办。五实例 30 秒错峰稳态已
  完成两批，但相同实现的零错峰冷启动先 `5/5 PASS`、独立确认批
  `3/5 FAIL`，因此同时冷启动仍是开放规模边界。
3. `FW-03`：当前四样本、Manifest、SHA-bound expectation、SD/NVS fixture、
   OpenAI DHCP/DNS/TCP443/pcap 和正确/错误 WPA2 密码均已完成；下一步是真实
   key/cloud 服务结果并扩更多设备与 firmware family。
4. `FW-01/02`、`RUNTIME-02/03/04`、`HW-01`：补运行态权限/许可、生产
   key/eFuse、C6 Zigbee 决策、Core2 控制器缺口和代表设备同固件 SHA
   的真机验证。
5. `SVC-02`、`SVC-03`、`DOC-01`、`TAB5-01`、`UI-01`、`CZ-01`：服务池、模块拆分、
   专项后端和视觉工作，不与当前 P0 混算完成。

## 可执行任务板

| ID | 状态 | 下一项最小交付 | 验收 |
| --- | --- | --- | --- |
| `NET-04` | 进行中 | 真实 server/worker network namespace、worker-local StickS3 QEMU、三个独立 Docker 容器对、active-token multicast discovery、cross-subnet/NAT unicast seed discovery、network blackhole 后 OS process 与真实 QEMU PID stop/reap + lease expiry/requeue/retry、worker-local `qemu-unified` 的 HTTP/BLE/pcap companion fence、central/runtime restart continuity、session-create idempotency、trusted-host companion continuity，以及 re-claim 后旧 lease result `409` fencing 已 PASS。下一步补物理跨主机迁移/reattach、无 reachable seed 的任意 NAT traversal、QEMU 内 guest/device-controller 和 worker 未拥有的外部 side-effect fencing、namespace-managed/Tab5/cross-host companion 和生产调度 | worker 重启后跨主机 job/evidence 可收敛；rotation 已完成；控制面不创建 session，执行面拥有 QEMU/evidence/cleanup；receipts 可审计；lease ownership fail-closed；活动实例不产生假 running |
| `CORE2-02` | 进行中 | QOM 8 MiB、upper-bank `esp_himem` `3/3`、`3×120s` heap/周期联网 `3/3`、单次 600 秒压力、121 轮三 lease、最终 `tb-size=128` 7200s、active-stop/recovery、30 秒错峰 `2×120s`、双/三/四实例两批独立门禁和五实例 30 秒错峰两批 `10/10` 均已 PASS；`0008` 建立真实 guest HCI event/ACL fast path，`0009` 以 `8/4` 备用池关闭四实例启动 ACK burst，四实例每轮 36 events/9 ACLs、HLI `45/45`、`hli-errors=0`。原始四实例 `1/4` 失败及五实例零错峰 `5/5 PASS`/`3/5 FAIL` 不稳定对照仍保留 | 再补五实例零错峰、大于五实例、持续吞吐、其他 teardown、controller/baseband、物理 PSRAM/cache timing 和真机 |
| `FW-01` | 进行中 | 运行时权限、完整源码级许可扫描与法律审批 | 文件清单可追踪；声明策略、资源权限和最终许可结论可审计且不混算 |
| `FW-02` | 进行中 | 真机 secure boot、Flash Encryption、eFuse 和生产 key 流程 | 支持矩阵与拒绝路径明确，敏感 key 不入库 |
| `FW-03` | 进行中 | API/WebBurner capability、Manifest、WebBurner 分段 size/SHA-256/SHA-1/MD5 完整性、矩阵 SHA、SD/NVS fixture 和 SHA-bound `ui-interactive`/`headless-serial`/`network-first` expectation 已完成；当前 AtomS3R/PaperMono 四样本为 `3 PASS / 1 PARTIAL / 0 FAIL`。OpenAI 在同一 BIN + NVS fixture 上通过 network-first 的 DHCP/DNS/TCP443/pcap；Open/WPA2 正确与错误密码也已确认。下一步补真实 key/云端服务结果，再扩更多设备与 firmware family | 每样本分层记录导入、capability、boot、输入和功能；同 ID/version 但 SHA、expectation 或 fixture 变化的旧结果不得复用；`runtime_fixture_gap`/`runtime_model_gap` 不得混作固件 FAIL；SD/存储/NVS 与网络 expectation 可重复注入 |
| `RUNTIME-02` | 进行中（backend blocked） | esp-emu `--thread-sim` 已观察到双向 802.15.4 帧，但 commissioning/join 未完成；补 MAC ACK/commissioning 语义或取得公开固件匹配 ELF | 完成至少一个真实 guest 生命周期并保留证据；否则继续显式返回 `runtime_model_gap` 且保留阻断证据 |
| `RUNTIME-03` | 进行中 | 对齐 Core2 legacy I2C controller port、SCL/SDA pin 与板级 bus；确认 `disable_timer_interrupt()` 的 BM8563 RTC 路径 | `UIFlow_Core2` 同固件 SHA 渲染非空帧，AXP2101 与 AXP192 差异有同日 evidence |
| `RUNTIME-04` | 进行中 | 为 Core2 for AWS 提供 ATECC608 测试 slot/config fixture | 固件越过安全元件初始化并渲染应用帧；不提交生产私钥 |
| `SVC-01` | 进行中 | central control-plane、runtime-service restart continuity、session-create idempotency 和 trusted-host unified HTTP/BLE companion continuity 已完成；namespace-managed/Tab5/cross-host companion、跨主机 idempotency、无 reachable seed 的任意 NAT traversal 与跨主机 reattach 仍待做 | 服务重启可接管或明确失败，不产生假 running |
| `SVC-02` | 待做 | warm pool、队列、配额、对象存储和审计 | latency/CPU/RSS/queue/GC 可观测，租户状态隔离 |
| `SVC-03` | 待做 | 拆分 `device_service.py` 的存储、runtime、evidence 和 session 状态机 | 对外 API/evidence 不回归；模块边界有契约测试 |
| `DOC-01` | 待做 | 将接近 6000 行的 `test_docs_consistency.py` 按文档索引、权威状态/Backlog、Core2、网络/worker、固件安全等领域拆分；把手写 stale-claim 断言收敛为结构化 claim/evidence 清单 | 相对链接、API 版本、生成物、当前/历史文档边界和证据冲突仍全覆盖；拆分前后同一提交全套测试通过 |
| `HW-01` | 待做 | 代表设备同固件 SHA 的真机测试计划 | evidence 明确标为 hardware validation |
| `TAB5-01` | 决策 | 重建或扩展 P4 backend | CSI、I2S/PCM、USB Host、SDIO、动态 I2C、ST7123、IP2326 有执行路径 |
| `UI-01` | 待做 | 逐设备高保真外壳、hitbox 和截图阈值 | 每台设备独立结构证据和视觉回归 |
| `CZ-01` | 待做 | CardputerZero 系统、驱动和长期回归 | 启动、USB、网络、音频、摄像头和真机边界明确 |

## P0：网络与 worker

### NET-04 远程 worker

现有基线只作为依赖，不在这里重复完成流水：

- durable queue、worker directory、HMAC、HTTPS/mTLS、rotation/drain、
  session-create idempotency、central/runtime restart continuity 和
  trusted-host unified HTTP/BLE companion continuity 已可用；
- active-token multicast discovery、cross-subnet/NAT unicast seed discovery、
  worker control/runtime 双平面、双 namespace worker-local StickS3 QEMU 和
  三个独立 Docker 容器对已通过；后两者仍分别属于单主机 namespace/容器；
- worker→control network blackhole 已在 process 与真实 worker-local QEMU
  两个 lane 各 `3/3 PASS`：bounded heartbeat、runtime DELETE、OS/QEMU PID
  reap、lease expiry/requeue 和 retry completion 均成立；
- worker-local `qemu-unified` lane 又在三个独立运行中证明 partition 前已有
  HTTP/BLE/pcap，fence 后 HTTP/BLE companion 终止、BLE PID 回收、pcap
  summary 完成，fresh retry 重新取得 unified evidence；
- 这些 lane 不证明 QEMU 内 guest/device-controller 已 quiesce，也不证明
  worker 未拥有的外部 side effect 已停止。

当前开放缺口：

- 物理跨主机 executor/reattach、迁移期间跨主机幂等与 evidence 收敛；
- 无 reachable seed 时的任意 NAT traversal；
- namespace-managed/Tab5/cross-host companion、连续外部 evidence 流和
  生产多机调度。

下一项最小交付：

1. 在真实多主机环境验证 executor、reattach、idempotency 和 control-plane
   故障边界；无法证明 ownership 时继续明确 `interrupted_failed`。
2. 验证 QEMU 内 guest/controller 内部状态和 worker 未拥有的外部 side effect。
3. 实现跨 worker 容量调度、持久 evidence 存储、幂等重放和队列审计。
4. 把 namespace、pcap、session history 和 cleanup 结果绑定到同一个 lease。

验收：

- worker 强杀、重启、失联和 drain 都有确定终态；
- 远程 worker 的 Linux policy 失败时 fail-closed；
- 任务、实际执行 worker、generation、QEMU PID/start time 和 evidence
  可关联；
- 本地 reattach 有 PID reuse、stale start-time、QMP 缺失、正常停止和残留清理
  证据；trusted-host HTTP/BLE companion reattach 已有同 PID、两代 HTTP、
  GATT cycle 2、原 lease evidence 和清理证据；跨主机/namespace/Tab5
  companion reattach 仍待补。

## P0：Core2 物理与 controller 边界

设计见 [Core2 native HCI backend](core2-native-hci-backend.md)。

### CORE2-02 物理与 controller 边界

已闭合输入见[验证证据台账](validation-ledger.md)，这里只保留不可回退的
边界：

- `semphr_give_wrapper` panic 已通过恢复 guest-call sregs 和限制 HLI
  注入上下文修复；两批短 hold 合计 `5×10s`，后续 `60s`/`120s` hold 与
  active-BLE 均通过。
- 同一 guest 的 30/60/120/121 轮 reconnect 已有三 lease 门禁；
  `3 个独立 lease 各 120 轮` 的 stale-ACK 根因是 Bumble 非法响应
  `HCI_Host_Number_of_Completed_Packets (0x0c35)`，不是 guest panic。
- artifact-bound `7200s`、`tcg,thread=single,tb-size=128`、
  active-stop/recovery、QOM `8 MiB`、upper-bank `esp_himem 3/3`、
  `3×120s` 和 600 秒 guest 压力均只覆盖对应虚机 workload。

当前开放缺口：

- 当前 native-HCI hook 偏移只对已验证的 UIFlow2 v2.5.3 build 成立；
  其他 Core2 固件需要新的符号/偏移校验，不能按 SoC 继承 PASS；
- bit-exact Espressif BT controller/baseband，而不是 VHCI 边界替换；
- 物理板载 `8 MiB` PSRAM 与物理 cache/PSRAM 时序对比；
- 五实例零错峰冷启动、大于五实例、持续吞吐和其他 teardown 模式；当前
  双实例 `8/8`、三实例 `6/6`、四实例 `8/8` 和五实例 30 秒错峰 `10/10`
  只覆盖对应实例数、启动方式、指定固件和 QEMU hook build；
- 同固件路径真机验证。

新调用必须使用 `core2-native-hci`。`core2-native-vhci` 依赖 GDB，只允许
作为显式诊断/兼容路径，不能用来证明稳定生产能力。

开放项验收：

- 新目标固件完成 hook/符号校验，并在对应长稳场景中保持 guest RX、
  notification、peer/pcap/evidence 和 HLI health；
- 物理 PSRAM/cache、controller/baseband 和真机行为分别提供同路径证据；
- 五实例零错峰及大于五实例在独立 artifact-bound 复跑中保持 aggregate
  `PASS`；四实例原始失败、五实例 `5/5 PASS`/`3/5 FAIL` 不稳定对照及
  `0009` 修复必须同时保留；双实例、三实例和四实例无错峰
  门禁已分别由两批独立复跑覆盖；
- runner 在失败时必须输出 aggregate `FAIL`，不能丢 traceback 或只保留成功
  次数；
- 首轮 panic 必须先于 reboot 次生故障被分类和符号化；
- 已闭合的 `extended-run` 与 `HCI-4` 只能作为依赖，不得替代开放项结论。

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

当前缺口：包内 sdkconfig、分区 flag、脱敏 eFuse summary、capability
preflight，以及 Secure Boot v2 signature sector 的 block CRC/image digest
和 RSA-PSS、ECDSA P-192/P-256/P-384 数学验证已有；签名公钥 SHA-256
还会与包内 `SECURE_BOOT_DIGEST` 做 match/mismatch/unavailable 对照；
application `secure_version` 也会与 eFuse `SECURE_VERSION` 做
below/satisfied/unavailable 对照。包内 summary 来源、embedded public key
authenticity/live eFuse trust root、bootloader anti-rollback 执行、
Secure Boot v1、Flash Encryption key、真机 secure boot/eFuse 和生产 key
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
OpenAI 首次启动 NVS 前置条件已经用内容寻址 fixture 和 Open/WPA2 虚拟 AP
对照关闭；空 NVS 不再作为模型故障。非空密码路径已完成正确密码
WPA2-PSK、错误密码 M2 MIC 拒绝、DHCP、DNS、TCP/443 和 pcap 对照，
`RUNTIME-05` 已关闭。
Zigbee 缺口继续由 `RUNTIME-02` 管理，不把“已分类”算成该任务完成。

CLI、WebBurner 和 `/api/v1/firmware/import` 已统一接受 required/optional
capability。网页上传不再只能生成空声明；`screen` 等别名会规范化，
`camera`-on-StickS3 等不匹配在 manifest 阶段返回结构化 409。该声明仍由
操作者提供；镜像签名现在可提供低置信度 observed evidence 和
declared/observed mismatch warning，但不能证明“代码确实在运行态调用了该
外设”。
包内 `sdkconfig` 的 WiFi、Bluetooth 和 PSRAM 开关会作为 detected
capability 保留 flag/source；目标 profile 缺失时只 warning，不会把
“编译时启用”误当成“运行时使用”。

WebBurner `parts[]` 支持可选 `size`、`sha256`、`sha1`、`md5` 或
`integrity` 包装声明。导入器流式复算，不把声明值当作可信校验结果；
任一 mismatch、非法 digest、冲突声明或未知 integrity 字段都会拒绝。
manifest 只记录已验证算法集合与 `weak_digest` 标志，不保存源包或声称
发布者身份、数字签名或安全启动成功。

Device Service 还接受完整 NVS partition fixture。服务验证固件
`data/nvs` 分区的 label/offset/size，只覆盖 session Flash 副本，并在
snapshot/evidence 中记录 base/effective Flash SHA 和 fixture SHA。
`nvs_image.py` 生成确定性 namespace/string 数据；当前 encoder 已与
ESP-IDF NVS generator 做字节级对照。Matrix 的 v1 review expectation 已把
`ui-interactive`、`headless-serial` 和 `network-first` 做成按
`device_id + firmware_id + sha256` 绑定的显式模式；required marker、
forbidden marker、network status、expectation digest 与 fixture SHA 进入
结果键。OpenAI network-first 集成证据已证明无需 UI frame 也能依据 guest
marker、DHCP/DNS/TCP 和 pcap 给出 PASS。剩余工作是真实 key/云端业务结果，
而不是再补 headless 判定本身。

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
ownership 和 running 状态完成“接管或明确失败”；central control-plane
重启和 runtime Device Service 重启后 worker 也已通过有界 retry 收敛原
lease/session/evidence。trusted-host unified session 的 HTTP fixture 与
BLE peer 也能按持久 ownership 重建/adopt，并在重启后完成第二轮 GATT 和
guest HTTP 请求。下一步补 namespace-managed companion、Tab5/network lane、
连续 evidence 流和跨主机接管，再实现 warm pool。不能把已失去父进程或
ownership 不匹配的进程默认为 running。

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

### DOC-01 文档契约拆分

`platform/tests/test_docs_consistency.py` 已接近 6000 行，继续把每个新
evidence 和旧说法都追加到单一文件会让冲突定位和 review 成本持续上升。拆分
必须保留相对链接、文档索引、API 版本、生成快照和当前/历史页边界检查；按
领域建立测试模块，并优先把重复的手写 stale-claim 断言收敛成“权威页面、
claim ID、允许文本、evidence 路径”的数据表。验收是拆分前后同一提交的全套
文档契约测试均通过，新增当前事实页能自动进入索引/日期/权威状态检查。

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
