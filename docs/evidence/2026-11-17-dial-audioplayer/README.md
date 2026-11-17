# Dial Unit AudioPlayer UART 原生复验

Virtual-device validation，候选原生 Xtensa 构建和独立 Device Service。
[精确哈希与结果](summary.json)包含 Dial 两个端口、无介质负控和原版
vinylM5Dial 1.0 的实际 GPIO、UART 与取帧记录。
[复现方法](../../../tests/units/dial_audioplayer_probe/README.md)。

官方 UIFlow2 驱动在 PORT.A、PORT.B 均发出 32 个有效命令并读取 30 个回复，
验证了介质识别、曲目查询与切换、播放/暂停/恢复/停止、音量、循环模式
和异常帧拒绝。空介质时两个请求都未收到回复。

原版 R1F30 在 PORT.B 查询介质和曲目数、设定模式与音量，自动选择并播放第
1 轨。普通 Device Service 旋钮输入 +3、−2 分别交付 12、8 条 GPIO 边沿，
原版发送索引播放命令达到第 4、2 轨。串口证据记录 UART0 的 ROM 行，原版
标明其应用日志使用 USB CDC。取帧持续全黑，较早的按键、中央和上方触摸探测
未触发播放状态或音量变化。

这里的播放状态来自 N9301 控制协议。实体 SD、音频解码、实际声音、屏幕修复、
物理设备和浏览器均未验收。原版整体保持 `SIM_PARTIAL`。
