# 设备中心接入契约

## 目录 API

```http
GET /api/devices
GET /api/devices/<chip-group>/<device>
GET /api/peripherals
GET /api/peripherals/<device>
GET /api/peripheral-interfaces
GET /api/peripheral-interfaces/<model>
GET /health
```

设备目录字段以 `platform/schema/device.schema.json` 为准。
外设接口直接返回 `platform/tools/peripheral_inventory.py` 生成的清单，包括：

- 设备真实硬件需求及覆盖它的组件；
- 芯片、总线、地址、QOM 路径、注入接口和数据面；
- 模型状态、板级状态、evidence 和具体 blocker；
- `complete`、`blocked_models` 和 `coverage_gaps`。
- `runtime_coverage`，包含 simulated 模型数、已覆盖模型数和矩阵/external
  case 数量。
- `completion_exemption`，仅用于已有的临时后端豁免，并带原因和复查日期；
  新设备不应出现该字段。
- `runtime_cases`，包含在该设备上实际执行的 matrix/external case、
  `case_models` 明细和 `measured_models` 本机实测模型列表；每个组件的
  `runtime_cases` 进一步给出覆盖它的具体 case，可直接作为设备中心调度入口。

设备中心应优先读取该接口，而不是自行解析 QEMU 源码或补丁。

`/api/peripheral-interfaces` 从运行时证据矩阵生成可执行控制描述，包含：

- QMP QOM 输入/输出路径、属性、启动期或运行期阶段；
- 多步 QOM 状态序列及其相对延迟，用于同一运行实例内的动态状态跃迁；
- QMP 触摸、按键和拖拽输入；
- PCM、RMT、摄像头和 SD 镜像的文件方向及格式；
- UART0/UART1 输出断言和 framebuffer 捕获；
- external probe 的测试入口和证据文件。

新增设备或芯片模型时，先让 runtime coverage 指向真实矩阵用例，接口清单会
自动包含它；不要在设备中心复制一份手写 property 映射。

## 设备状态

| 状态 | 设备中心行为 |
| --- | --- |
| `reference-ready` | 可执行显示、输入、截图和自动化测试 |
| `boot-capable` | 可执行固件启动/串口任务；显示任务需检查 `display_protocol` |
| `backend-required` | 只登记设备，不调度固件执行任务 |

当 `runtime.execution = native-qemu` 时，`reference-ready` 表示本机 QEMU
虚拟主机已完成目标尺寸首帧和输入重绘验收，不表示浏览器 WASM 页面可以执行。
设备中心应从 `platform/qemu/profiles.json` 读取机器名、外设模型和阻塞项，
通过统一矩阵或后续进程级执行器启动 QEMU。

ESP32-S3/C6/P4 的矩阵执行先通过 `esp-emu --strap-mode 0x02` 暴露 esptool
socket，再以 `write-flash` 写入虚拟 flash；Core2 通过 QEMU ESP32 ROM
UART 下载模式和 `esptool --no-stub` 写入。执行结果中的
`flash.transport` 和 `flash.verified` 应作为设备中心的调度证据。

## 页面接口

设备页面暴露：

```js
window.m5emu.loadFirmware(buffer, name)
window.m5emu.loadFirmwareUrl(url)
window.m5emu.reset()
window.m5emu.press(controlId, down)
window.m5emu.touch(x, y, down)
window.m5emu.setImu(ax, ay, az, gx, gy, gz)
window.m5emu.setBattery(percent, millivolts, charging, vbus)
window.m5emu.setRtc(epochSeconds)
window.m5emu.execPython(code)
window.m5emu.getFrame()
window.m5emu.getLog()
window.m5emu.getState()
window.m5emu.screenshot()
```

## 父页面消息

设备页加载完成后发送：

```js
window.parent.postMessage({
  type: 'm5emu:ready',
  deviceId: 'stopwatch',
  status: 'reference-ready'
}, location.origin);
```

状态变化发送：

```js
window.parent.postMessage({
  type: 'm5emu:state',
  deviceId: 'stopwatch',
  status: 'reference-ready',
  running: true,
  frames: 120,
  firmware: 'uiflow2.bin'
}, location.origin);
```

## 后续扩展

- WebSocket 串口桥：把原生 `esp-emu` 的 esptool/raw REPL 暴露给设备中心。
- 图像通道：`getFrame()` 的 PNG data URL 可替换成二进制 WebSocket/WebRTC。
- 固件入口：接受 merged flash 或带偏移的 bootloader/partition/app/filesystem
  分段，并记录 SHA-256、chip、flash size、可选 ELF/MAP 和来源。
- 任务调度：按 `runtime.status`、固件目标芯片、板级 profile、控制器覆盖和镜像兼容性
  选择执行器；UIFlow2 只是其中一种固件族。
- 实例调度：每个 lease 独占一个模拟实例；同类设备可创建多个副本，但不能共享
  可变 Flash、串口、输入或网络状态。推荐方案见 `simulator-service-architecture.md`。
- 已知问题：设备 `runtime.validation` 必须参与调度，避免把公开固件的 bootloader panic 判为应用通过。
