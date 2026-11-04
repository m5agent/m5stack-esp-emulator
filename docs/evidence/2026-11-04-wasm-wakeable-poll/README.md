# WASM host poll 唤醒：两板原 Flash 冷启动证据

日期与最近核对：`2026-11-04`。执行层级：**virtual-device validation**。
结构化身份、原始工件的 byte/SHA 与复验入口见 [summary.json](summary.json)。

fresh75 在两个原固定示例上完成独立本地冷启动：Atom Matrix `15/15`、
原 StickC Plus `26/26`，实际输入/输出及正常两阶段 Worker 清理均通过。
相同原 Flash、icount 与时钟下，单次 click-to-ready 分别为 `54.775 s`
与 `39.144 s`。这些结果只覆盖下列两组固定示例。新默认 UIFlow 镜像、
其他型号、线上 Pages、重复性能分布与物理硬件不从本记录继承。

**本独立 cold 批次未测 warm。** [后续 Matrix75 V1 首组](warm-summary.json)
另有 cold-prime `53.491 s` → warm `76.480 s`，warm 更慢；余下三组仍为
`NOT RUN`，纯 cache 暖启动收益未建立。这不改写本轮 cold 事实。硬件 reset
保留当前 guest，不能代替新建 guest 的 stop/start 资产缓存实验。

## 来源与构建身份

运行时来源为本分支已本地提交的
`e0d0d7dde13fa582d5c27c85cce25ef62aeaf2f8`，固定示例 runner 与 V1 web
来源为 `4a2de458776396bac8c3a1aa8d98c22bf910f7fe`。
本轮执行的 22 个 web 源文件逐字 SHA 与后者一致。V1 源码、导出 manifest
及实际执行报告已冻结；之后的 StackChan 键盘别名和 V2 页面不进入此对照。
本记录不声称这些本地提交或新运行时已经部署。

| 身份 | 值 |
| --- | --- |
| 上游 QEMU | `40edccac415693c5130f91c01d84176ae6008566`，`esp-develop-9.2.2-20260417` |
| 补丁链 | 固定 75 层，其中 native 47 层；不是引用可变的原生补丁列表 |
| SDK | Emscripten `3.1.50` |
| source lock SHA256 | `68f9696628ca9ba30484a2c57487e41f11fe9ce5a51a273e573434b932f2f2c1` |
| 构建 recipe SHA256 | `e1bc8875a591e03f656db09d93fec7eba56b51dabff99aca63664ddbcce8291d` |
| fresh75 WASM | `96ea9f91956aa80926182ed174ea426f3f4c84e96ca58754fa249063fdda5ca1`，12,746,345 bytes |
| runtime manifest | `fa6b56048ec91d100cb4f2a15088ce77e313bd2e6e8ba083229826b258297c51` |
| V1 site manifest | `f012e1b344536c44bc97472688e49aedbb3f51f594fa1ea8637549996fc6a4d1` |
| corresponding source | `1de631cd82597f6477ebc1bb700274e44aeb2f1c093e8122dae07dcbb88683c6`，35,244,932 bytes |

构建 receipt 为 `PASS`、`all_objects_rebuilt=true`；所有 QEMU objects 在新
构建目录中重编译。实际链接审计记录 `-O3`、64 KiB main/pthread stacks、
`STACK_OVERFLOW_CHECK=2` 与首次链接 `--emit-symbol-map`。symbol map 只作为
该次 WASM 的本地 sidecar，未成为分发资产，也没有启用运行时 tracing。
构建器的 `guest_execution=NOT RUN` 与下文实际 guest 结果分别记录。

源码入口：[0032 补丁](../../../patches/qemu-wasm-probe/0032-wasm-wakeable-host-poll.patch)、
[source lock](../../../scripts/qemu-wasm-build/sources.lock.json)、
[源码构建说明](../../../scripts/qemu-wasm-build/README.md)。

## 变化与真实 SDK 控制

`0032` SHA256 为
`5a43ac91491e1d8637f0147e7165066940dc78a245ad3a6c733ba12968f30e7c`。
原 host poll 在真实 `g_poll(...,0)` 尚无事件时睡至最多 5 ms 的下一次轮询。
新路径在真实 EventNotifier 写入之后递增共享 epoch 并唤醒 futex；poll 先读
epoch，再真实 poll，随后 compare-wait。唤醒后仍由真实 poll 判定 readiness。
`EINTR` 重试，非 `EAGAIN` 写失败先返回；已有满 pipe 的 `EAGAIN` 可以唤醒。

低层 notifier 新增路径只有 atomic increment/futex wake，环境读取与
`pthread_once` 留在 poll 初始化。请求的 fallback 仍最多 5 ms；main-runtime
线程的请求等待片最多 1 ms，以继续服务代理调用。正 deadline 在处理 queued
calls 后重算。代码不改 QEMU guest clock、原 Flash、WDT 或 vCPU profile。
全局唤醒可能造成无关唤醒；32-bit epoch 完整绕回的 ABA 仍由有限 fallback
收敛。请求等待片上限不是宿主实时调度保证。

最终 v7 用真实 SDK 的 pipe、poll、pthread、代理调用与 futex，两个拓扑各以
**同一个编译产物**运行 old-poll 函数、`M5SW_POLL_WAKE=0` 和 wake 三条路径。
三种模式共享新 notifier 的 unconditional atomic/wake，因此 old-poll 模式
不是完整旧 QEMU 二进制。每 lane 24 次输入，真实 revents 与读出数据都要通过。

| SDK 拓扑 | old-poll median | env=0 median | wake median |
| --- | ---: | ---: | ---: |
| proxied pthread | 6.222 ms | 6.205 ms | 0.036 ms |
| Node main-runtime | 3.895 ms | 3.885 ms | 0.007 ms |

六组均 exit 0，正向状态 `PASS`。延迟从真实 write 返回后计至实际 readiness，
不含整个写入/代理操作耗时。它不是 guest 启动、CPU 使用率或物理 Flash 延迟。
Node main-runtime 也不覆盖 browser Window 的 futex 忙等分支。
probe 的 atomic read 使用更强的 SEQ_CST，QEMU 的 `qatomic_read` 为 RELAXED；
这一 shim 差异保留，未发现已证实的失败 race。

**pthread cancellation：NOT ESTABLISHED。** 前一版 v5/v6 的 original/wake
取消控制都保留 FAIL：proxied 线程超时；v6 Node main-runtime 未在 fallback 前
完成取消，真实 pipe fallback 后才观察到 cleanup、join 和 canceled status。
v5 的旧 observer 快照错误另列归因。v6 使用的是前一版 patch hash，最终 v7
只重跑正向，取消为 `NOT RUN`，总体仍为 `PARTIAL`。未扩修 SDK。
浏览器中的 QMP quit 与实际 Worker 清理由下列两个 guest 分别验证。

复验方法与限定：[真实 SDK 控制](../../../tests/browser-qemu/poll_wake/README.md)。

## 同原 Flash 冷启动

两设备全部使用原固定示例的完整 Flash，不使用新的网页编程启动镜像。

| 设备 | 完整 Flash SHA256 | profile |
| --- | --- | --- |
| Atom Matrix | `f028cf0bca868f48b9ae9b5e5c524c6c0fa3ef8d5d19b4e75ab829a78ecbd88b` | `atom-matrix-wasm-deterministic-icount` / `m5atommatrix` |
| 原 StickC Plus | `69567208e8c5a8ff3e2dbf07d85a724c85a3436e80c5ebce3d866c47464a5a6a` | `stickc-plus-wasm-deterministic-icount` / `m5stickcplus` |

实际参数保持 `tcg,thread=single,tb-size=128`、
`-icount shift=5,align=off,sleep=off`、`clockDivisor=1`、无 clock override、
`oneInsnPerTb=false`、`persistentFlash=false`。每轮新建 Chrome process/context，
实际 ANGLE Metal renderer；不启 Profiler。原始 15/26 断言均保留，额外 timing
observer 只做 call-through 资产、编译、状态、串口和输入时间记录。

| cold 设备 | 原正式基线 3c | 中间基线 74 | fresh75 | 相对 74 单次减少 | fresh75 原断言 |
| --- | ---: | ---: | ---: | ---: | ---: |
| Atom Matrix | 109.458 s | 113.164 s | 54.775 s | 51.60% | 15/15 PASS |
| 原 StickC Plus | 90.687 s | 96.755 s | 39.144 s | 59.54% | 26/26 PASS |

以上是 click-to-ready；runtime-to-ready 分别为 Matrix `54.190 s`、Plus
`38.701 s`。3c 指本调查使用的原正式发布包
`3c6b249002d83118e0ddcbd82e4ee6336223293b98566fc7709d5087d9df4567`；
74 是中间 fresh 栈
`2c72cda0858521b47e730f4d19ae4ba9de9d800d9568fa25d20d41dbd8de5d14`。
3c→75 还包含中间的栈、链接及 UART 变化，不能把全部差值归到一行补丁。
这些单次结果没有建立分布、长期保证或其他设备的收益。

UART 阶段从实际 runtime start 计时：

| fresh75 | ROM entry | first I2C log | UIFlow banner | runtime ready |
| --- | ---: | ---: | ---: | ---: |
| Matrix | 18.424 s | 26.637 s | 35.994 s | 54.190 s |
| Plus | 17.523 s | 25.607 s | 28.953 s | 38.701 s |

entry→first I2C 从中间 74 的 `62.668/58.810 s` 缩至 `8.213/8.085 s`。
这些是宿主接收 UART marker 的阶段时间，不是读请求次数或 guest 指令计数。
未把 CDP samples 或不覆盖此 cache 路径的零 blockstats 转成 I/O 次数。

Matrix 的真实 Space/USER down/up 使原 guest 依次报告 pressed、count=1、released；
GPIO27 RMT 解码的 25 个 uniform LEDs 从 `#204060` 变为 `#40a020` 再回到
`#204060`，QOM 与模型一致。无 LCD/frame 路由及只读/非法输入负控保留。
这不建立非均匀矩阵空间顺序、IMU、IR 或物理光学结论。

Plus 的真实 Space/BtnA 使 guest count=1 并报告 release；135×240 native
RGB565 marker 改变，渲染后的模型纹理逐像素比较 32,400 点通过。pause 冻结、
resume 新 heartbeat、非触摸屏负控及无 panic/traceback 通过。
**这个固定例没有验证 BtnB/Power。**

每个 fresh75 guest 均正常 QMP exit 0，4 pthread 与 engine 共 **5 个实际 CDP
Worker targets** 全部关闭、live=0、零 forced disposal/fallback。保留了 iframe
移除前的 nested-worker 围栏和移除后的全部 target 围栏；没有以 browser context
关闭替代 guest 正常清理。

## 历史失败与复验边界

[原启动调查](../2026-11-04-browser-startup-investigation/README.md)继续保留
Matrix MT+oneInsn 的 ready 前 cache panic、single/icount+oneInsn 的
`126.620 s` 无收益及后续 observer 心跳假设 FAIL。两次失败轮的正常 CDP 清理
未捕获，不能由本轮 PASS 补齐。旧 `0bd…` producer 路径测量已撤回其适用范围，
未进入本次 3c/74/75 比较。

原始报告、执行 harness 与完整构建/SDK 日志保留在源码证据树之外；公开摘要只列
byte/SHA 和必要数据，不收录会话/target 标识、机器路径或 raw frame/trace。
普通 checkout 不依赖这些原始工件。

在上述固定来源、已核验 runtime/Flash 的导出站点上，以下命令复验同路径功能。
使用新的 agent-owned 输出目录，`SITE`、`BASE`、`CHROME` 与输出变量由执行者
显式提供。源码构建与导出先按前述构建说明完成；不把新构建 hash 假定为相同。

```sh
M5_PUBLIC_SITE="$SITE" M5_PUBLIC_BASE_PATH="$BASE" M5_PUBLIC_UI=1 \
M5_WASM_GPU=hardware M5_WASM_CHROME="$CHROME" \
M5_QEMU_DEVICE=atom-matrix M5_PUBLIC_QEMU_OUT="$MATRIX_OUT" \
node platform/tests/test_public_qemu_headless_guest.mjs

M5_PUBLIC_SITE="$SITE" M5_PUBLIC_BASE_PATH="$BASE" M5_PUBLIC_UI=1 \
M5_WASM_GPU=hardware M5_WASM_CHROME="$CHROME" \
M5_QEMU_DEVICE=stickc-plus M5_PUBLIC_QEMU_OUT="$PLUS_OUT" \
node platform/tests/test_public_qemu_board_guest.mjs
```

这些 checked-in runner 复验功能门槛；记录中的毫秒值来自另存 SHA 的 timestamp
observer。可用[便携生成器](../../../tests/browser-qemu/startup_timing/README.md)重建该计时观测器；
路径归一后的完整脚本与已执行 75 产物相同，不增加新的 guest 结果。
性能复测需同时记录该 observer、实际缓存状态和运行环境。
本条记录不关闭 [UIFlow 浏览器设计](../../plans/2026-11-04-uiflow-browser-workbench-design.md)
中的全设备、新默认、完整按键、cold/warm 或部署验收。
