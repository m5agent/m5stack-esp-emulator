# 全19板默认UIFlow网页编程与输入验收

日期与最近核对：`2026-11-04`。本次为本地静态站的 **virtual-device validation**：
R8父gate于`07:20:47Z`终态通过，**60/60 case、2,564项检查全部PASS**，没有未运行项。
这是一轮独立的canonical验收，未拼接此前preview或失败矩阵中的PASS。
V6静态导出具有发布门禁资格，但**本记录没有部署或正式HTTPS验证**。
`UI-03`继续保留逐板性能、长期稳定性和正式站点验收；运行时缺口`07/08/09`仍OPEN。

结构化事实见[summary.json](summary.json)，逐case列出raw报告字节数/SHA、控制源码、
精确Flash、实际profile/参数、帧及清场层级。摘要为63,855字节，SHA256为
`9703b94a23025b75be4c8464e32ac835cc75fffa10f5fcc9d88bc144de841151`。
60份raw合计167,174,366字节，未提交串口全文、像素数组、Flash、浏览器身份或主机路径。

## 同一轮执行身份

| 项目 | SHA256或执行范围 |
| --- | --- |
| V6 site manifest | `e597ce3c4465f582928042d4a36be684454a9cb4f8910f80720ad027cf1da898` |
| WASM / runtime75 | `96ea9f91956aa80926182ed174ea426f3f4c84e96ca58754fa249063fdda5ca1` |
| runtime manifest | `fa6b56048ec91d100cb4f2a15088ce77e313bd2e6e8ba083229826b258297c51` |
| 编译runtime源码提交 | `40edccac415693c5130f91c01d84176ae6008566`；其补丁/文件向量另由摘要绑定 |
| canonical registry | `0f0727d10e56811f6c99d45543eb48b60dd6642112dd3ab1e967bc3229448794` |
| 导出registry | `2b3e41efcdd43bbce45458575141126c72853646653c1e3928000e9cfeaebf37` |
| 父gate控制脚本 | `5c07aa157d0b815b4f4038f213ed5af1b4543819cc8faf00fca904d9ef8e2ba4` |
| 父raw报告 | 35,220字节，`4265d32ff912502cb000d6795f1fbd52bcb3795fc54ccb3f83d522db863a343a` |
| 完整编辑器控制脚本 | `8f9dad6414db348a315acdaceab73f4e95abdbe10440056edb7eed42356c93c2` |
| 按钮控制脚本 | `7e1ca495b0006f7976914ded0d51b6f137da9c8155b806ee371820620ac20989` |
| 原按钮API观察器 | `889b00d77edd0f076815b9e3a0a05fbd48ead181e62922f77988630d541bd7d4` |
| MicroPython运行中断JS | `f5cd3daa3cf4cdc363cd1093802fe3a2ed9ca62b8ebb59be0dd86e398c6ca196` |
| 共用startup main.py | `a109d9c11c09b4aa649e1a0a2d0929136fe7083f75bf2452e9c17b57f8b13ab0` |

19板各自从官方UIFlow2二进制基底组合网页编程boot/main：启动执行原`M5.begin()`后
返回真实REPL，不是完整原厂联网菜单。每板完整Flash、原base、boot/main文件和执行
profile均独立核对；相同Flash字节也不能替代不同板型的controller/输入结果。

11个S3工作台各有自己的精确Flash/main/ready/fixture策略，clockDivisor1、
oneInsnPerTb=true，要求`0027-gpio-bounded-transactions.patch`。本轮每份初始与停止
收据的实际完整argv均核对board、UART、eFuse与唯一
`-accel tcg,thread=multi,one-insn-per-tb=on`，没有icount或clock override。
classic、旧固定示例和unknown镜像不继承该工作台策略。profile名字保留candidate
后缀不代表本轮candidate准入：V6 registry为public，manifest候选列表为空。

## 60例的实际范围

| lane | 独立case | 实际检查 |
| --- | ---: | ---: |
| 默认UIFlow完整编辑器 | 19 | 1,179 |
| 普通可见按键键盘/鼠标 | 19 | 282 |
| Cardputer-ADV 56键 | 1 | 516 |
| StackChan三区机身电容触摸 | 1 | 35 |
| 旧固定示例回归 | 20 | 552 |
| 合计 | 60 | 2,564 |

逐板表的“编辑器”列为检查数/已完成program数，“按键”为检查数/subject trials。
CoreS3保留两个独立固定示例；Card56与Stack机身触摸另列，不能由普通G0或PMIC结果代替。

| 设备 | 编辑器检查 / program | 普通按键检查 / 试验 | 固定示例检查 |
| --- | ---: | ---: | ---: |
| `atom-matrix` | 58 / 11 | 10 / 2 | 15 |
| `stickc-plus` | 63 / 12 | 18 / 6 | 26 |
| `cardputer-adv` | 63 / 12 | 10 / 2 | 69 |
| `cores3` | 63 / 12 | 10 / 2 | 49 + 34 |
| `stopwatch` | 64 / 12 | 19 / 6 | 24 |
| `sticks3` | 63 / 12 | 19 / 6 | 25 |
| `atoms3` | 63 / 12 | 10 / 2 | 25 |
| `atoms3-lite` | 58 / 11 | 10 / 2 | 15 |
| `atoms3r` | 63 / 12 | 10 / 2 | 25 |
| `stamplc` | 63 / 12 | 18 / 6 | 25 |
| `stackchan` | 63 / 12 | 10 / 2 | 24 |
| `papercolor` | 64 / 12 | 23 / 8 | 27 |
| `papermono` | 63 / 12 | 19 / 6 | 33 |
| `core2` | 63 / 12 | 22 / 8 | 24 |
| `stickc-plus2` | 63 / 12 | 18 / 6 | 30 |
| `stickc` | 63 / 12 | 18 / 6 | 26 |
| `stickc-plus-se` | 63 / 12 | 18 / 6 | 26 |
| `atom-lite` | 58 / 11 | 10 / 2 | 15 |
| `atom-matrix-v11` | 58 / 11 | 10 / 2 | 15 |

编辑器共完成224次真实raw-paste执行。每板先读取未修改textarea，直接点击首Run，
再原样点击第二次Run；38次均运行精确源码SHA
`93ebf6c7166ac121b8f6163c836ed1001e4ba469c47e3cfd3a90f47908ccc1db`，
真实stdout为`Hello, UIFlow!`，stderr为空，并核对同session/generation/console epoch
和Run恢复。其后保留UTF-8、多行/长源码、预期语法/运行异常、文件导入、暂停/继续、
无限循环中断、同VM恢复、硬reset取消旧epoch及新boot执行。本结果证明这些具体路径，
不宣称`M5.begin()`严格保持全部状态，或任意应用/全部Python模块均兼容。

输入总计200组subject trials：41个普通subject各键鼠共82，Card56各键鼠共112，
Stack三区各键鼠共6。请求hold固定250ms；实际观察间隔单独记录。
Cardputer的Fn鼠标subject使用键盘grave伴随，不能称56组纯鼠标组合。
Stack的Z/X/C与真实pointer都沿可见capacitive组件、Si12T controller和原
`hardware.StackChan.get_touch()`读回；不注入LCD触摸或私有ISR。

四个PM1型号使用明确的应用配置，而非改变默认Flash/C：StopWatch/StickS3调用
原Python`M5PM1` helper；PaperColor已实际观察到缺该helper的ImportError，
PaperMono未探测helper导入，可用性为UNKNOWN。两Paper fixture均显式使用公开
`machine.I2C.readfrom_mem+writeto_mem`。逐板核对内部bus/pins/地址与真实
`0x49: 0x2a→0x2d`、`0x4a`不变；500ms为识别窗，真实输入仍请求250ms，事件由原
`M5.update()/BtnPWR`消费。没有读取IRQ42/BTN_STATUS来抢占原API，也没有运行时fallback。
模型的I2C0/1共享slave bus，因此不授予物理pinmux/电气证明。

实际显示按各自控制器判据验收：普通LCD红帧；StopWatch亮度255及精确圆形mask；
PaperMono真实480×800半黑白EPD；PaperColor原生帧400×600、240000点全为B800，并以
同一不可变快照核对hash/count及display/source双新鲜序号。四个headless板型不虚构LCD帧，
其固定示例的RMT/灯阵等路径保持各自原断言。

## 清场和功能并发

本机最多两个功能guest并行，每个独立Chrome/VM/随机端口/输出；同板editor→buttons→extra
串行，全部工作台组后才执行固定示例。首次任意失败会停止新派发，并等待在跑同伴结束，
没有自动重试。此功能并发下的ready观测不是cold/warm性能样本。
每板首次Start到观察到ready的墙钟值另见[readiness-summary.json](readiness-summary.json)，
逐项绑定各自raw/Flash/profile。19个值全部为正有限数，来自最多两个功能guest并发；
不作跨板速度排名、同固件前后提速或独占性能基准，严格摘要的performance_validation保持NOT MEASURED。

每个case都核对真实normal-QMP exit0、零强制pthread回收、零engine fallback及CDP目标关闭。
包括CoreS3固定例复开，共62个VM实例、按独立case累计348个实际CDP Worker目标关闭。
19个editor、Stack body及20个fixed共40例记录了保留iframe时的nested围栏；
19个普通buttons与Card56共20例只有all-workers-before-context证据，
**nested-before-iframe为NOT CAPTURED**，不借其它case补齐。
父Node退出或调度器drain本身不是normal-QMP/CDP证明。

首次严格汇总走完全部验证后，仅因indent2 JSON超过64KiB拒绝输出；原collector SHA
`4d817ba34c385622d6839ad8b2de42f61dbce98cc0afbb296b6322a4864bff6d`和拒绝收据
SHA`91505f5e40dd5d292a796458ee27a74790338248502ae8937d0f5808fe0ec76f`保留。
后续collector SHA`cb3363a4655f042ee5c25a6d0a8873d7cc88486e59a53ff2d520bd0e28147c78`
只改紧凑JSON编码，没有删除字段、弱化校验或改写任何raw。

## 独立DOM/model-only边界检查

[dom-qa-summary.json](dom-qa-summary.json)保持原V5执行身份，10,395字节，SHA
`c41fa9c8e12eecd06b0d5bb89804b295a4ea70643ca6a184bed37049aaa7a35d`。
CoreS3在1440/1024/768/390四宽检查实际3D模型、溢出、编辑器边界、禁用状态及Tab焦点；
CardputerZero/StopWatch在1440/390检查不可运行或PM1应用范围文案，共8个场景。
未启动QEMU/固件Worker；这些是DOM/model-only证据，不能称V6新布局或guest执行。

首观察器误选strict picker中不存在的legacy PaperS3而超时，原FAIL及截图未覆盖；
随后根据实际38选项picker另验两个可见边界设备。修正观察器范围没有新增产品准入。
两轮自有Chrome/server均关闭；首轮final CDP scan未捕获，后轮实际为0，不补造首轮收据。

## 历史失败与未授予范围

旧失败保持各自日期、Flash/runtime/source身份：
[首次UART与CoreS3限定验收](../2026-11-04-browser-uiflow-workbench/README.md)、
[圆屏/默认PM1/Card finally](../2026-11-04-browser-input-acceptance/README.md)、
[PaperColor观察器](../2026-11-04-papercolor-frame-oracle/README.md)、
[Paper缺Python helper](../2026-11-04-paper-pm1-application/README.md)、
[StamPLC reset](../2026-11-04-stamplc-workbench-reset/README.md)、
[Cardputer OOB](../2026-11-04-cardputer-workbench-reset/README.md)与
[AtomS3Lite首次启动PIF](../2026-11-04-s3-workbench-execution-policy/README.md)。
R3–R7父FAIL均不能生成COMPLETE；后续限定策略通过不关闭原策略的C根因。

本轮不授予逐19板提速、重复cold/warm基准、长期稳定性、未知/其它固件、全模块/云端业务、
完整原厂联网菜单、V6正式HTTPS上线或物理RF/电源/电气/声学/光学/机械结论。
未准入或其它后端设备不继承这19板的浏览器运行资格。

## 复现

按[构建与部署指南](../../pages-deployment.md)重新source-build QEMU/LittleFS并strict导出，
再执行当前[完整gate](../../../platform/tests/test_public_qemu_admitted_boards.mjs)：

```sh
npm ci --prefix platform/tests
M5_PUBLIC_SITE="$PWD/.work/public-site" M5_PUBLIC_BASE_PATH=/showcase/ \
M5_PUBLIC_QEMU_OUT="$PWD/.work/public-all19" \
M5_WASM_CHROME="<system-Chrome-executable>" M5_WASM_GPU=hardware \
M5_QEMU_READY_TIMEOUT_MS=600000 M5_QEMU_GATE_PHASE=all M5_QEMU_GATE_DEVICES='' \
M5_QEMU_GATE_REQUIRE_ALL=1 M5_QEMU_GATE_WORKERS=1 \
node platform/tests/test_public_qemu_admitted_boards.mjs
```

默认及CI为1 worker；本机2 worker只作功能验收。新构建/源码/导出会产生自己的身份，
必须保存同轮原始输入/输出、帧、控制器及清场收据，不能追认成本文旧hash结果。
公开源码不依赖本机ignored raw；summary只保存可核对的大小、SHA与有界事实。
