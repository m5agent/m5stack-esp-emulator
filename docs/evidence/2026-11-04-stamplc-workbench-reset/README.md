# StamPLC 工作台复位：精确执行策略与未关闭缺口

日期与最近核对：`2026-11-04`。执行层级：**virtual-device validation**。
原始工件的字节数、SHA256、实际参数、指令解码与清场收据见
[summary.json](summary.json)。本记录保留原多指令 TB 首次失败，并记录同一
Flash、runtime 和时钟下 oneInsn 策略的单次完整通过；**C/复位事务根因仍未确定**。

## 首次失败与策略对照

| 项目 | 原始 profile | 精确工作台策略 |
| --- | --- | --- |
| profile | `stamplc-wasm-wallclock` | `stamplc-wasm-uiflow-workbench-wallclock-oneinsn-candidate` |
| clockDivisor / override | `1` / 无 | `1` / 无 |
| icount | 无 | 无 |
| oneInsnPerTb | `false` | `true` |
| 显式 accelerator | 无 | `tcg,thread=multi,one-insn-per-tb=on` |
| guest 结果 | 首次 reset 后 PIF；此前44项已完成检查均通过 | 首次实际 guest `54/54 PASS`，无实际 guest 重试 |
| 清场 | normal QMP exit0、0强制/兜底终止，6实际CDP Worker关闭 | normal QMP exit0、0强制/兜底终止，6实际CDP Worker关闭 |

原始 run 首启到ready为13.156秒，九段编辑器程序、UTF-8/长源码、异常/导入、
暂停/继续/中断和红帧均已通过。硬件QMP `system_reset` 进入新console epoch后，
第二次启动发生Core1 `LoadStorePIFAddrError`，PC `0x4038a83a`、
EXCVADDR `0x60023008`，随后产生guest reset。它使当轮60项矩阵在20个已执行
case中以19 PASS、该case FAIL停止，不能写成完整60 PASS。

策略对照通过完整编辑器路径，包括硬件reset、旧程序取消、新console epoch
和再次执行源码。红帧为240×135、32400个红像素，像素SHA为
`01b2284e114ce1e4b8a1b456c523399f29d67800fd696bb4f2f8ad57fb21ee00`。
候选首启ready4.844秒只是单次功能观察，不是受控重复性能结论。

原失败留有事后真实normal-QMP元数据和六CDP在context关闭前消失的证据，
before-iframe两阶段CDP为 **NOT CAPTURED**。候选另外观察到五pthread在iframe
仍被保留时已关闭，之后全部六CDP关闭。两者收据不互相补齐。

## 精确身份与策略范围

| 身份 | SHA256 / 值 |
| --- | --- |
| 原官方base Flash | `ab684b9d79d5fc5527be9450c18bee46171ae1b93716492be8aeeede50511470` |
| 组成后的工作台 Flash | `0b2b9b4f69dba03a7f764499555bdbf5d2e608c9c1c6496369e8d520186fcb5d` |
| startup main.py | `a109d9c11c09b4aa649e1a0a2d0929136fe7083f75bf2452e9c17b57f8b13ab0` |
| runtime75 WASM | `96ea9f91956aa80926182ed174ea426f3f4c84e96ca58754fa249063fdda5ca1` |
| runtime manifest | `fa6b56048ec91d100cb4f2a15088ce77e313bd2e6e8ba083229826b258297c51` |
| 原V2 site manifest | `6376236fddb33ca0f242253b5fbd48a186a6d116ae36718b2cf9406ded45eb3e` |
| preview site manifest | `99afa5cb1a11ca10ed0854d17bc2eb1fe5ad06356e3bfa1c67e1bb084fc69a16` |
| 原/候选实际 runner | `b417ca05de7baf6465e44ad38c1ccbc84d903142ffdd6e319e067080473bd010` |
| required runtime patch | `0027-gpio-bounded-transactions.patch` / `43685da86d9b959b2e769cd9cda5785a5c4039b5076f73f3b9d6033d1d161bdf` |

精确策略同时绑定上述Flash、`uiflow-workbench-v1`、ready marker、startup源和
required patch，不是整个StamPLC型号或未知上传镜像的通用执行开关。
Flash、runtime二进制、控制器/板级接线、时钟及WDT未改；命令行因显式
accelerator/oneInsn而不同，不能称为相同参数。TCG仍是同一QEMU执行器。

preview为避免误授发布而暂标candidate，`publication_eligible=false`。
该次执行从独立源快照导出，所有其它导出资产不变、不共享可写inode。
通过后只把完全一致的功能variant加入canonical registry，保留原public admission；
preview发布元数据没有一起提升。此记录中的新canonical导出/全矩阵仍是
**NOT RUN**，由后续独立run追加结果；本记录不授线上Pages或其它固件通过。

## 地址、真实指令与只读源码证据

`DR_REG_SYSTIMER_BASE=0x60023000`，offset `0x08`为
`SYSTIMER_UNIT1_OP`，UPDATE为bit30。runtime75已把真实SYSTIMER MMIO映射到
该地址，原read/write实现明确处理offset8，没有根据timer状态拒绝普通读写的门控。
因此不能把这次异常描述为缺少控制器或该寄存器未实现。

从**同一精确Flash**提取的IRAM段为109028字节，VMA `0x40374000`，
SHA `ce71bf174b15da6ba74ba06f521c34c414f33bb6e8be8a38ce1fa5985af9cf96`。
实际Xtensa objdump解码PC `0x4038a83a`的字节`88 19`为
`l32i.n a8,a9,4`。panic的A9=`0x60023004`，所以这是对齐、不跨页的
32位普通读，实际地址`0x60023008`；前条是`memw`，随后序列OR bit30、
写回同地址并轮询bit29。它不是atomic/S32C1I，也没有用不匹配ELF命名函数。
固件内嵌ELF摘要不是可用的matching ELF，函数符号仍未建立。

通用CPU reset会清`mem_io_pc`、icount字段、异常和`cflags_next_tb`，并把
`can_do_io`设为true；Xtensa reset调用父reset并重置MMU。本lane无icount，
不能套用icount专属IRQ guard假说。**通用MMIO重编译和多指令TB末条I/O许可
仍适用于wallclock**，不能因无icount就排除该路径。普通TCI load把当前TB返回
指针直接传给memory helper；当前静态证据不能证明这个元数据、TLB或事务来源错误。

只读审查另记录了SYSTIMER counter保留、comparator定时器metadata复制，以及
RTC/CPU1 reset/stall处理边界。这些是实际源码行为，不是已证明的异常原因。
原失败的内存事务结果、实际命中region、TLB/CPU1 reset时序仍缺动态观测。

## 观察器失败、复验入口与缺口关闭条件

preview准备时有一次metadata allowlist错误、两次输出目录断言/父目录错误，
均在browser/guest创建前终止；原记录和byte/SHA保留在summary，不能计作guest
失败重试，也不能隐去。更正后只有一次实际候选guest，完整54项通过。

在已校验的精确导出和独立新输出目录中执行
[标准工作台runner](../../../platform/tests/test_public_uiflow_guest.mjs)，例如：

```sh
M5_PUBLIC_SITE="$SITE" M5_QEMU_DEVICE=stamplc M5_UIFLOW_SMOKE_ONLY=0 \
M5_WASM_CHROME="$CHROME" M5_PUBLIC_QEMU_OUT="$NEW_OUT" \
node platform/tests/test_public_uiflow_guest.mjs
```

原无oneInsn失败的复现必须使用记录的旧profile/源/导出身份，不能以新策略的
PASS代替。准备工具的本地raw及二进制不提交，也不是普通checkout测试的前置条件。

[RUNTIME-07](../../runtime-model-gap-register.md#runtime-07stamplc-浏览器多指令-tb-下硬件复位后-pif-异常)
继续OPEN：需要同固件原策略的复现和受控reset-before/after-program对照，采集
实际MMIO transaction/MemTxResult、region、TLB、指令恢复元数据和CPU1复位/中断
顺序，再验证真正修复及受影响回归。其它Flash/main.py/profile必须单独立证；
这次精确策略PASS不关闭广义模型缺口，也不允许跳过reset阶段。
