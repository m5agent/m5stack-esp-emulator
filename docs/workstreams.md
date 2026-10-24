# 工作流总台账

日期：`2026-10-24`

本页只维护工作流归属、稳定代码入口、当前权威状态入口和未完成 Task ID。
它不复制测试轮数、PASS 计数、固件 SHA 或逐设备结论：

- 设备、后端、固件样本和 Task 板自动汇总：
  [项目快照](project-snapshot.md)。
- 当前能力、风险和证据边界：[项目当前状态](project-status.md)。
- 未完成 Task、依赖和验收：[项目 Backlog](project-backlog.md)。
- 带日期的证据：[验证证据台账](validation-ledger.md)。
- 代码和测试入口：[代码与验证入口地图](code-map.md)。

## 工作流

| 工作流 | 稳定代码面 | 权威状态 | 未完成 Task |
| --- | --- | --- | --- |
| 设备、板级与统一运行时 | `devices/`、`platform/qemu/`、`patches/`、`tests/uiflow2/` | `project-status.md` 的设备矩阵和统一运行时章节 | 无独立 Task；新增设备必须走 onboarding |
| Device Service 与生命周期 | `serve.py`、`device_service.py`、`storage_policy.py` | `device-service-api.md`、`project-status.md` | `SVC-01`、`SVC-02`、`SVC-03` |
| 网络隔离、双 guest lab fabric 与 worker | `network_*.py`、`worker_*.py`、`transport_security.py`、`tests/network/` | `network-simulation-plan.md`、`device-service-api.md` | `NET-04`、`NET-05` |
| Core2 无线与长稳 | `core2_native_hci/`、`unified_core2/`、`ble_probe.py`、`ble_runtime_limits.py` | `core2-native-hci-backend.md`、`project-status.md` | `CORE2-02` |
| 固件导入、静态审查与安全 | `firmware_*.py`、`fetch_firmware.py`、`user_firmware_matrix.py`、`platform/web/firmware.*` | `firmware-manifest.md`、`user-firmware-simulation-matrix.md` | `FW-01`、`FW-02`、`FW-03` |
| 运行时模型缺口 | runtime coverage、QEMU patches、firmware evidence | `runtime-model-gap-register.md` | `RUNTIME-01`（已关闭）、`RUNTIME-02`、`RUNTIME-03`、`RUNTIME-04` |
| 真机同路径验证 | Device Test Center 和硬件证据流程 | `project-status.md` 的 hardware 边界 | `HW-01` |
| Tab5 P4 后端 | `platform/runtime/wasm/`、P4 patches、`tests/uiflow2/tab5_*` | `tab5-deferred-backlog.md` | `TAB5-01` |
| 设备视觉保真 | `platform/web/device-shell*`、设备 renderer | `device-visual-fidelity-backlog.md` | `UI-01` |
| CardputerZero | `patches/qemu-linux-arm64-cardputerzero/`、`tests/cardputer_zero/` | `project-status.md` 的 CardputerZero 边界 | `CZ-01` |

## 状态语义

| 状态 | 含义 |
| --- | --- |
| `DELIVERED` | 主路径已实现，当前契约测试和同路径虚拟设备证据通过 |
| `PILOT` | 功能已跑通，但生产服务、完整控制器或真机等价仍有距离 |
| `PARTIAL` | 已有可用子集，同时存在阻断完整验收的数据面或后端 |
| `FAIL` | 同一路径已有可复现失败 evidence；不得被其他 lease 的 PASS 覆盖 |
| `BACKLOG` | 设计或边界已明确，但尚未形成可用实现 |
| `HARDWARE NOT RUN` | 没有完成同固件路径的物理硬件验证 |

除非明确标注 `hardware validation`，所有项目结论都是
`virtual-device validation`。QEMU 功能网络不是 RF、天线、安全模式或功耗
模型；“能联网”和“物理无线行为通过”必须分开记录。

## 工作流流转

1. 新工作先进入 `project-backlog.md`，分配稳定 Task ID、依赖和验收条件。
2. 实现时在 `code-map.md` 登记代码与测试入口，不直接复制运行计数。
3. 验证后把带日期的检查项和 evidence 追加到 `validation-ledger.md`。
4. 只有达到验收条件时才从 Backlog 移除，并在 `project-status.md` 更新当前
   结论和边界。
5. 运行 `project_snapshot.py --write` 更新自动快照；`--check` 必须通过。
6. 外部结论使用完整 commit SHA 的 work-record permalink，并标明
   `virtual-device validation` 或 `hardware validation`。

Worker 工作流把 generation、durable lease、credential rotation 和
generation-pointer migration 视为同一状态机边界；旧 agent 不得覆盖新
generation 的外部 side effect。

## 代码边界

| 代码面 | 职责 | 维护原则 |
| --- | --- | --- |
| 设备/外设/QEMU 注册 | 描述真实硬件与可执行覆盖 | 生成物从源 catalog/profile 生成，不手写第二份事实 |
| QEMU 补丁 | SoC、板级器件、DMA/FIFO/endpoint | 从匹配 worktree 生成并做 reverse check |
| Device Service | lease、runtime、evidence、storage | 先固定 API/evidence 契约，再拆内部模块 |
| 固件工具 | 规范化、能力检查、静态审查、文件系统 | 结构 PASS、安全 REVIEW、运行 PASS 分层 |
| 网络工具 | policy、namespace、pcap、fault injection | 失败 fail-closed，不使用宿主假值绕过 guest |
| UIFlow2 runners | 设备级数据面和 unified 验收 | 每个模型必须有设备本地 case，不跨板继承 |

## 证据阅读顺序

1. 从 `project-snapshot.md` 找到设备、工作流和 Task ID。
2. 从 `project-status.md` 确认当前结论和已知边界。
3. 从 `validation-ledger.md` 找到对应日期的 evidence JSON。
4. 核对 firmware/ELF/QEMU SHA、device、runtime/profile、输入、serial、frame、
   网络或 peer 数据以及 `PASS`/`PARTIAL`/`FAIL` 字段。
5. 只有 schema、单元测试或静态检查时，把它写成实现支撑，不写成设备功能
   PASS。
