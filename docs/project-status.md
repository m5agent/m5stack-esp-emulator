# 项目当前状态

日期：`2026-10-24`

本文是项目能力的当前快照。代码、生成目录和自动化测试是权威来源；专题文档
负责解释实现和边界，[项目 Backlog](project-backlog.md) 只记录尚未完成的
工作，[代码与验证入口地图](code-map.md) 说明实现和证据位置。

## 总览

- 本文基线：`2026-10-24` 当前工作树和同 commit 的生成/测试结果；不再用
  历史提交号代表当前能力。
- 已登记 `14` 台设备：9 台 ESP32-S3、2 台 ESP32-C6、Core2、Tab5 和
  CardputerZero。
- Device Service 可创建 `13` 台设备：12 台 QEMU ESP32 加 Tab5。CardputerZero
  是独立 Linux ARM64 后端，当前不由 `/api/v1` 管理。
- `13` 台设备的登记外设已达到 `simulated`；Tab5 仍为 `partial`。
- S3/C6 已形成 `11` 条设备级 QEMU WiFi 验证路径；Core2 在
  `M5_CORE2_RADIO_QEMU` 环境门控下提供第 `12` 条 unified profile。规范
  runtime 为 `qemu-unified`，`qemu-ble` 仅为兼容别名。
- 最新完整 UIFlow2 外设矩阵在 `2026-10-24 00:11 +08:00` 完成：
  `67/67` 用例、`274/274` 检查 PASS，包含全部 6 个 Core2 case；每个
  case 都是 `attempts=1`、`retry_used=false`。Core2 使用
  `tcg,thread=single` + deterministic `icount`，RTC 从 boot epoch 起按
  QEMU 虚拟时钟推进。
- 当前平台测试：`223/223` PASS；runtime coverage、peripheral catalog 和
  QEMU profiles 校验通过。
- 以上全部是虚拟设备证据，物理硬件验证仍为 `NOT RUN`。

## P0 收口

| 工作 | 已闭合 | 仍开放 |
| --- | --- | --- |
| 网络观测与隔离 | 单 guest WiFi/DHCP/HTTP、pcap 摘要、错误密码、link fault/reconnect；trusted-host 与 Linux arm64 private namespace 下的 TLS + Host allowlist 均完成测试 CA、200/403 和 pcap 联合 PASS；QEMU patch `0027` 闭合 AES/GDMA 外部内存读取 | 正式 CI/worker、可控 resolver、通用 egress allowlist、DHCP renewal、双设备 lab fabric |
| Core2 | 确定性 TCG/icount 10/10 首轮、unified WiFi、公网 DNS/HTTP、HCI-offload GATT、stock VHCI BLE 5/5、同 guest native-VHCI 3/3、Device Service `core2-native-vhci` PASS | 非 GDB 生产实现、bit-exact ESP32 BT baseband/controller、物理 cache/PSRAM 等价性、RF/coexistence/soak |
| 通用固件 | FirmwareManifest、WebBurner/M5Burner/ESP-IDF 导入、安全状态 `unknown` 保持、capability mismatch、脱敏 URL/凭据/高熵审查、SPDX/CycloneDX SBOM 摘要 | 文件系统/资源权限审查、许可策略、生产 key/eFuse 流程、跨厂商回归、WebBurner 流式上传 |

## 工程工作流总表

| 工作流 | 当前状态 | 主要代码 | 已验证内容 | 下一道边界 |
| --- | --- | --- | --- | --- |
| 设备与板级契约 | 已完成 | `devices/`、`platform/peripherals/`、`platform/qemu/` | 14 台设备登记；13 台达到登记外设的模拟数据面；catalog、coverage、profile 校验通过 | 新设备逐项登记；视觉保真另列 |
| QEMU/S3/C6 外设 | 当前全矩阵通过 | `patches/`、`tests/uiflow2/` | QEMU patch `0027` 后最新 67/67、274/274，全部首轮无重试；11 条 S3/C6 unified 设备路径；Core2 targeted/native/UI 路径通过 | 新共享控制器变更后重新跑受影响矩阵/全矩阵 |
| Core2 LX6 | 功能路径完成，生产后端开放 | `patches/qemu-core2-*`、`tests/uiflow2/core2_*` | 10/10 确定性首轮启动、WiFi/公网、HCI-offload、stock VHCI 5/5、同 guest 3/3、Device Service lease PASS | 去掉 GDB bridge；bit-exact BT；物理 cache/PSRAM 与 soak |
| Device Service | v1 已实现，生产服务开放 | `platform/tools/device_service.py`、`serve.py`、`storage_policy.py` | lease、上传/烧录、frame/serial/input/QOM/audio/network/evidence、存储回收、API 1.8.0 | worker 化、活动进程恢复、warm pool、多机调度与 VM 隔离 |
| FirmwareManifest | v1 + 静态审查已实现 | `firmware_manifest.py`、`firmware_analysis.py`、`firmware_static_review.py`、`fetch_firmware.py` | merged/segmented/ZIP、WebBurner/M5Burner/flasher_args、安全状态、capability mismatch、脱敏 URL/凭据/高熵 finding 和 SBOM 摘要 | 文件系统/资源权限、许可策略、生产 key/eFuse、跨厂商回归、流式上传 |
| 网络隔离与取证 | Linux 单机路径闭环，正式 worker 开放 | `network_policy.py`、`network_sandbox.py`、`pcap_summary.py`、`tests/network/tls_allowlist/` | namespace 无外网、pcap、错误密码、link down/up、重新 DHCP 与前后 HTTP；trusted-host 和 Linux namespace TLS Host allowlist（200/403）及 QEMU AES/GDMA 外部内存路径 PASS | 可控 resolver、通用 egress allowlist、DHCP renewal、真实 AP 丢失、双设备 fabric、CI/worker |
| 浏览器与目录 | 可用 | `platform/web/`、`generate_catalog.py`、`peripheral_inventory.py` | 设备目录、会话观察、外设/运行时接口 | warm pool 的前端状态与视觉保真 |
| 物理硬件验证 | `NOT RUN` | Device Test Center 路径 | 当前仅有 virtual-device validation | 代表设备使用同固件 SHA 和同测试计划做实机证据 |

这张表是工作流级摘要，设备级细节在下文矩阵；真正未完成事项只在
[项目 Backlog](project-backlog.md) 维护。

## 现在可以做什么

### 虚拟设备与 Device Service

- 通过 `/api/v1` 租用、烧录、启动、停止和恢复 13 台设备的历史会话。
- 使用完整 merged 镜像或 bootloader/partition/app/filesystem 分段镜像。
- 采集串口、framebuffer、输入结果、QOM、设备状态、音频 PCM、网络和
  BLE peer evidence。
- 使用 `runtime=qemu-unified` 在单个 QEMU guest 中同时运行板级外设、
  WiFi 和 HCI-offload BLE。
- QEMU radio session 默认通过 `filter-dump` 保留 pcap，并生成 flow、
  DNS、DHCP、ARP、egress scope 和 payload hash 摘要。
- 可通过 `POST /sessions/{id}/network-fault` 对 `wifi0` 执行 link
  down/up；StickS3 reconnect probe 已完成 guest 断网、恢复 DHCP、前后
  HTTP 和 pcap 的联合验证。
- `qemu-ble` 保留为兼容别名；新调用应使用 `qemu-unified`。
- 对固件自建 SoftAP 的 provisioning 流程，使用 `runtime=network`、
  `firmware_ap_password` 和 loopback-only `hostfwd` 诊断门户。

### 网络与 BLE

- S3/C6 QEMU 驱动经过真实 guest MMIO、DMA、IRQ、QEMU NIC 和 SLiRP。
- 已验证 scan、association、DHCP、DNS、受控 HTTP；StickS3 和 Nesso N1
  还在同一 guest 中完成 `example.com` 的 IPv4 公网 HTTP。
- BLE 使用 UIFlow2 HCI-UART 测试构建，经 QEMU UART 到 Bumble controller，
  由外部 Bumble peer 完成 scan/connect/NUS/GATT write/notify。
- Core2 的 Device Service unified profile 仍使用 OpenMAC WiFi 加
  UART1 HCI-offload BLE。另有一个 standalone stock UIFlow2 路径：不重建
  HCI-UART 固件，在 QEMU 的 native ESP32 VHCI host API 边界把 H2C/C2H
  交给 Bumble controller；外部 peer 已完成 scan/connect/NUS subscribe/write
  和 guest notify 回读。独立 BLE runner 连续 5/5 PASS；扩展后的
  `unified_core2` runner 又在同一 guest 中合并 display/touch、音频、
  QOM、WiFi/DHCP、公网 DNS/HTTP 和 native-VHCI BLE，连续 3/3 PASS。
  该路径现已作为 `runtime=qemu-unified`、
  `profile=core2-native-vhci` 暴露到 Device Service：一个 lease 同时返回
  board/WiFi/公网/frame/QOM/BLE PASS，并从 evidence ZIP 提供 bridge、
  peer、pcap 和 manifest。实现仍依赖 GDB 诊断桥，没有执行 bit-exact
  Espressif BT baseband/controller 固件。
- 错误密码负向测试要求认证失败、重试、无 DHCP、无 HTTP 和失败 marker
  全部成立；StickS3 link-fault/reconnect 路径同时要求恢复后 DHCP 和
  `/after` HTTP。
- Linux arm64 已用同一 QEMU 源码重建 `qemu-system-xtensa`，在 private
  network namespace 内实跑 StickS3 guest：namespace 内 HTTP PASS、公网
  DNS 查询无响应、pcap 中无 global/slirp-redirect 目标。
- `esp-emu` 的 `user` 网络没有 pcap；pcap 只由 QEMU radio runtime 提供。

网络模型不是完整 RF/PHY。WPA2/WPA3、天线、距离、干扰、功耗和稳定性结论
必须来自真机或后续更完整的无线模型。

### 通用固件

- 输入支持 UIFlow1/UIFlow2、ESP-IDF、Arduino、MicroPython 和兼容的
  merged/segmented flash。
- Device Service 会检查镜像格式、芯片、Flash 大小、地址重叠和基础分区。
- 已提供版本化 FirmwareManifest、WebBurner/M5Burner/`flasher_args.json`
  导入、规范化完整 Flash、provenance/security 记录和结构化 capability
  mismatch；真实公开固件样本已 round-trip。
- 已提供公开社区固件抓取、热门固件批量仿真、结构分析、脱敏静态审查和
  SPDX/CycloneDX SBOM 摘要。manifest 不保存 URL query、凭据或编码载荷明文。
- 任意固件仍受板型、PSRAM、eFuse/安全启动、Flash 加密、分区和控制器覆盖
  约束；不支持时必须以结构化能力缺口返回，不能伪装成固件失败或 PASS。

## 设备矩阵

| 设备 | SoC / 后端 | 当前能力 | 网络状态 | 主要剩余缺口 |
| --- | --- | --- | --- | --- |
| StopWatch | ESP32-S3 / QEMU | 466×466 显示、触摸、电源、IMU、音频、振动和外设矩阵通过 | `qemu-unified` PASS | 高保真外观、真机与 RF 未验 |
| StickS3 | ESP32-S3 / QEMU | 显示、按键、电源、IMU、音频、IR 和外设矩阵通过 | `qemu-unified` PASS；同 guest 公网 DNS/HTTP PASS | 真机与 RF 未验 |
| CoreS3 | ESP32-S3 / QEMU | 显示、触摸、电源、IMU、音频、摄像头和 USB Host 数据面通过 | `qemu-unified` PASS | 启动菜单透明/调色板图像仍有模拟条纹 |
| AtomS3R | ESP32-S3 / QEMU | 显示、按键、IMU、磁力计、RGB、IR 通过 | `qemu-unified` PASS | 高保真外观与真机 |
| Cardputer-ADV | ESP32-S3 / QEMU | 显示、键盘、IMU、音频、SD、NFC、CC1101、IR 通过 | `qemu-unified` PASS | 高保真外观与真机 |
| PaperColor | ESP32-S3 / QEMU | Spectra 6、按键、电源、SHT4X、音频、SD、RGB、IR 通过 | `qemu-unified` PASS | 刷新时序与真机光学表现 |
| PaperMono | ESP32-S3 / QEMU | 灰度屏、触摸、电源、IMU、RTC、音频、NFC、LoRa、RGB 通过 | `qemu-unified` PASS | 刷新手感与真机显示表现 |
| StackChan | ESP32-S3 / QEMU | 显示、触摸、摄像头、环境/运动传感器、音频、NFC、IR、双舵机通过 | `qemu-unified` PASS | 机械运动、声学和相机光学 |
| StamPLC | ESP32-S3 / QEMU | 显示、按键、继电器/输入、CAN、RS-485、温度、蜂鸣器通过 | `qemu-unified` PASS | 工业电气特性和真机 |
| NanoC6 | ESP32-C6 / QEMU | 无屏控制台、GPIO、RGB、按键、IR、WiFi、BLE 通过 | `qemu-unified` PASS；独立公网探针 PASS | 原生 BT controller 与 C6 WiFi PHY |
| Nesso N1 | ESP32-C6 / QEMU | 显示、触摸、扩展 IO、电源、IMU、LoRa、IR、蜂鸣器、WiFi、BLE 通过 | `qemu-unified` PASS；同 guest 公网 DNS/HTTP PASS | stock `hardware.RGB()` 未验、原生 BT controller |
| Core2 | ESP32 LX6 / QEMU | 显示、触摸、PMIC、IMU、RTC、扬声器、麦克风、WiFi、公网 DNS/HTTP、HCI-offload BLE、stock native-VHCI BLE GATT | `core2-unified` 与 `core2-native-vhci` Device Service lease PASS；native-VHCI BLE 5/5；同 guest 3/3 | 非 GDB 生产实现、bit-exact BT controller、物理 cache/PSRAM 等价性 |
| Tab5 | ESP32-P4 / esp-emu | 烧录、启动、1280×720、触摸、RS-485、C6 ESP-Hosted、静态 I2C | unified network `NOT RUN` | I2S/PCM、CSI、USB Host、SDIO、动态 I2C、ST7123 controller |
| CardputerZero | BCM2837 / Linux ARM64 | 官方镜像、显示、键盘、I2C、双向 PCM、USB Hub、摄像头、SR9900A 帧回环 | Ethernet 路径，不是 WiFi | 完整系统回归、生产级 USB/时序和真机验证 |

逐项测试依据：

- [QEMU 设备适配矩阵](qemu-device-adaptation-matrix.md)
- [UIFlow2 外设测试矩阵](uiflow2-peripheral-test-matrix.md)
- [代码与验证入口地图](code-map.md)
- Core2 10-run evidence:
  [`tests/uiflow2/unified_core2/evidence-2026-10-23-icount-public.json`](../tests/uiflow2/unified_core2/evidence-2026-10-23-icount-public.json)
- Core2 native-VHCI GATT evidence:
  [`tests/uiflow2/core2_native_vhci/evidence-2026-10-23-vhci.json`](../tests/uiflow2/core2_native_vhci/evidence-2026-10-23-vhci.json)
- Core2 same-guest unified native-VHCI evidence:
  [`tests/uiflow2/unified_core2/evidence-2026-10-23-native-vhci.json`](../tests/uiflow2/unified_core2/evidence-2026-10-23-native-vhci.json)
- Core2 Device Service native-VHCI evidence:
  [`tests/uiflow2/unified_core2/evidence-2026-10-23-native-vhci-service.json`](../tests/uiflow2/unified_core2/evidence-2026-10-23-native-vhci-service.json)
- GDMA external-memory fix + latest full matrix evidence:
  [`tests/uiflow2/evidence-2026-10-24-gdma-external-memory-matrix.json`](../tests/uiflow2/evidence-2026-10-24-gdma-external-memory-matrix.json)
- TLS/Host allowlist pass evidence:
  [`tests/network/tls_allowlist/evidence-2026-10-23-pass.json`](../tests/network/tls_allowlist/evidence-2026-10-23-pass.json)
- Linux namespace TLS/Host allowlist evidence:
  [`tests/network/tls_allowlist/evidence-2026-10-24-linux-namespace-pass.json`](../tests/network/tls_allowlist/evidence-2026-10-24-linux-namespace-pass.json)
- Firmware redacted static review evidence:
  [`tests/firmware/evidence-2026-10-23-static-review.json`](../tests/firmware/evidence-2026-10-23-static-review.json)
- Linux guest-in-namespace evidence:
  [`tests/network/linux_isolation/evidence-2026-10-23-linux.json`](../tests/network/linux_isolation/evidence-2026-10-23-linux.json)
- [网络模拟方案](network-simulation-plan.md)
- [网络诊断 lane](network-lane.md)
- [统一设备运行时契约](unified-device-runtime.md)
- [Device Service API](device-service-api.md)

## 当前风险

1. **仿真边界**：QEMU/esp-emu PASS 不等于 RF、功耗、声学、光学或机械真机
   PASS。
2. **Core2 调度与 BT 等价性**：确定性 TCG/icount 已消除当前虚拟启动 WDT
   复现；native-VHCI 已在同一 guest 与 WiFi/公网/board 合并 3/3，并进入
   Device Service。但 GDB bridge 不是无调试器的生产模型，也不等于
   bit-exact Espressif BT controller 或物理 cache/PSRAM 时序。
3. **Tab5 闭源后端**：`esp-emu 0.50.0` 缺少若干动态设备与控制面，Tab5 仍是
   `partial`。
4. **网络隔离**：Linux namespace runner 和 guest-inside-namespace 整机路径
   已 PASS；trusted-host 和 Linux private namespace 下的 TLS/Host allowlist
   也已完成测试 CA、HTTPS 握手、200/403 和 pcap 联合验证。它仍不等同于
   恶意固件沙箱；通用 destination allowlist、resolver 和 worker/VM 隔离
   仍待实现。
5. **通用固件兼容性**：SoC 相同不代表板级、分区、安全配置和控制器全部
   兼容。
6. **视觉保真**：除 StopWatch 外，设备外壳仍主要是近似模型。

## 文档职责

- `README.md`：入口、当前摘要、快速开始和文档导航。
- 本文：当前能力与设备状态。
- `docs/project-backlog.md`：只列未完成事项、优先级和依赖。
- `docs/code-map.md`：代码入口、验证命令、证据目录和文档维护规则。
- `docs/unified-device-runtime.md`：单 lease/单 guest 的运行时契约。
- `docs/network-*.md`：网络数据面、测试夹具和边界。
- [固件清单与 WebBurner 导入](firmware-manifest.md)：manifest、导入和
  capability mismatch。
- `docs/*-backlog.md`：专项长期缺口。
