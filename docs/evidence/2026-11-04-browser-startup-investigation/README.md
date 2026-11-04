# Atom Matrix / StickC Plus 浏览器启动调查

日期：`2026-11-04`。类别：**browser virtual-device validation**。
总体 **PARTIAL**：已复现两款旧公开 UIFlow2 固定示例的慢启动，尚未接受新的优化。
物理硬件验证、完整按键覆盖、新默认工作台、全设备提速和新部署均不由本记录授予。

## 执行身份与范围

本轮使用上一轮正式发布的完整静态导出，在独占的本地静态服务器执行；不是新的
线上 HTTPS 延迟测量。每个独立案例使用全新 Chromium context、guest、Flash、
eFuse 和 Worker；浏览器采用系统 Chrome 与实际 Apple M4 Metal ANGLE，
未并发启动其他重型 guest 或构建。未改控制器、看门狗或固件内容来使测试通过。

| 身份 | SHA / 版本 |
| --- | --- |
| 固定 Web 源码 | `b41eba70eb61f7ddc5c41e0b981341064f9d1d1f`，22 个执行路径与导出逐项核对 |
| 原 producer 源码 | `1b86ed6f7edcc36deafc4834b45a28c6a6017c79` |
| QEMU 源码 | `40edccac415693c5130f91c01d84176ae6008566` |
| 站点 manifest | `c5991d737d4b20c4b1ae96b71587cec907a1e72f3c57fe2fee63c08e23daf323` |
| runtime manifest | `897114f09d5e0c695e44e665611fec4fa98aa62856cddce6eb1cbb906d21071c` |
| WASM | `3c6b249002d83118e0ddcbd82e4ee6336223293b98566fc7709d5087d9df4567`，12,745,460 bytes |
| 对应源码包 | `3bf6ee4fe907aff960ace53ae4622356345960055e0cb1cc1dee964ff6fc09b0` |

原发布来源与路径归一化边界见[上一轮交付记录](../2026-11-03-performance-pages-release/README.md)。
[summary.json](summary.json)保留 ROM、JS、Worker、source lock、配方与实际参数身份。

测试对象是公开路径原有的**合成固定示例**：基于官方 UIFlow2 基底保留原 C 固件，
在其 VFS 写入已审阅的 boot/main/config。它们不是未经修改的官方 launcher：

| 设备 | 固件 | 完整 Flash SHA-256 |
| --- | --- | --- |
| Atom Matrix C008-B | UIFlow2 v2.5.3，RGB/USER 固定示例 | `f028cf0bca868f48b9ae9b5e5c524c6c0fa3ef8d5d19b4e75ab829a78ecbd88b` |
| 原 StickC Plus K016-P | UIFlow2 v2.5.2，显示/BtnA 固定示例 | `69567208e8c5a8ff3e2dbf07d85a724c85a3436e80c5ebce3d866c47464a5a6a` |

所有候选继续使用各自相同的完整 Flash；没有换成更小的测试固件。上述结果不转授
Atom Matrix v1.1、StickC Plus SE/Plus2、stock menu 或任意上传固件。

## 同一运行时的基线

公开经典 ESP32 profile 使用 `clockDivisor=1`、
`tcg,thread=single,tb-size=128` 和 `icount shift=5,align=off,sleep=off`。
固定 icount 的虚拟时间不能按墙钟等价解释。

| 设备 | 点击至 ready UART | Runtime.start 至 ready | 首串口，自 Runtime.start | 功能检查 |
| --- | ---: | ---: | ---: | --- |
| Atom Matrix | 109.458 s | 108.890 s | 18.763 s | 15/15 |
| StickC Plus | 90.687 s | 90.506 s | 18.286 s | 26/26 |

每款只有一次未剖析的计时，不能给出延迟分布或速度保证。资产下载、编译和准备
与实际 guest 执行分开记录；本轮主要等待发生在 guest 开始之后。UART 阶段如下：

| 从 Runtime.start 起计 | Atom Matrix 基线 | StickC Plus 基线 | Atom Matrix，保留 icount，仅加 oneInsn |
| --- | ---: | ---: | ---: |
| ROM entry | 21.761 s | 21.377 s | 4.294 s |
| 首个 I2C 日志 | 84.218 s | 76.178 s | 57.034 s |
| UIFlow banner | 92.554 s | 81.783 s | 84.487 s |
| 固定 Python main begin | 108.040 s | 89.509 s | 125.517 s |
| ready UART | 108.890 s | 90.506 s | 126.351 s |

这组观测显示 oneInsn 的阶段收益不一致，不能仅用首串口或 ROM entry 宣称整体变快。

Atom Matrix 基线通过实际模型键盘绑定注入 USER 双边沿，guest 打印 pressed/count=1/
released，同一 guest 的 RMT/QOM 颜色和模型读回一致。Plus 基线验证的是 **BtnA**：
原驱动双边沿、计数、实际 framebuffer/模型纹理变化、暂停及恢复后的新心跳。
没有把它写成 B/Power 或全部按键通过。

两款基线均正常 Stop：guest exit 0、四个 pthread 与一个 engine 的实际 CDP target
在 iframe 移除前后两阶段清场，fallback 为零；页面与 guest 证据身份一致。

## 保留的候选失败

候选配置、schema 和参数构造的变化仅存在于 ignored 的独立诊断 source/site 副本，
`publication_eligible=false`。原 `3c` WASM、JS、Worker、ROM 和 Flash 均保持原字节。

### MTTCG + oneInsn：guest FAIL

Atom Matrix 的 exact-Flash 候选移除 icount，实际运行
`tcg,thread=multi,one-insn-per-tb=on`。在 ready 前发生：

```text
Cache disabled but cached memory region accessed
PC=0x40009a6e  EXCCAUSE=0x07  EXCVADDR=0x00000000
```

固件报告 ELF 前缀为 `939bab2ec`。首次失败保留；输入、稳态与 warm 阶段均 **NOT RUN**，
没有普通重试补齐。此现象不能证明具体的 cache 或调度根因，也不能继承 S3 的策略准入。

### single/icount5 + oneInsn：未见收益，观察器 FAIL

第二候选保留原 `thread=single,tb-size=128`、shift 5、divisor 1 与看门狗，
仅在实际参数中增加 `one-insn-per-tb=on`。点击至 ready 为 **126.620 s**，
本轮观测比 109.458 s 基线更慢，不构成优化交付。

实际键双边沿、count=1、RMT/QOM/模型读回及完整参数检查先通过；后续观察器错误要求
“8 秒墙钟内至少两次 2 秒虚拟心跳”，因此原报告保持 **FAIL**。实际是一个 ready、
零次心跳，没有观察到 panic 或重复启动。固定 icount 下的虚拟时长不能据此换算成墙钟；
这个失败属于观察器时序假设，不能直接判定固件 panic 或死锁。独立归因文件保留原报告哈希，
没有更改原 FAIL 或重新运行来取得 PASS。

这两个失败观察器在 finally 调用 Stop 后关闭 context，未保存失败轮的正常两阶段 CDP
清理结果，故该项均为 **NOT CAPTURED**。进程已结束、成功基线的清场，均不补成失败轮的
正常清场 PASS。后续观察器已补失败清理围栏，但没有追补本轮证据。

Plus 的同类候选及候选 warm 重复均 **NOT RUN**：Matrix 首次失败或无收益后让出 guest，
继续源码诊断和独立新构建验证。

## 20 秒独立 CDP 诊断

另开一个原 `3c` / 原 Flash / 原 icount profile 的 guest，从实际 QMP running 确认后
采集约 20 秒；不等待 application-ready、不注入按键。它是**有剖析开销的早启诊断**，
不计入上述未剖析计时，也不代表覆盖了后段 Python 导入。

Profiler 成功覆盖实际 engine 和全部四个 pthread。按同名叶帧合并后的主要观测：

| Worker | 样本数 | 主要叶帧 | 占该 Worker 样本 |
| --- | ---: | --- | ---: |
| engine | 15,994 | `(idle)` | 99.081% |
| pthread 1 | 15,999 | `wasm-function[2326]` | 99.925% |
| pthread 2 | 16,002 | `wasm-function[2326]` | 99.863% |
| pthread 3 | 16,001 | `wasm-function[2326]` | 99.344% |
| pthread 4 | 16,002 | `__emscripten_throw_longjmp` | 80.027% |

**这些比例和 timeDelta 累计不是 CPU 利用率，也不是每线程 CPU 时间。**
长时间保留同一采样栈的 Worker 可能处于等待，不能据此推断占用了三个核心；
`2326` 尚未解析为 C 符号。最后一个 pthread 的命名 JS longjmp、
`invoke_iii`、`doRewind`、`finishContextSwitch` 等祖先帧是非局部跳转/Asyncify
开销的调查线索，不能单独归因到 `cpu_io_recompile`、cooperative yield 或某个 helper。

该诊断正常 Stop 和两阶段实际 CDP target 清场通过，未用 context 关闭替代。
原始 profile 约 2.82 MB，只保留在 ignored 存储；本页和 JSON 仅记录摘要、哈希与尺寸。

## 符号与 trace 的验证边界

`3c` 无 function name section，关键索引也不能由导出表直接解析。以旧对象在独立输出及
独立 cache 中重放原链接，仅追加 `--emit-symbol-map`，生成
`qemu-system-xtensa.js.symbols`，格式为逐行 `function_index:function_name`。
原 SDK/source/build 未修改。

该链接产生 `c60dc0a8…`、12,745,464-byte WASM，**不是**原 `3c`。尽管只差四字节长度，
type/import/function/export/element/code section 均有索引排列差异，因此新 sidecar
**没有套用到原 3c profiler**；新二进制也未执行 guest。不能将它当作已获得精确 C 来源。

对实际 source/编译字符串的静态核查确认，已有 `M5_WASM_CSTACK_TRACE=1` 只保留
S3 cache write 与 fiber swap 前后的 stack phase 和每线程预算，不分类三种 CPU 退出原因。
classic Atom Matrix 不使用 S3 cache 实现。此轮未再开启 trace，也没有将静态阅读当作运行归因。
正在准备的 `0030` host 候选及后续新运行时必须另验，本文**不声称它已提速**。

## 撤回的旧运行时测量

最初误选了上一轮旧性能目录中的 `0bd94787…` 运行时。该包已因 producer 路径问题撤回。
其 Matrix 102.001 s、Plus 87.904 s 基线和 Matrix plain-MTTCG 62.503 s 轮次保留原始报告，
另标 `DIAGNOSTIC_OLD_RUNTIME_SUPERSEDED`；不能作为当前 Pages 或后续新构建的验证。
本记录的两款正式基线均已在正确的 `3c` 重新执行，未混用这些旧数字。

## 复现入口与证据保留

先在固定 `b41eba70…` 的隔离 checkout，按[Pages 构建与验收](../../pages-deployment.md)
准备对应的完整静态导出，核对上面的 manifest、`3c` WASM 与完整 Flash 身份。
换用另一个源码构建 hash 必须另验。公开仓库中的原功能路径可这样重跑，输出目录须新建：

```sh
M5_PUBLIC_SITE="$PWD/.work/repro-startup-site" \
M5_PUBLIC_BASE_PATH=/m5stack-esp-emulator/ \
M5_PUBLIC_QEMU_OUT="$PWD/.work/repro-atom-matrix" \
M5_QEMU_DEVICE=atom-matrix M5_PUBLIC_UI=1 M5_WASM_GPU=hardware \
M5_WASM_CHROME="/Applications/Google Chrome.app/Contents/MacOS/Google Chrome" \
node platform/tests/test_public_qemu_headless_guest.mjs

M5_PUBLIC_SITE="$PWD/.work/repro-startup-site" \
M5_PUBLIC_BASE_PATH=/m5stack-esp-emulator/ \
M5_PUBLIC_QEMU_OUT="$PWD/.work/repro-stickc-plus" \
M5_QEMU_DEVICE=stickc-plus M5_PUBLIC_UI=1 M5_WASM_GPU=hardware \
M5_WASM_CHROME="/Applications/Google Chrome.app/Contents/MacOS/Google Chrome" \
node platform/tests/test_public_qemu_board_guest.mjs
```

计时/CDP 轮次使用原功能验收器的本地只读 observer：记录 click、Runtime.start、资产/编译、
UART、状态、实际输入和 cleanup，Profiler 逐个 attach engine/pthread。执行脚本快照及 raw
报告均按 [summary.json](summary.json) 中的哈希/尺寸保留；这些 ignored 观察器未随源码分发，
上面原入口不会自行输出附加计时/profile。它们不是 fresh-clone 必需检查。

没有提交 Flash、ROM、trace 全文、私有路径、进程标识或帧序列。后续仍需实际新运行时、
新默认 UIFlow 镜像、每个设备的按键和代码工作台分别取证；本调查不关闭这些工作。
