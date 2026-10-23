# 项目 Backlog

日期：`2026-10-23`

本文只记录仍未完成的工作。已完成能力和验证证据统一见
[项目当前状态](project-status.md)，代码和测试入口见
[代码与验证入口地图](code-map.md)。

## 优先级总览

| 优先级 | 工作流 | 完成标准 | 依赖 / 主要风险 |
| --- | --- | --- | --- |
| P0 | 网络隔离、观测与重连 | namespace、DNS/egress policy、pcap、错误密码、断线重连的整机 CI 闭环 | Linux worker；CI/worker 生命周期、DHCP renewal 和真实 AP 消失 |
| P0 | Core2 BT 生产化与物理等价性 | 将已进入 Device Service 的 GDB VHCI bridge 改为 QEMU 内部/无调试器后端；bit-exact controller；物理 cache/PSRAM 时序 | LX6 baseband/controller 模型；真机 |
| P0 | 通用固件审查 | 更深静态审查、安全 key 真机流程和跨设备兼容回归 | 多厂商镜像格式；板级 profile 和 eFuse/安全启动差异 |
| P0 | 发布前硬件验证 | 代表设备在同一固件 SHA 和测试计划上通过真机 UART/画面/网络/外设证据 | 物理设备和测试槽；虚拟结果只能标 virtual-device |
| P1 | Tab5 后端补齐 | 重建或扩展 P4 后端，关闭 I2S/PCM、MIPI-CSI、USB Host、SDIO、动态 I2C、ST7123 controller | 闭源 `esp-emu 0.50.0`；建议 2–3 周并行工程 |
| P1 | 服务 worker 与调度 | worker daemon、活动进程跨重启接管、warm pool、多机容量和故障转移 | 生产部署；当前单机进程内 active lease |
| P1 | 热门外壳高保真 | 每台设备独立尺寸、结构、屏幕开孔、按键和 hitbox，并有视觉回归 | 实测尺寸/结构资料；专门视觉/3D 工作 |
| P2 | CardputerZero 系统收口 | 系统启动、驱动、音频、摄像头、网络、USB 回归和真机证据 | 独立 Linux 后端；不属于 ESP32/UIFlow2 |

## 可执行任务板

| ID | 状态 | 下一项最小交付 | 验收 |
| --- | --- | --- | --- |
| `NET-01` | 待做 | 增加 egress allowlist、可控 resolver 和 TLS 测试 CA | 允许/拒绝目标可重复，guest 无法旁路；pcap 和摘要一致 |
| `NET-02` | 待做 | 增加 DHCP renewal、AP 消失/恢复和 lease 变化 | 同一 guest 观测到 renewal 或 reacquire，前后 HTTP 与 pcap 对齐 |
| `NET-03` | 待做 | 双设备 private lab fabric 与宿主 LAN 隔离 | 两台 guest 仅通过预期 fabric 通信，控制面和宿主 LAN 不可达 |
| `NET-04` | 待做 | 把 Linux namespace/reconnect/pcap 接入正式 CI 与 worker | CI 可重复产出 evidence；namespace 创建失败保持 fail-closed |
| `CORE2-01` | 待做 | 将服务托管的 GDB VHCI bridge 改成 QEMU 内部或无调试器后端 | 同一 stock 固件无 GDB 完成外部 NUS GATT，evidence 不回退 |
| `CORE2-02` | 待做 | 执行 Espressif BT controller/baseband 语义并补物理 cache/PSRAM 时序 | controller 级协议与真机收敛；同路径 soak、coexistence 和 RF 边界可证 |
| `FW-01` | 待做 | 文件系统、URL/凭据、高熵载荷和 SBOM 静态审查 | 风险项结构化输出，安全状态 `unknown` 不被伪装成 PASS |
| `FW-02` | 待做 | eFuse、secure boot、Flash Encryption 和生产 key 流程 | 支持矩阵与拒绝路径明确，敏感 key 不入库 |
| `FW-03` | 待做 | 扩大 ESP-IDF/Arduino/MicroPython/vendor 固件回归集 | 每个样本记录导入、capability、启动/失败层，不混算 |
| `FW-04` | 待做 | WebBurner 网页流式导入和 chunk artifact upload | 大镜像无需先落完整宿主临时文件，校验和与 manifest 保持 |
| `SVC-01` | 待做 | 拆出 worker supervisor、注册/心跳、drain、re-attach | 服务重启可收敛 worker，active lease 有明确接管或失败状态 |
| `SVC-02` | 待做 | warm pool、队列、配额、对象存储和审计 | 启动延迟/CPU/RSS/队列/回收可观测，租户状态不泄漏 |
| `HW-01` | 待做 | 代表设备同固件 SHA 的真机 UART/画面/网络/外设计划 | evidence 标记 hardware validation，虚拟结果不冒充 |
| `TAB5-01` | 决策 | 决定重建/扩展 P4 后端并关闭动态外设数据面 | 关闭 CSI、I2S/PCM、USB Host、SDIO、动态 I2C 和 ST7123 controller |
| `UI-01` | 待做 | 逐设备高保真外壳、hitbox 和视觉回归 | 每台设备有独立尺寸/结构/截图阈值，不只改通用 CSS |

执行顺序以 `NET-04`、`CORE2-01`、`FW-01/02`、`SVC-01` 为当前主线；
`NET-01/02/03` 是网络正式化的可并行前置，`HW-01` 在对应功能稳定后立即
补同路径真机证据。

当前执行顺序：

1. 把 Linux namespace、pcap、错误密码和 reconnect 接入正式 CI/worker；
2. 将 Core2 native-VHCI GDB bridge 生产化为 QEMU 内部或无调试器后端；
3. 扩充 FirmwareManifest 的静态审查、安全 key 流程和跨固件回归；
4. 再推进 Tab5、worker pool、视觉保真和 CardputerZero 的长期项。

## P0：网络隔离、观测与重连

已有能力：

- S3/C6 的 11 条设备级 QEMU unified 路径；
- Core2 环境门控 unified path；
- 受控本地 HTTP、DNS、UDP、HCI BLE 和外部 Bumble peer；
- 固件自建 SoftAP 的 loopback `hostfwd` provisioning 诊断。

本轮已完成：

- Linux `network_sandbox` 创建 private namespace，并确保无外部路由；
- 无法创建 namespace 时 fail-closed，不降级到 host networking；
- 受控 HTTP/BLE peer 可在同一 namespace 内运行；
- QEMU radio session 默认记录 pcap，并生成 flow/DNS/DHCP/ARP/payload
  hash 摘要；
- StickS3 错误密码负向用例 PASS；
- StickS3 guest WLAN 断开 + QMP link down/up + 重新 DHCP + `/after` HTTP
  PASS；
- Linux arm64 重建 QEMU guest 并在 private namespace 内完成 DHCP、受控
  HTTP、DNS deny、pcap 和 `UNIFIED_STICKS3_READY`；
- Core2 OpenMAC 公网 DNS/HTTP PASS。

仍待完成：

1. 增加 allowlist、TLS 测试 CA 和可控 resolver；
2. 增加 DHCP renewal、真实 AP 消失/恢复和 lease 变化；
3. 把 multi-device 通信隔离和 host-to-device 访问做成容量测试；
4. 将 pcap 保留策略、对象存储和审计接入 worker；
5. 把 Linux integration test 接入 CI 和正式 worker 生命周期。

验收：Linux CI 中两个 virtual device 仅通过预期 lab fabric 通信；
guest 路径实际产生 pcap 和 reconnect 证据；不可信固件无法访问宿主 LAN
或控制面。

## P0：Core2 稳定性与原生无线

已有能力：

- 显示、触摸、AXP2101、INA3221、MPU6886、PCF8563、扬声器和麦克风；
- OpenMAC WiFi scan/association/DHCP/受控 HTTP；
- UART1 HCI-offload BLE NUS 的完整外部 GATT；
- `core2-unified` 在同一 guest 合并板级、WiFi 和 HCI BLE。

本轮已完成：

- 失败复现确认两核都在 idle WAITI，属于 interrupt-WDT/timer starvation，
  而非 cache illegal-access callback；
- `tcg,thread=single` + 确定性 icount 后 10/10 次无重试首轮 PASS；
- Core2 DNS、公网 HTTP 和同一 guest HCI-offload BLE 回归通过；
- Device Service `core2-unified` 同步使用确定性调度并通过 pcap evidence。
- stock UIFlow2 internal-controller VHCI 经外部 Bumble controller 完成
  scan/connect/NUS subscribe/write/notify，独立 runner 5/5 PASS。
- `unified_core2 --ble-transport native-vhci` 在同一 guest 合并 board、
  frame/touch、音频、QOM、WiFi/DHCP、公网 DNS/HTTP 和外部 NUS GATT，
  3/3 PASS。
- Device Service `qemu-unified/profile=core2-native-vhci` 完成真实
  `/api/v1` lease，network evidence 全 PASS，evidence ZIP 含 frame、PCM、
  QOM、pcap、bridge 和 peer log。

仍待完成：

1. 把 GDB 诊断桥改为 QEMU 内部或 Device Service worker 管理的无调试器
   VHCI backend；
2. 执行真正的 Espressif BT baseband/controller firmware，而不是在 VHCI
   边界用 Bumble 接管 controller；
3. 物理 cache/PSRAM 时序与确定性 QEMU 调度差异；
4. RF、coexistence、生产 payload/throughput、soak 和真机同路径验证。

## P0：通用固件审查

已有能力：

- merged 和 segmented flash；
- UIFlow1/UIFlow2、ESP-IDF、Arduino、MicroPython 及兼容自定义镜像；
- 静态镜像、分区、文件系统和字符串分析；
- 公开 community firmware 下载和热门固件批量仿真。

本轮已完成：

- 版本化 FirmwareManifest schema 和格式校验；
- WebBurner `manifest.json`、M5Burner sidecar、ESP-IDF `flasher_args.json`、
  merged/segmented/ZIP 导入；
- sparse 镜像补齐、完整 Flash SHA、partition/app 分析和 provenance；
- ELF/MAP/sdkconfig/resource 保留；
- SoC、Flash、PSRAM、secure boot/Flash Encryption 状态和 capability
  mismatch 的结构化拒绝；
- Device Service `kind=manifest` 创建路径；
- 三个真实公开固件样本 round-trip。

仍待完成：

1. 静态审查接入文件系统、嵌入 URL/凭据、异常高熵载荷和第三方 SBOM；
2. 真实 eFuse、生产 secure boot/Flash Encryption key 流程；
3. 更广的 ESP-IDF/Arduino/MicroPython/vendor 兼容回归集；
4. 从 WebBurner 网页直接流式导入和 artifact chunk 上传；
5. 对真机与虚拟设备分别生成同一测试计划的 evidence。

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
