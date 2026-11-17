# Cardputer ADV Flash 容量准入

[Issue #234](https://github.com/m5agent/m5stack-esp-emulator/issues/234) 的原版合并 BIN 为 2,041,968 字节，bootloader 头和分区表都要求 16 MiB。Cardputer ADV 档案为 8 MiB。

- 基线 Device Service 接受原 BIN，归一化为原始字节加 `0xff` 到 8 MiB。原生来宾报告 Flash probe 容量冲突和 `ESP_ERR_FLASH_NOT_INITIALISED`，取证后停止并释放租约。
- 候选的组合和导入路由均返回 HTTP 409 `firmware_flash_contract_mismatch`。保存快照的审核以 `E_STATIC` 结束，详情保留两种容量，无来宾会话或 Burner 提交。
- 同一候选与 QEMU 接受官方 Cardputer ADV 8 MiB UIFlow2 对照，实际来宾输出 240×135 非黑画面并释放租约。

[结构化摘要](summary.json)记录源码文件、BIN、运行时与取证哈希。物理烧录 `NOT RUN`。容量检查覆盖结构有效的 ESP 分区表及其匹配 bootloader。
