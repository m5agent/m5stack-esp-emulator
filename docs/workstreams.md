# 工作流总台账

日期：`2026-10-26`

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
| 固件导入、静态审查与安全 | `firmware_*.py`、`fetch_firmware.py`、`user_firmware_matrix.py`、`platform/web/firmware.*` | FirmwareManifest、WebBurner/M5Burner/ESP-IDF 导入、capability、文件系统、SD/NVS fixture、SBOM、许可声明和 Secure Boot v2 镜像分析可执行 | `FW-01`、`FW-02`、`FW-03`：运行态 ACL/完整许可、live eFuse/生产 key、真实云端业务和更多固件族 |
| 运行时模型缺口 | runtime coverage、QEMU patches、firmware/runtime evidence | `RUNTIME-01` Flash/PMP 与 `RUNTIME-05` S3 WPA2 已关闭；`RUNTIME-03` 的 Core2 shared I2C routing 已修复。修正后的最小 ESP-IDF 探针 20/20 进入 partition read，合并 current/portable 结果为 `14 PASS / 6 interrupt-WDT`；失败时两核位于 idle `waiti`。当前工作假设是虚拟定时器/中断交付与宿主调度模型差异，spinlock/CAS 未获最小探针支持；legacy 非空应用帧仍开放 | `RUNTIME-02`、`RUNTIME-03`、`RUNTIME-04` |
| Device Service 与生命周期 | `serve.py`、`device_service.py`、`storage_policy.py`、docs contract tests | lease、history、artifact upload、QEMU/QMP 与 companion recovery、控制面/本地 runtime API 分离可执行 | `SVC-01`、`SVC-02`、`SVC-03` |
| 真机同路径验证 | Device Test Center 和硬件证据流程 | 已有测试入口与分层规则；当前仓库结论仍以 virtual-device validation 为主 | `HW-01` |
| Tab5 P4 后端 | `platform/runtime/wasm/`、P4 patches、`tests/uiflow2/tab5_*` | 烧录、画面、触摸、RS-485、ESP-Hosted 和部分 I2C 可用，外设仍为 `partial` | `TAB5-01` |
| 设备视觉保真 | `platform/web/device-shell*`、设备 renderer | 功能验证与视觉保真分开；StopWatch 是参考质量外壳 | `UI-01` |
| CardputerZero | `patches/qemu-linux-arm64-cardputerzero/`、`tests/cardputer_zero/` | 独立 Linux ARM64 后端有显示、输入、音频、USB、摄像头和 Ethernet 子集 | `CZ-01` |

## Task ID 索引

| Task | 状态 | 一句话范围 |
| --- | --- | --- |
| `NET-04` | 进行中 | 物理跨主机和 P0 网络产品化剩余边界 |
| `CORE2-02` | 进行中 | Core2 controller、物理时序、容量和 teardown 边界 |
| `FW-01` | 进行中 | 运行态权限、ACL、完整许可与审批 |
| `FW-02` | 进行中 | 真机 Secure Boot、Flash Encryption、eFuse 和生产 key |
| `FW-03` | 进行中 | 真实云端业务、更多设备与固件族 |
| `RUNTIME-02` | 进行中（backend blocked） | C6 Zigbee/802.15.4 commissioning |
| `RUNTIME-03` | 进行中 | Core2 legacy UIFlow 后初始化 WDT、reset reason 和非空应用帧 |
| `RUNTIME-04` | 进行中 | Core2 for AWS ATECC608 fixture |
| `SVC-01` | 进行中 | 跨主机/namespace-managed/Tab5 companion 与跨主机幂等 |
| `SVC-02` | 待做 | warm pool、配额、对象存储、审计和多机容量 |
| `SVC-03` | 待做 | 拆分 `device_service.py` 编排热区 |
| `HW-01` | 待做 | 代表设备同固件 SHA 真机验证 |
| `TAB5-01` | 决策 | 重建或扩展 P4 backend |
| `UI-01` | 待做 | 逐设备结构、材质、hitbox 和视觉回归 |
| `CZ-01` | 待做 | CardputerZero 系统、驱动和长期回归 |

Task 的依赖、下一项最小交付和验收条件只在
[项目 Backlog](project-backlog.md)维护。

## 当前推进顺序

| 通道 | 当前内容 | 推进条件 |
| --- | --- | --- |
| 当前调查 | `RUNTIME-03`：关联 TIMG/CCOMPARE/INTENABLE/INTSET、虚拟时间和宿主调度，解释最小探针在 `READ_START` 后的 interrupt-WDT；再验证 legacy UIFlow 的 flash-cache/IPC/DPORT 路径并拿到同 SHA 非空应用帧 | 本地 Core2 runtime；涉及 `m5core2` QEMU 时与 `CORE2-02` 串行 |
| 可并行工程 | `FW-01`、`FW-03`、`SVC-03`、`UI-01`、`CZ-01` | 当前仓库和现有虚拟设备即可推进；代码拆分遵守“一次只移动一个边界” |
| 需要多机环境 | `NET-04` 以及依赖它的跨主机部分 | 两个可失联、可 drain、可独立寻址的节点；单机 namespace/container 不计为完成 |
| 需要真机/授权 | `FW-02`、`HW-01` | 同固件 SHA 的设备控制、外部观测和敏感 key/eFuse 流程授权 |
| 后端/外部阻塞 | `RUNTIME-02`、`RUNTIME-04`、`TAB5-01` | 可重建 radio MAC 路径、匹配 ELF/ATECC fixture，或明确的 P4 backend 决策 |

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
