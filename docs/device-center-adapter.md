# 设备中心接入契约

最近核对：`2026-10-25`

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
| `headless-ready` | 无显示设备；固件、串口、板级外设和自动化数据面可用 |
| `boot-capable` | 可执行固件启动/串口任务；显示任务需检查 `display_protocol` |
| `backend-required` | 只登记设备，不调度固件执行任务 |

当 `runtime.execution = native-qemu` 时，`reference-ready` 表示本机 QEMU
虚拟主机已完成目标尺寸首帧和输入重绘验收，不表示浏览器 WASM 页面可以执行。
设备中心应通过 Device Service 的 `GET /api/v1/devices` 读取 profile、
backend readiness、外设模型和阻塞项，通过 `POST /api/v1/sessions` 创建独占
lease。设备中心不直接启动 QEMU、不复制 profile 的启动参数，也不维护第二套
Flash/网络状态。

QEMU S3/C6/Core2 与 Tab5 `esp-emu` 的烧录由 Device Service 处理；Cardputer
Zero 是独立 Linux ARM64 后端，当前不属于 `/api/v1`。设备中心以 session
返回的 `flash.transport`、`flash.verified`、frame、serial 和 evidence 作为
调度证据，不以进程已启动作为固件 PASS。

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

## 已接入契约

- 固件入口：merged/segmented flash、FirmwareManifest、M5Burner/WebBurner/
  ESP-IDF 包、SHA-256、chip、flash size、ELF/MAP 和 provenance；
- 任务调度：按 runtime、目标芯片、板级 profile、控制器覆盖和 capability
  mismatch 选择执行器；
- 实例调度：每个 lease 独占一个模拟实例和可变 Flash，不共享串口、输入或
  网络状态；
- 观测：session history、last frame、serial、QOM、pcap、BLE peer 和
  evidence ZIP。
- worker 生命周期：durable queue、HMAC、HTTPS/mTLS、credential rotation、
  active-token multicast 与 cross-subnet unicast-seed discovery、
  network-partition runtime-process fence、central/runtime restart continuity、
  QEMU/QMP reattach 和 session-create idempotency 已有实现。

## 仍开放

- 二进制 WebSocket/WebRTC 图像与串口实时推送；当前 REST/轮询接口已可用，
  但还不是低延迟媒体协议；
- 无 reachable seed 的任意 NAT traversal、跨主机 QEMU executor/reattach、
  QEMU/device-specific 和 worker 未拥有的外部 side-effect fencing、远程
  worker 的 namespace-managed/Tab5/cross-host companion、连续 evidence 流、
  warm pool 和多机调度；同主机 QEMU/QMP 与 trusted-host unified HTTP/BLE
  companion 重启接管已实现；
- 设备中心正式消费 `runtime.validation` 的门禁字段，避免把公开固件的
  bootloader panic 判为应用通过；
- CardputerZero 的 `/api/v1` 适配，目前仍需独立后端。

完整状态只维护在 [项目当前状态](project-status.md)，剩余执行项只维护在
[项目 Backlog](project-backlog.md)；服务演进方案见
[`simulator-service-architecture.md`](simulator-service-architecture.md)。
