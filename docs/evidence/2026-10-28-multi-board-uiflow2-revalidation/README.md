# 2026-10-28：StopWatch / StickS3 / Core2 UIFlow2 接口复测

## 范围

本轮使用 M5Burner 当前 UIFlow2 `v2.5.3`，在独立 Device Service 上复测
StopWatch、StickS3 和 Core2。全部结果属于 **virtual-device validation**；
物理硬件、RF、声学、光学和电气测量均为 `NOT RUN`。

| 设备 | 基础镜像 SHA256 |
| --- | --- |
| StopWatch | `ef5e81b6da17ba04a0356b3bde782e9f0f8f93b217701a4414a52a8d8d8532c0` |
| StickS3 | `c45d4514e21d94a6c069185e08f05851c75b4747d354c1423decdefa625e1dd3` |
| Core2 | `b228c0e2d877e77a8a352e917ed84f4da8ea92d15b25e28f431a2999620fe3c4` |

QEMU runtime SHA256 为
`21b7e34cc96560b4c8185131791008ae49fb1c6975a8428e4e344188a8236394`，
由 28 个当前补丁构建。测试服务与用户现有服务隔离；每个保留 session 都先请求
evidence ZIP，再以 `purge=0` 停止，确认 PID 消失和 Flash 释放。

## 稳定通过项

| 域 | StopWatch | StickS3 | Core2 |
| --- | ---: | ---: | ---: |
| System runtime | 51/51 | 51/51 | 51/51 |
| Shared SDK 候选 | 7/7 | 7/7 | 7/7 |
| Sockets | 23/23 | 23/23 | 23/23 |
| MQTT | 42/42 | 42/42 | 42/42 |
| Network | 14/14 | 14/14 | 14/14 |
| HTTP stock | 15 PASS / 1 FAIL | 15 PASS / 1 FAIL | 15 PASS / 1 FAIL |
| HTTP 候选 | 2/2 | 2/2 | 2/2 |
| EasySocket | 57 PASS + 1 N/A | 57 PASS + 1 N/A | 57 PASS + 1 N/A |
| Modbus TCP stock | 42 PASS / 8 FAIL | 42 PASS / 8 FAIL | 42 PASS / 8 FAIL |
| Modbus 候选 | 50/50 | 50/50 | 50/50 |
| EzData owned fixture | 17/17 | 17/17 | 17/17 |
| ESP-NOW 控制面 | 8 PASS + 5 STATE_PASS + 1 configured | 同左 | 同左 |

`system_runtime` 的每台 51 项为 50 个 PASS 和一个显式板级边界
`STATE_PASS`。`umqtt` 在隔离探针中三台均为 2/2 PASS；此前加入综合探针时
卡住的现象不再复现，因此不记为固件失败。

## 已确认的共享 stock 缺陷及候选修复

| 问题 | stock 结果 | 候选修复与结果 |
| --- | --- | --- |
| `requests2.urlencode` 未转义保留字符和 UTF-8 | 三台均 1 FAIL | `0002-requests2-form-encoding`；三台 2/2 PASS |
| BLE advertising 32-bit UUID 被按 `double` 解包 | 三台均 `buffer too small` | `0021-ble-advertising-uuid32`；三台 4 个 16/32-bit 子项 PASS |
| `ModbusRTUFrame.transform_frame` 先构造非法 `func_code=0` | 三台均 ERROR | `0022-modbus-transform-frame`；request/response/error RTU bytes 和 CRC PASS |
| Modbus 八个 async 方法调用不存在的 `Loop.sock_recv` | 三台均 8 ERROR | `0023-modbus-async-socket`；三台各 50/50 Modbus 项 PASS |
| `M5Canvas.draw_triangle` descriptor 点数组未回写 | StopWatch、Core2 FAIL | `0001-m5ui-native-marshalling`；三台候选状态/画面测试通过 |
| M5Image 单参数浮点 `set_scale` | Core2 stock 报 float→int 转换错误 | 同 `0001`；Core2 候选 `STATE_PASS` 和画面 oracle PASS |
| M5Spinbox 整数 step 被乘十 | Core2 stock step=50 | 同 `0001`；Core2 候选 step=5、增量 25.0 PASS |

候选结果只证明上传的 hash-pinned 源码模块；不表示原厂冻结固件已经被替换。
StopWatch 的 `0001` 最终对照在同一个 hash-pinned firmware/runtime 上重跑，使用三角形
内部彩色中心点作为有效画面 oracle，得到 `4 STATE_PASS + 2 FRAME_PASS`。早先使用
三角形外背景点作为额外 oracle 的断言无效，因此不纳入最终结论。

## M5UI 与显示

- StopWatch 的 28 个 M5UI 类均能构造。文档方法批次共 505 项：409
  `STATE_PASS`、83 项等待画面/删除 oracle、11 项无 recipe、1 项固件明确
  `NotImplementedError`、1 项 Canvas triangle 失败。
- Core2 的 28 个 M5UI 类均能构造；已完成 6 个目标的文档方法批次，共 90 项
  结果，其中 73 `STATE_PASS`、15 等待画面/输入、1 项预期 unsupported、
  1 项 Canvas triangle 失败。其余 22 类构造覆盖通过，但完整文档方法批次
  仍为 `REVIEW`。
- StickS3 的该固件不导出 `m5ui`/`lvgl`，分类为 `NOT_EXPORTED`。
- StopWatch 的 `drawPixel` 在无后续 flush 时没有向 CO5300 发出像素数据。
  trace 显示只发送 CASET/RASET 和 RAMWR 头，原因是单像素窗口宽度为 1，
  与 `Panel_AMOLED` 的偶数窗口限制冲突。该项仍为固件/绑定缺陷。
- StopWatch 与 StickS3 的 PNG/BMP/JPEG/Image 在绝对 `/flash` 路径下通过；
  文档中的相对路径没有绘制。StopWatch `drawRawBuf` 使用像素数而非字节数
  后通过。
- OCR 未配置，文字 glyph 的视觉 oracle 为 `BLOCKED_ORACLE`，不以
  `drawString` 返回成功代替画面 PASS。

## 协议、硬件与模型边界

- TLS stock 三台均在 mTLS handshake 报证书过期；已有
  `0010-mbedtls-epoch` 候选补丁未在本轮重建固件，记为 `REVIEW`。
- `Widgets.QRCode.setText` 三台仍重绘旧 QR；已有
  `0014-widgets-qrcode-text` 候选固件补丁未在本轮重建。
- ESP-NOW 的实例、配置和 peer table 在三台均可用；send/recv/IRQ 因 OpenMAC
  没有 vendor-action peer TX/RX 路由，稳定标记为 `BLOCKED_MODEL`。
- Core2 的 native ESP-NOW API 形状和 peer table 可用，payload/IRQ 同样为
  `BLOCKED_MODEL`。
- 无输入 PCM fixture 时，三台 Mic buffer 均为零。Core2 能从 recording
  回到 0；StopWatch/StickS3 保持 `isRecording=1`，因此只记录控制面边界。
- Core2 `Speaker.playWavFile` 完成；StopWatch/StickS3 在 `playWav` 后调用
  `playWavFile` 不返回，记录为设备模型/固件路径边界。
- StopWatch 与 StickS3 的 BtnA hold callback 在真实 host key input 下完成
  attach、事件送达和 remove 验证。Core2 的 `setCallback/removeCallback`
  参数形式通过，但 key injection 到 hold/pressed callback 不稳定；只保留
  一次通过的原始记录，当前状态为 `REVIEW`，不外推为可靠输入 PASS。
- `EasyTCPServer.getpeername` 在 listening socket 上返回随机 tuple，而非
  明确异常；归类为 listener misuse 边界，不把结果当功能失败。

## 回归检查

- 完整平台套件：`1344` 项完成，`OK`，`1` 项既有 skip。
- `runtime_coverage`、`peripheral_catalog`、`qemu_profiles` 和
  `project_snapshot` 四个生成器检查均 PASS。
- 文档索引/当前状态、共享库候选和 API sweep 设备路由的定向契约共
  `27/27` PASS；`git diff --check` PASS。
- 所有测试 session 均先取 evidence，再以 `purge=0` 停止；最终检查未留下
  `qemu-system-*` 或独立测试服务进程。

## 复现入口

```bash
PYTHONPATH=platform/tools:.work/py python3 -m unittest \
  platform/tests/test_uiflow_shared_library_candidates.py \
  platform/tests/test_api_sweep_device_routing.py

python3 tests/uiflow2/api_sweep/prepare_uiflow_library_candidates.py \
  --candidate modbus-async \
  --source-root .work/uiflow-core2-2.5.3 \
  --out-dir .work/uiflow-library-candidates/modbus-async
```

主要脚本：

- `tests/uiflow2/api_sweep/run_guest.py`
- `tests/uiflow2/api_sweep/run_live_probe.py`
- `tests/uiflow2/api_sweep/run_ui_live.py`
- `tests/uiflow2/api_sweep/run_protocols.py`
- `tests/uiflow2/api_sweep/probe_shared_corrections.py`
- `tests/uiflow2/api_sweep/probe_system_runtime.py`
- `tests/uiflow2/api_sweep/probe_system_remaining.py`

原始 serial、frame、pcap、ZIP 和完整程序保存在 ignored `.work/`，不进入
源码仓库。
