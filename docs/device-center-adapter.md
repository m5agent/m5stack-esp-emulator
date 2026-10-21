# 设备中心接入契约

## 目录 API

```http
GET /api/devices
GET /api/devices/<chip-group>/<device>
GET /health
```

设备目录字段以 `platform/schema/device.schema.json` 为准。

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
- 任务调度：按 `runtime.status`、`uiflow2.supported`、`runtime.chip` 选择执行器。
- 已知问题：设备 `runtime.validation` 必须参与调度，避免把公开固件的 bootloader panic 判为应用通过。
