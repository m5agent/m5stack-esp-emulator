# 工作流总台账

日期：`2026-10-25`

本页只维护工作流归属、稳定代码入口、当前权威状态入口和未完成 Task ID。
它不复制测试轮数、PASS 计数、固件 SHA 或逐设备结论：

- 设备、后端、固件样本和 Task 板自动汇总：
  [项目快照](project-snapshot.md)。
- 当前能力、风险和证据边界：[项目当前状态](project-status.md)。
- 未完成 Task、依赖和验收：[项目 Backlog](project-backlog.md)。
- 带日期的证据：[验证证据台账](validation-ledger.md)。
- 代码和测试入口：[代码与验证入口地图](code-map.md)。

## 当前交付与在途

| 工作流 | 已交付的可执行面 | 当前在途 | 下一验收门禁 |
| --- | --- | --- | --- |
| 设备与统一运行时 | QEMU unified 单 guest 板级 + WiFi + BLE + evidence；设备覆盖与 Tab5 边界见当前状态和自动快照 | 长稳和设备级新固件回归 | 代表设备的同路径真机验证与剩余模型缺口 |
| 网络与取证 | namespace、pcap、双 guest fabric、跨 server/worker namespace 的 Bearer+HMAC control plane、active-token multicast worker discovery、central control-plane restart、runtime-service restart 后同 lease/session/evidence continuity、controlled DNS A/AAAA、TLS、exact IPv4/IPv6 egress、双栈 veth/NAT 与清理、同 guest IPv6 TCP/HTTP + controlled AAAA + denied-port + cleanup、worker queue/auth/TLS/reauth、worker 控制面与本地 runtime API 分离、worker namespace 内真实 StickS3 QEMU/artifact/evidence、generic ESP32-S3 `qemu-wifi` observe、S3 WPA2-PSK 正确/错误密码 | `NET-04` 真实跨主机 QEMU executor、NAT/跨子网 discovery、companion/evidence-stream continuity；CIDR/domain-set；WPA3/group multicast | 跨主机 job 可迁移、可重放、可清理；不可信固件进入 disposable VM |
| Core2 | 无 GDB 的 `core2-native-hci`，WiFi/公网/GATT/frame/QOM/pcap 同 lease；同 guest 多轮重连、active-BLE 和 bounded-TCG 门禁已闭合 | 长时并发/吞吐和 teardown；bit-exact controller/baseband 与物理 cache/PSRAM 边界 | controller/物理边界和同固件路径真机验证 |
| 通用固件审查 | manifest、API/WebBurner required/optional capability、security preflight、静态/SBOM、LittleFS/FAT/SPIFFS、WebBurner 流式上传、公开 BIN 强制刷新、session-isolated SD/NVS fixture、SHA-bound UI/headless/network-first expectation；OpenAI NVS、Open/WPA2 正确密码与错误密码、network-first DHCP/DNS/TCP/pcap 对照 | 真实 key/cloud 结果；`FW-01/02/03`；`RUNTIME-02/03/04` | 每轮绑定实际 BIN/expectation/fixture SHA、分层区分 firmware/model/fixture 结果、更多固件族、运行态权限/许可闭环和同 SHA 真机安全流程 |
| Device Service 生命周期 | durable queue、worker HMAC、HTTPS/mTLS、rotation/drain、同主机 reattach | `SVC-01/02/03` 与 `NET-04` | 跨主机/companion 接管、warm pool、容量和大型编排模块拆分 |

“当前在途”只表示工作已经启动，不是 PASS。具体轮数、PASS 计数、资源采样
和固件哈希以 [项目快照](project-snapshot.md) 与
[项目当前状态](project-status.md) 为准，本页只维护工作流归属和下一门禁。

## 未完成项执行顺序

1. `FW-03`：当前四样本已通过 Device Service 和 FAT32+MBR SD fixture；
   OpenAI first-boot NVS 前置条件与 headless/network-first expectation 已关闭，
   下一步补真实 key/cloud 结果，再扩固件族。
2. `NET-04` / `SVC-01`：control/runtime 双端点、worker-local QEMU、两个
   network namespace、authenticated multicast discovery、central
   control-plane restart 和 runtime-service restart continuity 已 PASS；
   下一步补物理跨主机 executor、NAT/跨子网 discovery、跨主机 reattach、
   companion/evidence-stream continuity 和不可信固件隔离。
3. `CORE2-02`：补长时吞吐/teardown、bit-exact controller/baseband 和
   物理 cache/PSRAM 边界；已完成的重连与 TCG 门禁不重复列为待办。
4. `RUNTIME-03`：先补 Core2 legacy I2C 的 port/pin/bus trace，再验证
   BM8563 RTC 路径；`RUNTIME-04` 独立补 ATECC608 fixture；
   `RUNTIME-02` 补 C6 802.15.4 commissioning 或保持显式不支持。
5. `FW-01/02`：补运行态 ACL/许可和真实安全配置流程。
6. `HW-01`：用代表设备完成同固件 SHA 的 physical hardware validation。
7. 后续再排 `TAB5-01`、`SVC-02/03`、`UI-01` 和 `CZ-01`。

## 工作流

| 工作流 | 稳定代码面 | 权威状态 | 未完成 Task |
| --- | --- | --- | --- |
| 设备、板级与统一运行时 | `devices/`、`platform/qemu/`、`patches/`、`tests/uiflow2/` | `project-status.md` 的设备矩阵和统一运行时章节 | 无独立 Task；新增设备必须走 onboarding |
| Device Service 与生命周期 | `serve.py`、`device_service.py`、`storage_policy.py` | `device-service-api.md`、`project-status.md` | `SVC-01`、`SVC-02`、`SVC-03` |
| 网络隔离、双 guest lab fabric 与 worker | `network_*.py`、`worker_*.py`、`transport_security.py`、`tests/network/` | `network-simulation-plan.md`、`device-service-api.md` | `NET-04` |
| Core2 无线与长稳 | `core2_native_hci/`、`unified_core2/`、`ble_probe.py`、`ble_runtime_limits.py` | `core2-native-hci-backend.md`、`project-status.md` | `CORE2-02` |
| 固件导入、静态审查与安全 | `firmware_*.py`、`fetch_firmware.py`、`user_firmware_matrix.py`、`platform/web/firmware.*` | `firmware-manifest.md`、`user-firmware-simulation-matrix.md` | `FW-01`、`FW-02`、`FW-03` |
| 运行时模型缺口 | runtime coverage、QEMU patches、firmware evidence | `runtime-model-gap-register.md` | `RUNTIME-02`、`RUNTIME-03`、`RUNTIME-04`；`RUNTIME-01`、`RUNTIME-05` 已关闭 |
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

`NET-05` 已从 Backlog 关闭：exact IPv4/IPv6 endpoint、双栈
veth/route/NAT、IPv6 neighbor control 和清理已在 Linux virtual-network
夹具连续通过，并由同一 source commit 的 GitHub Actions policy job 复验。
`NET-06` 也已关闭：同一 Linux namespace UIFlow2 guest 完成 controlled
AAAA、allowed IPv6 HTTP、denied-port、pcap、cleanup 和 QEMU reap。
CIDR、domain-set 和恶意固件沙箱仍是不同能力。

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
