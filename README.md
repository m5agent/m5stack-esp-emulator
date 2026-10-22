# M5Stack Firmware Simulation and Review Platform

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
- 设备服务已在 `127.0.0.1:8787` 提供会话租用、固件烧录、串口、画面和输入 API。

## 剩余工作

| 工作 | 当前状态 | 说明 |
| --- | --- | --- |
| 高保真逐设备外观建模 | `TODO` | 仅 StopWatch 接近参考质量，其余 13 台仍是通用近似外壳 |
| Tab5 外设完整闭环 | `partial` | 烧录、启动、1280×720 画面和触摸可用；摄像头、音频、USB、SDIO、动态 I2C 等未完成 |
| 网络模拟统一接入 | `TODO` | `esp-emu` 已有 WiFi/Ethernet 后端，尚未接入所有设备和自动测试 |
| 通用固件正式入口 | `TODO` | 支持 merged/segmented 架构，仍需 M5Burner/WebBurner 导入、静态检查和标准化 manifest |
| 服务池与持久化 | `TODO` | 当前为按需冷启动 + 固件缓存；尚无 warm pool、跨重启会话和多机调度 |
| 最新全量矩阵与真机验证 | `NOT RUN` | 当前结论均为仿真证据 |

高难度外观建模已单独记录，供后续更强的视觉/3D Agent 接手：

- [设备高保真建模 Backlog](docs/device-visual-fidelity-backlog.md)
- [完整项目 Backlog](docs/project-backlog.md)
- [Tab5 暂缓项](docs/tab5-deferred-backlog.md)
- [网络模拟方案](docs/network-simulation-plan.md)

## 快速开始

```bash
./start.sh
```

默认地址：

- 设备目录：<http://127.0.0.1:8787/platform/web/>
- 会话观察：<http://127.0.0.1:8787/platform/web/sessions.html>
- 设备服务 API：<http://127.0.0.1:8787/api/v1>
- OpenAPI：<http://127.0.0.1:8787/api/v1/openapi.yaml>

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
- application readiness、evidence ZIP、QOM/flash snapshot/diff；
- 停止会话前保存最后一帧，历史会话仍可查看串口和最后画面；
- 全局和单设备并发限制、TTL 自动回收。

当前工作站默认允许 `8` 个活动会话，同一型号最多 `6` 个。可通过
`M5_SERVICE_MAX_SESSIONS`、`M5_SERVICE_MAX_PER_DEVICE` 或对应 CLI 参数调整；
满载时超出容量仍返回 `429` 和 `Retry-After`。

`running` 只表示虚拟主机控制通道已启动；应用就绪请使用 `ready_marker`、
串口标记或非空截图确认。

人工观察页默认显示活动租约，以及最近 30 分钟内保存了最后一帧或串口的
完成会话；`显示全部历史` 可展开更早记录。API 可用
`GET /api/v1/sessions?include_stopped=0` 只取活动租约，也可从页面或
`DELETE /api/v1/sessions?state=stopped&purge=1` 清理历史。

完整接口和示例见：

- [Device Service API](docs/device-service-api.md)
- [OpenAPI 3.1](docs/device-service.openapi.yaml)

## 设备支持

| 分组 | 设备 | 状态 |
| --- | --- | --- |
| ESP32-S3 | StopWatch、StickS3、CoreS3、AtomS3R、Cardputer-ADV、StackChan、StamPLC、PaperMono、PaperColor | 功能矩阵通过；外观除 StopWatch 外为近似模型 |
| ESP32-C6 | NanoC6、Arduino Nesso N1 | 功能矩阵通过 |
| ESP32-P4 | Tab5 | 烧录、启动、显示和触摸可用；外设 `partial` |
| ESP32 LX6 | Core2 | 显示、触摸和外设通过；仍有间歇性 cache panic |
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
当前底层烧录工具可接受通用镜像，但正式的非 UIFlow 固件导入和静态审查仍在
backlog 中。

固件审查流程、证据分层和安全边界见：

- [固件审查与仿真测试工作流](docs/firmware-review-and-simulation-workflow.md)
- [外设仿真架构](docs/peripheral-simulation-architecture.md)
- [UIFlow2 外设测试矩阵](docs/uiflow2-peripheral-test-matrix.md)

## 本地开发依赖

浏览器设备目录和 API 只需要 Python 3。完整 QEMU/esp-emu 回归还需要：

- `.work/M5StopWatch-QEMU/`：按补丁构建的 QEMU；
- `.work/esp-emu-versions/0.50.0/`：P4/C6 使用的 `esp-emu`；
- Espressif QEMU ROM/eFuse 文件；
- 可选 `UIFLOW_MICROPYTHON_DIR`：UIFlow2 源码 checkout；
- 固件缓存：`python3 platform/tools/fetch_firmware.py <device>`。

固件、ROM、QEMU 二进制和构建目录均被 `.gitignore` 排除。

## 验证入口

每次改动先运行窄验证：

```bash
PYTHONPATH=platform/tools python3 -m unittest discover \
  -s platform/tests -p 'test_*.py'
python3 platform/tools/runtime_coverage.py --check
python3 platform/tools/peripheral_catalog.py --check
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

- [项目 Backlog](docs/project-backlog.md)
- [设备服务架构](docs/simulator-service-architecture.md)
- [设备服务 API](docs/device-service-api.md)
- [设备高保真建模 Backlog](docs/device-visual-fidelity-backlog.md)
- [虚拟主机适配矩阵](docs/qemu-device-adaptation-matrix.md)
- [外设仿真架构](docs/peripheral-simulation-architecture.md)
- [固件审查工作流](docs/firmware-review-and-simulation-workflow.md)
- [网络模拟方案](docs/network-simulation-plan.md)
- [Tab5 暂缓项](docs/tab5-deferred-backlog.md)
- [维护与验证规则](AGENTS.md)

## 边界

- 仿真 PASS 不等于真机 PASS。
- 当前网络模拟尚未接入统一设备服务。
- Tab5 外设不完整，但烧录、启动、串口、1280×720 画面和触摸可用。
- CardputerZero 不是 UIFlow2/ESP32 固件目标。
- 公开仓库不包含第三方固件、ROM、设备标识或云端凭据。

## License

项目原创代码与文档采用 [MIT License](LICENSE)。QEMU 补丁、WASM、产品参考图
和上游代码片段遵循各自许可，见 [`THIRD_PARTY_NOTICES.md`](THIRD_PARTY_NOTICES.md)。
