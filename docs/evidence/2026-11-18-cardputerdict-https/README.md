# CardputerDict 0.6.4 原版发音的隔离复验

2026-11-18。Virtual-device validation，设备为初代 Cardputer K132。
使用发布者的原版合并 BIN 和一个仅含 `hello` 词条的 FAT32 夹具。
初始 SD 没有音频。两轮使用同一份 BIN、规范化 Flash、ROM 和夹具字节。
[发布者固件](https://github.com/RadioDisney/CardputerDict/releases/tag/v0.6.4) ·
[发音和证书策略](https://github.com/RadioDisney/CardputerDict/blob/4b69cef2c59ef443eea191aa8e1b6bbef6178595/src/pronunciation.cpp)

使用 Linux arm64 原生 QEMU、`qemu-wifi` 和 `generic-observe`。
在独立 Device Service 会话中设定开放测试 AP，并使用实际键盘 Fn+W
保存配置。查询 `hello` 后按 Fn+P。为公开校时与发音服务分别设置
`network.dns_host_records` 的确定地址，沿用 namespace 及 nftables
默认拒绝。允许路径只授权校时 UDP/123 和发音 TCP/443。对照把发音
目标端口改为 444，同时保留相同的 DNS、固件、输入和校时许可。
每次复验前向发布方 DNS 核对地址并检查证书有效期，当前端点相关
配置只在测试会话内使用。通过标准 API 取得证据 ZIP 后停止并保留会话。
[API](../../device-service-api.md) ·
[结构化证据](summary.json)

允许轮核对了匹配的 SNTP 请求和回复、TLS 会话、10,605 字节发音
MP3 缓存，以及普通 `audio.pcm` 的非零输出。证据 ZIP 中的
PCM 长度为 61,952 字节，停机后经 API 读回 66,560 字节。调用请求
使用默认 I2S 行为。拒绝轮收到同样的 DNS 和校时应答，抓包显示出站
TCP/443 SYN 无对端响应，无音频缓存或 PCM。两轮清除命名空间、临时
NAT 和租约，上传的原件与 SD 夹具保持原样。

1.88 的服务在相同的外部地址策略下停在受理阶段。早期候选有一次
下载成功但清理回执未完成，并有无来宾触发的按键观察超时。单独的
I2S 诊断开关先验证了播放，再通过默认 API 完成同路径复验。
Reviewer 0.21.0 使用同一原版、同一 SD 夹具与同一 Linux 原生路径执行
保存快照 dry-run。放行轮为 `PASS`，同一会话保存了 10,605 字节 MP3
缓存，停机后的 PCM API 与证据 ZIP 均读回同一份 84,992 字节音频。
拒绝轮为 `POLICY_DENIED`，保留 DNS 与校时并记录 TCP/443 请求、零
回应、零缓存和零 PCM。缺少 Linux 网络隔离权限时返回准入
`PARTIAL`，分配会话数为零。Reviewer 0.20 的通用网络待复核结果保留。
[Reviewer 保存快照结果](reviewer-saved-snapshot-summary.json)

常驻 Linux 审核 worker 的持续运行、ADV 原版联网、实体音频和浏览器
仍待验收。Burner 提交数为零。
