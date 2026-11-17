# CardputerDict 原版 SD 词库复验

日期 `2026-11-17`。Virtual-device validation。

普通 Cardputer 的原版 CardputerDict 0.6.4 从 FAT32 SD 读取自编的
StarDict 词库并显示词条 `zorbax` 的释义 `MINT CACHE 7319`。独立
Device Service 和 saved-snapshot 审核的 Enter 后帧 SHA 一致。缺少
词义正文和无卡的同原版对照回退到内置演示。完整词库、缺正文和无卡
分别产生 131、82、0 条 SPI CMD17 读命令。审核启动与 60 秒观察通过，
整体仍为 `SIM_PARTIAL`。证据 ZIP、阶段帧、原版和运行时均在
[摘要](summary.json)中按 SHA-256 记录。未提交 Burner。

使用 UTF-8 的 `ecdict.ifo`、`ecdict.idx`、`ecdict.dict`，放在
FAT32 根目录的 `dictionaries` 下，文件后缀须小写。词库内容由验收自编。
[发布者固定版本的加载代码](https://github.com/RadioDisney/CardputerDict/blob/4b69cef2c59ef443eea191aa8e1b6bbef6178595/src/main.cpp#L355)

0.3.0 未取得可核对的原版，故未执行。朗读、网络、ADV 和实体设备未验证。
