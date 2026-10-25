# 工程交接总览

最近核对：`2026-10-25`

本页用于让新接手的人快速理解“项目现在是什么、代码在哪里、哪些已经能跑、
接下来做什么”。它是导航摘要，不维护动态数量，也不替代以下权威入口：

- 当前能力、风险和验证边界：[项目当前状态](project-status.md)
- 未完成工作、依赖和验收：[项目 Backlog](project-backlog.md)
- 设备、样本、缺口和 Task 的机器生成计数：[自动项目快照](project-snapshot.md)
- 带日期的运行结果和 evidence：[验证证据台账](validation-ledger.md)
- 代码、测试和证据入口：[代码与验证入口地图](code-map.md)

如果本页与上述页面冲突，以上述权威入口和当前代码/evidence 为准。

## 结论

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
- C6 Zigbee/802.15.4、Core2 legacy I2C 和 Core2 for AWS ATECC608 仍是
  明确的 `runtime_model_gap`；
- 通用固件审查已有结构/静态/运行分层，但运行态 ACL、完整许可、真机
  secure boot/Flash Encryption/key 流程和更多厂商固件仍未闭环；
- 所有物理 RF、功耗、声学、光学、机械和电气结论仍是 `NOT RUN`；
- 当前单机 namespace/container 路径不是恶意多租户固件的最终 VM 沙箱。

## 最近成果已经并入哪里

以下后期工作已经反映在当前状态、Backlog 和专题页，不再属于“尚未开发”：

- controlled DNS 的 exact A/AAAA、domain suffix、最多 8 跳 CNAME chain，
  以及同一 stock guest 的 CNAME→HTTP/denied-name/denied-port 生命周期；
- 有界 IPv4/IPv6 地址/CIDR egress、双栈 veth/NAT、IPv6 neighbor control
  和 cleanup；
- worker control/runtime 双平面、HMAC、HTTPS/mTLS、rotation/drain、
  authenticated discovery、central/runtime restart continuity、
  session-create idempotency 和 trusted-host companion continuity；
- multicast 与 unicast discovery seed；后者在两个 routed/masqueraded
  subnet 中 `3/3 PASS`，错误/旧 token、rotation 和 cleanup 同轮验证；
- worker→control network blackhole 的 bounded heartbeat fence；真实
  namespace 中 runtime session、OS child process、lease expiry/requeue 和
  retry completion 连续 `3/3 PASS`；worker-local Device Service + StickS3
  QEMU lane 也 `3/3 PASS`，首轮 QEMU PID 与 attempt 2 QEMU PID 均回收；
- worker-local `qemu-unified` partition lane 也完成 `3/3 PASS`：断网前
  同 session 已有 HTTP、BLE PASS 和非空 pcap；fence 后 HTTP/BLE companion
  终止、BLE PID 回收、pcap summary 完成，attempt 2 重新取得 unified
  evidence。QEMU 内 guest/controller 内部状态和 worker 未拥有的外部
  side effect 仍开放；
- central 与 worker-local runtime/QEMU 在两个独立 Docker 容器中的真实
  QEMU job、terminal evidence、三工件哈希和 container/bridge cleanup；
- Core2 `core2-native-hci`、同 guest 120/121 轮重连、active-stop、
  bounded TCG、QOM 8 MiB PSRAM、upper-bank MMU remap、虚拟 PSRAM 持续压力
  和长时间 active-BLE 功能保持；两个 lease 在 30 秒启动错峰后完成
  concurrent `2×120s`，每 session 使用独立 QEMU `guestfwd` HTTP。无错峰
  路径修正 extended GATT 超时并在 `0007` 中加入 HLI valid-queue gate；
  首批 `4×120s` 为 `4/4 PASS`，但独立复核仍有一个 guest 在
  `ble_hs_hci_process_ack` LoadProhibited，故该边界继续 `OPEN`；
- FirmwareManifest/WebBurner required/optional capability、安全证据冲突、
  image-signature observation、WebBurner part size/SHA/MD5 复算、SD/NVS
  fixture、包内 eFuse `SECURE_BOOT_DIGEST` 与签名公钥摘要的
  match/mismatch 对照、application/eFuse `secure_version` 对照，以及
  SHA-bound UI/headless/network-first expectation；
- macOS arm64 可复现 runtime bundle，以及 Generic ESP32-S3
  `qemu-wifi/generic-observe`、Open/WPA2 正确密码和错误密码对照。

精确轮次、固件 SHA、检查数量和 evidence 路径只在
[验证证据台账](validation-ledger.md)维护；本页保留能力归类，避免复制会漂移的
运行数字。

## 成熟度怎么看

| 工作流 | 当前可执行面 | 阶段 | 主要边界 |
| --- | --- | --- | --- |
| 设备与统一运行时 | `runtime=qemu-unified` 单 guest 返回板级、WiFi、BLE 和 evidence | `PILOT` | 真机、RF 和未建模控制器 |
| 网络与取证 | controlled DNS/CNAME、有界 CIDR、TLS Host 策略、pcap、重连、双 guest fabric、cross-subnet seed discovery | `PILOT` | 物理跨主机、无 reachable seed 的 NAT、任意公网解析 |
| Worker 与恢复 | durable queue、409/network-partition fence、OS process + real QEMU PID reap、HMAC、HTTPS/mTLS、rotation、multicast/unicast discovery、restart/reattach、跨容器 QEMU | `PILOT` | 物理跨主机、生产调度、QEMU 内 guest/device-controller 和 worker 未拥有的外部 side effect |
| Core2 | native-HCI、公网 WiFi、同 guest 重连、active-stop、bounded TCG、8 MiB PSRAM MMU、虚拟 PSRAM 压力、30 秒错峰 2×120s 并发、无错峰首批 4/4 | `PILOT` | 物理 PSRAM/cache timing、bit-exact controller、无错峰冷启动稳定性、持续吞吐 |
| 通用固件审查 | Manifest/WebBurner、capability/security、Secure Boot v2 image signature 结构/摘要/数学验证、包内 eFuse 摘要与 anti-rollback version 对照、文件系统、SD/NVS、公开矩阵 | `PARTIAL` | 包内 eFuse 来源与公钥 trust root、bootloader anti-rollback 执行、运行态权限/许可、真机 key、更多固件族 |
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
| 固件审查 | `firmware_manifest.py`、`firmware_analysis.py`、`firmware_filesystems.py`、`firmware_static_review.py` | 导入、规范化、capability/security、文件系统和静态审查 |
| 网络 | `network_policy.py`、`network_egress.py`、`network_sandbox.py`、`network_fabric.py` | DNS/CNAME、nftables、namespace、veth/NAT、双 guest fabric |
| Web | `platform/web/` | 设备目录、Live sessions、输入、WebBurner 和报告 |
| 验证 | `platform/tests/`、`tests/uiflow2/`、`tests/network/`、`tests/firmware/` | 契约、设备本地数据面、网络/worker 和固件审查 |

当前生产代码没有未处理的 `TODO/FIXME/HACK`。代码整理的主要债务是边界，而
不是散落的标记：

- `device_service.py` 同时承担存储、runtime、证据和 session 状态机，拆分由
  `SVC-03` 跟踪；
- `test_device_service.py` 和 `test_docs_consistency.py` 体量较大，应在保持
  API/evidence 契约的前提下按领域拆测试；
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
取得 control URL；该路径已在两个 routed/masqueraded subnet 中 `3/3 PASS`。
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

执行顺序和验收只由[项目 Backlog](project-backlog.md)维护。当前 P0 的最小
交付可以概括为：

| Task | 下一步 | 为什么还不能关闭 |
| --- | --- | --- |
| `NET-04` | 物理跨主机 executor/reattach、无 reachable seed 的任意 NAT traversal、跨主机幂等、QEMU guest/controller 内部状态和 worker 未拥有的外部 side effect | 409 与 network partition 已 fence worker-owned OS/QEMU process 和 `qemu-unified` companions；跨容器和同机 subnet/NAT 仍不能替代物理主机 |
| `CORE2-02` | bit-exact controller/baseband、物理 PSRAM/cache timing、无错峰冷启动稳定性、持续吞吐和其他 teardown | 功能级虚拟证据不能证明物理等价；无错峰首批 `4/4` 已清除 HLI errors，但同实现独立复核仍触发 guest panic |
| `FW-01` | 运行态 ACL/权限、完整源码/依赖许可和法律审批 | 镜像属性或声明扫描不是运行态权限 PASS |
| `FW-02` | 真机 secure boot、Flash Encryption、live eFuse、bootloader anti-rollback 和生产 key 流程 | 包内 sdkconfig/eFuse summary 只是自报证据；摘要 match 或 version satisfied 不等于运行时已执行 |
| `FW-03` | 真实 key/cloud 业务与更多设备/固件族 | 当前样本和 network-first 覆盖不等于任意固件 |
| `RUNTIME-02` | C6 Zigbee commissioning/join 或明确不支持 | 观察到 802.15.4 帧不等于完整生命周期 |
| `RUNTIME-03` | Core2 legacy I2C port/pin/bus 路由 | AXP chip id 可读不代表后续 RTC/PMIC 路径 |
| `RUNTIME-04` | ATECC608 测试 slot/config fixture | 安全元件未建模时固件只能得到模型缺口 |
| `SVC-01` | namespace-managed/Tab5/cross-host companion、跨主机 idempotency 和连续 evidence 流 | trusted-host 和单机 restart PASS 不能继承 |
| `SVC-02` | warm pool、配额、对象存储、审计和容量观测 | 当前仍是 cold/on-demand 本地服务 |
| `SVC-03` | 拆分 service 的存储、runtime、evidence 和 session 状态机 | 维护边界仍集中在少数大文件 |
| `HW-01` | 代表设备同固件 SHA 真机验证 | 仓库目前没有 hardware validation 结果 |
| `TAB5-01` | 可扩展/可重建 P4 backend | 闭源后端缺少多个必需端点和数据面 |
| `UI-01` | 逐设备高保真外壳、hitbox 和视觉阈值 | 除 StopWatch 外仍是近似外壳 |
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
