# Platform

共享基础设施，不含具体产品档案。

```text
platform/
├── runtime/wasm/        # esp-emu 0.49.0 WASM（Apache-2.0）
├── web/                 # 设备目录、通用设备页、设备外壳、共享 worker
├── tools/               # HTTP 服务、设备生成器、固件下载器
├── schema/              # device.json schema
└── tests/               # 静态设备测试与 Playwright 测试
```

## 运行时

- `esp-emulator-wasm`：S3/C6/P4 固件启动和 UART。
- `external-linux-arm64`：CardputerZero 预留，需要独立 Linux/Raspberry Pi 模拟后端。
- `qemu-esp32lx6`：Core2 使用经典 ESP32 QEMU machine、ROM UART 下载和
  `esptool --no-stub` 虚拟烧录。

## 设备中心 API

`platform/tools/serve.py` 除设备目录外还暴露：

```text
GET /api/peripherals
GET /api/peripherals/<device>
GET /api/peripheral-interfaces
GET /api/peripheral-interfaces/<model>
```

接口内容来自 `peripheral_inventory.py`，可直接取得硬件需求、组件芯片、
总线、地址、注入方式、数据面、evidence、blocker、完成状态和该设备需要执行
的 `runtime_cases`。`runtime_interfaces.py` 进一步把 QOM/QMP/PCM/RMT/SD/
UART/framebuffer 操作展开为机器可读接口。

## 显示协议

`m5emu-shared-v1`：

1. 固件启动时输出 `M5EMU:SHARED=0x........`；
2. 共享结构头部提供 magic、宽高、framebuffer 地址和 frame sequence；
3. worker 通过 `read_memory` 分块读取 framebuffer；
4. 设备页按 RGB565 解码到 canvas。

没有该协议的固件仍可运行并显示 UART，但设备页会明确显示“板级 framebuffer 适配待接入”。
