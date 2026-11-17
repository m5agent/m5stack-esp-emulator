# 原版 vinylM5Dial 画面和操作复验

2026-11-17，virtual-device validation。原版 vinylM5Dial 1.0 R1F30 BIN
SHA-256 为 `7778656ee942bb5e87fbc780955c452f752059c9cf9325d7e026b83ec6c7ffaf`。
通过独立 Device Service 在 M5Dial 挂载 PORT.B Unit AudioPlayer 和 7 个索引曲目。

旧运行时上，原版会播放并正确切歌，240×240 帧为全黑。隔离诊断从原版
USB Serial/JTAG 读到渲染任务已启动及递增的应用帧计数，GP-SPI 传输计数为 0。
同一诊断设置下，仅给 GC9A01 接入原有 GPIO 三线面板适配器，随后观察到
11,247 次 GP-SPI 传输及非黑帧。板级接线为 CS7、SCK6、DC4、SDA5，
面板通过该路径参与初始化探测，后续画面走原有 GP-SPI 控制器。
[M5Dial 板型与引脚](https://docs.m5stack.com/en/core/Dial)

最终运行时仅包含板级接线修复，实测默认时钟及关闭诊断的原版。自动播放第 1 轨，
10 次有符号旋转均收到目标索引播放帧，包括 5 ms 和 35 ms 各一次正反向整周旋转，
每圈 64 条 GPIO 边沿。另一次完整序列中，−16@5 ms 的 64 条边沿已交付，
原版未发目标选曲命令，快速整周的应用层稳定性保持 PARTIAL。中点两次按下与释放
分别暂停、恢复，屏幕上/下方触摸
令音量 11→12→11，物理按键 A 停止再播放。用 Unit 实际接收的 UART 命令
和状态转换核对，原版取到 240×240 非黑画面。同一最终运行时启动官方
Dial UIFlow2，继续观察到非黑画面与 GP-SPI 传输。

- [固件、运行时、ZIP 指纹及分组结果](summary.json)
- [精确 BIN 复现命令](../../../tests/units/dial_audioplayer_probe/README.md)

每轮取证后停止，保留会话记录并释放可写 Flash。Unit 覆盖控制协议和索引夹具。
实体 SD、实际解码/声音、单目录夹具外的切换、浏览器 WASM、真机和 Burner
提交均为 NOT RUN。
