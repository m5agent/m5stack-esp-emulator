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

## 原版实际读取 GPIO 的复验

同一原版在 `c53750bf0cc23e717943c6c3c79e49b11e1a227a` 的两次冷启动中
复现快转偶发漏选。原生诊断 QEMU 的 SHA-256 为
`0a4d21d04c16b5ce6be647239b731f2a3e59a7ccbd7904e70d54436a17a37560`。
两个会话均保留 [AudioPlayer PORT.B](../2026-11-17-dial-audioplayer/README.md)
的七首索引曲目和新的有效 N9301 播放命令。

- 默认 35 ms 共 18/18 选对，来宾每个 GPIO 相位都有读回。显式 5 ms 共 15/18
  选对，短转 6/6，整圈 9/12。两种间隔均交付了每格四个正确的 Gray 相位。
  5 ms 组的虚拟边沿间隔为 5.030–10.681 ms。
- 在原版反汇编中，`0x4204de12`、`0x4204de1b` 是分别提取 A、B 的两次
  `GPIO_IN1` 读取。两轮共配对 17,263 组实际寄存器读回，无一跨越相位边沿。
  按原版状态表重算，三次漏选分别得到 −60、+60、−60 个计数，准确对应 UART
  发出的曲目。三次漏选的期望计数分别为 −64、+64、−64。两次冷启动中漏读的
  相位序号不同。

| 冷启动 | 输入 | 未读取的相位序号 | 预期曲目 | 原版实际曲目 |
| --- | --- | --- | --- | --- |
| 1 | −16 @ 5 ms | 35 | 7 | 1 |
| 2 | +16 @ 5 ms | 20、31 | 4 | 3 |
| 2 | −16 @ 5 ms | 45 | 6 | 7 |

每轮先注入 `+3, −2`（默认），`+3, −2`（5 ms），`+2`（默认），`−3`（5 ms），
再将 `+16`（5 ms）、`−16`（默认）、`−16`（5 ms）、`+16`（默认）重复三次。
在 `dial` 的原生 `/api/v1` 会话中省略 `edge_period_ms` 即走默认值。在 GPIO
读取回调中用只读的 TCG 状态定位 guest 指令，以有界缓冲记录虚拟纳秒、相位序号、
CPU 和实际返回的 G41/G40 值。每次动作后比对 `4 × abs(delta)` 个相位以及新的
索引播放 UART 帧。最后补一次默认 `+1` 刷出诊断缓冲，该动作不计入配对结果。
用两个指令的返回值组合相位并重放原版状态表，按七首曲目取模比较 UART 索引。
诊断记录未注入引脚值或改动定时期限；两轮均未丢弃观察数据。

[逐动作摘要](original-pair-summary.json)保留固件、运行时、证据包和尾帧哈希。
两轮均先导出证据包，再停会话、释放 Flash 和租约并关闭独立服务。由实际读取
可解释这三次漏选。5 ms 整圈仍为 PARTIAL，原版取样间隔的成因、无诊断观察器时的
失败比例、浏览器和同一 BIN 的实物结果均有待验证。
[官方 M5Dial Encoder 1.0.3 参考实现](https://github.com/m5stack/M5Dial/blob/533c9d0198e72621d55a4d35f726d3d53a7e1431/src/utility/Encoder.h)
也使用分开的寄存器读取和相位状态表；以上原版指令和计数均来自 BIN 的读回。

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
