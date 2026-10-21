# 多主控模拟设备平台设计

## 目标

建立一个可迁移、可部署、面向 UIFlow2 固件验证的设备模拟平台。每个 M5Stack 主控拥有独立设备档案和物理外壳，共享 Emulator 运行时、固件下载、串口注入、显示回传和设备中心接口。

## 首批设备

- ESP32-S3：StickS3、CoreS3、StopWatch、Cardputer-ADV、PaperMono、PaperColor、StackChan、AtomS3R、StamPLC
- ESP32-C6：NanoC6、Arduino Nesso N1
- ESP32-P4：Tab5
- ESP32 LX6：Core2
- Linux ARM64：CardputerZero

## 能力分层

| 层级 | 含义 |
| --- | --- |
| `reference-ready` | 真实固件可启动，画面帧可回传，输入可注入 |
| `boot-capable` | 当前 WASM 可启动对应芯片固件并查看串口；板级显示/外设适配待接入 |
| `backend-required` | 当前 esp-emulator 不支持该主控架构，需要独立后端 |

## 目录结构

```text
devices/
  catalog.json
  <chip-family>/<device>/
    device.json
    README.md
    firmware.json
    web/                    # 仅设备专属页面，如 StopWatch 参考运行时
platform/
  runtime/wasm/             # Apache-2.0 esp-emu WASM 包
  web/                      # 设备画廊、通用设备页、共享 worker
  tools/                    # HTTP 服务、固件抓取、校验
docs/
  device-center-adapter.md
```

## 数据流

```text
UIFlow2 merged bin
  -> platform/web/emulator-worker.js
  -> Espressif esp-emulator WASM
  -> UART log / framebuffer / GPIO state
  -> device shell canvas + inspector

M5EMU shared protocol firmware
  -> SHARED address marker
  -> width/height/framebuffer address
  -> worker read_memory
  -> device canvas
```

## 设备档案

每个 `device.json` 至少包含：

- 稳定 `id`、名称、SKU、分类、芯片组
- SoC、架构、Flash、PSRAM
- 屏幕类型、分辨率、形状、触摸
- 按键、IMU、RTC、音频等外设
- 外壳样式参数
- 运行时后端与能力层级
- UIFlow2 支持情况、m5ui 支持、公开固件版本与下载地址
- 未实现项和补测条件

## 显示与外壳

通用页面根据 `shell.preset` 渲染：

- `watch-round`
- `stick`
- `core`
- `cardputer`
- `paper`
- `tab`
- `atom`
- `robot`
- `industrial`
- `console-only`

## 自动化接口

设备页面暴露稳定接口：

```js
window.m5emu = {
  loadFirmware,
  reset,
  pause,
  resume,
  press,
  touch,
  setImu,
  setBattery,
  setRtc,
  execPython,
  getFrame,
  getLog,
  getState,
  screenshot
}
```

设备中心后续通过 Playwright、iframe message 或原生 WebSocket 适配以上接口。

## 非目标

- 不把 profile-only 页面称为固件模拟成功。
- 不模拟未确认的引脚、传感器或电源行为。
- 不用仿真结果替代真机屏幕、音频、电源、射频和总线时序验收。
- 不在本轮修改 UIFlow2 主线；`M5EMU_PORT` 固件适配作为后续分支工作。
