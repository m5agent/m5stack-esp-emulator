# 工作流总台账

日期：`2026-10-28`

本页只回答“某项工作由哪条代码链负责、当前事实和未完成项应该去哪里看”。
它不保存 PASS 计数、固件 SHA、运行流水或第二份执行顺序。

## 权威顺序

| 问题 | 入口 |
| --- | --- |
| 一页理解产品、代码阅读顺序和下一步 | [工程交接总览](engineering-handoff.md) |
| 当前到底支持什么、边界是什么 | [项目当前状态](project-status.md) |
| 还有什么没完成、验收是什么 | [项目 Backlog](project-backlog.md) |
| 某项结论何时、用什么 evidence 验证 | [验证证据台账](validation-ledger.md) |
| 设备、样本、缺口和 Task 的动态计数 | [自动项目快照](project-snapshot.md) |
| 源码、测试和生成物在哪里 | [代码与验证入口地图](code-map.md) |
| 已知 `runtime_model_gap` 和关闭条件 | [运行时模型缺口登记](runtime-model-gap-register.md) |

发生冲突时，以当前代码、同提交生成物和最新 evidence 为准；当前能力回写
`project-status.md`，未完成范围回写 `project-backlog.md`。

## 工作流路由

| 工作流 | 稳定代码面 | 当前事实 | 未完成 Task |
| --- | --- | --- | --- |
| 设备、板级与统一运行时 | `devices/`、`platform/qemu/`、`patches/`、`tests/uiflow2/` | `runtime=qemu-unified` 在单 lease、单 guest 内组合板级、WiFi、BLE、frame/QOM 和 evidence；Core2 使用 `core2-native-hci` | 新增设备按 onboarding 流程；不设独立 Task |
| 网络隔离、双 guest fabric 与 worker | `network_*.py`、`worker_*.py`、`transport_security.py`、`tests/network/` | namespace、controlled DNS/TLS、CNAME、有界 IPv4/IPv6 egress、pcap、双 guest、跨 container 的 worker-local QEMU、同 guest IPv6 TCP/HTTP、generation-pointer credential migration、lease ownership `409` fencing、network-partition process/QEMU/`qemu-unified` companion fencing 和 companion continuity 已进入统一执行链；`NET-05`、`NET-06` 已完成当前虚拟设备范围 | `NET-04`：物理跨主机 executor/reattach、跨主机 idempotency、无 reachable seed 的任意 NAT traversal、QEMU 内 guest/device-controller side effect、namespace-managed/Tab5/cross-host companion 和生产调度 |
| Core2 无线、映射与长稳 | `tests/uiflow2/core2_native_hci/`、`unified_core2/`、`ble_probe.py`、`ble_runtime_limits.py`、`qemu_accel.py` | native-HCI、WiFi/公网/GATT、8 MiB PSRAM QOM、upper-bank MMU、重连、active-stop 和当前单设备容量门禁已有虚拟设备证据 | `CORE2-02`：大于当前服务容量、持续吞吐、active-stop 之外 teardown、bit-exact controller/baseband、物理 PSRAM/cache timing 和真机 |
| 固件导入、静态审查与安全 | `firmware_*.py`、`fetch_firmware.py`、`user_firmware_matrix.py`、`platform/web/firmware.*` | FirmwareManifest、WebBurner/M5Burner/ESP-IDF 导入、ZIP/资源/build 选择 fail-closed、capability、文件系统、SD/NVS fixture、SBOM、许可声明和 Secure Boot v2 镜像分析可执行 | `FW-01`、`FW-02`、`FW-03`：运行态 ACL/完整许可、live eFuse/生产 key、真实云端业务和更多固件族 |
| 运行时模型缺口 | runtime coverage、QEMU patches、firmware/runtime evidence | `RUNTIME-01` Flash/PMP 与 `RUNTIME-05` S3 WPA2 已关闭；`RUNTIME-03` 已修复 shared I2C、timer、WDT mask、stateful SSI、pending SPI remap 和 classic RMT，并由 `0065` 关闭 high-priority DPORT handoff 调度死锁。legacy Serial 到达 `APIKEY`，但 normal-WDT reset、WDT-off 黑帧、display completion、setup/REPL 和非空帧继续 OPEN。`0067` 已补齐 ESP-NOW controller TX/RX DMA 的默认关闭 peer loopback，外部/加密 peer 仍 OPEN | `RUNTIME-02`、`RUNTIME-03`、`RUNTIME-04`、`RUNTIME-06` |
| Device Service 与生命周期 | `serve.py`、`device_service.py`、`storage_policy.py`、docs contract tests | lease、history、artifact upload、QEMU/QMP 与 companion recovery、控制面/本地 runtime API 分离可执行 | `SVC-01`、`SVC-02`、`SVC-03` |
| 真机同路径验证 | Device Test Center 和硬件证据流程 | 已有测试入口与分层规则；当前仓库结论仍以 virtual-device validation 为主 | `HW-01` |
| Tab5 P4 后端 | `platform/runtime/wasm/`、P4 patches、`tests/uiflow2/tab5_*` | 烧录、画面、触摸、RS-485、ESP-Hosted 和部分 I2C 可用，外设仍为 `partial` | `TAB5-01` |
| 设备视觉保真 | `platform/web/device-shell*`、设备 renderer | 功能验证与视觉保真分开；StopWatch 是参考质量外壳 | `UI-01` |
| 外接 Unit 与新外壳 | `platform/units/`、`unit_runtime.py`、`platform/web/model-shell.js`、Unit panel | 固定公开视觉源、官方芯片/接线目录与会话接口正在集成；guest 数据面单独验收 | `UNIT-01` |
| CardputerZero | `patches/qemu-linux-arm64-cardputerzero/`、`tests/cardputer_zero/` | 独立 Linux ARM64 后端有显示、输入、音频、USB、摄像头和 Ethernet 子集 | `CZ-01` |

## 历史证据索引

以下编号只用于定位已记录的历史事实，不代表当前 PASS：

- `0032` TIMG trace 与 `0034` equal-deadline `CCOMPARE` 修复曾分别用于定位
  interrupt-WDT 和最小 `READ_START` probe 的 timer 问题；`0035` 修复 QIO
  路径中的 TIMG WDT mask，`0036` 验证 stateful SSI 数据面；
- `0037` 统一记录 cross-core、flash-cache、DPORT、SSI、UART 和 TIMG
  timeline，`0038` 增加 exact-time pause，`0039/0040` 分别记录 state sweep
  与 setter trace；normal-WDT reset 前完成约 `4,376` 次 handoff，否定永久
  deadlock，历史 `800 ms` TG1 gap 在后续当前配置检查中为未复现；
- `0041/0042` 将 WDT-off late-state 的 CPU1 `0x40100049` 收敛到 LVGL
  double-buffer flush wait，并验证 SPI `TRANS_DONE/TRANS_INTEN` IRQ level；
  legacy normal-WDT completion 仍未闭环。
- `0065` 将旧固定双 PC 解释为 TCG icount slice 下的 DPORT start/end
  ordering artifact，并在 level-4/5 `memw`/`retw` 协议点协作让出；
  `0066` 补 classic ESP32 RMT，移除 Neopixel translator 初始化错误并让
  legacy Serial 到达 `APIKEY`。两者都不关闭 normal-WDT、LVGL 或应用帧。

## Task ID 索引

| Task | 状态 | 一句话范围 |
| --- | --- | --- |
| `API-01` | 进行中 | CoreS3/Cardputer-ADV 双主机接口审计与运行时/SDK修正已交付；stock失败、模型/配置/可选外设缺口继续按审计证据推进 |
| `NET-04` | 进行中 | 物理跨主机和 P0 网络产品化剩余边界 |
| `CORE2-02` | 进行中 | Core2 controller、物理时序、容量和 teardown 边界 |
| `FW-01` | 进行中 | 运行态权限、ACL、完整许可与审批 |
| `FW-02` | 进行中 | 真机 Secure Boot、Flash Encryption、eFuse 和生产 key |
| `FW-03` | 进行中 | 真实云端业务、更多设备与固件族 |
| `RUNTIME-02` | 进行中（backend blocked） | C6 Zigbee/802.15.4 commissioning |
| `RUNTIME-03` | 进行中 | high-priority DPORT handoff 与 classic RMT 已修复；Core2 legacy UIFlow 到 `APIKEY` 后仍 normal-WDT reset/黑帧，尚无 display completion、setup/REPL 或 non-empty frame |
| `RUNTIME-04` | 进行中 | Core2 for AWS ATECC608 fixture |
| `RUNTIME-06` | 进行中 | ESP-NOW 同 guest controller-DMA loopback 已有三设备证据；外部 peer、PMK 加密 payload、跨设备 fabric 与 RF/timing 仍 OPEN |
| `SVC-01` | 进行中 | 跨主机/namespace-managed/Tab5 companion 与跨主机幂等 |
| `SVC-02` | 待做 | warm pool、配额、对象存储、审计和多机容量 |
| `SVC-03` | 待做 | 拆分 `device_service.py` 编排热区 |
| `HW-01` | 待做 | 代表设备同固件 SHA 真机验证 |
| `TAB5-01` | 决策 | 重建或扩展 P4 backend |
| `UI-01` | 待做 | 逐设备结构、材质、hitbox 和视觉回归 |
| `UI-02` | 进行中 | 公众工作台、Pages 分享与浏览器执行可行性；边界见[调研](browser-runtime-feasibility.md)，范围见 Backlog |
| `UNIT-01` | 进行中 | 外壳固定版本、Unit 控制器与主机端口、Web 双向状态及逐型号证据 |
| `CZ-01` | 待做 | CardputerZero 系统、驱动和长期回归 |

Task 的依赖、下一项最小交付和验收条件只在
[项目 Backlog](project-backlog.md)维护。

## 当前推进顺序

| 通道 | 当前内容 | 推进条件 |
| --- | --- | --- |
| 当前调查 | `RUNTIME-03`：保持 `0065/0066` 的 DPORT 协作、classic RMT 和三设备设备组回归；从最终 `APIKEY` 状态定位 normal-WDT reset 与 display completion 的首个未完成路径；matching ELF/MAP 可并行取得 | 本地 Core2 runtime；WDT-off 只是诊断 control；RMT 初始化、独立 SPI probe、UIFlow2 设备组或 302-byte 黑帧升级前不得声明 legacy PASS |
| 可并行工程 | `FW-01`、`FW-03`、`SVC-03`、`UI-01`、`CZ-01` | 当前仓库和现有虚拟设备即可推进；代码拆分遵守“一次只移动一个边界” |
| 需要多机环境 | `NET-04` 以及依赖它的跨主机部分 | 两个可失联、可 drain、可独立寻址的节点；单机 namespace/container 不计为完成 |
| 需要真机/授权 | `FW-02`、`HW-01` | 同固件 SHA 的设备控制、外部观测和敏感 key/eFuse 流程授权 |
| 后端/外部阻塞 | `RUNTIME-02`、`RUNTIME-04`、`RUNTIME-06`、`TAB5-01` | 可重建 radio MAC 路径、匹配 ELF/ATECC fixture、两个独立 guest/外部 ESP-NOW peer，或明确的 P4 backend 决策 |

完成一轮工作后的固定顺序是：先落 evidence，再更新
`validation-ledger.md`；只有能力或边界变化时才改 `project-status.md`；
开放范围变化才改 `project-backlog.md`；最后重新生成项目快照。

## 状态语义

| 状态 | 含义 |
| --- | --- |
| `DELIVERED` | 主路径已实现，当前契约测试和同路径虚拟设备 evidence 通过 |
| `PILOT` | 功能已跑通，但生产服务、完整控制器或真机等价仍有距离 |
| `PARTIAL` | 已有可用子集，同时存在明确的数据面或后端 blocker |
| `FAIL` | 同一路径已有可复现失败 evidence；不能被其他 lease 的 PASS 覆盖 |
| `BACKLOG` | 设计或边界已明确，但尚未形成可用实现 |
| `HARDWARE NOT RUN` | 没有完成同固件路径的物理硬件验证 |

除非明确标注 `hardware validation`，所有项目结论都是
`virtual-device validation`。QEMU 功能网络不是 RF、天线、安全模式或功耗
模型；“能联网”和“物理无线行为通过”必须分开记录。

## 变更流转

1. 新工作先进入 `project-backlog.md`，分配稳定 Task ID、依赖和验收条件。
2. 在 `code-map.md` 登记代码与测试入口，不在多个页面复制运行计数。
3. 验证后把带日期的检查项和 evidence 追加到 `validation-ledger.md`。
4. 达到验收条件后更新 `project-status.md`，并从 Backlog 删除该项。
5. 运行 `project_snapshot.py --write`，并让 `--check` 通过。
6. 外部结论使用完整 commit SHA 的 work-record permalink，并准确标注
   `virtual-device validation` 或 `hardware validation`。
