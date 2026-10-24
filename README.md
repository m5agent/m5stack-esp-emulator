# M5Stack Firmware Simulation and Review Platform

Last reconciled: `2026-10-24`

[![CI](https://github.com/m5agent/m5stack-esp-emulator/actions/workflows/ci.yml/badge.svg)](https://github.com/m5agent/m5stack-esp-emulator/actions/workflows/ci.yml)

面向 M5Stack 多主控固件启动、烧录、UI 预览、外设联调和自动测试的模拟平台。
当前验证最完整的是 UIFlow2，但架构也支持满足兼容条件的 ESP-IDF、Arduino、
MicroPython 和其他完整 Flash 固件。

![设备目录](docs/images/device-gallery.png)

## 当前状态

- 已登记 14 台设备：9 台 ESP32-S3、2 台 ESP32-C6、Tab5、Core2 和 CardputerZero。
- 12 台 QEMU-backed ESP32 + Tab5 可通过设备服务创建和烧录。
- 13 台设备已完成登记外设的模拟数据面；Tab5 外设状态仍为 `partial`。
- CardputerZero 使用独立 ARM64 Linux 后端，不属于 ESP32/UIFlow2 路径。
- S3/C6 已有 11 条设备级 QEMU WiFi/BLE 验证路径；Core2 在环境门控下增加
  第 12 条设备级路径，并细分为 `core2-unified`、`core2-native-hci` 和
  legacy `core2-native-vhci`。当前共 14 个 unified profile，规范 runtime 为
  `qemu-unified`，`qemu-ble` 仅保留兼容。
- 最新 UIFlow2 外设全矩阵在 `2026-10-24 06:47 +08:00` 完成：
  `67/67` 用例、`274/274` 检查 PASS；所有用例均为 `attempts=1`、
  `retry_used=false`，Core2 6/6 也在 `tcg,thread=single` + `icount`
  下首轮通过。该轮包含双 guest WiFi patch `0028`。本轮在同一工作树执行
  本地平台套件，共 `296` 项，
  `296` 项通过、`0` 项跳过。
- 网络新增一台 namespace 内的 QEMU socket L2 switch 夹具：两台 StickS3
  guest 各自完成 DHCP，A 通过真实 guest TCP 访问 B，双侧 pcap 同时包含
  双向流量；switch 按配置 MAC 绑定连接槽位；宿主控制面、公网 IPv4、
  metadata 和默认路由均不可达。
- WebBurner 的 SHA256 与 upload client Node 测试 `2/2 PASS`，真实浏览器
  已用 `9.44 MiB`、`3` chunk 包完成上传和 manifest 导入。
- 设备服务已在 `127.0.0.1:8787` 提供 lease、烧录、串口、画面、输入、
  QOM、网络和 evidence API。
- 本地 worker 已具备稳定 ID、独占状态目录、generation、heartbeat、
  drain/resume、租约预留、pcap 结果记录和重启后 abandoned-lease 分类；
  远程 worker 已有持久化注册目录、identity/generation 冲突检查、
  heartbeat/drain/stop、bounded result metadata，以及 durable job queue、
  idempotent submit、capability claim、lease heartbeat、expiry retry 和
  worker 失联回收。独立 HTTP `worker_agent.py` 已能 claim job、运行真实
  QEMU session、下载 evidence ZIP/SHA256 并提交结果；本地 QEMU 也可在
  PID start-time、QMP ownership 和 `query-status=running` 校验后恢复
  QMP 控制面。启用 API token 时，worker-only mutation 需要
  worker/generation 派生 HMAC、时间戳和 nonce replay 防护；跨主机
  executor/TLS/mTLS、credential rotation、companion/BLE/evidence
  continuity 和生产多机调度仍未完成。
- restart reattach 已做实跑：仅 SIGKILL Device Service、保留真实 StickS3
  QEMU，第二代服务以同一 PID 重新接管并恢复 worker lease，随后 stop
  清理 QEMU；这是 QEMU/QMP 控制面验证，不是 companion 或 evidence 流恢复。
- Core2 的 QEMU 内部 native-HCI 路径已通过 `HCI-4`：规范的
  `runtime=qemu-unified/profile=core2-native-hci` 在五个独立
  `/api/v1` lease 中同时通过 frame、QOM、WiFi DHCP/HTTP、公网
  DNS/HTTP、外部 NUS GATT、pcap 和 evidence ZIP 检查，不启动 GDB bridge。
  旧的 `core2-native-vhci` 只保留为显式诊断/兼容 profile。
- Core2 的短时延长运行已闭环：`0005` 恢复 nested guest call 前后的
  caller-saved Xtensa sregs，并把 HLI allocator/callback 注入限制在
  halted/idle vCPU。两批独立 `5×10s` hold 运行合计 `10/10`；每轮
  `hli-errors=0`、HLI/meta queue 深度为 0。此前的
  `semphr_give_wrapper`、`PC=0` 和 `Cache error` 证据保留为失败历史。
- GitHub Actions 已运行完整平台测试，并在 Ubuntu runner 上执行 fail-closed
  namespace + nftables exact IPv4 egress、拒绝端口/IP、veth/NAT、清理和
  private bridge/TAP primitive 回归。

完整设备矩阵、证据日期和风险边界见
[项目当前状态](docs/project-status.md)。
按工作流查看“已交付、验证入口、未完成 Task ID”见
[工作流总台账](docs/workstreams.md)。
代码入口、模块职责和验证证据分层见
[代码与验证入口地图](docs/code-map.md)。
每项里程碑的日期、检查项和原始 evidence 见
[验证证据台账](docs/validation-ledger.md)。
第一次阅读建议从 [文档导航与新鲜度规则](docs/README.md) 开始；该页会区分
当前事实、契约、历史调查和待办，避免把旧计划当成当前能力。

### 最近收敛的主线

| 主线 | 已交付 | 验证证据 | 仍开放 |
| --- | --- | --- | --- |
| 网络隔离与受控访问 | Linux namespace/CI、controlled DNS、TLS/SNI Host allowlist、nftables exact IPv4 egress、veth/NAT、DHCP renewal、虚拟 radio/AP 丢失恢复、QEMU pcap、双 guest DHCP/TCP/双侧 pcap 隔离、远程目录、durable job queue、authenticated HTTP executor 和本地 QEMU/QMP restart reattach | [`executor-auth-pass.json`](tests/network/worker_executor/evidence-2026-10-24-executor-auth-pass.json) | 跨主机 executor/TLS/mTLS、credential rotation、companion/evidence continuity、跨主机 reattach、生产多机调度、外部 IPv6 |
| Core2 稳定性与无线 | `HCI-4` 五 lease PASS；两批独立 `5×10s` extended-run `10/10` PASS，且每轮 HLI errors/queue depth 为零 | [`hci4-service-5x.json`](tests/uiflow2/core2_native_hci/evidence-2026-10-24-hci4-service-5x.json)、[`hci4-halted-gate-5x.json`](tests/uiflow2/core2_native_hci/evidence-2026-10-24-hci4-halted-gate-5x.json) | halt-gated HLI 注入和 sregs 恢复修复了短时 repeated-start 崩溃；分钟级/小时级 coexistence、物理 cache/PSRAM、bit-exact controller 与真机仍开放。旧 `core2-native-vhci` 仍是 GDB 诊断/兼容 profile |
| 通用固件审查 | FirmwareManifest、WebBurner/M5Burner/ESP-IDF 导入、浏览器流式 SHA256/chunk 上传、进度/重试/取消/刷新恢复、写入回滚和 staging GC、eFuse summary、capability mismatch、脱敏静态审查、SBOM、LittleFS/FAT12/16/32/SPIFFS 文件清单与 SPDX、声明级许可 allowlist/denylist | [`spiffs-inventory.json`](tests/firmware/evidence-2026-10-24-spiffs-inventory.json)、[`webburner-ui.json`](tests/firmware/evidence-2026-10-24-webburner-ui.json) | 运行时权限、完整源码级许可扫描/法律审批、真机 key/eFuse、跨厂商回归 |
| 共享 QEMU 回归 | 双 guest WiFi patch `0028` 合入后，S3/C6/Core2 全矩阵 `67/67` 首轮通过；键盘测试补齐 10 秒启动 settle | [`dual-guest-fabric-matrix.json`](tests/uiflow2/evidence-2026-10-24-dual-guest-fabric-matrix.json) | 后续共享控制器改动重跑受影响矩阵；真机同路径证据 |

## 剩余工作

| 工作 | 当前状态 | 说明 |
| --- | --- | --- |
| 高保真逐设备外观建模 | `TODO` | 仅 StopWatch 接近参考质量，其余 13 台仍是通用近似外壳 |
| Tab5 外设完整闭环 | `partial` | 烧录、启动、1280×720 画面和触摸可用；摄像头、音频、USB、SDIO、动态 I2C 等未完成 |
| 网络隔离与安全回归 | `mostly complete` | Linux namespace/CI、pcap、错误密码、radio/AP 丢失恢复、controlled DNS、TLS/Host allowlist、exact IPv4 egress、veth/NAT、DHCP renewal、双 guest lab fabric、本地 worker lifecycle、QEMU/QMP restart reattach、远程目录、durable queue/lease supervisor、同主机 HTTP executor 和 HMAC worker auth 已通；跨主机 executor/TLS/mTLS、rotation、companion/evidence continuity、跨主机 reattach、生产多机调度和外部 IPv6 仍待补 |
| 通用固件正式入口 | `mostly complete` | merged/segmented、FirmwareManifest、WebBurner/M5Burner/flasher_args 导入、浏览器 chunk 上传与刷新恢复、脱敏 eFuse summary、capability mismatch、静态审查、SBOM、LittleFS/FAT12/16/32/SPIFFS 文件清单和声明级许可 allowlist/denylist 已通；运行时权限、完整源码级许可审批与真机 key 流程仍待补 |
| 服务池与持久化 | `partial` | 已支持本地 worker heartbeat/drain/resume、PID/start-time/QMP 校验后的 restart reattach、远程目录、durable queue、HMAC-authenticated HTTP executor、claim/lease/expiry retry、worker 失联回收和 evidence ZIP/SHA256 回传；尚无跨主机 executor、TLS/mTLS、rotation、companion/BLE/evidence 连续接管、warm pool 和生产多机调度 |
| Core2 稳定性与原生无线 | `partial` | `HCI-4` 五 lease 与两批 `5×10s` extended-run `10/10` 已通过，HLI health 为零错误；分钟级/小时级 coexistence、bit-exact Espressif BT controller/baseband、物理 cache/PSRAM 和真机同路径仍开放 |
| 真机验证 | `NOT RUN` | 当前设备功能结论均为仿真证据，RF/功耗/声学/光学/机械仍需真机 |

关键索引：

- [文档导航与新鲜度规则](docs/README.md)
- [工作流总台账](docs/workstreams.md)
- [项目当前状态](docs/project-status.md)
- [完整项目 Backlog](docs/project-backlog.md)
- [代码与验证入口地图](docs/code-map.md)
- [验证证据台账](docs/validation-ledger.md)
- [设备高保真建模 Backlog](docs/device-visual-fidelity-backlog.md)
- [热门用户固件仿真矩阵](docs/user-firmware-simulation-matrix.md)
- [Tab5 暂缓项](docs/tab5-deferred-backlog.md)
- [网络模拟方案](docs/network-simulation-plan.md)
- [统一设备运行时契约](docs/unified-device-runtime.md)

## 快速开始

```bash
./start.sh
```

默认地址：

- 设备目录：<http://127.0.0.1:8787/platform/web/>
- 会话观察：<http://127.0.0.1:8787/platform/web/sessions.html>
- WebBurner 固件导入：<http://127.0.0.1:8787/platform/web/firmware.html>
- 设备服务 API：<http://127.0.0.1:8787/api/v1>
- OpenAPI：<http://127.0.0.1:8787/api/v1/openapi.yaml>

这条命令不需要 `.work/`，可以启动设备目录、只读设备清单和 OpenAPI 页面。
`.work/` 是本地构建与运行时缓存，已被 `.gitignore` 排除；全新 clone
**不会**包含它，因此也不能只靠 clone 创建 QEMU 会话。

需要创建、烧录和操作虚拟设备时，请按
[部署与运行时资产](docs/deployment.md) 准备对应资产。

也可以直接启动：

```bash
python3 platform/tools/serve.py 8787
```

`8787` 是本项目默认端口；本机 `8080` 已被其他 Docker 服务占用。

## 设备服务

其他 Agent 可以按 lease 创建独占虚拟设备：

```bash
curl -sS -H 'Content-Type: application/json' \
  -d '{"device_id":"sticks3","ttl_seconds":600}' \
  http://127.0.0.1:8787/api/v1/sessions
```

主要能力：

- reference UIFlow2 固件或上传的 merged/segmented 固件；
- 真实 esptool 虚拟烧录和 prepared-flash cache；
- 每 session 独立虚拟 Flash；
- 串口、QEMU 日志、PNG framebuffer；
- 按键/触摸/拖拽、QOM、reset、renew、stop；
- Linux namespace 下的 nftables 精确 IPv4 IP/协议/端口 allowlist、controlled
  DNS、TLS Host decision 和 per-session veth/NAT；
- application readiness、evidence ZIP、QOM/flash snapshot/diff；
- 停止会话前保存最后一帧，历史会话仍可查看串口和最后画面；
- stopped/failed 历史按时间、条数和字节数自动回收；停止后默认释放整份
  可变虚拟 Flash，仅在需要 Flash 快照/diff 时用 `retain_flash=1` 保留；
- 无引用的 artifact、firmware、prepared-flash 缓存和中断的上传
  staging 按 grace period GC；
- `GET /api/v1/storage` 查看磁盘、历史与缓存占用，写入前保留最低空闲空间；
- 全局和单设备并发限制、TTL 自动回收。

当前工作站默认允许 `12` 个活动会话，同一型号最多 `8` 个。可通过
`M5_SERVICE_MAX_SESSIONS`、`M5_SERVICE_MAX_PER_DEVICE` 或对应 CLI 参数调整；
满载时超出容量仍返回 `429` 和 `Retry-After`。

`running` 只表示虚拟主机控制通道已启动；应用就绪请使用 `ready_marker`、
串口标记或非空截图确认。

人工观察页默认显示活动租约，以及最近 30 分钟内保存了最后一帧或串口的
完成会话；`显示全部历史` 可展开更早记录。API 可用
`GET /api/v1/sessions?include_stopped=0` 只取活动租约，也可从页面或
`DELETE /api/v1/sessions?state=stopped&purge=1` 清理历史。
清除历史后可用 `POST /api/v1/storage/prune?include_cache=1` 同步回收不再
被会话或 firmware 引用的 artifact、firmware 和 prepared-flash 缓存。

完整接口和示例见：

- [Device Service API](docs/device-service-api.md)
- [OpenAPI 3.1](docs/device-service.openapi.yaml)

## 设备支持

| 分组 | 设备 | 状态 |
| --- | --- | --- |
| ESP32-S3 | StopWatch、StickS3、CoreS3、AtomS3R、Cardputer-ADV、StackChan、StamPLC、PaperMono、PaperColor | 功能矩阵通过；StickS3 同 guest 公网 DNS/HTTP 通过；外观除 StopWatch 外为近似模型 |
| ESP32-C6 | NanoC6、Arduino Nesso N1 | 功能矩阵通过；两台 C6 设备的板级外设、QEMU WiFi DHCP/HTTP 和 UART1 HCI BLE 均在同一 QEMU guest 与同一 Device Service lease 内通过；Nesso N1 同 guest 公网 DNS/HTTP 通过 |
| ESP32-P4 | Tab5 | 烧录、启动、显示和触摸可用；外设 `partial` |
| ESP32 LX6 | Core2 | 显示、触摸和外设通过；规范的 `qemu-unified/profile=core2-native-hci` 通过五 lease 与两批 `5×10s` extended-run，全程无 GDB bridge。旧的 `core2-native-vhci` 保留为诊断/兼容路径；更长 soak、bit-exact controller、coexistence 和物理 cache/PSRAM 未完成 |
| Linux ARM64 | CardputerZero | 独立后端，部分外设通过 |

CoreS3 的 UIFlow2 启动菜单顶部图标目前存在条纹伪影，reference 固件同样可复现；
普通文字、矩形、RGB PNG 和自定义不透明绘制正常。该问题跟踪为
[CoreS3 图像渲染边界](docs/cores3-image-rendering-boundary.md)，不影响启动、
烧录和像素级 UI 测试，但尚不能称为完全视觉保真。

详细逐设备状态见
[`devices/README.md`](devices/README.md) 和
[`docs/qemu-device-adaptation-matrix.md`](docs/qemu-device-adaptation-matrix.md)。

## 固件与审查

当前输入支持：

- UIFlow1/UIFlow2
- ESP-IDF
- Arduino ESP32
- MicroPython
- 其他完整 merged Flash 或带地址的分段镜像

兼容前提是芯片、板级 profile、Flash/PSRAM/eFuse、分区布局和控制器模型匹配。
当前底层烧录工具可接受通用镜像；`fetch_firmware.py --firmware-id` 可校验公开
状态与支持设备、按当前 metadata 下载社区固件并运行结构与脱敏静态审查。设备级兼容
仍需按具体 SoC/板级 profile 和控制器覆盖验证。

固件审查流程、证据分层和安全边界见：

- [固件审查与仿真测试工作流](docs/firmware-review-and-simulation-workflow.md)
- [WebBurner 浏览器固件导入](platform/web/firmware.html)
- [虚拟设备功能测试入口与持久化规则](docs/device-functional-test-workflow.md)
- [外设仿真架构](docs/peripheral-simulation-architecture.md)
- [UIFlow2 外设测试矩阵](docs/uiflow2-peripheral-test-matrix.md)

## 本地开发依赖

设备目录、只读设备清单 API 和 OpenAPI 只需要 Python 3。需要 lease、
烧录、串口、截图或输入的 `/api/v1/sessions` 路径时，还必须有匹配当前
commit 与主机架构的 `.work/` 运行时：

- `.work/M5StopWatch-QEMU/`：按补丁构建的 QEMU；
- `.work/esp-emu-versions/0.50.0/`：Tab5 P4 和 network 诊断 lane 使用的
  `esp-emu`；
- Espressif QEMU ROM/eFuse 文件；
- 可选 `UIFLOW_MICROPYTHON_DIR`：UIFlow2 源码 checkout；
- LittleFS 清单：`python3 -m pip install littlefs-python`（缺失时 manifest
  记录 `UNAVAILABLE`）；
- FAT12/16/32 清单使用内置只读 parser，不需要宿主挂载或额外工具；
- SPIFFS 常见 page/block/name/meta 配置使用内置只读 parser，不执行镜像；
- 内置 UIFlow2 缓存：`python3 platform/tools/fetch_firmware.py <device>`；
- 任意公开社区固件：
  `python3 platform/tools/fetch_firmware.py --firmware-id <id> --device-slug <slug> --analyze --chip-id 0x9 --cache /tmp/m5-firmware`。

固件、ROM、QEMU 二进制和构建目录均被 `.gitignore` 排除。
`fetch_firmware.py` 只下载参考固件，不会生成 QEMU 运行时。

## 验证入口

每次改动先运行窄验证：

```bash
PYTHONPATH=platform/tools python3 -m unittest discover \
  -s platform/tests -p 'test_*.py'
python3 platform/tools/runtime_coverage.py --check
python3 platform/tools/peripheral_catalog.py --check
python3 platform/tools/qemu_profiles.py --check
```

相关外设用例：

```bash
PYTHONPATH=.work/py python3 tests/uiflow2/run_peripheral_matrix.py \
  --case <case-id> --out-dir /tmp/m5-<case-id>
```

全量矩阵只在发布、里程碑或跨设备大改时运行：

```bash
PYTHONPATH=.work/py python3 tests/uiflow2/run_peripheral_matrix.py \
  --out-dir /tmp/m5-uiflow2-peripheral-matrix
```

## 文档索引

- [文档导航与新鲜度规则](docs/README.md)
- [项目当前状态](docs/project-status.md)
- [项目 Backlog](docs/project-backlog.md)
- [代码与验证入口地图](docs/code-map.md)
- [验证证据台账](docs/validation-ledger.md)
- [设备服务架构](docs/simulator-service-architecture.md)
- [设备服务 API](docs/device-service-api.md)
- [设备高保真建模 Backlog](docs/device-visual-fidelity-backlog.md)
- [虚拟主机适配矩阵](docs/qemu-device-adaptation-matrix.md)
- [外设仿真架构](docs/peripheral-simulation-architecture.md)
- [固件审查工作流](docs/firmware-review-and-simulation-workflow.md)
- [网络模拟方案](docs/network-simulation-plan.md)
- [网络诊断 lane](docs/network-lane.md)
- [双设备 private lab fabric](tests/network/lab_fabric/README.md)
- [TLS Host allowlist fixture](tests/network/tls_allowlist/README.md)
- [固件清单与 WebBurner 导入](docs/firmware-manifest.md)
- [统一设备运行时契约](docs/unified-device-runtime.md)
- [Tab5 暂缓项](docs/tab5-deferred-backlog.md)
- [维护与验证规则](AGENTS.md)

## 边界

- 仿真 PASS 不等于真机 PASS。
- S3/C6/Core2 的 QEMU 网络是 MAC/DMA 与 user-net 数据面，不是完整
  PHY/RF/天线模型。
- `egress=allowlist` 的精确网络策略当前覆盖 IPv4；外部 IPv6、CIDR 和域名
  不会被当成隐式放行。
- BLE 默认是 HCI-UART offload 到 Bumble；Core2 另有 stock
  internal-controller 路径。规范主路径是 QEMU
  `runtime=qemu-unified/profile=core2-native-hci`：`HCI-4` 使用五个独立
  `/api/v1` lease 通过 frame、QOM、WiFi/公网、外部 NUS GATT、pcap 和
  evidence ZIP，且 `gdb_bridge=false`。`0005` 将 guest-call 注入限制在
  halted/idle vCPU，并恢复 caller-saved sregs；两批 `5×10s` hold 运行
  合计 `10/10`。旧的 `core2-native-vhci` 仍依赖
  GDB 暂停、callback 注入和 synthetic return，只保留为显式诊断/兼容路径，
  不再作为新调用首选。该结果仍不是 bit-exact ESP32 BT
  baseband/controller、分钟级/小时级 soak、RF 或真机验证。当前 hook
  偏移绑定已验证的
  UIFlow2 v2.5.3 build；换 Core2 固件必须重新验证同一路径。
- `runtime=network` 的 SoftAP/hostfwd 是 provisioning 诊断路径，不是恶意
  固件沙箱。
- Tab5 外设不完整，但烧录、启动、串口、1280×720 画面和触摸可用。
- CardputerZero 不是 UIFlow2/ESP32 固件目标。
- 公开仓库不包含第三方固件、ROM、设备标识或云端凭据。

## 参考项目与致谢

本项目的多主控适配和验证流程参考了以下公开项目：

- [zqqf16/M5StopWatch-QEMU](https://github.com/zqqf16/M5StopWatch-QEMU)：
  StopWatch QEMU 适配、板级模型与早期 UI 验证思路的重要参考。
- [espressif/esp-emulator](https://github.com/espressif/esp-emulator)：
  ESP32-C3/C6/P4 RISC-V 运行时、esptool 下载接口、UART/GDB 控制能力。
- [espressif/qemu](https://github.com/espressif/qemu)：
  ESP32/S3/P4 QEMU SoC 与板级模型的源码基础。
- [m5stack/uiflow-micropython](https://github.com/m5stack/uiflow-micropython)：
  UIFlow2 固件构建、板型配置和 MicroPython API 来源。
- [m5stack/M5GFX](https://github.com/m5stack/M5GFX) 与
  [m5stack/M5Unified](https://github.com/m5stack/M5Unified)：
  显示、触摸、板型探测和设备外设路径。
- [espressif/esp-toolchain-docs](https://github.com/espressif/esp-toolchain-docs)：
  QEMU 与 esptool/ESP-IDF 联调方法的公开文档。
- [m5stack/m5stack-linux-dtoverlays](https://github.com/m5stack/m5stack-linux-dtoverlays)：
  CardputerZero 官方 Linux 设备树 overlay 来源。
- [CardputerZero/FactoryTest](https://github.com/CardputerZero/FactoryTest)：
  CardputerZero 官方外设探测、音频、摄像头和电源接口行为参考。
- [torvalds/linux `sound/soc/codecs/es8389.c`](https://github.com/torvalds/linux/blob/master/sound/soc/codecs/es8389.c)
  与 [bouffalolab/bouffalo_sdk `audio_codec_es8389.c`](https://github.com/bouffalolab/bouffalo_sdk/blob/master/bsp/common/audio_codec/audio_codec_es8389.c)：
  ES8389 寄存器布局、身份寄存器与编解码控制路径参考。
- [Linux `r8152.c`](https://github.com/raspberrypi/linux/blob/rpi-6.6.y/drivers/net/usb/r8152.c)
  与 [CoreChips SR9900A 数据手册](https://www.lcsc.com/datasheet/C521278.pdf)：
  SR9900A 的 RTL8152-compatible USB 控制、TX/RX 描述符和以太网数据面参考。
- [Genesys Logic GL852G 数据手册](https://www.lcsc.com/datasheet/C7501404.pdf)：
  `05e3:0610` 默认身份、四口 Hub 与 USB 2.0 行为参考。

各组件的许可与二进制再分发边界见
[`THIRD_PARTY_NOTICES.md`](THIRD_PARTY_NOTICES.md)。

## License

项目原创代码与文档采用 [MIT License](LICENSE)。QEMU 补丁、WASM、产品参考图
和上游代码片段遵循各自许可，见 [`THIRD_PARTY_NOTICES.md`](THIRD_PARTY_NOTICES.md)。
