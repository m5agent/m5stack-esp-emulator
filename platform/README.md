# Platform

共享基础设施，不含具体产品档案。当前能力以
[`docs/project-status.md`](../docs/project-status.md) 为准，代码和证据入口见
[`docs/code-map.md`](../docs/code-map.md)。

```text
platform/
├── qemu/                 # QEMU machine/profile 注册表
├── peripherals/          # 外设契约、runtime coverage 和模板
├── runtime/wasm/         # esp-emu WASM 运行时
├── schema/               # device.json schema
├── tests/                # API、catalog、manifest、network、文档契约测试
├── tools/                # Device Service、固件、网络、生成器和证据工具
└── web/                  # 设备目录、会话观察和浏览器设备外壳
```

## 运行时分层

| 后端 | 覆盖 | 定位 |
| --- | --- | --- |
| `qemu-esp32s3` | 9 台 ESP32-S3 设备 | 产品主路径：板级外设、WiFi MAC/DMA、UART HCI BLE |
| `qemu-esp32c6` | NanoC6、Nesso N1 | 产品主路径：C6 板级模型、WiFi MAC/DMA、UART HCI BLE |
| `qemu-esp32lx6` | Core2 | 产品主路径：LX6 板级、OpenMAC WiFi、HCI-offload 与 stock native-VHCI BLE |
| `esp-emu 0.50.0` | Tab5 | P4 专用例外：烧录、启动、framebuffer、touch mailbox、RS-485、静态 I2C |
| Linux ARM64 QEMU | CardputerZero | 独立 Linux 后端，不是 ESP32/UIFlow2 路径 |
| `esp-emu runtime=network` | 诊断/Provisioning | 网络和 SoftAP 排障 lane，不提供整机板级 PASS |

QEMU S3/C6 和 Core2 的单个 `qemu-unified` lease 可以同时提供板级外设、WiFi、
受控 HTTP、BLE peer 和 evidence。它们仍是功能级虚拟设备，不是完整 PHY/RF、
安全模式、功耗或物理时序模型。

## Device Service

`platform/tools/device_service.py` 提供按 lease 创建独立虚拟设备的本地服务；
`platform/tools/serve.py` 暴露 HTTP 和 `/api/v1`：

- 内容寻址 firmware/artifact 和版本化 FirmwareManifest；
- merged/segmented/ZIP 导入与 capability mismatch；
- QEMU 与 Tab5 session 生命周期、TTL、容量和存储回收；
- 串口、framebuffer、输入、QOM、reset、network-fault 和 evidence ZIP；
- `runtime=qemu-unified` 的 S3/C6/Core2 单 guest 板级 + 网络 + BLE；
- Core2 `profile=core2-native-vhci` 的 stock firmware VHCI → Bumble 路径；
- QEMU pcap、flow/DNS/DHCP/ARP 和 payload-hash 摘要；
- Linux private namespace、fail-closed isolation、TLS/Host allowlist fixture
  和 SoftAP `hostfwd` 诊断。

当前边界：

- `core2-native-vhci` 已进入 `/api/v1`，但内部仍使用服务托管的 GDB bridge；
  bit-exact Espressif BT baseband/controller 和物理 cache/PSRAM 等价性未完成。
- Tab5 通过 `esp-emu` 单独接入，外设状态明确为 `partial`。
- CardputerZero 不由 `/api/v1` 管理。
- trusted-host 网络 namespace 不是恶意固件沙箱；worker/VM 生命周期仍未完成。
- TLS/Host allowlist fixture 已在 trusted-host 下 PASS，QEMU patch `0027`
  闭合 AES/GDMA 外部内存读取；Linux namespace TLS 尚未执行，且该能力
  仍不是任意公网目标 allowlist。

完整契约见
[`docs/device-service-api.md`](../docs/device-service-api.md) 和
[`docs/device-service.openapi.yaml`](../docs/device-service.openapi.yaml)。
服务演进路线见
[`docs/simulator-service-architecture.md`](../docs/simulator-service-architecture.md)。

## 主要工具入口

| 路径 | 职责 |
| --- | --- |
| `tools/device_service.py` | session、lease、runtime 编排、证据和状态机 |
| `tools/firmware_manifest.py` | ZIP/目录/WebBurner/M5Burner/flasher_args 导入 |
| `tools/firmware_static_review.py` | 脱敏 URL/凭据/高熵审查和 SPDX/CycloneDX SBOM 摘要 |
| `tools/firmware_analysis.py` | ESP image、分区、应用描述和静态分析 |
| `tools/fetch_firmware.py` | 公开 M5Burner 固件查询、下载和缓存 |
| `tools/user_firmware_matrix.py` | 热门用户固件仿真矩阵 |
| `tools/network_policy.py` | isolation、egress、DNS、Host allowlist 和 pcap 策略 |
| `tools/network_sandbox.py` | Linux private namespace 与 fail-closed runner |
| `tools/network_lane.py` | esp-emu 网络/Provisioning 诊断 lane |
| `tools/pcap_summary.py` | pcap 元数据和 payload hash 摘要 |
| `tools/ble_probe.py` | 外部 BLE controller/peer 与 GATT 验证 |
| `tools/storage_policy.py` | 历史、Flash 和缓存回收策略 |
| `../tests/network/tls_allowlist/` | 测试 CA、HTTPS Host allowlist、200/403、pcap 断言和 AES/GDMA 回归证据 |

## 目录服务 API

`serve.py` 除 `/api/v1` 外还暴露：

```text
GET /api/peripherals
GET /api/peripherals/<device>
GET /api/peripheral-interfaces
GET /api/peripheral-interfaces/<model>
```

内容来自 peripheral contract 和 inventory，可取得硬件需求、组件芯片、总线、
地址、QOM、数据面、evidence、blocker、完成状态和设备的 `runtime_cases`。

## 显示协议

`m5emu-shared-v1`：

1. 固件启动时输出 `M5EMU:SHARED=0x........`；
2. 共享结构头部提供 magic、宽高、framebuffer 地址和 frame sequence；
3. worker 通过 `read_memory` 分块读取 framebuffer；
4. 设备页按 RGB565 解码到 canvas。

没有该协议的固件仍可运行并显示 UART，但设备页会明确显示板级 framebuffer
尚未适配。QEMU unified 路径优先使用 QEMU framebuffer，不依赖该协议。

## 验证

```bash
PYTHONPATH=platform/tools python3 -m unittest discover \
  -s platform/tests -p 'test_*.py'
python3 platform/tools/runtime_coverage.py --check
python3 platform/tools/peripheral_catalog.py --check
python3 platform/tools/qemu_profiles.py --check
```

平台测试中的 `test_docs_consistency.py` 还负责检查关键文档、相对链接、API
版本和设备计数，防止旧状态重新写回当前入口。
