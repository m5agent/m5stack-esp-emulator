# 最终 main 与原生用户路径交付

日期：`2026-11-14`。本页是日期化证据入口，当前能力和待办仍分别以
[项目状态](../../project-status.md)及[Backlog](../../project-backlog.md)为准。

源码 `70ef503fc2fb8b2c787fa9065e2952f525c40099` 已进入 main，
[同提交 main CI](https://github.com/m5agent/m5stack-esp-emulator/actions/runs/43496500912)
完成通过。原生 C6 与 CoreS3 的部署后验采用同一固定源码，原版应用及完整矩阵
保留各自真实执行提交。以下是 **virtual-device validation**，不是物理硬件测量。

| 范围 | 已执行结果 | 保留边界 |
| --- | --- | --- |
| Nesso 原执行分区 + VFS Pin.irq 探针 | 两轮 32/32、22 次实际输入、一次重置；绿色帧、原 APP 分区不变及 8 个 ZIP 成员核验通过 | 不是全 BIN 未改；不证明 BMI270 IRQ、FT6336 精确时序、NMI 或电气时序 |
| CoreS3 原版云固件 | 握手后至少 195 秒，UI/身份 30/30、5870 次 frame 304、运行错误 0 | 7 次文本心跳、6 次控制 PING/0 PONG，guest 在首次控制 PING 后 120.047286 秒发 FIN；持续连接 FAIL |
| 完整原生回归 | 70/70、每项一次、原应用分区不变并清理 | 实际执行 `0e00cdcb…`，不冒充最终服务或浏览器执行 |
| 原 Mesh A 按键合同 | 150 秒、8/8 及视觉通过；长 A 开菜单、短 A 改变选择 | 不证明区域提交或 LoRa 发包；与另次 B 观察合同不同 |
| 原 Bruce 触摸与复位 | 150 秒、6/6 及视觉通过 | Wi-Fi、攻击或 RF 未验 |
| 原 Honeypot | 180 秒、7/7 配置控制台通过 | 总体 PARTIAL；AP 关联和 HTTP 数据面 NOT RUN |
| 另次 Mesh B 输入观察 | 150 秒、5/6，选择观察断言未满足的原始 FAIL 保留；后续 B 输入唤回可读画面 | 原版选择合同为 A 长/短；该 B 观察不证明按键缺陷，也不改写原始失败 |

完整固件、运行时、原始摘要与 ZIP 哈希见[有界摘要](summary.json)。
永久工作记录：[C6、中断矩阵与原版应用](https://github.com/m5agent/agent-work-logs/tree/02ecde371901c8f97d5746eaab0ee7182b56cf5c/records/esp-emulator/2026-11-14-c6-gpio-irq) ·
[Cloud 身份与最终用户路径](https://github.com/m5agent/agent-work-logs/tree/02ecde371901c8f97d5746eaab0ee7182b56cf5c/records/esp-emulator/2026-11-14-uiflow-cloud-websocket/followups/2026-11-14-identity-capability)。
两者均固定到同一完整归档提交，原始失败与后续结果分别保留。
C6 和 Cloud 均在停止前取得同会话证据，停止后释放本次 guest、Flash 和 lease，
原有历史保留；浏览器也完成清理。Cloud ZIP 没有 Flash 成员，只核原 BIN 与 FF
标准化哈希，不声称 postrun APP 字节读回；实际 NIC argv/eFuse 挂接由执行期 helper
检查，未留 raw argv 供停止后重算，身份收据、eFuse 内容、Ethernet 与 WS 身份可复核。

[完整矩阵原记录](../2026-11-14-c6-gpio-irq/native-matrix/README.md)绑定 `0e00cdcb…`，
与 `014841a8…` 的 523 个相关 Git blob 相同；`014841a8…` 到最终 `70ef503f…`
只有文档改动。原版应用会话同样实际执行于 `0e00cdcb…`，最终身份服务差异由
上表的部署后验单独验证。最早横竖屏观察器失败、不同输入合同下的 Mesh B 失败观察、旧候选网络观察失败
均保留，后续通过不改写旧结果。

本次没有改写原版可执行代码来隐藏故障，也没有提交 Burner。浏览器 WASM 与 Pages
使用独立导出和门禁，现有 WASM 不自动获得本次原生 C6 修复；该范围只由独立发布
证据决定。物理 RF、功耗、电气与远程代码执行不在本页结论中。
