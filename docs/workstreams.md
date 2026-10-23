# 工作流总台账

日期：`2026-10-24`

本文把“现在在做什么、已经做到哪里、代码和证据在哪里、下一步是什么”放在
一张表中。它不替代两个权威页面：

- 当前能力、验证日期和边界只看 [项目当前状态](project-status.md)。
- 尚未达到验收条件的工作只看 [项目 Backlog](project-backlog.md)。

代码入口和详细验证命令见 [代码与验证入口地图](code-map.md)。

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
| S3/C6 单 guest unified runtime | `PILOT` | `platform/tools/device_service.py`、`tests/uiflow2/unified_*/` | 11 条 S3/C6 profile 在单 QEMU guest 合并 board、WiFi 和 HCI BLE | 完整 PHY/RF、任意固件覆盖、正式 AP 丢失测试、真机 |
| Core2 稳定性与无线 | `PILOT` | `patches/qemu-core2-*`、`tests/uiflow2/core2_*`、`unified_core2/` | deterministic TCG/icount 10/10、OpenMAC WiFi、公网 HTTP、HCI 与 stock native-VHCI GATT、Device Service lease | `CORE2-01` 无 GDB 后端；`CORE2-02` controller、物理 cache/PSRAM、coexistence/soak |
| 网络隔离、策略与取证 | `DELIVERED`（单机） | `network_sandbox.py`、`network_egress.py`、`network_policy.py`、`pcap_summary.py` | namespace、controlled DNS、TLS/Host allowlist、精确 IPv4 IP/端口、veth/NAT、pcap、重连、DHCP renewal | `NET-02` 真实 AP 丢失、`NET-03` 双设备 fabric、`NET-04` CI/worker、`NET-05` IPv6 |
| 通用固件导入与静态审查 | `DELIVERED`（静态范围） | `firmware_manifest.py`、`firmware_analysis.py`、`firmware_filesystems.py`、`firmware_static_review.py` | merged/segmented/ZIP、WebBurner/M5Burner/flasher_args、capability mismatch、脱敏 review、SBOM、LittleFS/FAT 清单 | `FW-01` SPIFFS/权限/许可策略、`FW-02` 生产 key/eFuse、`FW-03` 跨厂商回归、`FW-04` 流式上传 |
| Device Service | `PILOT` | `serve.py`、`device_service.py`、`storage_policy.py`、`docs/device-service-api.md` | lease、烧录、serial/frame/input/QOM/audio/network/evidence、历史与 GC | `SVC-01` worker 生命周期、`SVC-02` warm pool/多机、`SVC-03` 拆分 6.7k 行编排热区 |
| 热门公开固件仿真 | `PILOT` | `fetch_firmware.py`、`user_firmware_matrix.py` | 按 M5Burner 热度选样并通过 `/api/v1` 留下 session/evidence | 更大样本面、跨厂商统计、长时间稳定性 |
| 浏览器目录与设备页 | `DELIVERED`（本地） | `platform/web/`、`generate_catalog.py`、`peripheral_inventory.py` | 设备目录、Live sessions、输入和证据浏览 | `UI-01` 逐设备高保真外壳与视觉回归 |
| Tab5 P4/C6 | `PARTIAL` | `esp-emu 0.50.0`、Tab5 patches、`tests/uiflow2/tab5_*` | 烧录、启动、1280×720、触摸、RS-485、静态 I2C | `TAB5-01` I2S/PCM、CSI、USB Host、SDIO、动态 I2C、ST7123、P4↔C6 端到端网络 |
| CardputerZero Linux ARM64 | `PARTIAL` | `patches/qemu-linux-arm64-cardputerzero/`、`tests/cardputer_zero/` | 官方镜像、显示、输入、I2C、音频、摄像头、USB Hub、Ethernet 帧回环 | `CZ-01` 系统级长期回归、USB 时序、网络隔离和真机 |
| 物理硬件验证 | `HARDWARE NOT RUN` | Device Test Center 工作流 | 当前没有可引用的同固件 SHA 真机记录 | `HW-01` 代表设备、同测试计划、明确标记 hardware validation |

## 当前执行顺序

1. 先关 P0 中能形成稳定回归边界的工作：`NET-02`、`CORE2-01`、
   `FW-01`，同时为 `HW-01` 准备同固件路径。
2. 把已跑通路径产品化：`NET-04`、`SVC-01`，随后处理 `SVC-03` 的
   编排模块拆分，避免继续扩大单文件热区。
3. 再扩展覆盖面：`NET-03`、`NET-05`、`FW-02` 至 `FW-04`、
   `SVC-02`、`CORE2-02`。
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

1. 先读本页确认工作流边界，再读 `project-status.md` 的最新证据。
2. 打开对应页内的 evidence JSON，核对设备、固件 SHA、runtime/profile、
   check 和 boundary。
3. 只有 schema/单元测试时，把结论写成实现支撑，不写成设备功能 PASS。
4. 对外结论必须使用完整 commit SHA 的可复现记录，并明确
   `virtual-device validation` 或 `hardware validation`。
