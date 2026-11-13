# Pages 发布与 HTTPS 限定验收

日期：`2026-11-14`。本页记录 **virtual-device validation** 的本地完整资格、正式发布与 HTTPS 两例限定验收，
当前能力仍以[项目状态](../../project-status.md)为准，流程见[Pages 部署](../../pages-deployment.md)。

执行源码为 `70ef503fc2fb8b2c787fa9065e2952f525c40099`，导出 manifest
`54fc8d8fe023ef0d86e3bfdea3d3db37599a2f59404c54fdb8920d466bd14a8c`。
该导出的本地完整串行门禁 **72/72 PASS**、2,993 项检查通过；所有子进程
退出码均为 0，没有过滤设备、替换旧结果或未执行项目。

| 本地执行范围 | 结果 |
| --- | --- |
| 23 款设备的默认 UIFlow 编辑器与普通输入 | 23 + 23 例通过 |
| Cardputer ADV 完整键盘与 StackChan 三区触摸 | 1 + 1 例通过 |
| 固定示例，包括 CoreS3 原参考版与 SDK 候选 | 24 例通过 |
| 独立原版 CoreMatrix 客体前置验证 | 1 例通过；8 次输入边沿、9 次同会话帧观察 |
| Canvas 与 COI 浏览器前置控制 | 5 + 13 项 host 控制；不计入 guest 用例 |

合计 75 份子报告，其中 73 份 guest 用例报告、2 份 host 控制报告。
CoreS3 固定用例中的重新打开客体属于同一用例的子步骤，不另增用例基数。
COI 的 4 个原上游失败是预期负控，不改写为成功客体。
执行器、同一固件/ROM 收据、实际输入、串口、帧及 Worker 退出均已核对。
Chrome `157.0.8103.52` 的前后可执行文件 SHA 相同，393 次采样一致；两份
CoreS3 固定报告及 COI 报告自身未记录版本，仍为 `NOT_RECORDED`，由独立
外层身份记录约束调用，未回填原报告。Stock CoreMatrix 的 iframe 移除前
pthread 围栏仍为 `NOT CAPTURED`，移除后的 CDP 退出计数通过。

发布包 SHA256 为
`8c25e92e124fc0d323afd51b13c8ce05719e54167c1cbc5d1a3507eab28b9b98`，
长度 `186574444` 字节；已重新计算实际压缩包字节哈希。导出含 manifest 在内
共 2,179 个文件，不打包原固件。完整身份及资格收据哈希见[有界摘要](summary.json)。
[永久资格记录](https://github.com/m5agent/agent-work-logs/tree/6f06108d3b68b35f679e3c37aebeac60972434fe/records/esp-emulator/2026-11-14-uiflow-cloud-websocket/followups/2026-11-14-pages-qualification)固定到公开归档完整提交，包含逐例有界证据及复现入口。

[Prepared 发布工作流](https://github.com/m5agent/m5stack-esp-emulator/actions/runs/43511659965)
已完成，deployment `7776988548` 为 success。正式 HTTPS 的 2,179 个文件、合计
304,564,570 字节逐项匹配同一导出，含 42 个 runtime 资产；0 错误、0 重试。
清单在资产读回前后均符合预期。随后在正式 HTTPS 地址执行两个 CoreS3 示例，
原参考示例 49/49、正常时钟 SDK 候选 34/34，共 83 项检查通过，0 错误。
实际 DOM 触摸到 LVGL Clicks、PIR 串口状态、原始 framebuffer、暂停/恢复及
正常停止均由原始报告验证；两例各包含冷启和重新打开，共四次生命周期，仍只计两例。
10 份原始帧哈希匹配，正常退出的 Worker 无 fallback；终态无剩余客体或浏览器进程。
执行期间没有 Device Service 或本机服务请求。

HTTPS 外层 Chrome 身份前后一致，20 次可执行文件采样均匹配；两个子报告自身
仍为版本 `NOT_RECORDED`，没有把外层版本回填。固件与 ROM SHA 绑定实际启动收据，
未做运行后可变 Flash 读回。线上两例是 **subset PASS**，正式托管完整门禁
**NOT RERUN**。旧 hosted FAIL/PARTIAL、之前未完成
导出轮次，以及把正在运行的 keyboard 检查点误读为终态失败的观察器纠正均保留。

42 份既有 WASM/runtime 资产与先前发布字节完全相同，没有在此轮重建。
[原生 C6 GPIO 修复](../2026-11-14-c6-gpio-irq/README.md)没有因此进入 WASM，
[原生用户路径后验](../2026-11-14-native-identity-delivery/README.md)也不转授浏览器联网或其它外设能力。
