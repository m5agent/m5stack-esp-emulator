# 工程交接总览

最近核对：`2026-10-29`

本页用于让新接手的人快速理解“项目现在是什么、代码在哪里、哪些已经能跑、
接下来做什么”。它是导航摘要，不维护动态数量，也不替代以下权威入口：

- 当前能力、风险和验证边界：[项目当前状态](project-status.md)
- 未完成工作、依赖和验收：[项目 Backlog](project-backlog.md)
- 设备、样本、缺口和 Task 的机器生成计数：[自动项目快照](project-snapshot.md)
- 带日期的运行结果和 evidence：[验证证据台账](validation-ledger.md)
- 代码、测试和证据入口：[代码与验证入口地图](code-map.md)

如果本页与上述页面冲突，以上述权威入口和当前代码/evidence 为准。

## 当前盘点

下表只回答“现在做到哪、下一步是什么”。精确固件 SHA、轮次、资源数值和
失败 control 仍只放在[验证证据台账](validation-ledger.md)与 evidence 中。

| 工作流 | 已经形成可执行路径 | 仍在推进 | 当前判定 |
| --- | --- | --- | --- |
| 网络、隔离与 worker | same-guest controlled DNS/CNAME、exact/domain/CNAME answer binding、严格 Host authority、有界 IPv4/IPv6 egress、pcap、WPA2 正误密码、radio/AP 恢复、DHCP renewal、双 guest fabric、worker-local QEMU、持久队列、claim/evidence response-loss idempotency、lease-bound central evidence store、TLS/mTLS、discovery、restart/reattach 和 process/companion fence | `NET-04` 的物理跨主机 executor/reattach、queue/session/evidence 跨主机复制、无 reachable seed 的任意 NAT、QEMU guest/controller 内部状态和 worker 未拥有的外部 side effect | `PILOT`；单机、同 Docker daemon 或单个 control-plane evidence store 的结果不能写成物理多机/对象存储复制 PASS |
| Core2 | native-HCI、WiFi/公网、外部 GATT、重连、active-BLE 长稳、active-stop、post-reset stop、QOM `8 MiB` PSRAM、upper-bank MMU、high-priority DPORT IRQ 协作、classic RMT 和当前服务容量内并发 | `RUNTIME-03` legacy UIFlow normal-WDT reset、`APIKEY` 后黑帧与 LVGL completion；`CORE2-02` 物理 PSRAM/cache、bit-exact controller、更大规模、持续吞吐和更复杂 teardown | 功能级 `PILOT`；legacy UIFlow `PARTIAL`；不能从 RMT 初始化或虚拟容量外推物理等价 |
| ESP-NOW | `0067` loopback、`0076` plaintext、`0077` CCMP、`0078/0079` replay window、native/M5ESPNow lifecycle、`0080` key-state、`0081` shared-LMK fabric、`0082` per-peer routing、`0083` PN exhaustion/new-LMK rekey 和 `0084` loss/retry/channel/rate/60 秒 soak 已通过 | bit-exact controller/baseband、RF/antenna、实测 channel/rate 和电气时序 | `FIXED`（virtual-device validation）；link metadata、loss proxy 与长稳 PASS 不能写成物理 controller/RF 结论 |
| FirmwareManifest 与固件审查 | merged/segmented、WebBurner/M5Burner/ESP-IDF、content-stable manifest、ZIP path/casefold/symlink 与资源唯一性、显式 sdkconfig 优先级、多 build SoC 选择、unknown required capability fail closed、文件系统/NVS/SD、静态审查、Secure Boot v2 镜像数学和 security-evidence understatement fail closed；Device Service `1.51.0` 外部 runtime ACL/执行策略 | `FW-01/02/03` 的 guest filesystem ACL、完整许可与法律审批、live eFuse/trust root、生产 key、真实云端业务和更多固件族 | `PILOT`；静态镜像、service ACL 与包内自报安全证据不能写成设备文件权限或 trust root PASS |
| Device Service 与服务池 | lease、虚拟 Flash、串口、frame/input/QOM、网络故障、pcap、evidence、历史恢复、本地/远程 worker 生命周期 | `SVC-01` 跨主机接管，`SVC-02` warm pool/配额/对象存储/审计，`SVC-03` 从 `device_service.py` 编排热区分步拆分 | `PILOT`；当前是可信主机服务，不是恶意多租户 VM 沙箱 |
| 专项设备与表现层 | Tab5、CardputerZero 和逐设备外壳均有可用子集；StopWatch 是当前参考外壳 | `TAB5-01` 后端决策、`CZ-01` 长期回归、`UI-01` 视觉保真 | 均为独立边界，不能继承 S3/C6/Core2 的功能结论 |
| 真机验证 | 已定义同固件 SHA、同输入、同关键路径的验收规则 | `HW-01` 代表设备 hardware validation | `NOT RUN`；仓库当前没有可继承的物理 RF、功耗、声学、光学或电气结论 |

已完成里程碑只保留为依赖摘要，不再继续累加成“新待办”。一个工作流从
“有功能”到“可发布”必须分别通过功能、稳定性、安全、物理边界和同路径证据；
局部 PASS 不会自动升级整个平台。

## 结论

当前用户优先级是 `API-01`：按[双主机验证计划](plans/2026-10-27-uiflow2-complete-api-sweep.md)
逐项核对 UIFlow2 API、Unit 联测和 Device Service；原厂失败、候选修正及模型
阻塞分别保留，不把清单或局部通过视为全量完成。具体补丁、分母和复现入口见
[本轮审计证据](evidence/2026-10-27-uiflow2-api-sweep/README.md)。

项目已经不是单固件 PoC。当前主线具备以下可执行能力：

- 多设备 QEMU 启动、虚拟 Flash、串口、画面、输入、QOM 和外设数据面；
- S3/C6/Core2 的单 lease、单 guest、板级 + WiFi + BLE + evidence 路径；
- controlled DNS、有界 IPv4/IPv6 egress、pcap、错误密码、断线恢复和
  session 内网络取证；
- durable worker queue、HTTPS/mTLS、凭据轮换、自动发现、控制面/执行面
  分离、重启恢复和 worker-local QEMU；
- FirmwareManifest、WebBurner/M5Burner/ESP-IDF 导入、capability mismatch、
  静态审查、安全/文件系统/SD/NVS fixture 和公开固件矩阵；
- Device Service、浏览器设备目录/Live sessions、WebBurner 和证据包。

当前仍不是“任意固件都可无差别自动审查”的完成态。主要边界是：

- 物理跨主机 QEMU、无 reachable seed 的任意 NAT traversal、跨主机
  reattach/idempotency 和
  namespace-managed/Tab5/cross-host companion 尚未验证；
- Core2 已具备功能级 native-HCI、WiFi、重连、QOM `8 MiB` PSRAM 模型、
  upper-bank MMU remap 和持续压力证据，但 bit-exact BT controller/baseband、
  物理 PSRAM/cache timing 尚未覆盖；
- C6 Zigbee/802.15.4 和 Core2 legacy UIFlow normal-WDT/`APIKEY` 后黑帧仍是
  明确的 `runtime_model_gap`。Core2 for AWS ATECC608 初始化/identity 已由
  `0085` 以确定性测试 config 和 classic DMA link/DC 修复关闭，三个公开固件
  session 均产生非空帧；ECDSA、生产 trust root、电气和真机不继承。
  Core2 shared I2C、
  `CCOMPARE == CCOUNT` equal-deadline timer、TIMG WDT mask、pending SPI
  remap、high-priority DPORT IRQ 协作和 classic RMT 已作为独立模型缺口修复
  或验证。
  `0065` 证明旧固定双 PC deadlock 来自大 TCG slice 让 sender 抢在 peer
  handler 观察共享 flag 前开始下一轮；handler `memw` 后与 sender `retw`
  路径协作让出后，五轮首启动不再固定旧双 PC。`0066` 补 classic RMT
  `mem_size`、RMTMEM、threshold、`TX_END` 和 INTMATRIX，Neopixel translator
  错误消失，legacy Serial 到达 `APIKEY`。normal-WDT 仍在
  `17.249530334 s` 以 `TG0WDT_SYS_RESET` 重启，WDT-off 68 秒仍为 302-byte
  黑帧。当前未闭合物是 `APIKEY` 后 display completion、setup/REPL、
  watchdog 和非空应用帧，而不是 RMT 初始化或通用 SPI IRQ level。运行比例
  和 evidence 只查验证台账；
- 通用固件审查已有结构/静态/服务运行分层，但 guest filesystem ACL、完整许可、真机
  secure boot/Flash Encryption/key 流程和更多厂商固件仍未闭环；
- 所有物理 RF、功耗、声学、光学、机械和电气结论仍是 `NOT RUN`；
- 当前单机 namespace/container 路径不是恶意多租户固件的最终 VM 沙箱。

## 当前代码盘点

本页只保留稳定的代码边界。运行次数、PASS 比例、资源和提交 SHA 会随每次
验证变化，统一放在[验证证据台账](validation-ledger.md)和 evidence 文件中。

| 代码面 | 当前可执行基线 | 主要未闭环 | 稳定入口 |
| --- | --- | --- | --- |
| Device Service | lease、虚拟 Flash、串口、frame/input/QOM、网络故障、pcap、evidence、历史恢复和本地 worker 生命周期 | 跨主机接管、生产池、模块边界仍偏大 | `serve.py`、`device_service.py` |
| 统一运行时 | S3/C6/Core2 在同一 lease/guest 中组合板级、WiFi、BLE 和 evidence；Core2 规范 BLE 路径为 `core2-native-hci` | 真机、RF、bit-exact controller、物理 PSRAM/cache | `platform/qemu/profiles.json`、`tests/uiflow2/` |
| 网络 | controlled DNS/TLS、有界 IPv4/IPv6 egress、CNAME、WPA2、错误密码、断线恢复、双 guest fabric 和 pcap | 任意 NAT、跨物理主机、不可信固件 VM 沙箱 | `network_*.py`、`tests/network/` |
| Worker | durable queue、HMAC、HTTPS/mTLS、轮换、发现、restart/reattach、跨容器 QEMU 和 process/companion fencing | 物理跨主机、迁移、外部 side effect ownership、生产调度 | `worker_*.py`、`transport_security.py` |
| 固件审查 | FirmwareManifest、WebBurner/M5Burner/ESP-IDF、ZIP/资源/build 选择策略、capability、文件系统、SD/NVS fixture、静态审查、Secure Boot v2 镜像分析和 Device Service runtime ACL | guest filesystem ACL、完整许可、live eFuse/trust root、生产 key、真实云端业务 | `firmware_*.py`、`user_firmware_matrix.py`、`runtime_acl.py` |
| 设备差异 | ESP32 设备矩阵可由 Device Service 创建；Tab5 与 CardputerZero 是独立后端 | Tab5 外设、CardputerZero 长期回归、逐设备视觉保真 | `devices/`、`platform/peripherals/` |

最近这一轮只改变调查边界，不改变产品结论：

- shared I2C、equal-deadline timer、TIMG WDT mask、stateful SSI、pending
  SPI remap、high-priority DPORT IRQ 协作和 classic RMT 已是可重放的修复
  或验证控制；它们仍没有让 legacy 固件完成正常启动；
- state sweep、setter trace、三次 WDT liveness 和 WDT-off late-state 已逐项
  排除当前配置下的 UART storm、永久 handoff deadlock、TG1 feed 停止和
  “Flash 扫描永不结束”；late state 的 CPU1 `0x40100049` 已由 BIN-bound
  反汇编绑定到 LVGL `lv_refr_vdb_flush`；
- `0065` 关闭 scheduler-induced DPORT handoff deadlock，`0066` 让 legacy
  Serial 越过 Neopixel RMT 初始化并到达 `APIKEY`；当前最窄的下一步是定位
  `APIKEY` 后首个未完成 guest/controller 路径，并让 display completion、
  `lv_disp_flush_ready`、setup/REPL 和非空帧可观测；matching ELF/MAP 可
  并行提高符号置信度；
- 当前事实只在[项目当前状态](project-status.md)，详细证据只在
  [验证证据台账](validation-ledger.md)；本页不再复制逐次运行时间线。

## 最近成果已经并入哪里

已完成里程碑只保留为依赖摘要，精确轮次、SHA、检查数量和 evidence 路径
统一在[验证证据台账](validation-ledger.md)维护。当前稳定代码面的摘要如下：

- 网络：controlled DNS/CNAME、domain/CIDR egress、TLS Host policy、pcap、
  WPA2 正误密码、断线与 DHCP renewal 已进入 unified/namespace 路径；
- Worker：durable queue、认证、TLS/mTLS、轮换、发现、控制/执行面分离、
  restart/reattach、跨容器 QEMU 和 side-effect fencing 已落地；
- Core2：native-HCI、WiFi/公网/GATT、QOM PSRAM/MMU、长稳、重连、
  active-stop 和当前服务容量门禁已有虚拟设备证据；
- 固件：Manifest/WebBurner 的 ZIP/资源/build 选择 fail-closed 规则、
  capability/security、文件系统、SD/NVS fixture 和 SHA-bound review
  expectation 已可执行；
- 运行与分发：Device Service、Live sessions、WebBurner、macOS arm64 runtime
  bundle 和 generic ESP32-S3 observe 路径可用。

本页不复制运行流水；当前结论只来自状态页，开放项只来自 Backlog。

## 成熟度怎么看

| 工作流 | 当前可执行面 | 阶段 | 主要边界 |
| --- | --- | --- | --- |
| 设备与统一运行时 | `runtime=qemu-unified` 单 guest 返回板级、WiFi、BLE 和 evidence | `PILOT` | 真机、RF 和未建模控制器 |
| 网络与取证 | controlled DNS/CNAME、有界 CIDR、TLS Host 策略、pcap、重连、双 guest fabric、cross-subnet seed discovery | `PILOT` | 物理跨主机、无 reachable seed 的 NAT、任意公网解析 |
| Worker 与恢复 | durable queue、409/network-partition fence、OS process + real QEMU PID reap、HMAC、HTTPS/mTLS、rotation、multicast/unicast discovery、restart/reattach、跨容器 QEMU | `PILOT` | 物理跨主机、生产调度、QEMU 内 guest/device-controller 和 worker 未拥有的外部 side effect |
| Core2 | native-HCI、公网 WiFi、同 guest 重连、active-stop、post-reset stop、bounded TCG/固定 icount、8 MiB PSRAM MMU、虚拟 PSRAM 压力和当前容量内并发 | `PILOT` | 大于当前服务容量、物理 PSRAM/cache timing、bit-exact controller、持续吞吐和更复杂 teardown |
| 通用固件审查 | Manifest/WebBurner 导入选择、capability/security、Secure Boot v2 image signature 结构/摘要/数学验证、包内 eFuse 摘要与 anti-rollback version 对照、文件系统、SD/NVS、公开矩阵和 service runtime ACL | `PARTIAL` | 包内 eFuse 来源与公钥 trust root、bootloader anti-rollback 执行、guest filesystem 权限、完整许可、真机 key、更多固件族 |
| Tab5 P4 | 烧录、显示、触摸、RS-485、ESP-Hosted、部分 I2C | `PARTIAL` | CSI、I2S/PCM、USB Host、SDIO、动态 I2C、ST7123 |
| CardputerZero | 独立 Linux ARM64 后端、显示、输入、音频、USB、摄像头帧回放 | `PARTIAL` | 完整系统回归、生产级时序和真机 |
| 真机验证 | 已有测试入口和证据规则 | `NOT RUN` | 物理设备上的同固件路径验证 |

阶段不是营销标签：

- `DELIVERED`：主路径已实现，契约测试和同路径虚拟设备 evidence 通过；
- `PILOT`：功能可执行，但生产服务、完整 controller 或真机等价仍有距离；
- `PARTIAL`：存在可用子集，同时有明确的数据面或后端 blocker；
- `NOT RUN`：所需路径没有执行，不能由 build、静态分析或其他 lease 推导 PASS。

## 代码怎么读

建议按下面的调用链阅读，而不是从最大的源文件开始逐行浏览：

```text
devices/catalog.source.json
  -> platform/peripherals/catalog.json
  -> platform/peripherals/runtime-coverage.json
  -> platform/qemu/profiles.json
  -> platform/tools/device_service.py
  -> tests/uiflow2/ + tests/network/ + tests/firmware/
  -> retained session + evidence JSON/ZIP
```

| 代码面 | 主要入口 | 作用 |
| --- | --- | --- |
| 设备/外设/后端登记 | `devices/`、`platform/peripherals/`、`platform/qemu/` | 声明真实硬件、模型覆盖和可执行 profile |
| QEMU/板级模型 | `patches/` | SoC 控制器、板级器件、DMA/FIFO/端点 |
| Device Service | `platform/tools/serve.py`、`device_service.py` | lease、Flash、runtime、网络、输入、证据和生命周期 |
| Worker | `worker_queue.py`、`worker_agent.py`、`worker_auth.py`、`transport_security.py`、`worker_discovery.py`、`worker_discovery_seed.py` | 排队、执行、认证、TLS、multicast/unicast 发现、恢复和结果回报 |
| 固件审查 | `firmware_manifest.py`、`firmware_analysis.py`、`firmware_filesystems.py`、`firmware_static_review.py` | 导入/资源选择、规范化、capability/security、文件系统和静态审查 |
| 网络 | `network_policy.py`、`network_egress.py`、`network_sandbox.py`、`network_fabric.py` | DNS/CNAME、nftables、namespace、veth/NAT、双 guest fabric |
| Web | `platform/web/` | 设备目录、Live sessions、输入、WebBurner 和报告 |
| 验证 | `platform/tests/`、`tests/uiflow2/`、`tests/network/`、`tests/firmware/` | 契约、设备本地数据面、网络/worker 和固件审查 |

当前生产代码没有未处理的 `TODO/FIXME/HACK`。代码整理的主要债务是边界，而
不是散落的标记：

- `device_service.py` 同时承担存储、runtime、证据和 session 状态机，拆分由
  `SVC-03` 跟踪；
- `test_device_service.py` 仍是大型 service 契约测试；文档契约已从单一
  6400 行文件拆成五个领域模块，并保留 `test_docs_consistency.py` 兼容入口；
  当前状态页和 stale-claim 目录也已收敛；
- 当前仓库没有从空目录重建全部运行时的 bootstrap；macOS arm64 有可复现
  release 包，其他主机仍需匹配 commit/架构的 runtime 资产；
- Tab5 的闭源 `esp-emu` 后端必须视为单独边界，不能把 QEMU S3/C6/LX6 的
  完成度继承给 P4。

详细模块、消费者和测试归属见[代码与验证入口地图](code-map.md)。

## 当前工作流

### 设备和运行时

产品验收路径是 `runtime=qemu-unified`：一个 lease、一个固件、一个 guest、
一份 evidence。S3/C6 已把板级、WiFi、BLE 和网络证据放进同一 session；
Core2 使用 `profile=core2-native-hci`，旧 `core2-native-vhci` 只保留为 GDB
诊断/兼容路径。

任何 `PASS` 都只对设备、固件 SHA、runtime/profile、输入和观察窗口成立。
`running`、HTTP 200、非空首帧或单条串口 marker 都不能单独代替应用 PASS。

### 网络

已实现的网络安全面包括：

- private namespace、controlled resolver、TLS/Host allowlist 和 pcap；
- 有界 IPv4/IPv6 地址/CIDR + protocol + port egress；
- exact A/AAAA、domain suffix 和最多 8 跳 CNAME chain；
- 同 guest CNAME→terminal A→HTTP、拒绝域名/端口和 cleanup；
- WPA2-PSK 正确/错误密码、radio/AP 丢失恢复和 DHCP renewal；
- 两个 guest 的 private QEMU socket L2 fabric；
- central control plane 与 worker-local runtime/QEMU 在同主机 namespace
  和独立 Docker 容器中的分离执行。

网络 PASS 仍不是 RF/PHY、任意公网服务或恶意固件 VM 沙箱。

### Worker

控制面和执行面已经拆开：central 负责 queue、claim、heartbeat 和 result；
worker-local runtime Device Service 负责 session、QEMU、evidence 和 stop。
已覆盖同主机 restart、QEMU/QMP ownership reattach、trusted-host HTTP/BLE
companion continuity、session-create idempotency 和跨容器 QEMU。

multicast 不能跨 subnet 时，worker 可从 reachable HMAC-signed unicast seed
取得 control URL；该路径已在 routed/masqueraded subnet fixture 中通过。
尚未覆盖物理跨主机进程迁移、无 reachable seed 的任意 NAT traversal、跨主机幂等存储、
namespace-managed/Tab5/cross-host companion 和生产多机调度。

### 通用固件审查

固件结果必须分层记录：

1. artifact/Manifest：大小、SHA、芯片、分区和 capability；
2. static/security：URL、凭据、SBOM、许可声明、文件系统和安全证据；
3. runtime：boot marker、frame/input 或 headless marker、外设数据面；
4. network/BLE：同 guest 的服务、DNS、TCP/UDP、pcap 或 HCI/GATT；
5. persistence：Flash/NVS/文件系统和结束状态；
6. hardware：物理 RF、功耗、声学、光学、机械和安全模式。

模型缺口、fixture 缺失、基础设施错误和固件 FAIL 必须分开。公开 CDN 的对象
可能在相同 ID/version 下变化，因此每次矩阵运行都要重新下载并绑定当前 SHA。

## 接下来做什么

`UNIT-01` 在独立工作树推进公开视觉模型与 Unit 控制器集成。实现契约见
[Unit 集成计划](plans/2026-10-25-unit-runtime-integration.md)，官方芯片/协议
和接线登记在 `platform/units/`；接入期间的主机问题另见
[Unit 接入问题](unit-integration-host-issues.md)。视觉与协议目录不代表 guest
数据面已验收，具体运行能力仍由状态页和同路径 evidence 决定。
`UNIT-HOST-36` 已关闭 Relay/Relay2 的数字 hard-reset 基线/计数边界，但不关闭
FlashLight reset、其它 Unit 或机械/电气状态；实现和 A/B 入口见
[本块证据](evidence/2026-10-29-unit-hard-reset-output-boundary/README.md)。
`UNIT-HOST-37` 已关闭 FlashLight cold constructor/低基线；四台 S3 主机的原厂
API 与同 PID Run 替换通过，mounted Web 为 actual-QOM snapshot replay，
实时轮询、动态 S1/PWM 和物理光电/热仍独立，见
[四host证据](evidence/2026-10-29-flashlight-cold-route-four-host/README.md)。

执行顺序和验收只由[项目 Backlog](project-backlog.md)维护。当前 P0 的最小
交付可以概括为：

| Task | 下一步 | 为什么还不能关闭 |
| --- | --- | --- |
| `RUNTIME-03` | 保持 `0065` DPORT IRQ 协作与 `0066` classic RMT 回归；从最终 `APIKEY` 状态定位下一个未完成路径。同版本 ELF/MAP 可并行取得 | normal-WDT reset、LVGL completion、`lv_disp_flush_ready`、setup/REPL 和同 SHA 非空应用帧仍 OPEN；RMT 初始化或独立 SPI PASS 不外推 |
| `NET-04` | 物理跨主机 executor/reattach、无 reachable seed 的任意 NAT traversal、queue/session/evidence 的跨主机复制、QEMU guest/controller 内部状态和 worker 未拥有的外部 side effect | claim/evidence response-loss idempotency、lease-bound central evidence、409 与 network partition 已 fence worker-owned OS/QEMU process 和 `qemu-unified` companions；同 control-plane state-dir、跨容器和同机 subnet/NAT 仍不能替代物理主机/对象存储 |
| `CORE2-02` | 补大于当前服务容量；同时补 bit-exact controller/baseband、物理 PSRAM/cache timing、持续吞吐和 active-stop/post-reset 之外 teardown | 当前容量、旧失败 control 和 `shift=auto` trace 只证明各自窗口，不能外推到更大规模或物理 controller |
| `FW-01` | Guest filesystem ACL/权限、完整源码/依赖许可和法律审批 | 镜像属性、service runtime ACL 或声明扫描都不是 guest 文件权限 PASS |
| `FW-02` | 真机 secure boot、Flash Encryption、live eFuse、bootloader anti-rollback 和生产 key 流程 | 包内 sdkconfig/eFuse summary 只是自报证据；摘要 match 或 version satisfied 不等于运行时已执行 |
| `FW-03` | 真实 key/cloud 业务与更多设备/固件族 | 当前样本和 network-first 覆盖不等于任意固件 |
| `RUNTIME-02` | C6 Zigbee commissioning/join 或明确不支持 | 观察到 802.15.4 帧不等于完整生命周期 |
| `RUNTIME-04` | 已关闭 Core2 for AWS ATECC608 初始化/identity；ECDSA、生产 slot/trust root、电气和真机独立 | 三个公开固件 session 通过非空帧，但测试 fixture 不代表生产安全元件 |
| `RUNTIME-06` | ESP-NOW loss/retry and long-run stability | controller loopback/plaintext/CCMP/replay/lifecycle、stock key-state、shared-LMK fabric、peer-MAC→pairwise-LMK、cross-wire、PN exhaustion 和 new/same-LMK rekey 已验证；loss/retry、channel/rate、RF 或 long-run timing 仍未覆盖 |
| `SVC-01` | namespace-managed/Tab5/cross-host companion、跨主机 session/evidence 存储和连续 evidence 流 | durable claim response-loss replay、trusted-host 和单机 restart PASS 不能继承为跨主机 |
| `SVC-02` | warm pool、配额、对象存储、审计和容量观测 | 当前仍是 cold/on-demand 本地服务 |
| `SVC-03` | 拆分 service 的存储、runtime、evidence 和 session 状态机 | 维护边界仍集中在少数大文件 |
| `HW-01` | 代表设备同固件 SHA 真机验证 | 仓库目前没有 hardware validation 结果 |
| `TAB5-01` | 可扩展/可重建 P4 backend | 闭源后端缺少多个必需端点和数据面 |
| `UI-01` | 逐设备高保真外壳、hitbox 和视觉阈值 | 除 StopWatch 外仍是近似外壳 |
| `UI-02` | 公众工作台、Pages 分享入口与 browser backend 调研 | 见[公众入口计划](plans/2026-10-28-public-simulator.md)；限定browser/原生fixture与模型验收见证据；创建响应丢失后的恢复与安全停止已有限定真实证据；正式 GitHub Pages 已部署并从公开 HTTPS 地址完成 21 项真实 CoreS3 验收，更多原生固件仍单列扩展 |
| `CZ-01` | CardputerZero 完整系统、驱动和长期回归 | 独立 Linux 后端不能继承 ESP32 结论 |

如果跨主机环境暂时不可用，先扩展 QEMU 内 guest/device-controller side-effect fencing、
worker 未拥有外部 side effect 的 ownership 契约或跨主机
idempotency/recovery，不应把单机 namespace/subnet 结果改写成跨主机完成。

## 文档怎么维护

| 文档 | 职责 | 不应放什么 |
| --- | --- | --- |
| 本页 | 人读交接、代码阅读顺序和工作流摘要 | 动态计数、逐次 PASS 流水 |
| `project-status.md` | 当前能力、风险和验证边界 | 未完成 Task 的完整计划 |
| `project-backlog.md` | 未完成 Task、依赖和验收 | 已完成的运行流水 |
| `project-snapshot.md` | 机器生成的设备、样本、Task 和规模计数 | 人工结论 |
| `validation-ledger.md` | 按日期保存单次检查项和 evidence | 当前能力定义 |
| `code-map.md` | 源码、测试、证据和维护债 | 产品当前结论 |
| `unified-device-runtime.md` | 单 lease/单 guest 验收契约 | 设备完成计数 |
| 专题页 | 深入解释某个模型、网络或工作流 | 与其他页面重复的 P0 状态表 |
| 历史页 | 固定当时根因、截图或设计 | 被后续证据推翻的“当前”结论 |

新工作应先登记 Backlog Task，再改代码和测试；验证后追加 evidence，更新当前
状态，最后运行 `project_snapshot.py --write`。日期较早的专题页如果没有明确
标为历史，至少要先核对它链接的当前状态页和 evidence。

## 最小验证集

```bash
PYTHONPATH=platform/tools python3 -m unittest discover \
  -s platform/tests -p 'test_*.py'
python3 platform/tools/runtime_coverage.py --check
python3 platform/tools/peripheral_catalog.py --check
python3 platform/tools/qemu_profiles.py --check
python3 platform/tools/project_snapshot.py --check
git diff --check
```

设备或外设改动再运行对应 `tests/uiflow2/run_peripheral_matrix.py --case`
或 `--device`。只有共享 SoC/controller、批量设备变化或里程碑才运行完整
matrix。

Agent 触发的普通功能测试必须走 Device Service `/api/v1`，让 session 在 Live
sessions 可观察并在停止后保留历史；直接 QEMU runner 只用于仓库回归开发和
证据复现。
