# PaperColor帧观察器：固定Spectra6红色与默认Run

日期与最近核对：`2026-11-04`。执行层级：**virtual-device validation**。
原始报告字节数/SHA、固定源码postimage、观察器与执行身份见
[summary.json](summary.json)。本记录保留R5首次失败；修复观察器后的独立单板
完整run **64/64 PASS**。其后报告层又有source-only加严，须由下一完整guest
矩阵独立验证，没有全19款、全60例或线上部署通过声明。

## 原始失败

R5的PaperColor完整编辑器先通过41项代码/串口/编辑器检查，随后等待通用LCD红帧
观察器超时。实际原公开`M5.Lcd.fillScreen(0xFF0000)`已返回；保留帧为400×600，
240000个RGB565像素全部为`0xb800`，帧SHA为
`302109d862954d082040aa86344563144a1cd571a03502d2e39b381f3e8fc900`。
旧观察器要求超过95%为`0xf800`，因此没有接受实际Spectra6面板输出。

首FAIL raw为13,041,559字节，SHA
`782a369e083ff304a860ed13dd152457a4f9f5fdab3a8820ea51876c1359b2a6`。
41个已完成check均为true；超时发生时没有追加一个false check row，不能把它解读为
完整编辑器PASS。当轮全60例以24started、23PASS及该FAIL停止。

失败后的实际stop正常QMP exit0、nested workers0、零强制disposal、零engine
fallback；六个实际CDP Worker在context关闭前全部消失。**保留iframe时的实际
CDP检查为NOT CAPTURED**，不能由engine metadata的before-iframe阶段补齐。

## 同一产物身份

| 身份 | SHA256 / 值 |
| --- | --- |
| 原官方base Flash | `166dbd7cfccda4ade1b2284774176955776d24a6fb08434b7ef1d8fca5897816` |
| PaperColor工作台Flash | `c4486aba3d494048a8dd9e464a610bce0d19369b51ae814f2f221ddc630b6b34` |
| runtime75 WASM | `96ea9f91956aa80926182ed174ea426f3f4c84e96ca58754fa249063fdda5ca1` |
| runtime manifest | `fa6b56048ec91d100cb4f2a15088ce77e313bd2e6e8ba083229826b258297c51` |
| 原V5 site manifest | `6123a283c5a32254d76b9de64aaba2bae64de22aecd7207b48dd2ce0af2c8bbb` |
| 首失败原runner | `b417ca05de7baf6465e44ad38c1ccbc84d903142ffdd6e319e067080473bd010` |

实际board为`m5papercolor`，profile为`papercolor-wasm-wallclock-epaper-probe`，
clockDivisor1、无clock override、无icount或oneInsn override。startup boot/main
及source/runtime/test SHA另列于摘要。此次修复范围为测试观察器与验收覆盖，
产品V5、C/runtime、默认Flash、控制器、时钟和WDT没有改变。

## 独立源码链为何预期B800

以下三个实际build源文件SHA均与runtime manifest的postimage一致：

| 源文件 | SHA256 | 作用 |
| --- | --- | --- |
| `hw/m5stopwatch/m5_epd_panel.c` | `34a1b53b7265f7ae7d4d33cd0410bcb650a499979aa80192e76d53576d2d8a89` | 解码Spectra6 packed nibble，index3返回ARGB `0xffbf0000` |
| `ui/console.c` | `a8502037244411eb2cb712b2edee94031ebf2511c3a8a0275c2433cae844c23b` | 使用`PIXMAN_OP_SRC`转换为共享帧`PIXMAN_r5g6b5` |
| `hw/m5stopwatch/m5papercolor.c` | `48c9056ed530834f2bed3fe085e0823b7613efb2aa9059d09f11ff7659d27360` | native/output均400×600，`color=true` |

因此模型的红色8-bit分量为`0xbf`，转RGB565为
`(0xbf >> 3) << 11 = 23 << 11 = 0xb800`。这是固定控制器调色板与真实帧转换路径
的预期，不是从失败截图临时学习目标颜色，也不是物理面板颜色准确度测量。

既有[EPD质量fixture](../../../platform/tests/fixtures/browser_epd_quality_oracles.json)
为15,921字节，SHA
`2957661990130249d17b2250e6962f0cfd86210c09fad54f637d85af3db4e3aa`，
其中输入`0xff0000`的red ROI也独立预期64/64点为`0xb800`、例外0。
它只佐证固定source/旧固定例的契约，不能转授本次新默认工作台guest通过。

## 严格新观察器与host负控

新[PaperColor观察器](../../../platform/tests/public_qemu_papercolor_frame_oracle.mjs)
要求同时满足：

- 物理帧恰为400×600、`rgb565le`、480000字节；
- 240000点逐点恰为`0xb800`，一处错色也失败；
- transport sequence是有效整数且大于绘制前snapshot；
- sourceSequence同样有效且大于绘制前snapshot，拒绝旧source帧。

它只观察原guest帧，不改像素、不降低颜色占比阈值。
[host合同](../../../platform/tests/test_public_qemu_papercolor_frame_oracle.mjs)
用独立Uint16构造正控及序列化浏览器函数正控，包含16项负控：LCD满红F800、
其它颜色/字节交换、方向/尺寸/格式/短buffer、旧sequence/sourceSequence、无效
freshness、缺帧、单点错色和负snapshot bound等。本文只读核对这些source，未在
根代理拥有的guest运行期间重复执行；host控制也不代表固件或物理验证。

## 原样默认textarea与重复直接Run

更新的完整runner还将默认textarea与以下原始文本逐字比较，保持编辑器内容不动，
直接Run一次并在同VM中再次直接Run：

```python
import M5
M5.begin()
print("Hello, UIFlow!")
```

两次都必须通过原UART runner、返回实际`Hello, UIFlow!`并重新启用Run。
然后继续原UTF-8/长源码、异常、文件输入、暂停/中断、显示、硬件reset及正常清场
检查，没有增加额外VM启动。新增覆盖不是失败后的自动重试，也不替代原完整检查。

## 独立单板64项结果与入口

终态后独立核对的PaperColor完整复验为 **64/64 PASS**。报告为18,818,790字节，
SHA `5e0d22bf082d6d031222791a666856b954562c028eca65dbc77b2cd97c818c04`。
实际guest验收控制脚本SHA为
`a8aec2e14e5010900bbcae9dfbfa9551b1f5b7bb2cddfe336a88fa5c5434a32f`；
PaperColor oracle SHA为
`47074556aec371cd7808cf8123cc004c6ece62417d937cb48e476c6e1f58b78e`，
独立provenance helper另为`7a8d75a2bf4d8ce51c611530f0c69403e1b0930385f786397dcc105a12d67935`。

原textarea第一次和重复直接Run均真实执行同一源码，SHA
`93ebf6c7166ac121b8f6163c836ed1001e4ba469c47e3cfd3a90f47908ccc1db`，
两次stdout为`Hello, UIFlow!`、stderr空、runner error空，session/console一致。
随后原完整源码、暂停/中断、显示与hardware-reset后的新console执行通过。

绘制前display/source sequence为5/18，观察器记录的新frame为6/20，全部240000
点为`0xb800`、unexpected0。实际像素SHA仍为
`302109d862954d082040aa86344563144a1cd571a03502d2e39b381f3e8fc900`，
相同纯色内容不代表复用旧帧，两个freshness计数独立增加。该历史报告的top-level
source_sequence未捕获，20保存在oracle内，不能事后补成新字段。

实际normal-QMP exit0、nested workers0、零强制disposal、零engine fallback；
保留iframe时与context关闭前的两阶段实际六CDP检查均通过。原R5 FAIL及其缺失
的held-iframe围栏仍保留；后续正常收据不回填。

```sh
M5_PUBLIC_SITE="$SITE" M5_QEMU_DEVICE=papercolor \
M5_PUBLIC_QEMU_OUT="$NEW_OUT" M5_WASM_CHROME="$CHROME" \
node platform/tests/test_public_uiflow_guest.mjs
```

使用记录的默认Flash/runtime/profile与已校验静态导出、Chrome/Playwright及全新
ignored输出。旧b417失败与新观察器结果分别保留；raw报告、像素、binary与私有
浏览器身份不随源码提交。普通checkout不依赖这些本机历史工件。
全60矩阵、其它镜像、线上Pages与物理光学/电气行为仍须分别立证。

## 后续报告层source-only加严

单板64 PASS之后，共用runner进一步移除PaperMono无关的expected-red字段；
PaperColor改用一次不可变实际frame快照统一计算hash/count/oracle，并从同一
快照补充top-level source_sequence。产品V5与执行的guest源码没有改变。
更新脚本SHA为
`8f9dad6414db348a315acdaceab73f4e95abdbe10440056edb7eed42356c93c2`。

根代理报告该source阶段28项Node合同通过，本文未重复执行。它们是host证据，
不能把实际A8窄run追认为8f9的guest PASS；下一完整60例将独立执行8f9控制脚本。
