# Atom / Stick 主机运行接入（限定验证）

本轮从公开模型仓库固定提交 `4879ab51eb8bb11ce024e670ae6880529e3d0f42`
导入新增主机，并为十款设备实现独立 QEMU 板接线。模型库存为 38 款主机、
184 款 Unit；中央运行目录为 24 款。编译出 machine、能够创建 lease、
模型交互和原厂固件功能通过是不同的证据层级。

机器可读结果与准确固件/运行时/报告哈希见 [summary.json](summary.json)。
原始串口、帧、QOM、Flash、ZIP 和浏览器请求记录保存在本地忽略的 `.work`，
未提交二进制或未脱敏运行日志。所有 PASS 均为虚拟设备验证。

## 已验证的原生路径

| 独立设备 | 同一 guest 内验证的行为 | 尚未覆盖 |
| --- | --- | --- |
| AtomS3 C123 | 128×128 GC9107、GPIO41 A down/up/count 与帧、MPU6886 两组六轴输入、GPIO35 RMT 实际双色输出 | 默认 RGB() 返回 None；IR、网络和物理硬件 |
| AtomS3 Lite C124 | 原 RGB()、GPIO41 A、GPIO35 WS2812 RMT 双色与释放恢复；无 LCD | USB CDC、IR、网络、物理光度 |
| StickC K016 | 80×160 ST7735S、GPIO37 实际电平和 BtnA、64 像素标记、MPU6886 一组六轴输入 | B/电源、RTC、音频及其它外设 |
| StickC Plus SE | 135×240 ST7789V2、GPIO37 实际电平和 BtnA、64 像素标记 | B/电源、RTC、音频；本板没有 IMU |
| StickC Plus2 K016-P2 | 135×240、A/B/PWR 三键 down/up、MPU6886 两组六轴输入、PCF8563 I2C1 写读及推进 | ADC、音频、IR、保持供电/唤醒；该官方构建关闭 LVGL |

`M5.getBoard()` 是原 UIFlow2 绑定里的编译期 `BOARD_ID`，只作为固件身份辅助，
不单独证明 M5Unified 自动识别。板级证据还包括真实 GPIO、显示控制器、
I2C/RMT 事务和同 session 的 guest 结果。

Lite 和 Dial 的官方固件关闭 UART REPL，默认日志经 USB CDC。测试 boot
显式使用现有真实 UART0 `os.dupterm`；AtomS3/Plus2 保留原 UART0 REPL，
不重复初始化。第一次仅等待 UART0 banner 的超时不是 Lite 启动故障：旧运行已
有 RMT 帧，后续按下和释放确实改变原 guest 的 RGB。无因果证据的空载 SPI
候选修复已撤销，没有进入最终补丁集。

## 纯浏览器与同 VM Run

五款新增设备的独立 Chrome/Metal 验收共 117 项通过：AtomS3 24、Lite 14、
StickC 25、SE 25、Plus2 29。各自保持准确 Flash SHA，按键经过原厂驱动，
真实帧逐像素送到模型；Lite 的原 RGB() 经 RMT 解码/只读 QOM 回到模型。
CDP 观察 engine 与全部 pthread 在 iframe 移除前关闭；无 Device Service
请求、页面错误或强制终止兜底。新准入后的完整公开导出回归另在 summary 记录。

原生 AtomS3 和 Plus2 还分别通过 11 项 `uiflow-live` 验证：同 VM 两次 Run、
A 键与实际帧、故意 RuntimeError 的 failed 状态、恢复后 DONE、nonce/PID/固件
保持一致和过期 execution 拒绝。两台均在 ZIP 后停止并释放 Flash；不将此
原生编辑器结果拼接成浏览器 Run 或其它设备的证据。

## 修复与边界

Plus2 原厂镜像的 LittleFS 挂载失败来自 classic ESP32 SSI 的 QIO 头长度：
旧桥固定按 ISSI 的三字节 mode/dummy 发出，而实际 GigaDevice/Winbond
Flash 模型需要五字节，导致 `Partition.readblocks` 前移两字节。`0089` 按所接
Flash 模型设置长度，仅作用于 CS0，PSRAM CS1 保留原事务。
原厂固件对照、UART raw REPL 分区读诊断和修复后同 guest 回归分别保留。

Atom Lite、Atom Matrix 和 Matrix v1.1 各自的准确官方固件，均在独立 55 秒
原生窗口内未到 Python probe、没有 RMT 帧。touch/GPIO 自动识别只是待验证
假设，不能写成根因。未强制板型、未借用其它型号固件、未替代传感器数值。
原 StickC Plus 尚缺准确已核验 UIFlow2 镜像，Service 明确阻断；SE/Plus2 的
固件不作为替代。其它芯片或改版主机仍按 Backlog 单独接入。

Dial 的显示、触摸、GPIO42 按键和 RTC 已有同 guest 原生结果；首次 5ms
旋钮边沿试验发生丢步，旋钮功能在完成修复和新运行时复验前保持 partial。详见 [GPIO 回调诊断](dial-rotary.md)。
浏览器准入与原生结果分别记录，不从本表自动继承。

## 复现入口

- 固定来源导入：`python3 platform/tools/sync_visual_models.py --source <public-model-repo> --commit 4879ab51eb8bb11ce024e670ae6880529e3d0f42 --check`。
- 原生源码：`scripts/bootstrap-unit-runtime.py` 与
  `patches/qemu-m5stack-peripherals/0085..0089`；完整配方和上下文层见对应 README。
- 源码组成：`platform/tools/uiflow_source.py`，从准确原镜像实际分区表保留
  VFS 外字节，只加入已核验 probe。新增源码位于 `tests/uiflow2/`。
- 功能运行：独立端口、状态目录及令牌的 Device Service `/api/v1`；逐型号
  artifact/firmware/session → serial/frame/input/QOM → evidence ZIP →
  stop `purge=0`。不使用用户测试服务。
- 浏览器：固定锁源码构建、LittleFS 源码构建、静态子路径导出及独立端口；
  `test_public_qemu_board_guest.mjs` 与 `test_public_qemu_headless_guest.mjs`
  检查同浏览器 guest、纹理/LED、输入和 Worker 退出，无 Device Service 拼接。
- 共享控制器回归、平台及来源门禁结果另在 summary / 验证台账追加；
  未执行的项目明确记录，不据局部通过宣称整机完成。
