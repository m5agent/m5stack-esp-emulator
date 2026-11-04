# 浏览器输入验收：圆屏、PM1 应用配置与 Cardputer 清理

日期与最近核对：`2026-11-04`。执行层级：**virtual-device validation**。
本记录覆盖 StopWatch 显示观察器、显式 PM1 按键应用模式，以及 Cardputer-ADV
56 键与运行中断清理。原始失败、诊断观察器错误和缺失收据均保留。
它记录三个独立范围，未授予全19款、完整60例或生产部署通过。

| 范围 | 保留的早期结果 | 后续独立结果 |
| --- | --- | --- |
| StopWatch 圆屏 | 41项已完成编辑器检查通过，随后矩形满红观察器超时 | 明确亮度与逐像素圆形观察器，完整编辑器 `55/55 PASS` |
| StopWatch PM1 | 默认应用模式的 PWR 250 ms 输入未观察到事件 | 显式500 ms识别窗、250 ms输入，正式 `19/19 PASS`、6个键鼠pulse |
| Cardputer-ADV | R3的112项输入均通过，随后 finally 中 deinit 被 KeyboardInterrupt 打断 | 单Ctrl-C与同run幂等修复后，V4独立 `516/516 PASS`、112项输入与deinit通过 |

结构化入口是 [summary.json](summary.json)。三个分主题摘要分别是
[圆屏](stopwatch-frame-summary.json)、[PM1应用模式](pm1-application-summary.json)、
[Cardputer输入与中断](cardputer-interrupt-summary.json)。每份摘要小于64 KiB，
只收录必要事实、原始工件字节数和SHA；不提交raw、Flash、像素数组或浏览器身份。
后续完整矩阵R4因独立的Cardputer编辑器复位异常终止。
本记录只追加该次失败的hash与范围边界；连续复位诊断和精确执行策略另见
[复位调查](../2026-11-04-cardputer-workbench-reset/README.md)，不向本记录转授。

## 同一执行产物与可继承边界

| 身份 | SHA256 |
| --- | --- |
| StopWatch工作台Flash | `5a7fb2941c2dfa7b17ca57defa5ea857191e64daeb774d05da5cd427cd45fe2a` |
| Cardputer-ADV工作台Flash | `b6255f6af5ad10236380eae09a76b44ca174b5c4de391aef16413bdc590952bd` |
| runtime75 WASM | `96ea9f91956aa80926182ed174ea426f3f4c84e96ca58754fa249063fdda5ca1` |
| runtime manifest | `fa6b56048ec91d100cb4f2a15088ce77e313bd2e6e8ba083229826b258297c51` |
| V4 site manifest | `772f9e8618a6d32fa8f44981734bcfe1f1dd3a77f6bf834a61c8d5f971420f6f` |
| 修复后的运行中断JS | `f5cd3daa3cf4cdc363cd1093802fe3a2ed9ca62b8ebb59be0dd86e398c6ca196` |

摘要另列原官方base、确定性组合的boot/main源码、实际profile、source/test/helper
SHA、各历史site manifest、运行时资产和原始报告摘要。两板均为clockDivisor1、
无clock override、无icount、无oneInsn override；每个case绑定自己的真实收据。
这些修复没有重建QEMU/C、修改WDT、guest时钟或默认Flash。网页运行中断JS的
变化单独记录，PM1寄存器配置由运行的应用通过原公开API完成。

## StopWatch：观察器应服从固定圆形几何

原始失败帧为466×466：圆内170499点均为`0x7800`，圆外46657点均为黑。
其41项已完成的源码/编辑器检查都通过；等待帧观察器时才超时。
原观察器要求矩形帧超过95%为亮红色，而圆形可见区域仅占78.5145%，因此即使
满亮度也无法满足原条件。首FAIL报告SHA为
`ffd4ede8cf0d8dc2b631f88da18d6a4cf3ea64a3ee7d525894616f61179dc187`。

实际编译的`hw/m5stopwatch/co5300.c` SHA为
`c97309ceb1a2f96f6667c1161f82bdaa6003d8417c2c103cb38396ff780155cd`。
它保留满足`(x-233)^2+(y-233)^2 <= 233^2`的点，并强制其它console点为黑；
整数坐标范围为0至465。原SDK亮度默认127与控制器的brightness/255缩放可预测
红色`0x7800`，但RGB565量化意味着帧本身不能反推出唯一的未读取亮度寄存器值。

修复的guest源码使用原公开`M5.Display.setRotation(0)`、`setBrightness(255)`
和`fillScreen(0xFF0000)`，回读SDK逻辑宽高468×468、亮度255；物理帧继续保持
466×466。新观察器逐点要求圆内170499点为`0xf800`、圆外46657点为0。
它使用固定审核几何，没有根据输出重新估计圆，也没有降低全帧红色比例阈值。
对应[观察器和原API说明](../../../tests/browser-qemu/uiflow_workbench/README.stopwatch-frame.md)
列出固定M5GFX来源；host正控与11项负控覆盖半亮度、满红矩形、单点错色、角落
泄漏、精确边界及尺寸/缓冲区等，均不是guest执行替代。

独立修复run的55项完整编辑器检查通过，实际帧圆内/外错误数均为0，帧SHA为
`8d2b8ecd9cb38142e7160c2ff1cea605e4ab4b73f0d64fb953f4abfde02b566f`。
首FAIL只有六个实际CDP Worker关闭收据，normal-QMP事后状态为 **NOT CAPTURED**；
后续55 PASS另有正常QMP退出、零强制/兜底终止、保留iframe时的CDP检查和最终
六target关闭。后来的收据不填补原失败缺口。

## PM1：500 ms是应用识别窗，输入仍为250 ms

首次正式StopWatch按键run的A/B键鼠4个pulse通过，随后PWR键盘250 ms输入后
没有原`BtnPWR`事件；guest心跳持续，实际controller已接受P down/up。
该run的PWR鼠标case未执行，normal-QMP和独立CDP清场为 **NOT CAPTURED**。
首FAIL SHA为`da299a6b5a50af376a92aa47e6fce4472c2ff0ebc32b9ce3747935837223aca4`。

四个独立有界诊断分别执行配置/公开Power元数据、独占`Power.getKeyState()`、
真实I2C配置后的原`M5.update()/BtnPWR`，以及原公开Python驱动配置。
默认配置实读为`0x49=0x2a`、`0x4a=0`；默认reader诊断的键盘/鼠标250 ms均未观察
到事件。`Power.getKeyState()`消费IRQ42，不能与`M5.update()`同时抢读；寄存器48
还有读清除副作用。各诊断采用独立reader与VM，均保留正常QMP和实际六CDP清场。

最终正式应用fixture使用：

```python
pm1 = M5PM1(i2c, addr=0x6e)
pm1.disable_single_click_reset()
pm1.set_button_timing(M5PM1.BUTTON_TIMING_CLICK, 500)
```

实际guest回读`0x49: 0x2a -> 0x2d`、`0x4a: 0 -> 0`，保留其它配置位。
它选择single-click IRQ并扩大点击识别窗；真实键盘/鼠标pulse仍固定请求250 ms，
没有延长输入等待guest确认。正式run的A/B/PWR键鼠6个pulse与19项检查均通过，
PWR两种输入都由原`wasClicked`报告；正常QMP退出、零兜底终止及实际六CDP关闭。
该结果是 **configured application PASS**，不能写成默认PM1模式已有按键事件。

显式配置表只含源码已核实的四个PM1型号：

| 型号 | 原公开内部I2C | SCL/SDA | PM1地址 |
| --- | --- | --- | --- |
| StopWatch | I2C1 | 48/47 | `0x6e` |
| StickS3 | I2C1 | 48/47 | `0x6e` |
| PaperColor | I2C1 | 2/3 | `0x6e` |
| PaperMono | I2C1 | 48/47 | `0x6e` |

本记录只授予StopWatch正式应用结果；其它三板仍需自己的guest证据。
实际模型把I2C0/1接到共享slave bus，不能把通过描述为电气GPIO约束证明。
固定release/M5Unified与后续Python driver源码用于解释API，未冒充October base
二进制的bit-exact源码；同一实际二进制已独立执行公开driver API。
默认250 ms阈值的原C函数host对照支持“实际略超过阈值可无事件”的解释，但
首失败的私有PM1虚拟hold未被测量，不能据此宣称唯一原因已证明。

## Cardputer：完整输入通过仍须完成finally清理

原旧双Ctrl-C产品已有一次独立516 PASS，仍保留。R3后来在56键各键盘/真实鼠标
共112项输入全部通过后，唯一失败为`public-driver-deinit-and-raw-repl-interrupt`。
实际stderr落在finally调用的`hardware/matrix_keyboard.py:80 deinit`内，
`interrupted=true`、runner error为空，但缺少deinit完成marker。原R3报告SHA为
`24a3aa82a4a2a02632e8a94a2d7b517847e38ab17b4d5c63dbf5eb4d74b4a1db`。
该失败有实际正常QMP exit0、零兜底终止与六CDP关闭，不能把输入通过替代清理通过。

固定官方MicroPython源码显示，pending exception槽处理后会先清空再raise；
原UART0 `dupterm_notify`在读到Ctrl-C时结束该次通知读取，第二字节可能稍后再
调度一次异常。用户函数及finally仍在执行时，pyexec尚未关闭Ctrl-C。两个字节
也可能先到达而合并，因此旧solo PASS和后来的FAIL并不矛盾。

首次自然短诊断中两种transport的finally均完成，没有重现R3时序；其两份报告
仍为FAIL，因为新诊断观察器误把随后正常退出raw REPL的Ctrl-B `[2]`也算成了
interrupt写入。这些raw状态未重写，新摘要明确分开Ctrl-C与Ctrl-B事实。

随后另立**受控拆包fault injection**：只对运行态原payload `[3,3]`，通过原
`writeUart`及同一owner先发送第一3，实际收到guest的`FINALLY_BEGIN`后，再发送
其原有第二3。200 ms finally窗口内，第二字节在marker后约27.4 ms送入，实际
打断清理、缺失deinit结束。候选单`[3]`接收两个并发interrupt请求，实际只发送
一次，原公开`MatrixKeyboard.deinit()`完整结束。两组诊断都正常退出并关闭六CDP。
这是修改transport的明确负/正对照，证明第二次异常能抢finally；它没有重建
原R3逐字节通知时序，也不代替完整键盘验收。

修复提交`9c8f0762603d41f5a880df2bac0e36e510bc1199`只改变运行中断：发送一个
Ctrl-C，并在进入transport前为同run锁住Promise。重复请求不再发送异常、不刷新
中断deadline；session/epoch、UART owner、upload、pause及stop守卫仍在锁之前。
新run有新锁，原连接阶段CR/Ctrl-C/Ctrl-C握手保持。原fixture的finally、公开
deinit和marker检查均未放宽；四项受影响窄Node合同是host证据，另列于摘要。

V4正式独立run的 **516/516检查、112输入、56个鼠标raycast及deinit全部PASS**。
每个subject都保留250 ms请求，实际宿主记录约250.973–256.990 ms；这不是性能
分布结论。原public callback、按下与释放状态均来自TCA8418/I2C/GPIO11 IRQ及
原驱动，没有外部private ISR、手动FIFO扫描、tick或替换Pin IRQ。
V4报告SHA为`00147ec3a208cd743c54e1274ef34fff700c2a2d2196dc84a30e1524d98959cd`。

Fn按原API采用Fn+grave伴随形成ESC；鼠标Fn的grave伴随仍是单独记录的键盘输入，
因此不是56组纯鼠标单键/chord。旧11键private-ISR固定fixture不能继承这项
56键真实IRQ结论；G0/Boot、power/reset滑块及其它型号也各有独立验收边界。
V4 normal-QMP/engine metadata与六实际CDP在context关闭前消失均已捕获；
**保留iframe时的实际CDP检查为NOT CAPTURED**，不能借engine metadata或其它
runner的两阶段证据补齐。实际ANGLE renderer已记录，该runner未断言特定renderer字符串。

后续全60例R4在7个已启动case中以6 PASS和Cardputer完整编辑器FAIL终止。
该case先通过44项检查，实际硬件QMP reset后第二次启动发生WASM
`memory access out of bounds`。其raw为1,705,609字节、SHA
`a369b601cecf52ae9ae4243ae0ad315ed18eeca475451341f0eb3bb024bcac2e`。
实际normal-QMP为false、engine fallback1，虽六个CDP均已关闭，仍不能称正常guest退出。
这是独立的完整编辑器复位路径缺口，原因尚未确定。V4单独516 PASS只授予本次
56键真实IRQ/输入和单中断finally清理；Cardputer完整editor reset、稳定性与
全60验收继续开放。该OOB没有被归因到早期双Ctrl-C的清理竞态。

## 复验入口

使用匹配记录manifest/runtime/default registry的已校验静态导出、Chrome与
Playwright，给每次run分配全新ignored输出。标准入口如下：

```sh
M5_PUBLIC_SITE="$SITE" M5_QEMU_DEVICE=stopwatch \
M5_PUBLIC_QEMU_OUT="$NEW_OUT" M5_WASM_CHROME="$CHROME" \
node platform/tests/test_public_uiflow_guest.mjs

M5_PUBLIC_SITE="$SITE" M5_QEMU_DEVICE=stopwatch \
M5_PUBLIC_QEMU_OUT="$NEW_OUT" M5_WASM_CHROME="$CHROME" \
node platform/tests/test_public_qemu_buttons_guest.mjs

M5_PUBLIC_SITE="$SITE" M5_CARDPUTER_KEYBOARD_IRQ=1 \
M5_QEMU_DEVICE=cardputer-adv M5_QEMU_BUTTON_HOLD_MS=250 \
M5_PUBLIC_QEMU_OUT="$NEW_OUT" M5_WASM_CHROME="$CHROME" \
node platform/tests/test_public_uiflow_cardputer_keyboard_guest.mjs
```

历史FAIL须使用对应旧source/export身份；标准runner不会启用拆包fault injection。
更多输入契约见[按键fixture](../../../tests/browser-qemu/uiflow_workbench/README.buttons.md)
与[Cardputer IRQ fixture](../../../tests/browser-qemu/uiflow_workbench/README.cardputer-keyboard.md)。
普通checkout检查不依赖本机历史raw。这些结果不建立物理RF、电气、功耗或光学等价，
线上Pages和全60矩阵须分别保留自己的真实执行证据。
