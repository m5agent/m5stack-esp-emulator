# CoreS3 LVGL + PIR browser-QEMU fixture

`boot.py` 和 `main.py` 是用于同 guest 验证的固定源码。程序使用官方
UIFlow2 v2.5.3 固件内置的 `m5ui`、`lvgl` 和 `unit.PIRUnit`，不上传驱动覆盖。
`boot.py` 沿用既有 UART0 / `os.dupterm` bootstrap，使真实 guest 串口可观测。
仅构造和刷新 LVGL 控件；不混入 Widgets 或宿主绘制的数据。

`contract.json` 固定原始 base、补齐后的 base、组合 Flash、源码和 ROM SHA。
组合后的 Flash SHA 必须是
`78961297e751ec9c743b4cdf89cc2c137e7e2c801dda3ead9df2ea45d59fbd3f`。
源码包哈希使用按文件路径排序的紧凑 JSON UTF-8 格式；换行或源码变化会改变身份。
此目录不包含固件、ROM、运行日志和验证结果；fixture 本身不授予运行 PASS。

通过独立端口、state 目录和 token 的 [Device Service](../../../docs/device-service-api.md)
执行。用户的 8787 服务与 8830 预览必须保留，不用于此测试。
先上传并导入 base，再将本目录两个 Python 文件交给 `/firmware/uiflow`，同时提供
`base_firmware_id` 和规范化 base 的 `expected_base_sha256`。创建可见
`runtime=qemu` 会话并附加 Port A 的 PIR；浏览器结果还必须核对实际 WASM 身份。
不直接启动 QEMU。每份结果独立绑定同一个 session、guest、固件和运行时，
原生对照不能替代浏览器执行证据。

验收需要同时满足以下条件：

- 串口出现 `CORES3_WASM ` JSON 的 `begin`、`m5_ready`、`lvgl_ready`、`ready`；
  `fixture` 一致，`seq` 递增，显示尺寸为 320×240。上传回显不计执行。
- 从 guest framebuffer 获取真实页面：标题、`Clicks: 0`、`PIR: CLEAR` 和蓝色按钮。
  精确采样点、区域和 RGB565 容差见 contract；浏览器模型外壳不替代 framebuffer。
- 触摸背景 `(310,235)` 后计数仍为零；触摸按钮中心 `(160,184)` 两次，要求实际
  PRESSED / RELEASED / CLICKED 事件、计数 1 / 2，以及计数和按钮文字区域改变。
- 通过同会话 Unit API 显式输入 `motion=false → true → false`，同时检查 QOM
  `input-events`、`input-level` 与 guest `kind=pir,value=0 → 1 → 0`。官方驱动读的是
  白线 GPIO1；`PIRUnit((1,2))` 的黄线 GPIO2 对该 Unit 为 NC。
- `motion=false` 可能仍处于既有两秒虚拟时钟 hold，须等待真实 GPIO 和 guest
  转换。PIR 文字区域应改变并恢复；最终 heartbeat 保持 `clicks=2,pir=0`。
- 停止前取得 evidence ZIP，再以 `purge=0` 停止；检查 lease 释放、运行进程或
  Worker 退出，以及历史串口和最后一帧保留。原始证据放在 Git 之外。

API 依据为官方文档 `m5ui/_overview.md`、page/button/label、unit/pir、
hardware/display/uart，采用 `M5.begin()`、`m5ui.init()`、显式 parent page、
Montserrat 字体、LVGL 事件、文本更新、`screen_load()`、`M5.update()` 和
`get_status()`。官方源码与产品链接、仓库接线依据见 contract。

PIR 是输入 Unit。本例证明范围只包含精确 guest 的 GPIO、触摸和 LVGL 路径；
不声明物理硬件、光学检测、电气、网络、音频或其他 Unit/设备/固件兼容性。
