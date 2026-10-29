# 剩余 Xtensa 板型的浏览器接入

日期：2026-10-29。用户确认 PR #19 已合并，要求先同步主线，再继续其他设备的浏览器使用。

## 目标与约束

从 `origin/main@ee15f7614f822dce7178188a89d57a0333b71f2a` 开始，复用已验证的源码构建 WASM，处理剩余六个已编译候选：StopWatch、Cardputer-ADV、StamPLC、StackChan、PaperColor、PaperMono。保持既有四板与两种 CoreS3 示例兼容；原生结果不授予浏览器准入，编译成功也不授予准入。

独立 worktree、独立分支与静态测试端口。用户主 checkout、8787/8830 服务和无关会话保持不动。ROM/Flash/WASM/原始帧与完整运行日志不进源码 Git。公开部署仍由管理员在原仓库执行，延续已授权的验证后 PR 交付。

## 执行与验收

1. 核对最新主线、官方固件/ROM/eFuse、实际分区、原客体驱动和板型输入；保留主线新增修复。
2. 逐板组合固定源码，独立 Python 与浏览器 LittleFS 都验证完整 Flash SHA、原文件保留、VFS 外字节不变及写后重挂载读取；禁止任意源码路径和格式化。
3. 以正常虚拟时钟测试真实固件；Cardputer 使用原矩阵键盘路径，电子纸使用实际面板颜色和刷新 oracle，不用主机假图或慢放掩盖错误。
4. 实际公众 UI 选择→本地组合→真实屏幕→板级输入 press/release→同 guest 串口/像素变化→暂停恢复→自然退出与 Worker/iframe 清理。不能通过的设备保留 candidate，并记录精确阻断和下一验收条件。
5. 候选验证与公开准入分开，冻结实现后导出公开站并按所有已准入板型/示例执行发布门禁；变化范围决定回归范围，不跨板继承。
6. 平台/Node/生成器及 scope 检查完成后更新权威状态/Backlog/台账、归档原始证据并提交后续 PR。C6 RISC-V、P4 和 Linux ARM64 继续按独立目标列出，不凭 Xtensa 结果宣布支持。

## 进展

已确认 PR #19 合并并同步 main。六板初始固定源码均通过独立 Python
组合和真实 Chrome LittleFS 重挂载验证，30 个错误输入负控均被拒绝；
这些结果不授予 guest 准入。五个新增模型的真实浏览器桥接检查通过。

Cardputer 的 QAPI 字母枚举按扫描码排列，旧范围运算导致若干键错误或丢失。
新增 `0016` 用明确的物理矩阵表修复原控制器路径，3 项 C 重放测试覆盖
204 个控制，旧 preimage 负控必须失败。44 层固定源码已完整重建，
WASM SHA256 为 `c58d4316abfe4443f7b008179ae5fb9c8d873539944f57ea374c55d2cb4b22a0`；
最终准入须重跑此 runtime，不能继承旧 43 层产物的执行结果。

StopWatch 增加圆内 marker，并分别核对逻辑 468² 和实际面板 466²；
StamPLC 使用原固件 landscape rotation。两款电子纸使用公开 SDK 的
`startWrite/endWrite` 自动提交刷新，不调用不存在的 `display/waitDisplay`。
电子纸使用原 `UART0/dupterm` 配置接出默认 USB console，Cardputer 同样以
rotation 1 取得 240×135 的真实 ready。两板 EPD 和 Cardputer 新组合重新通过
Chrome 包装检查。QUALITY 模式按固定官方算法产生抖色，验收用独立源码
推导的逐像素 pattern，不能假设色块或黑色 marker 完全均匀。

旧 C runtime 的 `txbuf=0` 与 ringbuf 串口单变量对照均未关闭 WDT，保留失败。
进一步实际 C 函数控制确认 systimer 对迟到周期反复安排过去的 deadline；
已在保留原 counter/IRQ/周期相位的前提下完成仅 WASM 周期 deadline 修复，45 层固定源码全部重建；
实际 C old/WASM/native 控制验证迟到双比较器的回调从 102 降为 2。新 WASM SHA 为
`762535a63ff61fa8ba1cc1dcf154e791e1cc3e4550bb797d17e97fb2296404e0`。
该模型修复单独仍未关闭浏览器 WDT；新 runtime 首轮保留三板 UART/FIFO WDT 失败。

工作期间再次同步 main 至 `cb689891`，保留原生 ESP-NOW CCMP/replay 更新；
浏览器固定源码没有继承该网络路径的执行结果。

再次同步主线至 `2f048c9f`，未改动用户主 checkout。PaperMono 固定示例改用官方
`getTouchPointRaw(0)` 做 portrait 命中，原 `getX/getY` 校准缺口仍开放；精确
Flash `2b731175…02f70` 的原始浏览器检查通过，新专项门禁仍需重新执行。

同 Flash/正常时钟对照中，Metal 路径通过而 SwiftShader 主线程路径仍失败。
把 QEMU factory、MEMFS 和原 direct-UART 移到 module DedicatedWorker 后，
SwiftShader 的 StackChan 三次输入、90 秒持续运行、暂停恢复和实际 6 个
DedicatedWorker 退出均通过；iframe 保留到观察到实际 close，未用 iframe
销毁掩盖退出。该结果只关闭这个固定应用/运行时的控制，不跨板授予准入。
当前集成方案正在执行六候选与既有公开板型的独立回归。

集成后的 45 层 Worker 回归：StamPLC、StackChan、PaperMono、PaperColor、
StopWatch 均通过；PaperMono 新 raw 专项与逐像素纹理读回、移除 iframe 前
的实际六 Worker 关闭也通过。Cardputer 在多键序列中保留一次 N 松开未交付
失败：QMP release 已确认，guest heartbeat 仍保留按下状态，不能授予准入。

TI SCPS215G 说明 CFG0 的未读 FIFO 必须保留 K_INT，最后 FIFO pop 也不能
自行解除锁存中断。`0018` 修复该寄存器/IRQ 语义；5 项 actual-C old/new
控制及无缓存复验通过，CFG1 旧行为保持且 50 µs 脉冲不在支持范围。46 层
固定源码正在完整重建，最终客体与发布门禁不得继承前述 45 层结果。

## 本轮收口

已再次同步至 `96ee9f33`。46 层完整构建通过后，相同 Cardputer Flash 在
11 键实际 press/release/frame/退出门禁得到 66 项通过；六板准入完成。
冻结最终公开导出后，10 板/11 例共 313 项浏览器检查全部通过，CoreS3 两例
各有分享重开，全部 Worker 在 iframe DOM 真正移除前被独立观察到关闭。
平台 1505 项检查 OK、10 skipped；本轮边界和完整身份移入
[最终证据](../evidence/2026-10-29-wasm-remaining-xtensa/README.md)。
本轮完成固定示例准入与 PR 交付；`UI-02` 的其它应用、性能/长稳、逻辑校准、
新 CPU 目标和正式部署仍按唯一 Backlog 继续，不把这个结果升级为全设备完成。

交付前再次同步 main 至 `75d66458`，保留新增原生 ESP-NOW fabric 与验证记录。
本轮 41 个非文档文件与浏览器门禁版本逐字节一致，源码锁身份不变；最终浏览器
证据仍绑定原执行时的 `96ee9f33` 基线，不把后续原生更新写成浏览器运行结果。
