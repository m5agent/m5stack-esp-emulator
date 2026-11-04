# S3工作台执行策略候选：首次启动PIF与待验边界

日期与最近核对：`2026-11-04`。原失败属于 **virtual-device validation**；
源码审查、反汇编和候选准备分别标注。结构化身份、工件字节数/SHA与清场收据见
[summary.json](summary.json)。**原AtomS3Lite启动PIF根因仍为OPEN。**
后续八板精确候选完成 **DIAGNOSTIC_PASS 17/17、656项检查**。本文只在终态后
核对原报告；80项静态检查、17例功能诊断和canonical完整60例是不同证据层级。
原根因登记为[RUNTIME-09 OPEN](../../runtime-model-gap-register.md)，不因候选通过关闭。

## 原R7首次失败

原全60例在16个已启动case中以15 PASS及AtomS3Lite FAIL终止，其余44例未运行。
AtomS3Lite只完成四项网页/UI检查，尚未到工作台ready，也没有执行用户program。
这是首次启动失败，不能写成硬件reset后的第二次启动失败。

原报告为28,744字节，SHA
`930501c55a9a08d5c20677fcb6d95f18d88f312a03b3e055943ec51fc84e5830`。
串口实际报告Core1 `LoadStorePIFAddrError`，PC为`0x403864c3`，
EXCVADDR为`0x6002306c`、EXCCAUSE为`0x0f`；记录到两次guest reset事件。
固件为组合后的精确工作台Flash
`5c06f621bd765980f8ac274760b5648df58f3828d647f9d13acf77fb4d9601e8`。
原profile为`atoms3-lite-wasm-wallclock`，board `m5atoms3lite`，divisor1，
无clock override、无显式`-icount`或`-accel`，`oneInsnPerTb=false`。

失败后的实际stop为normal-QMP=true、exitCode0、engine fallback0；
五个nested pthread归零，engine正常终止一次，self-close通知一次。
stop后的实际CDP检查确认六个Worker均已关闭、live0；保留iframe时的外部CDP
围栏为 **NOT CAPTURED**。正常清场不改变启动FAIL。

## 精确Flash反汇编与已实现的寄存器

本机已有8,388,608字节组合镜像，其全量SHA与原报告逐字一致。分区表中的
factory app起点为`0x10000`；包含故障PC的IRAM段起点为`0x40374000`，
长度109,028字节，SHA
`d4e871d37a8fd21eb2bf4eca7a675e4d3650969836087302dfc6c532d7f7953e`。
使用固定Xtensa objdump，从原始故障PC这个已知指令边界解码，未使用其他固件的
ELF或StamPLC指令字节：

```text
403864c3: 82271b  l32i  a8, a7, 108
403864c6: bd03    mov.n a11, a3
403864c8: 608820  or    a8, a8, a6
403864cb: c02000  memw
403864ce: 82671b  s32i  a8, a7, 108
```

故障指令是普通32位load，不是atomic/S32C1I。串口A7=`0x60023000`，
故有效地址为`0x60023000 + 0x6c`，四字节对齐且不跨页；之后OR使用的A6为2。
没有匹配ELF函数符号，本文不为该地址指定函数名。

精确75来源的头文件定义`0x6c = SYSTIMER_INT_CLR`；`TARGET1_CONF`位于另一
偏移`0x38`。AtomS3Lite继承共享ESP32-S3 SoC，SYSTIMER在`0x60023000`映射
256字节区域。generic `esp_systimer_read`对INT_CLR有显式case，返回初始值0；
对应write清除所选comparators的raw状态并更新IRQ。S3派生类只覆写write，
read仍使用generic方法。现有MemoryRegionOps和普通read dispatch接受这次
对齐四字节访问，普通read accessor在回调后返回MEMTX_OK。

七个相关源码文件已逐一核对runtime manifest的patched-file SHA或未修改的
固定QEMU Git blob，详细SHA在JSON中。这些事实说明该地址已有映射和实现，
**不能单凭异常地址判断控制器缺失或访问大小不支持**。当次实际MemoryRegion
选择、回调是否到达、CPU/TLB/TB状态与返回元数据尚未采集，因而根因仍开放。
generic MMIO/TB recompile也并非仅在icount下发生，不能由无icount排除它。

早前[StamPLC复位观察](../2026-11-04-stamplc-workbench-reset/README.md)涉及
`0x60023008`的UNIT1_OP，触发阶段、固件和字节均不同；
[Cardputer复位观察](../2026-11-04-cardputer-workbench-reset/README.md)是另一个
WASM OOB。本页不推定三者有共同C根因，也不关闭既有模型缺口。

## 八板精确执行策略preview

候选只为下列各自精确工作台Flash增加一个variant。共同约束为
`uiflow-workbench-v1`、`M5_UIFLOW_WORKBENCH_READY`和startup main.py SHA
`a109d9c11c09b4aa649e1a0a2d0929136fe7083f75bf2452e9c17b57f8b13ab0`。
相应profile后缀为`-wasm-uiflow-workbench-wallclock-oneinsn-candidate`，
clockDivisor仍为1，无新增icount，要求
`0027-gpio-bounded-transactions.patch`，SHA
`43685da86d9b959b2e769cd9cda5785a5c4039b5076f73f3b9d6033d1d161bdf`。
新增实际参数为`-accel tcg,thread=multi,one-insn-per-tb=on`。

| 设备 | 精确组合Flash SHA256 |
| --- | --- |
| StopWatch | `5a7fb2941c2dfa7b17ca57defa5ea857191e64daeb774d05da5cd427cd45fe2a` |
| StickS3 | `43855f0144edec8fafc4525ac6c8e30b01e2386d7b7f282ddb92833d792932fc` |
| AtomS3 | `8252177a41539523b8fcdd49c3d2bb0835c5087d76ab9cbe563051b44074e1ab` |
| AtomS3Lite | `5c06f621bd765980f8ac274760b5648df58f3828d647f9d13acf77fb4d9601e8` |
| AtomS3R | `babc0e35df7677a469e8829ac98eb465a6565d431182c0c6ff812df0c50be45a` |
| StackChan | `8ed58bd2c21ccb811fcef5ffbce902ebe3a8eea7cb005d641a4c3ecf54df0394` |
| PaperColor | `c4486aba3d494048a8dd9e464a610bce0d19369b51ae814f2f221ddc630b6b34` |
| PaperMono | `f03a6fccab31e3f3b1a3c83aabff6953f822744b5672e5b46df2ee7e57b5a9f0` |

准备收据为12,291字节，SHA
`2c5cceb7f439e88b5f206df70255c6628c4f545a1326de3781ae090b77231ecb`。
preview site manifest为
`dc722d4f6531e398368c2497c53551d0891d6330a2c00f8428aecc283bdf2c52`，
runtime仍为同一WASM
`96ea9f91956aa80926182ed174ea426f3f4c84e96ca58754fa249063fdda5ca1`。
八个preview admission为candidate，`publication_eligible=false`。
准备时canonical registry未改；functional新增行和仅供preview的准入变化分别保存，
后者不能被推广为公开准入。

准备层完成80项 **STATIC PASS / GUEST NOT RUN**：核对每板精确Flash/main/ready/
clock/补丁、未知Flash保留旧策略、旧fixed与已有variant不变、错误source/ready/
fixture或缺0027时拒绝，以及未选板不变。C、接线、Flash、runtime二进制、guest
时钟/WDT和原runner没有改动；其余导出资产逐字一致。这些都是准备层事实，
不是80次guest执行，也没有证明性能收益或根因修复。

## 17例功能诊断的实际结果

终态parent报告为18,443字节，SHA
`7658ce438c1797d110cf6b9730a7780184324449769c0441221ad31aed521bdb`，
状态为`DIAGNOSTIC_PASS`、`publication_eligible=false`，17例全部完成，first_failure
为空、NOT RUN为0。最多两个guest并行，只作功能诊断，不是性能样本。
各板先完整editor，再buttons，另跑StackChan独立三区body-touch：

| 设备 | editor检查 | buttons检查 / 键鼠trial |
| --- | ---: | ---: |
| StopWatch | 64 PASS | 19 PASS / 6 |
| StickS3 | 63 PASS | 19 PASS / 6 |
| AtomS3 | 63 PASS | 10 PASS / 2 |
| AtomS3Lite | 58 PASS | 10 PASS / 2 |
| AtomS3R | 63 PASS | 10 PASS / 2 |
| StackChan | 63 PASS | 10 PASS / 2 |
| PaperColor | 64 PASS | 23 PASS / 8 |
| PaperMono | 63 PASS | 19 PASS / 6 |

StackChan三区body-touch另完成35项、六个键鼠trial。总计656项检查，34个普通
button trial加六个body trial，均保留请求250ms。每例原报告的实际byte/SHA、
Flash/base、profile、执行源码SHA和清场引用逐项保存在JSON中。

八个editor均保留原断言：未改初始textarea的第一次及重复直接Run、UTF-8/
长源码/异常/恢复、暂停/继续、中断及硬件reset后新console再次执行源码。
有显示器的七板各执行12段program，AtomS3Lite执行11段、没有补假LCD检查。
三个原runner和provenance helper未修改；实际17例receipt均逐项匹配对应精确
variant的Flash/main/fixture/ready/0027、oneInsn=true、divisor1、无override/
无icount及显式TCG参数。独立actual-arguments收据为8,019字节，SHA
`5db3b5e1a77b0f591b74a1d1ca34c6159c41b8cc33f24154b7d91ca35216ed41`。

四块PM1板实际readback均为cfg49 `0x2a→0x2d`、cfg4a保持，窗口500ms而输入
仍为250ms。StopWatch/StickS3使用各自固件已有的官方driver公开API；两块Paper
显式使用公开machine.I2C寄存器RMW，没有import失败后的自动fallback。
这仍是[PM1应用配置](../2026-11-04-paper-pm1-application/README.md)，不能改写成
默认PM1模式通过，也不能由alias bus推定物理pinmux验证。

实际17例均normal-QMP exit0、零forced disposal/engine fallback，五个nested
pthread归零，engine正常终止与self-close各一次。八个editor和StackChan body
均捕获保留iframe及context关闭前两阶段外部CDP：每阶段六target关闭、live0。
八个buttons只有实际before-context六target关闭收据；held-iframe外部CDP为
**NOT CAPTURED**，不能继承另外九例的两阶段结果。

每个variant必须逐板匹配实际Flash、firmwareVariant、argv、runtime和clock，保留
实际输出/输入/帧及正常或fallback清场；StackChan另核三区原控制器/驱动。
这17例只授予各自精确策略路径。随后commit
`27f01487a99fab06e9d8429430401ea5b06859ca`仅应用八个functional精确行，
canonical registry SHA为
`0f0727d10e56811f6c99d45543eb48b60dd6642112dd3ab1e967bc3229448794`。
原19个public admission、未知固件、classic、旧fixed及原三个精确行保留，
没有推广preview-only准入元数据。

首轮host合同因旧StackChan仅dance白名单断言FAIL，原日志hash保留；后续白名单
精确纳入已实测的workbench `8ed58…`，Factory仍未放开，28个host合同命令通过。
它们不代表新guest执行。V6 canonical导出完成2,130项资产、251,195,290字节，
manifest SHA为
`e597ce3c4465f582928042d4a36be684454a9cb4f8910f80720ad027cf1da898`，
`publication_eligible=true`、candidate列表为空，仍用同一96ea WASM。
导出身份与先前publication=false的17例preview身份分别保留。

新canonical完整60例R8仍在运行，本页未读取active子报告，状态为 **PENDING**。
未知固件、多指令异常根因、长期稳定性、性能和线上部署也均不能由这17例授予。

本目录只包含有界文字/JSON和原工件byte/SHA，不含完整raw串口、二进制、完整frame、
机器路径、内部端点或会话/设备标识。导航、缺口登记与执行队列由当前authority
页面统一维护，本历史草稿不替代它们。
