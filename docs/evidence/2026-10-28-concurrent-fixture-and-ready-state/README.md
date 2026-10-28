# 2026-10-28：三设备 UIFlow2 并发复测与 runner 竞态修复

## 范围

本轮在 StopWatch、StickS3、Core2 的官方 UIFlow2 `v2.5.3` 上复测系统运行时、
共享候选、网络协议、显示、输入、音频和 M5UI 接口。设备之间并发，设备内部
按 runner 串行执行，统一使用 Device Service `/api/v1`。

全部结果为 **virtual-device validation**；物理硬件、RF、声学、光学和电气为
`NOT RUN`。

QEMU SHA256：

`6ff2aca091909ea078e5b9805b420cb04c11e3f9928b52c2fac199e33e45b2ef`

| 设备 | Base firmware SHA256 |
| --- | --- |
| StopWatch | `99d6482befe094de47bf68ce43618d3868bd62fb1fc72f0b55c0d0c2ea4e7f8d` |
| StickS3 | `c08196024019273ccadee9b4b3da303567f7ab206fa14edd1af283f04f6e98d8` |
| Core2 | `b228c0e2d877e77a8a352e917ed84f4da8ea92d15b25e28f431a2999620fe3c4` |

## 稳定结果

| 域 | StopWatch | StickS3 | Core2 |
| --- | ---: | ---: | ---: |
| System runtime | `50 PASS + 1 STATE_PASS` | 同左 | 同左 |
| Shared corrections | `7/7` | `7/7` | `7/7` |
| Sockets | `23/23` | `23/23` | `23/23` |
| MQTT | `42/42` | `42/42` | `42/42` |
| Network | `14/14` | `14/14` | `14/14` |
| EzData | `17/17` | `17/17` | `17/17` |
| Audio player | `15/15` | `15/15` | `NOT_EXPORTED` |
| Audio recorder | `12/12` | `12/12` | `NOT_EXPORTED` |

Standalone `Display.drawPixel`：

- StopWatch stock preimage 仍 `FAIL`，独立奇偶像素未刷新；
- StickS3、Core2 stock frame 均为 `FRAME_PASS`；
- 这与已有 `0024-display-draw-pixel-transaction` 候选修复一致，未把候选结果
  覆盖到 stock lane。

BtnA `WAS_HOLD` 在 StopWatch、StickS3 均收到一次真实回调，remove 后无新事件。
Core2 PWR `WAS_HOLD` 与 FT5x06 触控点也在同一真实输入路径通过。

## 并发问题与修复

### 固定 HTTP fixture 端口

多个 `qemu-wifi` prompt runner 同时创建 StickS3 会话时，服务镜像的固定
`10.0.2.2` HTTP fixture 会竞争 profile 分配的 host port，出现
`Address already in use`。协议 probe 本身已有独立 owned peer，不需要该固定
listener。

新增 `network.http_fixture`（默认 `true`）后，测试 runner 显式传 `false`，
只关闭固定 controlled endpoint，保留 WiFi NIC、serial、frame、QOM、pcap 和
真实本地 peer。两个 StickS3 会话并发重跑：

- Sockets `23/23 PASS`；
- Network `14/14 PASS`。

两个 `qemu-unified` StickS3 ESP-NOW loopback 会话也同时完成，每台均为
`12 PASS + 5 STATE_PASS + 1 CONFIGURED_UNVERIFIED`；这只证明同一 guest 的
controller TX/RX loopback，不证明外部或加密 peer。

### READY 与会话状态竞态

串口 boot marker 可能早于服务把 session 发布为 `running`。硬件 runner 在
marker 后立即发 `keydown` 时，StickS3 首次请求曾收到 `409`。runner 现在在
执行 marker action 前轮询同一 session，直到状态为 `running`；失败或停止状态
立即报错。修复后同一 BtnA/WAS_HOLD 路径完成 attach、输入、callback 和 remove。

### Core2 启动预算

并发启动时，Core2 系统菜单/测试代码可能晚于旧 10 秒窗口。bounded drive 的
等待由 10 秒提高到 30 秒，Core2 特定 case 使用 18 秒首等待。顺序复测结果：

| Case | 结果 | Frame |
| --- | --- | --- |
| `core2-peripherals` | `PASS` | `6612` nonblack pixels，成功标记绿 |
| `core2-imu` | `PASS` | `3766` nonblack pixels |
| `core2-axp192` | `PASS` | `3917` nonblack pixels |

此前并发批处理中的黑帧/缺 marker 保留为失败 control；它们与 10 秒 drive
上限和启动竞争一致，不是 UIFlow2 API 回归。

## Stock 固件边界

冻结固件仍复现已有源码缺陷：

- HTTP：`15 PASS / 1 FAIL`，失败为 `requests2.urlencode`；
- Modbus TCP：`42 PASS / 8 ERROR`，八个 async 方法调用不存在的
  `Loop.sock_recv`；
- StopWatch/Core2 M5UI correction probe：
  `M5Canvas.draw_triangle`、`M5Image.set_scale`、`M5Spinbox.set_step` 失败，
  decimal step 子项 `STATE_PASS`；StickS3 不导出 `m5ui`。

这些失败由已有 hash-pinned 候选源码/固件修复覆盖，不能写成 stock firmware
已修复。

## 平台与 API 验证

- Device Service API sweep：`81` operations、`95` cases、
  `13` positive + `70` boundary，全部 PASS；
- platform tests：`1364` 项完成，`OK`，`1` skipped；
- `runtime_coverage`、`peripheral_catalog`、`qemu_profiles` 和
  `project_snapshot` 检查全部 PASS。

## 复现入口

```bash
PYTHONPATH=platform/tools:tests/uiflow2 \
  .work/issue-review-venv/bin/python3.12 \
  tests/uiflow2/api_sweep/run_protocols.py \
  --execute --api http://127.0.0.1:<isolated-port>/api/v1 \
  --token-file <private-token-file> --device sticks3 --group sockets \
  --out-dir <new-output-dir>

PYTHONPATH=platform/tools:tests/uiflow2 \
  .work/issue-review-venv/bin/python3.12 \
  tests/uiflow2/api_sweep/run_hardware_guest.py \
  --api http://127.0.0.1:<isolated-port> \
  --token-file <private-token-file> --device sticks3 \
  --source tests/uiflow2/api_sweep/probe_button_callback.py \
  --append-code "run_button_callback('BtnA')" \
  --drive-json tests/uiflow2/api_sweep/fixtures/button_callback_a.json \
  --done-marker BUTTON_CALLBACK_DONE --out-dir <new-output-dir>
```

不要复用输出目录；停止会话时保留 evidence 和 `purge=0` 历史。

## 未覆盖项

- Core2 legacy UIFlow `RUNTIME-03` 的正常 WDT、原厂 startup UI、setup/REPL 和
  完整应用帧；
- 外部加密 ESP-NOW peer、RF、Timing、loss/retry 和跨设备 fabric；
- StopWatch/Core2 二十八类 M5UI 完整文档方法矩阵；
- 所有物理硬件、触控压力、显示时序、声学、光学和电气验证。
