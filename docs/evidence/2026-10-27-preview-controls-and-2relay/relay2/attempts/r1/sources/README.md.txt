# 2Relay CoreS3 r1 源码重构快照

此目录不是运行当时捕获的原始文件副本。三份文件由后续冻结版本逆向撤回本轮
黑色像素 oracle / rawcleanup 保留的窄修复而重构；仅当 SHA256 与未修改的
`.work/preview-2relay-cores3-r1-20261027/report.json` 中 `source_sha256`
逐字匹配时才写入，并标记 `reconstructed`。不匹配者在 manifest 中明确 `missing`。

原 r1 raw 目录未修改；最新版源文件也未修改。本目录保存旧错误 oracle 与原清理
报告缺口，供归档重现失败原因，不能当作功能 PASS 或重新执行授权。

精确来源、重构方法、每文件期望/实际摘要与来源报告摘要见 `manifest.json`。
