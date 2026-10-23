# 项目 Backlog

日期：`2026-10-23`

本文只记录仍未完成的工作。已完成能力和验证证据统一见
[项目当前状态](project-status.md)。

## 优先级总览

| 优先级 | 工作流 | 完成标准 | 依赖 / 主要风险 |
| --- | --- | --- | --- |
| P0 | 网络隔离、观测与重连 | 独立 namespace、DNS/egress policy、pcap、错误密码、断线重连 | Linux worker；不能把 `user,restrict=yes` 当恶意固件沙箱 |
| P0 | Core2 稳定性与原生无线 | 消除 cache/PSRAM 启动崩溃；原生 BT controller 有外部 peer/GATT；DNS/公网 HTTP | LX6 PHY/controller/定时器路径；硬件或更完整 QEMU 模型 |
| P0 | 通用固件审查 | 标准 firmware manifest、WebBurner 导入、镜像/分区/安全配置检查、结构化 capability mismatch | 多厂商镜像格式；板级 profile 和 eFuse/安全启动差异 |
| P0 | 发布前硬件验证 | 代表设备在同一固件 SHA 和测试计划上通过真机 UART/画面/网络/外设证据 | 物理设备和测试槽；虚拟结果只能标 virtual-device |
| P1 | Tab5 后端补齐 | 重建或扩展 P4 后端，关闭 I2S/PCM、MIPI-CSI、USB Host、SDIO、动态 I2C、ST7123 controller | 闭源 `esp-emu 0.50.0`；建议 2–3 周并行工程 |
| P1 | 服务 worker 与调度 | worker daemon、活动进程跨重启接管、warm pool、多机容量和故障转移 | 生产部署；当前单机进程内 active lease |
| P1 | 热门外壳高保真 | 每台设备独立尺寸、结构、屏幕开孔、按键和 hitbox，并有视觉回归 | 实测尺寸/结构资料；专门视觉/3D 工作 |
| P2 | CardputerZero 系统收口 | 系统启动、驱动、音频、摄像头、网络、USB 回归和真机证据 | 独立 Linux 后端；不属于 ESP32/UIFlow2 |

## P0：网络隔离、观测与重连

已有能力：

- S3/C6 的 11 条设备级 QEMU unified 路径；
- Core2 环境门控 unified path；
- 受控本地 HTTP、DNS、UDP、HCI BLE 和外部 Bumble peer；
- 固件自建 SoftAP 的 loopback `hostfwd` provisioning 诊断。

仍待完成：

1. 为每个不可信固件 session 建立独立 network namespace 或 disposable VM；
2. 默认阻断工作站 LAN、host 文件系统、cloud metadata 和内部服务；
3. 增加只允许/拒绝 DNS、TCP、UDP 和 TLS 测试 CA 的受控 fixture；
4. 记录 pcap 或摘要、DNS 查询、连接目标和 payload hash，不含凭据；
5. 增加错误密码、AP 消失、DHCP 租约变化和自动重连测试；
6. 增加 WPA2/WPA3 的可用范围说明；当前 S3/C6 open AP 不等于安全协议 PASS；
7. 把 multi-device 通信隔离和 host-to-device 访问做成容量测试。

验收：两个 virtual device 仅通过预期 lab fabric 通信；超时、失败和 cleanup
都有可审计证据；不可信固件无法访问宿主 LAN 或控制面。

## P0：Core2 稳定性与原生无线

已有能力：

- 显示、触摸、AXP2101、INA3221、MPU6886、PCF8563、扬声器和麦克风；
- OpenMAC WiFi scan/association/DHCP/受控 HTTP；
- UART1 HCI-offload BLE NUS 的完整外部 GATT；
- `core2-unified` 在同一 guest 合并板级、WiFi 和 HCI BLE。

仍待完成：

1. 定位并修复间歇性 flash/cache/PSRAM 启动崩溃，而不是继续依赖重试；
2. 原生 ESP32 BT controller 的外部 advertising/connection/GATT；
3. Core2 DNS 和受控公网 HTTP；
4. RF、coexistence、连接恢复和生产 payload/throughput；
5. 真机验证同一固件路径。

## P0：通用固件审查

已有能力：

- merged 和 segmented flash；
- UIFlow1/UIFlow2、ESP-IDF、Arduino、MicroPython 及兼容自定义镜像；
- 静态镜像、分区、文件系统和字符串分析；
- 公开 community firmware 下载和热门固件批量仿真。

仍待完成：

1. 正式 `FirmwareManifest` schema，统一 artifact、ELF、MAP、sdkconfig、
   `flasher_args.json` 和 license/provenance；
2. WebBurner/M5Burner 导入器，将下载内容规范化为完整虚拟 Flash；
3. 明确处理安全启动、Flash encryption、eFuse、PSRAM 和 OTA/恢复分区；
4. 依据目标设备 profile 产生 `unsupported_capability`，避免把模型缺口算成
   固件崩溃；
5. 静态审查接入网络、文件系统、嵌入 URL/凭据、异常高熵载荷和第三方
   SBOM；
6. 提供一组真实 ESP-IDF、Arduino、MicroPython 和 vendor 镜像作为兼容回归；
7. 对真机与虚拟设备分别生成同一测试计划的 evidence，不混淆结论。

## P1：Tab5 后端补齐

当前可用：虚拟烧录、UIFlow2 启动、1280×720 framebuffer、触摸、
RS-485、C6 ESP-Hosted 和静态 I2C register probe。

仍待完成：

- 动态 I2C/RTC 状态机；
- P4 I2S/PCM；
- MIPI-CSI/SC2356；
- P4 USB Host；
- SDIO block backend；
- controller-level ST7123 touch；
- IP2326 充放电、终止和运行中状态；
- P4 ↔ C6 ESP-Hosted 的 UIFlow2/ESP-IDF end-to-end association、DHCP 和
  受控请求。

建议先决定“重建可扩展 P4 后端”还是“继续扩展闭源 esp-emu”。没有这个
前提，不承诺 Tab5 剩余外设完成日期。

## P1：服务 worker 与调度

当前 v1 服务是单机模块化单体：

- active session 进程是本地状态；
- service 重启后历史可恢复，但 active emulator 不能接管；
- 无 warm pool、无 remote worker registry、无跨主机调度；
- 容量为 12 个全局 session、8 个同型号 session 的工作站默认值。

后续顺序：

1. 把进程 supervisor、端口、临时目录和 evidence 收集拆成 worker；
2. 控制面与 worker 注册、心跳、re-attach、drain 和故障收敛；
3. 先缓存 runtime image，再增加少量 hot model 的 warm pool；
4. 增加队列、配额、对象存储、pcap/evidence retention 和审计；
5. 对可疑固件使用 disposable VM/copy-on-write flash；
6. 观测启动 latency、CPU/RSS、队列时间、失败率和 cleanup。

## P1：视觉保真

StopWatch 目前是唯一的参考质量外壳，其余设备主要是通用近似模型。该项不是
显示器适配问题，需要独立完成：

- 外形尺寸和结构资料；
- 分层机身、屏幕、按钮、接口和材质；
- 物理 hitbox 与 framebuffer clipping；
- 每台设备的视觉回归截图和误差阈值；
- 不把近似 CSS 外壳描述成物理模型。

见 [设备视觉保真 Backlog](device-visual-fidelity-backlog.md)。

## P2：CardputerZero

CardputerZero 已有独立 ARM64 Linux 后端和多项数据面验证，但它不属于
ESP32/UIFlow2 产品路径，也不由当前 Device Service `/api/v1` 管理。

仍待完成：

- 完整系统启动和服务回归；
- 更严格的 USB/Low-Speed 时序；
- SR9900A 真实网络性能与隔离；
- 摄像头、音频、电源和键盘长期稳定性；
- 真机同路径验证。

## 发布门禁

发布或外部结论前至少完成：

1. 最新平台测试、runtime coverage、peripheral catalog 和 QEMU profiles check；
2. 受影响设备组的 targeted matrix；
3. 共享 QEMU/控制器变更时跑最新 67-case 全矩阵；
4. 使用目标 commit 和同主机架构重新构建运行时；
5. 公共/发布声明按真机或 validated virtual-device path 分层；
6. 更新 README、当前状态、API/OpenAPI、专题文档和工作记录后再发布。
