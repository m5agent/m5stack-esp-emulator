# Cardputer工作台硬复位：原OOB与限定策略观察

日期与最近核对：`2026-11-04`。执行层级：**virtual-device validation**。
结构化身份、原始工件字节数/SHA和清场收据见[summary.json](summary.json)。
**原R4复位后的WASM OOB根因仍为OPEN。** 后续原策略诊断和精确oneInsn候选各自
通过限定检查，不能覆盖首次FAIL，也不能证明全60例、复位稳定性或模型根因已修复。

## 首次失败与后续观察

| 路径 | 实际结果 | 例外与边界 |
| --- | --- | --- |
| R4原完整编辑器、多指令TB | 44项已完成检查均通过，硬件reset后第二次启动OOB | normal-QMP=false、engine fallback1；六CDP关闭不等于正常guest退出 |
| 独占原策略、首版Worker异常观察器 | 原完整54项通过 | 未等待内层Runtime/Debugger ACK；事件0不能证明无异常 |
| 独占原策略、首版观察器stress | 126项通过，原reset之外再完成12次reset | 同样缺少每target内层ACK；不能关闭原失败 |
| ACK配对Cardputer原策略 | 126项通过，共13次reset | 每次之前六target三类ACK；未采到异常事件；Debugger改变时序 |
| ACK配对CoreS3 companion | 126项通过，共13次reset | 独立固件/profile，只作功能负载伴随，不向Cardputer转移结果 |
| 精确oneInsn preview、未改原runner | 原完整 `54/54 PASS` | 单次功能观察；原策略诊断也曾通过，根因继续OPEN |
| 精确候选ACK-stress | 126项通过，共13次reset | 实际ACK围栏/异常计数另存；原多指令OOB仍未关闭 |

R4原始报告为1,705,609字节，SHA
`a369b601cecf52ae9ae4243ae0ad315ed18eeca475451341f0eb3bb024bcac2e`。
首次启动、九段编辑器源码、红帧和中断等44项检查已经通过；实际主机QMP
`system_reset`后，在等待新console启动时报告
`Uncaught RuntimeError: memory access out of bounds`。
当轮全60例在7个已启动case中以6 PASS和该FAIL终止，剩余case没有获准通过。

失败后的实际stop收据为normal-QMP=false、exitCode未知、engine fallback1；
没有正常nested-worker退出/显式disposal收据。六个实际CDP Worker最终全部关闭，
保留iframe时的CDP围栏为 **NOT CAPTURED**。因此清理不能描述为graceful PASS。
原报告没有足以定位C/TCG/内存事务的已确认Worker异常栈，本文不推定具体函数根因。

## 精确固件与执行策略

| 身份 | SHA256 / 值 |
| --- | --- |
| 官方base Flash | `38b308769e35fe3393bde711e67d27403c32166cf62c10951c19d684fdb38631` |
| 组合后的工作台Flash | `b6255f6af5ad10236380eae09a76b44ca174b5c4de391aef16413bdc590952bd` |
| startup main.py | `a109d9c11c09b4aa649e1a0a2d0929136fe7083f75bf2452e9c17b57f8b13ab0` |
| runtime75 WASM | `96ea9f91956aa80926182ed174ea426f3f4c84e96ca58754fa249063fdda5ca1` |
| runtime manifest | `fa6b56048ec91d100cb4f2a15088ce77e313bd2e6e8ba083229826b258297c51` |
| 原V4 site manifest | `772f9e8618a6d32fa8f44981734bcfe1f1dd3a77f6bf834a61c8d5f971420f6f` |
| preview site manifest | `371c7711ae8c9e28624b29c0e73a73c907959d54e9492ba922f68b31f96c11bb` |
| 未修改完整runner | `b417ca05de7baf6465e44ad38c1ccbc84d903142ffdd6e319e067080473bd010` |

原profile为`cardputer-adv-wasm-wallclock`，board `m5cardputeradv`，
clockDivisor1、无clock override、无icount、`oneInsnPerTb=false`，未显式指定
accelerator。后续原策略诊断保持同Flash、WASM和该执行配置；增加的CDP观察器
属于测量路径差异，不能称为干净性能样本。

候选只为完全匹配的Flash、`uiflow-workbench-v1`、ready marker和startup源码
绑定`cardputer-adv-wasm-uiflow-workbench-wallclock-oneinsn-candidate`。
它使用`tcg,thread=multi,one-insn-per-tb=on`，divisor仍为1，无icount，要求原
`0027-gpio-bounded-transactions.patch`；GPIO0的`0029`输入补丁要求保持。
准备阶段只转换registry与preview准入元数据，其余导出资产逐字相同、没有共享
可写inode；C、runtime二进制、Flash、控制器接线、guest时钟和WDT均未改。
preview的`publication_eligible=false`，不能由准备或单次运行推定已部署。

## 首版异常观察器的证据缺口

独占首轮诊断保留原54项检查，报告SHA为
`fbe7c2a80a4342a71d705492f6e72b80a3ed1f87c1452395725ea40cd213606d`。
独占stress保留原检查，并加12轮“源码运行中硬复位、重新ready、新console再
执行源码”，126项通过，报告SHA为
`357ce38f922258a9cf1293af85c9f4bab01a5f8aee60fe5b619103d2c3ebddad`。
两次均正常QMP exit0、零强制/兜底终止，保留iframe时和最终context关闭前
两阶段CDP检查通过。它们是分别成立的诊断观察，原R4失败没有被替换。

首版观察器为六个真实Worker建立了session，并向内层发送`Runtime.enable`；
stress还发送Debugger配置。但它只等待`Target.sendMessageToTarget`的外层
递送响应，没有要求每个target返回内层`{id,result/error}`后才进行reset。
因此两次报告的events=0、capture_errors=0不能证明完整异常观察已就绪，更不能
作为“异常不存在”的依据。54/126项程序检查与该异常取证缺口分开记录。

## 真实tiny-WASM控制与ACK修正

新的独立观察器在每个被研究reset之前，要求所有六个实际Worker返回内层
`Runtime.enable`、`Debugger.enable`和`Debugger.setPauseOnExceptions`响应。
遇到`Debugger.paused`先保留原callframes，再立即恢复同target，并等待内层
`Debugger.resume` ACK。该观察器不改变guest值、源码、Flash或控制器。

观察器先接受一个独立浏览器控制：真实48字节WebAssembly模块在dummy Worker
内执行越界load。它不是QEMU或固件guest。首个控制确实捕获到一次
`Debugger.paused`和一次`Runtime.exceptionThrown`，resume也已ACK，但断言要求
callFrame本身的URL以wasm开头；实际该URL为空，因而保留 **FAIL**。
首报告为11,705字节、SHA
`e8b289dc0244da882ae44bc7bfdc88235c9eb89e22b4e6fbc5c0be11c173e402`。

v2按callFrame的`location.scriptId`关联已捕获的`Debugger.scriptParsed`，确认
`scriptLanguage=WebAssembly`，保留真实OOB、paused、resume-ACK要求；控制通过，
显式dummy清理后live Workers为0。v2报告为11,406字节、SHA
`0170b2fb0604e33fba9dc5ee04bb25db7bb472635fee9daa5af21a6d5150e098`。
两份控制都标`guest_execution=NOT RUN`：它们验证观察器，不能描述为复现了
Cardputer复位根因或修复了QEMU内存错误。

## ACK配对原策略诊断

两台独立浏览器VM作为明确的并行功能负载，分别执行Cardputer和CoreS3 companion。
每台均通过126项检查、原完整run的1次reset及12次额外reset，共13次。
每次reset前都检查六个实际target的三类内层ACK状态，13个ready围栏均满足要求。
观察器在每个Worker session建立时只初始化一次：每台每类有6个不同的实际命令
ACK，共18个；各围栏复用这些已确认、仍存活session的响应。13×6=78表示每类的
target围栏核验记录，不能当成78个不同命令的ACK。

| VM | 原始报告字节数 | SHA256 |
| --- | ---: | --- |
| Cardputer原策略 | 2,376,315 | `f0ee70cbda1629ce4e44b067c96d99756069e9a16152af3b792ad780eb099d05` |
| CoreS3 companion | 5,308,914 | `d1ff94986dd5916472b005057e9f89ce962c3e459223b056766e94d778aabbbe` |

两台均记录0个异常事件、0 protocol errors、0 capture errors；这只表示该次
已确认就绪的观察窗口未采到异常。实际均正常QMP退出、零兜底终止，保留iframe
时及context关闭前的CDP检查通过。CoreS3使用自己的Flash与已绑定oneInsn工作台
profile，摘要单独列明；其结果不会成为Cardputer的固件或原策略通过证据。
Debugger与ACK观察可扰动调度，未复现不证明并发无风险，原R4根因继续开放。

## 精确候选的未修改编辑器结果

候选随后用**未修改的原b417 runner、无额外Debugger观察器**完成54项完整编辑器
检查，包括原硬件reset后的新console、再次执行源码及正常清场。
报告为2,234,683字节，SHA
`aa5d437dbdc42d274067de7fc3643bae567236b2ca68bf5c12bf2d37047a13cb`。
实际normal-QMP exit0、五pthread与engine共六个实际CDP Worker关闭，零强制
disposal与零engine fallback，保留iframe时及最终context关闭前两阶段围栏通过。

单次click-to-ready为4.8405秒，属于本次功能观察，不是重复性能基准。
原策略的独占诊断和ACK配对诊断此前也通过，因此当前事实不是确定的“原策略
必败、候选必胜”对照。候选通过只限定于记录的Flash/main/profile/required-patch；
原多指令复位OOB的C、TCG、TLB或CPU复位事务根因仍未建立。

候选额外12轮ACK-stress随后独立终态通过：原54项和额外72项共126项、原1次加
额外12次共13次reset。额外轮次console epoch从1推进到13，每轮增加1。
13个围栏均核实六个实际target三类ACK，每类6个不同命令的ACK，未采到异常事件，
protocol/capture errors均为0。其source为生成的ACK-stress入口，SHA
`a52c02242aa247afe3197ad97efc2625dfbb7d9fbbce255cd02189016e2fdb34`，
保留原54项并增加诊断；不能把它冒充未修改的b417。共享ACK辅助源码SHA为
`6db52788d336d68df97118c1a23891bba2d6e076706ed3a9f618dd63e101b924`。
该报告为2,380,207字节，SHA
`82d8ae3afa102e95df89fe9981a275a550a59ce2fa2eda0d758146419e7550fc`。
实际normal-QMP exit0、零兜底终止、两阶段六CDP清场通过。该诊断也有Debugger
时序扰动，独立未复现不能被因果归功于oneInsn。

## 精确功能策略进入canonical registry

完成上述实际候选结果后，只把功能variant加入canonical registry，SHA由
`40549688154e2489a8809ba4f7278388b52b00d509a8a5256bdbcd6b36562e9c`
变为`150be972fc4f53c1dbbe7ad052d80f878dd4a01d6100ce292c5b51ec189bbbe4`。
语义差异仅为Cardputer增加一条绑定完整Flash/main/fixture/ready marker/0027的
`firmwareProfiles`记录。原public admission和0029输入要求不变，其它板与未知
Flash的原profile保持；preview准入/发布元数据没有提升。profile名称里的
candidate后缀保留实际执行身份，不改变原public板级准入。

新增绑定的host正/负控通过由根代理记录，本文未重跑。该源配置推广表示**精确
工作台执行策略的限定功能验收**；推广后的完整60例或线上部署未由本记录验证。
原多指令profile、未知Flash、Cardputer整体稳定性和C复位根因均未获通用修复结论。

## 复验与关闭条件

标准完整编辑器入口如下，需使用记录的原V4或精确preview导出、同一默认Flash、
Chrome/Playwright和全新ignored输出：

```sh
M5_PUBLIC_SITE="$SITE" M5_QEMU_DEVICE=cardputer-adv \
M5_UIFLOW_SMOKE_ONLY=0 M5_PUBLIC_QEMU_OUT="$NEW_OUT" \
M5_WASM_CHROME="$CHROME" node platform/tests/test_public_uiflow_guest.mjs
```

诊断版本保留原54项和normal-QMP/CDP收场，再增加逐Worker异常观察或12轮reset。
公开摘要只保留其准确source SHA与复验步骤；历史raw、源快照、二进制和完整CDP
响应不进入源码Git，普通checkout检查不依赖这些本机工件。

[RUNTIME-08 OPEN](../../runtime-model-gap-register.md#runtime-08cardputer-工作台硬件复位后-wasm-越界)
的关闭条件包括：同精确原策略的受控reset-before/after-
program与负载对照、每次reset前实际内层ACK、陷阱时对应的精确WASM/module/
script映射与原callframes、reset/console顺序，以及真正修改后的完整编辑器和
受影响回归。若要归因具体C/TCG/TLB路径，须绑定同次链接symbol map及动态状态
证据。独立精确策略PASS本身不关闭原模型根因；其它Flash/profile仍须单独立证。

[输入验收记录](../2026-11-04-browser-input-acceptance/README.md)中的独立V4
516项/112输入只覆盖原56键IRQ和单中断finally清理。该结果与本文完整编辑器
硬复位是不同验收范围。全60例、任意应用、线上Pages和物理硬件均不从本文继承。
