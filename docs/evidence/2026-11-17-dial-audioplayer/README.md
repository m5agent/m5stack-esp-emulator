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

## 2026-11-18 原版音频数据面的复验

在 `5f8e2f8f` 服务和无跟踪的原生 QEMU 上，同一原版 R1F30 在 PORT.B 启动，
产生非黑 240×240 画面。
七曲目索引夹具上电后收到全盘循环指令 `0bf402010002`，原版发出第 1 轨的播放命令。
默认 35 ms 旋转 +3、−2 交付 12、8 条 GPIO 边沿，Unit 收到第 4、2 轨的索引命令。
这段结果验证到选曲和播放控制。见[逐项证据](audio-media-boundary.json)。

独立解码确认有效的 440 Hz、16 kHz 单声道 s16le WAV 上传成功，传给 Unit 的媒体
字段被拒绝（HTTP 400 `invalid_unit_input`）。同一会话读取 `audio.pcm` 和提交
`audio.inject` 均返回 HTTP 409 `audio_unsupported`。这两个接口服务于 Cardputer 系列
的 SoC 音频。证据包含 Unit 状态、UART 控制记录和画面，音频条目为空。首次运行在
来宾完成选曲后，取帧分析因验证环境缺少 Pillow 中断；补齐依赖后重新冷启动完成取证。
两次均已停止会话、释放 Flash 与租约。

按上方方法挂载七曲目索引夹具，上传 0.5 秒的 440 Hz WAV。固定样本按
`round(10000 * sin(i * tau * 440 / 16000))` 写入单声道 s16le WAV。用同一固件
创建会话时，在 Unit 的 `initial` 里加入 `media-artifact-id` 验证 400，再按既有字段
启动正常会话，完成 +3、−2 后调用两个音频接口并导出证据包。U197 的 microSD、
MP3/WAV 解码及 3.5 mm 输出位于 Unit 内。实际音频路径仍需 Unit 媒体与解码后的 PCM 证据。
[U197 官方规格](https://docs.m5stack.com/en/unit/Unit_AudioPlayer) ·
[N9301 UART 协议](https://m5stack-doc.oss-cn-shenzhen.aliyuncs.com/1155/Unit-AudioPlayer-Protocol-CN.pdf)

## 2026-11-18 原版 WAV 输出

原版 R1F30、Dial PORT.B 和独立 Device Service 保持同一路径，改用原生 QEMU
0226 与显式的 WAV 媒体列表。启动及两次编码器动作 +3、−2 后，分别确认第
1、4、2 轨，稳定 PCM 窗与各对应 WAV 字节一致。中央触摸暂停、恢复和按键停止
均经真实 UART，暂停、停止期间采样长度保持固定。短音轨对照核验原版设置的
全盘模式在 EOF 自动推进 1→2→1。

API 样本、频率与同会话 ZIP 逐段校验。格式错误与旧版后端都在分配租约前拒绝，
通过的会话保存证据、关闭来宾并释放 Flash。[有界摘要](wav-playback-summary.json)

验收范围是 Unit 的 16 kHz 单声道 PCM，数据取自模拟 DAC 之前。Unit 内部
FAT、MP3、多目录与物理声音另行验收。

## 2026-11-18 原版保存快照审核

[审核 dry-run 摘要](review-playback-summary.json)固定原版 BIN、描述、原生后端、
有序 WAV 和服务源码。验收为第 1 轨的 PCM 基线、顺时针旋转一格的回执、切换到
第 2 轨后的两段连续 PCM，以及同一证据 ZIP 中相应的原始字节与 Unit UART。
失败对照只改预期主频，权限对照移除音频读取权限。报告分别记录 `PASS`、
`FAIL` 和 `PARTIAL`。本轮是 virtual-device validation。
