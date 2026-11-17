# Dial 快速旋转时序

2026-11-18，virtual-device validation。旧运行时绑定
`a0fa14ae26f047fe4bef2c53681f9ea61b13eb8e`。所有固件通过独立
Device Service 原生会话运行。对照包含 ESP-IDF GPIO ISR 夹具、
以同一官方 UIFlow2 底包合成的 RotaryIRQ 探针和未修改的 vinylM5Dial 1.0 R1F30。

## 原生边沿

旧模型以当前虚拟整毫秒加间隔计算下一个期限，丢掉当前时间的小数。
原生时钟日志显示，标称 5 ms 的间隔最短为 4.527 ms，126 个间隔中
15 个短于请求值。35 ms 组有 35/126 短于请求值。补丁 0220 将旋钮的
首次及后续期限都改为从当前虚拟纳秒起算。匹配的诊断运行时在 5 ms
和 35 ms 各有 0/126 个短间隔，均为实际 GPIO 正反相序。
Device Service 仍以毫秒接受输入间隔。

关闭边沿日志后，在纯候选运行时的双轮复验中，GPIO ISR 记录了全部
512 条正确相序。保留首轮的负对照，其中 64 条回调仍到达，但一个回调
读到了后一相位。原生时间和来宾 IRQ 回调的实际读引脚时间分别取证。

## UIFlow2 驱动

同一未加回调采样的 RotaryIRQ 探针在旧版和新版的 5 ms 整圈均只读成 ±8。
35 ms 对照在旧版有 4/4 精确，纯候选版有 3/4 精确，另一次读成 −15。
诊断探针每组都捕获 64 个回调，记录约 27 ms 的回调间隔与重复、
跳变的实时 A/B 读数。仅省略计数变化后的同步 LCD 重画并保留
20 ms 前台循环，旧版和新版的 5 ms 正反整圈均准确。
[官方 GPIO 回调绑定](https://github.com/m5stack/uiflow-micropython/blob/64c3ce1346ceb4d404c1c3d74e66fed7eadb4d90/m5stack/libs/driver/rotary/rotary_irq_esp.py)
[官方 Rotary 状态机](https://github.com/m5stack/uiflow-micropython/blob/64c3ce1346ceb4d404c1c3d74e66fed7eadb4d90/m5stack/libs/driver/rotary/rotary.py)

## 未修改的 vinylM5Dial 原版

两次冷会话均使用原版 SHA-256
`7778656ee942bb5e87fbc780955c452f752059c9cf9325d7e026b83ec6c7ffaf`，
经 PORT.B 同一索引 Unit。每个会话执行同一组 10 次有符号动作和夹具读回。
旧版总体 17/20，5 ms 整圈 2/4。纯候选总体 20/20，5 ms 整圈 4/4。
每次成功由新出现的有效 N9301 索引播放命令绑定，原版画面也保持非黑。
以上结论限于这两轮。此前原版漏选曲与本次 UIFlow2 重画负对照继续保留。

## 复现

按同一硬件路径复现时，通过独立 Device Service 注入
`{"kind":"encoder","delta":16,"edge_period_ms":5}`，再执行反向及
35 ms 对照。等 `/machine/encoder` 的 `delivered-detents` 到达
目标，并校验 `gpio-edges` 单圈增加 64。GPIO ISR 夹具读 G41/G40
共用输入寄存器的当前相位及 `esp_timer_get_time()`。复用
`tests/uiflow2/dial_peripherals/` 的官方驱动探针作来宾计数。
原版通过 PORT.B AudioPlayer 的索引播放 UART 帧断言选曲。

[具体验证及清理记录](summary.json)。实体旋钮的电气、实际音频、浏览器
和实机对照为 NOT RUN。
