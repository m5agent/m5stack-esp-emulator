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

0.3.0 未取得可核对的原版，故未执行。0.6.4 这轮的朗读、网络、ADV 和实体设备未验证。

## Cardputer ADV 0.5.0

日期 `2026-11-18`。Virtual-device validation。

三个独立原生 Device Service 会话使用同一原版 0.5.0，在 Cardputer ADV 上输入
`zorbax` 并按 Enter。完整词库的屏幕显示词条和释义 `MINT CACHE 7319`，
缺少词义正文和无卡时两个对照均未显示该释义。完整词库、缺正文和无卡分别
记录 128、79、0 条实际 SPI CMD17 读取，收据中的次数与同会话 ZIP 内的
控制器日志一致。

原版 BIN 原样补齐至 8 MiB。原始及规范化 Flash、FAT32 夹具和 OCR、帧、
运行时及三份证据 ZIP 的哈希均可核对。三个会话释放 Flash 和租约，各自的
隔离服务已退出。保存快照审核、真机和浏览器为 `NOT RUN`。未提交 Burner。
[Cardputer ADV 0.5.0 证据](adv-0.5.0-summary.json)
