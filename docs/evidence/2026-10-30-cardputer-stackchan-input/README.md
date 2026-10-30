# Cardputer-ADV 原键盘/显示与 StackChan 运动中屏幕输入

基线为已合并 PR #30/#39 的 `main e3f149c1`。结果限定浏览器虚拟设备；
原用户上传镜像、物理硬件和本轮完整 native 外设矩阵均为 **NOT RUN**。
源码、构建检查和真实 guest 结果分别记录，不从旧 Pages 或 native 继承通过。

## Cardputer-ADV

电脑双 Shift、Alt 和 grave 需要路由到 ADV 的实际物理键；修复仅作用于该
型号实例，保留聚合释放及浏览器快捷键保护。正常键盘使用原 TCA8418
GPIO11 IRQ → `M5Cardputer.update()`，没有手动调用私有 ISR 或替换按键状态。

显示有两个独立错误：原方向 getter 从最后绘图窗口判断横竖屏，8×8 局部更新
会使方向丢失；玻璃安装方向还使默认 rotation 1 的文字倒置。`0022` 使用
MADCTL.MV，`0023` 仅纠正 ADV 的玻璃安装方向；网页平面图及坐标使用互逆的
顺时针变换。非 Cardputer 面板不再查询其专用 SPI 方向 QOM。

四种旋转分别核验尺寸、独立四角颜色、64 像素局部绘制和实际模型纹理；键盘
逐个验证 56 个物理键的按下/松开，并覆盖双 Shift、大写、grave、Fn-Up 与
原修饰标志。最终导出的同包复核见 `cardputer.summary.json`。
构建与执行入口见[固定原始 Arduino 探针](../../../tests/firmware/cardputer_input_orientation/README.md)。

早期观察器使用错误 ESM query 的 guest 未运行，旧 66-patch 包确实显示倒置。
初版探针的 signed RGB888 常量误选 RGB565 overload 及自动推进的观察竞态
单独保留，不将其当成后端颜色缺陷。旧 Piano Tiles 镜像当前未取得，未复测。

## StackChan

不是舵机运动与屏幕触摸必须互斥。原默认示例在前台同步执行 SCS UART 和
整条遥测重画，实际绘图约 1.16–1.33 秒、循环间隔约 1.64–1.75 秒，足以漏掉
真实输入。相同基底的受控 A/B 表明原 `StackChan(i2c=1)` 构造前后都能读到
屏幕触摸；不能将其解释为 Touch 被禁用或 I2C 构造必然破坏总线。

新版默认使用真实 MicroPython `_thread` 执行原 UART SCS API；前台独占
`M5.update()`、FT6336U、Si12T、显示及供电 I2C。八项队列锁内无 IO，
绘图每轮至多更新一个字符。串口事件由前台统一输出，异常断电也留在前台。
没有拉长网页输入、伪造 Touch 或用目标角度代替实际位置。

最终默认入口的实际 DOM 持有时间为 105.355、302.000、802.825ms，三档均读到
原 Touch 按下/松开及匹配坐标；持有期间独立 QOM 实际位置分别变化
20、32/24、229 ticks。另有 raw-frame 诊断。24 项检查全部通过，普通 Stop
在 context 关闭前使六个 CDP Worker 归零。观察到的最大轮询间隔为 187ms，
本次成功不构成普遍 100ms 响应上界或任意负载不漏短按保证。
见[默认入口摘要](stackchan-reference.summary.json)。

独立[Arduino 原 BSP 探针](../../../tests/firmware/stackchan_screen_motion/README.md)
同时运行真实 Motion task 与屏幕轮询；故意 `delay(6000)` 不轮询的负控保留。
FT6336U 屏幕与 Si12T 顶部电极是不同输入。固定官方 Dance 帧循环的
`Motion.move()` 加 `delay()` 也未在内部更新 Touch；不能据此推定未取得的
用户镜像具有同一缺陷。Arduino 最终结果单独记录，不拼接到默认 UIFlow2。
最终两 case 的输入/FT 读回/运动/负控功能均通过；首 polling 普通 Stop 虽已
exit0，清理等待预算结束仍有一个 engine CDP target，因此整体 **PARTIAL**。
第二 blocked case 在关闭其 context 前累计 12 个 Worker 全部归零，不能覆盖
第一次清理失败。准确时长与身份见 `stackchan-arduino.summary.json`。

## 身份、失败与范围

- [新运行时构建摘要](runtime-build.summary.json)：67 patches，158 源文件，
  全新 1446 个 Ninja target；WASM `a7fe7180…9230e`，构建检查不授 guest PASS。
- [最终 V4 导出](export-v4.summary.json)：manifest `16ab2bb4…59f40`，
  2115 资源，19 public / 0 candidate，不含固件、ROM 或服务地址。
- [原失败与诊断](stackchan-diagnostics.summary.json)：原默认短按失效、I2C
  A/B、同步工作计时及 V3 最小优化失败原样分层保留；V3 raw300 的 Touch
  通过但运动重叠证据不足，不能称整项通过。

所有完整 Flash、串口、截图、帧系列、浏览器响应及冻结源码留在忽略存储。
公开文件只是有界摘要。默认示例正常 Stop 通过不关闭 Arduino 普通 Stop 或
已知自然 PWR 的 engine Worker 回收问题；其它板型、CFG1、RGB666、更多固件、
长期稳定性、机械和电气仍独立。
fork Pages 是预览发布；原仓库标准 all-admitted 发布门禁本轮未运行。
