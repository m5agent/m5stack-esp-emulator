# UIFlow工作台：携已知问题部署

日期与最近核对：2026-11-04。**DEPLOYED_WITH_KNOWN_FAILURES**。
用户明确要求先合并部署、问题保留记录；这不是完整生产功能门禁通过。

[正式站点](https://m5agent.github.io/m5stack-esp-emulator/)已由
[prepared-preview工作流](https://github.com/m5agent/m5stack-esp-emulator/actions/runs/41816252534)
于10:45:44Z（UTC）完成部署，工作流结论success。
[summary.json](summary.json)绑定MAIN23d源码/树、MF685、fa6/96运行时、归档与原收据SHA。
149,451,828字节归档上传后下载SHA相同；2,130个声明HTTPS资产共251,196,202字节
逐一比对length/SHA通过，向量SHA为90ebdb820deeded74cc3495066c5cda13a028239e1bb61e700f20d16f6031a94。
资产一致性不等于guest功能通过；本次文档维护没有新增guest或构建。

## 独立HTTPS子集

实际首6例为功能并发（最多2个guest），不是性能样本。六例均normal QMP0、零forced/fallback，
32个实际CDP Worker在context关闭前全部消失；三editor另有held-iframe围栏，三buttons该围栏NOT CAPTURED。
终态父报告9,038B，SHA103eba714eabc894099d15539cbbe8f9fa26e945b14ee3552e17d3ec3969be72；
逐例raw byte/SHA、固件、控制脚本及实际执行策略见摘要。没有用本子集覆盖原hosted或Lite复位FAIL。

## 已知失败与验收边界

- [部署前资格失败](../2026-11-04-pages-rollout-qualification/README.md)原样保留：hosted Matrix600秒未app-ready；同导出本地计划16PASS、Lite1FAIL、43NOT RUN。
- Lite精确oneInsn在代码后的硬reset仍触发Core1 PIF；`RUNTIME-07`、`RUNTIME-08`、`RUNTIME-09`根因继续OPEN。没有C/固件/时钟修复声明。
- [此前V6/R8完整本地通过](../2026-11-04-browser-uiflow-all19-acceptance/README.md)保留其日期和身份，不能转授本次导出或线上结果。
- 独立HTTPS首6例已终态 **SUBSET_PASS / full_scope=false**：Matrix、StickC Plus、CoreS3各editor+buttons共222检查、35程序、6次未改默认Run和10次250ms输入通过；其余34例NOT RUN/HOLD，不授全19线上通过。v4诊断不是发布修复或验收证据。

部署前证据中的“未部署/站点未变”是其当时检查点事实；本页追加后续部署事实，不改写旧JSON。
部署成功及所有资产匹配不关闭标准hosted失败、本地复位缺口、长期稳定性或性能边界；
不授物理硬件或网络/安全问题结论。
