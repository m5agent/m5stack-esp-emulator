# 工作流总台账

日期：`2026-10-24`

本文把“现在在做什么、已经做到哪里、代码和证据在哪里、下一步是什么”放在
一张表中。它不替代两个权威页面：

- 当前能力、验证日期和边界只看 [项目当前状态](project-status.md)。
- 尚未达到验收条件的工作只看 [项目 Backlog](project-backlog.md)。

代码入口和详细验证命令见 [代码与验证入口地图](code-map.md)。
每项里程碑的日期、当时检查项和 evidence 见
[验证证据台账](validation-ledger.md)。

本轮台账对账到 `2026-10-24` 当前工作树、生成物和已提交 evidence。平台套件
共 `292` 项，其中 `292` 项通过、`0` 项环境相关测试跳过。文档整理本身不
产生新的设备能力；浏览器 SHA256/upload client Node 测试另为 `2/2 PASS`。
运行时结论仍以对应固件 SHA、profile 和 evidence 为准。

## 交接摘要

- **当前基线**：`main` 工作树通过平台 `292/292`、catalog/profile 校验，
  最新共享 QEMU 全矩阵仍是 `67/67` case、`274/274` check；这些数字不覆盖
  真机、RF 或未执行的新控制器路径。
- **网络 P0**：单机 namespace、DNS/TLS、exact IPv4 egress、pcap、错误密码、
  radio/AP 恢复、DHCP renewal、双 guest lab fabric、本地 worker
  lifecycle、远程 worker 注册目录及 durable job queue/lease supervisor
  已有实现/证据；同主机 HTTP executor 和验证 PID start-time/QMP ownership
  后的本地 QEMU/QMP restart reattach 也已通过。未完成的是跨主机 executor、
  worker auth 强化、companion/evidence continuity、跨主机 reattach、
  生产多机调度和外部 IPv6。
- **Core2 milestone**：stock native-VHCI 已进入 Device Service，但仍是 GDB 诊断桥；
  QEMU native-HCI 的 `HCI-1` 至 `HCI-4` 已闭环。规范 profile
  `core2-native-hci` 在五个独立 Device Service lease 中同时通过
  frame/QOM/WiFi/公网/NUS GATT/pcap，且不启动 GDB。旧
  `core2-native-vhci` 仅保留为显式诊断/兼容路径。剩余是 bit-exact
  controller/baseband、物理 cache/PSRAM、coexistence/soak 和真机。
- **固件审查 P0**：Manifest、WebBurner、静态审查、安全配置分层和
  LittleFS/FAT/SPIFFS inventory、声明级许可 allowlist/denylist 已实现；
  运行时权限、完整源码级许可扫描/法律审批、真机 key/eFuse 闭环和跨厂商
  样本仍开放。
- **下一手顺序**：推进 `NET-04` 远程 worker 和 `NET-05` IPv6；固件侧
  继续 `FW-01`/`FW-03`/`FW-02`；Core2 转入 `CORE2-02` 的物理与
  controller 等价性，`HCI-4` 不再作为待办。

## 状态语义

| 状态 | 含义 |
| --- | --- |
| `DELIVERED` | 主路径已实现，当前自动化测试或同路径虚拟设备证据通过 |
| `PILOT` | 功能已跑通，但离生产服务、完整控制器或真机等价仍有明确距离 |
| `PARTIAL` | 已有可用子集，同时存在阻断完整验收的数据面或后端 |
| `BACKLOG` | 设计和边界已明确，但尚未形成可用实现 |
| `HARDWARE NOT RUN` | 没有完成同固件路径的物理硬件验证 |

除明确标注 `HARDWARE` 外，本表所有结果都是 `virtual-device validation`。
QEMU 的功能网络不是 RF、天线、WPA2/WPA3 安全模式或功耗模型。

## 交付台账

| 工作流 | 当前状态 | 代码 / 契约 | 验证与证据 | 未完成项 |
| --- | --- | --- | --- | --- |
| 设备与后端登记 | `DELIVERED` | `devices/catalog.source.json`、`platform/peripherals/catalog.json`、`platform/qemu/profiles.json` | catalog、peripheral、runtime coverage、QEMU profile 校验 | 新设备必须走完整 onboarding；视觉保真另算 |
| UIFlow2 板级与外设矩阵 | `DELIVERED`（virtual） | `patches/`、`tests/uiflow2/run_peripheral_matrix.py` | 最新 `67/67` case、`274/274` check，全部首轮无重试 | Tab5 外设、CoreS3 透明/调色板图像、真机同路径 |
| S3/C6 单 guest unified runtime | `PILOT` | `platform/tools/device_service.py`、`tests/uiflow2/unified_*/` | 11 条 S3/C6 profile 在单 QEMU guest 合并 board、WiFi 和 HCI BLE；StickS3 radio/AP 丢失恢复 | 完整 PHY/RF、任意固件覆盖、真机 |
| Core2 稳定性与无线 | `PILOT` | `patches/qemu-core2-*`、`tests/uiflow2/core2_*`、`unified_core2/`、`xtensa_elf_symbols.py` | deterministic TCG/icount 10/10、OpenMAC WiFi、公网 HTTP、HCI-offload、stock VHCI；native-HCI `HCI-1` 至 `HCI-4` PASS，`HCI-3b` 的 HLI/API-boundary GATT 与 `HCI-4` 均 `5/5`；`core2-native-hci` 五个独立 Device Service lease 同时通过 frame/QOM/WiFi/公网/NUS GATT/pcap，且无 GDB bridge；旧 `core2-native-vhci` 的 `1/2` 只作为诊断反例保留 | `CORE2-02` bit-exact controller/baseband、物理 cache/PSRAM、coexistence/soak 和真机同路径 |
| 网络隔离、策略与取证 | `DELIVERED`（单机、双 guest lab fabric、本地 worker lifecycle、HTTP executor、QEMU/QMP restart reattach、远程目录、durable queue/lease supervisor 与 Linux policy CI） | `worker_registry.py`、`worker_directory.py`、`worker_queue.py`、`worker_agent.py`、`network_fabric.py`、`network_sandbox.py`、`network_egress.py`、`network_policy.py`、`pcap_summary.py` | namespace、controlled DNS、TLS/Host allowlist、精确 IPv4 IP/端口、veth/NAT、pcap、radio/AP 丢失重连、DHCP renewal；双 guest lab fabric；本地 heartbeat/drain/restart；PID/start-time/QMP verified local reattach；远程目录；幂等 job、claim/lease/expiry retry；同主机 HTTP executor 运行真实 QEMU job、下载 evidence ZIP/SHA256 并回报；GitHub Actions policy fixture 与 TAP/bridge primitive | `NET-04` 跨主机 executor、worker auth 强化、companion/evidence continuity、跨主机 reattach、多机调度、`NET-05` IPv6 |
| 通用固件导入与静态审查 | `DELIVERED`（静态、上传与浏览器入口范围） | `firmware_manifest.py`、`firmware_analysis.py`、`firmware_filesystems.py`、`firmware_static_review.py`、artifact upload API、`platform/web/firmware.*` | merged/segmented/ZIP、WebBurner/M5Burner/flasher_args、浏览器流式 SHA256/chunk 上传、进度/重试/取消/刷新恢复、capability mismatch、脱敏 review/SBOM、eFuse 安全摘要、LittleFS/FAT/SPIFFS 清单、声明级许可 allowlist/denylist、失败回滚与 staging GC | `FW-01` 运行时权限与完整源码许可扫描、`FW-02` 真机 key/eFuse、`FW-03` 跨厂商回归 |
| Device Service | `PILOT` | `serve.py`、`device_service.py`、`worker_registry.py`、`worker_directory.py`、`worker_queue.py`、`worker_agent.py`、`storage_policy.py`、`docs/device-service-api.md` | 本地 lease/worker lifecycle；PID/start-time/QMP 验证后的 restart reattach；远程注册；durable job queue、claim/lease/expiry/cancel/result；HTTP executor、evidence ZIP/SHA256 和 worker 失联回收；烧录、serial/frame/input/QOM/audio/network/evidence、历史与 GC | `SVC-01` 跨主机 worker auth 与 companion/evidence continuity、`SVC-02` warm pool/多机、`SVC-03` 拆分大型编排热区 |
| 热门公开固件仿真 | `PILOT` | `fetch_firmware.py`、`user_firmware_matrix.py` | 按 M5Burner 热度选样并通过 `/api/v1` 留下 session/evidence | 更大样本面、跨厂商统计、长时间稳定性 |
| 浏览器目录与设备页 | `DELIVERED`（本地） | `platform/web/`、`generate_catalog.py`、`peripheral_inventory.py` | 设备目录、Live sessions、输入和证据浏览 | `UI-01` 逐设备高保真外壳与视觉回归 |
| Tab5 P4/C6 | `PARTIAL` | `esp-emu 0.50.0`、Tab5 patches、`tests/uiflow2/tab5_*` | 烧录、启动、1280×720、触摸、RS-485、静态 I2C | `TAB5-01` I2S/PCM、CSI、USB Host、SDIO、动态 I2C、ST7123、P4↔C6 端到端网络 |
| CardputerZero Linux ARM64 | `PARTIAL` | `patches/qemu-linux-arm64-cardputerzero/`、`tests/cardputer_zero/` | 官方镜像、显示、输入、I2C、音频、摄像头、USB Hub、Ethernet 帧回环 | `CZ-01` 系统级长期回归、USB 时序、网络隔离和真机 |
| 物理硬件验证 | `HARDWARE NOT RUN` | Device Test Center 工作流 | 当前没有可引用的同固件 SHA 真机记录 | `HW-01` 代表设备、同测试计划、明确标记 hardware validation |

## 当前执行顺序

1. 推进网络产品化：双设备真实 QEMU lab fabric、本地 worker
   heartbeat/drain、远程目录、durable queue、同主机 HTTP executor 和本地
   QEMU/QMP reattach 已具备，下一步 `NET-04` / `SVC-01` 跨主机 executor/
   reattach、worker auth 强化、companion/evidence continuity 与多机调度；
   `NET-05` 外部 IPv6 单列。
2. 固件审查继续 `FW-01` 权限/许可，再处理 `FW-03` 跨厂商样本和
   `FW-02` 真机 key/eFuse。
3. `CORE2-02` 与 `HW-01` 推进 controller/baseband、物理
   cache/PSRAM、coexistence/soak 和同固件真机路径。
4. Tab5、视觉保真与 CardputerZero 是专项工作；没有后端、素材和真机证据时
   不把它们写成统一运行时完成。

## 代码边界

| 代码面 | 当前职责 | 维护原则 |
| --- | --- | --- |
| 设备/外设/QEMU 注册 | 描述真实硬件与可执行覆盖 | 生成物从源 catalog 生成，不手改出第二份事实 |
| QEMU 补丁 | SoC 控制器、板级器件、DMA/FIFO/端点 | 必须从匹配 worktree 生成，并做 reverse check |
| Device Service | lease、运行时、证据、存储生命周期 | 对外 API 优先；新增能力先定状态机和证据契约 |
| 固件工具 | 规范化、能力检查、静态审查、文件系统清单 | 结构 PASS、安全 REVIEW、运行 PASS 分开记录 |
| 网络工具 | 策略生成、namespace、pcap 摘要、故障注入 | 失败必须 fail-closed；不使用 Python 假值绕过 guest |
| UIFlow2 runners | 设备级数据面与 unified 验收 | 设备本地 probe 不得从另一块板继承 PASS |

## 证据读取顺序

1. 先读本页确认工作流边界，再读 `project-status.md` 的当前结论。
2. 打开 `validation-ledger.md` 找到对应日期的 evidence JSON，核对设备、
   固件 SHA、runtime/profile、check 和 boundary。
3. 只有 schema/单元测试时，把结论写成实现支撑，不写成设备功能 PASS。
4. 对外结论必须使用完整 commit SHA 的可复现记录，并明确
   `virtual-device validation` 或 `hardware validation`。
